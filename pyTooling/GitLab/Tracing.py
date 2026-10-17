# ==================================================================================================================== #
#             _____           _ _               ____ _ _   _          _                                                #
#  _ __  _   |_   _|__   ___ | (_)_ __   __ _  / ___(_) |_| |    __ _| |__                                             #
# | '_ \| | | || |/ _ \ / _ \| | | '_ \ / _` || |  _| | __| |   / _` | '_ \                                            #
# | |_) | |_| || | (_) | (_) | | | | | | (_| || |_| | | |_| |__| (_| | |_) |                                           #
# | .__/ \__, ||_|\___/ \___/|_|_|_| |_|\__, (_)____|_|\__|_____\__,_|_.__/                                            #
# |_|    |___/                          |___/                                                                          #
# ==================================================================================================================== #
# Authors:                                                                                                             #
#   Patrick Lehmann                                                                                                    #
#                                                                                                                      #
# License:                                                                                                             #
# ==================================================================================================================== #
# Copyright 2026-2026 Patrick Lehmann - Bötzingen, Germany                                                             #
#                                                                                                                      #
# Licensed under the Apache License, Version 2.0 (the "License");                                                      #
# you may not use this file except in compliance with the License.                                                     #
# You may obtain a copy of the License at                                                                              #
#                                                                                                                      #
#   http://www.apache.org/licenses/LICENSE-2.0                                                                         #
#                                                                                                                      #
# Unless required by applicable law or agreed to in writing, software                                                  #
# distributed under the License is distributed on an "AS IS" BASIS,                                                    #
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.                                             #
# See the License for the specific language governing permissions and                                                  #
# limitations under the License.                                                                                       #
#                                                                                                                      #
# SPDX-License-Identifier: Apache-2.0                                                                                  #
# ==================================================================================================================== #
#
"""
Read the timing of a GitLab CI/CD pipeline into a software execution trace.

A pipeline becomes a :class:`~pyTooling.Tracing.Trace`, and each job a :class:`~pyTooling.Tracing.Span`. The time a job
waited for a runner is a separate timespan in front of the job. The instances of a matrix are grouped below a timespan
named like the job, and the jobs of a child pipeline below a timespan named like the trigger job.

.. code-block:: python

   from os import getenv
   from pyTooling.GitLab.Tracing import PipelineReader

   reader = PipelineReader("gitlab-org/gitlab-development-kit", token=getenv("GITLAB_TOKEN"))
   trace = reader.ReadPipeline(2954836704)
   print("\\n".join(trace.Format()))

.. hint::

   See :ref:`high-level help <VIS/PipelineTrace>` for explanations and usage examples.
"""
from datetime              import datetime, timedelta
from typing                import Any, ClassVar, Iterable, Mapping, Optional as Nullable, Self, Union

from pyTooling.CI          import Base, JobGroup, JSONObject, Matrix
from pyTooling.Common      import getFullyQualifiedName
from pyTooling.Decorators  import export
from pyTooling.GitLab      import DownstreamPipeline, GitLabError, Job, MatrixJob, Pipeline, ProjectClient, Status
from pyTooling.MetaClasses import ExtendedType
from pyTooling.REST        import RESTError
from pyTooling.Tracing     import Span
from pyTooling.Tracing.CI  import OTLP, Result
from pyTooling.Tracing.CI  import JobSpan as CIJobSpan, MatrixSpan as CIMatrixSpan
from pyTooling.Tracing.CI  import PipelineTrace as CIPipelineTrace, QueuedSpan as CIQueuedSpan
from pyTooling.Tracing.CI  import WorkflowSpan as CIWorkflowSpan


@export
class GitLab(metaclass=ExtendedType, slots=True):
	"""
	Attribute keys naming what only GitLab CI/CD reports, beside the keys of :class:`~pyTooling.Tracing.CI.OTLP`.

	The nesting mirrors the key itself, as it does there: :attr:`GitLab.Runner.Tags` spells ``'gitlab.runner.tags'``.
	"""

	Status: ClassVar[str] = "gitlab.status"  #: GitLab's own status, next to the result it maps to.

	class Pipeline(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming a pipeline."""

		IID:    ClassVar[str] = "gitlab.pipeline.iid"     #: The pipeline's number within its project.
		Source: ClassVar[str] = "gitlab.pipeline.source"  #: What started the pipeline, e.g. ``'push'``.

	class Project(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming a project."""

		ID: ClassVar[str] = "gitlab.project.id"  #: GitLab's identifier of the project.

	class Job(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming a job."""

		Stage:         ClassVar[str] = "gitlab.job.stage"           #: The stage the job is listed in.
		AllowFailure:  ClassVar[str] = "gitlab.job.allow_failure"   #: Whether the job may fail, its pipeline not.
		FailureReason: ClassVar[str] = "gitlab.job.failure_reason"  #: Why the job failed, e.g. ``'script_failure'``.

	class Matrix(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming a matrix."""

		Dimensions: ClassVar[str] = "gitlab.matrix.dimensions"  #: One instance's values, e.g. ``['3.14', 'linux']``.

	class Runner(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming the runner a job ran on."""

		ID:   ClassVar[str] = "gitlab.runner.id"    #: GitLab's identifier of the runner.
		Tags: ClassVar[str] = "gitlab.runner.tags"  #: The tags the job asked for, e.g. ``['saas-linux-small-amd64']``.

	class Downstream(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming a downstream pipeline."""

		ID:        ClassVar[str] = "gitlab.downstream.id"          #: GitLab's identifier of the downstream pipeline.
		ProjectID: ClassVar[str] = "gitlab.downstream.project_id"  #: GitLab's identifier of its project.

	class Trigger(metaclass=ExtendedType, slots=True):
		"""Attribute keys naming the trigger job, which started a downstream pipeline."""

		ID:     ClassVar[str] = "gitlab.trigger.id"      #: GitLab's identifier of the trigger job.
		Status: ClassVar[str] = "gitlab.trigger.status"  #: The trigger job's status.
		URL:    ClassVar[str] = "gitlab.trigger.url"     #: The trigger job's address.


@export
def runnerCategory(span: Span) -> str:
	"""
	Span category naming the runner a timespan ran on, for :class:`~pyTooling.Tracing.Render.GanttLayout`.

	The runner is the first tag of the timespan or its nearest ancestor, e.g. ``saas-linux-large-amd64``; a job without
	tags is categorized by the runner's description, :data:`OTLP.CICD.Worker.Name <pyTooling.Tracing.CI.OTLP>`.

	:param span: The timespan.
	:returns:    The category, or the empty string if neither the timespan nor an ancestor names its runner.
	"""
	current: Nullable[Span] = span
	while current is not None:
		if GitLab.Runner.Tags in current and len(tags := current[GitLab.Runner.Tags]) > 0:
			return str(tags[0])
		elif OTLP.CICD.Worker.Name in current:
			return str(current[OTLP.CICD.Worker.Name])

		current = current.Parent

	return ""


@export
class GitLabTimespanMixin(metaclass=ExtendedType, mixin=True):
	"""
	Mixin-class for a timespan built from :mod:`pyTooling.GitLab`'s model of a pipeline.

	It holds what every flavour needs to read that model: the result an element's outcome is, and the span a group's
	contents have. Everything else the model answers itself - the order its elements are in, and the times of a
	downstream pipeline, which contain the jobs of its child pipeline.
	"""

	@staticmethod
	def _Result(element: Base) -> Nullable[Result]:
		"""
		Return the CI/CD result of an element of the model.

		The result is the member of the same value as the element's :attr:`~pyTooling.CI.Base.Outcome`. A GitLab
		status is mapped onto an outcome by :meth:`Status.ToOutcome <pyTooling.GitLab.Status.ToOutcome>`.

		:param element: The pipeline, job or downstream pipeline.
		:returns:       The CI/CD result, or ``None`` while the element hasn't ended.
		"""
		if element.Outcome is None:
			return None

		return Result(element.Outcome.value)

	@staticmethod
	def _NotBefore(end: Nullable[datetime], begin: datetime) -> Nullable[datetime]:
		"""
		Clamp an end time so it doesn't precede a begin time.

		:param end:   Optional, the end time. Default: ``None``.
		:param begin: The begin time.
		:returns:     The end time, but not before the begin time.
		"""
		return None if end is None else max(end, begin)

	@staticmethod
	def _Value(status: Nullable[Status]) -> Nullable[str]:
		"""
		Return the value of a status, as GitLab reports it.

		:param status: Optional, the status. Default: ``None``.
		:returns:      The status' value, or ``None`` if there is none.
		"""
		return None if status is None else status.value

	@staticmethod
	def _NotBeforeParent(begin: datetime, parent: Span) -> datetime:
		"""
		Clamp a begin time so it doesn't precede the begin of the parent timespan.

		:mod:`pyTooling.Tracing` requires a timespan to lie within its parent. GitLab reports a job's times in
		milliseconds, but the time it was queued as a duration, so a waiting timespan may reach a moment before the
		timespan holding it.

		:param begin:  The begin time.
		:param parent: The parent timespan.
		:returns:      The begin time, but not before the parent's.
		"""
		if parent.StartTime is None or begin >= parent.StartTime:
			return begin

		return parent.StartTime

	@staticmethod
	def _Earliest(times: Iterable[datetime]) -> Nullable[datetime]:
		"""
		Return the earliest of some times.

		:param times: The times.
		:returns:     The earliest time, or ``None`` if there is none.
		"""
		return min(times, default=None)

	@staticmethod
	def _QueueBegin(job: Job) -> Nullable[datetime]:
		"""
		Return when a job started waiting for a runner, by the time GitLab reports it was queued.

		:param job: The job.
		:returns:   The time, or ``None`` if the job hasn't started, was skipped, or wasn't queued.
		"""
		if job.StartedAt is None or job.QueuedDuration is None or job.QueuedDuration <= 0.0 or job.Status is Status.Skipped:
			return None

		return job.StartedAt - timedelta(seconds=job.QueuedDuration)

	@classmethod
	def _GroupTimespan(cls, group: JobGroup) -> tuple[Nullable[datetime], Nullable[datetime]]:
		"""
		Return the timespan of a group, which holds the time its jobs were queued too.

		A group begins when it or its first element started, or earlier, when a job was queued for a runner before. A group
		reporting no start - a downstream pipeline whose payload wasn't read - begins at its creation. A group nothing of
		which started - e.g. a matrix of jobs waiting to be started by hand - has nothing to place on a timeline.

		:param group: The group - a pipeline, a downstream pipeline or a matrix.
		:returns:     When the timespan begins and ends, each ``None`` if there is nothing to place on a timeline
		              respectively while it is still running.
		"""
		begins = [queueBegin for job in group.IterateJobs() if (queueBegin := cls._QueueBegin(job)) is not None]
		for started in (group.StartedAt, group.ContentsStartedAt):
			if started is not None:
				begins.append(started)

		if len(begins) == 0:
			if not group.IsReported or group.CreatedAt is None:
				return None, None

			begins.append(group.CreatedAt)

		begin = min(begins)

		return begin, cls._NotBefore(group.CompletedAt, begin)

	@classmethod
	def _AddContents(cls, group: JobGroup, parent: Span) -> None:
		"""
		Add the jobs, matrices and downstream pipelines of a group to a timespan, in the order they were created.

		:param group:  The group - a pipeline, a downstream pipeline or a matrix.
		:param parent: The timespan the group's contents are added to.
		"""
		for item in group.IterateElements():
			if isinstance(item, Job):
				JobSpan.FromJob(item, parent)
			elif isinstance(item, Matrix):
				MatrixSpan.FromGroup(item, parent)
			else:
				DownstreamSpan.FromDownstreamPipeline(item, parent)


@export
class QueuedSpan(CIQueuedSpan, GitLabTimespanMixin):
	"""The timespan a GitLab job waited for a runner, in front of the job's own timespan."""

	@classmethod
	def FromJob(cls, job: Job, begin: datetime, started: Nullable[datetime], parent: Span) -> Self:
		"""
		Build the timespan a job waited for a runner.

		:param job:     The job that waited.
		:param begin:   When the job started waiting for a runner.
		:param started: Optional, when the job started, or ``None`` while it is still waiting.
		:param parent:  The timespan of the trace, matrix or downstream pipeline containing the job.
		:returns:       The waiting timespan.
		"""
		begin = cls._NotBeforeParent(begin, parent)

		return cls(
			f"{job!s} (queued)",
			begin,
			cls._NotBefore(started, begin),
			parent=parent,
			taskName=job.QualifiedName,
			attributes={GitLab.Runner.Tags: list(job.Tags)}
		)


@export
class JobSpan(CIJobSpan, GitLabTimespanMixin):
	"""The timespan of a GitLab job, from the moment it started on a runner until it completed."""

	@classmethod
	def FromJob(cls, job: Job, parent: Span) -> Nullable[Self]:
		"""
		Build the timespans of a job: the time it waited for a runner, and the job itself.

		GitLab creates every job of a pipeline when the pipeline is created, so the time between a job's creation and
		its start is mostly the time it waited for the jobs it depends on. The waiting timespan is therefore the time
		GitLab reports the job was queued for a runner - :attr:`~pyTooling.GitLab.JobMixin.QueuedDuration` - right in
		front of its start. A job not yet started has no timespan.

		:param job:    The job.
		:param parent: The timespan of the trace, matrix or downstream pipeline containing the job.
		:returns:      The job's timespan, or ``None`` if the job hasn't started.
		"""
		started =   job.StartedAt
		completed = job.CompletedAt

		if job.Status is Status.Skipped:
			# A skipped job neither waited for a runner nor ran on one: it is placed at the moment it was skipped.
			if (skippedAt := started if started is not None else completed) is None:
				return None

			begin = cls._NotBeforeParent(skippedAt, parent)
			end =   begin
		elif started is None:
			return None
		else:
			if (queueBegin := cls._QueueBegin(job)) is not None:
				QueuedSpan.FromJob(job, queueBegin, started, parent)

			begin = cls._NotBeforeParent(started, parent)
			end =   cls._NotBefore(completed, begin)

		attributes: dict[str, Any] = {
			GitLab.Status:            cls._Value(job.Status),
			GitLab.Job.Stage:         job.Stage,
			GitLab.Job.AllowFailure:  job.AllowFailure,
			GitLab.Job.FailureReason: job.FailureReason,
			GitLab.Runner.ID:         job.RunnerID,
			GitLab.Runner.Tags:       list(job.Tags)
		}
		if isinstance(job, MatrixJob):
			attributes[GitLab.Matrix.Dimensions] = [str(value) for value in job.Dimensions.values()]

		return cls(
			str(job),
			begin,
			end,
			parent=parent,
			taskName=job.QualifiedName,
			runID=None if job.ID is None else str(job.ID),
			runURL=None if job.URL is None else str(job.URL),
			result=cls._Result(job),
			workerName=job.RunnerDescription,
			attributes=attributes
		)


@export
class MatrixSpan(CIMatrixSpan, GitLabTimespanMixin):
	"""The instances a matrix produced, grouped into one timespan."""

	@classmethod
	def FromGroup(cls, group: Matrix, parent: Span) -> Nullable[Self]:
		"""
		Build the timespan of a matrix and everything below it.

		:param group:  The matrix.
		:param parent: The timespan containing the matrix.
		:returns:      The matrix' timespan, or ``None`` if no instance of it started.
		"""
		begin, end = cls._GroupTimespan(group)
		if begin is None:
			return None

		begin = cls._NotBeforeParent(begin, parent)
		span = cls(str(group), begin, cls._NotBefore(end, begin), parent=parent, taskName=group.QualifiedName)
		cls._AddContents(group, span)

		return span


@export
class DownstreamSpan(CIWorkflowSpan, GitLabTimespanMixin):
	"""The jobs of a downstream pipeline, grouped into one timespan named like its trigger job."""

	@classmethod
	def FromDownstreamPipeline(cls, pipeline: DownstreamPipeline, parent: Span) -> Nullable[Self]:
		"""
		Build the timespan of a downstream pipeline and everything below it.

		:param pipeline: The downstream pipeline.
		:param parent:   The timespan containing the trigger job.
		:returns:        The downstream pipeline's timespan, or ``None`` if it hasn't been created, or nothing of it
		                 started.
		"""
		begin, end = cls._GroupTimespan(pipeline)
		if begin is None:
			return None

		begin = cls._NotBeforeParent(begin, parent)
		span = cls(
			str(pipeline),
			begin,
			cls._NotBefore(end, begin),
			parent=parent,
			taskName=pipeline.QualifiedName,
			attributes={
				OTLP.CICD.Pipeline.Task.Run.ID:       None if pipeline.DownstreamID is None else str(pipeline.DownstreamID),
				OTLP.CICD.Pipeline.Task.Run.URL.Full: None if pipeline.URL is None else str(pipeline.URL),
				OTLP.CICD.Pipeline.Task.Run.Result:   cls._Result(pipeline),
				GitLab.Status:                        cls._Value(pipeline.Status),
				GitLab.Job.Stage:                     pipeline.Stage,
				GitLab.Downstream.ID:                 pipeline.DownstreamID,
				GitLab.Downstream.ProjectID:          pipeline.DownstreamProjectID,
				GitLab.Trigger.ID:                    pipeline.ID,
				GitLab.Trigger.Status:                cls._Value(pipeline.TriggerStatus),
				GitLab.Trigger.URL:                   None if pipeline.TriggerURL is None else str(pipeline.TriggerURL)
			}
		)
		cls._AddContents(pipeline, span)

		return span


@export
class PipelineTrace(CIPipelineTrace, GitLabTimespanMixin):
	"""A GitLab CI/CD pipeline as a trace."""

	@classmethod
	def Parse(
		cls,
		pipeline:   JSONObject,
		jobs:       Nullable[Iterable[JSONObject]]                 = None,
		bridges:    Nullable[Iterable[JSONObject]]                 = None,
		downstream: Nullable[Mapping[Union[int, str], JSONObject]] = None
	) -> Self:
		"""
		Build the trace of a pipeline from the payloads the GitLab REST API answers with.

		The payloads are read into a :class:`~pyTooling.GitLab.Pipeline` first, so the tree - the matrices, the jobs
		and the downstream pipelines - is reconstructed by the model rather than here, and :meth:`FromPipeline` turns it
		into timespans.

		:param pipeline:     The pipeline, as returned by ``GET /projects/{id}/pipelines/{pipeline_id}``.
		:param jobs:         Optional, the pipeline's jobs, as listed by ``GET .../pipelines/{pipeline_id}/jobs``.
		:param bridges:      Optional, the pipeline's trigger jobs, as listed by
		                     ``GET .../pipelines/{pipeline_id}/bridges``.
		:param downstream:   Optional, the downstream pipelines' payloads, by the downstream pipeline's identifier, as
		                     for :meth:`Pipeline.Parse <pyTooling.GitLab.Pipeline.Parse>`. Default: ``None``.
		:returns:            The pipeline as a trace.
		:raises TypeError:   If parameter 'pipeline' is not of type :class:`dict`.
		:raises GitLabError: If a mandatory field is missing, or a field holds a value GitLab doesn't document.
		"""
		return cls.FromPipeline(Pipeline.Parse(pipeline, jobs, bridges, downstream))

	@classmethod
	def FromPipeline(cls, pipeline: Pipeline) -> Self:
		"""
		Build the trace of a pipeline, as :mod:`pyTooling.GitLab` models it.

		* The pipeline becomes the trace, widened where a job started earlier or completed later than the pipeline
		  reports.
		* A matrix and a downstream pipeline become a timespan holding the jobs below them.
		* A job becomes a timespan from its start to its completion, preceded by ``<job> (queued)`` for the time GitLab
		  reports it was queued for a runner. A job that hasn't started has no timespan; a skipped job no waiting
		  timespan.
		* Every timespan is classified by :attr:`CI.Span.Kind <pyTooling.Tracing.CI.CI>` and carries the OpenTelemetry
		  CI/CD attributes, GitLab's status (:class:`GitLab`), and for jobs the stage, the runner and its tags.

		:param pipeline:   The pipeline.
		:returns:          The pipeline as a trace.
		:raises TypeError: If parameter 'pipeline' is not of type :class:`~pyTooling.GitLab.Pipeline`.
		"""
		if not isinstance(pipeline, Pipeline):
			ex = TypeError("Parameter 'pipeline' is not of type 'Pipeline'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(pipeline)}'.")
			raise ex

		beginTime = pipeline.StartedAt if pipeline.StartedAt is not None else pipeline.CreatedAt
		endTime =   cls._NotBefore(pipeline.CompletedAt, beginTime) if beginTime is not None else pipeline.CompletedAt

		# a job's queue may begin before the pipeline reports itself started, and a job may complete after it finished
		jobsBegin = cls._Earliest(
			queueBegin for job in pipeline.IterateJobs() if (queueBegin := cls._QueueBegin(job)) is not None
		)
		jobsEnd =   pipeline.ContentsCompletedAt
		if (contentsBegin := pipeline.ContentsStartedAt) is not None:
			jobsBegin = contentsBegin if jobsBegin is None else min(jobsBegin, contentsBegin)

		if jobsBegin is not None:
			beginTime = jobsBegin if beginTime is None else min(beginTime, jobsBegin)

		if endTime is not None and jobsEnd is not None:
			endTime = max(endTime, jobsEnd)

		trace = cls(
			pipeline.Name,
			beginTime,
			endTime,
			runID=None if pipeline.ID is None else str(pipeline.ID),
			runURL=None if pipeline.URL is None else str(pipeline.URL),
			result=cls._Result(pipeline),
			reference=pipeline.GitReference,
			revision=pipeline.SHA,
			attributes={
				GitLab.Status:          cls._Value(pipeline.Status),
				GitLab.Pipeline.IID:    pipeline.IID,
				GitLab.Pipeline.Source: None if pipeline.Source is None else pipeline.Source.value,
				GitLab.Project.ID:      pipeline.ProjectID
			}
		)
		cls._AddContents(pipeline, trace)

		return trace


@export
class PipelineReader(ProjectClient):
	"""
	Reads pipelines of a GitLab project through the GitLab REST API and converts them into traces.

	A token is needed for a private project - inside a pipeline, ``CI_JOB_TOKEN`` doesn't suffice, a token with the
	``read_api`` scope does. A public project's pipelines are read without one.
	"""

	def ReadPayloads(self, pipelineID: int, downstream: bool = True) -> JSONObject:
		"""
		Read a pipeline's payloads: the pipeline, its jobs, its trigger jobs, and those of its child pipelines.

		The result has the shape of :meth:`Pipeline.Parse <pyTooling.GitLab.Pipeline.Parse>`'s parameters, so it is read
		with :pycode:`Pipeline.Parse(**payloads)`. A child pipeline - a downstream pipeline of the same project - is read
		with its own child pipelines; a multi-project pipeline isn't, as it belongs to a project this reader wasn't
		made for.

		:param pipelineID:   The pipeline's identifier.
		:param downstream:   Optional, ``True``, if the child pipelines are read too. Default: ``True``.
		:returns:            The payloads - ``pipeline``, ``jobs``, ``bridges`` and ``downstream``.
		:raises ValueError:  If parameter 'pipelineID' is ``None``.
		:raises TypeError:   If parameter 'pipelineID' is not of type :class:`int`.
		:raises ValueError:  If parameter 'pipelineID' isn't positive.
		:raises TypeError:   If parameter 'downstream' is not of type :class:`bool`.
		:raises RESTError:   If a request fails, or GitLab's answer isn't JSON of the expected shape.
		:raises GitLabError: If GitLab's answer lacks a mandatory field.
		"""
		if pipelineID is None:
			raise ValueError("Parameter 'pipelineID' is None.")
		elif isinstance(pipelineID, bool) or not isinstance(pipelineID, int):
			ex = TypeError("Parameter 'pipelineID' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(pipelineID)}'.")
			raise ex
		elif pipelineID <= 0:
			ex = ValueError("Parameter 'pipelineID' isn't positive.")
			ex.add_note(f"Got value '{pipelineID}'.")
			raise ex

		if not isinstance(downstream, bool):
			ex = TypeError("Parameter 'downstream' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(downstream)}'.")
			raise ex

		pipelinePath = f"{self.ProjectResourcePath}/pipelines/{pipelineID}"
		pipeline, _ = self.GetJSONObject(pipelinePath)
		if not isinstance(pipeline, dict) or (projectID := pipeline.get("project_id", None)) is None:
			raise GitLabError(f"Field 'project_id' is missing in the answer of '{pipelinePath}'.")

		jobs =    self.GetJSONArray(f"{pipelinePath}/jobs")
		bridges = self.GetJSONArray(f"{pipelinePath}/bridges")

		children: dict[str, JSONObject] = {}
		if downstream:
			for bridge in bridges:
				child = bridge.get("downstream_pipeline", None)
				if isinstance(child, dict) and child.get("project_id", None) == projectID and child.get("id", None) is not None:
					children[str(child["id"])] = self.ReadPayloads(child["id"])

		return {"pipeline": pipeline, "jobs": jobs, "bridges": bridges, "downstream": children}

	def ReadPipeline(self, pipelineID: int, downstream: bool = True) -> PipelineTrace:
		"""
		Read a pipeline, its jobs and its child pipelines, and convert them into a trace.

		:param pipelineID:   The pipeline's identifier.
		:param downstream:   Optional, ``True``, if the child pipelines are read too. Default: ``True``.
		:returns:            The pipeline as a trace (see :meth:`PipelineTrace.Parse`).
		:raises ValueError:  If parameter 'pipelineID' is ``None``.
		:raises TypeError:   If parameter 'pipelineID' is not of type :class:`int`.
		:raises ValueError:  If parameter 'pipelineID' isn't positive.
		:raises TypeError:   If parameter 'downstream' is not of type :class:`bool`.
		:raises RESTError:   If a request fails, or GitLab's answer isn't JSON of the expected shape.
		:raises GitLabError: If GitLab's answer lacks a mandatory field, or a field holds a value GitLab doesn't document.
		"""
		return PipelineTrace.Parse(**self.ReadPayloads(pipelineID, downstream))

	def _AddErrorNotes(self, error: RESTError, status: int) -> None:
		"""
		Add a note saying what a failing status means for the GitLab REST API.

		:param error:  The error the note is added to.
		:param status: The HTTP status the request failed with.
		"""
		if status in (401, 403, 404):
			error.add_note("Check the project's path or identifier, and that the token may read the project's pipelines.")

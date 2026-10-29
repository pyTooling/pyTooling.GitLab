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
Unit tests for :mod:`pyTooling.GitLab.Tracing`.
"""
from typing                   import Any
from unittest                 import mock
from urllib.error             import HTTPError

from pyTooling.GitLab         import GitLabError, Pipeline
from pyTooling.GitLab.Tracing import DownstreamSpan, GitLab, JobSpan, MatrixSpan, PipelineReader, PipelineTrace, \
                                     QueuedSpan, runnerCategory
from pyTooling.REST           import RESTError
from pyTooling.Tracing.CI     import CI, OTLP, Result, SpanKind
from pyTooling.Testing        import Testcase, testsuite, testcase

from tests.unit.Run           import _Response, _bridge, _datetime, _job, _pipeline, _recording, _time


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


@testsuite("Attribute keys")
class AttributeKeys(Testcase):
	"""The keys naming what only GitLab reports spell the key their path names."""

	@testcase("Keys")
	def Keys(self) -> None:
		"""
		Every key is spelled as its nesting reads.

		Checks the keys of a pipeline, a job, a runner, a downstream pipeline and its trigger job.
		"""
		self.assertEqual("gitlab.status", GitLab.Status)
		self.assertEqual("gitlab.pipeline.iid", GitLab.Pipeline.IID)
		self.assertEqual("gitlab.pipeline.source", GitLab.Pipeline.Source)
		self.assertEqual("gitlab.project.id", GitLab.Project.ID)
		self.assertEqual("gitlab.job.stage", GitLab.Job.Stage)
		self.assertEqual("gitlab.job.allow_failure", GitLab.Job.AllowFailure)
		self.assertEqual("gitlab.job.failure_reason", GitLab.Job.FailureReason)
		self.assertEqual("gitlab.matrix.dimensions", GitLab.Matrix.Dimensions)
		self.assertEqual("gitlab.runner.id", GitLab.Runner.ID)
		self.assertEqual("gitlab.runner.tags", GitLab.Runner.Tags)
		self.assertEqual("gitlab.downstream.id", GitLab.Downstream.ID)
		self.assertEqual("gitlab.downstream.project_id", GitLab.Downstream.ProjectID)
		self.assertEqual("gitlab.trigger.id", GitLab.Trigger.ID)
		self.assertEqual("gitlab.trigger.status", GitLab.Trigger.Status)
		self.assertEqual("gitlab.trigger.url", GitLab.Trigger.URL)


@testsuite("Timespans")
class Timespans(Testcase):
	"""A pipeline converted into timespans."""

	@testcase("Pipeline")
	def Pipeline(self) -> None:
		"""
		The pipeline becomes the trace, carrying the OpenTelemetry attributes and GitLab's.

		Converts a pipeline without jobs.
		"""
		trace = PipelineTrace.Parse(_pipeline())

		self.assertEqual("#12", trace.Name)
		self.assertEqual(_datetime(5), trace.StartTime)
		self.assertEqual(SpanKind.Pipeline, trace[CI.Span.Kind])
		self.assertEqual("4711", trace[OTLP.CICD.Pipeline.Run.ID])
		self.assertEqual(Result.Success, trace[OTLP.CICD.Pipeline.Result])
		self.assertEqual("main", trace[OTLP.VCS.Ref.Head.Name])
		self.assertEqual("abc123", trace[OTLP.VCS.Ref.Head.Revision])
		self.assertEqual("success", trace[GitLab.Status])
		self.assertEqual(12, trace[GitLab.Pipeline.IID])
		self.assertEqual("push", trace[GitLab.Pipeline.Source])
		self.assertEqual(99, trace[GitLab.Project.ID])

	@testcase("Job and its queue")
	def Job(self) -> None:
		"""
		A job becomes a timespan from its start to its completion, behind the time GitLab reports it was queued.

		Converts a job queued for 2 seconds, started at 10 s and completed at 70 s.
		"""
		trace = PipelineTrace.Parse(_pipeline(), [_job(queued_duration=2.0)])
		queued, job = trace.IterateSubSpans()

		self.assertIsInstance(queued, QueuedSpan)
		self.assertEqual("build (queued)", queued.Name)
		self.assertEqual(_datetime(8), queued.StartTime)
		self.assertEqual(_datetime(10), queued.StopTime)
		self.assertIsInstance(job, JobSpan)
		self.assertEqual(_datetime(10), job.StartTime)
		self.assertEqual(_datetime(70), job.StopTime)
		self.assertEqual("100", job[OTLP.CICD.Pipeline.Task.Run.ID])
		self.assertEqual(Result.Success, job[OTLP.CICD.Pipeline.Task.Run.Result])
		self.assertEqual("shared-runner", job[OTLP.CICD.Worker.Name])
		self.assertEqual("build", job[GitLab.Job.Stage])
		self.assertEqual(["linux"], job[GitLab.Runner.Tags])
		self.assertEqual(7, job[GitLab.Runner.ID])

	@testcase("Queue before the pipeline")
	def QueueBeforePipeline(self) -> None:
		"""
		A job queued before the pipeline reports itself started widens the trace.

		Converts a job queued for 9 seconds, started 4 seconds after the pipeline started.
		"""
		trace = PipelineTrace.Parse(_pipeline(), [_job(started_at=_time(9), queued_duration=9.0)])

		self.assertEqual(_datetime(0), trace.StartTime)

	@testcase("Jobs without timespans")
	def WithoutTimespans(self) -> None:
		"""
		A job that hasn't started has no timespan, nor has a matrix of such jobs; a skipped job lasts no time.

		Converts a manual job, a matrix of manual jobs and a skipped job.
		"""
		trace = PipelineTrace.Parse(_pipeline(), [
			_job(id=101, name="deploy", status="manual", started_at=None, finished_at=None),
			_job(id=102, name="novel: [arch]", status="manual", started_at=None, finished_at=None),
			_job(id=103, name="lint", status="skipped", started_at=None, finished_at=_time(30), queued_duration=None),
		])

		spans = list(trace.IterateSubSpans())
		self.assertEqual(1, len(spans))
		skipped = spans[0]
		self.assertEqual("lint", skipped.Name)
		self.assertEqual(_datetime(30), skipped.StartTime)
		self.assertEqual(_datetime(30), skipped.StopTime)
		self.assertEqual(Result.Skip, skipped[OTLP.CICD.Pipeline.Task.Run.Result])

	@testcase("Matrix")
	def Matrix(self) -> None:
		"""
		A matrix groups its instances, which list their values.

		Converts a matrix of two instances.
		"""
		trace = PipelineTrace.Parse(_pipeline(), [
			_job(id=101, name="unit: [3.13]", queued_duration=None),
			_job(id=102, name="unit: [3.14]", started_at=_time(20), finished_at=_time(90), queued_duration=None)
		])
		matrix = next(trace.IterateSubSpans())
		instances = list(matrix.IterateSubSpans())

		self.assertIsInstance(matrix, MatrixSpan)
		self.assertEqual("unit", matrix.Name)
		self.assertEqual(_datetime(10), matrix.StartTime)
		self.assertEqual(_datetime(90), matrix.StopTime)
		self.assertEqual(["unit: [3.13]", "unit: [3.14]"], [span.Name for span in instances])
		self.assertEqual(["3.14"], instances[1][GitLab.Matrix.Dimensions])

	@testcase("Child pipeline")
	def Child(self) -> None:
		"""
		A downstream pipeline groups the jobs of its child pipeline, and carries its own facts and its trigger job's.

		Converts a downstream pipeline known by GitLab's summary only - created at 112 s, last updated at 400 s -, whose
		job ran from 130 s to 300 s: it begins with its job and ends at its completion.
		"""
		trace = PipelineTrace.Parse(_pipeline(), None, [_bridge()], {
			4800: {"jobs": [_job(id=300, name="unit", started_at=_time(130), finished_at=_time(300), queued_duration=None)]}
		})
		child = next(trace.IterateSubSpans())

		self.assertIsInstance(child, DownstreamSpan)
		self.assertEqual("child", child.Name)
		self.assertEqual(_datetime(130), child.StartTime)
		self.assertEqual(_datetime(400), child.StopTime)
		self.assertEqual("4800", child[OTLP.CICD.Pipeline.Task.Run.ID])
		self.assertEqual("https://gitlab.com/group/project/-/pipelines/4800", child[OTLP.CICD.Pipeline.Task.Run.URL.Full])
		self.assertEqual(Result.Success, child[OTLP.CICD.Pipeline.Task.Run.Result])
		self.assertEqual(4800, child[GitLab.Downstream.ID])
		self.assertEqual(200, child[GitLab.Trigger.ID])
		self.assertEqual("success", child[GitLab.Trigger.Status])
		self.assertEqual("child / unit", next(child.IterateSubSpans())[OTLP.CICD.Pipeline.Task.Name])

	@testcase("Downstream pipeline without contents")
	def WithoutContents(self) -> None:
		"""
		A downstream pipeline whose payloads weren't read - e.g. a multi-project pipeline - spans its own creation to its
		completion; a trigger job that hasn't started a pipeline has no timespan.

		Converts a trigger job with GitLab's summary of its downstream pipeline, and a manual trigger job.
		"""
		trace = PipelineTrace.Parse(_pipeline(), None, [
			_bridge(), _bridge(id=201, name="manual", status="manual", downstream_pipeline=None)
		])
		spans = list(trace.IterateSubSpans())

		self.assertEqual(["child"], [span.Name for span in spans])
		self.assertEqual(_datetime(112), spans[0].StartTime)
		self.assertEqual(_datetime(400), spans[0].StopTime)

	@testcase("Runner category")
	def RunnerCategory(self) -> None:
		"""
		A job is categorized by its first tag, or by its runner's description without tags.

		Converts a job with tags and one without.
		"""
		trace = PipelineTrace.Parse(_pipeline(), [
			_job(id=101, name="a", tag_list=["saas-linux-small-amd64", "docker"], queued_duration=None),
			_job(id=102, name="b", tag_list=[], queued_duration=None)
		])

		first, second = trace.IterateSubSpans()
		self.assertEqual("saas-linux-small-amd64", runnerCategory(first))
		self.assertEqual("shared-runner", runnerCategory(second))
		self.assertEqual("", runnerCategory(trace))

	@testcase("Model")
	def Model(self) -> None:
		"""
		The trace is built from the model, which is checked for its type.

		Converts a model and checks the message for something else.
		"""
		self.assertEqual("#12", PipelineTrace.FromPipeline(Pipeline.Parse(_pipeline())).Name)

		with self.assertRaises(TypeError) as context:
			PipelineTrace.FromPipeline(_pipeline())

		self.assertEqual("Parameter 'pipeline' is not of type 'Pipeline'.", str(context.exception))

	@testcase("Recorded pipeline")
	def Recorded(self) -> None:
		"""
		A recorded pipeline with matrices, manual jobs and a child pipeline becomes a trace.

		Converts the GitLab Development Kit's pipeline: 68 of its 72 jobs ran - 4 wait to be started by hand -, grouped by
		5 matrices and the child pipeline.
		"""
		trace = PipelineTrace.Parse(**_recording("GitLabDevelopmentKit"))
		jobs = []
		groups = []
		pending = list(trace.IterateSubSpans())
		while len(pending) > 0:
			span = pending.pop()
			if span[CI.Span.Kind] == SpanKind.Job:
				jobs.append(span)
			elif span[CI.Span.Kind] in (SpanKind.Matrix, SpanKind.Workflow):
				groups.append(span)

			pending.extend(span.IterateSubSpans())

		self.assertEqual(68, len(jobs))
		self.assertEqual(6, len(groups))
		self.assertEqual(Result.Success, trace[OTLP.CICD.Pipeline.Result])


@testsuite("Reader")
class Reader(Testcase):
	"""Reading a pipeline through GitLab's REST API."""

	def _Serve(self, answers: dict[str, Any]) -> tuple[Any, list[str]]:
		"""
		Patch :func:`urlopen` to answer requests from a dictionary of resource paths.

		:param answers: The documents to answer with, by the resource path below the API, without query.
		:returns:       The patcher, and the list collecting the requested URLs.
		"""
		requests = []

		def urlopen(request: Any, timeout: float) -> _Response:
			"""
			Nested function answering a request from the dictionary.

			:param request: The request.
			:param timeout: The request's timeout.
			:returns:       The answer.
			"""
			requests.append(request.full_url)
			path = request.full_url.removeprefix("https://gitlab.com/api/v4/").partition("?")[0]

			return _Response(answers[path])

		return mock.patch("pyTooling.REST.urlopen", side_effect=urlopen), requests

	@testcase("Pipeline with a child pipeline")
	def Child(self) -> None:
		"""
		A pipeline is read with its jobs, its trigger jobs and its child pipeline, which becomes the trace.

		Serves a pipeline, whose trigger job started a child pipeline, and another started a multi-project pipeline.
		"""
		otherProject = _bridge(id=201, name="other", downstream_pipeline={
			"id": 9000, "project_id": 7, "status": "success", "created_at": _time(112), "updated_at": _time(500),
			"web_url": "https://gitlab.com/group/other/-/pipelines/9000"
		})
		patcher, requests = self._Serve({
			"projects/group%2Fproject/pipelines/4711":         _pipeline(),
			"projects/group%2Fproject/pipelines/4711/jobs":    [_job()],
			"projects/group%2Fproject/pipelines/4711/bridges": [_bridge(), otherProject],
			"projects/group%2Fproject/pipelines/4800":         _pipeline(id=4800, source="parent_pipeline"),
			"projects/group%2Fproject/pipelines/4800/jobs":    [_job(id=300, name="unit")],
			"projects/group%2Fproject/pipelines/4800/bridges": [],
		})
		with patcher:
			reader = PipelineReader("group/project")
			payloads = reader.ReadPayloads(4711)
			trace = reader.ReadPipeline(4711)

		self.assertEqual(["pipeline", "jobs", "bridges", "downstream"], list(payloads))
		self.assertEqual(["4800"], list(payloads["downstream"]))
		self.assertEqual(12, len(requests))
		self.assertEqual("#12", trace.Name)
		self.assertEqual(["build (queued)", "build", "child", "other"], [span.Name for span in trace.IterateSubSpans()])

	@testcase("Without child pipelines")
	def WithoutChildren(self) -> None:
		"""
		The child pipelines aren't read, if not asked for.

		Serves a pipeline with a trigger job.
		"""
		patcher, requests = self._Serve({
			"projects/99/pipelines/4711":         _pipeline(),
			"projects/99/pipelines/4711/jobs":    [],
			"projects/99/pipelines/4711/bridges": [_bridge()],
		})
		with patcher:
			payloads = PipelineReader(99).ReadPayloads(4711, downstream=False)

		self.assertEqual({}, payloads["downstream"])
		self.assertEqual(3, len(requests))

	@testcase("Missing project")
	def MissingProject(self) -> None:
		"""
		An answer without the pipeline's project is an error.

		Serves a pipeline without 'project_id'.
		"""
		patcher, _ = self._Serve({"projects/99/pipelines/4711": _pipeline(project_id=None)})
		with patcher:
			with self.assertRaises(GitLabError) as context:
				PipelineReader(99).ReadPayloads(4711)

		self.assertEqual(
			"Field 'project_id' is missing in the answer of 'projects/99/pipelines/4711'.", str(context.exception)
		)

	@testcase("Failing request")
	def FailingRequest(self) -> None:
		"""
		A request failing with HTTP 404 says what to check.

		Answers every request with HTTP 404.
		"""
		def urlopen(request: Any, timeout: float) -> _Response:
			"""
			Nested function failing every request.

			:param request: The request.
			:param timeout: The request's timeout.
			:returns:       Never.
			"""
			raise HTTPError(request.full_url, 404, "Not Found", {}, None)

		with mock.patch("pyTooling.REST.urlopen", side_effect=urlopen):
			with self.assertRaises(RESTError) as context:
				PipelineReader(99).ReadPipeline(4711)

		self.assertIn(
			"Check the project's path or identifier, and that the token may read the project's pipelines.",
			context.exception.__notes__
		)

	@testcase("Wrong parameters")
	def WrongParameters(self) -> None:
		"""
		The pipeline's identifier and the switch for child pipelines are checked.

		Checks each message.
		"""
		reader = PipelineReader(99)

		with self.assertRaises(ValueError) as context:
			reader.ReadPayloads(None)
		self.assertEqual("Parameter 'pipelineID' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			reader.ReadPayloads("4711")
		self.assertEqual("Parameter 'pipelineID' is not of type 'int'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			reader.ReadPayloads(0)
		self.assertEqual("Parameter 'pipelineID' isn't positive.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			reader.ReadPayloads(4711, downstream="yes")
		self.assertEqual("Parameter 'downstream' is not of type 'bool'.", str(context.exception))

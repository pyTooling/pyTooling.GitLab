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
Working with GitLab CI/CD pipelines: pipeline files, pipeline runs, and their conversion into traces.

A pipeline file is a :file:`.gitlab-ci.yml` and the files it includes. A pipeline run is read from GitLab's REST API.
A trace is written e.g. as OpenTelemetry's OTLP/JSON.

The models derive from the service-independent model :mod:`pyTooling.CI`. Every exception raised by this package
derives from :exc:`GitLabError`.
"""
from __future__                import annotations

__author__ =            "Patrick Lehmann"
__email__ =             "Paebbels@gmail.com"
__copyright__ =         "2026-2026, Patrick Lehmann"
__license__ =           "Apache License, Version 2.0"
__version__ =           "0.1.0rc1"
__keywords__ =          ["GitLab", "GitLab CI/CD", "Pipeline", "CI", "Trace", "OpenTelemetry", "OTLP"]
__project_url__ =       "https://github.com/pyTooling/pyTooling.GitLab"
__documentation_url__ = "https://pyTooling.github.io/pyTooling.GitLab"
__issue_tracker_url__ = "https://GitHub.com/pyTooling/pyTooling.GitLab/issues"

from datetime                  import datetime, timezone
from typing                    import Optional as Nullable, Any, ClassVar, Hashable, Iterable, Mapping, Self

from pyTooling.CI              import CIError, JSONObject, MatrixInstanceMixin, Outcome
from pyTooling.CI              import Job as CIJob, JobGroup as CIJobGroup, Matrix as CIMatrix
from pyTooling.Common          import getFullyQualifiedName, parseISO8601Timestamp, StringEnum
from pyTooling.Decorators      import export, readonly
from pyTooling.GenericPath.URL import URL
from pyTooling.MetaClasses     import ExtendedType


__all__ = ["STATUS_TO_OUTCOME", "TIMEOUT_FAILURE_REASONS"]


@export
class GitLabError(CIError):
	"""Base-exception of all exceptions raised by :mod:`pyTooling.GitLab`."""


@export
class Status(StringEnum):
	"""The state a pipeline or a job is in."""

	Created =            "created"               #: Created, but not yet processed.
	WaitingForResource = "waiting_for_resource"  #: Waiting for a resource group.
	Preparing =          "preparing"             #: The runner prepares the execution environment.
	WaitingForCallback = "waiting_for_callback"  #: Waiting for a callback from an external service.
	Pending =            "pending"               #: Queued, waiting for a runner.
	Running =            "running"               #: Running.
	Success =            "success"               #: Succeeded.
	Failed =             "failed"                #: Failed.
	Canceling =          "canceling"             #: Being canceled, while its ``after_script`` runs.
	Canceled =           "canceled"              #: Canceled by hand, or aborted.
	Skipped =            "skipped"               #: Not run, because a rule or a dependency excluded it.
	Manual =             "manual"                #: Waiting to be started by hand.
	Scheduled =          "scheduled"             #: Scheduled to start later.

	@classmethod
	def Parse(cls, value: Nullable[str]) -> Nullable[Status]:
		"""
		Convert GitLab's ``status`` field to a member of this enumeration.

		:param value:        Optional, the field's value. Default: ``None``.
		:returns:            The matching member, or ``None`` if the field was absent or empty.
		:raises TypeError:   If parameter 'value' is not of type :class:`str`.
		:raises GitLabError: If the value is not a status GitLab documents. |br|
		                     The note lists the documented values.
		"""
		try:
			return super().Parse(value)
		except ValueError as ex:
			error = GitLabError(f"'{value}' is not a GitLab status.")
			error.add_note(f"Known: {', '.join(member.value for member in cls)}.")
			raise error from ex

	def ToOutcome(self, failureReason: Nullable[str] = None) -> Nullable[Outcome]:
		"""
		Return the service-independent outcome this status corresponds to.

		The statuses ending a pipeline or a job are listed in :data:`STATUS_TO_OUTCOME`; a failure for one of the
		:data:`TIMEOUT_FAILURE_REASONS` is a :attr:`~pyTooling.CI.Outcome.Timeout`. Any other status - e.g.
		:attr:`Manual` or :attr:`Running` - hasn't ended.

		:param failureReason: Optional, the reason GitLab reports for a failure. Default: ``None``.
		:returns:             The outcome, or ``None`` while the status hasn't ended.
		"""
		if self is Status.Failed and failureReason in TIMEOUT_FAILURE_REASONS:
			return Outcome.Timeout

		return STATUS_TO_OUTCOME.get(self, None)


STATUS_TO_OUTCOME = {
	Status.Success:  Outcome.Success,
	Status.Failed:   Outcome.Failure,
	Status.Canceled: Outcome.Cancellation,
	Status.Skipped:  Outcome.Skip,
}
"""GitLab's statuses ending a pipeline or a job, and their service-independent outcome."""

TIMEOUT_FAILURE_REASONS = frozenset(("job_execution_timeout", "stuck_or_timeout_failure"))
"""GitLab's failure reasons of a job stopped by a timeout."""


@export
class Source(StringEnum):
	"""What started a pipeline, as GitLab's ``CI_PIPELINE_SOURCE`` names it."""

	Unknown =                            "unknown"                                #: The source isn't known.
	Push =                               "push"                                   #: A branch or tag was pushed.
	Web =                                "web"                                    #: Started from GitLab's web interface.
	Trigger =                            "trigger"                                #: Started with a trigger token.
	Schedule =                           "schedule"                               #: A pipeline schedule fired.
	API =                                "api"                                    #: Started through the pipelines API.
	External =                           "external"                               #: Started by another CI service.
	Pipeline =                           "pipeline"                               #: A multi-project pipeline.
	Chat =                               "chat"                                   #: Started by a ChatOps command.
	WebIDE =                             "webide"                                 #: Started from the Web IDE.
	MergeRequestEvent =                  "merge_request_event"                    #: A merge request was touched.
	ExternalPullRequestEvent =           "external_pull_request_event"            #: A GitHub pull request was touched.
	ParentPipeline =                     "parent_pipeline"                        #: A child pipeline.
	OnDemandDASTScan =                   "ondemand_dast_scan"                     #: An on-demand DAST scan.
	OnDemandDASTValidation =             "ondemand_dast_validation"               #: An on-demand DAST validation.
	SecurityOrchestrationPolicy =        "security_orchestration_policy"          #: A scan execution policy.
	ContainerRegistryPush =              "container_registry_push"                #: An image was pushed to the registry.
	DuoWorkflow =                        "duo_workflow"                           #: Started by a GitLab Duo workflow.
	PipelineExecutionPolicySchedule =    "pipeline_execution_policy_schedule"     #: A scheduled execution policy.
	DependencyManagementSecurityUpdate = "dependency_management_security_update"  #: A dependency security update.

	@classmethod
	def Parse(cls, value: Nullable[str]) -> Nullable[Source]:
		"""
		Convert GitLab's ``source`` field to a member of this enumeration.

		:param value:        Optional, the field's value. Default: ``None``.
		:returns:            The matching member, or ``None`` if the field was absent or empty.
		:raises TypeError:   If parameter 'value' is not of type :class:`str`.
		:raises GitLabError: If the value is not a pipeline source GitLab knows. |br|
		                     The note lists the known values.
		"""
		try:
			return super().Parse(value)
		except ValueError as ex:
			error = GitLabError(f"'{value}' is not a GitLab pipeline source.")
			error.add_note(f"Known: {', '.join(member.value for member in cls)}.")
			raise error from ex


def _parseISO8601Timestamp(value: Nullable[str], field: str) -> Nullable[datetime]:
	"""
	Parse an ISO 8601 timestamp, as the GitLab REST API reports them.

	A timestamp without a time zone is read as UTC, so every timestamp of a pipeline can be compared with every other.

	:param value:        Optional, the field's value. Default: ``None``.
	:param field:        Name of the field, for the exception's message.
	:returns:            The timestamp, or ``None`` if the field was absent or empty.
	:raises GitLabError: If the value isn't an ISO 8601 timestamp. |br|
	                     The note reports the value that was read.
	"""
	try:
		return parseISO8601Timestamp(value, timezone.utc)
	except ValueError as ex:
		error = GitLabError(f"Field '{field}' isn't an ISO 8601 timestamp.")
		error.add_note(f"Got '{value}'.")
		raise error from ex


def _parseURL(value: Nullable[str]) -> Nullable[URL]:
	"""
	Parse a URL, as the GitLab REST API reports them.

	:param value: Optional, the field's value. Default: ``None``.
	:returns:     The URL, or ``None`` if the field was absent or empty.
	"""
	if value is None or value == "":
		return None

	return URL.Parse(value)


def _splitMatrixJobName(name: str) -> tuple[str, Nullable[dict[str, str]]]:
	"""
	Split a job's name into the matrix' name and the dimensions, if it carries any.

	GitLab names the instances of a matrix after the job and the values of the instance's dimensions: a
	``parallel:matrix`` instance ``test: [3.14, linux]``, an instance of ``parallel: 4`` ``test 1/4``. That suffix is
	how GitLab names a job, not a field of the payload, so a job genuinely named ``deploy 1/2`` by its pipeline file is
	indistinguishable from one produced by ``parallel``.

	A ``parallel:matrix`` suffix carries no dimension names, so a dimension is named by the position of its value:
	``"0"``, ``"1"``, ... An instance of ``parallel: N`` carries the variables GitLab sets for it, ``CI_NODE_INDEX`` and
	``CI_NODE_TOTAL``.

	:param name: The job's name.
	:returns:    The name without the suffix and the dimensions, or the name and ``None`` if it carries none.
	"""
	if name.endswith("]") and ": [" in name:
		base, _, values = name[:-1].rpartition(": [")
		if base != "":
			return base, {str(position): value.strip() for position, value in enumerate(values.split(","))}

		return name, None

	base, _, suffix = name.rpartition(" ")
	index, _, total = suffix.partition("/")
	if base == "" or not index.isdigit() or not total.isdigit():
		return name, None

	return base, {"CI_NODE_INDEX": index, "CI_NODE_TOTAL": total}


def _matrixInstanceName(name: str, dimensions: Mapping[str, Any]) -> str:
	"""
	Return the name GitLab gives an instance of a matrix, the inverse of :func:`_splitMatrixJobName`.

	:param name:       The job's name, without the instance's values.
	:param dimensions: The instance's dimensions.
	:returns:          The name with the instance's values: ``test 1/4`` for ``parallel``, ``test: [3.14, linux]`` for
	                   ``parallel:matrix``, and the name alone without dimensions.
	"""
	if len(dimensions) == 0:
		return name
	elif tuple(dimensions) == ("CI_NODE_INDEX", "CI_NODE_TOTAL"):
		return f"{name} {dimensions['CI_NODE_INDEX']}/{dimensions['CI_NODE_TOTAL']}"

	return f"{name}: [{', '.join(str(value) for value in dimensions.values())}]"


@export
class StatusMixin(metaclass=ExtendedType, mixin=True, expects=("_outcome",)):
	"""
	Mixin-class for the elements GitLab reports: a pipeline, a downstream pipeline and a job.

	GitLab reports a :class:`Status` for each of them, a failure reason for a failed job, and a URL. The status is also
	the element's generic :attr:`~pyTooling.CI.Base.Outcome`, by :meth:`Status.ToOutcome`.
	"""

	_status:        Nullable[Status]  #: State the element is in.
	_failureReason: Nullable[str]     #: Reason GitLab reports for a failure.
	_url:           Nullable[URL]     #: URL of the element in GitLab's web interface.

	def __init__(
		self,
		status:        Nullable[Status] = None,
		failureReason: Nullable[str]    = None,
		url:           Nullable[URL]    = None
	) -> None:
		"""
		Initializes what GitLab reports about an element.

		:param status:        Optional, state the element is in. Default: ``None``.
		:param failureReason: Optional, reason GitLab reports for a failure, e.g. ``script_failure``. Default: ``None``.
		:param url:           Optional, URL of the element in GitLab's web interface. Default: ``None``.
		:raises TypeError:    If parameter 'status' is not of type :class:`Status`.
		:raises TypeError:    If parameter 'failureReason' is not of type :class:`str`.
		:raises TypeError:    If parameter 'url' is not of type :class:`~pyTooling.GenericPath.URL.URL`.
		"""
		if status is not None and not isinstance(status, Status):
			ex = TypeError("Parameter 'status' is not of type 'Status'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(status)}'.")
			raise ex

		if failureReason is not None and not isinstance(failureReason, str):
			ex = TypeError("Parameter 'failureReason' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(failureReason)}'.")
			raise ex

		if url is not None and not isinstance(url, URL):
			ex = TypeError("Parameter 'url' is not of type 'URL'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(url)}'.")
			raise ex

		self._status =        status
		self._failureReason = failureReason
		self._url =           url
		if status is not None:
			self._outcome = status.ToOutcome(failureReason)

	@readonly
	def Status(self) -> Nullable[Status]:
		"""
		Read-only property to access the state the element is in (:attr:`_status`).

		The service-independent :attr:`~pyTooling.CI.Base.Outcome` is derived from it by :meth:`Status.ToOutcome`.

		:returns: The state, or ``None`` if GitLab reported none.
		"""
		return self._status

	@readonly
	def FailureReason(self) -> Nullable[str]:
		"""
		Read-only property to access the reason GitLab reports for a failure (:attr:`_failureReason`).

		GitLab reports it for a failed job, e.g. ``script_failure`` or ``job_execution_timeout``.

		:returns: The reason, or ``None`` if GitLab reported none.
		"""
		return self._failureReason

	@readonly
	def URL(self) -> Nullable[URL]:
		"""
		Read-only property to access the element's URL in GitLab's web interface (:attr:`_url`).

		:returns: The URL, or ``None`` if GitLab reported none.
		"""
		return self._url


@export
class JobMixin(metaclass=ExtendedType, mixin=True):
	"""
	Mixin-class for what GitLab reports about a job: a job running on a runner, and a trigger job.

	Both are listed in a stage and may be allowed to fail; GitLab reports how long a job waited in its queue.
	"""

	_id:             Nullable[int]    #: GitLab's identifier of the job.
	_stage:          Nullable[str]    #: Stage the job is listed in.
	_allowFailure:   Nullable[bool]   #: Whether the job may fail without failing its pipeline.
	_queuedDuration: Nullable[float]  #: Seconds the job waited in GitLab's queue.

	def __init__(
		self,
		identifier:     Nullable[int]   = None,
		stage:          Nullable[str]   = None,
		allowFailure:   Nullable[bool]  = None,
		queuedDuration: Nullable[float] = None
	) -> None:
		"""
		Initializes what GitLab reports about a job.

		:param identifier:     Optional, GitLab's identifier of the job. Default: ``None``.
		:param stage:          Optional, stage the job is listed in. Default: ``None``.
		:param allowFailure:   Optional, ``True``, if the job may fail without failing its pipeline. Default: ``None``.
		:param queuedDuration: Optional, seconds the job waited in GitLab's queue. Default: ``None``.
		:raises TypeError:     If parameter 'identifier' is not of type :class:`int`.
		:raises TypeError:     If parameter 'stage' is not of type :class:`str`.
		:raises TypeError:     If parameter 'allowFailure' is not of type :class:`bool`.
		:raises TypeError:     If parameter 'queuedDuration' is not of type :class:`float`.
		"""
		if identifier is not None and (isinstance(identifier, bool) or not isinstance(identifier, int)):
			ex = TypeError("Parameter 'identifier' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(identifier)}'.")
			raise ex

		if stage is not None and not isinstance(stage, str):
			ex = TypeError("Parameter 'stage' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(stage)}'.")
			raise ex

		if allowFailure is not None and not isinstance(allowFailure, bool):
			ex = TypeError("Parameter 'allowFailure' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(allowFailure)}'.")
			raise ex

		if queuedDuration is not None and (
			isinstance(queuedDuration, bool) or not isinstance(queuedDuration, (int, float))
		):
			ex = TypeError("Parameter 'queuedDuration' is not of type 'float'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(queuedDuration)}'.")
			raise ex

		self._id =             identifier
		self._stage =          stage
		self._allowFailure =   allowFailure
		self._queuedDuration = None if queuedDuration is None else float(queuedDuration)

	@readonly
	def ID(self) -> Nullable[int]:
		"""
		Read-only property to access GitLab's identifier of the job (:attr:`_id`).

		:returns: The identifier, or ``None`` if GitLab reported none.
		"""
		return self._id

	@readonly
	def Stage(self) -> Nullable[str]:
		"""
		Read-only property to access the stage the job is listed in (:attr:`_stage`).

		GitLab reports a job's stage, but not the order of the stages, and not a job's ``needs``.

		:returns: The stage's name, or ``None`` if GitLab reported none.
		"""
		return self._stage

	@readonly
	def AllowFailure(self) -> Nullable[bool]:
		"""
		Read-only property to access whether the job may fail without failing its pipeline (:attr:`_allowFailure`).

		:returns: ``True``, if a failure of the job doesn't fail its pipeline, or ``None`` if GitLab reported nothing.
		"""
		return self._allowFailure

	@readonly
	def QueuedDuration(self) -> Nullable[float]:
		"""
		Read-only property to access how long the job waited in GitLab's queue (:attr:`_queuedDuration`).

		GitLab counts the time the job was pending for a runner. The time a job waited for the jobs it depends on isn't
		included, though it lies between :attr:`~pyTooling.CI.Base.CreatedAt` and :attr:`~pyTooling.CI.Base.StartedAt`.

		:returns: Seconds, as GitLab reports them, or ``None`` if GitLab reported none.
		"""
		return self._queuedDuration


@export
class Job(CIJob, StatusMixin, JobMixin):
	"""A job of a pipeline, which ran on a runner."""

	_tags:              list[str]      #: Tags the job requested its runner by, i.e. its ``tags``.
	_runnerID:          Nullable[int]  #: GitLab's identifier of the runner the job ran on.
	_runnerDescription: Nullable[str]  #: Description of the runner the job ran on.

	def __init__(
		self,
		name:              str,
		identifier:        Nullable[int]                    = None,
		stage:             Nullable[str]                    = None,
		status:            Nullable[Status]                 = None,
		failureReason:     Nullable[str]                    = None,
		allowFailure:      Nullable[bool]                   = None,
		createdAt:         Nullable[datetime]               = None,
		startedAt:         Nullable[datetime]               = None,
		completedAt:       Nullable[datetime]               = None,
		queuedDuration:    Nullable[float]                  = None,
		url:               Nullable[URL]                    = None,
		tags:              Nullable[Iterable[str]]          = None,
		runnerID:          Nullable[int]                    = None,
		runnerDescription: Nullable[str]                    = None,
		*,
		keyValuePairs:     Nullable[Mapping[Hashable, Any]] = None,
		parent:            Nullable[CIJobGroup]             = None
	) -> None:
		"""
		Initializes a job of a pipeline.

		:param name:              Name of the job.
		:param identifier:        Optional, GitLab's identifier of the job. Default: ``None``.
		:param stage:             Optional, stage the job is listed in. Default: ``None``.
		:param status:            Optional, state the job is in. Default: ``None``.
		:param failureReason:     Optional, reason GitLab reports for a failure. Default: ``None``.
		:param allowFailure:      Optional, ``True``, if the job may fail without failing its pipeline. Default: ``None``.
		:param createdAt:         Optional, time the job was created. Default: ``None``.
		:param startedAt:         Optional, time the job started running on a runner. Default: ``None``.
		:param completedAt:       Optional, time the job finished. Default: ``None``.
		:param queuedDuration:    Optional, seconds the job waited in GitLab's queue. Default: ``None``.
		:param url:               Optional, URL of the job in GitLab's web interface. Default: ``None``.
		:param tags:              Optional, tags the job requested its runner by. Default: ``None``.
		:param runnerID:          Optional, GitLab's identifier of the runner the job ran on. Default: ``None``.
		:param runnerDescription: Optional, description of the runner the job ran on. Default: ``None``.
		:param keyValuePairs:     Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:param parent:            Optional, reference to the group containing the job. Default: ``None``.
		:raises TypeError:        If an element of parameter 'tags' is not of type :class:`str`.
		:raises TypeError:        If parameter 'runnerID' is not of type :class:`int`.
		:raises TypeError:        If parameter 'runnerDescription' is not of type :class:`str`.
		"""
		if runnerID is not None and (isinstance(runnerID, bool) or not isinstance(runnerID, int)):
			ex = TypeError("Parameter 'runnerID' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(runnerID)}'.")
			raise ex

		if runnerDescription is not None and not isinstance(runnerDescription, str):
			ex = TypeError("Parameter 'runnerDescription' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(runnerDescription)}'.")
			raise ex

		tagList = []
		if tags is not None:
			for tag in tags:
				if not isinstance(tag, str):
					ex = TypeError("An element of parameter 'tags' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(tag)}'.")
					raise ex

				tagList.append(tag)

		super().__init__(
			name, createdAt=createdAt, startedAt=startedAt, completedAt=completedAt, keyValuePairs=keyValuePairs,
			parent=parent
		)
		StatusMixin.__init__(self, status, failureReason, url)
		JobMixin.__init__(self, identifier, stage, allowFailure, queuedDuration)

		self._tags =              tagList
		self._runnerID =          runnerID
		self._runnerDescription = runnerDescription

	@readonly
	def Tags(self) -> list[str]:
		"""
		Read-only property to access the tags the job requested its runner by (:attr:`_tags`).

		These are the values of the job's ``tags:``; a runner picks a job, whose tags it was registered with.

		:returns: The tags, empty if GitLab reported none.
		"""
		return self._tags

	@readonly
	def RunnerID(self) -> Nullable[int]:
		"""
		Read-only property to access GitLab's identifier of the runner the job ran on (:attr:`_runnerID`).

		:returns: The runner's identifier, or ``None`` while the job hasn't started.
		"""
		return self._runnerID

	@readonly
	def RunnerDescription(self) -> Nullable[str]:
		"""
		Read-only property to access the description of the runner the job ran on (:attr:`_runnerDescription`).

		:returns: The runner's description, e.g. its host, or ``None`` while the job hasn't started.
		"""
		return self._runnerDescription

	@classmethod
	def _ParseFields(cls, json: JSONObject, path: str) -> dict[str, Any]:
		"""
		Read the fields of a job from the JSON object the GitLab REST API answers with.

		:param json:         The job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/jobs``.
		:param path:         Position of the job, for an exception's message.
		:returns:            The values of the job's initializer, by parameter name.
		:raises TypeError:   If parameter 'json' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		if not isinstance(json, dict):
			ex = TypeError("Parameter 'json' is not of type 'dict'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(json)}'.")
			raise ex

		if (name := json.get("name", None)) is None:
			raise GitLabError(f"Field '{path}.name' is missing.")

		if (runner := json.get("runner", None)) is None:
			runner = {}

		return {
			"name":              name,
			"identifier":        json.get("id", None),
			"stage":             json.get("stage", None),
			"status":            Status.Parse(json.get("status", None)),
			"failureReason":     json.get("failure_reason", None),
			"allowFailure":      json.get("allow_failure", None),
			"createdAt":         _parseISO8601Timestamp(json.get("created_at", None), f"{path}.created_at"),
			"startedAt":         _parseISO8601Timestamp(json.get("started_at", None), f"{path}.started_at"),
			"completedAt":       _parseISO8601Timestamp(json.get("finished_at", None), f"{path}.finished_at"),
			"queuedDuration":    json.get("queued_duration", None),
			"url":               _parseURL(json.get("web_url", None)),
			"tags":              json.get("tag_list", None),
			"runnerID":          runner.get("id", None),
			"runnerDescription": runner.get("description", None),
		}

	@classmethod
	def Parse(cls, json: JSONObject, path: str = "job", *, parent: Nullable[CIJobGroup] = None) -> Self:
		"""
		Build a job from the JSON object the GitLab REST API answers with.

		:param json:         The job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/jobs``.
		:param path:         Optional, position of the job, for an exception's message. Default: ``'job'``.
		:param parent:       Optional, reference to the group containing the job. Default: ``None``.
		:returns:            The job.
		:raises TypeError:   If parameter 'json' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		return cls(**cls._ParseFields(json, path), parent=parent)


@export
class MatrixJob(Job, MatrixInstanceMixin):
	"""
	One instance of a job produced by ``parallel:matrix`` or ``parallel``.

	GitLab reports a matrix instance as an ordinary job, whose name carries the instance's values:
	``test: [3.14, linux]`` for ``parallel:matrix``, ``test 1/4`` for ``parallel: 4``. :meth:`Pipeline.Parse` reads
	those back into :attr:`~pyTooling.CI.MatrixInstanceMixin.Dimensions` and groups the instances below a
	:class:`~pyTooling.CI.Matrix`. The job's payload names no dimension of a ``parallel:matrix`` - only the pipeline
	file does -, so a dimension's name is the position of its value, ``{"0": "3.14", "1": "linux"}``, until the names
	are known. An instance of ``parallel`` carries ``CI_NODE_INDEX`` and ``CI_NODE_TOTAL``, as GitLab names them.
	"""

	_PARENT_TYPE: ClassVar[Nullable[type]] = CIMatrix  #: A matrix instance is contained in a matrix.

	def __init__(
		self,
		name:              str,
		dimensions:        Nullable[Mapping[str, Any]]      = None,
		identifier:        Nullable[int]                    = None,
		stage:             Nullable[str]                    = None,
		status:            Nullable[Status]                 = None,
		failureReason:     Nullable[str]                    = None,
		allowFailure:      Nullable[bool]                   = None,
		createdAt:         Nullable[datetime]               = None,
		startedAt:         Nullable[datetime]               = None,
		completedAt:       Nullable[datetime]               = None,
		queuedDuration:    Nullable[float]                  = None,
		url:               Nullable[URL]                    = None,
		tags:              Nullable[Iterable[str]]          = None,
		runnerID:          Nullable[int]                    = None,
		runnerDescription: Nullable[str]                    = None,
		*,
		keyValuePairs:     Nullable[Mapping[Hashable, Any]] = None,
		parent:            Nullable[CIMatrix]               = None
	) -> None:
		"""
		Initializes one instance of a job produced by a matrix.

		:param name:              Name of the job, without the instance's values.
		:param dimensions:        Optional, the dimensions' names and values this instance ran with. Default: ``None``.
		:param identifier:        Optional, GitLab's identifier of the job. Default: ``None``.
		:param stage:             Optional, stage the job is listed in. Default: ``None``.
		:param status:            Optional, state the job is in. Default: ``None``.
		:param failureReason:     Optional, reason GitLab reports for a failure. Default: ``None``.
		:param allowFailure:      Optional, ``True``, if the job may fail without failing its pipeline. Default: ``None``.
		:param createdAt:         Optional, time the job was created. Default: ``None``.
		:param startedAt:         Optional, time the job started running on a runner. Default: ``None``.
		:param completedAt:       Optional, time the job finished. Default: ``None``.
		:param queuedDuration:    Optional, seconds the job waited in GitLab's queue. Default: ``None``.
		:param url:               Optional, URL of the job in GitLab's web interface. Default: ``None``.
		:param tags:              Optional, tags the job requested its runner by. Default: ``None``.
		:param runnerID:          Optional, GitLab's identifier of the runner the job ran on. Default: ``None``.
		:param runnerDescription: Optional, description of the runner the job ran on. Default: ``None``.
		:param keyValuePairs:     Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:param parent:            Optional, reference to the matrix containing the instance. Default: ``None``.
		"""
		super().__init__(
			name, identifier, stage, status, failureReason, allowFailure, createdAt, startedAt, completedAt,
			queuedDuration, url, tags, runnerID, runnerDescription, keyValuePairs=keyValuePairs, parent=parent
		)
		MatrixInstanceMixin.__init__(self, dimensions)

	def __str__(self) -> str:
		"""
		Return a string representation of the matrix instance.

		:returns: The job's name with the instance's values, as GitLab prints it.
		"""
		return _matrixInstanceName(self._name, self._dimensions)

	@classmethod
	def Parse(
		cls,
		json:       JSONObject,
		path:       str                         = "job",
		name:       Nullable[str]               = None,
		dimensions: Nullable[Mapping[str, Any]] = None,
		*,
		parent:     Nullable[CIMatrix]          = None
	) -> Self:
		"""
		Build a matrix instance from the JSON object the GitLab REST API answers with.

		:param json:         The job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/jobs``.
		:param path:         Optional, position of the job, for an exception's message. Default: ``'job'``.
		:param name:         Optional, the job's name without the instance's values. Default: read from the payload.
		:param dimensions:   Optional, the dimensions' names and values. Default: read from the payload.
		:param parent:       Optional, reference to the matrix containing the instance. Default: ``None``.
		:returns:            The matrix instance.
		:raises TypeError:   If parameter 'json' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		fields = cls._ParseFields(json, path)
		if name is None:
			name, dimensions = _splitMatrixJobName(fields["name"])

		fields["name"] = name

		return cls(**fields, dimensions=dimensions, parent=parent)
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
from __future__            import annotations

__author__ =            "Patrick Lehmann"
__email__ =             "Paebbels@gmail.com"
__copyright__ =         "2026-2026, Patrick Lehmann"
__license__ =           "Apache License, Version 2.0"
__version__ =           "0.1.0"
__keywords__ =          ["GitLab", "GitLab CI/CD", "Pipeline", "CI", "Trace", "OpenTelemetry", "OTLP"]
__project_url__ =       "https://github.com/pyTooling/pyTooling.GitLab"
__documentation_url__ = "https://pyTooling.github.io/pyTooling.GitLab"
__issue_tracker_url__ = "https://GitHub.com/pyTooling/pyTooling.GitLab/issues"

from datetime              import datetime, timezone
from http                  import HTTPMethod
from json                  import loads as json_loads
from typing                import Optional as Nullable, Any, ClassVar, Hashable, Iterable, Mapping, Self, Union

from pyTooling.CI          import CIError, MatrixInstanceMixin, Outcome, Job as CIJob, JobGroup as CIJobGroup, \
                                  Matrix as CIMatrix, Pipeline as CIPipeline, PipelineGroup as CIPipelineGroup, \
                                  Workflow as CIWorkflow
from pyTooling.Common      import getFullyQualifiedName, parseISO8601Timestamp, StringEnum
from pyTooling.Decorators  import export, readonly
from pyTooling.URI         import URL
from pyTooling.MetaClasses import ExtendedType
from pyTooling.REST        import JSONObject, MediaType, RESTClient, RESTError


__all__ = ["GITLAB_API_URL", "STATUS_TO_OUTCOME", "TIMEOUT_FAILURE_REASONS"]


@export
class GitLabError(CIError):
	"""Base-exception of all exceptions raised by :mod:`pyTooling.GitLab`."""


GITLAB_API_URL = URL.Parse("https://gitlab.com/api/v4")
"""Base URL of the REST API of gitlab.com."""


@export
class ProjectClient(RESTClient):
	"""
	A client of the GitLab REST API for one project.

	A reader of a project's data derives from it. The requests themselves - the retries, the pagination and the
	token's boundary - are :class:`~pyTooling.REST.RESTClient`'s. GitLab answers a list as a JSON array rather than a
	JSON object, so this client reads arrays too, with :meth:`GetJSONArray`.
	"""

	_project: str  #: The project, as its numeric identifier or its path.

	def __init__(
		self,
		project:    Union[int, str],
		token:      Nullable[str] = None,
		*,
		apiURL:     Union[str, URL] = GITLAB_API_URL,
		timeout:    float = 30.0,
		retries:    int = 3,
		retryDelay: float = 2.0
	) -> None:
		"""
		Initializes a client for one project.

		:param project:     The project, as its numeric identifier, e.g. ``74823``, or as its path, e.g.
		                    ``gitlab-org/gitlab-development-kit``.
		:param token:       Optional, token authorizing the requests. Default: anonymous requests.
		:param apiURL:      Optional, base URL of the GitLab REST API, e.g. of a self-managed instance.
		                    Default: :data:`GITLAB_API_URL`.
		:param timeout:     Optional, timeout of a single request in seconds. Default: ``30.0``.
		:param retries:     Optional, how often a transiently failing request is tried again. ``0`` tries once.
		                    Default: ``3``.
		:param retryDelay:  Optional, pause in seconds before a request is tried again the first time. The pause doubles
		                    with every further attempt. Default: ``2.0``.
		:raises ValueError: If parameter 'project' is ``None``.
		:raises TypeError:  If parameter 'project' is neither of type :class:`int` nor :class:`str`.
		:raises ValueError: If parameter 'project' is a negative number, an empty path, or a path with an empty part.
		:raises TypeError:  If a parameter of :class:`~pyTooling.REST.RESTClient` has the wrong type.
		:raises ValueError: If a parameter of :class:`~pyTooling.REST.RESTClient` has an invalid value.
		"""
		super().__init__(apiURL, token, timeout=timeout, retries=retries, retryDelay=retryDelay)

		if project is None:
			raise ValueError("Parameter 'project' is None.")
		elif isinstance(project, bool) or not isinstance(project, (int, str)):
			ex = TypeError("Parameter 'project' is neither of type 'int' nor 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(project)}'.")
			raise ex
		elif isinstance(project, int) and project < 0:
			ex = ValueError("Parameter 'project' is a negative number.")
			ex.add_note(f"Got value '{project}'.")
			raise ex
		elif isinstance(project, str) and (project == "" or "" in project.split("/")):
			ex = ValueError("Parameter 'project' is an empty path or has an empty part.")
			ex.add_note(f"Got value '{project}'.")
			raise ex

		self._project = str(project)

	@readonly
	def Project(self) -> str:
		"""
		Read-only property to access the project, as its numeric identifier or its path (:attr:`_project`).

		:returns: The project's identifier or path, as given.
		"""
		return self._project

	@readonly
	def ProjectResourcePath(self) -> str:
		"""
		Read-only property to return the project's resource path below the API.

		A project's path is URL-encoded, so ``gitlab-org/cli`` becomes ``projects/gitlab-org%2Fcli``.

		:returns: The resource path of the project.
		"""
		return f"projects/{self._project.replace('/', '%2F')}"

	def GetJSONArray(self, resourcePath: str, pageSize: int = 100) -> list[JSONObject]:
		"""
		Read a list GitLab answers as a JSON array, following its pages.

		:param resourcePath: Path of the resource below :attr:`~pyTooling.REST.RESTClient.APIURL`.
		:param pageSize:     Optional, number of entries per page, at most 100. Default: ``100``.
		:returns:            The entries of every page, in the order GitLab answered them.
		:raises ValueError:  If parameter 'pageSize' is not in range 1..100.
		:raises RESTError:   If a request fails, or an answer isn't a JSON array.
		"""
		if not (1 <= pageSize <= 100):
			ex = ValueError("Parameter 'pageSize' is out of range 1..100.")
			ex.add_note(f"Got value '{pageSize}'.")
			raise ex

		separator = "&" if "?" in resourcePath else "?"
		entries: list[JSONObject] = []
		nextResourcePath: Nullable[str] = f"{resourcePath}{separator}per_page={pageSize}"
		while nextResourcePath is not None:
			document, nextResourcePath = self._Request(HTTPMethod.GET, nextResourcePath)
			if not isinstance(document, list):
				raise RESTError(f"API didn't answer with a JSON array: {self._apiURL / resourcePath}")

			entries.extend(document)

		return entries

	def _ProcessAnswer(self, body: bytes, contentType: Nullable[str], url: URL) -> Nullable[Union[JSONObject, list[Any]]]:
		"""
		Read an answer's body as a JSON object or a JSON array.

		:param body:        The answer's body.
		:param contentType: The answer's ``Content-Type`` header, or ``None``.
		:param url:         The URL that was requested.
		:returns:           The JSON object or array, or ``None`` if the answer had no body.
		:raises RESTError:  If the answer's media type isn't JSON. |br|
		                    The note reports the media type that was announced.
		:raises RESTError:  If the answer isn't valid JSON.
		:raises RESTError:  If the answer is JSON, but neither a JSON object nor a JSON array.
		"""
		if len(body) == 0:
			return None

		if contentType is not None and not MediaType.JSON.Matches(contentType):
			error = RESTError(f"API didn't answer with JSON: {url}")
			error.add_note(f"Got 'Content-Type: {contentType}'.")
			raise error

		try:
			document = json_loads(body)
		except ValueError as ex:
			raise RESTError(f"API answered with invalid JSON: {url}") from ex

		if not isinstance(document, (dict, list)):
			raise RESTError(f"API didn't answer with a JSON object or array: {url}")

		return document


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
		:raises TypeError:    If parameter 'url' is not of type :class:`~pyTooling.URI.URL`.
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
class PipelineGroup(CIPipelineGroup):
	"""
	Every pipeline GitLab started for one commit, and the top of the tree.

	A commit can have several pipelines: a branch pipeline started by the push, a merge request pipeline, a pipeline at
	a tag of the same commit, a scheduled one. GitLab lists a project's pipelines without its child pipelines, which
	belong to the pipeline that triggered them (see :class:`~pyTooling.CI.Workflow`).

	The group has no times of its own and derives them from its pipelines.
	"""

	def __init__(
		self,
		sha:           str,
		pipelines:     Nullable[Iterable[Pipeline]]     = None,
		*,
		keyValuePairs: Nullable[Mapping[Hashable, Any]] = None
	) -> None:
		"""
		Initializes a group of pipelines started for one commit.

		:param sha:           Commit every pipeline of the group was started on.
		:param pipelines:     Optional, the pipelines, which are attached to the group. Default: ``None``.
		:param keyValuePairs: Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:raises ValueError:   If parameter 'sha' is ``None``.
		:raises TypeError:    If parameter 'sha' is not of type :class:`str`.
		:raises ValueError:   If parameter 'sha' is empty.
		:raises TypeError:    If an element of parameter 'pipelines' is not of type :class:`Pipeline`.
		"""
		super().__init__(sha, pipelines, keyValuePairs=keyValuePairs)

	@readonly
	def SHA(self) -> str:
		"""
		Read-only property to access the commit every pipeline of the group was started on (:attr:`_name`).

		:returns: The commit's hash.
		"""
		return self._name

	def ByGitReference(self) -> dict[Nullable[str], list[Pipeline]]:
		"""
		Group the commit's pipelines by the reference they were started on.

		A commit pushed to a branch, proposed in a merge request and later tagged has its pipelines under three keys -
		e.g. ``main``, ``refs/merge-requests/6293/merge`` and ``v1.0.0``.

		:returns: Dictionary of a reference to the pipelines started on it, in the order they were reported.
		"""
		byReference: dict[Nullable[str], list[Pipeline]] = {}
		for pipeline in self._pipelines:
			if (pipelines := byReference.get(pipeline.GitReference, None)) is None:
				pipelines = []
				byReference[pipeline.GitReference] = pipelines

			pipelines.append(pipeline)

		return byReference

	@classmethod
	def Parse(
		cls,
		pipelines: Iterable[JSONObject],
		jobs:      Nullable[Mapping[int, Iterable[JSONObject]]] = None,
		sha:       Nullable[str] = None
	) -> Self:
		"""
		Build a group of pipelines from the JSON objects the GitLab REST API answers with.

		:param pipelines:    The pipelines, as returned by ``GET /projects/{id}/pipelines?sha=...``, or each as returned
		                     by ``GET /projects/{id}/pipelines/{pipeline_id}``.
		:param jobs:         Optional, the jobs of each pipeline, by the pipeline's identifier. Default: ``None``.
		:param sha:          Optional, the commit. Default: the ``sha`` the pipelines report.
		:returns:            The group, with its pipelines attached.
		:raises GitLabError: If the pipelines report different commits.
		:raises GitLabError: If no pipeline reports a commit and parameter 'sha' wasn't given.
		"""
		pipelineList = []
		shas = set()
		for json in pipelines:
			pipelineJobs = None
			if jobs is not None and isinstance(json, dict):
				pipelineJobs = jobs.get(json.get("id", None), None)

			pipeline = Pipeline.Parse(json, pipelineJobs)
			pipelineList.append(pipeline)
			if pipeline.SHA is not None:
				shas.add(pipeline.SHA)

		if sha is None:
			if (commits := len(shas)) == 0:
				raise GitLabError("None of the pipelines reports a 'sha', and parameter 'sha' wasn't given.")
			elif commits > 1:
				error = GitLabError("The pipelines report different commits.")
				error.add_note(f"Got {', '.join(sorted(shas))}.")
				raise error

			sha = shas.pop()

		return cls(sha, pipelineList)


@export
class PipelineContentsMixin(metaclass=ExtendedType, mixin=True, expects=("_elements", "_matrices", "_workflows")):
	"""
	Mixin-class for the groups holding what GitLab lists for a pipeline: a pipeline and a downstream pipeline.

	It adds the jobs GitLab lists for a pipeline and the trigger jobs starting downstream pipelines, and the
	dependencies the stages imply.
	"""

	def _AddJobs(self, jobs: Iterable[JSONObject], path: str) -> None:
		"""
		Add the jobs GitLab listed for this pipeline, in the order it created them.

		:param jobs:         The pipeline's jobs, as listed by ``GET .../pipelines/{pipeline_id}/jobs``.
		:param path:         Name of the jobs' list, for an exception's message.
		:raises TypeError:   If an element of parameter 'jobs' is not of type :class:`dict`.
		:raises GitLabError: If a job's field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		jobList = list(jobs)
		for position, job in enumerate(jobList):
			if not isinstance(job, dict):
				ex = TypeError(f"Job {position} is not of type 'dict'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(job)}'.")
				raise ex

		for position, job in sorted(enumerate(jobList), key=self._CreationOrder):
			jobPath = f"{path}[{position}]"
			if (fullName := job.get("name", None)) is None:
				raise GitLabError(f"Field '{jobPath}.name' is missing.")

			jobName, dimensions = _splitMatrixJobName(fullName)
			if dimensions is None:
				Job.Parse(job, jobPath, parent=self)
			else:
				if (matrix := self._matrices.get(jobName, None)) is None:
					matrix = CIMatrix(jobName, parent=self)

				MatrixJob.Parse(job, jobPath, jobName, dimensions, parent=matrix)

	def _AddBridges(
		self,
		bridges:    Iterable[JSONObject],
		downstream: Nullable[Mapping[Union[int, str], JSONObject]],
		path:       str
	) -> None:
		"""
		Add a downstream pipeline for every trigger job GitLab listed, in the order it created them.

		:param bridges:      The trigger jobs, as listed by ``GET .../pipelines/{pipeline_id}/bridges``.
		:param downstream:   The downstream pipelines' payloads, by the downstream pipeline's identifier, or ``None``.
		:param path:         Name of the trigger jobs' list, for an exception's message.
		:raises TypeError:   If an element of parameter 'bridges' is not of type :class:`dict`.
		:raises GitLabError: If a trigger job's field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		bridgeList = list(bridges)
		for position, bridge in enumerate(bridgeList):
			if not isinstance(bridge, dict):
				ex = TypeError(f"Trigger job {position} is not of type 'dict'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(bridge)}'.")
				raise ex

		for position, bridge in sorted(enumerate(bridgeList), key=self._CreationOrder):
			bridgePath = f"{path}[{position}]"
			if (fullName := bridge.get("name", None)) is None:
				raise GitLabError(f"Field '{bridgePath}.name' is missing.")

			payload = None
			if downstream is not None and (child := bridge.get("downstream_pipeline", None)) is not None:
				if (payload := downstream.get(child.get("id", None), None)) is None:
					payload = downstream.get(str(child.get("id", None)), None)

			bridgeName, dimensions = _splitMatrixJobName(fullName)
			if dimensions is None:
				DownstreamPipeline.Parse(bridge, payload, bridgePath, parent=self)
			else:
				if (matrix := self._matrices.get(bridgeName, None)) is None:
					matrix = CIMatrix(bridgeName, parent=self)

				MatrixDownstreamPipeline.Parse(bridge, payload, bridgePath, bridgeName, dimensions, parent=matrix)

	@staticmethod
	def _CreationOrder(entry: tuple[int, JSONObject]) -> tuple[bool, int]:
		"""
		Sort the jobs GitLab listed by their identifier, which grows with a job's creation.

		:param entry: A job's position in its list, and the job.
		:returns:     The sort key; a job without identifier is placed behind every job with one.
		"""
		identifier = entry[1].get("id", None)

		return (identifier is None, 0 if identifier is None else identifier)

	def ApplyNeeds(self, stages: Iterable[str], needs: Nullable[Mapping[str, Iterable[str]]] = None) -> None:
		"""
		Add the dependencies between the elements of this pipeline, which the stages and the ``needs`` imply.

		GitLab's REST API reports a job's stage, but neither the order of the stages nor a job's ``needs``; both are
		in the pipeline file. An element listed in parameter 'needs' needs the siblings named there - a matrix or a
		downstream pipeline by its name, ``[]`` needing nothing. Every other element needs every element of the
		nearest earlier stage holding elements, as GitLab runs them. A downstream pipeline's contents aren't touched:
		apply its own stages to it.

		:param stages:       The pipeline's stages, in their order.
		:param needs:        Optional, the names an element needs, by the element's name. Default: ``None``.
		:raises ValueError:  If parameter 'stages' is ``None``.
		:raises TypeError:   If parameter 'stages' is not iterable.
		:raises TypeError:   If parameter 'needs' is not a mapping.
		:raises GitLabError: If an element's stage is unknown or not one of parameter 'stages'.
		:raises GitLabError: If an element needs a name no sibling has.
		"""
		if stages is None:
			raise ValueError("Parameter 'stages' is None.")
		elif not isinstance(stages, Iterable) or isinstance(stages, str):
			ex = TypeError("Parameter 'stages' is not iterable.")
			ex.add_note(f"Got type '{getFullyQualifiedName(stages)}'.")
			raise ex

		if needs is not None and not isinstance(needs, Mapping):
			ex = TypeError("Parameter 'needs' is not a mapping ('dict', ...).")
			ex.add_note(f"Got type '{getFullyQualifiedName(needs)}'.")
			raise ex

		stageIndex = {stage: index for index, stage in enumerate(stages)}
		byStage: dict[int, list[Any]] = {}
		elementStages = {}
		for element in self._elements:
			stage = element.Instances[0].Stage if isinstance(element, CIMatrix) else element.Stage
			if (index := stageIndex.get(stage, None)) is None:
				ex = GitLabError(f"Element '{element.Name}' of '{self}' is in stage '{stage}', which isn't one of the stages.")
				ex.add_note(f"Stages: {', '.join(stageIndex)}.")
				raise ex

			byStage.setdefault(index, []).append(element)
			elementStages[element] = index

		siblings = {element.Name: element for element in self._elements}
		for element, index in elementStages.items():
			if needs is not None and element.Name in needs:
				for name in needs[element.Name]:
					if (need := siblings.get(name, None)) is None:
						raise GitLabError(f"Element '{element.Name}' of '{self}' needs '{name}', which no sibling is named.")

					element.AddNeed(need)
			elif len(earlier := [stage for stage in byStage if stage < index]) > 0:
				for need in byStage[max(earlier)]:
					element.AddNeed(need)


@export
class Pipeline(CIPipeline, StatusMixin, PipelineContentsMixin):
	"""
	A pipeline.

	A pipeline contains its jobs and a :class:`~pyTooling.CI.Matrix` for every job with ``parallel`` or
	``parallel:matrix``. Several pipelines of one commit are held by a :class:`PipelineGroup`, which is the top of the
	tree.
	"""

	_PARENT_TYPE: ClassVar[Nullable[type]] = PipelineGroup  #: A pipeline is contained in a pipeline group.

	_id:             Nullable[int]     #: GitLab's identifier of the pipeline, unique on the instance.
	_iid:            Nullable[int]     #: Number of the pipeline within its project.
	_projectID:      Nullable[int]     #: GitLab's identifier of the project.
	_source:         Nullable[Source]  #: What started the pipeline.
	_gitReference:   Nullable[str]     #: Branch, tag or merge request reference the pipeline was started on.
	_sha:            Nullable[str]     #: Commit the pipeline was started on.
	_isTag:          Nullable[bool]    #: Whether the reference is a tag.
	_queuedDuration: Nullable[float]   #: Seconds the pipeline waited before its first job started.

	def __init__(
		self,
		name:           str,
		identifier:     Nullable[int]                    = None,
		iid:            Nullable[int]                    = None,
		projectID:      Nullable[int]                    = None,
		status:         Nullable[Status]                 = None,
		createdAt:      Nullable[datetime]               = None,
		startedAt:      Nullable[datetime]               = None,
		completedAt:    Nullable[datetime]               = None,
		url:            Nullable[URL]                    = None,
		source:         Nullable[Source]                 = None,
		gitReference:   Nullable[str]                    = None,
		sha:            Nullable[str]                    = None,
		isTag:          Nullable[bool]                   = None,
		queuedDuration: Nullable[float]                  = None,
		*,
		keyValuePairs:  Nullable[Mapping[Hashable, Any]] = None,
		parent:         Nullable[PipelineGroup]          = None
	) -> None:
		"""
		Initializes a pipeline.

		:param name:           Name of the pipeline.
		:param identifier:     Optional, GitLab's identifier of the pipeline, unique on the instance. Default: ``None``.
		:param iid:            Optional, number of the pipeline within its project. Default: ``None``.
		:param projectID:      Optional, GitLab's identifier of the project. Default: ``None``.
		:param status:         Optional, state the pipeline is in. Default: ``None``.
		:param createdAt:      Optional, time the pipeline was created. Default: ``None``.
		:param startedAt:      Optional, time the pipeline started. Default: ``None``.
		:param completedAt:    Optional, time the pipeline finished. Default: ``None``.
		:param url:            Optional, URL of the pipeline in GitLab's web interface. Default: ``None``.
		:param source:         Optional, what started the pipeline. Default: ``None``.
		:param gitReference:   Optional, branch, tag or merge request reference the pipeline was started on.
		                       Default: ``None``.
		:param sha:            Optional, commit the pipeline was started on. Default: ``None``.
		:param isTag:          Optional, ``True``, if the reference is a tag. Default: ``None``.
		:param queuedDuration: Optional, seconds the pipeline waited before its first job started. Default: ``None``.
		:param keyValuePairs:  Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:param parent:         Optional, reference to the group of the commit's pipelines. Default: ``None``.
		:raises TypeError:     If parameter 'identifier' is not of type :class:`int`.
		:raises TypeError:     If parameter 'iid' is not of type :class:`int`.
		:raises TypeError:     If parameter 'projectID' is not of type :class:`int`.
		:raises TypeError:     If parameter 'source' is not of type :class:`Source`.
		:raises TypeError:     If parameter 'gitReference' is not of type :class:`str`.
		:raises TypeError:     If parameter 'sha' is not of type :class:`str`.
		:raises TypeError:     If parameter 'isTag' is not of type :class:`bool`.
		:raises TypeError:     If parameter 'queuedDuration' is not of type :class:`float`.
		"""
		super().__init__(
			name, createdAt=createdAt, startedAt=startedAt, completedAt=completedAt, keyValuePairs=keyValuePairs,
			parent=parent
		)
		StatusMixin.__init__(self, status, None, url)

		for parameterName, number in (
			("identifier", identifier),
			("iid",        iid),
			("projectID",  projectID)
		):
			if number is not None and (isinstance(number, bool) or not isinstance(number, int)):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'int'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(number)}'.")
				raise ex

		if source is not None and not isinstance(source, Source):
			ex = TypeError("Parameter 'source' is not of type 'Source'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(source)}'.")
			raise ex

		for parameterName, text in (("gitReference", gitReference), ("sha", sha)):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		if isTag is not None and not isinstance(isTag, bool):
			ex = TypeError("Parameter 'isTag' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(isTag)}'.")
			raise ex

		if queuedDuration is not None and (
			isinstance(queuedDuration, bool) or not isinstance(queuedDuration, (int, float))
		):
			ex = TypeError("Parameter 'queuedDuration' is not of type 'float'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(queuedDuration)}'.")
			raise ex

		self._id =             identifier
		self._iid =            iid
		self._projectID =      projectID
		self._source =         source
		self._gitReference =   gitReference
		self._sha =            sha
		self._isTag =          isTag
		self._queuedDuration = None if queuedDuration is None else float(queuedDuration)

	@readonly
	def ID(self) -> Nullable[int]:
		"""
		Read-only property to access GitLab's identifier of the pipeline (:attr:`_id`).

		The identifier is unique on the GitLab instance; :attr:`IID` numbers the pipelines of a project.

		:returns: The identifier, or ``None`` if GitLab reported none.
		"""
		return self._id

	@readonly
	def IID(self) -> Nullable[int]:
		"""
		Read-only property to access the number of the pipeline within its project (:attr:`_iid`).

		:returns: The number, or ``None`` if GitLab reported none.
		"""
		return self._iid

	@readonly
	def ProjectID(self) -> Nullable[int]:
		"""
		Read-only property to access GitLab's identifier of the project the pipeline belongs to (:attr:`_projectID`).

		:returns: The identifier, or ``None`` if GitLab reported none.
		"""
		return self._projectID

	@readonly
	def Source(self) -> Nullable[Source]:
		"""
		Read-only property to access what started the pipeline (:attr:`_source`).

		:returns: The source, or ``None`` if GitLab reported none.
		"""
		return self._source

	@readonly
	def GitReference(self) -> Nullable[str]:
		"""
		Read-only property to access the reference the pipeline was started on (:attr:`_gitReference`).

		It is a branch's or a tag's name, e.g. ``main``, or a merge request's reference, e.g.
		``refs/merge-requests/6293/merge``. :attr:`IsTag` tells a tag from a branch.

		:returns: The reference, or ``None`` if GitLab reported none.
		"""
		return self._gitReference

	@readonly
	def SHA(self) -> Nullable[str]:
		"""
		Read-only property to access the commit the pipeline was started on (:attr:`_sha`).

		:returns: The commit's hash, or ``None`` if GitLab reported none.
		"""
		return self._sha

	@readonly
	def IsTag(self) -> Nullable[bool]:
		"""
		Read-only property to access whether the pipeline was started on a tag (:attr:`_isTag`).

		:returns: ``True``, if :attr:`GitReference` is a tag, or ``None`` if GitLab reported nothing.
		"""
		return self._isTag

	@readonly
	def QueuedDuration(self) -> Nullable[float]:
		"""
		Read-only property to access how long the pipeline waited before its first job started (:attr:`_queuedDuration`).

		:returns: Seconds, as GitLab reports them, or ``None`` if GitLab reported none.
		"""
		return self._queuedDuration

	@classmethod
	def Parse(
		cls,
		pipeline:   JSONObject,
		jobs:       Nullable[Iterable[JSONObject]]                 = None,
		bridges:    Nullable[Iterable[JSONObject]]                 = None,
		downstream: Nullable[Mapping[Union[int, str], JSONObject]] = None,
		*,
		parent:     Nullable[PipelineGroup]                        = None
	) -> Self:
		"""
		Build a pipeline and its tree from the JSON objects the GitLab REST API answers with.

		A pipeline without a ``name`` - GitLab reports one only when the pipeline file sets ``workflow:name`` - is named
		by its number within the project, e.g. ``#47177``. The jobs are added in the order GitLab created them. A job
		named as an instance of a matrix - ``test: [3.14, linux]`` or ``test 1/4`` - becomes a :class:`MatrixJob` below
		a :class:`~pyTooling.CI.Matrix` named ``test``. A trigger job becomes a :class:`DownstreamPipeline`, holding the
		downstream pipeline's jobs if parameter 'downstream' carries them.

		Parameter 'downstream' maps a downstream pipeline's identifier - an :class:`int`, or its text as a JSON file's
		key - to a JSON object with the downstream pipeline's payloads: ``pipeline``, ``jobs``, ``bridges`` and its own
		``downstream``, in the shape of this method's parameters.

		:param pipeline:     The pipeline, as returned by ``GET /projects/{id}/pipelines/{pipeline_id}``.
		:param jobs:         Optional, the pipeline's jobs, as listed by ``GET .../pipelines/{pipeline_id}/jobs``.
		:param bridges:      Optional, the pipeline's trigger jobs, as listed by
		                     ``GET .../pipelines/{pipeline_id}/bridges``.
		:param downstream:   Optional, the downstream pipelines' payloads, by the downstream pipeline's identifier.
		                     Default: ``None``.
		:param parent:       Optional, reference to the group of the commit's pipelines. Default: ``None``.
		:returns:            The pipeline, with its matrices, jobs and downstream pipelines attached.
		:raises TypeError:   If parameter 'pipeline' is not of type :class:`dict`.
		:raises TypeError:   If an element of parameter 'jobs' is not of type :class:`dict`.
		:raises TypeError:   If an element of parameter 'bridges' is not of type :class:`dict`.
		:raises GitLabError: If field ``id`` is missing.
		:raises GitLabError: If a job's or a trigger job's field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		if not isinstance(pipeline, dict):
			ex = TypeError("Parameter 'pipeline' is not of type 'dict'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(pipeline)}'.")
			raise ex

		if (identifier := pipeline.get("id", None)) is None:
			raise GitLabError("Field 'pipeline.id' is missing.")

		iid = pipeline.get("iid", None)
		if (name := pipeline.get("name", None)) is None or name == "":
			name = f"#{identifier if iid is None else iid}"

		result = cls(
			name,
			identifier,
			iid,
			pipeline.get("project_id", None),
			Status.Parse(pipeline.get("status", None)),
			_parseISO8601Timestamp(pipeline.get("created_at", None), "pipeline.created_at"),
			_parseISO8601Timestamp(pipeline.get("started_at", None), "pipeline.started_at"),
			_parseISO8601Timestamp(pipeline.get("finished_at", None), "pipeline.finished_at"),
			_parseURL(pipeline.get("web_url", None)),
			Source.Parse(pipeline.get("source", None)),
			pipeline.get("ref", None),
			pipeline.get("sha", None),
			pipeline.get("tag", None),
			pipeline.get("queued_duration", None),
			parent=parent
		)

		if jobs is not None:
			result._AddJobs(jobs, "jobs")

		if bridges is not None:
			result._AddBridges(bridges, downstream, "bridges")

		return result


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
		super().__init__(
			name, createdAt=createdAt, startedAt=startedAt, completedAt=completedAt, keyValuePairs=keyValuePairs,
			parent=parent
		)
		StatusMixin.__init__(self, status, failureReason, url)
		JobMixin.__init__(self, identifier, stage, allowFailure, queuedDuration)

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


@export
class DownstreamPipeline(CIWorkflow, StatusMixin, JobMixin, PipelineContentsMixin):
	"""
	A downstream pipeline, started by a trigger job: a child pipeline of the same project, or a multi-project pipeline.

	It stands where its trigger job stands - GitLab calls that job a *bridge* - and is named after it, but it reports
	the downstream pipeline's own status, URL and times. What GitLab reports about the trigger job - its identifier,
	stage, status and URL - is kept beside them. A child pipeline's jobs, matrices and own downstream pipelines are its
	contents, if they were read; a multi-project pipeline names its project as :attr:`~pyTooling.CI.Workflow.Reference`.
	"""

	_downstreamID:        Nullable[int]     #: GitLab's identifier of the downstream pipeline.
	_downstreamProjectID: Nullable[int]     #: GitLab's identifier of the downstream pipeline's project.
	_triggerStatus:       Nullable[Status]  #: State the trigger job is in.
	_triggerURL:          Nullable[URL]     #: URL of the trigger job in GitLab's web interface.

	def __init__(
		self,
		name:                str,
		identifier:          Nullable[int]                    = None,
		stage:               Nullable[str]                    = None,
		status:              Nullable[Status]                 = None,
		allowFailure:        Nullable[bool]                   = None,
		createdAt:           Nullable[datetime]               = None,
		startedAt:           Nullable[datetime]               = None,
		completedAt:         Nullable[datetime]               = None,
		queuedDuration:      Nullable[float]                  = None,
		url:                 Nullable[URL]                    = None,
		downstreamID:        Nullable[int]                    = None,
		downstreamProjectID: Nullable[int]                    = None,
		triggerStatus:       Nullable[Status]                 = None,
		triggerURL:          Nullable[URL]                    = None,
		*,
		reference:           Nullable[str]                    = None,
		keyValuePairs:       Nullable[Mapping[Hashable, Any]] = None,
		parent:              Nullable[CIWorkflow]             = None
	) -> None:
		"""
		Initializes a downstream pipeline.

		:param name:                Name of the trigger job.
		:param identifier:          Optional, GitLab's identifier of the trigger job. Default: ``None``.
		:param stage:               Optional, stage the trigger job is listed in. Default: ``None``.
		:param status:              Optional, state the downstream pipeline is in. Default: ``None``.
		:param allowFailure:        Optional, ``True``, if the trigger job may fail without failing its pipeline.
		                            Default: ``None``.
		:param createdAt:           Optional, time the downstream pipeline was created. Default: ``None``.
		:param startedAt:           Optional, time the downstream pipeline started. Default: ``None``.
		:param completedAt:         Optional, time the downstream pipeline finished. Default: ``None``.
		:param queuedDuration:      Optional, seconds the trigger job waited in GitLab's queue. Default: ``None``.
		:param url:                 Optional, URL of the downstream pipeline in GitLab's web interface. Default: ``None``.
		:param downstreamID:        Optional, GitLab's identifier of the downstream pipeline. Default: ``None``.
		:param downstreamProjectID: Optional, GitLab's identifier of the downstream pipeline's project. Default: ``None``.
		:param triggerStatus:       Optional, state the trigger job is in. Default: ``None``.
		:param triggerURL:          Optional, URL of the trigger job in GitLab's web interface. Default: ``None``.
		:param reference:           Optional, the project of a multi-project pipeline, e.g. ``gitlab-org/gitlab``.
		                            Default: ``None``.
		:param keyValuePairs:       Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:param parent:              Optional, reference to the pipeline containing the trigger job. Default: ``None``.
		:raises TypeError:          If parameter 'downstreamID' is not of type :class:`int`.
		:raises TypeError:          If parameter 'downstreamProjectID' is not of type :class:`int`.
		:raises TypeError:          If parameter 'triggerStatus' is not of type :class:`Status`.
		:raises TypeError:          If parameter 'triggerURL' is not of type :class:`~pyTooling.URI.URL`.
		"""
		super().__init__(
			name, reference=reference, createdAt=createdAt, startedAt=startedAt, completedAt=completedAt,
			keyValuePairs=keyValuePairs, parent=parent
		)
		StatusMixin.__init__(self, status, None, url)
		JobMixin.__init__(self, identifier, stage, allowFailure, queuedDuration)

		for parameterName, number in (
			("downstreamID",        downstreamID),
			("downstreamProjectID", downstreamProjectID)
		):
			if number is not None and (isinstance(number, bool) or not isinstance(number, int)):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'int'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(number)}'.")
				raise ex

		if triggerStatus is not None and not isinstance(triggerStatus, Status):
			ex = TypeError("Parameter 'triggerStatus' is not of type 'Status'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(triggerStatus)}'.")
			raise ex

		if triggerURL is not None and not isinstance(triggerURL, URL):
			ex = TypeError("Parameter 'triggerURL' is not of type 'URL'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(triggerURL)}'.")
			raise ex

		self._downstreamID =        downstreamID
		self._downstreamProjectID = downstreamProjectID
		self._triggerStatus =       triggerStatus
		self._triggerURL =          triggerURL

	@readonly
	def DownstreamID(self) -> Nullable[int]:
		"""
		Read-only property to access GitLab's identifier of the downstream pipeline (:attr:`_downstreamID`).

		:returns: The identifier, or ``None`` while the trigger job hasn't started a pipeline.
		"""
		return self._downstreamID

	@readonly
	def DownstreamProjectID(self) -> Nullable[int]:
		"""
		Read-only property to access the identifier of the downstream pipeline's project (:attr:`_downstreamProjectID`).

		:returns: The identifier, or ``None`` while the trigger job hasn't started a pipeline.
		"""
		return self._downstreamProjectID

	@readonly
	def TriggerStatus(self) -> Nullable[Status]:
		"""
		Read-only property to access the state the trigger job is in (:attr:`_triggerStatus`).

		It differs from the downstream pipeline's :attr:`~StatusMixin.Status` for a trigger job without
		``strategy: depend``, which succeeds once it started the downstream pipeline, and for a trigger job waiting to be
		started by hand, which hasn't started a pipeline yet.

		:returns: The state, or ``None`` if GitLab reported none.
		"""
		return self._triggerStatus

	@readonly
	def TriggerURL(self) -> Nullable[URL]:
		"""
		Read-only property to access the trigger job's URL in GitLab's web interface (:attr:`_triggerURL`).

		:returns: The URL, or ``None`` if GitLab reported none.
		"""
		return self._triggerURL

	@readonly
	def IsMultiProject(self) -> Nullable[bool]:
		"""
		Read-only property to return whether the downstream pipeline belongs to another project.

		:returns: ``True`` for a multi-project pipeline, ``False`` for a child pipeline, or ``None`` if either project
		          isn't known.
		"""
		if self._downstreamProjectID is None or self._pipeline is None or self._pipeline.ProjectID is None:
			return None

		return self._downstreamProjectID != self._pipeline.ProjectID

	@staticmethod
	def _CheckPayload(payload: Nullable[JSONObject], path: str) -> Nullable[JSONObject]:
		"""
		Check the downstream pipeline's payloads, and return the downstream pipeline's own payload.

		:param payload:    The downstream pipeline's payloads, or ``None``.
		:param path:       Position of the trigger job, for an exception's message.
		:returns:          The downstream pipeline, as returned by ``GET /projects/{id}/pipelines/{pipeline_id}``, or
		                   ``None``, if it wasn't read.
		:raises TypeError: If parameter 'payload' is not of type :class:`dict`.
		"""
		if payload is None:
			return None
		elif not isinstance(payload, dict):
			ex = TypeError(f"Payload of '{path}' is not of type 'dict'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(payload)}'.")
			raise ex

		return payload.get("pipeline", None)

	@classmethod
	def _ParseFields(cls, bridge: JSONObject, pipeline: Nullable[JSONObject], path: str) -> dict[str, Any]:
		"""
		Read the fields of a downstream pipeline from the JSON objects the GitLab REST API answers with.

		The downstream pipeline's status, URL and times are taken from its own payload, if it was read; otherwise from
		the summary GitLab gives in the trigger job's ``downstream_pipeline``, which has no start, and whose last update
		is the pipeline's completion once it ended.

		:param bridge:       The trigger job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/bridges``.
		:param pipeline:     The downstream pipeline, as returned by ``GET /projects/{id}/pipelines/{pipeline_id}``, or
		                     ``None``, if it wasn't read.
		:param path:         Position of the trigger job, for an exception's message.
		:returns:            The values of the initializer, by parameter name.
		:raises TypeError:   If parameter 'bridge' is not of type :class:`dict`.
		:raises TypeError:   If parameter 'pipeline' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		if not isinstance(bridge, dict):
			ex = TypeError("Parameter 'bridge' is not of type 'dict'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(bridge)}'.")
			raise ex

		if pipeline is not None and not isinstance(pipeline, dict):
			ex = TypeError(f"Downstream pipeline of '{path}' is not of type 'dict'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(pipeline)}'.")
			raise ex

		if (name := bridge.get("name", None)) is None:
			raise GitLabError(f"Field '{path}.name' is missing.")

		if (summary := bridge.get("downstream_pipeline", None)) is None:
			summary = {}

		if pipeline is None:
			ownPath =     f"{path}.downstream_pipeline"
			status =      Status.Parse(summary.get("status", None))
			createdAt =   _parseISO8601Timestamp(summary.get("created_at", None), f"{ownPath}.created_at")
			startedAt =   None
			completedAt = None
			if status is not None and status.ToOutcome() is not None:
				completedAt = _parseISO8601Timestamp(summary.get("updated_at", None), f"{ownPath}.updated_at")
			url =         _parseURL(summary.get("web_url", None))
		else:
			ownPath =     f"{path}.pipeline"
			status =      Status.Parse(pipeline.get("status", None))
			createdAt =   _parseISO8601Timestamp(pipeline.get("created_at", None), f"{ownPath}.created_at")
			startedAt =   _parseISO8601Timestamp(pipeline.get("started_at", None), f"{ownPath}.started_at")
			completedAt = _parseISO8601Timestamp(pipeline.get("finished_at", None), f"{ownPath}.finished_at")
			url =         _parseURL(pipeline.get("web_url", None))

		reference = None
		if (projectID := bridge.get("pipeline", {}).get("project_id", None)) is not None and url is not None:
			if summary.get("project_id", None) not in (None, projectID):
				reference = str(url.Path).strip("/").partition("/-/")[0]

		return {
			"name":                name,
			"identifier":          bridge.get("id", None),
			"stage":               bridge.get("stage", None),
			"status":              status,
			"allowFailure":        bridge.get("allow_failure", None),
			"createdAt":           createdAt,
			"startedAt":           startedAt,
			"completedAt":         completedAt,
			"queuedDuration":      bridge.get("queued_duration", None),
			"url":                 url,
			"downstreamID":        summary.get("id", None),
			"downstreamProjectID": summary.get("project_id", None),
			"triggerStatus":       Status.Parse(bridge.get("status", None)),
			"triggerURL":          _parseURL(bridge.get("web_url", None)),
			"reference":           reference,
		}

	def _AddContents(self, payload: Nullable[JSONObject], path: str) -> None:
		"""
		Add the downstream pipeline's jobs and trigger jobs from its payloads.

		:param payload:      The downstream pipeline's payloads - ``jobs``, ``bridges``, ``downstream`` -, or ``None``.
		:param path:         Position of the trigger job, for an exception's message.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		if payload is None:
			return

		if (jobs := payload.get("jobs", None)) is not None:
			self._AddJobs(jobs, f"{path}.jobs")

		if (bridges := payload.get("bridges", None)) is not None:
			self._AddBridges(bridges, payload.get("downstream", None), f"{path}.bridges")

	@classmethod
	def Parse(
		cls,
		bridge:  JSONObject,
		payload: Nullable[JSONObject]     = None,
		path:    str                      = "bridge",
		*,
		parent:  Nullable[CIWorkflow]     = None
	) -> Self:
		"""
		Build a downstream pipeline from the JSON objects the GitLab REST API answers with.

		:param bridge:       The trigger job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/bridges``.
		:param payload:      Optional, the downstream pipeline's payloads - ``pipeline``, ``jobs``, ``bridges`` and
		                     ``downstream`` in the shape of :meth:`Pipeline.Parse`'s parameters. Default: ``None``.
		:param path:         Optional, position of the trigger job, for an exception's message. Default: ``'bridge'``.
		:param parent:       Optional, reference to the pipeline containing the trigger job. Default: ``None``.
		:returns:            The downstream pipeline, with its contents attached.
		:raises TypeError:   If parameter 'bridge' is not of type :class:`dict`.
		:raises TypeError:   If parameter 'payload' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		pipeline = cls._CheckPayload(payload, path)
		result = cls(**cls._ParseFields(bridge, pipeline, path), parent=parent)
		result._AddContents(payload, path)

		return result


@export
class MatrixDownstreamPipeline(DownstreamPipeline, MatrixInstanceMixin):
	"""
	One instance of a trigger job produced by ``parallel:matrix``, and the downstream pipeline it started.

	It is named like a :class:`MatrixJob`, as GitLab names it: ``deploy: [staging]``.
	"""

	_PARENT_TYPE: ClassVar[Nullable[type]] = CIMatrix  #: A matrix instance is contained in a matrix.

	def __init__(
		self,
		name:                str,
		dimensions:          Nullable[Mapping[str, Any]]      = None,
		identifier:          Nullable[int]                    = None,
		stage:               Nullable[str]                    = None,
		status:              Nullable[Status]                 = None,
		allowFailure:        Nullable[bool]                   = None,
		createdAt:           Nullable[datetime]               = None,
		startedAt:           Nullable[datetime]               = None,
		completedAt:         Nullable[datetime]               = None,
		queuedDuration:      Nullable[float]                  = None,
		url:                 Nullable[URL]                    = None,
		downstreamID:        Nullable[int]                    = None,
		downstreamProjectID: Nullable[int]                    = None,
		triggerStatus:       Nullable[Status]                 = None,
		triggerURL:          Nullable[URL]                    = None,
		*,
		reference:           Nullable[str]                    = None,
		keyValuePairs:       Nullable[Mapping[Hashable, Any]] = None,
		parent:              Nullable[CIMatrix]               = None
	) -> None:
		"""
		Initializes one instance of a trigger job produced by a matrix.

		:param name:                Name of the trigger job, without the instance's values.
		:param dimensions:          Optional, the dimensions' names and values this instance ran with. Default: ``None``.
		:param identifier:          Optional, GitLab's identifier of the trigger job. Default: ``None``.
		:param stage:               Optional, stage the trigger job is listed in. Default: ``None``.
		:param status:              Optional, state the downstream pipeline is in. Default: ``None``.
		:param allowFailure:        Optional, ``True``, if the trigger job may fail without failing its pipeline.
		                            Default: ``None``.
		:param createdAt:           Optional, time the downstream pipeline was created. Default: ``None``.
		:param startedAt:           Optional, time the downstream pipeline started. Default: ``None``.
		:param completedAt:         Optional, time the downstream pipeline finished. Default: ``None``.
		:param queuedDuration:      Optional, seconds the trigger job waited in GitLab's queue. Default: ``None``.
		:param url:                 Optional, URL of the downstream pipeline in GitLab's web interface. Default: ``None``.
		:param downstreamID:        Optional, GitLab's identifier of the downstream pipeline. Default: ``None``.
		:param downstreamProjectID: Optional, GitLab's identifier of the downstream pipeline's project. Default: ``None``.
		:param triggerStatus:       Optional, state the trigger job is in. Default: ``None``.
		:param triggerURL:          Optional, URL of the trigger job in GitLab's web interface. Default: ``None``.
		:param reference:           Optional, the project of a multi-project pipeline. Default: ``None``.
		:param keyValuePairs:       Optional, mapping (dictionary) of key-value-pairs. Default: ``None``.
		:param parent:              Optional, reference to the matrix containing the instance. Default: ``None``.
		"""
		super().__init__(
			name, identifier, stage, status, allowFailure, createdAt, startedAt, completedAt, queuedDuration, url,
			downstreamID, downstreamProjectID, triggerStatus, triggerURL, reference=reference, keyValuePairs=keyValuePairs,
			parent=parent
		)
		MatrixInstanceMixin.__init__(self, dimensions)

	def __str__(self) -> str:
		"""
		Return a string representation of the matrix instance.

		:returns: The trigger job's name with the instance's values, as GitLab prints it.
		"""
		return _matrixInstanceName(self._name, self._dimensions)

	@classmethod
	def Parse(
		cls,
		bridge:     JSONObject,
		payload:    Nullable[JSONObject]        = None,
		path:       str                         = "bridge",
		name:       Nullable[str]               = None,
		dimensions: Nullable[Mapping[str, Any]] = None,
		*,
		parent:     Nullable[CIMatrix]          = None
	) -> Self:
		"""
		Build a matrix instance of a trigger job from the JSON objects the GitLab REST API answers with.

		:param bridge:       The trigger job, as listed by ``GET /projects/{id}/pipelines/{pipeline_id}/bridges``.
		:param payload:      Optional, the downstream pipeline's payloads, as for :meth:`DownstreamPipeline.Parse`.
		                     Default: ``None``.
		:param path:         Optional, position of the trigger job, for an exception's message. Default: ``'bridge'``.
		:param name:         Optional, the trigger job's name without the instance's values. Default: read from the payload.
		:param dimensions:   Optional, the dimensions' names and values. Default: read from the payload.
		:param parent:       Optional, reference to the matrix containing the instance. Default: ``None``.
		:returns:            The matrix instance, with its contents attached.
		:raises TypeError:   If parameter 'bridge' is not of type :class:`dict`.
		:raises TypeError:   If parameter 'payload' is not of type :class:`dict`.
		:raises GitLabError: If field ``name`` is missing.
		:raises GitLabError: If a field holds a value GitLab doesn't document.
		"""
		fields = cls._ParseFields(bridge, cls._CheckPayload(payload, path), path)
		if name is None:
			name, dimensions = _splitMatrixJobName(fields["name"])

		fields["name"] = name
		result = cls(**fields, dimensions=dimensions, parent=parent)
		result._AddContents(payload, path)

		return result

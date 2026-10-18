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
Unit tests for the pipeline run model of :mod:`pyTooling.GitLab`.
"""
from datetime              import datetime, timezone
from json                  import dumps as json_dumps, loads as json_loads
from pathlib               import Path
from typing                import Any
from unittest              import mock

from pyTooling.CI          import Matrix, Outcome
from pyTooling.GitLab      import DownstreamPipeline, GitLabError, Job, MatrixDownstreamPipeline, MatrixJob, Pipeline
from pyTooling.GitLab      import PipelineGroup, ProjectClient, Source, Status
from pyTooling.GitLab      import STATUS_TO_OUTCOME
from pyTooling.REST        import RESTError
from pyTooling.Testing     import Testcase, testsuite, testcase


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


def _time(seconds: int) -> str:
	"""
	Return a GitLab timestamp the given number of seconds after the pipeline was created.

	:param seconds: Seconds after 2026-10-16T10:00:00Z.
	:returns:       The timestamp, as GitLab formats it.
	"""
	return f"2026-10-16T10:{seconds // 60:02d}:{seconds % 60:02d}.000Z"


def _datetime(seconds: int) -> datetime:
	"""
	Return the time the given number of seconds after the pipeline was created.

	:param seconds: Seconds after 2026-10-16T10:00:00Z.
	:returns:       The time, in UTC.
	"""
	return datetime(2026, 10, 16, 10, seconds // 60, seconds % 60, tzinfo=timezone.utc)


def _job(**fields: Any) -> dict[str, Any]:
	"""
	Build a successful job.

	:param fields: Fields overriding the defaults.
	:returns:      The job, as the GitLab REST API lists it.
	"""
	job = {
		"id": 100, "name": "build", "stage": "build", "status": "success", "allow_failure": False,
		"created_at": _time(0), "started_at": _time(10), "finished_at": _time(70), "queued_duration": 1.5,
		"web_url": "https://gitlab.com/group/project/-/jobs/100", "tag_list": ["linux"],
		"runner": {"id": 7, "description": "shared-runner"}
	}
	job.update(fields)

	return job


@testsuite("Status and source")
class Enumerations(Testcase):
	"""GitLab's 'status' and 'source' fields become enumeration members."""

	@testcase("Statuses")
	def Statuses(self) -> None:
		"""
		Every status GitLab documents is a member carrying that value.

		Parses each of GitLab's 13 statuses.
		"""
		for value in (
			"created", "waiting_for_resource", "preparing", "waiting_for_callback", "pending", "running", "success",
			"failed", "canceling", "canceled", "skipped", "manual", "scheduled"
		):
			self.assertEqual(value, Status.Parse(value).value)

		self.assertEqual(13, len(Status))

	@testcase("Sources")
	def Sources(self) -> None:
		"""
		Every pipeline source GitLab knows is a member carrying that value.

		Parses each of the 20 values of GitLab's pipeline sources.
		"""
		for value in (
			"unknown", "push", "web", "trigger", "schedule", "api", "external", "pipeline", "chat", "webide",
			"merge_request_event", "external_pull_request_event", "parent_pipeline", "ondemand_dast_scan",
			"ondemand_dast_validation", "security_orchestration_policy", "container_registry_push", "duo_workflow",
			"pipeline_execution_policy_schedule", "dependency_management_security_update"
		):
			self.assertEqual(value, Source.Parse(value).value)

		self.assertEqual(20, len(Source))

	@testcase("No value")
	def Nothing(self) -> None:
		"""
		An absent or empty field is no member.

		Parses ``None`` and the empty string.
		"""
		self.assertIsNone(Status.Parse(None))
		self.assertIsNone(Status.Parse(""))
		self.assertIsNone(Source.Parse(None))

	@testcase("Unknown status")
	def UnknownStatus(self) -> None:
		"""
		A value GitLab doesn't document is an error, whose note lists the documented values.

		Checks the message, the note and the cause.
		"""
		with self.assertRaises(GitLabError) as context:
			Status.Parse("succeeded")

		self.assertEqual("'succeeded' is not a GitLab status.", str(context.exception))
		self.assertTrue(context.exception.__notes__[0].startswith("Known: created, waiting_for_resource, "))
		self.assertIsInstance(context.exception.__cause__, ValueError)

	@testcase("Unknown source")
	def UnknownSource(self) -> None:
		"""
		A pipeline source GitLab doesn't know is an error.

		Checks the message.
		"""
		with self.assertRaises(GitLabError) as context:
			Source.Parse("cron")

		self.assertEqual("'cron' is not a GitLab pipeline source.", str(context.exception))

	@testcase("Outcomes")
	def Outcomes(self) -> None:
		"""
		The statuses ending a job have an outcome; the others haven't ended.

		Checks the mapping and every status without an outcome.
		"""
		self.assertEqual(Outcome.Success, Status.Success.ToOutcome())
		self.assertEqual(Outcome.Failure, Status.Failed.ToOutcome())
		self.assertEqual(Outcome.Cancellation, Status.Canceled.ToOutcome())
		self.assertEqual(Outcome.Skip, Status.Skipped.ToOutcome())
		self.assertEqual(4, len(STATUS_TO_OUTCOME))

		for status in Status:
			if status not in STATUS_TO_OUTCOME:
				self.assertIsNone(status.ToOutcome())

	@testcase("Timeouts")
	def Timeouts(self) -> None:
		"""
		A job failed for a timeout has the outcome 'Timeout'; another failure reason is a failure.

		Checks both timeout reasons and a script failure.
		"""
		self.assertEqual(Outcome.Timeout, Status.Failed.ToOutcome("job_execution_timeout"))
		self.assertEqual(Outcome.Timeout, Status.Failed.ToOutcome("stuck_or_timeout_failure"))
		self.assertEqual(Outcome.Failure, Status.Failed.ToOutcome("script_failure"))
		self.assertEqual(Outcome.Success, Status.Success.ToOutcome("job_execution_timeout"))


@testsuite("Jobs")
class Jobs(Testcase):
	"""A job and a matrix instance, built by hand and read from a payload."""

	@testcase("Parse")
	def Parse(self) -> None:
		"""
		Every field GitLab reports about a job is read.

		Parses a successful job.
		"""
		job = Job.Parse(_job())

		self.assertEqual("build", job.Name)
		self.assertEqual(100, job.ID)
		self.assertEqual("build", job.Stage)
		self.assertIs(Status.Success, job.Status)
		self.assertIs(Outcome.Success, job.Outcome)
		self.assertFalse(job.AllowFailure)
		self.assertEqual(_datetime(0), job.CreatedAt)
		self.assertEqual(_datetime(10), job.StartedAt)
		self.assertEqual(_datetime(70), job.CompletedAt)
		self.assertEqual(60.0, job.Duration)
		self.assertEqual(1.5, job.QueuedDuration)
		self.assertEqual("https://gitlab.com/group/project/-/jobs/100", str(job.URL))
		self.assertEqual(["linux"], job.Tags)
		self.assertEqual(7, job.RunnerID)
		self.assertEqual("shared-runner", job.RunnerDescription)
		self.assertIsNone(job.FailureReason)

	@testcase("Not started")
	def NotStarted(self) -> None:
		"""
		A manual job hasn't started: no times, no runner, no outcome.

		Parses a job waiting to be started by hand.
		"""
		job = Job.Parse(_job(status="manual", started_at=None, finished_at=None, runner=None, queued_duration=None))

		self.assertIs(Status.Manual, job.Status)
		self.assertIsNone(job.Outcome)
		self.assertIsNone(job.StartedAt)
		self.assertIsNone(job.Duration)
		self.assertIsNone(job.RunnerID)
		self.assertIsNone(job.QueuedDuration)

	@testcase("Failure reason")
	def FailureReason(self) -> None:
		"""
		A job stopped by a timeout reports the reason, and the outcome 'Timeout'.

		Parses a failed job.
		"""
		job = Job.Parse(_job(status="failed", failure_reason="job_execution_timeout", allow_failure=True))

		self.assertEqual("job_execution_timeout", job.FailureReason)
		self.assertIs(Outcome.Timeout, job.Outcome)
		self.assertTrue(job.AllowFailure)

	@testcase("Missing name")
	def MissingName(self) -> None:
		"""
		A job without a name is an error naming the field's position.

		Checks the message.
		"""
		job = _job()
		del job["name"]
		with self.assertRaises(GitLabError) as context:
			Job.Parse(job, "jobs[3]")

		self.assertEqual("Field 'jobs[3].name' is missing.", str(context.exception))

	@testcase("Wrong timestamp")
	def WrongTimestamp(self) -> None:
		"""
		A timestamp that isn't ISO 8601 is an error naming the field, whose note reports the value.

		Checks the message and the note.
		"""
		with self.assertRaises(GitLabError) as context:
			Job.Parse(_job(started_at="yesterday"))

		self.assertEqual("Field 'job.started_at' isn't an ISO 8601 timestamp.", str(context.exception))
		self.assertEqual(["Got 'yesterday'."], context.exception.__notes__)

	@testcase("Payload type")
	def PayloadType(self) -> None:
		"""
		A payload that isn't a JSON object is rejected.

		Checks the message and the note.
		"""
		with self.assertRaises(TypeError) as context:
			Job.Parse([])

		self.assertEqual("Parameter 'json' is not of type 'dict'.", str(context.exception))
		self.assertEqual(["Got type 'list'."], context.exception.__notes__)

	@testcase("Parameter types")
	def ParameterTypes(self) -> None:
		"""
		Each parameter of a job is checked for its type.

		Builds a job with one wrong parameter at a time.
		"""
		with self.assertRaises(TypeError) as context:
			Job("build", identifier="100")
		self.assertEqual("Parameter 'identifier' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", stage=1)
		self.assertEqual("Parameter 'stage' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", allowFailure="no")
		self.assertEqual("Parameter 'allowFailure' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", queuedDuration="1")
		self.assertEqual("Parameter 'queuedDuration' is not of type 'float'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", status="success")
		self.assertEqual("Parameter 'status' is not of type 'Status'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", failureReason=1)
		self.assertEqual("Parameter 'failureReason' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", url="https://gitlab.com")
		self.assertEqual("Parameter 'url' is not of type 'URL'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", tags=[1])
		self.assertEqual("An element of parameter 'tags' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", runnerID="7")
		self.assertEqual("Parameter 'runnerID' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("build", runnerDescription=7)
		self.assertEqual("Parameter 'runnerDescription' is not of type 'str'.", str(context.exception))

	@testcase("Matrix instance")
	def MatrixInstance(self) -> None:
		"""
		A 'parallel:matrix' instance carries its values, named by position, and prints GitLab's name.

		Parses ``test: [3.14, linux]`` into a matrix.
		"""
		matrix = Matrix("test")
		job = MatrixJob.Parse(_job(name="test: [3.14, linux]"), parent=matrix)

		self.assertEqual("test", job.Name)
		self.assertEqual({"0": "3.14", "1": "linux"}, job.Dimensions)
		self.assertEqual("test: [3.14, linux]", str(job))
		self.assertEqual([job], matrix.Instances)

	@testcase("Parallel instance")
	def ParallelInstance(self) -> None:
		"""
		An instance of 'parallel: N' carries GitLab's variables, and prints GitLab's name.

		Parses ``test 2/4``.
		"""
		job = MatrixJob.Parse(_job(name="test 2/4"), parent=Matrix("test"))

		self.assertEqual("test", job.Name)
		self.assertEqual({"CI_NODE_INDEX": "2", "CI_NODE_TOTAL": "4"}, job.Dimensions)
		self.assertEqual("test 2/4", str(job))

	@testcase("Not a matrix instance")
	def NoInstance(self) -> None:
		"""
		A name without an instance's suffix is printed as it is.

		Builds an instance without dimensions, and parses names that only look like a suffix.
		"""
		self.assertEqual("deploy", str(MatrixJob("deploy", parent=Matrix("deploy"))))
		for name in ("deploy 1/x", "deploy x/2", ": [a]", "1/2"):
			with self.subTest(name):
				job = MatrixJob.Parse(_job(name=name), parent=Matrix("m"))

				self.assertEqual(name, job.Name)
				self.assertEqual({}, job.Dimensions)


def _pipeline(**fields: Any) -> dict[str, Any]:
	"""
	Build a successful pipeline.

	:param fields: Fields overriding the defaults.
	:returns:      The pipeline, as the GitLab REST API returns it.
	"""
	pipeline = {
		"id": 4711, "iid": 12, "project_id": 99, "name": None, "status": "success", "source": "push", "ref": "main",
		"sha": "abc123", "tag": False, "created_at": _time(0), "started_at": _time(5), "finished_at": _time(600),
		"queued_duration": 2.0, "web_url": "https://gitlab.com/group/project/-/pipelines/4711"
	}
	pipeline.update(fields)

	return pipeline


def _recording(name: str) -> dict[str, Any]:
	"""
	Read a recorded pipeline: its payloads and those of its child pipelines.

	:param name: Name of the fixture file in ``tests/data/Runs``, without extension.
	:returns:    The payloads - ``pipeline``, ``jobs``, ``bridges`` and ``downstream``.
	"""
	with Path(f"tests/data/Runs/{name}.json").open("r", encoding="utf-8") as file:
		return json_loads(file.read())


class _Response:
	"""A fake HTTP response for :func:`urllib.request.urlopen`."""

	def __init__(self, document: Any, link: str = "") -> None:
		"""
		Initializes a response answering with a JSON document.

		:param document: The document to answer with.
		:param link:     Optional, the response's ``Link`` header. Default: none.
		"""
		self._body =    json_dumps(document).encode("utf-8")
		self.headers = {"Content-Type": "application/json", "Link": link}

	def read(self) -> bytes:
		"""
		Return the response's body.

		:returns: The JSON document's text.
		"""
		return self._body

	def __enter__(self) -> "_Response":
		"""
		Enter the context and return the response.

		:returns: The response.
		"""
		return self

	def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
		"""
		Exit the context.

		:param exc_type: Exception type
		:param exc_val:  Exception instance
		:param exc_tb:   Exception's traceback.
		"""


@testsuite("Project client")
class Client(Testcase):
	"""The client of the GitLab REST API for one project."""

	@testcase("Project")
	def Project(self) -> None:
		"""
		A project is given by its identifier or its path; a path is URL-encoded in the resource path.

		Checks both forms.
		"""
		self.assertEqual("projects/74823", ProjectClient(74823).ProjectResourcePath)
		client = ProjectClient("gitlab-org/gitlab-development-kit")

		self.assertEqual("gitlab-org/gitlab-development-kit", client.Project)
		self.assertEqual("projects/gitlab-org%2Fgitlab-development-kit", client.ProjectResourcePath)
		self.assertEqual("https://gitlab.com/api/v4", str(client.APIURL))

	@testcase("Wrong project")
	def WrongProject(self) -> None:
		"""
		A project that is ``None``, of another type, negative, or a path with an empty part is rejected.

		Checks each message.
		"""
		with self.assertRaises(ValueError) as context:
			ProjectClient(None)
		self.assertEqual("Parameter 'project' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			ProjectClient(1.5)
		self.assertEqual("Parameter 'project' is neither of type 'int' nor 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			ProjectClient(-1)
		self.assertEqual("Parameter 'project' is a negative number.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			ProjectClient("group//project")
		self.assertEqual("Parameter 'project' is an empty path or has an empty part.", str(context.exception))

	@testcase("Pages of an array")
	def Pages(self) -> None:
		"""
		A list is read from every page GitLab links, and the token is sent as a bearer token.

		Answers two pages, the first linking the second.
		"""
		requests = []

		def urlopen(request: Any, timeout: float) -> _Response:
			"""
			Nested function answering a request with the page it asks for.

			:param request: The request.
			:param timeout: The request's timeout.
			:returns:       The page.
			"""
			requests.append(request)
			if request.full_url.endswith("page=2"):
				return _Response([{"id": 3}])

			nextPage = "https://gitlab.com/api/v4/projects/99/pipelines/1/jobs?per_page=100&page=2"
			return _Response([{"id": 1}, {"id": 2}], f'<{nextPage}>; rel="next"')

		with mock.patch("pyTooling.REST.urlopen", side_effect=urlopen):
			entries = ProjectClient(99, "secret").GetJSONArray("projects/99/pipelines/1/jobs")

		self.assertEqual([{"id": 1}, {"id": 2}, {"id": 3}], entries)
		self.assertEqual("https://gitlab.com/api/v4/projects/99/pipelines/1/jobs?per_page=100", requests[0].full_url)
		self.assertEqual("Bearer secret", requests[0].get_header("Authorization"))
		self.assertEqual(2, len(requests))

	@testcase("Not an array")
	def NotAnArray(self) -> None:
		"""
		A list answered with a JSON object is an error.

		Answers a JSON object.
		"""
		with mock.patch("pyTooling.REST.urlopen", return_value=_Response({"message": "x"})):
			with self.assertRaises(RESTError) as context:
				ProjectClient(99).GetJSONArray("projects/99/pipelines/1/jobs?scope=failed")

		self.assertEqual(
			"API didn't answer with a JSON array: https://gitlab.com/api/v4/projects/99/pipelines/1/jobs?scope=failed",
			str(context.exception)
		)

	@testcase("Page size")
	def PageSize(self) -> None:
		"""
		A page size out of GitLab's range 1..100 is rejected.

		Checks the message and the note.
		"""
		with self.assertRaises(ValueError) as context:
			ProjectClient(99).GetJSONArray("projects/99/pipelines", 101)

		self.assertEqual("Parameter 'pageSize' is out of range 1..100.", str(context.exception))
		self.assertEqual(["Got value '101'."], context.exception.__notes__)


@testsuite("Pipelines")
class Pipelines(Testcase):
	"""A pipeline and a group of pipelines, read from payloads."""

	@testcase("Parse")
	def Parse(self) -> None:
		"""
		Every field GitLab reports about a pipeline is read; a pipeline without a name is named by its number.

		Parses a successful pipeline without jobs.
		"""
		pipeline = Pipeline.Parse(_pipeline())

		self.assertEqual("#12", pipeline.Name)
		self.assertEqual(4711, pipeline.ID)
		self.assertEqual(12, pipeline.IID)
		self.assertEqual(99, pipeline.ProjectID)
		self.assertIs(Status.Success, pipeline.Status)
		self.assertIs(Outcome.Success, pipeline.Outcome)
		self.assertIs(Source.Push, pipeline.Source)
		self.assertEqual("main", pipeline.GitReference)
		self.assertEqual("abc123", pipeline.SHA)
		self.assertFalse(pipeline.IsTag)
		self.assertEqual(2.0, pipeline.QueuedDuration)
		self.assertEqual(595.0, pipeline.Duration)
		self.assertEqual("https://gitlab.com/group/project/-/pipelines/4711", str(pipeline.URL))
		self.assertIs(pipeline, pipeline.Pipeline)

	@testcase("Named pipeline")
	def Named(self) -> None:
		"""
		A pipeline named by 'workflow:name' keeps that name; without a number, it is named by its identifier.

		Parses a named pipeline, and one without number.
		"""
		self.assertEqual("Nightly", Pipeline.Parse(_pipeline(name="Nightly")).Name)
		self.assertEqual("#4711", Pipeline.Parse(_pipeline(iid=None)).Name)

	@testcase("Jobs and matrices")
	def JobsAndMatrices(self) -> None:
		"""
		Jobs are added in the order GitLab created them; matrix instances are grouped in a matrix.

		Parses jobs listed newest first, as GitLab lists them.
		"""
		pipeline = Pipeline.Parse(_pipeline(), [
			_job(id=104, name="test 2/2", stage="test"),
			_job(id=103, name="test 1/2", stage="test"),
			_job(id=102, name="lint: [ruff]", stage="test"),
			_job(id=101, name="build")
		])

		self.assertEqual(["build"], [job.Name for job in pipeline.Jobs])
		self.assertEqual(["lint", "test"], list(pipeline.Matrices))
		self.assertEqual(["test 1/2", "test 2/2"], [str(job) for job in pipeline.Matrices["test"].Instances])
		self.assertEqual(4, len(list(pipeline.IterateJobs())))
		self.assertEqual("test 1/2", pipeline.Matrices["test"].Instances[0].QualifiedName)

	@testcase("Missing identifier")
	def MissingIdentifier(self) -> None:
		"""
		A pipeline without an identifier is an error.

		Checks the message.
		"""
		with self.assertRaises(GitLabError) as context:
			Pipeline.Parse(_pipeline(id=None))

		self.assertEqual("Field 'pipeline.id' is missing.", str(context.exception))

	@testcase("Wrong payloads")
	def WrongPayloads(self) -> None:
		"""
		A pipeline or a job that isn't a JSON object is rejected; a job without a name is an error.

		Checks each message.
		"""
		with self.assertRaises(TypeError) as context:
			Pipeline.Parse([])
		self.assertEqual("Parameter 'pipeline' is not of type 'dict'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline.Parse(_pipeline(), [_job(), "job"])
		self.assertEqual("Job 1 is not of type 'dict'.", str(context.exception))

		with self.assertRaises(GitLabError) as context:
			Pipeline.Parse(_pipeline(), [{"id": 1}])
		self.assertEqual("Field 'jobs[0].name' is missing.", str(context.exception))

	@testcase("Parameter types")
	def ParameterTypes(self) -> None:
		"""
		Each parameter of a pipeline is checked for its type.

		Builds a pipeline with one wrong parameter at a time.
		"""
		with self.assertRaises(TypeError) as context:
			Pipeline("p", identifier="1")
		self.assertEqual("Parameter 'identifier' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", iid=True)
		self.assertEqual("Parameter 'iid' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", projectID=1.0)
		self.assertEqual("Parameter 'projectID' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", source="push")
		self.assertEqual("Parameter 'source' is not of type 'Source'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", gitReference=1)
		self.assertEqual("Parameter 'gitReference' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", sha=1)
		self.assertEqual("Parameter 'sha' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", isTag="no")
		self.assertEqual("Parameter 'isTag' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline("p", queuedDuration="2")
		self.assertEqual("Parameter 'queuedDuration' is not of type 'float'.", str(context.exception))

	@testcase("Group")
	def Group(self) -> None:
		"""
		A commit's pipelines form a group, grouped further by the reference they were started on.

		Parses a branch pipeline and a merge request pipeline of one commit.
		"""
		group = PipelineGroup.Parse(
			[_pipeline(), _pipeline(id=4712, iid=13, ref="refs/merge-requests/5/merge", source="merge_request_event")],
			{4711: [_job()]}
		)

		self.assertEqual("abc123", group.SHA)
		self.assertEqual(2, group.PipelineCount)
		self.assertEqual(1, len(group.Pipelines[0].Jobs))
		self.assertEqual(0, len(group.Pipelines[1].Jobs))
		self.assertEqual(["main", "refs/merge-requests/5/merge"], list(group.ByGitReference()))
		self.assertIs(Outcome.Success, group.Outcome)

	@testcase("Group of several commits")
	def GroupCommits(self) -> None:
		"""
		Pipelines of different commits, or of no reported commit, can't form a group without a given commit.

		Checks both messages.
		"""
		with self.assertRaises(GitLabError) as context:
			PipelineGroup.Parse([_pipeline(), _pipeline(id=4712, sha="def456")])
		self.assertEqual("The pipelines report different commits.", str(context.exception))
		self.assertEqual(["Got abc123, def456."], context.exception.__notes__)

		with self.assertRaises(GitLabError) as context:
			PipelineGroup.Parse([_pipeline(sha=None)])
		self.assertEqual(
			"None of the pipelines reports a 'sha', and parameter 'sha' wasn't given.", str(context.exception)
		)

		self.assertEqual("abc123", PipelineGroup.Parse([_pipeline(sha=None)], sha="abc123").SHA)

	@testcase("Group commit")
	def GroupCommit(self) -> None:
		"""
		A group's commit is checked.

		Checks each message.
		"""
		with self.assertRaises(ValueError) as context:
			PipelineGroup(None)
		self.assertEqual("Parameter 'name' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineGroup(1)
		self.assertEqual("Parameter 'name' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			PipelineGroup("")
		self.assertEqual("Parameter 'name' is empty.", str(context.exception))


@testsuite("Recorded pipelines")
class Recordings(Testcase):
	"""Pipelines of public projects on gitlab.com, as the REST API reported them."""

	@testcase("GitLab Development Kit")
	def GitLabDevelopmentKit(self) -> None:
		"""
		A merge request pipeline with 'parallel:matrix' instances and manual jobs.

		Reads the pipeline's jobs: 22 jobs, 6 matrices of 2 instances, one matrix of manual jobs, which hasn't ended.
		"""
		recording = _recording("GitLabDevelopmentKit")
		pipeline = Pipeline.Parse(recording["pipeline"], recording["jobs"])

		self.assertEqual("#47177", pipeline.Name)
		self.assertIs(Source.MergeRequestEvent, pipeline.Source)
		self.assertIs(Outcome.Success, pipeline.Outcome)
		self.assertEqual(22, len(pipeline.Jobs))
		self.assertEqual(6, len(pipeline.Matrices))
		self.assertEqual(34, len(list(pipeline.IterateJobs())))
		self.assertEqual(["rspec: [3.3]", "rspec: [3.4]"], [str(job) for job in pipeline.Matrices["rspec"].Instances])
		self.assertIsNone(pipeline.Matrices["novel:linux-amd64"].Outcome)

	@testcase("GitLab Runner")
	def GitLabRunner(self) -> None:
		"""
		A merge request pipeline with instances of 'parallel: 4'.

		Reads the pipeline's 86 jobs.
		"""
		recording = _recording("GitLabRunner")
		pipeline = Pipeline.Parse(recording["pipeline"], recording["jobs"])

		self.assertEqual(86, len(list(pipeline.IterateJobs())))
		instances = pipeline.Matrices["integration test"].Instances
		self.assertEqual(
			["integration test 1/4", "integration test 2/4", "integration test 3/4", "integration test 4/4"],
			[str(job) for job in instances]
		)
		self.assertEqual({"CI_NODE_INDEX": "3", "CI_NODE_TOTAL": "4"}, instances[2].Dimensions)


def _bridge(**fields: Any) -> dict[str, Any]:
	"""
	Build a successful trigger job, which started a child pipeline.

	:param fields: Fields overriding the defaults.
	:returns:      The trigger job, as the GitLab REST API lists it.
	"""
	bridge = {
		"id": 200, "name": "child", "stage": "deploy", "status": "success", "allow_failure": False,
		"created_at": _time(100), "started_at": _time(110), "finished_at": _time(120), "queued_duration": 0.5,
		"web_url": "https://gitlab.com/group/project/-/jobs/200",
		"pipeline": {"id": 4711, "project_id": 99},
		"downstream_pipeline": {
			"id": 4800, "project_id": 99, "status": "success", "created_at": _time(112), "updated_at": _time(400),
			"web_url": "https://gitlab.com/group/project/-/pipelines/4800"
		}
	}
	bridge.update(fields)

	return bridge


@testsuite("Downstream pipelines")
class Downstream(Testcase):
	"""Trigger jobs and the downstream pipelines they started."""

	@testcase("Child pipeline")
	def Child(self) -> None:
		"""
		A trigger job becomes a downstream pipeline holding the child pipeline's jobs, which reports the child pipeline's
		own status, URL and times.

		Parses a pipeline with a trigger job and the child pipeline's payloads.
		"""
		pipeline = Pipeline.Parse(_pipeline(), [_job()], [_bridge()], {
			4800: {
				"pipeline": _pipeline(
					id=4800, status="failed", created_at=_time(115), started_at=_time(125), finished_at=_time(320),
					web_url="https://gitlab.com/group/project/-/pipelines/4800"
				),
				"jobs": [_job(id=300, name="unit", status="failed", started_at=_time(130), finished_at=_time(300))]
			}
		})
		child = pipeline.Workflows["child"]

		self.assertIsInstance(child, DownstreamPipeline)
		self.assertIs(Status.Failed, child.Status)
		self.assertIs(Outcome.Failure, child.Outcome)
		self.assertEqual("https://gitlab.com/group/project/-/pipelines/4800", str(child.URL))
		self.assertEqual(_datetime(115), child.CreatedAt)
		self.assertEqual(_datetime(125), child.StartedAt)
		self.assertEqual(_datetime(320), child.CompletedAt)
		self.assertEqual(200, child.ID)
		self.assertEqual("deploy", child.Stage)
		self.assertIs(Status.Success, child.TriggerStatus)
		self.assertEqual("https://gitlab.com/group/project/-/jobs/200", str(child.TriggerURL))
		self.assertEqual(4800, child.DownstreamID)
		self.assertEqual(99, child.DownstreamProjectID)
		self.assertFalse(child.IsMultiProject)
		self.assertIsNone(child.Reference)
		self.assertEqual("child / unit", child.Jobs[0].QualifiedName)
		self.assertIs(pipeline, child.Jobs[0].Pipeline)
		self.assertEqual(2, len(list(pipeline.IterateJobs())))

	@testcase("Without the downstream payload")
	def Summary(self) -> None:
		"""
		A downstream pipeline whose payloads weren't read reports GitLab's summary of it: its creation, and its last update
		as its completion once it ended - but no start - and has no contents.

		Parses a trigger job without a downstream payload.
		"""
		child = Pipeline.Parse(_pipeline(), None, [_bridge()]).Workflows["child"]

		self.assertEqual(0, child.ElementCount)
		self.assertEqual(_datetime(112), child.CreatedAt)
		self.assertIsNone(child.StartedAt)
		self.assertEqual(_datetime(400), child.CompletedAt)
		self.assertIs(Outcome.Success, child.Outcome)
		self.assertEqual("https://gitlab.com/group/project/-/pipelines/4800", str(child.URL))

	@testcase("Running downstream pipeline")
	def Running(self) -> None:
		"""
		A downstream pipeline still running has no completion, though GitLab reports its last update.

		Parses a trigger job, whose downstream pipeline is running.
		"""
		summary = {"id": 4800, "project_id": 99, "status": "running", "created_at": _time(112), "updated_at": _time(400)}
		child = Pipeline.Parse(_pipeline(), None, [_bridge(downstream_pipeline=summary)]).Workflows["child"]

		self.assertIs(Status.Running, child.Status)
		self.assertIsNone(child.CompletedAt)
		self.assertIsNone(child.Outcome)

	@testcase("Multi-project pipeline")
	def MultiProject(self) -> None:
		"""
		A downstream pipeline of another project names that project as its reference, and reports its own status.

		Parses a trigger job, whose downstream pipeline failed, while the trigger job succeeded.
		"""
		child = Pipeline.Parse(_pipeline(), None, [_bridge(downstream_pipeline={
			"id": 5000, "project_id": 7, "status": "failed", "created_at": _time(112), "updated_at": _time(400),
			"web_url": "https://gitlab.com/gitlab-org/gitlab/-/pipelines/5000"
		})]).Workflows["child"]

		self.assertTrue(child.IsMultiProject)
		self.assertEqual("gitlab-org/gitlab", child.Reference)
		self.assertIs(Status.Failed, child.Status)
		self.assertIs(Status.Success, child.TriggerStatus)

	@testcase("Not started")
	def NotStarted(self) -> None:
		"""
		A manual trigger job hasn't started a pipeline yet: no status, no outcome, no times.

		Parses a trigger job without a downstream pipeline.
		"""
		child = Pipeline.Parse(_pipeline(), None, [_bridge(status="manual", downstream_pipeline=None)]).Workflows["child"]

		self.assertIsNone(child.DownstreamID)
		self.assertIsNone(child.IsMultiProject)
		self.assertIsNone(child.Status)
		self.assertIsNone(child.Outcome)
		self.assertIsNone(child.CreatedAt)
		self.assertIs(Status.Manual, child.TriggerStatus)

	@testcase("Matrix of trigger jobs")
	def Matrix(self) -> None:
		"""
		A trigger job with 'parallel:matrix' is an instance of a matrix, named as GitLab names it.

		Parses two instances.
		"""
		pipeline = Pipeline.Parse(_pipeline(), None, [
			_bridge(id=201, name="deploy: [staging]"), _bridge(id=202, name="deploy: [production]")
		])
		instances = pipeline.Matrices["deploy"].Instances

		self.assertEqual(["deploy: [staging]", "deploy: [production]"], [str(instance) for instance in instances])
		self.assertIsInstance(instances[0], MatrixDownstreamPipeline)
		self.assertEqual({"0": "staging"}, instances[0].Dimensions)
		self.assertEqual("deploy: [staging]", instances[0].QualifiedName)
		self.assertIs(Status.Success, instances[0].Status)

	@testcase("Wrong payloads")
	def WrongPayloads(self) -> None:
		"""
		A trigger job or a downstream payload that isn't a JSON object is rejected; a trigger job needs a name.

		Checks each message.
		"""
		with self.assertRaises(TypeError) as context:
			Pipeline.Parse(_pipeline(), None, ["bridge"])
		self.assertEqual("Trigger job 0 is not of type 'dict'.", str(context.exception))

		with self.assertRaises(GitLabError) as context:
			Pipeline.Parse(_pipeline(), None, [{"id": 1}])
		self.assertEqual("Field 'bridges[0].name' is missing.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline.Parse(_pipeline(), None, [_bridge()], {4800: []})
		self.assertEqual("Payload of 'bridges[0]' is not of type 'dict'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Pipeline.Parse(_pipeline(), None, [_bridge()], {4800: {"pipeline": []}})
		self.assertEqual("Downstream pipeline of 'bridges[0]' is not of type 'dict'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			DownstreamPipeline("child", downstreamID="4800")
		self.assertEqual("Parameter 'downstreamID' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			DownstreamPipeline("child", triggerStatus="success")
		self.assertEqual("Parameter 'triggerStatus' is not of type 'Status'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			DownstreamPipeline("child", triggerURL="https://gitlab.com")
		self.assertEqual("Parameter 'triggerURL' is not of type 'URL'.", str(context.exception))

	@testcase("Recorded child pipeline")
	def RecordedChild(self) -> None:
		"""
		A recorded pipeline with a child pipeline: the child's 38 jobs are below its trigger job, which reports the child
		pipeline's times.

		Reads the GitLab Development Kit's pipeline with its trigger job and child pipeline.
		"""
		recording = _recording("GitLabDevelopmentKit")
		pipeline = Pipeline.Parse(**recording)
		child = pipeline.Workflows["components"]
		childPipeline = recording["downstream"]["2954935189"]["pipeline"]

		self.assertEqual(2954935189, child.DownstreamID)
		self.assertFalse(child.IsMultiProject)
		self.assertEqual(38, len(child.Jobs))
		self.assertEqual(72, len(list(pipeline.IterateJobs())))
		self.assertEqual(datetime.fromisoformat(childPipeline["finished_at"]), child.CompletedAt)
		self.assertEqual("components / component:redis:test", child.GetElement("component:redis:test").QualifiedName)

	@testcase("Recorded multi-project pipelines")
	def RecordedMultiProject(self) -> None:
		"""
		A recorded pipeline triggering pipelines of two other projects, one of which failed.

		Reads the GitLab Runner's pipeline with its trigger jobs.
		"""
		pipeline = Pipeline.Parse(**_recording("GitLabRunner"))
		incept = pipeline.Workflows["trigger runner-incept tests"]

		self.assertEqual(2, len(pipeline.Workflows))
		self.assertTrue(incept.IsMultiProject)
		self.assertEqual("gitlab-org/ci-cd/tests/runner-incept", incept.Reference)
		self.assertIs(Status.Failed, incept.Status)
		self.assertIs(Status.Success, incept.TriggerStatus)
		self.assertEqual(
			"gitlab-org/ci-cd/gitlab-runner-ubi-images", pipeline.Workflows["trigger UBI images build"].Reference
		)


@testsuite("Stage dependencies")
class Stages(Testcase):
	"""Dependencies the stages and the 'needs' of a pipeline file imply."""

	def _Pipeline(self) -> Pipeline:
		"""
		Build a pipeline with jobs in three stages, a matrix and a trigger job.

		:returns: The pipeline.
		"""
		return Pipeline.Parse(_pipeline(), [
			_job(id=101, name="compile", stage="build"),
			_job(id=102, name="lint", stage="build"),
			_job(id=103, name="unit: [3.13]", stage="test"),
			_job(id=104, name="unit: [3.14]", stage="test"),
			_job(id=105, name="docs", stage="test"),
		], [_bridge(id=201, name="release", stage="deploy")])

	@testcase("Stages")
	def ByStage(self) -> None:
		"""
		An element needs every element of the nearest earlier stage holding elements.

		Applies the stages ``build``, ``test``, an empty ``package`` and ``deploy``.
		"""
		pipeline = self._Pipeline()
		pipeline.ApplyNeeds(("build", "test", "package", "deploy"))

		self.assertEqual([], pipeline.GetElement("compile").Needs)
		self.assertEqual(["compile", "lint"], [need.Name for need in pipeline.Matrices["unit"].Needs])
		self.assertEqual(["compile", "lint"], [need.Name for need in pipeline.GetElement("docs").Needs])
		self.assertEqual(["unit", "docs"], [need.Name for need in pipeline.Workflows["release"].Needs])
		pipeline.Validate()

	@testcase("Needs")
	def Needs(self) -> None:
		"""
		An element with 'needs' needs the named siblings only; 'needs: []' needs nothing.

		Applies the stages with 'needs' for the matrix and the trigger job.
		"""
		pipeline = self._Pipeline()
		pipeline.ApplyNeeds(("build", "test", "deploy"), {"unit": ["compile"], "release": []})

		self.assertEqual(["compile"], [need.Name for need in pipeline.Matrices["unit"].Needs])
		self.assertEqual([], pipeline.Workflows["release"].Needs)
		self.assertEqual(["compile", "lint"], [need.Name for need in pipeline.GetElement("docs").Needs])

	@testcase("Unknown stage")
	def UnknownStage(self) -> None:
		"""
		An element of a stage that isn't listed is an error, whose note lists the stages.

		Applies stages without ``deploy``.
		"""
		with self.assertRaises(GitLabError) as context:
			self._Pipeline().ApplyNeeds(("build", "test"))

		self.assertEqual(
			"Element 'release' of '#12' is in stage 'deploy', which isn't one of the stages.", str(context.exception)
		)
		self.assertEqual(["Stages: build, test."], context.exception.__notes__)

	@testcase("Unknown need")
	def UnknownNeed(self) -> None:
		"""
		A need naming no sibling is an error.

		Applies a need of a job that doesn't exist.
		"""
		with self.assertRaises(GitLabError) as context:
			self._Pipeline().ApplyNeeds(("build", "test", "deploy"), {"docs": ["missing"]})

		self.assertEqual("Element 'docs' of '#12' needs 'missing', which no sibling is named.", str(context.exception))

	@testcase("Wrong parameters")
	def WrongParameters(self) -> None:
		"""
		The stages and the needs are checked.

		Checks each message.
		"""
		with self.assertRaises(ValueError) as context:
			self._Pipeline().ApplyNeeds(None)
		self.assertEqual("Parameter 'stages' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			self._Pipeline().ApplyNeeds("build")
		self.assertEqual("Parameter 'stages' is not iterable.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			self._Pipeline().ApplyNeeds(("build",), ["unit"])
		self.assertEqual("Parameter 'needs' is not a mapping ('dict', ...).", str(context.exception))

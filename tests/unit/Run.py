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
from typing                import Any

from pyTooling.CI          import Matrix, Outcome
from pyTooling.GitLab      import GitLabError, Job, MatrixJob, Source, Status, STATUS_TO_OUTCOME
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

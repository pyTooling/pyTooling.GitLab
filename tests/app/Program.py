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
The commands of the :program:`pytooling-gitlab` program, run as the installed console script.
"""
from json                 import loads as json_loads
from pathlib              import Path
from re                   import search
from subprocess           import CompletedProcess
from tempfile             import TemporaryDirectory
from typing               import ClassVar

from pyTooling.TerminalUI import TerminalApplication
from pyTooling.Testing    import ApplicationTestcase, stripANSIColorCodes, testsuite, testcase


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


class ProgramMixin:
	"""
	What every testcase here runs, and how it reads what the program printed.

	A **classic mixin** - a plain class, no metaclass: it is combined with :class:`~pyTooling.Testing.Testcase`,
	which derives from :class:`unittest.TestCase` and has no ``__slots__``, so ``mixin=True`` would raise
	:exc:`~pyTooling.Exceptions.BaseClassWithoutSlotsError`.
	"""

	_CONSOLE_SCRIPT: ClassVar[str] = "pytooling-gitlab"  #: The console script under test.

	def Output(self, result: CompletedProcess) -> str:
		"""
		Return what the program printed on both streams, without the ANSI escape sequences colouring it.

		:param result: The completed process.
		:returns:      Both streams, joined and stripped of colour.
		"""
		return stripANSIColorCodes(f"{result.stdout}{result.stderr}")


@testsuite("Common commands")
class CommonCommands(ProgramMixin, ApplicationTestcase):
	"""The commands every pyTooling program has: no command at all, ``help`` and ``version``."""

	@testcase("No command")
	def NoCommand(self) -> None:
		"""
		A call without a command prints the headline and the help page.

		Runs the program without arguments.
		"""
		result = self.RunEntrypoint()

		self.assertExitCode(result)
		output = self.Output(result)
		self.assertIn("pyTooling.GitLab Service Program", output)
		self.assertIn("usage: pytooling-gitlab", output)

	@testcase("Version")
	def Version(self) -> None:
		"""
		'version' prints the version and the project's URL.

		Runs 'version'.
		"""
		result = self.RunEntrypoint("version")

		self.assertExitCode(result)
		output = self.Output(result)
		self.assertIn("Version:", output)
		self.assertIn("https://github.com/pyTooling/pyTooling.GitLab", output)

	@testcase("Help")
	def Help(self) -> None:
		"""
		The help page names every command, the help page of 'pipeline' every option.

		Runs 'help' and 'help pipeline'.
		"""
		result = self.RunEntrypoint("help")

		self.assertExitCode(result)
		self.assertIn("Read a CI pipeline", self.Output(result))

		result = self.RunEntrypoint("help", "pipeline")

		self.assertExitCode(result)
		output = self.Output(result)
		for option in (
			"--gitlab-project", "--gitlab-pipeline-id", "--gitlab-api-url", "--token", "--trace-file", "--gantt", "--force"
		):
			self.assertIn(option, output)

	@testcase("Unknown command")
	def UnknownCommand(self) -> None:
		"""
		A command the program doesn't have is argparse's error, not a traceback.

		Runs 'nonsense'.
		"""
		result = self.RunEntrypoint("nonsense")

		self.assertNotEqual(0, result.returncode)
		self.assertIn("invalid choice", self.Output(result))


@testsuite("Command 'pipeline'")
class PipelineCommand(ProgramMixin, ApplicationTestcase):
	"""
	What the ``pipeline`` command says before it reads anything.

	The command checks its outputs and its arguments before the network round-trip, so everything here runs without
	reaching GitLab.
	"""

	@testcase("Unknown trace format")
	def TraceFormat(self) -> None:
		"""
		A format '--trace-file' doesn't accept is reported with the formats it does.

		Runs the command with format 'nonsense'.
		"""
		result = self.RunEntrypoint(
			"pipeline", "--gitlab-project=group/project", "--gitlab-pipeline-id=1", "--trace-file=nonsense:trace.json"
		)

		self.assertExitCode(result, TerminalApplication.FATAL_EXIT_CODE)
		output = self.Output(result)
		self.assertIn("'nonsense' is not a valid TraceFormat.", output)
		self.assertIn("Allowed values: otlp-json", output)

	@testcase("Existing file")
	def ExistingFile(self) -> None:
		"""
		Without '--force', a file that exists is an error and keeps its content.

		Runs the command with an existing trace file.
		"""
		with TemporaryDirectory() as directory:
			existing = Path(directory) / "trace.json"
			existing.write_text("{}", encoding="utf-8")

			result = self.RunEntrypoint(
				"pipeline", "--gitlab-project=group/project", "--gitlab-pipeline-id=1", f"--trace-file={existing}"
			)

			self.assertExitCode(result, TerminalApplication.FATAL_EXIT_CODE)
			self.assertIn("--force", self.Output(result))
			self.assertEqual("{}", existing.read_text(encoding="utf-8"))

	@testcase("No project")
	def NoProject(self) -> None:
		"""
		Without '--gitlab-project' and without $CI_PROJECT_ID, the command says which one to set.

		Runs the command outside of a GitLab pipeline.
		"""
		result = self.RunEntrypoint("pipeline", "--gitlab-pipeline-id=1", environment={"CI_PROJECT_ID": None})

		self.assertExitCode(result, 2)
		output = self.Output(result)
		self.assertIn("No project given.", output)
		self.assertIn("$CI_PROJECT_ID", output)

	@testcase("Pipeline not a number")
	def PipelineNotANumber(self) -> None:
		"""
		A pipeline is the number in its URL, so anything else is rejected before the request.

		Runs the command with pipeline 'latest'.
		"""
		result = self.RunEntrypoint("pipeline", "--gitlab-project=group/project", "--gitlab-pipeline-id=latest")

		self.assertExitCode(result, 2)
		self.assertIn("Pipeline 'latest' isn't a number.", self.Output(result))


@testsuite("Outputs of 'pipeline'")
class PipelineOutputs(ProgramMixin, ApplicationTestcase):
	"""
	What ``pipeline`` writes, read from a finished public pipeline on gitlab.com.

	A finished pipeline doesn't change, so it can be read on every system; a public project's pipeline is read
	without a token.
	"""

	PROJECT:     ClassVar[str] = "gitlab-org/gitlab-development-kit"  #: The project the pipeline belongs to.
	PIPELINE_ID: ClassVar[int] = 2954836704                           #: A finished pipeline with a child pipeline.

	@testcase("Trace file and Gantt chart")
	def TraceFileAndGantt(self) -> None:
		"""
		The pipeline is read once, and both outputs are written from it.

		Runs the command with both outputs.
		"""
		with TemporaryDirectory() as directory:
			trace = Path(directory) / "report" / "Pipeline.otlp.json"
			chart = Path(directory) / "report" / "Pipeline.png"
			result = self.RunEntrypoint(
				"pipeline", f"--gitlab-project={self.PROJECT}", f"--gitlab-pipeline-id={self.PIPELINE_ID}",
				f"--trace-file={trace}", f"--gantt={chart}",
				timeout=120.0
			)

			self.assertExitCode(result)
			document = json_loads(trace.read_text(encoding="utf-8"))
			png = chart.read_bytes()

		output = self.Output(result)
		spans = document["resourceSpans"][0]["scopeSpans"][0]["spans"]
		self.assertIn("Pipeline:  #47177", output)
		self.assertIn(f"Trace:     {trace}", output)
		self.assertIsNotNone(search(r"Gantt: +.+Pipeline\.png \(\d+ rows\)", output), output)
		self.assertGreater(len(spans), 70, "The trace holds the pipeline, its jobs and its child pipeline's jobs.")
		self.assertEqual(b"\x89PNG", png[:4])

	@testcase("Token")
	def Token(self) -> None:
		"""
		'--token' is sent to GitLab instead of $GITLAB_TOKEN: GitLab rejects an invalid token, though the project is public.

		Runs the command with an invalid token, without $GITLAB_TOKEN.
		"""
		result = self.RunEntrypoint(
			"pipeline", f"--gitlab-project={self.PROJECT}", f"--gitlab-pipeline-id={self.PIPELINE_ID}",
			"--token=glpat-invalid-token-of-a-test",
			environment={"GITLAB_TOKEN": None},
			timeout=120.0
		)

		self.assertNotEqual(0, result.returncode)
		output = self.Output(result)
		self.assertIn("HTTP 401", output)
		self.assertIn("Check the project's path or identifier", output)

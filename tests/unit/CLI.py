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
Unit tests for :mod:`pyTooling.GitLab.CLI`: the program called in-process.
"""
from argparse                      import Namespace
from contextlib                    import redirect_stdout
from io                            import StringIO
from json                          import loads as json_loads
from os                            import environ
from pathlib                       import Path
from sys                           import argv as sys_argv
from tempfile                      import TemporaryDirectory
from typing                        import Any, ClassVar, Iterable
from unittest                      import skipUnless
from unittest.mock                 import MagicMock, patch

from pyTooling.Attributes.ArgParse import splitFormat
from pyTooling.Exceptions          import MissingDependencyError
from pyTooling.GitLab.CLI          import Application, main
from pyTooling.GitLab.CLI.Pipeline import GanttFormat, TraceFormat
from pyTooling.GitLab.Tracing      import PipelineTrace
from pyTooling.Testing             import Testcase, testsuite, testcase

from tests.unit.Run                import _recording

try:
	import matplotlib
	HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover
	HAS_MATPLOTLIB = False


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


def _run(arguments: Iterable[str]) -> str:
	"""
	Run the program with the given command line and return what it wrote to stdout.

	The program reads :data:`sys.argv`, so the command line is put there for the call, and it writes through two
	streams - its own, captured when it was constructed, and :data:`sys.stdout`, which argparse prints a help page
	to - so both are pointed at the same buffer.

	:param arguments: The command line, without the program's name.
	:returns:         Everything the program printed.
	"""
	application = Application()
	application.Configure()

	output = StringIO()
	argv = sys_argv[:]
	stream = application._stdout
	sys_argv[:] = ["pytooling-gitlab", *arguments]
	application._stdout = output
	try:
		with redirect_stdout(output):
			application.Run(enableAutoComplete=False)
	finally:
		sys_argv[:] = argv
		application._stdout = stream

	return output.getvalue()


@testsuite("Program")
class Program(Testcase):
	"""The program's parser and its common commands."""

	@testcase("Commands")
	def Commands(self) -> None:
		"""
		The commands are declared as attributes; the program is a singleton.

		Checks the parser's sub-parsers.
		"""
		application = Application()

		self.assertEqual("pytooling-gitlab", application.MainParser.prog)
		self.assertIn("help", application.SubParsers)
		self.assertIn("version", application.SubParsers)
		self.assertIn("pipeline", application.SubParsers)
		self.assertIs(application, Application())

	@testcase("Version")
	def Version(self) -> None:
		"""
		'version' prints the package's version and author.

		Runs the command.
		"""
		output = _run(["version"])

		self.assertIn("Version:", output)
		self.assertIn("Patrick Lehmann", output)

	@testcase("Help")
	def Help(self) -> None:
		"""
		'help', 'help <command>' and no command print a help page.

		Runs each call.
		"""
		self.assertIn("usage: pytooling-gitlab", _run(["help"]))
		self.assertIn("usage: pytooling-gitlab version", _run(["help", "version"]))
		self.assertIn("usage: pytooling-gitlab", _run([]))

		output = _run(["help", "pipeline"])
		for option in (
			"--gitlab-project", "--gitlab-pipeline-id", "--gitlab-api-url", "--token", "--trace-file", "--gantt", "--force"
		):
			self.assertIn(option, output)

	@testcase("Missing dependency")
	def MissingDependency(self) -> None:
		"""
		An optional package that isn't installed is not a bug: 'main' prints the commands installing it.

		Lets the program raise a missing dependency.
		"""
		application = Application()
		errors = StringIO()
		stream = application._stderr
		exception = MissingDependencyError(dependency="matplotlib", extra="diagram")

		application._stderr = errors
		try:
			with patch.object(Application, "Run", side_effect=exception):
				with self.assertRaises(SystemExit) as context:
					main()
		finally:
			application._stderr = stream

		self.assertEqual(MissingDependencyError.EXIT_CODE, context.exception.code)
		self.assertIn("pip install pyTooling[diagram]", errors.getvalue())


@testsuite("Formats")
class Formats(Testcase):
	"""The formats the outputs are written in."""

	@testcase("Trace formats")
	def TraceFormats(self) -> None:
		"""
		A trace is written as OTLP/JSON, also when the value names no format.

		Checks the default and a value without format.
		"""
		self.assertIs(TraceFormat.OTLPJSON, TraceFormat.DEFAULT)
		self.assertEqual(
			(TraceFormat.OTLPJSON, Path("report/Pipeline.otlp.json")), splitFormat("report/Pipeline.otlp.json", TraceFormat)
		)

	@testcase("Gantt formats")
	def GanttFormats(self) -> None:
		"""
		A Gantt format is the backend and the file format; the default draws a PNG.

		Checks every format and the default.
		"""
		self.assertIs(GanttFormat.MatplotlibPNG, GanttFormat.DEFAULT)
		for fileFormat in GanttFormat:
			backend, _, suffix = fileFormat.value.partition("-")
			self.assertEqual("matplotlib", backend)
			self.assertIn(suffix, ("png", "svg", "pdf"))


@testsuite("Command 'pipeline'")
class PipelineCommand(Testcase):
	"""
	The ``pipeline`` command, called in-process.

	The command falls back to the variables a GitLab pipeline sets, so a testcase about a missing argument takes the
	fallback away.
	"""

	NO_PIPELINE: ClassVar[tuple[str, ...]] = ("CI_PROJECT_ID", "CI_PIPELINE_ID", "CI_API_V4_URL")  #: Variables removed.

	def _Handle(self, **arguments: Any) -> tuple[str, Any]:
		"""
		Call the command's handler with the given arguments, outside of a GitLab pipeline.

		:param arguments: The arguments overriding the defaults.
		:returns:         What the program wrote to stderr, and the exception it exited with.
		"""
		application = Application()
		application._errorCount = 0
		namespace = Namespace(
			gitlabProject=None, gitlabPipelineID=None, gitlabAPIURL=None, token=None, traceFile=None, gantt=None, force=False
		)
		for name, value in arguments.items():
			setattr(namespace, name, value)

		errors = StringIO()
		stream = application._stderr
		application._stderr = errors
		try:
			with patch.dict(environ):
				for key in self.NO_PIPELINE:
					environ.pop(key, None)

				with self.assertRaises(SystemExit) as context:
					application.HandlePipeline(namespace)
		finally:
			application._stderr = stream

		return errors.getvalue(), context.exception

	@testcase("No project")
	def NoProject(self) -> None:
		"""
		Without '--gitlab-project' and without $CI_PROJECT_ID, the command says which one to set.

		Checks the messages and the exit code.
		"""
		errors, systemExit = self._Handle(gitlabPipelineID="1")

		self.assertEqual(2, systemExit.code)
		self.assertIn("No project given.", errors)
		self.assertIn("$CI_PROJECT_ID", errors)

	@testcase("No pipeline")
	def NoPipeline(self) -> None:
		"""
		Without '--gitlab-pipeline-id' and without $CI_PIPELINE_ID, the command says which one to set.

		Checks the messages.
		"""
		errors, systemExit = self._Handle(gitlabProject="group/project")

		self.assertEqual(2, systemExit.code)
		self.assertIn("No pipeline given.", errors)
		self.assertIn("$CI_PIPELINE_ID", errors)

	@testcase("Wrong arguments")
	def WrongArguments(self) -> None:
		"""
		A pipeline that isn't a number, a project with an empty part and a Gantt file of another type are rejected.

		Checks each message.
		"""
		errors, _ = self._Handle(gitlabProject="group/project", gitlabPipelineID="latest")
		self.assertIn("Pipeline 'latest' isn't a number.", errors)

		errors, _ = self._Handle(gitlabProject="group//project", gitlabPipelineID="1")
		self.assertIn("Project 'group//project' is neither a path nor an identifier.", errors)

		errors, _ = self._Handle(gantt="chart.svg")
		self.assertIn("Option '--gantt': format 'matplotlib-png' writes a '.png' file.", errors)

		errors, _ = self._Handle(traceFile="json:trace.json")
		self.assertIn("Option '--trace-file': 'json' is not a valid TraceFormat.", errors)

	@testcase("Reader")
	def Reader(self) -> None:
		"""
		The reader is made for the project - an identifier as a number -, the API's URL and the token.

		Replaces the reader and reads a pipeline of project 74823.
		"""
		reader = MagicMock()
		reader.return_value.ReadPipeline.return_value = PipelineTrace.Parse(**_recording("GitLabDevelopmentKit"))
		Application()._errorCount = 0
		environment = {"CI_API_V4_URL": "https://gitlab.example.com/api/v4", "GITLAB_TOKEN": "secret"}
		with patch.dict(environ, environment), patch("pyTooling.GitLab.CLI.Pipeline.PipelineReader", reader):
			output = _run(["pipeline", "--gitlab-project=74823", "--gitlab-pipeline-id=2954836704"])

		reader.assert_called_once_with(74823, "secret", apiURL="https://gitlab.example.com/api/v4")
		reader.return_value.ReadPipeline.assert_called_once_with(2954836704)
		self.assertIn("Pipeline:  #47177", output)

	@testcase("Token")
	def Token(self) -> None:
		"""
		'--token' wins over $GITLAB_TOKEN; without either, the pipeline is read anonymously.

		Replaces the reader and reads a pipeline three times.
		"""
		reader = MagicMock()
		reader.return_value.ReadPipeline.return_value = PipelineTrace.Parse(**_recording("GitLabDevelopmentKit"))
		arguments = ["pipeline", "--gitlab-project=group/project", "--gitlab-pipeline-id=1"]
		with patch("pyTooling.GitLab.CLI.Pipeline.PipelineReader", reader):
			with patch.dict(environ, {"GITLAB_TOKEN": "variable"}):
				Application()._errorCount = 0
				_run([*arguments, "--token=option"])
				Application()._errorCount = 0
				_run(arguments)

			with patch.dict(environ):
				environ.pop("GITLAB_TOKEN", None)
				Application()._errorCount = 0
				_run(arguments)

		self.assertEqual(["option", "variable", None], [call.args[1] for call in reader.call_args_list])


@testsuite("Outputs of 'pipeline'")
class PipelineOutputs(Testcase):
	"""What ``pipeline`` writes once it has read a pipeline, which is the recorded pipeline here."""

	def _Run(self, *outputs: str) -> str:
		"""
		Run ``pipeline`` with the given output options against the recorded pipeline.

		The program is a singleton, and testcases reporting an error leave it counted, so the count starts at zero.

		:param outputs: The output options, e.g. ``--trace-file=...``.
		:returns:       Everything the program printed.
		"""
		Application()._errorCount = 0
		trace = PipelineTrace.Parse(**_recording("GitLabDevelopmentKit"))
		with patch.object(Application, "_ReadPipeline", return_value=trace):
			return _run(["pipeline", "--gitlab-project=group/project", "--gitlab-pipeline-id=1", *outputs])

	@testcase("Trace file")
	def TraceFile(self) -> None:
		"""
		'--trace-file' writes the trace as OTLP/JSON.

		Writes the recorded pipeline's trace.
		"""
		with TemporaryDirectory() as directory:
			file = Path(directory) / "Pipeline.otlp.json"
			output = self._Run(f"--trace-file={file}")
			document = json_loads(file.read_text(encoding="utf-8"))

		self.assertIn(f"Trace:     {file}", output)
		self.assertGreater(len(document["resourceSpans"][0]["scopeSpans"][0]["spans"]), 70)

	@testcase("Gantt chart")
	@skipUnless(HAS_MATPLOTLIB, "matplotlib isn't installed.")
	def Gantt(self) -> None:
		"""
		'--gantt' draws the trace as a PNG image.

		Draws the recorded pipeline.
		"""
		with TemporaryDirectory() as directory:
			file = Path(directory) / "Pipeline.png"
			output = self._Run(f"--gantt={file}")
			png = file.read_bytes()

		self.assertIn("Gantt:     ", output)
		self.assertEqual(b"\x89PNG", png[:4])

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
"""
Unit tests for :mod:`pyTooling.GitLab.PipelineFile`: the configuration file, its stages, variables and jobs.
"""
from pathlib                       import Path
from tempfile                      import TemporaryDirectory
from textwrap                      import dedent

from pyTooling.GitLab.PipelineFile import DEFAULT_STAGES, Job, PipelineFile, PipelineFileError, Variable, When
from pyTooling.Testing             import Testcase, testsuite, testcase


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


DATA = Path(__file__).parent.parent / "data" / "PipelineFiles"
"""Directory of the configuration files the testcases read."""


class Fixture(Testcase):
	"""Base-class of the testcases: a temporary directory to write configuration files into."""

	_directory: TemporaryDirectory
	_path:      Path

	def setUp(self) -> None:
		self._directory = TemporaryDirectory()
		self._path = Path(self._directory.name)

	def tearDown(self) -> None:
		self._directory.cleanup()

	def _Write(self, content: str, name: str = ".gitlab-ci.yml") -> Path:
		"""
		Write a configuration file into the temporary directory.

		:param content: Content of the file; its indentation is removed.
		:param name:    Optional, name of the file. Default: ``.gitlab-ci.yml``.
		:returns:       Path to the file.
		"""
		path = self._path / name
		path.write_text(dedent(content), encoding="utf-8")
		return path


@testsuite("Configuration file")
class File(Fixture):
	"""Reading a configuration file: its path, stages and header document."""

	@testcase("Declared stages")
	def DeclaredStages(self) -> None:
		"""
		The stages of the 'stages' key run between '.pre' and '.post'.

		Reads a file declaring three stages.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Variables.yml")

		self.assertEqual(DATA / "Variables.yml", pipelineFile.Path)
		self.assertEqual(("build", "test", "deploy"), pipelineFile.DeclaredStages)
		self.assertEqual((".pre", "build", "test", "deploy", ".post"), pipelineFile.Stages)
		self.assertIsNone(pipelineFile.Parent)
		self.assertIs(pipelineFile, pipelineFile.PipelineFile)
		self.assertEqual(1, pipelineFile.Line)

	@testcase("Default stages")
	def DefaultStages(self) -> None:
		"""
		A file without 'stages' has GitLab's default stages; '.pre' and '.post' written in 'stages' aren't repeated.

		Reads a file without stages and one declaring '.pre' itself.
		"""
		withoutStages = PipelineFile.FromFile(self._Write("variables:\n  A: a\n"))
		self.assertIsNone(withoutStages.DeclaredStages)
		self.assertEqual((".pre", *DEFAULT_STAGES, ".post"), withoutStages.Stages)

		withPre = PipelineFile.FromFile(self._Write("stages: [.pre, lint]\n", "pre.yml"))
		self.assertEqual((".pre", "lint", ".post"), withPre.Stages)

	@testcase("Header document")
	def Header(self) -> None:
		"""
		A header document with 'spec' precedes the configuration.

		Reads a file with a header document and checks the configuration's variable.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Header.yml")

		self.assertEqual(["STAGE"], list(pipelineFile.Variables))
		self.assertEqual("$[[ inputs.stage ]]", pipelineFile.Variables["STAGE"].Value)

	@testcase("Empty file")
	def Empty(self) -> None:
		"""
		An empty file is an empty configuration.

		Reads an empty file and one holding a comment only.
		"""
		self.assertEqual({}, PipelineFile.FromFile(self._Write("")).Variables)
		self.assertEqual({}, PipelineFile.FromFile(self._Write("# nothing\n")).Variables)

	@testcase("No parent")
	def NoParent(self) -> None:
		"""
		A configuration file has no parent.

		Checks the TypeError's message.
		"""
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"))

		with self.assertRaises(TypeError) as context:
			pipelineFile.Parent = PipelineFile(Path("other.yml"))

		self.assertEqual("A 'pyTooling.GitLab.PipelineFile.PipelineFile' has no parent.", str(context.exception))


@testsuite("Variables")
class Variables(Testcase):
	"""Reading the top-level 'variables' key, and constructing variables."""

	@testcase("Values")
	def Values(self) -> None:
		"""
		A variable's value is its text; a number and a boolean are written as GitLab reads them.

		Checks the plain variables of the fixture.
		"""
		variables = PipelineFile.FromFile(DATA / "Variables.yml").Variables

		self.assertEqual("plain value", variables["PLAIN"].Value)
		self.assertEqual("3.14", variables["NUMBER"].Value)
		self.assertEqual("true", variables["FLAG"].Value)
		self.assertIsNone(variables["EMPTY"].Value)

	@testcase("Prefilled variables")
	def Prefilled(self) -> None:
		"""
		A variable declared as mapping has a value, a description, options and 'expand'.

		Checks the variables declared as mappings.
		"""
		variables = PipelineFile.FromFile(DATA / "Variables.yml").Variables

		environment = variables["DEPLOY_ENVIRONMENT"]
		self.assertEqual("staging", environment.Value)
		self.assertEqual("The deployment target.", environment.Description)
		self.assertEqual(("production", "staging"), environment.Options)
		self.assertIsNone(environment.Expand)

		note = variables["DEPLOY_NOTE"]
		self.assertIsNone(note.Value)
		self.assertEqual("The deployment note.", note.Description)
		self.assertEqual((), note.Options)

		raw = variables["RAW"]
		self.assertEqual("$NOT_EXPANDED", raw.Value)
		self.assertIs(False, raw.Expand)
		self.assertIsNone(raw.Description)

	@testcase("File order and lines")
	def Order(self) -> None:
		"""
		Variables keep their file order, their line, their parent and their file.

		Checks the names, a line, and each variable's parent.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Variables.yml")

		self.assertEqual(
			["PLAIN", "NUMBER", "FLAG", "EMPTY", "DEPLOY_ENVIRONMENT", "DEPLOY_NOTE", "RAW"], list(pipelineFile.Variables)
		)
		self.assertEqual(8, pipelineFile.Variables["PLAIN"].Line)
		for variable in pipelineFile.Variables.values():
			self.assertIs(pipelineFile, variable.Parent)
			self.assertIs(pipelineFile, variable.PipelineFile)
			self.assertEqual(variable.Name, str(variable))

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A variable constructed with a configuration file as parent is attached to it.

		Constructs a file and a variable.
		"""
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"), ["build"])
		variable = Variable("A", 3, "a", "Description.", ["a", "b"], True, parent=pipelineFile)

		self.assertIs(variable, pipelineFile.Variables["A"])
		self.assertEqual(("a", "b"), variable.Options)
		self.assertIs(True, variable.Expand)

	@testcase("Attached by the file")
	def Attached(self) -> None:
		"""
		A variable passed to a configuration file takes it as parent.

		Constructs a variable, then a file with it.
		"""
		variable = Variable("A", 3)
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"), variables=[variable])

		self.assertIs(pipelineFile, variable.Parent)
		self.assertIs(pipelineFile, variable.PipelineFile)


@testsuite("Parameter checks")
class Parameters(Testcase):
	"""The constructors reject parameters of the wrong type or value."""

	@testcase("Path")
	def Path(self) -> None:
		"""
		A configuration file needs a path.

		Checks the ValueError and the TypeError.
		"""
		with self.assertRaises(ValueError) as context:
			PipelineFile(None)
		self.assertEqual("Parameter 'path' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(".gitlab-ci.yml")
		self.assertEqual("Parameter 'path' is not of type 'Path'.", str(context.exception))

	@testcase("Stages")
	def Stages(self) -> None:
		"""
		A stage is a string.

		Checks the TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), ["build", 1])
		self.assertEqual("An element of parameter 'stages' is not of type 'str'.", str(context.exception))

	@testcase("Variables of a file")
	def FileVariables(self) -> None:
		"""
		A file's variables are of type Variable.

		Checks the TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), variables=["A"])
		self.assertEqual("An element of parameter 'variables' is not of type 'Variable'.", str(context.exception))

	@testcase("Line")
	def Line(self) -> None:
		"""
		An element's line is a positive integer.

		Checks the ValueErrors and the TypeErrors.
		"""
		with self.assertRaises(ValueError) as context:
			Variable("A", None)
		self.assertEqual("Parameter 'line' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable("A", "3")
		self.assertEqual("Parameter 'line' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable("A", True)
		self.assertEqual("Parameter 'line' is not of type 'int'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Variable("A", 0)
		self.assertEqual("Parameter 'line' is not positive.", str(context.exception))

	@testcase("Name of a variable")
	def Name(self) -> None:
		"""
		A variable's name is a non-empty string.

		Checks the ValueErrors and the TypeError.
		"""
		with self.assertRaises(ValueError) as context:
			Variable(None, 1)
		self.assertEqual("Parameter 'name' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable(1, 1)
		self.assertEqual("Parameter 'name' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Variable("", 1)
		self.assertEqual("Parameter 'name' is empty.", str(context.exception))

	@testcase("Texts of a variable")
	def Texts(self) -> None:
		"""
		A variable's value and description are strings, its options strings, 'expand' a boolean.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Variable("A", 1, value=1)
		self.assertEqual("Parameter 'value' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable("A", 1, description=1)
		self.assertEqual("Parameter 'description' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable("A", 1, options=["a", 1])
		self.assertEqual("An element of parameter 'options' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Variable("A", 1, expand="no")
		self.assertEqual("Parameter 'expand' is not of type 'bool'.", str(context.exception))

	@testcase("Parent of a variable")
	def Parent(self) -> None:
		"""
		A variable's parent is a configuration file or a job, and can't be reset to None.

		Checks the TypeErrors and the ValueError.
		"""
		with self.assertRaises(TypeError) as context:
			Variable("A", 1, parent=Variable("B", 1))
		self.assertEqual("Parameter 'parent' is not of type 'PipelineFile' or 'Job'.", str(context.exception))

		variable = Variable("A", 1)
		with self.assertRaises(TypeError) as context:
			variable.Parent = Variable("B", 1)
		self.assertEqual("Parameter 'value' is not of type 'PipelineFile' or 'Job'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			variable.Parent = None
		self.assertEqual("Parameter 'value' is None.", str(context.exception))


@testsuite("Malformed configuration files")
class Errors(Fixture):
	"""A file that isn't a well-formed configuration raises PipelineFileError, naming file and line."""

	@testcase("Path checks")
	def PathChecks(self) -> None:
		"""
		FromFile needs a path of type Path to an existing file.

		Checks the ValueError, the TypeError and the PipelineFileError.
		"""
		with self.assertRaises(ValueError) as context:
			PipelineFile.FromFile(None)
		self.assertEqual("Parameter 'path' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile.FromFile(".gitlab-ci.yml")
		self.assertEqual("Parameter 'path' is not of type 'Path'.", str(context.exception))

		missing = self._path / "missing.yml"
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(missing)
		self.assertEqual("Configuration file doesn't exist.", str(context.exception))
		self.assertEqual(missing, context.exception.Path)
		self.assertIsNone(context.exception.Line)
		self.assertIsInstance(context.exception.__cause__, FileNotFoundError)

	@testcase("Not YAML")
	def NotYAML(self) -> None:
		"""
		A file that isn't YAML names the line the parser stopped at.

		Checks message, line and note.
		"""
		path = self._Write("variables:\n  A: [unclosed\n")
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(path)

		self.assertEqual("Configuration file is not a YAML document.", str(context.exception))
		self.assertIsNotNone(context.exception.Line)
		self.assertEqual([f"In '{path}:{context.exception.Line}'."], context.exception.__notes__)

	@testcase("Documents")
	def Documents(self) -> None:
		"""
		A file holds at most two documents, the first of two being a header with 'spec'.

		Checks both messages.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec: {}\n---\na: 1\n---\nb: 2\n"))
		self.assertEqual("Configuration file holds more than two documents.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("header: {}\n---\na: 1\n"))
		self.assertEqual("Header document of configuration file has no 'spec' key.", str(context.exception))
		self.assertEqual(1, context.exception.Line)

	@testcase("Configuration not a mapping")
	def NotAMapping(self) -> None:
		"""
		The configuration is a mapping.

		Checks message and note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("- a\n- b\n"))

		self.assertEqual("Configuration is not a mapping.", str(context.exception))
		self.assertIn("Got type 'ruamel.yaml.comments.CommentedSeq'.", context.exception.__notes__)

	@testcase("Stages not a list")
	def StagesNotAList(self) -> None:
		"""
		Key 'stages' is a list.

		Checks message and line.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables: {}\nstages: build\n"))

		self.assertEqual("Key 'stages' is not a list.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

	@testcase("Malformed variables")
	def MalformedVariables(self) -> None:
		"""
		Each malformed variable declaration is named with its line.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables: [A]\n"))
		self.assertEqual("Key 'variables' is not a mapping.", str(context.exception))
		self.assertEqual(1, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A: [a]\n"))
		self.assertEqual("Variable 'A' is neither a value nor a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A:\n    value: a\n    secret: b\n"))
		self.assertEqual("Variable 'A' has unknown key 'secret'.", str(context.exception))
		self.assertEqual(4, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A:\n    options: a\n"))
		self.assertEqual("Key 'options' of variable 'A' is not a list of values.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A:\n    options: [[a]]\n"))
		self.assertEqual("Key 'options' of variable 'A' is not a list of values.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A:\n    expand: maybe\n"))
		self.assertEqual("Key 'expand' of variable 'A' is not a boolean.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

	@testcase("Unknown key's note")
	def UnknownKeyNote(self) -> None:
		"""
		The error of an unknown variable key lists the allowed keys.

		Checks the note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables:\n  A:\n    secret: b\n"))

		self.assertIn("Allowed keys: value, description, options, expand.", context.exception.__notes__)


@testsuite("Jobs")
class Jobs(Fixture):
	"""Reading the jobs of a configuration file, and constructing jobs."""

	@testcase("Jobs and hidden jobs")
	def Kinds(self) -> None:
		"""
		A top-level key, which isn't a global keyword, is a job; one starting with a dot a hidden job.

		Checks the collections, the counters and the iterators.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Jobs.yml")

		self.assertEqual(["build", "test", "deploy"], list(pipelineFile.Jobs))
		self.assertEqual(["build", "test", "deploy"], [job.Name for job in pipelineFile.IterateJobs()])
		self.assertEqual(3, pipelineFile.JobCount)
		self.assertTrue(pipelineFile.ContainsJob("build"))
		self.assertFalse(pipelineFile.ContainsJob(".template"))

		self.assertEqual([".template"], list(pipelineFile.HiddenJobs))
		self.assertEqual([".template"], [job.Name for job in pipelineFile.IterateHiddenJobs()])
		self.assertTrue(pipelineFile.HiddenJobs[".template"].IsHidden)
		for job in pipelineFile.IterateJobs():
			self.assertFalse(job.IsHidden)

	@testcase("Parent, file and location")
	def Location(self) -> None:
		"""
		A job knows its file and the line its name is written at; its variables have the job as parent.

		Checks job 'build' and its variable.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Jobs.yml")
		build = pipelineFile.Jobs["build"]

		self.assertIs(pipelineFile, build.Parent)
		self.assertIs(pipelineFile, build.PipelineFile)
		self.assertEqual(10, build.Line)
		self.assertEqual("Jobs.yml:10", build.Location)
		self.assertEqual("build", str(build))
		self.assertEqual("Jobs.yml", str(pipelineFile))

		variable = build.Variables["CONFIGURATION"]
		self.assertIs(build, variable.Parent)
		self.assertIs(pipelineFile, variable.PipelineFile)
		self.assertEqual("release", variable.Value)

	@testcase("Job 'build'")
	def Build(self) -> None:
		"""
		Stage, image and service names from mappings, tags, and a script with nested lists.

		Checks job 'build'.
		"""
		build = PipelineFile.FromFile(DATA / "Jobs.yml").Jobs["build"]

		self.assertEqual("build", build.Stage)
		self.assertEqual("python:3.14", build.Image)
		self.assertEqual(("postgres:17", "redis:8"), build.Services)
		self.assertEqual(("linux", "docker"), build.Tags)
		self.assertEqual(('echo "build"', 'echo "nested"', 'echo "lists"'), build.Script)
		self.assertEqual((), build.BeforeScript)
		self.assertIsNone(build.When)
		self.assertIsNone(build.AllowFailure)

	@testcase("Job 'test'")
	def Test(self) -> None:
		"""
		A job without stage is in 'test'; 'when' and the exit codes it may fail with.

		Checks job 'test'.
		"""
		test = PipelineFile.FromFile(DATA / "Jobs.yml").Jobs["test"]

		self.assertEqual("test", test.Stage)
		self.assertEqual(("pytest", ), test.Script)
		self.assertIs(When.Manual, test.When)
		self.assertIs(True, test.AllowFailure)
		self.assertEqual((137, 255), test.AllowedExitCodes)
		self.assertIsNone(test.Image)

	@testcase("Job 'deploy'")
	def Deploy(self) -> None:
		"""
		The environment's name from a mapping, 'allow_failure' as boolean, before and after scripts.

		Checks job 'deploy'.
		"""
		deploy = PipelineFile.FromFile(DATA / "Jobs.yml").Jobs["deploy"]

		self.assertEqual("deploy", deploy.Stage)
		self.assertEqual("production", deploy.Environment)
		self.assertIs(True, deploy.AllowFailure)
		self.assertEqual((), deploy.AllowedExitCodes)
		self.assertEqual(('echo "before"', ), deploy.BeforeScript)
		self.assertEqual(('echo "after"', ), deploy.AfterScript)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A job constructed with a file as parent is attached to it; a variable passed to a job takes it as parent.

		Constructs a file, a job and a hidden job.
		"""
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"))
		variable = Variable("A", 4, "a")
		job = Job("build", 3, "build", When.Always, False, [1], ["make"], variables=[variable], parent=pipelineFile)
		hidden = Job(".template", 7, parent=pipelineFile)

		self.assertIs(job, pipelineFile.Jobs["build"])
		self.assertIs(hidden, pipelineFile.HiddenJobs[".template"])
		self.assertIs(job, variable.Parent)
		self.assertIs(pipelineFile, variable.PipelineFile)
		self.assertEqual("test", hidden.Stage)

	@testcase("Attached by the file")
	def Attached(self) -> None:
		"""
		A job passed to a file takes it as parent, and its variables take the file too.

		Constructs a job with a variable, then a file with the job.
		"""
		variable = Variable("A", 4)
		job = Job("build", 3, variables=[variable])
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"), jobs=[job])

		self.assertIs(pipelineFile, job.Parent)
		self.assertIs(pipelineFile, variable.PipelineFile)
		self.assertEqual("line 3", Job("x", 3).Location)


@testsuite("Parameter checks of jobs")
class JobParameters(Testcase):
	"""The job's constructor rejects parameters of the wrong type or value."""

	@testcase("Name")
	def Name(self) -> None:
		"""
		A job's name is a non-empty string.

		Checks the ValueErrors and the TypeError.
		"""
		with self.assertRaises(ValueError) as context:
			Job(None, 1)
		self.assertEqual("Parameter 'name' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job(1, 1)
		self.assertEqual("Parameter 'name' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Job("", 1)
		self.assertEqual("Parameter 'name' is empty.", str(context.exception))

	@testcase("Stage")
	def Stage(self) -> None:
		"""
		A job's stage is a non-empty string.

		Checks the ValueErrors and the TypeError.
		"""
		with self.assertRaises(ValueError) as context:
			Job("a", 1, None)
		self.assertEqual("Parameter 'stage' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, 1)
		self.assertEqual("Parameter 'stage' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Job("a", 1, "")
		self.assertEqual("Parameter 'stage' is empty.", str(context.exception))

	@testcase("Scalars")
	def Scalars(self) -> None:
		"""
		'when' is a When, 'allowFailure' a boolean, 'image' and 'environment' strings.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Job("a", 1, when="manual")
		self.assertEqual("Parameter 'when' is not of type 'When'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, allowFailure="yes")
		self.assertEqual("Parameter 'allowFailure' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, image=1)
		self.assertEqual("Parameter 'image' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, environment=1)
		self.assertEqual("Parameter 'environment' is not of type 'str'.", str(context.exception))

	@testcase("Collections")
	def Collections(self) -> None:
		"""
		Exit codes are integers, script lines, services and tags strings, variables Variables.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Job("a", 1, allowedExitCodes=[True])
		self.assertEqual("An element of parameter 'allowedExitCodes' is not of type 'int'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, script=["make", 1])
		self.assertEqual("An element of parameter 'script' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, afterScript=[1])
		self.assertEqual("An element of parameter 'afterScript' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, tags=[1])
		self.assertEqual("An element of parameter 'tags' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, variables=["A"])
		self.assertEqual("An element of parameter 'variables' is not of type 'Variable'.", str(context.exception))

	@testcase("Jobs of a file")
	def FileJobs(self) -> None:
		"""
		A file's jobs are of type Job.

		Checks the TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), jobs=["build"])
		self.assertEqual("An element of parameter 'jobs' is not of type 'Job'.", str(context.exception))


@testsuite("Malformed jobs")
class JobErrors(Fixture):
	"""A malformed job raises PipelineFileError, naming file and line."""

	@testcase("Job not a mapping")
	def NotAMapping(self) -> None:
		"""
		A job is a mapping.

		Checks message and line.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables: {}\nbuild: make\n"))
		self.assertEqual("Job 'build' is not a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

	@testcase("Undeclared stage")
	def UndeclaredStage(self) -> None:
		"""
		A job's stage is one of the pipeline's stages.

		Checks message, line and note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("stages: [build]\nlint:\n  stage: check\n  script: make\n"))
		self.assertEqual("Job 'lint' is in stage 'check', which isn't declared.", str(context.exception))
		self.assertEqual(2, context.exception.Line)
		self.assertIn("Stages: .pre, build, .post.", context.exception.__notes__)

	@testcase("Unknown 'when'")
	def UnknownWhen(self) -> None:
		"""
		Key 'when' holds a value GitLab knows.

		Checks message and note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  when: sometimes\n"))
		self.assertEqual("Key 'when' of job 'build' is not a known value.", str(context.exception))
		self.assertEqual(2, context.exception.Line)
		self.assertIn(
			"Allowed values: on_success, on_failure, never, always, manual, delayed.", context.exception.__notes__
		)

	@testcase("Keys of the wrong kind")
	def WrongKinds(self) -> None:
		"""
		'allow_failure' is a boolean or a mapping, 'services' and 'tags' lists, a script no mapping, 'variables' a mapping.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  allow_failure: maybe\n"))
		self.assertEqual("Key 'allow_failure' of job 'build' is not a boolean.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  services: postgres\n"))
		self.assertEqual("Key 'services' of job 'build' is not a list.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  tags: linux\n"))
		self.assertEqual("Key 'tags' of job 'build' is not a list.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  script:\n    run: make\n"))
		self.assertEqual("Key 'script' of job 'build' is not a script.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  variables: [A]\n"))
		self.assertEqual("Key 'variables' of job 'build' is not a mapping.", str(context.exception))

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
Unit tests for :mod:`pyTooling.GitLab.PipelineFile`: the configuration file, its stages, variables,
jobs, needs, rules, workflow, includes and default.
"""
from pathlib                       import Path
from tempfile                      import TemporaryDirectory
from textwrap                      import dedent

from pyTooling.GitLab.PipelineFile import DEFAULT_STAGES, Job, Need, NeedKind, PipelineFile, PipelineFileError
from pyTooling.GitLab.PipelineFile import Default, Include, IncludeKind, Rule, Variable, When, Workflow
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
		job = Job(
			"build", 3, "build", when=When.Always, allowFailure=False, allowedExitCodes=[1], script=["make"],
			variables=[variable], parent=pipelineFile
		)
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


@testsuite("Needs")
class Needs(Fixture):
	"""Reading the 'needs' of jobs, and constructing needs."""

	@testcase("Without and with an empty 'needs'")
	def Empty(self) -> None:
		"""
		A job without 'needs' has None, one with 'needs: []' an empty tuple.

		Checks jobs 'production' and 'lint'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Needs.yml").Jobs

		self.assertIsNone(jobs["production"].Needs)
		self.assertEqual((), jobs["production"].NeededJobs)
		self.assertEqual((), jobs["lint"].Needs)

	@testcase("Jobs of the same pipeline")
	def SamePipeline(self) -> None:
		"""
		A need names a job as a string, or as 'job' of a mapping with 'artifacts'.

		Checks jobs 'linux:rspec' and 'mac:rspec'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Needs.yml").Jobs

		linux = jobs["linux:rspec"].Needs[0]
		self.assertIs(NeedKind.Job, linux.Kind)
		self.assertEqual("linux:build", linux.JobName)
		self.assertIs(True, linux.Artifacts)
		self.assertIs(False, linux.IsOptional)
		self.assertIs(jobs["linux:build"], linux.NeededJob)
		self.assertIs(jobs["linux:rspec"], linux.Parent)
		self.assertEqual(20, linux.Line)
		self.assertEqual("linux:build", str(linux))
		self.assertEqual((jobs["linux:build"], ), jobs["linux:rspec"].NeededJobs)

		mac = jobs["mac:rspec"].Needs[0]
		self.assertEqual("mac:build", mac.JobName)
		self.assertIs(False, mac.Artifacts)
		self.assertEqual((jobs["mac:build"], ), jobs["mac:rspec"].NeededJobs)

	@testcase("Optional need of a missing job")
	def Optional(self) -> None:
		"""
		An optional need may name a job the file doesn't have; it resolves to no job.

		Checks job 'optional'.
		"""
		job = PipelineFile.FromFile(DATA / "Needs.yml").Jobs["optional"]

		need = job.Needs[0]
		self.assertIs(True, need.IsOptional)
		self.assertIsNone(need.NeededJob)
		self.assertEqual((), job.NeededJobs)

	@testcase("Other pipelines")
	def OtherPipelines(self) -> None:
		"""
		A need of another pipeline's job, another project's job, or another pipeline's status.

		Checks jobs 'child', 'downstream' and 'mirror'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Needs.yml").Jobs

		child = jobs["child"].Needs[0]
		self.assertIs(NeedKind.PipelineJob, child.Kind)
		self.assertEqual("generate", child.JobName)
		self.assertEqual("$PARENT_PIPELINE_ID", child.Pipeline)
		self.assertIsNone(child.NeededJob)

		downstream = jobs["downstream"].Needs[0]
		self.assertIs(NeedKind.ProjectJob, downstream.Kind)
		self.assertEqual("group/other", downstream.Project)
		self.assertEqual("main", downstream.Ref)
		self.assertEqual("group/other: build", str(downstream))

		mirror = jobs["mirror"].Needs[0]
		self.assertIs(NeedKind.PipelineStatus, mirror.Kind)
		self.assertIsNone(mirror.JobName)
		self.assertEqual("other/project", mirror.Pipeline)
		self.assertEqual("pipeline other/project", str(mirror))
		self.assertEqual((), jobs["mirror"].NeededJobs)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A need constructed with a job as parent is attached to it; a need passed to a job takes it as parent.

		Constructs two jobs with needs.
		"""
		job = Job("test", 3)
		need = Need("build", 4, parent=job)
		self.assertEqual((need, ), job.Needs)
		self.assertIs(job, need.Parent)

		passed = Need("build", 9)
		other = Job("other", 8, needs=[passed])
		self.assertIs(other, passed.Parent)
		self.assertEqual((passed, ), other.Needs)


@testsuite("Parameter checks of needs")
class NeedParameters(Testcase):
	"""The need's constructor rejects parameters of the wrong type, or missing for its kind."""

	@testcase("Kind")
	def Kind(self) -> None:
		"""
		A need's kind is a NeedKind.

		Checks the ValueError and the TypeError.
		"""
		with self.assertRaises(ValueError) as context:
			Need("a", 1, None)
		self.assertEqual("Parameter 'kind' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Need("a", 1, "job")
		self.assertEqual("Parameter 'kind' is not of type 'NeedKind'.", str(context.exception))

	@testcase("Types")
	def Types(self) -> None:
		"""
		The texts are strings, the flags booleans.

		Checks a TypeError of each kind of parameter.
		"""
		with self.assertRaises(TypeError) as context:
			Need(1, 1)
		self.assertEqual("Parameter 'job' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Need("a", 1, NeedKind.ProjectJob, project="p", ref=1)
		self.assertEqual("Parameter 'ref' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Need("a", 1, artifacts="yes")
		self.assertEqual("Parameter 'artifacts' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Need("a", 1, optional=1)
		self.assertEqual("Parameter 'optional' is not of type 'bool'.", str(context.exception))

	@testcase("Missing for the kind")
	def MissingForKind(self) -> None:
		"""
		A kind needs its keys: a job, a pipeline, a project and a ref.

		Checks message and note of each ValueError.
		"""
		with self.assertRaises(ValueError) as context:
			Need(None, 1)
		self.assertEqual("Parameter 'job' is None.", str(context.exception))
		self.assertEqual(["A need of kind 'job' needs it."], context.exception.__notes__)

		with self.assertRaises(ValueError) as context:
			Need(None, 1, NeedKind.PipelineStatus)
		self.assertEqual("Parameter 'pipeline' is None.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Need("a", 1, NeedKind.ProjectJob, ref="main")
		self.assertEqual("Parameter 'project' is None.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Need("a", 1, NeedKind.ProjectJob, project="group/other")
		self.assertEqual("Parameter 'ref' is None.", str(context.exception))

	@testcase("Needs of a job")
	def JobNeeds(self) -> None:
		"""
		A job's needs are of type Need.

		Checks the TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Job("a", 1, needs=["build"])
		self.assertEqual("An element of parameter 'needs' is not of type 'Need'.", str(context.exception))


@testsuite("Malformed needs")
class NeedErrors(Fixture):
	"""A malformed or unresolvable 'needs' raises PipelineFileError, naming file and line."""

	@testcase("Unknown job")
	def UnknownJob(self) -> None:
		"""
		A need names a job of the file, unless it is optional.

		Checks message, line and note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  script: make\ntest:\n  needs: [biuld]\n"))
		self.assertEqual("Job 'test' needs job 'biuld', which the file doesn't have.", str(context.exception))
		self.assertEqual(4, context.exception.Line)
		self.assertIn("Jobs: build, test.", context.exception.__notes__)

	@testcase("Cycle")
	def Cycle(self) -> None:
		"""
		Jobs don't need each other in a cycle.

		Checks the message naming the cycle.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("a:\n  needs: [b]\nb:\n  needs: [c]\nc:\n  needs: [a]\n"))
		self.assertEqual("Jobs need each other in a cycle: a -> b -> c -> a.", str(context.exception))
		self.assertEqual(1, context.exception.Line)

	@testcase("Malformed entries")
	def MalformedEntries(self) -> None:
		"""
		'needs' is a list or a mapping; an entry a job's name or a mapping of known keys, with the keys its kind needs.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs: build\n"))
		self.assertEqual("Key 'needs' of job 'test' is neither a list nor a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs:\n    - [build]\n"))
		self.assertEqual("Need of job 'test' is neither a job's name nor a mapping.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs:\n    - job: build\n      when: always\n"))
		self.assertEqual("Need of job 'test' has unknown key 'when'.", str(context.exception))
		self.assertEqual(4, context.exception.Line)
		self.assertIn("Allowed keys: job, artifacts, optional, pipeline, project, ref.", context.exception.__notes__)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs:\n    - job: build\n      artifacts: some\n"))
		self.assertEqual("Key 'artifacts' of a need of job 'test' is not a boolean.", str(context.exception))
		self.assertEqual(4, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs:\n    - artifacts: false\n"))
		self.assertEqual("Need of job 'test' has no 'job' key.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  needs:\n    - project: group/other\n      job: build\n"))
		self.assertEqual("Need of job 'test' with key 'project' has no 'ref' key.", str(context.exception))


@testsuite("Rules and workflow")
class Rules(Fixture):
	"""Reading the 'workflow' key and the 'rules' of jobs, and constructing rules."""

	@testcase("Workflow")
	def WorkflowKey(self) -> None:
		"""
		The workflow has the pipeline's name and its rules.

		Checks the workflow and its rules.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Rules.yml")
		workflow = pipelineFile.Workflow

		self.assertIs(pipelineFile, workflow.Parent)
		self.assertEqual("Pipeline for $CI_COMMIT_REF_NAME", workflow.Name)
		self.assertEqual(2, workflow.Line)
		self.assertEqual(3, len(workflow.Rules))
		self.assertEqual('$CI_PIPELINE_SOURCE == "merge_request_event"', workflow.Rules[0].Condition)
		self.assertIsNone(workflow.Rules[0].When)
		self.assertIs(When.Never, workflow.Rules[1].When)
		self.assertIsNone(workflow.Rules[2].Condition)
		self.assertIs(When.Always, workflow.Rules[2].When)
		for rule in workflow.Rules:
			self.assertIs(workflow, rule.Parent)
			self.assertIs(pipelineFile, rule.PipelineFile)

	@testcase("Without workflow")
	def WithoutWorkflow(self) -> None:
		"""
		A file without 'workflow' has none, a job without 'rules' no rules.

		Checks fixture 'Jobs.yml'.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Jobs.yml")

		self.assertIsNone(pipelineFile.Workflow)
		self.assertEqual([], pipelineFile.Jobs["build"].Rules)

	@testcase("Rules of a job")
	def JobRules(self) -> None:
		"""
		'if' with 'changes'; 'changes' as mapping with 'compare_to', 'when' and 'allow_failure'; 'exists' with variables.

		Checks the three rules of job 'docs'.
		"""
		docs = PipelineFile.FromFile(DATA / "Rules.yml").Jobs["docs"]
		first, second, third = docs.Rules

		self.assertEqual('$CI_COMMIT_BRANCH == "main"', first.Condition)
		self.assertEqual(("doc/**/*", "README.md"), first.Changes)
		self.assertIsNone(first.CompareTo)
		self.assertEqual(13, first.Line)
		self.assertIs(docs, first.Parent)

		self.assertIsNone(second.Condition)
		self.assertEqual(("src/**/*", ), second.Changes)
		self.assertEqual("refs/heads/main", second.CompareTo)
		self.assertIs(When.Manual, second.When)
		self.assertIs(True, second.AllowFailure)

		self.assertEqual(("Dockerfile", ), third.Exists)
		self.assertEqual((), third.Changes)
		self.assertEqual({"IMAGE": "docker", "RETRIES": "3"}, third.Variables)
		self.assertIsNone(third.AllowFailure)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A rule constructed with a job or workflow as parent is attached to it; one passed to them takes them as parent.

		Constructs a job and a workflow with rules.
		"""
		job = Job("build", 3)
		rule = Rule(4, "$A", parent=job)
		self.assertEqual([rule], job.Rules)

		passed = Rule(8, when=When.Always)
		workflow = Workflow(7, "Name", [passed])
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"), workflow=workflow)
		self.assertIs(workflow, passed.Parent)
		self.assertIs(pipelineFile, passed.PipelineFile)
		self.assertIs(workflow, pipelineFile.Workflow)

		other = PipelineFile(Path("other.yml"))
		attached = Workflow(2, parent=other)
		self.assertIs(attached, other.Workflow)


@testsuite("Parameter checks of rules and workflow")
class RuleParameters(Testcase):
	"""The constructors of rules and workflows reject parameters of the wrong type."""

	@testcase("Rule")
	def RuleChecks(self) -> None:
		"""
		A rule's texts are strings, its paths strings, 'when' a When, 'allowFailure' a boolean.

		Checks a TypeError of each kind of parameter.
		"""
		with self.assertRaises(TypeError) as context:
			Rule(1, condition=1)
		self.assertEqual("Parameter 'condition' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Rule(1, exists=["a", 1])
		self.assertEqual("An element of parameter 'exists' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Rule(1, when="never")
		self.assertEqual("Parameter 'when' is not of type 'When'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Rule(1, allowFailure=1)
		self.assertEqual("Parameter 'allowFailure' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Rule(1, parent=PipelineFile(Path(".gitlab-ci.yml")))
		self.assertEqual("Parameter 'parent' is not of type 'Job' or 'Workflow' or 'Include'.", str(context.exception))

	@testcase("Workflow")
	def WorkflowChecks(self) -> None:
		"""
		A workflow's name is a string, its rules Rules; a file's workflow a Workflow; a job's rules Rules.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Workflow(1, 1)
		self.assertEqual("Parameter 'name' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Workflow(1, rules=["$A"])
		self.assertEqual("An element of parameter 'rules' is not of type 'Rule'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), workflow="workflow")
		self.assertEqual("Parameter 'workflow' is not of type 'Workflow'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, rules=["$A"])
		self.assertEqual("An element of parameter 'rules' is not of type 'Rule'.", str(context.exception))


@testsuite("Malformed rules and workflow")
class RuleErrors(Fixture):
	"""A malformed 'workflow' or 'rules' raises PipelineFileError, naming file and line."""

	@testcase("Workflow not a mapping")
	def WorkflowNotAMapping(self) -> None:
		"""
		Key 'workflow' is a mapping.

		Checks message and line.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables: {}\nworkflow: [a]\n"))
		self.assertEqual("Key 'workflow' is not a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

	@testcase("Malformed rules")
	def MalformedRules(self) -> None:
		"""
		'rules' is a list of mappings, whose keys hold values of the right kind.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules: always\n"))
		self.assertEqual("Key 'rules' of job 'build' is not a list.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("workflow:\n  rules:\n    - always\n"))
		self.assertEqual("Rule of the workflow is not a mapping.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules:\n    - changes: README.md\n"))
		self.assertEqual("Key 'changes' of a rule of job 'build' is not a list of paths.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules:\n    - exists:\n        project: a\n"))
		self.assertEqual("Key 'exists' of a rule of job 'build' is not a list of paths.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules:\n    - when: sometimes\n"))
		self.assertEqual("Key 'when' of a rule of job 'build' is not a known value.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules:\n    - allow_failure: often\n"))
		self.assertEqual("Key 'allow_failure' of a rule of job 'build' is not a boolean.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("build:\n  rules:\n    - variables: [A]\n"))
		self.assertEqual("Key 'variables' of a rule of job 'build' is not a mapping.", str(context.exception))


@testsuite("Includes and default")
class Includes(Fixture):
	"""Reading the 'include' and 'default' keys, and constructing includes and defaults."""

	@testcase("Kinds of includes")
	def Kinds(self) -> None:
		"""
		A path is a local include, a URL a remote one; a mapping names its kind by its key.

		Checks kind and location of every include.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Includes.yml")
		includes = pipelineFile.Includes

		self.assertEqual(7, len(includes))
		self.assertIs(IncludeKind.Local, includes[0].Kind)
		self.assertEqual("/ci/build.yml", includes[0].Location)
		self.assertIs(IncludeKind.Local, includes[1].Kind)
		self.assertEqual("/ci/test.yml", includes[1].Location)
		self.assertIs(IncludeKind.Remote, includes[2].Kind)
		self.assertIs(IncludeKind.Project, includes[3].Kind)
		self.assertIs(IncludeKind.Project, includes[4].Kind)
		self.assertIs(IncludeKind.Template, includes[5].Kind)
		self.assertEqual("Auto-DevOps.gitlab-ci.yml", includes[5].Location)
		self.assertIs(IncludeKind.Component, includes[6].Kind)
		self.assertEqual("component: $CI_SERVER_FQDN/group/components/lint@1.2", str(includes[6]))
		for include in includes:
			self.assertIs(pipelineFile, include.Parent)

	@testcase("Another project's files")
	def Project(self) -> None:
		"""
		An include of another project has the project's path, its files - a list or one - and a reference.

		Checks the two includes of other projects.
		"""
		includes = PipelineFile.FromFile(DATA / "Includes.yml").Includes

		self.assertEqual("group/shared", includes[3].Location)
		self.assertEqual("v1.0", includes[3].Ref)
		self.assertEqual(("/templates/a.yml", "/templates/b.yml"), includes[3].Files)
		self.assertEqual(6, includes[3].Line)

		self.assertEqual(("/templates/c.yml", ), includes[4].Files)
		self.assertIsNone(includes[4].Ref)

	@testcase("Inputs and rules of an include")
	def InputsAndRules(self) -> None:
		"""
		An include passes inputs with the types they are written with, and has rules.

		Checks the component's include.
		"""
		component = PipelineFile.FromFile(DATA / "Includes.yml").Includes[6]

		self.assertEqual({"stage": "test", "strict": True}, component.Inputs)
		self.assertEqual(1, len(component.Rules))
		self.assertEqual('$LINT == "yes"', component.Rules[0].Condition)
		self.assertIs(component, component.Rules[0].Parent)
		self.assertEqual({}, PipelineFile.FromFile(DATA / "Includes.yml").Includes[0].Inputs)

	@testcase("Default and global keywords")
	def Default(self) -> None:
		"""
		'default' sets image, services, tags and scripts; a global keyword fills in what 'default' doesn't set.

		Checks the default of the fixture.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Includes.yml")
		default = pipelineFile.Default

		self.assertIs(pipelineFile, default.Parent)
		self.assertEqual(21, default.Line)
		self.assertEqual("python:3.14", default.Image)
		self.assertEqual(("postgres:17", ), default.Services)
		self.assertEqual(("linux", ), default.Tags)
		self.assertEqual(('echo "default before"', ), default.BeforeScript)
		self.assertEqual(('echo "global after"', ), default.AfterScript)

	@testcase("Global keywords only")
	def GlobalsOnly(self) -> None:
		"""
		Without 'default', the global keywords form the default, starting at the first one; without both, there's none.

		Reads a file with global keywords, and one without.
		"""
		default = PipelineFile.FromFile(self._Write("variables: {}\nimage: alpine\nbefore_script: [echo]\n")).Default
		self.assertEqual(2, default.Line)
		self.assertEqual("alpine", default.Image)
		self.assertEqual(("echo", ), default.BeforeScript)

		self.assertIsNone(PipelineFile.FromFile(DATA / "Jobs.yml").Default)
		self.assertEqual([], PipelineFile.FromFile(DATA / "Jobs.yml").Includes)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		An include and a default constructed with a file as parent are attached to it, and so are those passed to it.

		Constructs includes and defaults both ways.
		"""
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"))
		include = Include(IncludeKind.Local, "/ci/a.yml", 2, parent=pipelineFile)
		default = Default(5, "alpine", parent=pipelineFile)
		self.assertEqual([include], pipelineFile.Includes)
		self.assertIs(default, pipelineFile.Default)

		rule = Rule(4)
		passedInclude = Include(IncludeKind.Template, "A.yml", 3, rules=[rule])
		passedDefault = Default(6)
		other = PipelineFile(Path("other.yml"), includes=[passedInclude], default=passedDefault)
		self.assertIs(other, passedInclude.Parent)
		self.assertIs(other, rule.PipelineFile)
		self.assertIs(other, passedDefault.Parent)


@testsuite("Parameter checks of includes and default")
class IncludeParameters(Testcase):
	"""The constructors of includes and defaults reject parameters of the wrong type or value."""

	@testcase("Include")
	def IncludeChecks(self) -> None:
		"""
		An include's kind is an IncludeKind, its location a non-empty string, its files strings.

		Checks each exception.
		"""
		with self.assertRaises(ValueError) as context:
			Include(None, "a", 1)
		self.assertEqual("Parameter 'kind' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Include("local", "a", 1)
		self.assertEqual("Parameter 'kind' is not of type 'IncludeKind'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Include(IncludeKind.Local, None, 1)
		self.assertEqual("Parameter 'location' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Include(IncludeKind.Local, 1, 1)
		self.assertEqual("Parameter 'location' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Include(IncludeKind.Local, "", 1)
		self.assertEqual("Parameter 'location' is empty.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Include(IncludeKind.Project, "g/p", 1, files=[1])
		self.assertEqual("An element of parameter 'files' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Include(IncludeKind.Project, "g/p", 1, ref=1)
		self.assertEqual("Parameter 'ref' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Include(IncludeKind.Local, "a", 1, rules=["$A"])
		self.assertEqual("An element of parameter 'rules' is not of type 'Rule'.", str(context.exception))

	@testcase("Default")
	def DefaultChecks(self) -> None:
		"""
		A default's image is a string, its lists strings; a file's includes are Includes, its default a Default.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Default(1, 1)
		self.assertEqual("Parameter 'image' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Default(1, tags=[1])
		self.assertEqual("An element of parameter 'tags' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), includes=["/ci/a.yml"])
		self.assertEqual("An element of parameter 'includes' is not of type 'Include'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), default="alpine")
		self.assertEqual("Parameter 'default' is not of type 'Default'.", str(context.exception))


@testsuite("Malformed includes and default")
class IncludeErrors(Fixture):
	"""A malformed 'include' or 'default' raises PipelineFileError, naming file and line."""

	@testcase("Malformed includes")
	def MalformedIncludes(self) -> None:
		"""
		An include is a path or a mapping naming one kind; another project's include has files; inputs are a mapping.

		Checks message, line and note of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - [a]\n"))
		self.assertEqual("Include is neither a path nor a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - ref: main\n"))
		self.assertEqual("Include has none of its kinds' keys.", str(context.exception))
		self.assertIn("Kinds: local, project, remote, template, component.", context.exception.__notes__)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - local: a.yml\n    template: b.yml\n"))
		self.assertEqual("Include has more than one of its kinds' keys.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - project: g/p\n"))
		self.assertEqual("Include of another project has no 'file' key.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - project: g/p\n    file:\n      path: a.yml\n"))
		self.assertEqual("Key 'file' of an include is neither a path nor a list.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include:\n  - local: a.yml\n    inputs: [a]\n"))
		self.assertEqual("Key 'inputs' of an include is not a mapping.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

	@testcase("Malformed default")
	def MalformedDefault(self) -> None:
		"""
		'default' is a mapping, its 'services' and 'tags' lists, its scripts no mappings.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("variables: {}\ndefault: alpine\n"))
		self.assertEqual("Key 'default' is not a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("default:\n  services: postgres\n"))
		self.assertEqual("Key 'services' of the default is not a list.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("default:\n  tags: linux\n"))
		self.assertEqual("Key 'tags' of the default is not a list.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("default:\n  before_script:\n    run: a\n"))
		self.assertEqual("Key 'before_script' of the default is not a script.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

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
Unit tests for :mod:`pyTooling.GitLab.PipelineFile`.

The configuration file, its stages, variables, jobs, needs, rules, workflow, includes and default, how jobs extend each
other, parallel jobs, triggers, inputs, and the pipeline a file defines.
"""
from pathlib                       import Path
from tempfile                      import TemporaryDirectory
from textwrap                      import dedent

from pyTooling.GitLab.PipelineFile import DEFAULT_STAGES, Job, Need, NeedKind, PipelineFile, PipelineFileError
from pyTooling.GitLab.PipelineFile import Default, Include, IncludeKind, Parallel, Rule, Trigger, TriggerStrategy
from pyTooling.GitLab.PipelineFile import Input, InputType, Variable, Workflow
from pyTooling.GitLab.PipelineFile import DefinedJob, DefinedMatrix, DefinedMatrixJob, DefinedPipeline
from pyTooling.GitLab.PipelineFile import DefinedWorkflow, IncludeResolver
from pyTooling.CI                  import RuleOutcome
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
		self.assertIs(RuleOutcome.Manual, test.When)
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
			"build", 3, "build", when=RuleOutcome.Always, allowFailure=False, allowedExitCodes=[1], script=["make"],
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
		'when' is a RuleOutcome, 'allowFailure' a boolean, 'image' and 'environment' strings.

		Checks each TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			Job("a", 1, when="manual")
		self.assertEqual("Parameter 'when' is not of type 'RuleOutcome'.", str(context.exception))

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
			"Allowed values: on_success, on_failure, always, manual, delayed, never.", context.exception.__notes__
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
		self.assertEqual(["A need of kind 'Job' needs it."], context.exception.__notes__)

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
		self.assertIn(
			"Allowed keys: job, artifacts, optional, pipeline, project, ref, parallel.", context.exception.__notes__
		)

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
		self.assertIs(RuleOutcome.Never, workflow.Rules[1].When)
		self.assertIsNone(workflow.Rules[2].Condition)
		self.assertIs(RuleOutcome.Always, workflow.Rules[2].When)
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
		self.assertIs(RuleOutcome.Manual, second.When)
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

		passed = Rule(8, when=RuleOutcome.Always)
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
		A rule's texts are strings, its paths strings, 'when' a RuleOutcome, 'allowFailure' a boolean.

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
		self.assertEqual("Parameter 'when' is not of type 'RuleOutcome'.", str(context.exception))

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
		self.assertIn("Kinds: local, project, remote, template, component, artifact.", context.exception.__notes__)

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


@testsuite("Extends, references and default")
class Extends(Fixture):
	"""Merging the jobs a job extends, resolving '!reference' tags, and giving jobs the default."""

	@testcase("Deep merge")
	def DeepMerge(self) -> None:
		"""
		A job's keys are those of the job it extends, mappings merged, its own keys winning.

		Checks job 'job' of the fixture.
		"""
		job = PipelineFile.FromFile(DATA / "Extends.yml").Jobs["job"]

		self.assertEqual((".base", ), job.Extends)
		self.assertEqual((), job.Unresolved)
		self.assertEqual("build", job.Stage)
		self.assertEqual(("base", ), job.Tags)
		self.assertEqual(["VAR1", "VAR2"], list(job.Variables))
		self.assertEqual("job 1", job.Variables["VAR1"].Value)
		self.assertEqual("base 2", job.Variables["VAR2"].Value)
		self.assertEqual(19, job.Variables["VAR2"].Line)

	@testcase("References")
	def References(self) -> None:
		"""
		A '!reference' in a list splices the referred list in; references nest.

		Checks the script and the rules of job 'job', and job 'nested'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Extends.yml").Jobs

		self.assertEqual(("echo setup", "echo job"), jobs["job"].Script)
		self.assertEqual(2, len(jobs["job"].Rules))
		self.assertEqual("$A", jobs["job"].Rules[0].Condition)
		self.assertEqual(27, jobs["job"].Rules[0].Line)
		self.assertIs(RuleOutcome.Never, jobs["job"].Rules[1].When)
		self.assertEqual(("echo one", "echo two"), jobs["nested"].Script)

	@testcase("Several jobs extended")
	def Several(self) -> None:
		"""
		The jobs of an 'extends' list merge in order, a later one winning.

		Checks job 'multi'.
		"""
		multi = PipelineFile.FromFile(DATA / "Extends.yml").Jobs["multi"]

		self.assertEqual((".base", ".other"), multi.Extends)
		self.assertEqual("test", multi.Stage)
		self.assertEqual("python", multi.Image)
		self.assertEqual(("base", ), multi.Tags)
		self.assertEqual(("base", ), multi.Script)

	@testcase("Null removes a key")
	def Null(self) -> None:
		"""
		A key set to null removes what the extended job has.

		Checks job 'nulled'.
		"""
		nulled = PipelineFile.FromFile(DATA / "Extends.yml").Jobs["nulled"]

		self.assertEqual({}, nulled.Variables)
		self.assertEqual(("base", ), nulled.Script)

	@testcase("Default")
	def Default(self) -> None:
		"""
		A job gets the default's keys it doesn't set, unless 'inherit.default' excludes them; a hidden job doesn't.

		Checks jobs 'job', 'noDefault', 'someDefault' and hidden job '.base'.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Extends.yml")
		jobs = pipelineFile.Jobs

		self.assertEqual("alpine", jobs["job"].Image)
		self.assertEqual(("echo default", ), jobs["job"].BeforeScript)

		self.assertIsNone(jobs["noDefault"].Image)
		self.assertEqual((), jobs["noDefault"].Tags)

		self.assertEqual("alpine", jobs["someDefault"].Image)
		self.assertEqual((), jobs["someDefault"].Tags)

		self.assertIsNone(pipelineFile.HiddenJobs[".base"].Image)

	@testcase("Unresolved with includes")
	def Unresolved(self) -> None:
		"""
		A file including files may extend or refer to jobs it doesn't have; the job lists them.

		Reads a file including a file, whose job extends and refers to a missing job.
		"""
		path = self._Write(dedent("""\
			include: /ci/templates.yml
			job:
			  extends: .template
			  script:
			    - !reference [.setup, script]
			    - echo job
			"""))
		job = PipelineFile.FromFile(path).Jobs["job"]

		self.assertEqual((".template", ), job.Extends)
		self.assertEqual(("!reference [.setup, script]", "extends .template"), job.Unresolved)
		self.assertEqual(("echo job", ), job.Script)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A job is constructed with the names it extends and what it couldn't resolve.

		Checks the properties and the TypeError.
		"""
		job = Job("a", 1, extends=[".base"], unresolved=["extends .base"])
		self.assertEqual((".base", ), job.Extends)
		self.assertEqual(("extends .base", ), job.Unresolved)

		with self.assertRaises(TypeError) as context:
			Job("a", 1, extends=[1])
		self.assertEqual("An element of parameter 'extends' is not of type 'str'.", str(context.exception))


@testsuite("Malformed extends and references")
class ExtendsErrors(Fixture):
	"""What can't be resolved, without included files to explain it, raises PipelineFileError."""

	@testcase("Missing job")
	def MissingJob(self) -> None:
		"""
		A job extends a job of the file, if the file includes no files.

		Checks message and line.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("job:\n  extends: .base\n  script: x\n"))
		self.assertEqual("Job 'job' extends job '.base', which the file doesn't have.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

	@testcase("Missing key")
	def MissingKey(self) -> None:
		"""
		A reference refers to a key of the file, if the file includes no files - and always in 'default'.

		Checks message and line of both errors.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write(".a:\n  b: 1\njob:\n  script:\n    - !reference [.a, script]\n"))
		self.assertEqual(
			"Reference [.a, script] of job 'job' refers to a key the file doesn't have.", str(context.exception)
		)
		self.assertEqual(5, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("include: a.yml\ndefault:\n  before_script: !reference [.a, b]\n"))
		self.assertEqual("Reference [.a, b] of the default refers to a key the file doesn't have.", str(context.exception))

	@testcase("Cycle")
	def Cycle(self) -> None:
		"""
		Jobs don't extend each other in a cycle.

		Checks the message naming the cycle.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write(".a:\n  extends: .b\n.b:\n  extends: .a\n"))
		self.assertEqual("Jobs extend each other in a cycle: .a -> .b -> .a.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

	@testcase("Too deep")
	def TooDeep(self) -> None:
		"""
		'extends' nests at most 11 levels, '!reference' tags 10.

		Checks both messages.
		"""
		chain = "".join(f".j{level}:\n  extends: .j{level + 1}\n" for level in range(12)) + ".j12:\n  script: x\n"
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write(chain))
		self.assertEqual("Job '.j11' extends more than 11 levels.", str(context.exception))

		references = ".r:\n" + "".join(f"  l{level}:\n    - !reference [.r, l{level + 1}]\n" for level in range(11))
		references += "  l11: [echo]\njob:\n  script:\n    - !reference [.r, l0]\n"
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write(references))
		self.assertIn("nests more than 10 levels.", str(context.exception))


@testsuite("Parallel jobs and triggers")
class ParallelAndTriggers(Fixture):
	"""Reading 'parallel' and 'trigger', and constructing them."""

	@testcase("Matrix")
	def Matrix(self) -> None:
		"""
		A matrix entry contributes the product of its variables' lists, named as GitLab names the instances.

		Checks job 'build'.
		"""
		build = PipelineFile.FromFile(DATA / "Parallel.yml").Jobs["build"]
		parallel = build.Parallel

		self.assertIs(build, parallel.Parent)
		self.assertTrue(parallel.IsMatrix)
		self.assertIsNone(parallel.Count)
		self.assertEqual(({"PROVIDER": ("aws", ), "STACK": ("monitoring", "app1")},
			{"PROVIDER": ("gcp", "vultr"), "STACK": ("data", )}), parallel.Matrix)
		self.assertEqual(
			[
				{"PROVIDER": "aws", "STACK": "monitoring"},
				{"PROVIDER": "aws", "STACK": "app1"},
				{"PROVIDER": "gcp", "STACK": "data"},
				{"PROVIDER": "vultr", "STACK": "data"}
			],
			parallel.Combinations
		)
		self.assertEqual(
			["build: [aws, monitoring]", "build: [aws, app1]", "build: [gcp, data]", "build: [vultr, data]"],
			parallel.InstanceNames
		)

	@testcase("Count")
	def Count(self) -> None:
		"""
		'parallel: N' runs a job N times, named 'job i/N'.

		Checks job 'test'.
		"""
		parallel = PipelineFile.FromFile(DATA / "Parallel.yml").Jobs["test"].Parallel

		self.assertFalse(parallel.IsMatrix)
		self.assertEqual(3, parallel.Count)
		self.assertEqual((), parallel.Matrix)
		self.assertEqual(["test 1/3", "test 2/3", "test 3/3"], parallel.InstanceNames)

	@testcase("Needed instances")
	def NeededInstances(self) -> None:
		"""
		A need's 'parallel.matrix' names the needed instances.

		Checks the need of job 'test'.
		"""
		need = PipelineFile.FromFile(DATA / "Parallel.yml").Jobs["test"].Needs[0]

		self.assertIs(need, need.Parallel.Parent)
		self.assertEqual(["build: [aws, app1]"], need.Parallel.InstanceNames)
		self.assertIsNone(PipelineFile.FromFile(DATA / "Needs.yml").Jobs["linux:rspec"].Needs[0].Parallel)

	@testcase("Child pipelines")
	def ChildPipelines(self) -> None:
		"""
		A trigger including files starts a child pipeline; an include of a job's artifact names the job.

		Checks jobs 'child' and 'single'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Parallel.yml").Jobs
		trigger = jobs["child"].Trigger

		self.assertIs(jobs["child"], trigger.Parent)
		self.assertTrue(trigger.IsChildPipeline)
		self.assertIsNone(trigger.Project)
		self.assertIs(TriggerStrategy.Mirror, trigger.Strategy)
		self.assertEqual(2, len(trigger.Includes))
		self.assertIs(IncludeKind.Local, trigger.Includes[0].Kind)
		self.assertEqual({"environment": "staging"}, trigger.Includes[0].Inputs)
		self.assertIs(trigger, trigger.Includes[0].Parent)
		self.assertIs(IncludeKind.Artifact, trigger.Includes[1].Kind)
		self.assertEqual("generated.yml", trigger.Includes[1].Location)
		self.assertEqual("build", trigger.Includes[1].ArtifactJob)

		single = jobs["single"].Trigger
		self.assertEqual("/ci/single.yml", single.Includes[0].Location)
		self.assertIsNone(single.Strategy)

	@testcase("Other projects' pipelines")
	def OtherProjects(self) -> None:
		"""
		A trigger naming a project, as mapping or as string, starts that project's pipeline.

		Checks jobs 'downstream' and 'short'.
		"""
		jobs = PipelineFile.FromFile(DATA / "Parallel.yml").Jobs

		downstream = jobs["downstream"].Trigger
		self.assertFalse(downstream.IsChildPipeline)
		self.assertEqual("group/other", downstream.Project)
		self.assertEqual("main", downstream.Branch)
		self.assertIs(TriggerStrategy.Depend, downstream.Strategy)
		self.assertEqual([], downstream.Includes)

		self.assertEqual("group/short", jobs["short"].Trigger.Project)
		self.assertIsNone(jobs["short"].Trigger.Branch)
		self.assertIsNone(jobs["build"].Trigger)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		A parallel and a trigger constructed with a job as parent are attached to it, and so are those passed to it.

		Constructs both both ways.
		"""
		job = Job("a", 1)
		parallel = Parallel(2, 4, parent=job)
		trigger = Trigger(3, "group/other", parent=job)
		self.assertIs(parallel, job.Parallel)
		self.assertIs(trigger, job.Trigger)
		self.assertEqual(["a 1/4", "a 2/4", "a 3/4", "a 4/4"], parallel.InstanceNames)

		include = Include(IncludeKind.Local, "/ci/child.yml", 5)
		passedTrigger = Trigger(4, includes=[include])
		passedParallel = Parallel(6, matrix=[{"A": ["1", "2"]}])
		other = Job("b", 3, parallel=passedParallel, trigger=passedTrigger)
		self.assertIs(other, passedTrigger.Parent)
		self.assertIs(passedTrigger, include.Parent)
		self.assertEqual(["b: [1]", "b: [2]"], passedParallel.InstanceNames)

		need = Need("b", 7, parallel=Parallel(8, matrix=[{"A": ["1"]}]))
		self.assertEqual(["b: [1]"], need.Parallel.InstanceNames)


@testsuite("Parameter checks of parallel and trigger")
class ParallelParameters(Testcase):
	"""The constructors of parallels and triggers reject parameters of the wrong type or value."""

	@testcase("Parallel")
	def ParallelChecks(self) -> None:
		"""
		A parallel has a count in range 1..200 or a matrix of mappings of strings, not both.

		Checks each exception.
		"""
		with self.assertRaises(ValueError) as context:
			Parallel(1)
		self.assertEqual("Parameters 'count' and 'matrix' are both given, or both None.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Parallel(1, 2, [{"A": ["1"]}])
		self.assertEqual("Parameters 'count' and 'matrix' are both given, or both None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Parallel(1, "3")
		self.assertEqual("Parameter 'count' is not of type 'int'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Parallel(1, 201)
		self.assertEqual("Parameter 'count' is out of range 1..200.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Parallel(1, matrix=["A"])
		self.assertEqual("An entry of parameter 'matrix' is not a mapping.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Parallel(1, matrix=[{"A": [1]}])
		self.assertEqual("Variable 'A' of parameter 'matrix' has values not of type 'str'.", str(context.exception))

	@testcase("Trigger")
	def TriggerChecks(self) -> None:
		"""
		A trigger's project and branch are strings, its strategy a TriggerStrategy, its includes Includes.

		Checks each TypeError, and those of the job and the need.
		"""
		with self.assertRaises(TypeError) as context:
			Trigger(1, 1)
		self.assertEqual("Parameter 'project' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Trigger(1, strategy="mirror")
		self.assertEqual("Parameter 'strategy' is not of type 'TriggerStrategy'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Trigger(1, includes=["/ci/a.yml"])
		self.assertEqual("An element of parameter 'includes' is not of type 'Include'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, trigger="group/other")
		self.assertEqual("Parameter 'trigger' is not of type 'Trigger'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, parallel=3)
		self.assertEqual("Parameter 'parallel' is not of type 'Parallel'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Need("a", 1, parallel=3)
		self.assertEqual("Parameter 'parallel' is not of type 'Parallel'.", str(context.exception))


@testsuite("Malformed parallel and trigger")
class ParallelErrors(Fixture):
	"""A malformed 'parallel' or 'trigger' raises PipelineFileError, naming file and line."""

	@testcase("Malformed parallel")
	def MalformedParallel(self) -> None:
		"""
		'parallel' is a count in range 1..200 or a matrix of mappings; a need's 'parallel' a matrix.

		Checks message and line of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  parallel: 300\n"))
		self.assertEqual("Key 'parallel' of job 'test' is out of range 1..200.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  parallel: many\n"))
		self.assertEqual(
			"Key 'parallel' of job 'test' is neither a count nor a mapping with 'matrix'.", str(context.exception)
		)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  parallel:\n    matrix: [A]\n"))
		self.assertEqual("Key 'parallel.matrix' of job 'test' is not a list of mappings.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("test:\n  parallel:\n    matrix:\n      - A: [[1]]\n"))
		self.assertEqual(
			"Variable 'A' of the matrix of job 'test' is neither a value nor a list of values.", str(context.exception)
		)
		self.assertEqual(4, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("b:\n  script: x\nt:\n  needs:\n    - job: b\n      parallel: 2\n"))
		self.assertEqual("Key 'parallel' of a need of job 't' has no 'matrix' key.", str(context.exception))
		self.assertEqual(5, context.exception.Line)

	@testcase("Malformed trigger")
	def MalformedTrigger(self) -> None:
		"""
		'trigger' is a project or a mapping with 'include' or 'project', whose strategy GitLab knows.

		Checks message, line and note of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("t:\n  trigger:\n    branch: main\n"))
		self.assertEqual(
			"Key 'trigger' of job 't' is neither a project nor a mapping with 'include' or 'project'.", str(context.exception)
		)
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("t:\n  trigger:\n    project: g/p\n    strategy: wait\n"))
		self.assertEqual("Key 'strategy' of the trigger of job 't' is not a known value.", str(context.exception))
		self.assertEqual(4, context.exception.Line)
		self.assertIn("Allowed values: depend, mirror.", context.exception.__notes__)


@testsuite("Inputs")
class Inputs(Fixture):
	"""Reading the header's 'spec:inputs' and the inputs of jobs, and constructing inputs."""

	@testcase("Inputs of the header")
	def Header(self) -> None:
		"""
		The header's inputs have a type, a default of that type, and are required without one.

		Checks the inputs of the fixture.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Inputs.yml")
		inputs = pipelineFile.Inputs

		self.assertEqual("Lints a Python package.", pipelineFile.Description)
		self.assertEqual(["stage", "python", "strict", "retries", "paths", "version", "environment"], list(inputs))
		self.assertEqual(4, inputs["stage"].Line)
		self.assertIs(pipelineFile, inputs["stage"].Parent)
		self.assertEqual("stage", str(inputs["stage"]))

		self.assertIs(InputType.String, inputs["stage"].Type)
		self.assertEqual("test", inputs["stage"].Default)
		self.assertEqual("Stage of the job.", inputs["stage"].Description)
		self.assertIs(False, inputs["stage"].Required)

		self.assertEqual(("3.13", "3.14"), inputs["python"].Options)
		self.assertIs(InputType.Boolean, inputs["strict"].Type)
		self.assertIs(False, inputs["strict"].Default)
		self.assertIs(InputType.Number, inputs["retries"].Type)
		self.assertEqual(2, inputs["retries"].Default)
		self.assertIs(InputType.Array, inputs["paths"].Type)
		self.assertEqual(["src", "tests"], inputs["paths"].Default)

		self.assertEqual(r"^v\d+$", inputs["version"].Regex)
		self.assertIs(True, inputs["version"].Required)
		self.assertIs(True, inputs["environment"].Required)
		self.assertIsNone(inputs["environment"].Default)

	@testcase("Inputs of a job")
	def JobInputs(self) -> None:
		"""
		A job's inputs have a default, options and a description.

		Checks the input of job 'lint'.
		"""
		lint = PipelineFile.FromFile(DATA / "Inputs.yml").Jobs["lint"]
		level = lint.Inputs["level"]

		self.assertIs(lint, level.Parent)
		self.assertEqual("warning", level.Default)
		self.assertEqual(("warning", "error"), level.Options)
		self.assertEqual("Level reported.", level.Description)
		self.assertEqual("$[[ inputs.stage ]]", lint.Stage)

	@testcase("Rules of an input")
	def Rules(self) -> None:
		"""
		An input's rules are kept as written.

		Reads an input with two rules.
		"""
		path = self._Write(dedent("""\
			spec:
			  inputs:
			    size:
			      rules:
			        - if: $[[ inputs.env ]] == 'dev'
			          options: [small]
			          default: small
			        - options: [large]
			          default: large
			---
			job:
			  script: x
			"""))
		size = PipelineFile.FromFile(path).Inputs["size"]

		self.assertEqual(
			({"if": "$[[ inputs.env ]] == 'dev'", "options": ["small"], "default": "small"},
			{"options": ["large"], "default": "large"}),
			size.Rules
		)

	@testcase("Without header")
	def WithoutHeader(self) -> None:
		"""
		A file without header has no inputs and no description; a job without 'inputs' none.

		Checks fixture 'Jobs.yml'.
		"""
		pipelineFile = PipelineFile.FromFile(DATA / "Jobs.yml")

		self.assertEqual({}, pipelineFile.Inputs)
		self.assertIsNone(pipelineFile.Description)
		self.assertEqual({}, pipelineFile.Jobs["build"].Inputs)

	@testcase("Constructed")
	def Constructed(self) -> None:
		"""
		An input constructed with a file or job as parent is attached to it, and so is one passed to them.

		Constructs inputs both ways.
		"""
		pipelineFile = PipelineFile(Path(".gitlab-ci.yml"), description="A component.")
		stage = Input("stage", 3, parent=pipelineFile)
		self.assertIs(stage, pipelineFile.Inputs["stage"])
		self.assertEqual("A component.", pipelineFile.Description)

		passed = Input("level", 7, InputType.String, False, "warning")
		job = Job("lint", 6, inputs=[passed])
		other = PipelineFile(Path("other.yml"), inputs=[Input("a", 2)], jobs=[job])
		self.assertIs(job, passed.Parent)
		self.assertIs(other, passed.PipelineFile)
		self.assertEqual(["a"], list(other.Inputs))


@testsuite("Parameter checks of inputs")
class InputParameters(Testcase):
	"""The input's constructor rejects parameters of the wrong type or value."""

	@testcase("Input")
	def InputChecks(self) -> None:
		"""
		An input's name is a non-empty string, its type an InputType, 'required' a boolean, its texts strings.

		Checks each exception, and those of the file and the job.
		"""
		with self.assertRaises(ValueError) as context:
			Input(None, 1)
		self.assertEqual("Parameter 'name' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Input(1, 1)
		self.assertEqual("Parameter 'name' is not of type 'str'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			Input("", 1)
		self.assertEqual("Parameter 'name' is empty.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Input("a", 1, "string")
		self.assertEqual("Parameter 'inputType' is not of type 'InputType'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Input("a", 1, required="yes")
		self.assertEqual("Parameter 'required' is not of type 'bool'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Input("a", 1, regex=1)
		self.assertEqual("Parameter 'regex' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), inputs=["a"])
		self.assertEqual("An element of parameter 'inputs' is not of type 'Input'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			PipelineFile(Path(".gitlab-ci.yml"), description=1)
		self.assertEqual("Parameter 'description' is not of type 'str'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			Job("a", 1, inputs=["a"])
		self.assertEqual("An element of parameter 'inputs' is not of type 'Input'.", str(context.exception))


@testsuite("Malformed inputs")
class InputErrors(Fixture):
	"""A malformed 'spec' or input raises PipelineFileError, naming file and line."""

	@testcase("Malformed spec")
	def MalformedSpec(self) -> None:
		"""
		'spec' and 'spec:inputs' are mappings, an input empty or a mapping of known keys.

		Checks message, line and note of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec: [a]\n---\njob:\n  script: x\n"))
		self.assertEqual("Key 'spec' of the header is not a mapping.", str(context.exception))
		self.assertEqual(1, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec:\n  inputs: [a]\n---\njob:\n  script: x\n"))
		self.assertEqual("Key 'spec:inputs' is not a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec:\n  inputs:\n    a: [b]\n---\njob:\n  script: x\n"))
		self.assertEqual("Input 'a' is not a mapping.", str(context.exception))
		self.assertEqual(3, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec:\n  inputs:\n    a:\n      value: b\n---\njob:\n  script: x\n"))
		self.assertEqual("Input 'a' has unknown key 'value'.", str(context.exception))
		self.assertEqual(4, context.exception.Line)
		self.assertIn("Allowed keys: default, type, description, options, regex, rules.", context.exception.__notes__)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("spec:\n  inputs:\n    a:\n      type: text\n---\njob:\n  script: x\n"))
		self.assertEqual("Key 'type' of input 'a' is not an input type.", str(context.exception))
		self.assertIn("Allowed values: string, number, boolean, array.", context.exception.__notes__)

	def _Input(self, declaration: str) -> Path:
		"""
		Write a configuration file, whose header declares input 'a'.

		:param declaration: The keys of input 'a', each line indented by six spaces.
		:returns:           Path to the file.
		"""
		return self._Write(f"spec:\n  inputs:\n    a:\n{declaration}---\njob:\n  script: x\n")

	@testcase("Defaults, options and regex")
	def Defaults(self) -> None:
		"""
		A default matches the type and the options; a regex needs type 'string'; options and rules are lists.

		Checks message and note of each error.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      type: number\n      default: two\n"))
		self.assertEqual("Default of input 'a' is not of type 'number'.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      type: boolean\n      default: 1\n"))
		self.assertEqual("Default of input 'a' is not of type 'boolean'.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      type: number\n      default: true\n"))
		self.assertEqual("Default of input 'a' is not of type 'number'.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      options: [x, y]\n      default: z\n"))
		self.assertEqual("Default of input 'a' is not one of its options.", str(context.exception))
		self.assertIn("Options: x, y.", context.exception.__notes__)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      type: number\n      regex: \\\\d\n"))
		self.assertEqual("Key 'regex' of input 'a' needs type 'string'.", str(context.exception))

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Input("      options: x\n"))
		self.assertEqual("Key 'options' of input 'a' is not a list.", str(context.exception))

	@testcase("Malformed inputs of a job")
	def MalformedJobInputs(self) -> None:
		"""
		A job's 'inputs' is a mapping, and each input has a default.

		Checks message and line of both errors.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("j:\n  inputs: [a]\n"))
		self.assertEqual("Key 'inputs' of job 'j' is not a mapping.", str(context.exception))
		self.assertEqual(2, context.exception.Line)

		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(self._Write("j:\n  inputs:\n    level:\n      options: [a]\n"))
		self.assertEqual("Input 'level' of job 'j' has no default.", str(context.exception))
		self.assertEqual(3, context.exception.Line)


REPOSITORY = DATA / "Repository"
"""Directory of a repository, whose configuration starts a child pipeline of its own files."""


@testsuite("Pipeline built from a file")
class ToPipeline(Fixture):
	"""Building the pyTooling.CI pipeline a configuration file defines."""

	@testcase("Elements")
	def Elements(self) -> None:
		"""
		A job becomes a job, a job with 'parallel' a matrix of instances, a trigger job a workflow; hidden jobs none.

		Checks the elements built from the repository's configuration.
		"""
		pipelineFile = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml")
		pipeline = pipelineFile.ToPipeline()

		self.assertIsInstance(pipeline, DefinedPipeline)
		self.assertEqual(".gitlab-ci.yml", pipeline.Name)
		self.assertIs(pipelineFile, pipeline.Definition)
		self.assertEqual(["build", "lint", "docs"], [job.Name for job in pipeline.Jobs])
		for job in pipeline.Jobs:
			self.assertIsInstance(job, DefinedJob)
			self.assertIs(pipelineFile.Jobs[job.Name], job.Definition)

		matrix = pipeline.Matrices["test"]
		self.assertIsInstance(matrix, DefinedMatrix)
		self.assertEqual([{"PYTHON": "3.13"}, {"PYTHON": "3.14"}], [instance.Dimensions for instance in matrix.Instances])
		for instance in matrix.Instances:
			self.assertIsInstance(instance, DefinedMatrixJob)
		self.assertEqual(["test: [3.13]", "test: [3.14]"], [str(instance) for instance in matrix.Instances])
		self.assertIs(matrix.Instances[1], matrix.GetElement("test: [3.14]"))

		self.assertEqual(["deploy", "downstream"], list(pipeline.Workflows))
		self.assertEqual("local: /ci/child.yml", pipeline.Workflows["deploy"].Reference)
		self.assertEqual((), pipeline.Workflows["deploy"].ChildFiles)
		self.assertEqual("group/other", pipeline.Workflows["downstream"].Reference)
		self.assertIsInstance(pipeline.Workflows["deploy"], DefinedWorkflow)

	@testcase("Name of the pipeline")
	def Name(self) -> None:
		"""
		A pipeline is named by 'workflow:name', or else by the file's name.

		Builds the pipelines of a file with a workflow's name and of the repository's configuration.
		"""
		named = PipelineFile.FromFile(self._Write("workflow:\n  name: Nightly\nbuild:\n  script: make\n"))
		self.assertEqual("Nightly", named.ToPipeline().Name)

		self.assertEqual(".gitlab-ci.yml", PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline().Name)

	@testcase("Rules")
	def Rules(self) -> None:
		"""
		A job's rules are the element's rules; a job with neither rules nor 'when' has none.

		Checks jobs 'docs' and 'build'.
		"""
		pipeline = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline()

		docs = pipeline.GetElement("docs")
		self.assertEqual(1, docs.RuleCount)
		self.assertEqual('$CI_COMMIT_BRANCH == "main"', docs.Rules[0].Condition)
		self.assertIs(RuleOutcome.OnSuccess, docs.Rules[0].When)
		self.assertIs(docs, docs.Rules[0].Parent)

		self.assertEqual(0, pipeline.GetElement("build").RuleCount)

	@testcase("Rules: when and key-value-pairs")
	def RulesWhen(self) -> None:
		"""
		A rule decides its own 'when', else the job's, else on_success; a job's 'when' without rules is a rule.

		Checks the rules of the workflow, of a job with 'when' only, of a job with rules and of a matrix' instances.
		"""
		pipelineFile = PipelineFile.FromFile(self._Write(dedent("""\
			workflow:
			  rules:
			    - if: $CI_COMMIT_TAG
			      when: never
			    - if: $CI_PIPELINE_SOURCE == "push"
			build:
			  script: make
			  when: manual
			test:
			  script: pytest
			  when: manual
			  rules:
			    - if: $A
			      changes:
			        paths: [src/**]
			        compare_to: main
			      allow_failure: true
			      variables:
			        X: "1"
			    - exists: [setup.py]
			      when: never
			    - when: on_success
			matrix:
			  script: pytest
			  parallel: 2
			  rules:
			    - if: $B
			""")))
		pipeline = pipelineFile.ToPipeline()

		self.assertEqual(2, pipeline.RuleCount)
		self.assertEqual("$CI_COMMIT_TAG", pipeline.Rules[0].Condition)
		self.assertIs(RuleOutcome.Never, pipeline.Rules[0].When)
		self.assertIs(RuleOutcome.Always, pipeline.Rules[1].When)

		build = pipeline.GetElement("build")
		self.assertEqual(1, build.RuleCount)
		self.assertIsNone(build.Rules[0].Condition)
		self.assertIs(RuleOutcome.Manual, build.Rules[0].When)

		first, second, third = pipeline.GetElement("test").Rules
		self.assertEqual("$A", first.Condition)
		self.assertIs(RuleOutcome.Manual, first.When)
		self.assertEqual(("src/**", ), first["changes"])
		self.assertEqual("main", first["compare_to"])
		self.assertIs(True, first["allow_failure"])
		self.assertEqual({"X": "1"}, first["variables"])
		self.assertIsNone(second.Condition)
		self.assertIs(RuleOutcome.Never, second.When)
		self.assertEqual(("setup.py", ), second["exists"])
		self.assertNotIn("changes", second)
		self.assertIs(RuleOutcome.OnSuccess, third.When)

		matrix = pipeline.Matrices["matrix"]
		self.assertEqual("$B", matrix.Rules[0].Condition)
		self.assertIsNot(matrix.Instances[0].Rules[0], matrix.Instances[1].Rules[0])
		self.assertIs(matrix.Instances[1], matrix.Instances[1].Rules[0].Parent)

	@testcase("Needs")
	def Needs(self) -> None:
		"""
		A job without 'needs' needs the elements of the nearest earlier stage holding some; 'needs' replaces that.

		Checks the needs of every element.
		"""
		pipeline = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline()

		def needs(name: str) -> list[str]:
			"""
			Nested function returning the names of the elements an element needs.

			:param name: Name of the element.
			:returns:    The needed elements' names.
			"""
			return [element.Name for element in pipeline.GetElement(name).Needs]

		self.assertEqual([], needs("build"))
		self.assertEqual([], needs("lint"))
		self.assertEqual(["build", "lint"], needs("test"))
		self.assertEqual(["build"], needs("docs"))
		self.assertEqual(["test", "docs"], needs("deploy"))
		self.assertEqual([], needs("downstream"))

	@testcase("Child pipeline expanded")
	def ChildPipeline(self) -> None:
		"""
		With a resolver, a trigger job's workflow holds the child pipeline's elements, unless the depth is used up.

		Builds the pipeline with a resolver, and with depth 0.
		"""
		resolver = IncludeResolver(REPOSITORY)
		pipeline = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline(resolver)
		deploy = pipeline.Workflows["deploy"]

		self.assertEqual(1, len(deploy.ChildFiles))
		self.assertEqual("child.yml", deploy.ChildFiles[0].Path.name)
		self.assertEqual(["first"], [job.Name for job in deploy.Jobs])
		second = deploy.Matrices["second"]
		self.assertEqual([{"CI_NODE_INDEX": "1"}, {"CI_NODE_INDEX": "2"}], [i.Dimensions for i in second.Instances])
		self.assertEqual(["second 1/2", "second 2/2"], [str(instance) for instance in second.Instances])
		self.assertEqual(["first"], [element.Name for element in second.Needs])

		shallow = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline(resolver, 0)
		self.assertEqual([], shallow.Workflows["deploy"].Jobs)

	@testcase("Graph")
	def Graph(self) -> None:
		"""
		The pipeline converts into a graph.

		Checks the graph has a vertex per job of the configuration, hidden jobs aside.
		"""
		graph = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml").ToPipeline().ToGraph()

		vertices = sorted(str(vertex.ID) for vertex in graph.IterateVertices())
		self.assertEqual(["build", "deploy", "docs", "downstream", "lint", "test"], vertices)

	@testcase("Child pipeline running itself")
	def RunsItself(self) -> None:
		"""
		A child pipeline running a file expanded above it is an error.

		Checks the message and the note.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(REPOSITORY / "ci" / "self.yml").ToPipeline(IncludeResolver(REPOSITORY))
		self.assertEqual("Child pipeline 'self.yml' runs itself.", str(context.exception))
		self.assertIn("Runs: self.yml -> self.yml.", context.exception.__notes__)

	@testcase("Parameter checks")
	def Parameters(self) -> None:
		"""
		The resolver is an IncludeResolver, the depth a non-negative integer.

		Checks each exception.
		"""
		pipelineFile = PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml")

		with self.assertRaises(TypeError) as context:
			pipelineFile.ToPipeline(REPOSITORY)
		self.assertEqual("Parameter 'resolver' is not of type 'IncludeResolver'.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			pipelineFile.ToPipeline(depth="1")
		self.assertEqual("Parameter 'depth' is not of type 'int'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			pipelineFile.ToPipeline(depth=-1)
		self.assertEqual("Parameter 'depth' is negative.", str(context.exception))


@testsuite("Include resolver")
class Resolver(Fixture):
	"""Reading local includes from a repository's directory."""

	@testcase("Local files")
	def LocalFiles(self) -> None:
		"""
		A local include is read once, with or without a leading slash; a missing file or another kind isn't read.

		Resolves includes of every outcome.
		"""
		resolver = IncludeResolver(REPOSITORY)

		self.assertEqual(REPOSITORY, resolver.Root)
		child = resolver.Resolve(Include(IncludeKind.Local, "/ci/child.yml", 1))
		self.assertEqual("child.yml", child.Path.name)
		self.assertIs(child, resolver.Resolve(Include(IncludeKind.Local, "ci/child.yml", 2)))
		self.assertIsNone(resolver.Resolve(Include(IncludeKind.Local, "/ci/missing.yml", 3)))
		self.assertIsNone(resolver.Resolve(Include(IncludeKind.Template, "Auto-DevOps.gitlab-ci.yml", 4)))

	@testcase("Parameter checks")
	def Parameters(self) -> None:
		"""
		A resolver needs a root of type Path; Resolve an Include.

		Checks each exception.
		"""
		with self.assertRaises(ValueError) as context:
			IncludeResolver(None)
		self.assertEqual("Parameter 'root' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			IncludeResolver(".")
		self.assertEqual("Parameter 'root' is not of type 'Path'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			IncludeResolver(REPOSITORY).Resolve(None)
		self.assertEqual("Parameter 'include' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			IncludeResolver(REPOSITORY).Resolve("/ci/child.yml")
		self.assertEqual("Parameter 'include' is not of type 'Include'.", str(context.exception))


@testsuite("Defined elements")
class DefinedElements(Testcase):
	"""The elements built from a file check their definition."""

	@testcase("Definitions")
	def Definitions(self) -> None:
		"""
		An element is built from a job of the kind it stands for.

		Checks each exception.
		"""
		with self.assertRaises(ValueError) as context:
			DefinedJob(None)
		self.assertEqual("Parameter 'definition' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			DefinedJob("build")
		self.assertEqual("Parameter 'definition' is not of type 'Job'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			DefinedWorkflow(Job("build", 1))
		self.assertEqual("Parameter 'definition' starts no pipeline.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			DefinedMatrix(Job("build", 1))
		self.assertEqual("Parameter 'definition' has no 'parallel'.", str(context.exception))

		with self.assertRaises(ValueError) as context:
			DefinedMatrixJob(Job("build", 1), None)
		self.assertEqual("Parameter 'dimensions' is None.", str(context.exception))

		with self.assertRaises(TypeError) as context:
			DefinedWorkflow(Job("deploy", 1, trigger=Trigger(2, "group/other")), childFiles=["child.yml"])
		self.assertEqual("An element of parameter 'childFiles' is not of type 'PipelineFile'.", str(context.exception))


@testsuite("Included files")
class IncludedFiles(Fixture):
	"""Extending jobs of, and referring to keys of, the local files a file includes."""

	@testcase("Resolved with a resolver")
	def Resolved(self) -> None:
		"""
		With a resolver, a job extends and refers to jobs of the included local files, also of nested includes.

		Checks jobs 'job' and 'deep'.
		"""
		pipelineFile = PipelineFile.FromFile(REPOSITORY / "ci" / "uses-templates.yml", IncludeResolver(REPOSITORY))
		job = pipelineFile.Jobs["job"]

		self.assertEqual((), job.Unresolved)
		self.assertEqual("test", job.Stage)
		self.assertEqual("templates", job.Variables["FROM"].Value)
		self.assertEqual(("echo setup", "echo job"), job.Script)
		self.assertEqual(("deep", ), pipelineFile.Jobs["deep"].Tags)
		self.assertEqual(["job", "deep", "other"], list(pipelineFile.Jobs))

	@testcase("Lines of included keys")
	def Lines(self) -> None:
		"""
		A key an included file contributes gets the line of the 'extends' key bringing it in.

		Checks the line of variable 'FROM' of job 'job'.
		"""
		pipelineFile = PipelineFile.FromFile(REPOSITORY / "ci" / "uses-templates.yml", IncludeResolver(REPOSITORY))

		self.assertEqual(7, pipelineFile.Jobs["job"].Variables["FROM"].Line)

	@testcase("What can't be read")
	def Unread(self) -> None:
		"""
		A job extending a job of an include that can't be read - a template - lists it; without a resolver, every one.

		Checks job 'other', and job 'job' without a resolver.
		"""
		resolved = PipelineFile.FromFile(REPOSITORY / "ci" / "uses-templates.yml", IncludeResolver(REPOSITORY))
		self.assertEqual(("extends .remote", ), resolved.Jobs["other"].Unresolved)

		unresolved = PipelineFile.FromFile(REPOSITORY / "ci" / "uses-templates.yml")
		self.assertEqual(("!reference [.setup, script]", "extends .base"), unresolved.Jobs["job"].Unresolved)

	@testcase("Every include read")
	def EveryIncludeRead(self) -> None:
		"""
		If every include was read, a job extending a job no file has is an error; without a resolver, it is listed.

		Checks the error, and the job read without a resolver.
		"""
		with self.assertRaises(PipelineFileError) as context:
			PipelineFile.FromFile(REPOSITORY / "ci" / "complete.yml", IncludeResolver(REPOSITORY))
		self.assertEqual("Job 'job' extends job '.missing', which the file doesn't have.", str(context.exception))

		job = PipelineFile.FromFile(REPOSITORY / "ci" / "complete.yml").Jobs["job"]
		self.assertEqual(("extends .missing", ), job.Unresolved)

	@testcase("Parameter check")
	def Parameter(self) -> None:
		"""
		The resolver of FromFile is an IncludeResolver.

		Checks the TypeError.
		"""
		with self.assertRaises(TypeError) as context:
			PipelineFile.FromFile(REPOSITORY / ".gitlab-ci.yml", REPOSITORY)
		self.assertEqual("Parameter 'resolver' is not of type 'IncludeResolver'.", str(context.exception))

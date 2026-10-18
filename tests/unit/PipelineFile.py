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
Unit tests for :mod:`pyTooling.GitLab.PipelineFile`: the configuration file, its stages and variables.
"""
from pathlib                       import Path
from tempfile                      import TemporaryDirectory
from textwrap                      import dedent

from pyTooling.GitLab.PipelineFile import DEFAULT_STAGES, PipelineFile, PipelineFileError, Variable
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
		A variable's parent is a configuration file, and can't be reset to None.

		Checks the TypeErrors and the ValueError.
		"""
		with self.assertRaises(TypeError) as context:
			Variable("A", 1, parent=Variable("B", 1))
		self.assertEqual("Parameter 'parent' is not of type 'PipelineFile'.", str(context.exception))

		variable = Variable("A", 1)
		with self.assertRaises(TypeError) as context:
			variable.Parent = Variable("B", 1)
		self.assertEqual("Parameter 'value' is not of type 'PipelineFile'.", str(context.exception))

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

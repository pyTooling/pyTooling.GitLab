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
Unit tests for :mod:`pyTooling.GitLab.Sphinx.Reference`: the directives summarizing a pipeline file.

Every testcase builds a small Sphinx project in a temporary directory, as :mod:`tests.unit.Sphinx.Domain` does.
"""
from textwrap               import dedent

from pyTooling.Testing      import testsuite, testcase

from tests.unit.Sphinx.Domain import PAGE, PARAMETERS, PIPELINE, Project


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


SIMPLE_PAGE = ".. glci:pipeline:: Simple\n\nSimple\n######\n"
"""A page documenting the pipeline 'Simple'."""


@testsuite("Parameter tables")
class ParameterTables(Project):
	"""The directive 'glci:parameter-table'."""

	@testcase("Inputs")
	def Inputs(self) -> None:
		"""
		The inputs' table lists every input in file order, linked to its entry, with required, type and default.

		Builds a page with the table of the inputs and the entries.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Build({"Package": PAGE + "\n.. glci:parameter-table::\n   :kinds: inputs\n\n" + PARAMETERS})

		self.assertEqual([], self._WarningLines())
		html = self._HTML("Package")
		table = html[html.index('class="glci-parameter-table glci-inputs'):]
		table = table[:table.index("</table>")]
		self.assertEqual(
			["package_name", "python_version", "dry_run", "pages_on", "level", "tag"],
			[part.split("<")[0] for part in table.split('<span class="pre">')[1:] if not part.startswith(("'", "false"))]
		)
		self.assertIn('href="#glci-input-Package.package_name"', table)
		self.assertIn("<td><p>yes</p></td>", table)
		self.assertIn("<td><p>boolean</p></td>", table)
		self.assertIn("<span class=\"pre\">'default-branch…'</span>", table)

	@testcase("Variables")
	def Variables(self) -> None:
		"""
		The variables' table lists every default variable with its value and description.

		Builds a page with the table of the variables.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Build({"Package": PAGE + "\n.. glci:parameter-table::\n   :kinds: variables\n\n" + PARAMETERS})

		html = self._HTML("Package")
		table = html[html.index('class="glci-parameter-table glci-variables'):]
		table = table[:table.index("</table>")]
		self.assertIn('href="#glci-variable-Package.DEPLOY_ENV"', table)
		self.assertIn("<span class=\"pre\">'staging'</span>", table)
		self.assertIn("<td><p>Where to deploy.</p></td>", table)

	@testcase("Every kind")
	def EveryKind(self) -> None:
		"""
		Without ':kinds:', a table per kind the file has parameters of, in the order of 'KINDS'.

		Builds a page with the tables of a file with inputs and variables, and of one with variables only.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Pipeline("Simple")
		self._Build({
			"Package": PAGE + "\n.. glci:parameter-table::\n\n" + PARAMETERS,
			"Simple":  SIMPLE_PAGE + "\n.. glci:parameter-table::\n"
		})

		html = self._HTML("Package")
		self.assertLess(html.index("glci-inputs"), html.index("glci-variables"))
		simple = self._HTML("Simple")
		self.assertNotIn("glci-inputs", simple)
		self.assertIn("glci-variables", simple)

	@testcase("Kind without parameters")
	def KindWithoutParameters(self) -> None:
		"""
		A kind named explicitly, of which the file has none, is a table saying so.

		Builds the inputs' table of a file without inputs.
		"""
		self._Pipeline("Simple")
		self._Build({"Simple": SIMPLE_PAGE + "\n.. glci:parameter-table::\n   :kinds: inputs\n"})

		self.assertIn("<em>No inputs</em>", self._HTML("Simple"))

	@testcase("Unknown kind")
	def UnknownKind(self) -> None:
		"""
		An unknown kind is an error.

		Builds a table of kind 'secrets'.
		"""
		self._Pipeline("Simple")
		self._Build({"Simple": SIMPLE_PAGE + "\n.. glci:parameter-table::\n   :kinds: secrets\n"})

		self.assertTrue(any(
			"glci:parameter-table::kinds: 'secrets' is not one of inputs, variables." in line for line in self._WarningLines()
		))

	@testcase("No pipeline")
	def NoPipeline(self) -> None:
		"""
		A summary without a preceding 'glci:pipeline' is a warning.

		Builds a page with only a table.
		"""
		self._Build({"Package": "Package\n#######\n\n.. glci:parameter-table::\n"})

		self.assertEqual(
			["src/Package.rst:4: WARNING: glci:parameter-table is not preceded by a glci:pipeline. [glci.pipeline]"],
			self._WarningLines()
		)


@testsuite("Interfaces")
class Interfaces(Project):
	"""The directive 'glci:interface'."""

	INTERFACE = dedent("""\
		spec:
		  inputs:
		    stage:
		      default: test
		    image:
		      description: 'The image.'
		---
		variables:
		  LEVEL:
		    value: 'info'
		    description: 'Log level.'
		  PLAIN: 'x'

		stages: [build, test, deploy]

		.template:
		  script: [make]

		Build:
		  stage: build
		  script: [make]

		Test:
		  extends: .template
		  stage: $[[ inputs.stage ]]
	""")
	"""A pipeline file, whose interface has an entry of every field."""

	@testcase("Fields")
	def Fields(self) -> None:
		"""
		The interface names the required inputs, the described variables, the stages used - one given by an input as
		written -, the jobs and the hidden jobs.

		Builds the interface of a file with every kind of entry.
		"""
		self._Pipeline("Template", self.INTERFACE)
		page = ".. glci:pipeline:: Template\n\nTemplate\n########\n\n.. glci:interface::\n\n.. glci:autoinputs::\n"
		self._Build({"Template": page})

		self.assertEqual([], self._WarningLines())
		html = self._HTML("Template")
		interface = html[html.index('class="glci-interface'):]
		interface = interface[:interface.index("</dl>")]
		fields = [part.split("<")[0].split(">")[1] for part in interface.split('<dt class="field-')[1:]]
		self.assertEqual(["Required Inputs", "Variables", "Stages", "Jobs", "Hidden Jobs"], fields)
		self.assertIn('href="#glci-input-Template.image"', interface)
		self.assertNotIn('href="#glci-input-Template.stage"', interface)
		self.assertIn('<span class="pre">LEVEL</span>', interface)
		self.assertNotIn("PLAIN", interface)
		self.assertIn('<span class="pre">build</span>', interface)
		self.assertIn('<span class="pre">inputs.stage</span>', interface)
		self.assertIn('<span class="pre">.template</span>', interface)

	@testcase("Nothing to state")
	def Nothing(self) -> None:
		"""
		A field without entries says *none*.

		Builds the interface of a file without inputs and hidden jobs.
		"""
		self._Pipeline("Simple")
		self._Build({"Simple": SIMPLE_PAGE + "\n.. glci:interface::\n"})

		html = self._HTML("Simple")
		self.assertEqual(3, html[html.index('class="glci-interface'):].count("<em>none</em>"))


@testsuite("Automatic input entries")
class AutoInputs(Project):
	"""The directive 'glci:autoinputs'."""

	@testcase("Entries")
	def Entries(self) -> None:
		"""
		Every input without a 'glci:input' in the document gets an entry, also those documented later are left out.

		Builds a page with one hand-written entry before and one after the automatic ones.
		"""
		self._Pipeline("Package", PIPELINE)
		page = PAGE + dedent("""\

			.. glci:input:: package_name

			.. glci:autoinputs::

			.. glci:input:: tag

			   :Example: ``v2``
		""")
		app = self._Build({"Package": page})

		self.assertEqual([], self._WarningLines())
		objects = app.env.get_domain("glci").Objects
		for name in ("package_name", "python_version", "dry_run", "pages_on", "level", "tag"):
			self.assertIn(("input", f"Package.{name}"), objects)

		html = self._HTML("Package")
		self.assertEqual(1, html.count('id="glci-input-Package.tag"'))
		self.assertIn('id="pipeline-package-input-python-version"', html)
		self.assertIn("<p>Python version.</p>", html)

	@testcase("No pipeline")
	def NoPipeline(self) -> None:
		"""
		Without a preceding 'glci:pipeline', it is a warning and creates nothing.

		Builds a page with only the directive.
		"""
		self._Build({"Package": "Package\n#######\n\n.. glci:autoinputs::\n"})

		self.assertEqual(
			["src/Package.rst:4: WARNING: glci:autoinputs is not preceded by a glci:pipeline. [glci.pipeline]"],
			self._WarningLines()
		)


@testsuite("Undocumented inputs")
class Drift(Project):
	"""The warning about inputs without an entry."""

	@testcase("Undocumented input")
	def Undocumented(self) -> None:
		"""
		An input without an entry in the document is a warning at the 'glci:pipeline'.

		Builds a page documenting every input but 'tag'.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Build({"Package": PAGE + PARAMETERS.replace(".. glci:input:: tag\n", "")})

		self.assertEqual(
			[
				"src/Package.rst:1: WARNING: Input 'tag' of pipeline 'Package' has no entry: add a glci:input or a "
				"glci:autoinputs. [glci.drift]"
			],
			self._WarningLines()
		)

	@testcase("Entry in another document")
	def OtherDocument(self) -> None:
		"""
		An entry in another document doesn't count.

		Builds two pages of the pipeline, one with the entries, one without.
		"""
		self._Pipeline("Package", PIPELINE)
		other = ".. glci:pipeline:: Package\n   :file: ../pipelines/Package.yml\n\nOther\n#####\n"
		self._Build({"Package": PAGE + PARAMETERS, "Other": other})

		drift = [line for line in self._WarningLines() if line.endswith("[glci.drift]")]
		self.assertEqual(6, len(drift))
		self.assertTrue(all(line.startswith("src/Other.rst:1: ") for line in drift))

	@testcase("Suppressed")
	def Suppressed(self) -> None:
		"""
		'suppress_warnings' silences the drift warnings.

		Builds a page without entries, suppressing 'glci.drift'.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Build({"Package": PAGE}, suppress_warnings=["glci.drift"])

		self.assertEqual([], self._WarningLines())


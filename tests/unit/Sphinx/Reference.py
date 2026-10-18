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


@testsuite("Dependency lists")
class DependencyLists(Project):
	"""The directive 'glci:dependencies'."""

	DEPENDENCIES = dedent("""\
		include:
		  - local: /ci/build.yml
		  - project: group/shared
		    ref: v1
		    file: [/templates/a.yml]
		  - remote: 'https://example.com/ci.yml'
		  - template: Auto-DevOps.gitlab-ci.yml
		  - component: $CI_SERVER_FQDN/group/components/lint@1.0

		default:
		  image: python:3.14

		Child:
		  trigger:
		    include: /ci/child.yml

		Downstream:
		  trigger:
		    project: group/other

		Test:
		  image: alpine
		  services: [postgres:16]
		  script: [make]
	""")
	"""A pipeline file using every kind of dependency."""

	PAGE = ".. glci:pipeline:: Uses\n\nUses\n####\n\n.. glci:dependencies::\n"
	"""A page listing the dependencies of the pipeline 'Uses'."""

	def setUp(self) -> None:
		super().setUp()
		(self._path / "pipelines" / "ci").mkdir()
		build = self._path / "pipelines" / "ci" / "build.yml"
		build.write_text("Build:\n  image: gcc\n  script: [make]\n", encoding="utf-8")
		(self._path / "pipelines" / "ci" / "child.yml").write_text("Job:\n  script: [make]\n", encoding="utf-8")

	@testcase("Derived")
	def Derived(self) -> None:
		"""
		The includes, the triggered pipelines and the images are listed; a local include with its own dependencies.

		Builds the list of a file using every kind of dependency.
		"""
		self._Pipeline("Uses", self.DEPENDENCIES)
		self._Build({"Uses": self.PAGE}, glci_repository_root="../pipelines")

		self.assertEqual([], self._WarningLines())
		html = self._HTML("Uses")
		dependencies = html[html.index('class="glci-dependencies'):]
		dependencies = dependencies[:dependencies.rindex("</ul>")]
		for text in (
			"/ci/build.yml", "group/shared", "/templates/a.yml", "https://example.com/ci.yml", "Auto-DevOps.gitlab-ci.yml",
			"$CI_SERVER_FQDN/group/components/lint&#64;1.0", "python:3.14", "alpine", "postgres:16", "group/other", "gcc"
		):
			with self.subTest(text=text):
				self.assertIn(text, dependencies)

		self.assertIn("<em>Child</em>", dependencies)
		self.assertIn("/ci/child.yml", dependencies)
		self.assertLess(dependencies.index("/ci/build.yml"), dependencies.index("gcc"))

	@testcase("Links")
	def Links(self) -> None:
		"""
		A local include links to GitLab at the documented ref; another project, a URL and a component link too.

		Builds the list with project, ref and repository root configured.
		"""
		self._Pipeline("Uses", self.DEPENDENCIES)
		self._Build({"Uses": self.PAGE}, glci_repository_root="../pipelines", glci_ref="v2")

		html = self._HTML("Uses")
		self.assertIn('href="https://gitlab.com/group/project/-/blob/v2/ci/build.yml"', html)
		self.assertIn('href="https://gitlab.com/group/shared"', html)
		self.assertIn('href="https://example.com/ci.yml"', html)
		self.assertIn('href="https://gitlab.com/group/components"', html)

	@testcase("Merged")
	def Merged(self) -> None:
		"""
		A hand-written item named as a derived one adds its nested list to it; any other is appended.

		Builds the list with hand-written items for an include and an image, and a new one.
		"""
		self._Pipeline("Uses", self.DEPENDENCIES)
		page = self.PAGE + (
			"\n"
			"   * /ci/build.yml\n\n"
			"     * GCC's plugins\n\n"
			"   * alpine\n\n"
			"     * curl\n\n"
			"   * pip\n"
		)
		self._Build({"Uses": page}, glci_repository_root="../pipelines")

		self.assertEqual([], self._WarningLines())
		html = self._HTML("Uses")
		dependencies = html[html.index('class="glci-dependencies'):]
		build = dependencies[dependencies.index("/ci/build.yml"):dependencies.index("group/shared")]
		self.assertIn("GCC’s plugins", build)
		alpine = dependencies[dependencies.index("alpine"):dependencies.index("postgres:16")]
		self.assertIn("curl", alpine)
		self.assertLess(dependencies.index("postgres:16"), dependencies.index("<p>pip</p>"))

	@testcase("No dependencies")
	def Nothing(self) -> None:
		"""
		A file using nothing says *none*.

		Builds the list of a file without includes, triggers and images.
		"""
		self._Pipeline("Simple")
		self._Build({"Simple": SIMPLE_PAGE + "\n.. glci:dependencies::\n"})

		self.assertIn("<em>none</em>", self._HTML("Simple"))

	@testcase("Malformed include")
	def MalformedInclude(self) -> None:
		"""
		A local include that isn't a well-formed configuration is a warning; it is listed without its dependencies.

		Builds the list of a file including a malformed file.
		"""
		build = self._path / "pipelines" / "ci" / "build.yml"
		build.write_text("Build:\n  needs: [Missing]\n  script: [x]\n", encoding="utf-8")
		self._Pipeline("Uses", self.DEPENDENCIES)
		self._Build({"Uses": self.PAGE}, glci_repository_root="../pipelines")

		lines = self._WarningLines()
		self.assertEqual(1, len(lines))
		self.assertTrue(lines[0].startswith("src/Uses.rst:6: WARNING: glci:dependencies: "))
		self.assertIn("/ci/build.yml", self._HTML("Uses"))


@testsuite("YAML excerpts")
class YAMLExcerpts(Project):
	"""The directive 'glci:yaml'."""

	def _Excerpt(self, options: str = "", **config: object) -> str:
		"""
		Build the page 'Package' with a YAML excerpt and return the excerpt's HTML.

		:param options: Optional, the directive's options, one per line. Default: ``""``.
		:param config:  Configuration values overriding the defaults.
		:returns:       The HTML of the excerpt's container.
		"""
		self._Pipeline("Package", PIPELINE)
		self._Build({"Package": PAGE + PARAMETERS + "\n.. glci:yaml::\n" + options}, **config)

		html = self._HTML("Package")
		return html[html.index('class="literal-block-wrapper'):]

	@testcase("Inputs")
	def Inputs(self) -> None:
		"""
		Section 'inputs' shows the header's inputs, numbered as in the file.

		Builds the excerpt of the inputs.
		"""
		excerpt = self._Excerpt("   :section: inputs\n")

		self.assertEqual([], self._WarningLines())
		self.assertIn("Package.yml, lines 3-21", excerpt)
		self.assertIn("package_name", excerpt)
		self.assertNotIn("DEPLOY_ENV", excerpt[:excerpt.index("</pre>")])

	@testcase("Top-level key")
	def TopLevelKey(self) -> None:
		"""
		A top-level key is found behind the header document.

		Builds the excerpts of the variables and the stages.
		"""
		excerpt = self._Excerpt("   :section: variables\n")
		self.assertIn("Package.yml, lines 23-28", excerpt)

		excerpt = self._Excerpt("   :section: stages\n")
		self.assertIn("Package.yml, line", excerpt)
		self.assertIn("build", excerpt)

	@testcase("Job")
	def Job(self) -> None:
		"""
		Option ':job:' shows a job, shifted left.

		Builds the excerpt of the job 'Build'.
		"""
		excerpt = self._Excerpt("   :job: Build\n")

		self.assertIn("Package.yml, lines 32-35", excerpt)
		self.assertIn("Building", excerpt)

	@testcase("Whole file with link")
	def File(self) -> None:
		"""
		Without options, the whole file is shown; the caption links to GitLab when project, ref and root are configured.

		Builds the excerpt of the whole file with 'glci_ref' and 'glci_repository_root'.
		"""
		excerpt = self._Excerpt(glci_ref="v1", glci_repository_root="..")

		self.assertIn('href="https://gitlab.com/group/project/-/blob/v1/pipelines/Package.yml"', excerpt)

	@testcase("Unknown job and missing section")
	def Missing(self) -> None:
		"""
		A job or a section the file doesn't have is a warning.

		Builds excerpts of an unknown job and of the section 'include'.
		"""
		self._Pipeline("Package", PIPELINE)
		excerpts = "\n.. glci:yaml::\n   :job: Unknown\n\n.. glci:yaml::\n   :section: include\n"
		self._Build({"Package": PAGE + PARAMETERS + excerpts})

		lines = self._WarningLines()
		self.assertIn("glci:yaml: Pipeline 'Package' has no job 'Unknown'. [glci.drift]", lines[0])
		self.assertIn("glci:yaml: Pipeline 'Package' has no include. [glci.drift]", lines[1])

	@testcase("Wrong options")
	def WrongOptions(self) -> None:
		"""
		Options ':section:' and ':job:' together, and an unknown section, are errors.

		Builds both.
		"""
		self._Pipeline("Package", PIPELINE)
		excerpts = "\n.. glci:yaml::\n   :job: Build\n   :section: inputs\n\n.. glci:yaml::\n   :section: jobs\n"
		page = PAGE + PARAMETERS + excerpts
		self._Build({"Package": page})

		lines = self._WarningLines()
		self.assertTrue(any("Options ':section:' and ':job:' exclude each other." in line for line in lines))
		message = "'jobs' is not one of inputs, variables, stages, include, workflow, default."
		self.assertTrue(any(message in line for line in lines))

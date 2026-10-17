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
Unit tests for the Sphinx domain ``glci`` of :mod:`pyTooling.GitLab.Sphinx`.

Every testcase builds a small Sphinx project in a temporary directory and checks the HTML, the domain's data and the
warnings.
"""
from io                import StringIO
from os                import sep
from pathlib           import Path
from sys               import version_info
from tempfile          import TemporaryDirectory
from textwrap          import dedent
from typing            import Any
from warnings          import catch_warnings, filterwarnings

from pytest            import mark

from pyTooling.Testing import Testcase, testsuite, testcase

# 'pyTooling.Sphinx' requires Sphinx 9.1, which requires Python 3.12.
sphinxIsSupported = version_info >= (3, 12)

if sphinxIsSupported:
	from sphinx.testing.util import SphinxTestApp
	from sphinx.util.console import strip_colors



if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


PIPELINE = dedent("""\
	spec:
	  description: 'Packages a Python project.'
	  inputs:
	    package_name:
	      description: 'Name of the package.'
	    python_version:
	      description: 'Python version.'
	      default: '3.14'
	    dry_run:
	      type: boolean
	      default: false
	    pages_on:
	      default: |
	        default-branch
	        release-tag
	    level:
	      default: 'info'
	      options: ['info', 'debug']
	    tag:
	      default: 'v1'
	      regex: '^v[0-9]+$'
	---
	variables:
	  DEPLOY_ENV:
	    value: 'staging'
	    description: 'Where to deploy.'
	    options: ['staging', 'production']
	  PLAIN: 'x'

	stages: [build]

	Build:
	  stage: build
	  script:
	    - echo "Building $[[ inputs.package_name ]]"
""")
"""A pipeline file with inputs and default variables."""

SIMPLE = dedent("""\
	variables:
	  PLAIN: 'x'

	Build:
	  script: [make]
""")
"""A pipeline file without inputs."""

PAGE = dedent("""\
	.. glci:pipeline:: Package

	Package
	#######
""")
"""A page documenting the pipeline 'Package'."""


@mark.skipif(not sphinxIsSupported, reason="Sphinx 9.1 needs Python 3.12 or newer.")
class Project(Testcase):
	"""Base-class of the testcases: a Sphinx project in a temporary directory, removed after each testcase."""

	_directory: TemporaryDirectory
	_path:      Path
	_warnings:  StringIO

	def setUp(self) -> None:
		self._directory = TemporaryDirectory()
		self._path = Path(self._directory.name)
		(self._path / "pipelines").mkdir()
		(self._path / "src").mkdir()

	def tearDown(self) -> None:
		self._directory.cleanup()

	def _Pipeline(self, name: str, content: str = SIMPLE) -> Path:
		"""
		Write a pipeline file.

		:param name:    Name of the pipeline, the file's stem.
		:param content: Optional, content of the file. Default: :data:`SIMPLE`.
		:returns:       Path to the file.
		"""
		path = self._path / "pipelines" / f"{name}.yml"
		path.write_text(content, encoding="utf-8")

		return path

	def _Build(self, documents: dict[str, str], parallel: int = 0, fresh: bool = True, **config: Any) -> "SphinxTestApp":
		"""
		Write the documents and build the project as HTML.

		:param documents: Content of the documents, by name; ``index`` has a toctree of the others.
		:param parallel:  Optional, number of processes reading the documents. Default: ``0``.
		:param fresh:     Optional, ``True`` to discard a previous build's environment. Default: ``True``.
		:param config:    Configuration values overriding the defaults.
		:returns:         The Sphinx application after the build.
		"""
		source = self._path / "src"
		(source / "conf.py").write_text('extensions = ["pyTooling.GitLab.Sphinx"]\n', encoding="utf-8")
		others = "".join(f"   {name}\n" for name in documents if name != "index")
		index = documents.get("index", "Index\n#####\n")
		(source / "index.rst").write_text(f"{index}\n\n.. toctree::\n\n{others}", encoding="utf-8")
		for name, content in documents.items():
			if name != "index":
				(source / f"{name}.rst").write_text(content, encoding="utf-8")

		overrides = {"glci_project": "group/project", "glci_pipeline_directory": "../pipelines"}
		overrides.update(config)
		self._warnings = StringIO()
		app = SphinxTestApp(
			"html", source, self._path / "build", freshenv=fresh, confoverrides=overrides, status=StringIO(),
			warning=self._warnings, parallel=parallel
		)
		try:
			with catch_warnings():
				# Sphinx forks its reading processes; in a multi-threaded process, like a pytest-xdist worker, Python warns
				# about fork(), and pytest turns a DeprecationWarning into an error.
				filterwarnings("ignore", r"This process .* is multi-threaded, use of fork\(\)", DeprecationWarning)
				app.build()
		finally:
			app.cleanup()

		return app

	def _HTML(self, name: str) -> str:
		"""
		Read a built page.

		:param name: Name of the document.
		:returns:    The page's HTML.
		"""
		return (self._path / "build" / "html" / f"{name}.html").read_text(encoding="utf-8")

	def _WarningLines(self) -> list[str]:
		"""
		Return the warnings of the last build, without the temporary directory's path and with ``/`` as path separator.

		The temporary directory is removed as given and as resolved, e.g. below ``/private/var`` on macOS.

		:returns: One line per warning.
		"""
		prefixes = sorted({str(self._path), str(self._path.resolve())}, key=len, reverse=True)
		lines = []
		for line in self._warnings.getvalue().splitlines():
			line = strip_colors(line)
			for prefix in prefixes:
				line = line.replace(f"{prefix}{sep}", "").replace(f"{prefix}/", "")
			lines.append(line.replace("\\", "/") if sep == "\\" else line)

		return lines


@testsuite("Pipelines")
class Pipelines(Project):
	"""The directive 'glci:pipeline': its target, its file and its configuration."""

	@testcase("Target")
	def Target(self) -> None:
		"""
		A pipeline gets a target, a label, and is found by the domain.

		Builds a page with 'glci:pipeline:: Package' and checks the anchors and 'ResolvePipeline'.
		"""
		self._Pipeline("Package")
		app = self._Build({"Package": PAGE})

		domain = app.env.get_domain("glci")
		self.assertEqual(("Package", "glci-pipeline-Package"), domain.ResolvePipeline("Package"))
		self.assertIsNone(domain.ResolvePipeline("Unknown"))
		self.assertEqual([], self._WarningLines())

		html = self._HTML("Package")
		self.assertIn('id="glci-pipeline-Package"', html)
		self.assertIn('id="pipeline-package"', html)

	@testcase("Parameter checks")
	def ParameterChecks(self) -> None:
		"""
		The domain's methods check their parameters.

		Calls 'ResolvePipeline', 'NoteObject' and 'LoadPipelineFile' with wrong parameters and checks the messages.
		"""
		self._Pipeline("Package")
		domain = self._Build({"Package": PAGE}).env.get_domain("glci")

		for argument, exceptionType, message in (
			(None, ValueError, "Parameter 'name' is None."),
			(1,    TypeError,  "Parameter 'name' is not of type 'str'.")
		):
			with self.subTest(method="ResolvePipeline", message=message):
				with self.assertRaises(exceptionType) as context:
					domain.ResolvePipeline(argument)

				self.assertEqual(message, str(context.exception))

		for arguments, exceptionType, message in (
			((None, "Package.x", "id"),               ValueError, "Parameter 'objectType' is None."),
			(("input", 1, "id"),                      TypeError,  "Parameter 'name' is not of type 'str'."),
			(("input", "Package.x", None),            ValueError, "Parameter 'nodeID' is None."),
			(("input", "Package.x", "id", "section"), TypeError,  "Parameter 'location' is not of type 'Node'.")
		):
			with self.subTest(method="NoteObject", message=message):
				with self.assertRaises(exceptionType) as context:
					domain.NoteObject(*arguments)

				self.assertEqual(message, str(context.exception))

		for argument, exceptionType, message in (
			(None,          ValueError, "Parameter 'path' is None."),
			("Package.yml", TypeError,  "Parameter 'path' is not of type 'Path'.")
		):
			with self.subTest(method="LoadPipelineFile", message=message):
				with self.assertRaises(exceptionType) as context:
					domain.LoadPipelineFile(argument)

				self.assertEqual(message, str(context.exception))

	@testcase("Index")
	def Index(self) -> None:
		"""
		A pipeline has an entry in the general index.

		Builds a page with a pipeline and reads the index page.
		"""
		self._Pipeline("Package")
		self._Build({"Package": PAGE})

		self.assertIn("GitLab CI/CD pipeline", self._HTML("genindex"))

	@testcase("Option ':file:'")
	def File(self) -> None:
		"""
		Option ':file:' names the file relative to the document.

		Builds a page whose pipeline file is in the source directory, without 'glci_pipeline_directory'.
		"""
		(self._path / "src" / "yaml").mkdir()
		self._Pipeline("Other").rename(self._path / "src" / "yaml" / "Package.yml")
		page = PAGE.replace(".. glci:pipeline:: Package\n", ".. glci:pipeline:: Package\n   :file: yaml/Package.yml\n")
		app = self._Build({"Package": page}, glci_pipeline_directory=None)

		self.assertEqual([], self._WarningLines())
		domain = app.env.get_domain("glci")
		self.assertEqual(("Package", "glci-pipeline-Package"), domain.ResolvePipeline("Package"))

	@testcase("Component layout")
	def Component(self) -> None:
		"""
		Without ':file:', a component's 'template.yml' in a directory named after the pipeline is found.

		Writes 'pipelines/Package/template.yml' and builds a page with 'glci:pipeline:: Package'.
		"""
		(self._path / "pipelines" / "Package").mkdir()
		(self._path / "pipelines" / "Package" / "template.yml").write_text(SIMPLE, encoding="utf-8")
		self._Build({"Package": PAGE})

		self.assertEqual([], self._WarningLines())

	@testcase("Pipeline directory from the repository root")
	def RepositoryRoot(self) -> None:
		"""
		Without 'glci_pipeline_directory', the files are read from 'glci_repository_root'.

		Builds a page with 'glci_repository_root' pointing to the directory of the pipeline files.
		"""
		self._Pipeline("Package")
		app = self._Build({"Package": PAGE}, glci_pipeline_directory=None, glci_repository_root="../pipelines")

		self.assertEqual([], self._WarningLines())
		domain = app.env.get_domain("glci")
		self.assertEqual((self._path / "pipelines").resolve(), domain.PipelineDirectory)
		self.assertIsNotNone(domain.Resolver)

	@testcase("Local includes")
	def LocalIncludes(self) -> None:
		"""
		A pipeline file is read with the domain's resolver, so a job extends a hidden job of a local include.

		Builds a page whose pipeline file extends a job of an included file, with and without 'glci_repository_root'.
		"""
		(self._path / "pipelines" / "ci").mkdir()
		(self._path / "pipelines" / "ci" / "base.yml").write_text(".base:\n  image: alpine\n", encoding="utf-8")
		path = self._Pipeline("Package", "include: [{local: /ci/base.yml}]\n\nBuild:\n  extends: .base\n  script: [make]\n")

		app = self._Build({"Package": PAGE}, glci_repository_root="../pipelines")
		self.assertEqual([], self._WarningLines())
		self.assertEqual("alpine", app.env.get_domain("glci").LoadPipelineFile(path).Jobs["Build"].Image)

		app = self._Build({"Package": PAGE})
		self.assertEqual(("extends .base", ), app.env.get_domain("glci").LoadPipelineFile(path).Jobs["Build"].Unresolved)

	@testcase("No file")
	def NoFile(self) -> None:
		"""
		A pipeline without ':file:' and without a configured directory is a warning.

		Builds a page without 'glci_pipeline_directory' and checks the warning.
		"""
		self._Build({"Package": PAGE}, glci_pipeline_directory=None)

		self.assertIn(
			"src/Package.rst:1: WARNING: glci:pipeline 'Package' has no file: give option ':file:' or set "
			"'glci_pipeline_directory'. [glci.pipeline]",
			self._WarningLines()
		)

	@testcase("Missing file")
	def MissingFile(self) -> None:
		"""
		A pipeline whose file doesn't exist is a warning naming the first candidate.

		Builds a page without writing the pipeline file.
		"""
		self._Build({"Package": PAGE})

		self.assertIn(
			"src/Package.rst:1: WARNING: glci:pipeline 'Package': file 'pipelines/Package.yml' doesn't exist. "
			"[glci.pipeline]",
			self._WarningLines()
		)

	@testcase("Malformed file")
	def Malformed(self) -> None:
		"""
		A file that isn't a well-formed configuration is a warning at the place in the file.

		Writes a job needing a job the file doesn't have.
		"""
		self._Pipeline("Package", "Build:\n  script: [make]\n  needs: [Missing]\n")
		self._Build({"Package": PAGE})

		lines = self._WarningLines()
		self.assertEqual(1, len(lines))
		self.assertTrue(lines[0].startswith("pipelines/Package.yml:"))
		self.assertIn("glci:pipeline 'Package':", lines[0])
		self.assertTrue(lines[0].endswith("[glci.pipeline]"))

	@testcase("Configuration values")
	def Config(self) -> None:
		"""
		The configuration values have their defaults, and can be set.

		Builds a project twice and reads the values.
		"""
		self._Pipeline("Package")
		app = self._Build({"Package": PAGE})

		self.assertIsNone(app.config.glci_ref)
		self.assertEqual("https://gitlab.com", app.config.glci_server)
		self.assertEqual("PIPELINE", app.config.glci_label_prefix)

		app = self._Build({"Package": PAGE}, glci_ref="v1")
		self.assertEqual("v1", app.config.glci_ref)

	@testcase("No label prefix")
	def LabelPrefix(self) -> None:
		"""
		Without a label prefix, no labels are registered.

		Builds a page with 'glci_label_prefix' set to None.
		"""
		self._Pipeline("Package")
		self._Build({"Package": PAGE}, glci_label_prefix=None)

		self.assertNotIn('id="pipeline-package"', self._HTML("Package"))

	@testcase("Duplicate")
	def Duplicate(self) -> None:
		"""
		A pipeline documented twice is a warning.

		Builds two pages documenting the pipeline 'Package'.
		"""
		self._Pipeline("Package")
		self._Build({"Package": PAGE, "Again": PAGE.replace("Package\n#######", "Again\n#####")})

		self.assertTrue(any("Duplicate description of glci:pipeline 'Package'" in line for line in self._WarningLines()))

	@testcase("Pipeline reference")
	def Reference(self) -> None:
		"""
		The role ':glci:pipeline:' and the label link to the pipeline, from another document too.

		Builds an index page referring to the pipeline.
		"""
		self._Pipeline("Package")
		index = "Index\n#####\n\n:glci:pipeline:`Package` and :ref:`PIPELINE/Package`\n"
		self._Build({"Package": PAGE, "index": index})

		html = self._HTML("index")
		self.assertEqual([], self._WarningLines())
		self.assertIn('href="Package.html#glci-pipeline-Package"', html)
		self.assertIn('href="Package.html#pipeline-package"><span class="std std-ref">Package</span>', html)


@testsuite("Builds")
class Builds(Project):
	"""Parallel and incremental builds."""

	@testcase("Parallel build")
	def Parallel(self) -> None:
		"""
		A parallel build merges the domain data of its readers.

		Builds six documents with two processes and checks references across documents.
		"""
		self._Pipeline("Package")
		self._Pipeline("Build")
		documents = {
			"Package": PAGE,
			"Build":   PAGE.replace("Package", "Build") + "\n:glci:pipeline:`Package`\n",
			"A": "A\n#\n", "B": "B\n#\n", "C": "C\n#\n", "D": "D\n#\n",
		}
		app = self._Build(documents, parallel=2)

		self.assertEqual([], self._WarningLines())
		objects = app.env.get_domain("glci").Objects
		self.assertEqual(("Build", "glci-pipeline-Build"), objects[("pipeline", "Build")])
		self.assertEqual(("Package", "glci-pipeline-Package"), objects[("pipeline", "Package")])
		self.assertIn('href="Package.html#glci-pipeline-Package"', self._HTML("Build"))

	@testcase("Incremental build")
	def Incremental(self) -> None:
		"""
		A document read again drops its objects.

		Builds a project, removes the pipeline from its page and builds again without discarding the environment.
		"""
		self._Pipeline("Package")
		index = "Index\n#####\n\n:glci:pipeline:`Package`\n"
		self._Build({"Package": PAGE, "index": index})
		self.assertEqual([], self._WarningLines())

		app = self._Build({"Package": "Package\n#######\n", "index": index}, fresh=False)

		self.assertNotIn(("pipeline", "Package"), app.env.get_domain("glci").Objects)
		self.assertIn(
			"src/index.rst:4: WARNING: glci:pipeline reference target not found: Package [ref.pipeline]",
			self._WarningLines()
		)


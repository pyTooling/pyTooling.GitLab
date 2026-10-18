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
Unit tests for :mod:`pyTooling.GitLab.Sphinx.Graph`: the pipeline graph of a pipeline file.

The DOT is checked as :class:`~pyTooling.GitLab.Sphinx.Graph.PipelineDotGraph` writes it, and as a Sphinx build hands it
to :mod:`sphinx.ext.graphviz`.
"""
from pathlib                  import Path
from shutil                   import which
from subprocess               import run as subprocess_run
from tempfile                 import TemporaryDirectory
from textwrap                 import dedent
from typing                   import Any, Optional as Nullable

from pytest                   import mark

from pyTooling.Testing        import Testcase, testsuite, testcase

from tests.unit.Sphinx.Domain import Project, sphinxIsSupported

if sphinxIsSupported:
	from sphinx.ext.graphviz           import graphviz
	from sphinx.testing.util           import SphinxTestApp

	from pyTooling.GitLab.PipelineFile import IncludeResolver, PipelineFile
	from pyTooling.GitLab.Sphinx.Graph import CSS_CLASS, PipelineDotGraph


if __name__ == "__main__":  # pragma: no cover
	print("ERROR: you called a testcase declaration file as an executable module.")
	print("Use: 'python -m unittest <testcase module>'")
	exit(1)


PIPELINE = dedent("""\
	stages: [build, test, deploy]

	Build:
	  stage: build
	  script: [make]

	Lint:
	  stage: build
	  script: [lint]

	Test:
	  stage: test
	  parallel:
	    matrix:
	      - PYTHON: ['3.13', '3.14']
	        OS: [linux]
	  script: [pytest]

	Shards:
	  stage: test
	  parallel: 2
	  script: [pytest]

	Docs:
	  stage: test
	  needs: [Build]
	  rules:
	    - if: '$CI_COMMIT_TAG'
	    - if: '$CI_PIPELINE_SOURCE == "web"'
	  script: [sphinx]

	Child:
	  stage: deploy
	  needs: [Docs]
	  trigger:
	    include: /ci/child.yml

	Downstream:
	  stage: deploy
	  needs: [Docs]
	  when: manual
	  trigger:
	    project: group/other
""")
"""A pipeline file with every kind of element."""

CHILD = dedent("""\
	Package:
	  stage: build
	  script: [build]

	Publish:
	  stage: deploy
	  script: [twine]
""")
"""The child pipeline 'ci/child.yml'."""


def write(directory: Path) -> Path:
	"""
	Write :data:`PIPELINE` as ``.gitlab-ci.yml`` and :data:`CHILD` as ``ci/child.yml`` into a directory.

	:param directory: The directory.
	:returns:         Path to the pipeline file.
	"""
	(directory / "ci").mkdir(exist_ok=True)
	(directory / "ci" / "child.yml").write_text(CHILD, encoding="utf-8")
	path = directory / ".gitlab-ci.yml"
	path.write_text(PIPELINE, encoding="utf-8")

	return path


def draw(directory: str, **options: Any) -> str:
	"""
	Write the pipeline files into a directory and draw the pipeline without Sphinx.

	:param directory: The directory.
	:param options:   Parameters of :class:`PipelineDotGraph` besides the file and the resolver.
	:returns:         The graph in the DOT language.
	"""
	root = Path(directory)
	path = write(root)

	return str(PipelineDotGraph(PipelineFile.FromFile(path), IncludeResolver(root), **options))


def line(code: str, start: str) -> str:
	"""
	Return the first line of a graph starting with a text, after its indentation.

	:param code:  The graph in the DOT language.
	:param start: The beginning of the line.
	:returns:     The line.
	"""
	return next(text for text in code.splitlines() if text.lstrip("\t").startswith(start))


@mark.skipif(not sphinxIsSupported, reason="Sphinx 9.1 needs Python 3.12 or newer.")
@testsuite("Nodes")
class Nodes(Testcase):
	"""The node of each kind of job."""

	@testcase("Job")
	def Job(self) -> None:
		"""
		A job running a script is a grey box with square corners, labelled with its stage.

		Draws the pipeline and reads the node of 'Build'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		build = line(code, '"Build" [')
		self.assertIn("stage: build", build)
		self.assertIn('style="filled", fillcolor="#f2f2f2"', build)

	@testcase("Rules")
	def Rules(self) -> None:
		"""
		A job whose rules have conditions is dashed, and its tooltip lists them, one per rule.

		Reads the nodes of 'Docs' and 'Build'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		docs = line(code, '"Docs" [')
		self.assertIn('style="filled,dashed"', docs)
		self.assertIn('tooltip="if: $CI_COMMIT_TAG\\nif: $CI_PIPELINE_SOURCE == \\"web\\""', docs)
		self.assertNotIn("dashed", line(code, '"Build" ['))

	@testcase("Other project's pipeline")
	def Downstream(self) -> None:
		"""
		A trigger job starting another project's pipeline is a white rounded box naming the project; a manual job is dashed.

		Reads the node of 'Downstream'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		downstream = line(code, '"Downstream" [')
		self.assertIn("project: group/other", downstream)
		self.assertIn("manual", downstream)
		self.assertIn('style="rounded,filled,dashed", fillcolor="#ffffff"', downstream)
		self.assertNotIn("glci-link", downstream)

	@testcase("Child pipeline not expanded")
	def ChildNode(self) -> None:
		"""
		At depth 0, a trigger job starting a child pipeline is a rounded box naming the files, marked for a link.

		Reads the node of 'Child'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		child = line(code, '"Child" [')
		self.assertIn("/ci/child.yml", child)
		self.assertIn('style="rounded,filled"', child)
		self.assertIn("/*glci-link:child*/", child)

	@testcase("Stable")
	def Stable(self) -> None:
		"""
		The same file is drawn as the same DOT.

		Draws the pipeline twice.
		"""
		with TemporaryDirectory() as first, TemporaryDirectory() as second:
			self.assertEqual(draw(first), draw(second))


@mark.skipif(not sphinxIsSupported, reason="Sphinx 9.1 needs Python 3.12 or newer.")
@testsuite("Edges")
class Edges(Testcase):
	"""The edges between the jobs."""

	@testcase("Stages and needs")
	def StagesAndNeeds(self) -> None:
		"""
		A job without 'needs' follows the jobs of the earlier stage; 'needs' replaces that; an implied edge is dropped.

		Reads the edges of the pipeline.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		self.assertIn('"Build" -> "Docs";', code)
		self.assertIn('"Lint" -> "Test/Test: [3.13, linux]" [lhead="cluster_Test"];', code)
		self.assertNotIn('"Lint" -> "Docs"', code)
		self.assertIn('"Docs" -> "Downstream";', code)

	@testcase("Not reduced")
	def NotReduced(self) -> None:
		"""
		Without the reduction, an edge a longer path implies is drawn too.

		Draws the pipeline with 'reduce' set to False and counts the edges.
		"""
		with TemporaryDirectory() as first, TemporaryDirectory() as second:
			reduced = draw(first)
			full = draw(second, reduce=False)

		self.assertGreaterEqual(full.count(" -> "), reduced.count(" -> "))

	@testcase("Roots and direction")
	def RootsAndDirection(self) -> None:
		"""
		The jobs needing nothing are in the first rank; the direction is a graph attribute.

		Draws the pipeline from top to bottom.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory, direction="TB")

		self.assertIn('{rank=min; "Build"; "Lint";}', code)
		self.assertIn("rankdir=TB;", code)


@mark.skipif(not sphinxIsSupported, reason="Sphinx 9.1 needs Python 3.12 or newer.")
@testsuite("Clusters")
class Clusters(Testcase):
	"""Matrices and expanded child pipelines."""

	@testcase("Matrix")
	def Matrix(self) -> None:
		"""
		A job with 'parallel:matrix' is a cluster of its instances, labelled with the dimensions; 'parallel: N' with the
		count. An instance is named as GitLab names it.

		Reads the clusters of 'Test' and 'Shards'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory)

		self.assertIn('subgraph "cluster_Test" {', code)
		self.assertIn("matrix: PYTHON, OS", code)
		self.assertIn('"Test/Test: [3.14, linux]" [label=<Test: [3.14, linux]>', code)
		self.assertIn("parallel: 2", code)
		self.assertIn('"Shards/Shards 2/2" [label=<Shards 2/2>', code)

	@testcase("Child pipeline expanded")
	def Child(self) -> None:
		"""
		At depth 1, a trigger job's child pipeline is a cluster of its jobs, linked as the node was; the files are listed.

		Draws the pipeline at depth 1.
		"""
		with TemporaryDirectory() as directory:
			root = Path(directory)
			graph = PipelineDotGraph(PipelineFile.FromFile(write(root)), IncludeResolver(root), depth=1)
			code = str(graph)

			self.assertEqual([".gitlab-ci.yml", "child.yml"], [pipelineFile.Path.name for pipelineFile in graph.Files])

		self.assertIn('subgraph "cluster_Child" {', code)
		self.assertIn('"Child/Package" -> "Child/Publish";', code)
		self.assertIn("\t\t/*glci-link:child*/\n", code)
		self.assertIn("Publish", [job.Name for job in graph.Jobs])

	@testcase("Graphviz accepts it")
	@mark.skipif(which("dot") is None, reason="Graphviz isn't installed.")
	def Syntax(self) -> None:
		"""
		Graphviz renders the graph without a complaint.

		Draws the pipeline at depth 1 and renders it with 'dot'.
		"""
		with TemporaryDirectory() as directory:
			code = draw(directory, depth=1, link=False)

		result = subprocess_run(["dot", "-Tsvg"], input=code, capture_output=True, text=True, check=False)
		self.assertEqual(0, result.returncode, result.stderr)
		self.assertEqual("", result.stderr)


@mark.skipif(not sphinxIsSupported, reason="Sphinx 9.1 needs Python 3.12 or newer.")
@testsuite("Parameters")
class Parameters(Testcase):
	"""The parameter checks of 'PipelineDotGraph'."""

	@testcase("Wrong parameters")
	def Wrong(self) -> None:
		"""
		Every parameter is checked: None, then type, then value.

		Creates graphs with wrong parameters and checks the messages.
		"""
		with TemporaryDirectory() as directory:
			root = Path(directory)
			pipelineFile = PipelineFile.FromFile(write(root))

			with self.assertRaises(ValueError) as context:
				PipelineDotGraph(None)
			self.assertEqual("Parameter 'pipelineFile' is None.", str(context.exception))

			for arguments, exceptionType, message in (
				(("pipeline.yml", ),               TypeError,  "Parameter 'pipelineFile' is not of type 'PipelineFile'."),
				((pipelineFile, root),             TypeError,  "Parameter 'resolver' is not of type 'IncludeResolver'."),
				((pipelineFile, None, None),       ValueError, "Parameter 'direction' is None."),
				((pipelineFile, None, 1),          TypeError,  "Parameter 'direction' is not of type 'str'."),
				((pipelineFile, None, "RL"),       ValueError, "Parameter 'direction' is neither 'LR' nor 'TB'."),
				((pipelineFile, None, "LR", None), ValueError, "Parameter 'depth' is None."),
				((pipelineFile, None, "LR", True), TypeError,  "Parameter 'depth' is not of type 'int'."),
				((pipelineFile, None, "LR", -1),   ValueError, "Parameter 'depth' is negative."),
				((pipelineFile, None, "LR", 0, None),        ValueError, "Parameter 'reduce' is None."),
				((pipelineFile, None, "LR", 0, "yes"),       TypeError,  "Parameter 'reduce' is not of type 'bool'."),
				((pipelineFile, None, "LR", 0, True, None),  ValueError, "Parameter 'link' is None."),
				((pipelineFile, None, "LR", 0, True, "yes"), TypeError,  "Parameter 'link' is not of type 'bool'."),
			):
				with self.subTest(message=message):
					with self.assertRaises(exceptionType) as context:
						PipelineDotGraph(*arguments)

					self.assertEqual(message, str(context.exception))


@testsuite("Directive")
class Directive(Project):
	"""The directive 'glci:pipeline-graph' in a Sphinx build."""

	def _Graph(
		self,
		options:   str                      = "",
		builder:   str                      = "html",
		documents: Nullable[dict[str, str]] = None,
		**config:  Any
	) -> list[str]:
		"""
		Build a project drawing ``.gitlab-ci.yml`` and return the DOT of its pipeline graphs.

		:param options:   Optional, lines of options of the directive, unindented. Default: none.
		:param builder:   Optional, name of the builder. Default: ``html``.
		:param documents: Optional, more documents, by name. Default: none.
		:param config:    Configuration values overriding the defaults.
		:returns:         The DOT of every pipeline graph after its links are resolved.
		"""
		write(self._path / "pipelines")
		source = self._path / "src"
		(source / "conf.py").write_text('extensions = ["pyTooling.GitLab.Sphinx"]\n', encoding="utf-8")
		documents = {} if documents is None else documents
		indented = "".join(f"   {text}\n" for text in dedent(options).splitlines())
		others = "".join(f"   {name}\n" for name in documents)
		(source / "index.rst").write_text(
			f"Index\n#####\n\n.. toctree::\n   :hidden:\n\n{others}\n"
			f".. glci:pipeline-graph:: ../pipelines/.gitlab-ci.yml\n{indented}",
			encoding="utf-8"
		)
		for name, content in documents.items():
			(source / f"{name}.rst").write_text(content, encoding="utf-8")

		codes = []

		def capture(_: Any, doctree: Any, __: str) -> None:
			"""
			Nested function collecting the DOT of the pipeline graphs of a resolved document.

			:param _:       The Sphinx application.
			:param doctree: The resolved document.
			:param __:      Name of the document.
			"""
			codes.extend(node["code"] for node in doctree.findall(graphviz) if CSS_CLASS in node["classes"])

		overrides = {"glci_project": "group/project"}
		overrides.update(config)
		app = SphinxTestApp(
			builder, source, self._path / "build", freshenv=True, confoverrides=overrides, status=self._warnings,
			warning=self._warnings
		)
		app.connect("doctree-resolved", capture, priority=900)
		try:
			app.build()
		finally:
			app.cleanup()

		return codes

	def setUp(self) -> None:
		super().setUp()
		from io import StringIO

		self._warnings = StringIO()

	@testcase("Link to the child pipeline's page")
	def Link(self) -> None:
		"""
		In HTML, a trigger job links to the page documenting its child pipeline by 'glci:pipeline'.

		Builds the graph and a page documenting the pipeline 'child'.
		"""
		page = ".. glci:pipeline:: child\n   :file: ../pipelines/ci/child.yml\n\nChild\n#####\n"
		(code, ) = self._Graph(documents={"child": page})

		self.assertIn(' URL="child.html#glci-pipeline-child" target="_top"];', line(code, '"Child" ['))
		self.assertNotIn("glci-link", code)

	@testcase("Expanded child pipeline")
	def Expanded(self) -> None:
		"""
		With ':depth: 1' and the repository's root configured, the child pipeline is a cluster.

		Builds the graph at depth 1.
		"""
		(code, ) = self._Graph(":depth: 1", glci_repository_root="../pipelines")

		self.assertIn('subgraph "cluster_Child" {', code)

	@testcase("Without links")
	def NoLinks(self) -> None:
		"""
		':link: no' links nothing; a format other than HTML neither, and no marker remains.

		Builds the graph without links, and as text.
		"""
		page = ".. glci:pipeline:: child\n   :file: ../pipelines/ci/child.yml\n\nChild\n#####\n"
		(code, ) = self._Graph(":link: no", documents={"child": page})
		self.assertNotIn("URL=", code)

		(code, ) = self._Graph(builder="text", documents={"child": page})
		self.assertNotIn("URL=", code)
		self.assertNotIn("glci-link", code)

	@testcase("Errors")
	def Errors(self) -> None:
		"""
		A missing file, a wrong direction and a wrong boolean are errors in the document.

		Builds the graph with wrong options.
		"""
		for options, message in (
			(":direction: RL", "direction"),
			(":reduce: maybe", "reduce"),
		):
			with self.subTest(options=options):
				self.assertEqual([], self._Graph(options))
				self.assertIn(message, self._warnings.getvalue())

		(self._path / "pipelines" / ".gitlab-ci.yml").unlink()
		source = self._path / "src"
		(source / "index.rst").write_text("Index\n#####\n\n.. glci:pipeline-graph:: missing.yml\n", encoding="utf-8")
		app = SphinxTestApp(
			"html", source, self._path / "build", freshenv=True, status=self._warnings, warning=self._warnings
		)
		try:
			app.build()
		finally:
			app.cleanup()

		self.assertIn("glci:pipeline-graph: Couldn't draw 'missing.yml'", self._warnings.getvalue())

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
A Sphinx directive drawing the pipeline a GitLab CI/CD pipeline file defines as a Graphviz graph.

The jobs of a pipeline file and the dependencies between them - the ``needs``, and the stages for a job without - are
its pipeline. This directive draws it at build time from the pipeline file:

.. code-block:: ReST

   .. glci:pipeline-graph:: ../.gitlab-ci.yml
      :depth: 1

A job is a node labelled with its name and stage. A trigger job starting a child pipeline, whose files are found
locally, is expanded into a cluster of the child pipeline's jobs, as many levels deep as ``:depth:`` says. In HTML, a
trigger job links to the page documenting its child pipeline, if the ``glci`` domain knows one.

.. seealso::

   :mod:`pyTooling.GitLab.PipelineFile`
      |rarr| The model of a pipeline file the graph is drawn from.
   :mod:`pyTooling.CI`
      |rarr| The service-independent model of a pipeline, which a pipeline file is converted into.
"""
from __future__                      import annotations

from html                            import escape as html_escape
from pathlib                         import Path, PurePosixPath
from re                              import Match, compile as re_compile
from typing                          import TYPE_CHECKING, Any, Optional as Nullable

from docutils                        import nodes
from docutils.parsers.rst            import directives
from sphinx.application              import Sphinx
from sphinx.ext.graphviz             import align_spec, figure_wrapper, graphviz

from pyTooling.CI                    import Base as CIBase, Matrix as CIMatrix, RuleOutcome, Workflow as CIWorkflow
from pyTooling.Common                import getFullyQualifiedName
from pyTooling.Decorators            import export, readonly
from pyTooling.Graph                 import Vertex
from pyTooling.MetaClasses           import ExtendedType
from pyTooling.Sphinx                import BaseDirective, SphinxExtensionError, strip, stripAndNormalize

if TYPE_CHECKING:  # pragma: no cover
	from pyTooling.GitLab.PipelineFile import IncludeResolver, Job, PipelineFile


__all__ = ["GRAPH_ATTRIBUTES", "CSS_CLASS", "LINK_MARKER"]

GRAPH_ATTRIBUTES = (
	"compound=true;",
	"newrank=true;",
	'fontname="sans-serif";',
	'fontsize="10";',
	"nodesep=0.25;",
	"ranksep=0.4;",
	'node [shape="box", style="rounded,filled", color="#5f6b7a", fillcolor="#fbe7d6", penwidth="1.0",',
	'      fontname="sans-serif", fontsize="10"];',
	'edge [color="#5f6b7a", arrowsize="0.7"];',
)
"""Attributes every pipeline graph is drawn with."""

CSS_CLASS = "glci-pipeline-graph"
"""CSS class of a pipeline graph's ``graphviz`` node, which is also how :func:`resolveLinks` finds it."""

LINK_MARKER = re_compile(r"(?P<space>\s*)/\*glci-link:(?P<name>[^*]*)\*/")
"""
A DOT comment, and the whitespace before it, standing where a trigger job's link belongs, until :func:`resolveLinks`
replaces it by the link or removes it.
"""


@export
class PipelineDotGraph(metaclass=ExtendedType, slots=True):
	"""
	The pipeline of a pipeline file in the DOT language: its jobs as nodes, their dependencies as edges.

	The pipeline file is converted by :meth:`PipelineFile.ToPipeline
	<pyTooling.GitLab.PipelineFile.PipelineFile.ToPipeline>` into a :mod:`pyTooling.CI` model, and that by
	:meth:`~pyTooling.CI.Workflow.ToGraph` into a :class:`~pyTooling.Graph.Graph`, which is drawn: a vertex is a node, an
	edge an edge, and a trigger job or a parallel job with a :class:`~pyTooling.Graph.Subgraph` a cluster of the vertices
	it links to.

	The kind of an element is its node's shape and style:

	* a job running a script is a box with square corners, labelled with its name and stage;
	* a trigger job starting a child pipeline is a rounded box, labelled with the child pipeline's files; one starting
	  another project's pipeline is a white rounded box, labelled with the project - it is never expanded;
	* a job whose rules have conditions - ``rules:if`` - is dashed, and its tooltip lists them, one per rule; a manual
	  job is dashed too, and labelled *manual*;
	* a job with ``parallel`` is a cluster of its instances, labelled with the matrix' dimensions or the count of
	  instances.

	A trigger job whose child pipeline :class:`~pyTooling.GitLab.PipelineFile.IncludeResolver` reads is drawn as a
	cluster of the child pipeline's jobs instead, until the depth is used up. An edge to or from a job drawn as a cluster
	ends at the cluster's border.

	The graph's edges read *needs*; an arrow is drawn the other way round, from the needed job to the job needing it,
	in the direction the pipeline runs. The graph is drawn in file order, so the same file is always drawn as the same
	DOT.
	"""

	_link:       bool                #: Whether a trigger job starting a child pipeline is marked for a link.
	_statements: list[str]           #: The statements written so far, one per line, already indented.
	_jobs:       list[Job]           #: The jobs drawn, each once, in the order they were drawn.
	_files:      list[PipelineFile]  #: The pipeline files drawn, each once, the drawn file first.

	def __init__(
		self,
		pipelineFile: PipelineFile,
		resolver:     Nullable[IncludeResolver] = None,
		direction:    str                       = "LR",
		depth:        int                       = 0,
		reduce:       bool                      = True,
		link:         bool                      = True
	) -> None:
		"""
		Initializes the graph by drawing a pipeline file.

		:param pipelineFile:       The pipeline file to draw.
		:param resolver:           Optional, the resolver reading the files of the child pipelines. Without it, no child
		                           pipeline is expanded. Default: ``None``.
		:param direction:          Optional, direction the pipeline flows in: ``LR`` (left to right) or ``TB`` (top to
		                           bottom). Default: ``LR``.
		:param depth:              Optional, levels of child pipelines expanded into clusters. Default: ``0``.
		:param reduce:             Optional, drop an edge a longer path implies. Default: ``True``.
		:param link:               Optional, mark a trigger job starting a child pipeline for :func:`resolveLinks`.
		                           Default: ``True``.
		:raises ValueError:        If parameter 'pipelineFile' is None.
		:raises TypeError:         If parameter 'pipelineFile' is not of type
		                           :class:`~pyTooling.GitLab.PipelineFile.PipelineFile`.
		:raises TypeError:         If parameter 'resolver' is not of type
		                           :class:`~pyTooling.GitLab.PipelineFile.IncludeResolver`.
		:raises ValueError:        If parameter 'direction' is None.
		:raises TypeError:         If parameter 'direction' is not of type :class:`str`.
		:raises ValueError:        If parameter 'direction' is neither ``LR`` nor ``TB``.
		:raises ValueError:        If parameter 'depth' is None.
		:raises TypeError:         If parameter 'depth' is not of type :class:`int`.
		:raises ValueError:        If parameter 'depth' is negative.
		:raises ValueError:        If parameter 'reduce' is None.
		:raises TypeError:         If parameter 'reduce' is not of type :class:`bool`.
		:raises ValueError:        If parameter 'link' is None.
		:raises TypeError:         If parameter 'link' is not of type :class:`bool`.
		:raises PipelineFileError: If a child pipeline's file to expand is not a well-formed configuration.
		"""
		from pyTooling.GitLab.PipelineFile import IncludeResolver, PipelineFile

		if pipelineFile is None:
			raise ValueError("Parameter 'pipelineFile' is None.")
		elif not isinstance(pipelineFile, PipelineFile):
			ex = TypeError("Parameter 'pipelineFile' is not of type 'PipelineFile'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(pipelineFile)}'.")
			raise ex

		if resolver is not None and not isinstance(resolver, IncludeResolver):
			ex = TypeError("Parameter 'resolver' is not of type 'IncludeResolver'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(resolver)}'.")
			raise ex

		if direction is None:
			raise ValueError("Parameter 'direction' is None.")
		elif not isinstance(direction, str):
			ex = TypeError("Parameter 'direction' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(direction)}'.")
			raise ex
		elif direction not in ("LR", "TB"):
			ex = ValueError("Parameter 'direction' is neither 'LR' nor 'TB'.")
			ex.add_note(f"Got value '{direction}'.")
			raise ex

		if depth is None:
			raise ValueError("Parameter 'depth' is None.")
		elif not isinstance(depth, int) or isinstance(depth, bool):
			ex = TypeError("Parameter 'depth' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(depth)}'.")
			raise ex
		elif depth < 0:
			ex = ValueError("Parameter 'depth' is negative.")
			ex.add_note(f"Got value '{depth}'.")
			raise ex

		for parameterName, value in (("reduce", reduce), ("link", link)):
			if value is None:
				raise ValueError(f"Parameter '{parameterName}' is None.")
			elif not isinstance(value, bool):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'bool'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
				raise ex

		self._link =       link
		self._statements = [f"\trankdir={direction};", *(f"\t{attribute}" for attribute in GRAPH_ATTRIBUTES), ""]
		self._jobs =       []
		self._files =      [pipelineFile]

		graph = pipelineFile.ToPipeline(resolver, depth).ToGraph(reduce=reduce)
		self._DrawVertices(list(graph.IterateVertices()), "", "\t")

	@readonly
	def Jobs(self) -> list[Job]:
		"""
		Read-only property to access the jobs drawn (:attr:`_jobs`).

		A child pipeline expanded twice is drawn twice, but its jobs are listed once.

		:returns: The jobs of every pipeline file drawn, in the order they were drawn.
		"""
		return self._jobs

	@readonly
	def Files(self) -> list[PipelineFile]:
		"""
		Read-only property to access the pipeline files drawn (:attr:`_files`).

		:returns: The drawn pipeline file, followed by every child pipeline's file expanded into a cluster, each once.
		"""
		return self._files

	@staticmethod
	def _Quote(text: str) -> str:
		"""
		Quote a text as a DOT string, keeping its line breaks as escape sequences.

		:param text: The text to quote.
		:returns:    The text in double quotes.
		"""
		text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

		return f'"{text}"'

	@staticmethod
	def _Label(title: str, lines: list[str]) -> str:
		"""
		Render an HTML-like label: a title and, below it, lines in a smaller font.

		:param title: The title, unescaped.
		:param lines: The lines below the title, unescaped.
		:returns:     The label in angle brackets, as DOT writes an HTML-like label.
		"""
		label = html_escape(title, quote=False)
		for line in lines:
			label += f'<br/><font point-size="8" color="#3d4652">{html_escape(line, quote=False)}</font>'

		return f"<{label}>"

	@staticmethod
	def _Describe(element: CIBase) -> tuple[list[str], list[str], str]:
		"""
		Describe an element of the pipeline: the lines of its label, the parts of its style, and its tooltip.

		:param element: The job, matrix or trigger job to describe.
		:returns:       The label's lines below the element's name, the style's parts, and the tooltip - the pipeline
		                started and the rules' conditions, one per line, or an empty string.
		"""

		job = element.Definition
		lines =   [] if isinstance(element.Parent, CIMatrix) else [f"stage: {job.Stage}"]
		style =   []
		tooltip = []

		if (trigger := job.Trigger) is not None:
			if trigger.Project is not None:
				lines.append(f"project: {trigger.Project}")
				tooltip.append(f"trigger: {trigger.Project}")
			else:
				locations = [include.Location for include in trigger.Includes]
				lines.extend(locations)
				tooltip.append(f"trigger: {', '.join(locations)}")

		if isinstance(element, CIMatrix) and (parallel := job.Parallel) is not None:
			if parallel.IsMatrix:
				dimensions = dict.fromkeys(name for entry in parallel.Matrix for name in entry)
				lines.append(f"matrix: {', '.join(dimensions)}")
			else:
				lines.append(f"parallel: {parallel.Count}")

		if job.When is RuleOutcome.Manual:
			lines.append("manual")
			style.append("dashed")

		conditions = [rule.Condition for rule in element.Rules if rule.Condition is not None]
		if len(conditions) > 0:
			if "dashed" not in style:
				style.append("dashed")

			tooltip.extend(f"if: {condition}" for condition in conditions)

		return lines, style, "\n".join(tooltip)

	def _DrawNode(self, element: CIBase, identifier: str, indent: str) -> None:
		"""
		Draw a job, a matrix or a trigger job that isn't expanded as a node.

		:param element:    The element to draw.
		:param identifier: Identifier of the node.
		:param indent:     Indentation of the node's statement.
		"""
		lines, style, tooltip = self._Describe(element)

		if (trigger := element.Definition.Trigger) is None:
			attributes = {"style": ",".join(("filled", *style)), "fillcolor": "#f2f2f2"}
		elif trigger.Project is None:
			attributes = {"style": ",".join(("rounded", "filled", *style))}
		else:
			attributes = {"style": ",".join(("rounded", "filled", *style)), "fillcolor": "#ffffff"}

		if isinstance(element, CIMatrix):
			attributes["peripheries"] = "2"

		statement = f"{indent}{self._Quote(identifier)} [label={self._Label(str(element), lines)}"
		for name, value in attributes.items():
			statement += f", {name}={self._Quote(value)}"

		if tooltip != "":
			statement += f", tooltip={self._Quote(tooltip)}"

		if self._link and (name := self._ChildPipelineName(element)) is not None:
			statement += f" /*glci-link:{name}*/"

		self._statements.append(f"{statement}];")

	@staticmethod
	def _ChildPipelineName(element: CIBase) -> Nullable[str]:
		"""
		Return the name a trigger job's child pipeline is documented by: the stem of its first local file.

		:param element: The element.
		:returns:       The stem, as ``child`` for ``/ci/child.yml``, or ``None`` if the element starts no child pipeline
		                from a local file.
		"""
		from pyTooling.GitLab.PipelineFile import IncludeKind

		if (trigger := element.Definition.Trigger) is None or trigger.Project is not None:
			return None

		for include in trigger.Includes:
			if include.Kind is IncludeKind.Local:
				return PurePosixPath(include.Location).stem

		return None

	def _OpenCluster(self, element: CIBase, cluster: str, indent: str) -> None:
		"""
		Open a cluster drawing a trigger job or a matrix: write its ``subgraph`` statement and its attributes.

		:param element: The trigger job or the matrix.
		:param cluster: Identifier of the cluster.
		:param indent:  Indentation of the cluster's statement.
		"""
		lines, style, tooltip = self._Describe(element)
		self._statements.append(f"{indent}subgraph {self._Quote(cluster)} {{")
		self._statements.append(f"{indent}\tlabel={self._Label(str(element), lines)};")
		self._statements.append(f'{indent}\tlabeljust="l";')
		self._statements.append(f"{indent}\tstyle={self._Quote(','.join(('rounded', 'filled', *style)))};")
		self._statements.append(f'{indent}\tcolor="#8a9bb2";')
		self._statements.append(f'{indent}\tfillcolor="#fdf6f0";')
		if tooltip != "":
			self._statements.append(f"{indent}\ttooltip={self._Quote(tooltip)};")

	def _DrawVertices(self, vertices: list[Vertex], prefix: str, indent: str) -> tuple[str, str]:
		"""
		Draw the vertices of one level of the graph - the graph itself, or the subgraph of a trigger job or of a matrix -
		and their edges.

		An edge of the graph goes from the element needing to the element it needs; its arrow is drawn the other way round.

		:param vertices: The vertices, in file order.
		:param prefix:   Prefix of the identifiers of their nodes: the path of the jobs containing them.
		:param indent:   Indentation of their statements.
		:returns:        Identifiers of the node an arrow into the level ends at - the first vertex needing nothing - and of
		                 the node an arrow out of it starts at - the last vertex nothing needs.
		"""
		# per vertex: the node an arrow into it ends at, the node an arrow out of it starts at, and its cluster
		anchors: dict[Vertex, tuple[str, str, Nullable[str]]] = {}
		for vertex in vertices:
			element = vertex.Value
			if element.Definition not in self._jobs:
				self._jobs.append(element.Definition)

			identifier = f"{prefix}{element}"
			if not isinstance(element, (CIWorkflow, CIMatrix)) or vertex.OutboundLinkCount == 0:
				self._DrawNode(element, identifier, indent)
				anchors[vertex] = (identifier, identifier, None)
				continue

			cluster = f"cluster_{identifier}"
			self._OpenCluster(element, cluster, indent)
			if isinstance(element, CIWorkflow):
				self._files.extend(childFile for childFile in element.ChildFiles if childFile not in self._files)
				if self._link and (name := self._ChildPipelineName(element)) is not None:
					self._statements.append(f"{indent}\t/*glci-link:{name}*/")

			entryNode, exitNode = self._DrawVertices(
				[link.Destination for link in vertex.OutboundLinks], f"{identifier}/", f"{indent}\t"
			)
			self._statements.append(f"{indent}}}")
			anchors[vertex] = (entryNode, exitNode, cluster)

		# the vertices needing nothing start together: in the first rank of the graph, or side by side in their cluster
		roots = [self._Quote(anchors[vertex][0]) for vertex in vertices if vertex.OutboundEdgeCount == 0]
		if prefix == "":
			self._statements.append(f"{indent}{{rank=min; {'; '.join(roots)};}}")
		elif len(roots) > 1:
			self._statements.append(f"{indent}{{rank=same; {'; '.join(roots)};}}")

		for vertex in vertices:
			for edge in vertex.OutboundEdges:
				_, tail, tailCluster = anchors[edge.Destination]
				head, _, headCluster = anchors[vertex]

				attributes = []
				if tailCluster is not None:
					attributes.append(f"ltail={self._Quote(tailCluster)}")

				if headCluster is not None:
					attributes.append(f"lhead={self._Quote(headCluster)}")

				statement = f"{indent}{self._Quote(tail)} -> {self._Quote(head)}"
				if len(attributes) > 0:
					statement += f" [{', '.join(attributes)}]"

				self._statements.append(f"{statement};")

		first = next(vertex for vertex in vertices if vertex.OutboundEdgeCount == 0)
		last = [vertex for vertex in vertices if vertex.InboundEdgeCount == 0][-1]

		return anchors[first][0], anchors[last][1]

	def __str__(self) -> str:
		"""
		Render the graph.

		:returns: The graph in the DOT language.
		"""
		statements = "\n".join(self._statements)

		return f"digraph pipeline {{\n{statements}\n}}"


@export
class PipelineGraph(BaseDirective):
	"""
	The ``glci:pipeline-graph`` directive: the pipeline a pipeline file defines, drawn from the file.

	One argument, the path of the pipeline file relative to the document using the directive.

	A trigger job's child pipeline is read from ``glci_repository_root`` - relative to the source directory, and by
	default the directory of the drawn pipeline file - and expanded, while ``:depth:`` allows. The files are read by the
	resolver of the ``glci`` domain, which reads every file once per build; without ``glci_repository_root``, by a
	resolver of its own.
	"""

	directiveName: str = "glci:pipeline-graph"  #: Name the directive is invoked by.

	has_content =               False  #: A boolean; ``True`` if content is allowed.
	required_arguments =        1      #: Number of required directive arguments: the pipeline file's path.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	# docutils declares 'option_spec' on 'Directive' and 'BaseDirective' assigns it, so mypy calls every
	# spelling of this override a conflict with one of them
	#: Mapping of option names to validator functions.
	option_spec: dict[str, Any] = {  # type: ignore[misc]
		"align":     align_spec,
		"alt":       strip,
		"caption":   strip,
		"depth":     directives.nonnegative_int,
		"direction": strip,
		"link":      stripAndNormalize,
		"name":      strip,
		"reduce":    stripAndNormalize,
	}

	def run(self) -> list[nodes.Node]:
		"""
		Read the pipeline file and hand its pipeline to :mod:`sphinx.ext.graphviz` for rendering.

		Every pipeline file drawn becomes a dependency of the document.

		:returns: A ``graphviz`` node, wrapped in a figure when a caption was given, or an error node when the options or
		          the pipeline files are wrong.
		"""
		relativePath, absolutePath = self.env.relfn2path(self.arguments[0])
		self.env.note_dependency(relativePath)
		path = Path(absolutePath)

		from pyTooling.GitLab.PipelineFile import IncludeResolver, PipelineFileError

		try:
			direction = self._ParseStringOption("direction", "LR", "(?i)(LR|TB)$").upper()
			reduce = self._ParseBooleanOption("reduce", True)
			link = self._ParseBooleanOption("link", True)
		except SphinxExtensionError as ex:
			return [self.state.document.reporter.error(str(ex), line=self.lineno)]

		domain = self.env.get_domain("glci")
		try:
			resolver = domain.Resolver if domain.Resolver is not None else IncludeResolver(path.parent)
			graph = PipelineDotGraph(
				domain.LoadPipelineFile(path), resolver, direction, self.options.get("depth", 0), reduce, link
			)
		except (OSError, ValueError, PipelineFileError) as ex:
			message = f"{self.directiveName}: Couldn't draw '{self.arguments[0]}': {ex}"
			for note in getattr(ex, "__notes__", []):
				message += f" {note}"

			return [self.state.document.reporter.error(message, line=self.lineno)]

		for pipelineFile in graph.Files[1:]:
			self.env.note_dependency(str(pipelineFile.Path))

		node = graphviz()
		node["code"] = str(graph)
		node["options"] = {"docname": self.env.docname}
		node["alt"] = self.options.get("alt", f"Pipeline of {path.name}")
		node["classes"] = [CSS_CLASS]
		if "align" in self.options:
			node["align"] = self.options["align"]

		if (caption := self.options.get("caption", None)) is not None:
			figure = figure_wrapper(self, node, caption)
			self.add_name(figure)
			return [figure]

		self.add_name(node)
		return [node]


@export
def resolveLinks(sphinx: Sphinx, doctree: nodes.document, docname: str) -> None:
	"""
	Call-back for Sphinx' ``doctree-resolved`` event, linking the trigger jobs of a pipeline graph to their child
	pipelines.

	A trigger job starting a child pipeline from a local file links to the page documenting that pipeline, as the
	``glci`` domain resolves the file's stem with ``ResolvePipeline``. Without a page for the pipeline, or in a format
	other than HTML, the job has no link.

	:param sphinx:  The Sphinx application.
	:param doctree: The resolved document.
	:param docname: Name of the document.
	"""
	if sphinx.builder.format != "html":
		for node in doctree.findall(graphviz):
			if CSS_CLASS in node["classes"]:
				node["code"] = LINK_MARKER.sub("", node["code"])

		return

	domain = sphinx.env.get_domain("glci")

	def link(match: Match[str]) -> str:
		"""
		Nested function returning the link attributes replacing a marker, or nothing.

		:param match: The marker.
		:returns:     The whitespace before the marker and the attributes ``URL`` and ``target``, or an empty string when
		              there is nothing to link to.
		"""
		if (target := domain.ResolvePipeline(match["name"])) is None:
			return ""

		targetDocname, anchor = target
		if (uri := sphinx.builder.get_relative_uri(docname, targetDocname)) == "":
			uri = PurePosixPath(sphinx.builder.get_target_uri(targetDocname)).name

		return f'{match["space"]}URL="{uri}#{anchor}" target="_top"'

	for node in doctree.findall(graphviz):
		if CSS_CLASS in node["classes"]:
			node["code"] = LINK_MARKER.sub(link, node["code"])

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
Directives of the ``glci`` domain summarizing the current pipeline file: its parameters, interface, dependencies and
YAML.

Each of them reads the pipeline file of the preceding ``glci:pipeline``:

.. code-block:: ReST

   .. glci:pipeline:: Package

   .. glci:parameter-table::
      :kinds: inputs

   .. glci:interface::

   .. glci:dependencies::

      * pip

   .. glci:yaml::
      :job: Package

   .. glci:autoinputs::

* ``glci:parameter-table`` - the summary tables of the inputs and variables;
* ``glci:interface`` - the contract with a pipeline including the file: the required inputs, the variables of the run
  form, the stages to declare, the jobs and hidden jobs it adds;
* ``glci:dependencies`` - the files included, the child and downstream pipelines triggered, the container images used,
  merged with hand-written ones;
* ``glci:yaml`` - the pipeline file or a part of it, as a code block linked to the file on GitLab;
* ``glci:autoinputs`` - an entry for every input the document has no ``glci:input`` for.

When a document was read, an input of its pipeline file without an entry is a ``glci.drift`` warning
(:func:`checkUndocumentedInputs`).

.. seealso::

   :mod:`pyTooling.GitLab.Sphinx`
      |rarr| The domain ``glci``, its pipelines and parameter entries.
"""
from __future__                      import annotations

from pathlib                         import Path
from typing                          import TYPE_CHECKING, Any, Callable, Optional as Nullable, TypeVar

from docutils                        import nodes
from docutils.parsers.rst            import directives
from sphinx                          import addnodes
from sphinx.application              import Sphinx
from sphinx.directives.code          import container_wrapper
from sphinx.transforms               import SphinxTransform
from sphinx.util.logging             import getLogger

from pyTooling.Decorators            import export
from pyTooling.Sphinx                import BaseDirective, SphinxExtensionError, strip
from pyTooling.GitLab.Sphinx         import NO_DEFAULT, WARNING_TYPE, InputDirective, formatValue

if TYPE_CHECKING:  # pragma: no cover
	from pyTooling.GitLab.PipelineFile import Include, PipelineFile, ValueT


__all__ = ["KINDS", "SECTIONS", "MAX_DEFAULT_LENGTH"]

KINDS = {
	"inputs":    ("Parameter Name", "Required", "Type", "Default"),
	"variables": ("Variable Name",  "Default",  "Description"),
}
"""
The kinds of parameters ``glci:parameter-table`` summarizes, in the order it shows them by default: kind |rarr| the
columns.
"""

SECTIONS = ("inputs", "variables", "stages", "include", "workflow", "default")
"""
The parts of a pipeline file ``glci:yaml`` shows by option ``:section:``: the inputs of the header's ``spec``, and
the top-level keys of the configuration.
"""

MAX_DEFAULT_LENGTH = 120
"""The length a default is shortened to in a summary table; a multi-line default is shortened to its first line."""

_logger = getLogger(__name__)

_ResultType = TypeVar("_ResultType")


@export
class PipelineReferenceDirective(BaseDirective):
	"""
	Base-class of the directives summarizing the current pipeline file, as set by the preceding ``glci:pipeline``.
	"""

	@staticmethod
	def _Reference(objectType: str, target: str, text: str) -> addnodes.pending_xref:
		"""
		Create a reference to an object of the domain, shown as literal text if the object isn't documented.

		:param objectType: The object type, as ``input``.
		:param target:     The object's name, as ``Package.package_name``.
		:param text:       The text of the reference.
		:returns:          The pending reference.
		"""
		return addnodes.pending_xref(
			"", nodes.literal(text, text), refdomain="glci", reftype=objectType, reftarget=target, refexplicit=True,
			refwarn=False
		)

	def _GitLabURL(self, path: Path, first: Nullable[int] = None, last: Nullable[int] = None) -> Nullable[str]:
		"""
		Return the URL of a file of the documented repository on GitLab, at the documented ref.

		:param path:  The file's path.
		:param first: Optional, the first line to mark. Default: ``None``.
		:param last:  Optional, the last line to mark. Default: ``None``.
		:returns:     The URL, or ``None`` if ``glci_project``, ``glci_ref`` or ``glci_repository_root`` isn't configured,
		              or the file isn't below the repository's root.
		"""
		project = self.config.glci_project
		ref = self.config.glci_ref
		if project is None or ref is None or (root := self.env.get_domain("glci").RepositoryRoot) is None:
			return None

		try:
			relative = path.resolve().relative_to(root).as_posix()
		except ValueError:
			return None

		url = f"{self.config.glci_server.rstrip('/')}/{project}/-/blob/{ref}/{relative}"
		if first is None:
			return url
		elif last is None or last == first:
			return f"{url}#L{first}"

		return f"{url}#L{first}-{last}"

	def _CurrentPipeline(self) -> Nullable[PipelineFile]:
		"""
		Return the model of the current pipeline file, and warn if there is no ``glci:pipeline`` before the directive.

		:returns: The pipeline file, or ``None`` if there is no ``glci:pipeline`` before the directive, or its file couldn't
		          be read - which the ``glci:pipeline`` directive reported already.
		"""
		if self.env.ref_context.get("glci:pipeline", None) is None:
			_logger.warning(
				f"{self.directiveName} is not preceded by a glci:pipeline.",
				location=self.get_location(), type=WARNING_TYPE, subtype="pipeline"
			)
			return None

		return self.env.get_domain("glci").GetCurrentPipeline()

	def _ResolveOrWarn(self, resolve: Callable[[], _ResultType], fallback: Callable[[], _ResultType]) -> _ResultType:
		"""
		Read a file a pipeline file includes or triggers, and report a file that is malformed as a warning.

		:param resolve:  The operation reading the file, as :meth:`IncludeResolver.Resolve
		                 <pyTooling.GitLab.PipelineFile.IncludeResolver.Resolve>`.
		:param fallback: The operation giving the result, when the file couldn't be read.
		:returns:        The result of ``resolve``, or of ``fallback`` after a warning.
		"""
		from pyTooling.GitLab.PipelineFile import PipelineFileError

		try:
			return resolve()
		except PipelineFileError as ex:
			_logger.warning(
				f"{self.directiveName}: {ex}", location=self.get_location(), type=WARNING_TYPE, subtype="pipeline"
			)
			return fallback()


@export
class ParameterTable(PipelineReferenceDirective):
	"""
	The directive ``glci:parameter-table``: summary tables of the current pipeline file's inputs and variables.

	.. code-block:: ReST

	   .. glci:parameter-table::
	      :kinds: inputs

	A table per kind, in the order ``:kinds:`` names them, by default the order of :data:`KINDS`. A table lists the
	parameters in file order, each name linked to its entry. An input's row states whether it is required, its type and
	its default; a variable's row its value and its description - a long or multi-line default is shortened, the entry
	shows it in full.

	Without ``:kinds:``, a table is shown for every kind the pipeline file has parameters of. A kind named explicitly, of
	which the file has none, is a table with a single row saying so.
	"""

	directiveName: str = "glci:parameter-table"  #: Name the directive is invoked by.

	has_content =               False  #: A boolean; ``True`` if content is allowed.
	required_arguments =        0      #: Number of required directive arguments.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	option_spec: dict[str, Any] = {  # type: ignore[misc]
		"kinds": strip,
	}  #: Mapping of option names to validator functions.

	def run(self) -> list[nodes.Node]:
		"""
		Create the summary tables.

		:returns: A table per kind, an error node if option ``:kinds:`` names an unknown kind, or nothing without a
		          current pipeline.
		"""
		try:
			kinds = self._ParseKinds()
		except SphinxExtensionError as ex:
			return [self.state.document.reporter.error(str(ex), line=self.lineno)]

		if (pipelineFile := self._CurrentPipeline()) is None:
			return []

		pipelineName = self.env.ref_context["glci:pipeline"]
		tables = []
		for kind in kinds:
			parameters = getattr(pipelineFile, kind.capitalize())
			if len(parameters) == 0 and "kinds" not in self.options:
				continue

			columns = KINDS[kind]
			tableGroup = self._CreateSingleRowTableHeader(
				columns=[(title, None) for title in columns],
				identifier=f"{pipelineName}-{kind}",
				classes=["glci-parameter-table", f"glci-{kind}"]
			)
			tableGroup += (tableBody := nodes.tbody())

			if len(parameters) == 0:
				entry = nodes.entry("", nodes.paragraph("", "", nodes.emphasis(text=f"No {kind}")), morecols=len(columns) - 1)
				tableBody += nodes.row("", entry)

			for name, parameter in parameters.items():
				row = nodes.row()
				row += nodes.entry("", nodes.paragraph("", "", self._Reference(kind[:-1], f"{pipelineName}.{name}", name)))
				if kind == "inputs":
					row += nodes.entry("", nodes.paragraph(text="yes" if parameter.Required else "no"))
					row += nodes.entry("", nodes.paragraph(text=parameter.Type.value))
					row += nodes.entry("", self._DefaultParagraph(parameter.Default))
				else:
					description = "" if parameter.Description is None else parameter.Description.strip()
					row += nodes.entry("", self._DefaultParagraph(parameter.Value))
					row += nodes.entry("", nodes.paragraph(description, description))

				tableBody += row

			tables.append(tableGroup.parent)

		return tables

	def _ParseKinds(self) -> tuple[str, ...]:
		"""
		Read option ``:kinds:``, a list of kinds separated by spaces or commas.

		:returns:                     The kinds named, in the order written and each once, or every kind of :data:`KINDS`
		                              without the option.
		:raises SphinxExtensionError: If a kind is not one of :data:`KINDS`.
		"""
		if "kinds" not in self.options:
			return tuple(KINDS)

		kinds = tuple(dict.fromkeys(self.options["kinds"].replace(",", " ").split()))
		for kind in kinds:
			if kind not in KINDS:
				raise SphinxExtensionError(f"{self.directiveName}::kinds: '{kind}' is not one of {', '.join(KINDS)}.")

		return kinds

	@staticmethod
	def _DefaultParagraph(value: ValueT) -> nodes.paragraph:
		"""
		Create the paragraph of a table cell showing a default.

		A multi-line string is shortened to its first line, and a longer text to :data:`MAX_DEFAULT_LENGTH` characters,
		each followed by ``…``.

		:param value: The default, as :attr:`Input.Default <pyTooling.GitLab.PipelineFile.Input.Default>`.
		:returns:     The paragraph, holding :data:`~pyTooling.GitLab.Sphinx.NO_DEFAULT` for ``None``, or the default as
		              literal text.
		"""
		if value is None:
			return nodes.paragraph(NO_DEFAULT, NO_DEFAULT)

		if isinstance(value, str):
			lines = value.splitlines()
			first = lines[0] if len(lines) > 0 else ""
			if len(lines) > 1 or len(first) > MAX_DEFAULT_LENGTH:
				value = f"{first[:MAX_DEFAULT_LENGTH]}…"

		text = formatValue(value)
		return nodes.paragraph("", "", nodes.literal(text, text))


@export
class Interface(PipelineReferenceDirective):
	"""
	The directive ``glci:interface``: the contract of the current pipeline file with a pipeline including it, as a field
	list.

	.. code-block:: ReST

	   .. glci:interface::

	* *Required Inputs* - the inputs without a default, which ``include:inputs`` has to set, each linked to its entry.
	* *Variables* - the default variables with a ``description``, which the form running a pipeline by hand prefills.
	* *Stages* - the stages the file's jobs run in, which the including pipeline has to declare, in the file's order; a
	  stage given by an input, as ``$[[ inputs.stage ]]``, as written.
	* *Jobs* and *Hidden Jobs* - the jobs the file adds to a pipeline, and the hidden jobs others may ``extends``.

	The files the pipeline file includes are listed by :class:`Dependencies`.
	"""

	directiveName: str = "glci:interface"  #: Name the directive is invoked by.

	has_content =               False  #: A boolean; ``True`` if content is allowed.
	required_arguments =        0      #: Number of required directive arguments.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	option_spec: dict[str, Any] = {}   #: Mapping of option names to validator functions.

	def run(self) -> list[nodes.Node]:
		"""
		Create the field list.

		:returns: The field list, or nothing without a current pipeline.
		"""
		if (pipelineFile := self._CurrentPipeline()) is None:
			return []

		pipelineName = self.env.ref_context["glci:pipeline"]

		fieldList = nodes.field_list(classes=["glci-interface"])
		fieldList += self._Field("Required Inputs", [
			[self._Reference("input", f"{pipelineName}.{name}", name)]
			for name, parameter in pipelineFile.Inputs.items() if parameter.Required
		])
		fieldList += self._Field("Variables", [
			[self._Reference("variable", f"{pipelineName}.{name}", name)]
			for name, variable in pipelineFile.Variables.items() if variable.Description is not None
		])
		used = dict.fromkeys(job.Stage for job in pipelineFile.IterateJobs())
		stages = [stage for stage in pipelineFile.Stages if stage in used]
		stages.extend(stage for stage in used if stage not in pipelineFile.Stages)
		fieldList += self._Field("Stages", [[nodes.literal(stage, stage)] for stage in stages])
		fieldList += self._Field("Jobs", [[nodes.literal(name, name)] for name in pipelineFile.Jobs])
		fieldList += self._Field("Hidden Jobs", [[nodes.literal(name, name)] for name in pipelineFile.HiddenJobs])

		return [fieldList]

	@staticmethod
	def _Field(name: str, items: list[list[nodes.Node]]) -> nodes.field:
		"""
		Create a field listing items separated by commas, or saying *none*.

		:param name:  The field's name.
		:param items: The items, each as the nodes of an item.
		:returns:     The field.
		"""
		if len(items) == 0:
			body = nodes.paragraph("", "", nodes.emphasis(text="none"))
		else:
			body = nodes.paragraph()
			for index, item in enumerate(items):
				if index > 0:
					body += nodes.Text(", ")
				body.extend(item)

		return nodes.field("", nodes.field_name(text=name), nodes.field_body("", body))


@export
class Dependencies(PipelineReferenceDirective):
	"""
	The directive ``glci:dependencies``: what the current pipeline file uses, as a nested bullet list.

	.. code-block:: ReST

	   .. glci:dependencies::

	      * /ci/build.yml

	        * Python packages given by :glci:input:`Build.requirements`.

	From the pipeline file, and the local files it includes and triggers, as far as they are known locally:

	* the files ``include`` adds - a local file, another project's files, a URL, a template, a component, a job's
	  artifact -, each once; a local file read from ``glci_repository_root`` with its own dependencies;
	* the child pipelines a trigger job runs, with the files of the child pipeline, and the other projects' pipelines a
	  trigger job starts;
	* the images of the containers and service containers the jobs run in, ``default`` included.

	The content is a bullet list of what a file can't tell, like packages installed by a script. It is merged into the
	derived list: an item whose text is the name of a derived item - an include as written, a trigger job as
	``trigger <job>``, a container as ``image`` or ``service``, or the image - adds its nested list to that item,
	recursively. Any other item is appended to the list it is in. Content after the bullet list follows the list.
	"""

	directiveName: str = "glci:dependencies"  #: Name the directive is invoked by.

	has_content =               True   #: The hand-written dependencies.
	required_arguments =        0      #: Number of required directive arguments.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	option_spec: dict[str, Any] = {}   #: Mapping of option names to validator functions.

	_keys: dict[int, set[str]]  #: Names of each derived item, by the item's identity.

	def run(self) -> list[nodes.Node]:
		"""
		Create the list: the derived dependencies, merged with the hand-written ones.

		:returns: The list and the content following it, a paragraph saying *none* if there are no dependencies, or
		          nothing without a current pipeline.
		"""
		if (pipelineFile := self._CurrentPipeline()) is None:
			return []

		self._keys = {}
		dependencies = self._FileItems(pipelineFile, {pipelineFile.Path.resolve()})
		dependencies["classes"].append("glci-dependencies")

		others = []
		for node in self.parse_content_to_nodes():
			if isinstance(node, nodes.bullet_list):
				self._Merge(dependencies, node)
			else:
				others.append(node)

		if len(dependencies) == 0:
			return [nodes.paragraph("", "", nodes.emphasis(text="none")), *others]

		return [dependencies, *others]

	def _Item(self, paragraph: nodes.paragraph, keys: set[str]) -> nodes.list_item:
		"""
		Create a derived item, known by the names a hand-written item may refer to it by.

		:param paragraph: The item's text.
		:param keys:      The names of the item.
		:returns:         The item.
		"""
		item = nodes.list_item("", paragraph)
		self._keys[id(item)] = keys

		return item

	def _IncludeItem(self, include: Include) -> nodes.list_item:
		"""
		Create the item of an include.

		A local file links to GitLab, if ``glci_project`` and ``glci_ref`` are configured; another project's files link
		to that project, a URL to itself, a component to its project.

		:param include: The include.
		:returns:       The item, known by the include as written.
		"""
		from pyTooling.GitLab.PipelineFile import IncludeKind

		text = include.Location
		literal = nodes.literal(text, text)
		paragraph = nodes.paragraph("", f"{include.Kind.value} ")
		server = self.config.glci_server.rstrip("/")
		url = None
		if include.Kind is IncludeKind.Local and (root := self.env.get_domain("glci").RepositoryRoot) is not None:
			url = self._GitLabURL(root / text.lstrip("/"))
		elif include.Kind is IncludeKind.Project:
			url = f"{server}/{text}"
		elif include.Kind is IncludeKind.Remote:
			url = text
		elif include.Kind is IncludeKind.Component and "/" in (path := text.partition("@")[0]):
			url = f"{server}/{path.partition('/')[2].rpartition('/')[0]}"

		paragraph += literal if url is None else nodes.reference(text, "", literal, refuri=url)
		if len(include.Files) > 0:
			paragraph += nodes.Text(f": {', '.join(include.Files)}")

		return self._Item(paragraph, {text, text.partition("@")[0], *include.Files})

	def _ImageItem(self, kind: str, image: str) -> nodes.list_item:
		"""
		Create the item of a container's image.

		:param kind:  The kind of container, as ``image`` or ``service``.
		:param image: The image, as written.
		:returns:     The item, known by the kind and the image.
		"""
		return self._Item(nodes.paragraph("", f"{kind} ", nodes.literal(image, image)), {kind, image})

	def _FileItems(self, pipelineFile: PipelineFile, visited: set[Path]) -> nodes.bullet_list:
		"""
		List a pipeline file's dependencies: its includes, the pipelines its trigger jobs start, and container images.

		:param pipelineFile: The pipeline file.
		:param visited:      The resolved paths of the files on the path to this one, which aren't expanded again.
		:returns:            A bullet list, empty if the file uses nothing.
		"""
		resolver = self.env.get_domain("glci").Resolver
		bulletList = nodes.bullet_list()
		for include in {(include.Kind, include.Location): include for include in pipelineFile.Includes}.values():
			bulletList += self._ResolvedItem(include, resolver, visited)

		for job in pipelineFile.IterateJobs():
			if (trigger := job.Trigger) is None:
				continue

			paragraph = nodes.paragraph("", "trigger ", nodes.emphasis(text=job.Name))
			if trigger.Project is not None:
				paragraph += (nodes.Text(" - project "), nodes.literal(trigger.Project, trigger.Project))

			item = self._Item(paragraph, {f"trigger {job.Name}", job.Name})
			if len(childIncludes := trigger.Includes) > 0:
				item += nodes.bullet_list("", *(self._ResolvedItem(include, resolver, visited) for include in childIncludes))

			bulletList += item

		images: dict[tuple[str, str], None] = {}
		if (default := pipelineFile.Default) is not None:
			if default.Image is not None:
				images[("image", default.Image)] = None
			images.update(dict.fromkeys(("service", service) for service in default.Services))

		for job in pipelineFile.IterateJobs():
			if job.Image is not None:
				images[("image", job.Image)] = None
			images.update(dict.fromkeys(("service", service) for service in job.Services))

		bulletList.extend(self._ImageItem(kind, image) for kind, image in images)

		return bulletList

	def _ResolvedItem(self, include: Include, resolver: Any, visited: set[Path]) -> nodes.list_item:
		"""
		Create the item of an include, with the dependencies of the local file it names, if that is readable.

		:param include:  The include.
		:param resolver: The domain's resolver, or ``None`` if ``glci_repository_root`` isn't configured.
		:param visited:  The resolved paths of the files on the path, which aren't expanded again.
		:returns:        The item.
		"""
		item = self._IncludeItem(include)
		if resolver is None:
			return item

		included = self._ResolveOrWarn(lambda: resolver.Resolve(include), lambda: None)
		if included is not None and (path := included.Path.resolve()) not in visited:
			if len(nested := self._FileItems(included, visited | {path})) > 0:
				item += nested

		return item

	def _Merge(self, derived: nodes.bullet_list, handwritten: nodes.bullet_list) -> None:
		"""
		Merge a hand-written list into a derived one.

		A hand-written item whose text is a name of a derived item of this list adds its nested lists to that item,
		merged recursively; any other item is appended.

		:param derived:     The derived list.
		:param handwritten: The hand-written list.
		"""
		for item in list(handwritten.children):
			text = item[0].astext().strip() if len(item) > 0 and isinstance(item[0], nodes.paragraph) else None
			match = next(
				(child for child in derived.children if text is not None and text in self._keys.get(id(child), ())), None
			)
			if match is None:
				derived += item
				continue

			for node in item.children[1:]:
				nested = next((child for child in match.children if isinstance(child, nodes.bullet_list)), None)
				if isinstance(node, nodes.bullet_list) and nested is not None:
					self._Merge(nested, node)
				else:
					match += node


@export
class YAMLExcerpt(PipelineReferenceDirective):
	"""
	The directive ``glci:yaml``: the current pipeline file or a part of it, as a YAML code block.

	.. code-block:: ReST

	   .. glci:yaml::
	      :section: inputs

	Option ``:section:`` selects one of :data:`SECTIONS` - the ``inputs`` of the header's ``spec``, or a top-level key of
	the configuration; option ``:job:`` selects one job. Without either, the whole file is shown.

	The lines are numbered as in the file, and the part is shifted left by the indentation of its first line. The caption
	names the file and the lines, and links to them on GitLab at ``glci_ref``, if ``glci_project``, ``glci_ref`` and
	``glci_repository_root`` are configured.
	"""

	directiveName: str = "glci:yaml"  #: Name the directive is invoked by.

	has_content =               False  #: A boolean; ``True`` if content is allowed.
	required_arguments =        0      #: Number of required directive arguments.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	option_spec: dict[str, Any] = {  # type: ignore[misc]
		"caption": directives.unchanged_required,
		"job":     strip,
		"name":    strip,
		"section": strip,
	}  #: Mapping of option names to validator functions.

	def run(self) -> list[nodes.Node]:
		"""
		Create the code block.

		:returns: The code block in a captioned container, an error node for wrong options, or nothing without a current
		          pipeline or when the part doesn't exist.
		"""
		if "section" in self.options and "job" in self.options:
			return [self.state.document.reporter.error(
				f"{self.directiveName}: Options ':section:' and ':job:' exclude each other.", line=self.lineno
			)]
		elif (section := self.options.get("section", None)) is not None and section not in SECTIONS:
			return [self.state.document.reporter.error(
				f"{self.directiveName}::section: '{section}' is not one of {', '.join(SECTIONS)}.", line=self.lineno
			)]

		if (pipelineFile := self._CurrentPipeline()) is None:
			return []

		pipelineName = self.env.ref_context["glci:pipeline"]
		lines = pipelineFile.Path.read_text(encoding="utf-8").splitlines()
		if section is not None:
			if (line := self._SectionLine(pipelineFile, lines, section)) is None:
				_logger.warning(
					f"{self.directiveName}: Pipeline '{pipelineName}' has no {section}.",
					location=self.get_location(), type=WARNING_TYPE, subtype="drift"
				)
				return []

			first, last = self._BlockOf(lines, line)
		elif (jobName := self.options.get("job", None)) is not None:
			job = pipelineFile.Jobs.get(jobName, None) or pipelineFile.HiddenJobs.get(jobName, None)
			if job is None:
				_logger.warning(
					f"{self.directiveName}: Pipeline '{pipelineName}' has no job '{jobName}'.",
					location=self.get_location(), type=WARNING_TYPE, subtype="drift"
				)
				return []

			first, last = self._BlockOf(lines, job.Line)
		else:
			first = 1
			last = len(lines)

		indentation = self._Indentation(lines[first - 1])
		excerpt = [line[min(indentation, self._Indentation(line)):] for line in lines[first - 1:last]]

		text = "\n".join(excerpt)
		literal = nodes.literal_block(text, text, language="yaml", linenos=True)
		literal["highlight_args"] = {"linenostart": first}
		self.set_source_info(literal)

		if (caption := self.options.get("caption", None)) is None:
			fileName = pipelineFile.Path.name
			if first == 1 and last == len(lines):
				caption = fileName
				url = self._GitLabURL(pipelineFile.Path)
			else:
				caption = f"{fileName}, lines {first}-{last}"
				url = self._GitLabURL(pipelineFile.Path, first, last)

			if url is not None:
				caption = f"`{caption} <{url}>`__"

		container = container_wrapper(self, literal, caption)
		self.add_name(container)

		return [container]

	@classmethod
	def _SectionLine(cls, pipelineFile: PipelineFile, lines: list[str], section: str) -> Nullable[int]:
		"""
		Return the line of a section's key.

		The inputs' key is the key holding the first input. A top-level key is searched in the configuration document,
		behind the header document's ``---``, if there is one.

		:param pipelineFile: The pipeline file.
		:param lines:        The lines of the file.
		:param section:      One of :data:`SECTIONS`.
		:returns:            The key's line, starting at 1, or ``None`` if the file hasn't the section.
		"""
		if section == "inputs":
			if len(pipelineFile.Inputs) == 0:
				return None

			return cls._ParentOf(lines, next(iter(pipelineFile.Inputs.values())).Line)

		start = 0
		if len(pipelineFile.Inputs) > 0 or pipelineFile.Description is not None:
			start = next((index + 1 for index, line in enumerate(lines) if line.rstrip() == "---"), 0)

		for index in range(start, len(lines)):
			if lines[index].startswith(f"{section}:"):
				return index + 1

		return None

	@staticmethod
	def _Indentation(line: str) -> int:
		"""
		Return the indentation of a line of a YAML file.

		:param line: The line.
		:returns:    The number of spaces the line starts with.
		"""
		return len(line) - len(line.lstrip(" "))

	@staticmethod
	def _IsBlank(line: str) -> bool:
		"""
		Return whether a line is empty or a comment.

		:param line: The line.
		:returns:    ``True``, if the line holds nothing but whitespace or a comment.
		"""
		stripped = line.strip()
		return stripped == "" or stripped.startswith("#")

	@classmethod
	def _ParentOf(cls, lines: list[str], line: int) -> int:
		"""
		Return the line of the key a line is nested in.

		:param lines: The lines of the file.
		:param line:  The nested line, starting at 1.
		:returns:     The nearest line above it that is indented less, starting at 1, or ``1``.
		"""
		indentation = cls._Indentation(lines[line - 1])
		for index in range(line - 2, -1, -1):
			text = lines[index]
			if not cls._IsBlank(text) and cls._Indentation(text) < indentation:
				return index + 1

		return 1

	@classmethod
	def _BlockOf(cls, lines: list[str], line: int) -> tuple[int, int]:
		"""
		Return the lines of a key and its value.

		The block ends before the next line - not empty and not a comment - indented as much as the key or less. A comment
		indented as much as the key or less, and empty lines, at the end aren't part of it.

		:param lines: The lines of the file.
		:param line:  The key's line, starting at 1.
		:returns:     The first and the last line of the block, starting at 1.
		"""
		indentation = cls._Indentation(lines[line - 1])
		last = line
		for index in range(line, len(lines)):
			text = lines[index]
			if text.strip() == "":
				continue
			elif cls._Indentation(text) > indentation:
				last = index + 1
			elif not cls._IsBlank(text):
				break

		return line, last


@export
class AutoInputs(PipelineReferenceDirective):
	"""
	The directive ``glci:autoinputs``: an entry for every input of the current pipeline file the document has no
	``glci:input`` for.

	.. code-block:: ReST

	   .. glci:autoinputs::

	An entry is created as a ``glci:input`` without content creates it: the facts of the pipeline file and its
	*Description*. Inputs documented by a ``glci:input`` later in the document are left out, too - the entries are
	created by :class:`AutoInputsTransform` when the whole document was parsed.
	"""

	directiveName: str = "glci:autoinputs"  #: Name the directive is invoked by.

	has_content =               False  #: A boolean; ``True`` if content is allowed.
	required_arguments =        0      #: Number of required directive arguments.
	optional_arguments =        0      #: Number of optional arguments after the required ones.
	final_argument_whitespace = False  #: A boolean; ``True`` if the last argument may contain spaces.
	option_spec: dict[str, Any] = {}   #: Mapping of option names to validator functions.

	def run(self) -> list[nodes.Node]:
		"""
		Create a placeholder, replaced by the entries once the document was parsed.

		:returns: The placeholder, or nothing without a current pipeline.
		"""
		if (pipelineFile := self._CurrentPipeline()) is None:
			return []

		details = {"pipeline": self.env.ref_context["glci:pipeline"], "path": pipelineFile.Path}
		pending = nodes.pending(AutoInputsTransform, details)
		self.set_source_info(pending)
		self.state.document.note_pending(pending)

		return [pending]


@export
class AutoInputsTransform(SphinxTransform):
	"""
	Replaces the placeholder of a ``glci:autoinputs`` by an entry for every input of its pipeline file the document has
	no ``glci:input`` for.

	It runs after the document was parsed - so every ``glci:input`` has registered its entry - and before the entries are
	collected for the table of contents and the index.
	"""

	default_priority = 400  #: Priority among the transforms: before the local table of contents and the smart quotes.

	def apply(self, **kwargs: Any) -> None:
		"""
		Replace the placeholder by the entries.

		:param kwargs: Unused.
		"""
		pending: nodes.pending = self.startnode
		pipelineName = pending.details["pipeline"]
		domain = self.env.get_domain("glci")
		pipelineFile = domain.LoadPipelineFile(pending.details["path"])

		entries = []
		for name, parameter in pipelineFile.Inputs.items():
			if domain.Objects.get(("input", f"{pipelineName}.{name}"), ("", ""))[0] != self.env.docname:
				entries.extend(InputDirective.CreateEntry(
					self.env, self.document, pipelineName, name, parameter, [], [], pending.source, pending.line
				))

		pending.replace_self(entries)


@export
def checkUndocumentedInputs(sphinx: Sphinx, doctree: nodes.document) -> None:
	"""
	Call-back for Sphinx' ``doctree-read`` event, warning about inputs the document has no entry for.

	Every input of a pipeline file the document names by ``glci:pipeline`` needs an entry in the document, by a
	``glci:input`` or a ``glci:autoinputs``; one without is a warning of type ``glci.drift`` at the ``glci:pipeline``.

	:param sphinx:  The Sphinx application.
	:param doctree: The document read.
	"""
	if (pipelines := sphinx.env.current_document.get("glci:pipelines", None)) is None:
		return

	domain = sphinx.env.get_domain("glci")
	for pipelineName, path, location in pipelines:
		for name in domain.LoadPipelineFile(path).Inputs:
			if domain.Objects.get(("input", f"{pipelineName}.{name}"), ("", ""))[0] != sphinx.env.docname:
				_logger.warning(
					f"Input '{name}' of pipeline '{pipelineName}' has no entry: add a glci:input or a glci:autoinputs.",
					location=location, type=WARNING_TYPE, subtype="drift"
				)

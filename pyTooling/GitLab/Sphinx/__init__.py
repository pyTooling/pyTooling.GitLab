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
A Sphinx domain ``glci`` documenting GitLab CI/CD pipeline files from their YAML files.

The facts of a pipeline file's parameters - an input's type, whether it is required, its default, its options - are
read from the file by :mod:`pyTooling.GitLab.PipelineFile`, so a page states them without copying them. What the file
can't say stays hand-written, as the content of a directive:

.. code-block:: rst

   .. glci:pipeline:: Package
      :file: ../templates/Package/template.yml

   Package
   #######

   .. glci:input:: package_name

      :Example: ``myPackage``

.. rubric:: What it registers

* Directives

  * ``glci:pipeline``
  * ``glci:input``
  * ``glci:variable``

* Roles

  * ``:glci:pipeline:``
  * ``:glci:input:``
  * ``:glci:variable:``

* Configuration values, as listed in :attr:`GitLabCIDomain.configValues`

  * ``glci_server``
  * ``glci_project``
  * ``glci_repository_root``
  * ``glci_pipeline_directory``
  * ``glci_ref``
  * ``glci_label_prefix``

The pipeline files are read with ``ruamel.yaml`` when a directive runs, not when this module is imported.

.. seealso::

   :mod:`pyTooling.GitLab.PipelineFile`
      |rarr| The model of a pipeline file the domain reads.
   :mod:`pyTooling.GitLab.Sphinx.Graph`
      |rarr| The ``glci:pipeline-graph`` directive, drawing a pipeline file's jobs and their dependencies.
   :mod:`pyTooling.GitLab.Sphinx.Reference`
      |rarr| The directives summarizing a pipeline file: its parameters, its interface, its dependencies, its YAML.
"""
from __future__                      import annotations

from pathlib                         import Path
from typing                          import TYPE_CHECKING, Any, ClassVar, Iterable, Optional as Nullable, Union

from docutils                        import nodes
from docutils.nodes                  import Element, Node, fully_normalize_name
from docutils.parsers.rst            import directives
from sphinx                          import addnodes
from sphinx.application              import Sphinx
from sphinx.builders                 import Builder
from sphinx.domains                  import Domain, ObjType
from sphinx.environment              import BuildEnvironment
from sphinx.roles                    import XRefRole
from sphinx.util.logging             import getLogger
from sphinx.util.nodes               import make_id, make_refnode

from pyTooling.Common                import getFullyQualifiedName
from pyTooling.Decorators            import export, readonly
from pyTooling.Sphinx                import BaseDirective

if TYPE_CHECKING:  # pragma: no cover
	from pyTooling.GitLab.PipelineFile import IncludeResolver, Input, PipelineFile, ValueT, Variable


__all__ = ["NO_DEFAULT", "WARNING_TYPE", "LEADING_FIELDS", "FILE_SUFFIXES"]

#: The text of the field *Default Value* when a parameter has no default.
NO_DEFAULT = "— — — —"

#: The type of the warnings this domain emits; the drift warnings have the subtype ``drift``, so
#: ``suppress_warnings = ["glci.drift"]`` silences them.
WARNING_TYPE = "glci"

#: The fields a *Description* taken from the pipeline file follows.
LEADING_FIELDS = ("Type", "Required", "Default Value", "Possible Values", "Pattern")

#: The file names a ``glci:pipeline`` without ``:file:`` tries in ``glci_pipeline_directory``, in this order; ``{name}``
#: is the pipeline's name. The last is a CI/CD component's layout.
FILE_SUFFIXES = ("{name}.yml", "{name}.yaml", "{name}/template.yml", "{name}/template.yaml")

_logger = getLogger(__name__)


@export
def formatValue(value: ValueT) -> str:
	"""
	Format a value read from a pipeline file the way the file writes it.

	A string is quoted as YAML quotes it - ``'3.14'`` -, a boolean is ``true`` or ``false``, a number is written as it is,
	and a list is written in YAML's flow style - ``['a', 'b']``.

	:param value: The value, as :attr:`Input.Default <pyTooling.GitLab.PipelineFile.Input.Default>`.
	:returns:     The value as text, or :data:`NO_DEFAULT` for ``None``.
	"""
	if value is None:
		return NO_DEFAULT
	elif isinstance(value, bool):
		return "true" if value else "false"
	elif isinstance(value, str):
		escaped = value.replace("'", "''")
		return f"'{escaped}'"
	elif isinstance(value, list):
		return f"[{', '.join(formatValue(item) for item in value)}]"
	elif isinstance(value, dict):
		return f"{{{', '.join(f'{key}: {formatValue(item)}' for key, item in value.items())}}}"

	return str(value)


@export
class PipelineDirective(BaseDirective):
	"""
	The directive ``glci:pipeline``: a pipeline file's target, its index entry, and the current pipeline of the document.

	.. code-block:: rst

	   .. glci:pipeline:: Package
	      :file: ../templates/Package/template.yml

	The argument is the pipeline's name. Without ``:file:``, the file is looked up in ``glci_pipeline_directory`` by the
	names of :data:`FILE_SUFFIXES`. Every ``glci:input`` and ``glci:variable`` following it in the document belongs to
	this pipeline.

	The directive writes no visible output. Placed above a page's title, its target is the title, as a label is.
	"""

	directiveName: str = "glci:pipeline"  #: Name the directive is invoked by.

	has_content =        False                                    #: The directive has no content.
	required_arguments = 1                                        #: The pipeline's name.
	option_spec =        {"file": directives.unchanged_required}  #: Path to the pipeline file, relative to the document.

	def run(self) -> list[Node]:
		"""
		Register the pipeline, read its file, and make it the current pipeline.

		:returns: An index node and the pipeline's target.
		"""
		name = self.arguments[0].strip()
		domain: GitLabCIDomain = self.env.get_domain("glci")

		path = None
		if "file" in self.options:
			path = Path(self.env.relfn2path(self.options["file"], self.env.docname)[1])
		elif (directory := domain.PipelineDirectory) is not None:
			candidates = [directory / suffix.format(name=name) for suffix in FILE_SUFFIXES]
			path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])

		if path is None:
			_logger.warning(
				f"{self.directiveName} '{name}' has no file: give option ':file:' or set 'glci_pipeline_directory'.",
				location=self.get_location(), type=WARNING_TYPE, subtype="pipeline"
			)
		elif not path.exists():
			_logger.warning(
				f"{self.directiveName} '{name}': file '{path}' doesn't exist.",
				location=self.get_location(), type=WARNING_TYPE, subtype="pipeline"
			)
		else:
			self.env.note_dependency(str(path))
			self._Load(domain, name, path)

		self.env.ref_context["glci:pipeline"] = name

		nodeID = make_id(self.env, self.state.document, "glci-pipeline", name)
		target = nodes.target("", "", ids=[nodeID])
		if (prefix := self.config.glci_label_prefix) is not None:
			label = f"{prefix}/{name}"
			target["ids"].append(nodes.make_id(label))
			target["names"].append(fully_normalize_name(label))

		self.set_source_info(target)
		self.state.document.note_explicit_target(target)
		domain.NoteObject("pipeline", name, nodeID, target)

		return [addnodes.index(entries=[("single", f"GitLab CI/CD pipeline; {name}", nodeID, "", None)]), target]

	def _Load(self, domain: GitLabCIDomain, name: str, path: Path) -> None:
		"""
		Read the pipeline file and make it the current one.

		A file that isn't a well-formed configuration is reported as a warning at the place in the file, and the document
		has no current pipeline model then. A pipeline read is added to the document's list ``glci:pipelines`` of (name,
		path, location of the directive), which is checked when the document was read.

		:param domain: The domain.
		:param name:   The pipeline's name, as given as argument.
		:param path:   Path to the pipeline file.
		"""
		from pyTooling.GitLab.PipelineFile import PipelineFileError

		try:
			domain.LoadPipelineFile(path)
		except PipelineFileError as ex:
			if ex.Path is None:
				location = self.get_location()
			elif ex.Line is None:
				location = str(ex.Path)
			else:
				location = f"{ex.Path}:{ex.Line}"

			_logger.warning(f"{self.directiveName} '{name}': {ex}", location=location, type=WARNING_TYPE, subtype="pipeline")
			return

		self.env.current_document["glci:pipeline-file"] = path
		self.env.current_document.setdefault("glci:pipelines", []).append((name, path, self.get_location()))


@export
class ParameterDirective(BaseDirective):
	"""
	Base-class of the directives documenting one parameter of the current pipeline.

	The entry is a section titled by the parameter's name, holding a field list: first the fields read from the pipeline
	file (:meth:`_FactFields`), then the fields of the directive's content, in the order written. Without a hand-written
	*Description*, the pipeline file's ``description`` is used, placed behind the :data:`LEADING_FIELDS`. Content after
	the field list follows it.

	A hand-written field repeating a fact of the file is a warning, and the file's value is shown.

	Besides its anchor ``glci-<type>-<Pipeline>.<name>``, the section carries the anchor of its label and - unless the
	document uses it already - the anchor docutils derives from a title, as a hand-written section has.
	"""

	OBJECT_TYPE: ClassVar[str]              #: The domain's object type, as ``input``.
	LABEL_KIND:  ClassVar[str]              #: The kind in a label, as ``Input`` in ``PIPELINE/Package/Input/name``.
	COLLECTION:  ClassVar[str]              #: The pipeline file's property holding the parameters, as ``Inputs``.
	FACT_FIELDS: ClassVar[tuple[str, ...]]  #: The fields the pipeline file may state.

	has_content =        True  #: The hand-written fields and text.
	required_arguments = 1     #: The parameter's name.

	def run(self) -> list[Node]:
		"""
		Create the parameter's entry and register it.

		:returns: An index node and the entry's section, or nothing outside a ``glci:pipeline``.
		"""
		name = self.arguments[0].strip()
		if (pipelineName := self.env.ref_context.get("glci:pipeline", None)) is None:
			_logger.warning(
				f"{self.directiveName} '{name}' is not preceded by a glci:pipeline.",
				location=self.get_location(), type=WARNING_TYPE, subtype="pipeline"
			)
			return []

		domain: GitLabCIDomain = self.env.get_domain("glci")
		parameter = None
		if (pipelineFile := domain.GetCurrentPipeline()) is not None:
			if (parameter := getattr(pipelineFile, self.COLLECTION).get(name, None)) is None:
				_logger.warning(
					f"Pipeline '{pipelineName}' has no {self.OBJECT_TYPE} '{name}' ({pipelineFile.Path.name}).",
					location=self.get_location(), type=WARNING_TYPE, subtype="drift"
				)

		facts = self.FACT_FIELDS if parameter is None else [field[0].astext() for field in self._FactFields(parameter)]

		content = self.parse_content_to_nodes()
		handwritten = []
		if len(content) > 0 and isinstance(content[0], nodes.field_list):
			handwritten = list(content[0].children)
			content = content[1:]

		fields = []
		for field in handwritten:
			fieldName = field[0].astext().strip()
			if fieldName in facts:
				_logger.warning(
					f"{self.directiveName} '{pipelineName}.{name}': field '{fieldName}' is taken from the pipeline file; "
					"remove it.",
					location=field, type=WARNING_TYPE, subtype="drift"
				)
				if parameter is not None:
					continue

			fields.append(field)

		source, line = self.get_source_info()
		return self.CreateEntry(self.env, self.state.document, pipelineName, name, parameter, fields, content, source, line)

	@classmethod
	def CreateEntry(
		cls,
		env:          BuildEnvironment,
		document:     nodes.document,
		pipelineName: str,
		name:         str,
		parameter:    Nullable[Union[Input, Variable]],
		fields:       list[nodes.field],
		content:      list[Node],
		source:       str,
		line:         Nullable[int]
	) -> list[Node]:
		"""
		Create a parameter's entry and register it in the domain.

		:param env:          The build environment.
		:param document:     The document the entry is placed in.
		:param pipelineName: The pipeline's name.
		:param name:         The parameter's name.
		:param parameter:    The parameter, as read from the pipeline file, or ``None`` if the pipeline file wasn't read or
		                     hasn't this parameter.
		:param fields:       The hand-written fields, without those repeating a fact of the pipeline file.
		:param content:      The nodes following the field list.
		:param source:       The source file the entry is reported at.
		:param line:         The line the entry is reported at, or ``None``.
		:returns:            An index node and the entry's section.
		"""
		fullName = f"{pipelineName}.{name}"
		nodeID = make_id(env, document, f"glci-{cls.OBJECT_TYPE}", fullName)
		section = nodes.section("", nodes.title(name, name), ids=[nodeID])
		if (titleID := nodes.make_id(name)) not in document.ids:
			section["ids"].append(titleID)

		# The label's anchor comes last: docutils links a name to a node's last anchor, so a link keeps its target.
		if (prefix := env.config.glci_label_prefix) is not None:
			label = f"{prefix}/{pipelineName}/{cls.LABEL_KIND}/{name}"
			section["ids"].append(nodes.make_id(label))
			section["names"].append(fully_normalize_name(label))

		section.source = source
		section.line = line
		document.note_explicit_target(section)

		if parameter is not None:
			fields = [*cls._FactFields(parameter), *fields]

		fieldNames = [field[0].astext().strip() for field in fields]
		if "Description" not in fieldNames and parameter is not None and parameter.Description:
			leading = [index + 1 for index, fieldName in enumerate(fieldNames) if fieldName in LEADING_FIELDS]
			position = max(leading, default=0)
			fields.insert(position, cls._TextField("Description", parameter.Description.strip()))

		if len(fields) > 0:
			section += nodes.field_list("", *fields)
		section.extend(content)

		domain: GitLabCIDomain = env.get_domain("glci")
		domain.NoteObject(cls.OBJECT_TYPE, fullName, nodeID, section)
		return [
			addnodes.index(entries=[("single", f"{name} ({cls.OBJECT_TYPE} of {pipelineName})", nodeID, "", None)]),
			section
		]

	@staticmethod
	def _Field(name: str, *body: Node) -> nodes.field:
		"""
		Create a field of a field list.

		:param name: Name of the field, as ``Type``.
		:param body: The nodes of the field's body.
		:returns:    The field.
		"""
		return nodes.field("", nodes.field_name(name, name), nodes.field_body("", *body))

	@classmethod
	def _TextField(cls, name: str, text: str) -> nodes.field:
		"""
		Create a field of a field list, whose body is a line of text.

		:param name: Name of the field, as ``Required``.
		:param text: Text of the field's body.
		:returns:    The field.
		"""
		return cls._Field(name, nodes.paragraph(text, text))

	@classmethod
	def _LiteralField(cls, name: str, texts: Iterable[str]) -> nodes.field:
		"""
		Create a field of a field list, whose body is a line of literals separated by commas.

		:param name:  Name of the field, as ``Possible Values``.
		:param texts: The literals' texts.
		:returns:     The field.
		"""
		paragraph = nodes.paragraph()
		for index, text in enumerate(texts):
			if index > 0:
				paragraph += nodes.Text(", ")
			paragraph += nodes.literal(text, text)

		return cls._Field(name, paragraph)

	@classmethod
	def _DefaultField(cls, value: ValueT) -> nodes.field:
		"""
		Create the field *Default Value*.

		A multi-line string becomes a literal block, keeping its line breaks; no default becomes :data:`NO_DEFAULT`.

		:param value: The default value.
		:returns:     The field.
		"""
		if value is None:
			return cls._TextField("Default Value", NO_DEFAULT)
		elif isinstance(value, str) and "\n" in value:
			return cls._Field("Default Value", nodes.literal_block(value, value, language="text"))

		return cls._LiteralField("Default Value", (formatValue(value), ))

	@classmethod
	def _FactFields(cls, parameter: Union[Input, Variable]) -> list[nodes.field]:
		"""
		Create the fields taken from the pipeline file.

		:param parameter: The parameter, as read from the pipeline file.
		:returns:         The fields the file states for this parameter, in the order of :attr:`FACT_FIELDS`.
		"""
		return []


@export
class InputDirective(ParameterDirective):
	"""
	The directive ``glci:input``: an input of the current pipeline file's ``spec:inputs``.

	The fields *Type*, *Required* and *Default Value* are taken from the pipeline file, and - where the file states them -
	*Possible Values* (``options``) and *Pattern* (``regex``).
	"""

	directiveName: str = "glci:input"  #: Name the directive is invoked by.

	OBJECT_TYPE = "input"   #: The domain's object type.
	LABEL_KIND =  "Input"   #: The kind in a label.
	COLLECTION =  "Inputs"  #: The pipeline file's property holding the parameters.

	#: The fields the file may state.
	FACT_FIELDS = ("Type", "Required", "Default Value", "Possible Values", "Pattern")

	@classmethod
	def _FactFields(cls, parameter: Input) -> list[nodes.field]:
		"""
		Create the fields *Type*, *Required*, *Default Value*, and *Possible Values* and *Pattern* if the input has them.

		:param parameter: The input, as read from the pipeline file.
		:returns:         The fields.
		"""
		fields = [
			cls._TextField("Type", parameter.Type.value),
			cls._TextField("Required", "yes" if parameter.Required else "no"),
			cls._DefaultField(parameter.Default)
		]
		if len(parameter.Options) > 0:
			fields.append(cls._LiteralField("Possible Values", (formatValue(option) for option in parameter.Options)))

		if parameter.Regex is not None:
			fields.append(cls._LiteralField("Pattern", (parameter.Regex, )))

		return fields


@export
class VariableDirective(ParameterDirective):
	"""
	The directive ``glci:variable``: a default variable of the current pipeline file, declared in its ``variables``.

	The fields *Type* - a variable is a string -, *Default Value* (``value``) and - where the file states them - *Possible
	Values* (``options``) are taken from the pipeline file. A variable with a ``description`` is prefilled in the form
	running a pipeline by hand.
	"""

	directiveName: str = "glci:variable"  #: Name the directive is invoked by.

	OBJECT_TYPE = "variable"                                    #: The domain's object type.
	LABEL_KIND =  "Variable"                                    #: The kind in a label.
	COLLECTION =  "Variables"                                   #: The pipeline file's property holding the parameters.
	FACT_FIELDS = ("Type", "Default Value", "Possible Values")  #: The fields the file may state.

	@classmethod
	def _FactFields(cls, parameter: Variable) -> list[nodes.field]:
		"""
		Create the fields *Type* and *Default Value*, and *Possible Values* if the variable has options.

		:param parameter: The variable, as read from the pipeline file.
		:returns:         The fields.
		"""
		fields = [cls._TextField("Type", "string"), cls._DefaultField(parameter.Value)]
		if len(parameter.Options) > 0:
			fields.append(cls._LiteralField("Possible Values", (formatValue(option) for option in parameter.Options)))

		return fields


@export
class GitLabCIXRefRole(XRefRole):
	"""
	The roles ``:glci:pipeline:``, ``:glci:input:`` and ``:glci:variable:``.

	A parameter is named as ``<Pipeline>.<name>``; inside a ``glci:pipeline``, the name alone refers to the current
	pipeline's parameter. A leading ``~`` shows only the part behind the last dot.
	"""

	def process_link(
		self,
		env:                BuildEnvironment,
		refnode:            Element,
		has_explicit_title: bool,
		title:              str,
		target:             str
	) -> tuple[str, str]:
		"""
		Remember the current pipeline on the reference, and shorten the title for a leading ``~``.

		:param env:                The build environment.
		:param refnode:            The reference node.
		:param has_explicit_title: ``True``, if the role was written with a title, as ``text <target>``.
		:param title:              The title.
		:param target:             The target.
		:returns:                  The title and the target.
		"""
		refnode["glci:pipeline"] = env.ref_context.get("glci:pipeline", None)
		if not has_explicit_title and target.startswith("~"):
			target = target[1:]
			title = target.rpartition(".")[2]

		return title, target


@export
class GitLabCIDomain(Domain):
	"""
	The Sphinx domain ``glci``, documenting GitLab CI/CD pipeline files.

	Its objects are keyed by type and name - ``("pipeline", "Package")``, ``("input", "Package.package_name")`` - and
	located by document and anchor. Directives of other modules reach the domain by ``self.env.get_domain("glci")``, and
	use :meth:`GetCurrentPipeline`, :meth:`LoadPipelineFile`, :attr:`Resolver` and :meth:`ResolvePipeline`.
	"""

	name =         "glci"          #: Name of the domain, the prefix of its directives and roles.
	label =        "GitLab CI/CD"  #: Name of the domain, as displayed.
	data_version = 1               #: Version of the data layout; a change discards pickled environments.

	object_types: ClassVar[dict[str, ObjType]] = {  # type: ignore[misc]
		"pipeline": ObjType("pipeline", "pipeline"),
		"input":    ObjType("input",    "input"),
		"variable": ObjType("variable", "variable"),
	}  #: The object types, each referenced by the role of the same name.

	directives: ClassVar[dict[str, type]] = {  # type: ignore[misc]
		"pipeline": PipelineDirective,
		"input":    InputDirective,
		"variable": VariableDirective,
	}  #: The directives, by name.

	roles: ClassVar[dict[str, XRefRole]] = {  # type: ignore[misc]
		"pipeline": GitLabCIXRefRole(innernodeclass=nodes.literal, warn_dangling=True),
		"input":    GitLabCIXRefRole(innernodeclass=nodes.literal, warn_dangling=True),
		"variable": GitLabCIXRefRole(innernodeclass=nodes.literal, warn_dangling=True),
	}  #: The roles, by name.

	initial_data: ClassVar[dict[str, Any]] = {  # type: ignore[misc]
		"objects": {},
	}  #: The domain's data: ``objects`` maps (type, name) to (document, anchor).

	#: The configuration values the domain adds to :file:`conf.py`, as ``name: (default, rebuild, types)``. Each is
	#: registered with the domain's name as prefix, e.g. ``glci_project``.
	#:
	#: ``server``
	#:    The URL of the GitLab instance links point to, ``https://gitlab.com`` by default, or a self-managed instance's,
	#:    as ``https://gitlab.example.com``.
	#: ``project``
	#:    The documented project, as ``group/project`` or ``group/subgroup/project``.
	#: ``repository_root``
	#:    The documented repository's root directory, relative to the Sphinx source directory, as ``..``. A local
	#:    ``include`` and a child pipeline's file are read from it.
	#: ``pipeline_directory``
	#:    The directory holding the pipeline files, relative to the Sphinx source directory, as ``../templates``. A
	#:    ``glci:pipeline`` without ``:file:`` reads its file from it; without it, from ``repository_root``.
	#: ``ref``
	#:    The ref - a branch or tag - of the documented project the documentation describes, as ``v1``, or ``None``.
	#: ``label_prefix``
	#:    The root of the ``:ref:`` labels the directives register besides their domain targets, as
	#:    ``PIPELINE/Package/Input/package_name``, or ``None`` for none.
	configValues: ClassVar[dict[str, tuple[Any, str, Any]]] = {
		"server":             ("https://gitlab.com", "env", str),
		"project":            (None,                 "env", (str, type(None))),
		"repository_root":    (None,                 "env", (str, type(None))),
		"pipeline_directory": (None,                 "env", (str, type(None))),
		"ref":                (None,                 "env", (str, type(None))),
		"label_prefix":       ("PIPELINE",           "env", (str, type(None))),
	}

	_files:    dict[Path, PipelineFile]   #: Pipeline files already read, by resolved path.
	_resolver: Nullable[IncludeResolver]  #: Resolver reading included files and child pipelines, created when needed.

	def __init__(self, env: BuildEnvironment) -> None:
		"""
		Initializes the domain.

		:param env: The build environment.
		"""
		super().__init__(env)

		self._files =    {}
		self._resolver = None

	@readonly
	def Objects(self) -> dict[tuple[str, str], tuple[str, str]]:
		"""
		Read-only property to return the documented objects.

		:returns: A mapping of (object type, name) to (document, anchor).
		"""
		return self.data["objects"]

	@readonly
	def RepositoryRoot(self) -> Nullable[Path]:
		"""
		Read-only property to return the documented repository's root directory.

		:returns: ``glci_repository_root`` resolved against the Sphinx source directory, or ``None`` if it isn't set.
		"""
		if (directory := self.env.config.glci_repository_root) is None:
			return None

		return (Path(self.env.srcdir) / directory).resolve()

	@readonly
	def PipelineDirectory(self) -> Nullable[Path]:
		"""
		Read-only property to return the directory holding the pipeline files.

		:returns: ``glci_pipeline_directory`` resolved against the Sphinx source directory, else :attr:`RepositoryRoot`.
		"""
		if (directory := self.env.config.glci_pipeline_directory) is None:
			return self.RepositoryRoot

		return (Path(self.env.srcdir) / directory).resolve()

	@readonly
	def Resolver(self) -> Nullable[IncludeResolver]:
		"""
		Read-only property to access the resolver reading local includes and child pipeline files (:attr:`_resolver`),
		created when first needed.

		:returns: The resolver reading from :attr:`RepositoryRoot`, or ``None`` if ``glci_repository_root`` isn't set.
		"""
		if self._resolver is None and (root := self.RepositoryRoot) is not None:
			from pyTooling.GitLab.PipelineFile import IncludeResolver

			self._resolver = IncludeResolver(root)

		return self._resolver

	def LoadPipelineFile(self, path: Path) -> PipelineFile:
		"""
		Read a pipeline file, once per build and process - a parallel build reads a file once in every process needing it.

		The local files it includes are read by :attr:`Resolver`, so ``extends`` and ``!reference`` reach the jobs they
		define.

		:param path:               Path to the pipeline file.
		:returns:                  The pipeline file's model.
		:raises ValueError:        If parameter 'path' is ``None``.
		:raises TypeError:         If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises PipelineFileError: If the file doesn't exist or is not a well-formed configuration.
		"""
		if path is None:
			raise ValueError("Parameter 'path' is None.")
		elif not isinstance(path, Path):
			ex = TypeError("Parameter 'path' is not of type 'Path'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(path)}'.")
			raise ex

		resolved = path.resolve()
		if (known := self._files.get(resolved, None)) is not None:
			return known

		from pyTooling.GitLab.PipelineFile import PipelineFile

		self._files[resolved] = PipelineFile.FromFile(path, self.Resolver)
		return self._files[resolved]

	def GetCurrentPipeline(self) -> Nullable[PipelineFile]:
		"""
		Return the model of the current document's pipeline file, as set by the last ``glci:pipeline``.

		:returns: The pipeline file, or ``None`` if the document has no ``glci:pipeline``, or its file couldn't be read -
		          which the ``glci:pipeline`` directive reported already.
		"""
		if (path := self.env.current_document.get("glci:pipeline-file", None)) is None:
			return None

		return self.LoadPipelineFile(path)

	def ResolvePipeline(self, name: str) -> Nullable[tuple[str, str]]:
		"""
		Return where a pipeline is documented.

		:param name:        The pipeline's name, as its ``glci:pipeline`` names it.
		:returns:           The document and the anchor of its ``glci:pipeline``, or ``None`` if it isn't documented.
		:raises ValueError: If parameter 'name' is ``None``.
		:raises TypeError:  If parameter 'name' is not of type :class:`str`.
		"""
		if name is None:
			raise ValueError("Parameter 'name' is None.")
		elif not isinstance(name, str):
			ex = TypeError("Parameter 'name' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(name)}'.")
			raise ex

		return self.data["objects"].get(("pipeline", name), None)

	def NoteObject(self, objectType: str, name: str, nodeID: str, location: Nullable[Node] = None) -> None:
		"""
		Register a documented object.

		:param objectType:  The object type, as ``input``.
		:param name:        The object's name, as ``Package.package_name``.
		:param nodeID:      The anchor of the object's node.
		:param location:    Optional, the node a duplicate is reported at. Default: ``None``.
		:raises ValueError: If parameter 'objectType' is ``None``.
		:raises TypeError:  If parameter 'objectType' is not of type :class:`str`.
		:raises ValueError: If parameter 'name' is ``None``.
		:raises TypeError:  If parameter 'name' is not of type :class:`str`.
		:raises ValueError: If parameter 'nodeID' is ``None``.
		:raises TypeError:  If parameter 'nodeID' is not of type :class:`str`.
		:raises TypeError:  If parameter 'location' is not of type :class:`~docutils.nodes.Node`.
		"""
		for parameterName, value in (
			("objectType", objectType),
			("name",       name),
			("nodeID",     nodeID)
		):
			if value is None:
				raise ValueError(f"Parameter '{parameterName}' is None.")
			elif not isinstance(value, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
				raise ex

		if location is not None and not isinstance(location, Node):
			ex = TypeError("Parameter 'location' is not of type 'Node'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(location)}'.")
			raise ex

		objects = self.data["objects"]
		if (known := objects.get((objectType, name), None)) is not None:
			_logger.warning(
				f"Duplicate description of glci:{objectType} '{name}', other instance in '{known[0]}'.",
				location=location, type=WARNING_TYPE, subtype="duplicate"
			)

		objects[(objectType, name)] = (self.env.docname, nodeID)

	def clear_doc(self, docname: str) -> None:
		"""
		Remove the objects of a document, before it is read again.

		:param docname: The document.
		"""
		objects = self.data["objects"]
		for key in [key for key, (document, _) in objects.items() if document == docname]:
			del objects[key]

	def merge_domaindata(self, docnames: Iterable[str], otherdata: dict[str, Any]) -> None:
		"""
		Merge the objects a parallel reader collected for its documents.

		:param docnames:  The documents the other reader read.
		:param otherdata: The other reader's data.
		"""
		documents = set(docnames)
		objects = self.data["objects"]
		for key, (document, nodeID) in otherdata["objects"].items():
			if document in documents:
				objects[key] = (document, nodeID)

	def resolve_xref(
		self,
		env:         BuildEnvironment,
		fromdocname: str,
		builder:     Builder,
		typ:         str,
		target:      str,
		node:        addnodes.pending_xref,
		contnode:    Element
	) -> Nullable[nodes.reference]:
		"""
		Resolve a reference by one of the domain's roles.

		A parameter's name without a pipeline is looked up in the pipeline current where the role was written.

		:param env:         The build environment.
		:param fromdocname: The document containing the reference.
		:param builder:     The builder.
		:param typ:         The role's name, as ``input``.
		:param target:      The target, as ``Package.package_name`` or ``package_name``.
		:param node:        The pending reference.
		:param contnode:    The node rendering the reference's title.
		:returns:           The reference, or ``None`` if the target isn't documented.
		"""
		if typ != "pipeline" and "." not in target and (pipelineName := node.get("glci:pipeline", None)) is not None:
			target = f"{pipelineName}.{target}"

		if (location := self.data["objects"].get((typ, target), None)) is None:
			return None

		return make_refnode(builder, fromdocname, location[0], location[1], contnode, target)

	def resolve_any_xref(
		self,
		env:         BuildEnvironment,
		fromdocname: str,
		builder:     Builder,
		target:      str,
		node:        addnodes.pending_xref,
		contnode:    Element
	) -> list[tuple[str, nodes.reference]]:
		"""
		Resolve a reference by the ``:any:`` role, trying every object type.

		:param env:         The build environment.
		:param fromdocname: The document containing the reference.
		:param builder:     The builder.
		:param target:      The target.
		:param node:        The pending reference.
		:param contnode:    The node rendering the reference's title.
		:returns:           A pair of role and reference per object type the target resolves for.
		"""
		results = []
		for objectType in self.object_types:
			if (reference := self.resolve_xref(env, fromdocname, builder, objectType, target, node, contnode)) is not None:
				results.append((f"glci:{objectType}", reference))

		return results

	def get_objects(self) -> Iterable[tuple[str, str, str, str, str, int]]:
		"""
		Iterate the documented objects, for the search index and the inventory.

		:returns: An iterator of (name, display name, type, document, anchor, priority).
		"""
		for (objectType, name), (document, nodeID) in self.data["objects"].items():
			yield name, name, objectType, document, nodeID, 1


@export
def setup(sphinx: Sphinx) -> dict[str, Any]:
	"""
	Register the domain ``glci``, its directives and its configuration values with Sphinx.

	The directives derive from :class:`~pyTooling.Sphinx.BaseDirective` and draw graphs with
	:mod:`sphinx.ext.graphviz`, so the extension :mod:`pyTooling.Sphinx` is set up first.

	:param sphinx: The Sphinx application to register with.
	:returns:      The extension's metadata.
	"""
	from pyTooling.GitLab                  import __version__
	from pyTooling.GitLab.Sphinx.Graph     import PipelineGraph, resolveLinks
	from pyTooling.GitLab.Sphinx.Reference import AutoInputs, Dependencies, Interface, ParameterTable, YAMLExcerpt
	from pyTooling.GitLab.Sphinx.Reference import checkUndocumentedInputs

	sphinx.setup_extension("pyTooling.Sphinx")

	sphinx.add_domain(GitLabCIDomain)
	sphinx.add_directive_to_domain("glci", "pipeline-graph", PipelineGraph)
	sphinx.add_directive_to_domain("glci", "parameter-table", ParameterTable)
	sphinx.add_directive_to_domain("glci", "interface", Interface)
	sphinx.add_directive_to_domain("glci", "dependencies", Dependencies)
	sphinx.add_directive_to_domain("glci", "yaml", YAMLExcerpt)
	sphinx.add_directive_to_domain("glci", "autoinputs", AutoInputs)

	for configName, (default, rebuild, types) in GitLabCIDomain.configValues.items():
		sphinx.add_config_value(f"{GitLabCIDomain.name}_{configName}", default, rebuild, types)

	sphinx.connect("doctree-read", checkUndocumentedInputs)
	sphinx.connect("doctree-resolved", resolveLinks)

	return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}

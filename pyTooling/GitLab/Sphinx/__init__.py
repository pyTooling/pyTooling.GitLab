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

A pipeline file is read by :mod:`pyTooling.GitLab.PipelineFile` and registered as the current pipeline of a document:

.. code-block:: rst

   .. glci:pipeline:: Package
      :file: ../templates/Package/template.yml

   Package
   #######

.. rubric:: What it registers

* Directives

  * ``glci:pipeline``

* Roles

  * ``:glci:pipeline:``
  * ``:glci:input:`` and ``:glci:variable:``, for the entries of parameters

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
"""
from __future__                      import annotations

from pathlib                         import Path
from typing                          import TYPE_CHECKING, Any, ClassVar, Iterable, Optional as Nullable

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
	from pyTooling.GitLab.PipelineFile import IncludeResolver, PipelineFile


__all__ = ["WARNING_TYPE", "FILE_SUFFIXES"]

#: The type of the warnings this domain emits; the drift warnings have the subtype ``drift``, so
#: ``suppress_warnings = ["glci.drift"]`` silences them.
WARNING_TYPE = "glci"

#: The file names a ``glci:pipeline`` without ``:file:`` tries in ``glci_pipeline_directory``, in this order; ``{name}``
#: is the pipeline's name. The last is a CI/CD component's layout.
FILE_SUFFIXES = ("{name}.yml", "{name}.yaml", "{name}/template.yml", "{name}/template.yaml")

_logger = getLogger(__name__)


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

	The directives derive from :class:`~pyTooling.Sphinx.BaseDirective`, so the extension :mod:`pyTooling.Sphinx` is set
	up first.

	:param sphinx: The Sphinx application to register with.
	:returns:      The extension's metadata.
	"""
	from pyTooling.GitLab import __version__

	sphinx.setup_extension("pyTooling.Sphinx")

	sphinx.add_domain(GitLabCIDomain)

	for configName, (default, rebuild, types) in GitLabCIDomain.configValues.items():
		sphinx.add_config_value(f"{GitLabCIDomain.name}_{configName}", default, rebuild, types)

	return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}

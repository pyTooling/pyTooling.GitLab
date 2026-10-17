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
Directives of the ``glci`` domain summarizing the current pipeline file: its parameters and interface.

Each of them reads the pipeline file of the preceding ``glci:pipeline``:

.. code-block:: ReST

   .. glci:pipeline:: Package

   .. glci:parameter-table::
      :kinds: inputs

   .. glci:interface::

   .. glci:autoinputs::

* ``glci:parameter-table`` - the summary tables of the inputs and variables;
* ``glci:interface`` - the contract with a pipeline including the file: the required inputs, the variables of the run
  form, the stages to declare, the jobs and hidden jobs it adds;
* ``glci:autoinputs`` - an entry for every input the document has no ``glci:input`` for.

When a document was read, an input of its pipeline file without an entry is a ``glci.drift`` warning
(:func:`checkUndocumentedInputs`).

.. seealso::

   :mod:`pyTooling.GitLab.Sphinx`
      |rarr| The domain ``glci``, its pipelines and parameter entries.
"""
from __future__                      import annotations

from typing                          import TYPE_CHECKING, Any, Optional as Nullable

from docutils                        import nodes
from sphinx                          import addnodes
from sphinx.application              import Sphinx
from sphinx.transforms               import SphinxTransform
from sphinx.util.logging             import getLogger

from pyTooling.Decorators            import export
from pyTooling.Sphinx                import BaseDirective, SphinxExtensionError, strip
from pyTooling.GitLab.Sphinx         import NO_DEFAULT, WARNING_TYPE, InputDirective, formatValue

if TYPE_CHECKING:  # pragma: no cover
	from pyTooling.GitLab.PipelineFile import PipelineFile, ValueT


__all__ = ["KINDS", "MAX_DEFAULT_LENGTH"]

#: The kinds of parameters ``glci:parameter-table`` summarizes, in the order it shows them by default: kind |rarr| the
#: columns.
KINDS = {
	"inputs":    ("Parameter Name", "Required", "Type", "Default"),
	"variables": ("Variable Name",  "Default",  "Description"),
}

#: The length a default is shortened to in a summary table; a multi-line default is shortened to its first line.
MAX_DEFAULT_LENGTH = 120

_logger = getLogger(__name__)

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

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
A data model of a GitLab CI/CD configuration file.

A configuration file - the project's :file:`.gitlab-ci.yml`, a file it includes, or the file of a child pipeline - is
read once into objects:

.. tree::

   - :class:`PipelineFile` | a configuration file, e.g. :file:`.gitlab-ci.yml`
     - :class:`Variable`   | a default variable, declared in the top-level ``variables``

Every element knows its parent, the file it belongs to and the line it starts at, so a consumer can name the place a
finding comes from, as ``.gitlab-ci.yml:42``.

The model is independent of :mod:`pyTooling.GitLab`, which models a pipeline *run* as the REST API reports it.
"""
from __future__               import annotations

from pathlib                  import Path
from typing                   import Any, ClassVar, Generic, Iterable, Iterator, Mapping, Optional as Nullable, Self
from typing                   import TypeVar, Union

from pyTooling.Common         import getFullyQualifiedName, StringEnum
from pyTooling.Decorators     import export, readonly
from pyTooling.MetaClasses    import ExtendedType, abstractclass

from pyTooling.GitLab         import GitLabError

from ruamel.yaml              import YAML, YAMLError
from ruamel.yaml.comments     import CommentedMap, CommentedSeq
from ruamel.yaml.scalarbool   import ScalarBoolean
from ruamel.yaml.scalarfloat  import ScalarFloat
from ruamel.yaml.scalarint    import ScalarInt
from ruamel.yaml.scalarstring import ScalarString


__all__ = ["ValueT", "DEFAULT_STAGES"]

ValueT = Union[str, bool, int, float, None, list["ValueT"], dict[str, "ValueT"]]
"""A value read from a configuration file, converted to plain Python types."""

ParentType = TypeVar("ParentType", bound="Base")
"""A type variable for the type of an element's parent."""

ParentTypes = Nullable[Union[type, tuple[type, ...]]]
"""The type of :attr:`Base._PARENT_TYPE`: ``None``, a class, or a tuple of classes."""

DEFAULT_STAGES = ("build", "test", "deploy")
"""Stages of a pipeline, whose configuration declares no ``stages``, between ``.pre`` and ``.post``."""


@export
class PipelineFileError(GitLabError):
	"""
	Base-exception of all exceptions raised by :mod:`pyTooling.GitLab.PipelineFile`.

	The exception is raised for a file that is not a well-formed configuration. It carries the file and the line the
	problem was found at in :attr:`Path` and :attr:`Line`, and names both in a note.
	"""

	_path: Nullable[Path]  #: Path to the configuration file.
	_line: Nullable[int]   #: Line in the configuration file, starting at 1.

	def __init__(self, message: str, path: Nullable[Path] = None, line: Nullable[int] = None) -> None:
		"""
		Initializes a configuration error and names the place it was found at in a note.

		:param message: The exception's message.
		:param path:    Optional, path to the configuration file. Default: ``None``.
		:param line:    Optional, line in the configuration file, starting at 1. Default: ``None``.
		"""
		super().__init__(message)

		self._path = path
		self._line = line

		if path is not None:
			self.add_note(f"In '{path}'." if line is None else f"In '{path}:{line}'.")

	@readonly
	def Path(self) -> Nullable[Path]:
		"""
		Read-only property to access the path to the configuration file (:attr:`_path`).

		:returns: The path, or ``None`` if the problem isn't tied to a file.
		"""
		return self._path

	@readonly
	def Line(self) -> Nullable[int]:
		"""
		Read-only property to access the line the problem was found at (:attr:`_line`).

		:returns: The line, starting at 1, or ``None`` if the problem isn't tied to a line.
		"""
		return self._line


@export
@abstractclass
class Base(Generic[ParentType], metaclass=ExtendedType, slots=True):
	"""
	Common behaviour of every element of a configuration file.

	Every element knows the element containing it, the configuration file it belongs to, and the line it starts at.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = None  #: Type a parent must have, or ``None`` when the element has no parent.

	_parent:       Nullable[ParentType]    #: Reference to the containing element.
	_pipelineFile: Nullable[PipelineFile]  #: Reference to the configuration file this element belongs to.
	_line:         int                     #: Line the element starts at in its file, starting at 1.

	def __init__(self, line: int, *, parent: Nullable[ParentType] = None) -> None:
		"""
		Initializes an element of a configuration file.

		:param line:        Line the element starts at in the configuration file, starting at 1.
		:param parent:      Optional, reference to the containing element. Default: ``None``.
		:raises ValueError: If parameter 'line' is ``None``.
		:raises TypeError:  If parameter 'line' is not of type :class:`int`.
		:raises ValueError: If parameter 'line' is not positive.
		:raises TypeError:  If parameter 'parent' is not of the type this class declares in :attr:`_PARENT_TYPE`.
		"""
		if line is None:
			raise ValueError("Parameter 'line' is None.")
		elif not isinstance(line, int) or isinstance(line, bool):
			ex = TypeError("Parameter 'line' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(line)}'.")
			raise ex
		elif line < 1:
			ex = ValueError("Parameter 'line' is not positive.")
			ex.add_note(f"Got value '{line}'.")
			raise ex

		if parent is not None and not isinstance(parent, self._PARENT_TYPE):
			parentTypes = self._PARENT_TYPE if isinstance(self._PARENT_TYPE, tuple) else (self._PARENT_TYPE, )
			ex = TypeError(f"Parameter 'parent' is not of type {' or '.join(f'{t.__name__!r}' for t in parentTypes)}.")
			ex.add_note(f"Got type '{getFullyQualifiedName(parent)}'.")
			raise ex

		self._parent =       parent
		self._pipelineFile = None if parent is None else parent._pipelineFile
		self._line =         line

	@property
	def Parent(self) -> Nullable[ParentType]:
		"""
		Property to access the containing element (:attr:`_parent`).

		Assigning a parent attaches an element constructed before it: the element takes the parent's configuration file,
		and so do the elements it contains.

		:returns:           The containing element, or ``None`` for a :class:`PipelineFile`.
		:raises ValueError: If ``None`` is assigned.
		:raises TypeError:  If a parent is assigned to a :class:`PipelineFile`, which has no parent.
		:raises TypeError:  If an assigned value is not of the type this class declares in :attr:`_PARENT_TYPE`.
		"""
		return self._parent

	@Parent.setter
	def Parent(self, value: ParentType) -> None:
		if value is None:
			raise ValueError("Parameter 'value' is None.")
		elif not isinstance(value, self._PARENT_TYPE):
			parentTypes = self._PARENT_TYPE if isinstance(self._PARENT_TYPE, tuple) else (self._PARENT_TYPE, )
			ex = TypeError(f"Parameter 'value' is not of type {' or '.join(f'{t.__name__!r}' for t in parentTypes)}.")
			ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
			raise ex

		self._parent =       value
		self._pipelineFile = value._pipelineFile

	@readonly
	def PipelineFile(self) -> Nullable[PipelineFile]:
		"""
		Read-only property to access the configuration file this element belongs to (:attr:`_pipelineFile`).

		:returns: The configuration file, or ``None`` for an element outside one.
		"""
		return self._pipelineFile

	@readonly
	def Line(self) -> int:
		"""
		Read-only property to access the line the element starts at in its file (:attr:`_line`).

		:returns: The line, starting at 1.
		"""
		return self._line

	@staticmethod
	def _KeyLine(mapping: CommentedMap, key: Any) -> int:
		"""
		Return the line a key of a mapping is written at.

		A key brought in by a YAML merge key (``<<: *anchor``) is written at the anchor; its line is the mapping's line.

		:param mapping: The mapping read from the file.
		:param key:     The key.
		:returns:       The line, starting at 1.
		"""
		try:
			return mapping.lc.key(key)[0] + 1
		except KeyError:
			return mapping.lc.line + 1

	@staticmethod
	def _ToPython(value: Any) -> ValueT:
		"""
		Convert a value read by ``ruamel.yaml`` into plain Python types.

		The round-trip loader returns its own types for mappings, lists, block scalars, anchored booleans, and numbers
		written in another notation than a plain decimal. They derive from the Python types, but keep what they were
		read with. Every other value is a Python type already.

		:param value: The value read from the file.
		:returns:     The value as :class:`dict`, :class:`list`, :class:`str`, :class:`bool`, :class:`int`,
		              :class:`float` or ``None``.
		"""
		if isinstance(value, CommentedMap):
			return {str(key): Base._ToPython(item) for key, item in value.items()}
		elif isinstance(value, CommentedSeq):
			return [Base._ToPython(item) for item in value]
		elif isinstance(value, ScalarBoolean):
			return bool(value)
		elif isinstance(value, ScalarInt):
			return int(value)
		elif isinstance(value, ScalarFloat):
			return float(value)
		elif isinstance(value, ScalarString):
			return str(value)

		return value

	@staticmethod
	def _ToText(value: Any) -> str:
		"""
		Convert a scalar read from the file into the text GitLab uses, so ``true`` stays ``true`` and not ``True``.

		:param value: The scalar.
		:returns:     The text.
		"""
		value = Base._ToPython(value)
		if isinstance(value, bool):
			return "true" if value else "false"

		return str(value)


@export
class PipelineFile(Base[None]):
	"""A GitLab CI/CD configuration file."""

	_path:      Path                       #: Path to the configuration file.
	_stages:    Nullable[tuple[str, ...]]  #: Stages, as the ``stages`` key declares them.
	_variables: dict[str, Variable]        #: Default variables, by name, in file order.

	def __init__(
		self,
		path:      Path,
		stages:    Nullable[Iterable[str]]      = None,
		variables: Nullable[Iterable[Variable]] = None
	) -> None:
		"""
		Initializes a configuration file.

		A variable is attached by passing it, or by constructing it with the configuration file as parent. Use
		:meth:`FromFile` to read a configuration file.

		:param path:        Path to the configuration file.
		:param stages:      Optional, stages as the ``stages`` key declares them. Default: ``None``, for a file without a
		                    ``stages`` key.
		:param variables:   Optional, default variables, which are attached to the file. Default: ``None``.
		:raises ValueError: If parameter 'path' is ``None``.
		:raises TypeError:  If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises TypeError:  If an element of parameter 'stages' is not of type :class:`str`.
		:raises TypeError:  If an element of parameter 'variables' is not of type :class:`Variable`.
		"""
		super().__init__(1)

		if path is None:
			raise ValueError("Parameter 'path' is None.")
		elif not isinstance(path, Path):
			ex = TypeError("Parameter 'path' is not of type 'Path'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(path)}'.")
			raise ex

		self._pipelineFile = self
		self._path =         path
		self._stages =       None
		self._variables =    {}

		if stages is not None:
			self._stages = tuple(stages)
			for stage in self._stages:
				if not isinstance(stage, str):
					ex = TypeError("An element of parameter 'stages' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(stage)}'.")
					raise ex

		if variables is not None:
			for variable in variables:
				if not isinstance(variable, Variable):
					ex = TypeError("An element of parameter 'variables' is not of type 'Variable'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(variable)}'.")
					raise ex

				self._variables[variable._name] = variable
				variable.Parent = self

	@Base.Parent.setter
	def Parent(self, value: None) -> None:
		ex = TypeError(f"A '{getFullyQualifiedName(self)}' has no parent.")
		ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
		raise ex

	@readonly
	def Path(self) -> Path:
		"""
		Read-only property to access the path to the configuration file (:attr:`_path`).

		:returns: The path.
		"""
		return self._path

	@readonly
	def DeclaredStages(self) -> Nullable[tuple[str, ...]]:
		"""
		Read-only property to access the stages as the ``stages`` key declares them (:attr:`_stages`).

		:returns: The stages, in the order they run, or ``None`` if the file has no ``stages`` key.
		"""
		return self._stages

	@readonly
	def Stages(self) -> tuple[str, ...]:
		"""
		Read-only property to return the stages of the pipeline, in the order they run.

		The stages are those of :attr:`DeclaredStages`, or :data:`DEFAULT_STAGES` without a ``stages`` key, and always
		begin with ``.pre`` and end with ``.post``.

		:returns: The stages.
		"""
		stages = DEFAULT_STAGES if self._stages is None else self._stages
		return (".pre", *(stage for stage in stages if stage not in (".pre", ".post")), ".post")

	@readonly
	def Variables(self) -> dict[str, Variable]:
		"""
		Read-only property to access the default variables (:attr:`_variables`).

		:returns: The variables, by name, in file order.
		"""
		return self._variables

	@classmethod
	def FromFile(cls, path: Path) -> Self:
		"""
		Read a configuration file.

		A file may begin with a header document holding the ``spec`` key, separated from the configuration by ``---``.

		:param path:               Path to the configuration file.
		:returns:                  The configuration file, with its variables attached.
		:raises ValueError:        If parameter 'path' is ``None``.
		:raises TypeError:         If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises PipelineFileError: If the file doesn't exist.
		:raises PipelineFileError: If the file can't be read.
		:raises PipelineFileError: If the file is not a YAML document.
		:raises PipelineFileError: If the file holds more than two documents, or its first of two documents has no
		                           ``spec`` key.
		:raises PipelineFileError: If the configuration is not a mapping.
		:raises PipelineFileError: If a key holds a value of the wrong kind.
		"""
		if path is None:
			raise ValueError("Parameter 'path' is None.")
		elif not isinstance(path, Path):
			ex = TypeError("Parameter 'path' is not of type 'Path'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(path)}'.")
			raise ex
		elif not path.exists():
			raise PipelineFileError("Configuration file doesn't exist.", path) from FileNotFoundError(path)

		try:
			content = path.read_text(encoding="utf-8")
		except OSError as cause:
			raise PipelineFileError("Configuration file can't be read.", path) from cause

		try:
			documents = list(YAML(typ="rt").load_all(content))
		except YAMLError as cause:
			mark = getattr(cause, "problem_mark", None)
			line = None if mark is None else mark.line + 1
			raise PipelineFileError("Configuration file is not a YAML document.", path, line) from cause

		if len(documents) > 2:
			raise PipelineFileError("Configuration file holds more than two documents.", path)
		elif len(documents) == 2:
			header = documents[0]
			if not isinstance(header, CommentedMap) or "spec" not in header:
				raise PipelineFileError("Header document of configuration file has no 'spec' key.", path, 1)

		document = documents[-1] if len(documents) > 0 else None
		if document is None:
			document = CommentedMap()
		elif not isinstance(document, CommentedMap):
			ex = PipelineFileError("Configuration is not a mapping.", path)
			ex.add_note(f"Got type '{getFullyQualifiedName(document)}'.")
			raise ex

		return cls._Parse(document, path)

	@classmethod
	def _Parse(cls, document: CommentedMap, path: Path) -> Self:
		"""
		Build a configuration file and the elements it contains from the configuration document read from it.

		:param document:           The configuration, a mapping.
		:param path:               Path to the configuration file.
		:returns:                  The configuration file, with its variables attached.
		:raises PipelineFileError: If key ``stages`` is not a list.
		:raises PipelineFileError: If key ``variables`` is not a mapping.
		:raises PipelineFileError: If a key of a variable holds a value of the wrong kind.
		"""
		stages = None
		if (stageList := document.get("stages", None)) is not None:
			if not isinstance(stageList, CommentedSeq):
				ex = PipelineFileError("Key 'stages' is not a list.", path, Base._KeyLine(document, "stages"))
				ex.add_note(f"Got type '{getFullyQualifiedName(stageList)}'.")
				raise ex

			stages = [Base._ToText(stage) for stage in stageList]

		variables = None
		if "variables" in document:
			variables = Variable._FromYAMLMapping(document["variables"], None, path, Base._KeyLine(document, "variables"))

		return cls(path, stages, variables)


@export
class Variable(Base[PipelineFile]):
	"""
	A CI/CD variable, declared in a ``variables`` key.

	A default variable - declared in the top-level ``variables`` - may carry a :attr:`Description`, which makes GitLab
	prefill it in the form running a pipeline by hand, and :attr:`Options` to select its value from.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = PipelineFile  #: A variable is declared by a configuration file.

	_name:        str               #: Name of the variable.
	_value:       Nullable[str]     #: Value of the variable.
	_description: Nullable[str]     #: Description of the variable, shown when running a pipeline by hand.
	_options:     tuple[str, ...]   #: Values to select from, when running a pipeline by hand.
	_expand:      Nullable[bool]    #: ``False``, if variables in the value are not expanded.

	_KEYS: ClassVar[tuple[str, ...]] = ("value", "description", "options", "expand")  #: Keys of a declaration as mapping.

	def __init__(
		self,
		name:        str,
		line:        int,
		value:       Nullable[str]           = None,
		description: Nullable[str]           = None,
		options:     Nullable[Iterable[str]] = None,
		expand:      Nullable[bool]          = None,
		*,
		parent:      Nullable[PipelineFile]  = None
	) -> None:
		"""
		Initializes a variable.

		:param name:        Name of the variable.
		:param line:        Line the variable's name is written at, starting at 1.
		:param value:       Optional, value of the variable. Default: ``None``.
		:param description: Optional, description of the variable. Default: ``None``.
		:param options:     Optional, values to select from when running a pipeline by hand. Default: ``None``.
		:param expand:      Optional, ``False``, if variables in the value are not expanded. Default: ``None``, for a
		                    variable that doesn't say.
		:param parent:      Optional, reference to the element declaring the variable. Default: ``None``.
		:raises ValueError: If parameter 'name' is ``None``.
		:raises TypeError:  If parameter 'name' is not of type :class:`str`.
		:raises ValueError: If parameter 'name' is empty.
		:raises TypeError:  If parameter 'value' is not of type :class:`str`.
		:raises TypeError:  If parameter 'description' is not of type :class:`str`.
		:raises TypeError:  If an element of parameter 'options' is not of type :class:`str`.
		:raises TypeError:  If parameter 'expand' is not of type :class:`bool`.
		"""
		super().__init__(line, parent=parent)

		if name is None:
			raise ValueError("Parameter 'name' is None.")
		elif not isinstance(name, str):
			ex = TypeError("Parameter 'name' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(name)}'.")
			raise ex
		elif name == "":
			raise ValueError("Parameter 'name' is empty.")

		for parameterName, text in (
			("value",       value),
			("description", description)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		self._options = () if options is None else tuple(options)
		for option in self._options:
			if not isinstance(option, str):
				ex = TypeError("An element of parameter 'options' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(option)}'.")
				raise ex

		if expand is not None and not isinstance(expand, bool):
			ex = TypeError("Parameter 'expand' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(expand)}'.")
			raise ex

		self._name =        name
		self._value =       value
		self._description = description
		self._expand =      expand

		if parent is not None:
			parent._variables[name] = self

	@readonly
	def Name(self) -> str:
		"""
		Read-only property to access the variable's name (:attr:`_name`).

		:returns: Name of the variable.
		"""
		return self._name

	@readonly
	def Value(self) -> Nullable[str]:
		"""
		Read-only property to access the variable's value (:attr:`_value`).

		A value written as a number or a boolean is its text, as ``3.14`` or ``true``.

		:returns: The value, or ``None`` if the declaration gives none.
		"""
		return self._value

	@readonly
	def Description(self) -> Nullable[str]:
		"""
		Read-only property to access the variable's description (:attr:`_description`).

		:returns: The description, or ``None`` if the declaration gives none.
		"""
		return self._description

	@readonly
	def Options(self) -> tuple[str, ...]:
		"""
		Read-only property to access the values to select from, when running a pipeline by hand (:attr:`_options`).

		:returns: The values, in the order the ``options`` key lists them.
		"""
		return self._options

	@readonly
	def Expand(self) -> Nullable[bool]:
		"""
		Read-only property to access whether variables in the value are expanded (:attr:`_expand`).

		:returns: The ``expand`` key, or ``None`` if the declaration gives none - GitLab expands then.
		"""
		return self._expand

	def __str__(self) -> str:
		"""
		Return the variable's name.

		:returns: Name of the variable.
		"""
		return self._name

	@classmethod
	def _FromYAML(cls, name: str, declaration: Any, path: Path, line: int) -> Self:
		"""
		Read a variable's declaration: a value, or a mapping of the keys in :attr:`_KEYS`.

		:param name:               Name of the variable.
		:param declaration:        The declaration.
		:param path:               Path to the configuration file.
		:param line:               Line the variable's name is written at, starting at 1.
		:returns:                  The variable.
		:raises PipelineFileError: If the declaration is neither a value nor a mapping.
		:raises PipelineFileError: If the mapping has a key GitLab doesn't know for a variable. |br|
		                           The note lists the allowed keys.
		:raises PipelineFileError: If key ``options`` is not a list of values, or key ``expand`` not a boolean.
		"""
		if declaration is None:
			return cls(name, line)
		elif isinstance(declaration, CommentedSeq):
			ex = PipelineFileError(f"Variable '{name}' is neither a value nor a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(declaration)}'.")
			raise ex
		elif not isinstance(declaration, CommentedMap):
			return cls(name, line, Base._ToText(declaration))

		for key in declaration:
			if key not in cls._KEYS:
				ex = PipelineFileError(f"Variable '{name}' has unknown key '{key}'.", path, Base._KeyLine(declaration, key))
				ex.add_note(f"Allowed keys: {', '.join(cls._KEYS)}.")
				raise ex

		options = None
		if (optionList := declaration.get("options", None)) is not None:
			isList = isinstance(optionList, CommentedSeq)
			if not isList or any(isinstance(item, (CommentedMap, CommentedSeq)) for item in optionList):
				ex = PipelineFileError(
					f"Key 'options' of variable '{name}' is not a list of values.", path, Base._KeyLine(declaration, "options")
				)
				ex.add_note(f"Got '{Base._ToPython(optionList)}'.")
				raise ex

			options = [Base._ToText(option) for option in optionList]

		expand = Base._ToPython(declaration.get("expand", None))
		if expand is not None and not isinstance(expand, bool):
			ex = PipelineFileError(
				f"Key 'expand' of variable '{name}' is not a boolean.", path, Base._KeyLine(declaration, "expand")
			)
			ex.add_note(f"Got '{expand}'.")
			raise ex

		value =       declaration.get("value", None)
		description = declaration.get("description", None)

		return cls(
			name, line,
			value=None if value is None else Base._ToText(value),
			description=None if description is None else str(description),
			options=options,
			expand=expand
		)

	@classmethod
	def _FromYAMLMapping(cls, mapping: Any, owner: Nullable[str], path: Path, line: int) -> list[Self]:
		"""
		Read the variables of a ``variables`` key.

		:param mapping:            The key's value.
		:param owner:              The element declaring the variables, for a message, as ``job 'build'``, or ``None``
		                           for the top-level ``variables``.
		:param path:               Path to the configuration file.
		:param line:               Line the ``variables`` key is written at, starting at 1.
		:returns:                  The variables, in file order.
		:raises PipelineFileError: If the value is not a mapping.
		:raises PipelineFileError: If a variable is malformed.
		"""
		if not isinstance(mapping, CommentedMap):
			ex = PipelineFileError(
				"Key 'variables' is not a mapping." if owner is None else f"Key 'variables' of {owner} is not a mapping.",
				path, line
			)
			ex.add_note(f"Got type '{getFullyQualifiedName(mapping)}'.")
			raise ex

		return [cls._FromYAML(str(name), value, path, Base._KeyLine(mapping, name)) for name, value in mapping.items()]

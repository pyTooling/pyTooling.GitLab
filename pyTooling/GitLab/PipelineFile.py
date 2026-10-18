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
     - :class:`Job`        | a job or a hidden job, in file order
       - :class:`Variable` | a variable of the job

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


__all__ = ["ValueT", "RESERVED_KEYS", "DEFAULT_STAGES"]

ValueT = Union[str, bool, int, float, None, list["ValueT"], dict[str, "ValueT"]]
"""A value read from a configuration file, converted to plain Python types."""

ParentType = TypeVar("ParentType", bound="Base")
"""A type variable for the type of an element's parent."""

ParentTypes = Nullable[Union[type, tuple[type, ...]]]
"""The type of :attr:`Base._PARENT_TYPE`: ``None``, a class, or a tuple of classes."""

RESERVED_KEYS = frozenset((
	"default", "include", "stages", "variables", "workflow", "image", "services", "cache", "before_script", "after_script"
))
"""Top-level keys of a configuration file, which declare no job."""

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
class When(StringEnum):
	"""When a job runs, as ``when`` names it."""

	OnSuccess = "on_success"  #: When no job of an earlier stage failed.
	OnFailure = "on_failure"  #: When a job of an earlier stage failed.
	Never =     "never"       #: Never.
	Always =    "always"      #: Whatever the jobs of earlier stages did.
	Manual =    "manual"      #: When started by hand.
	Delayed =   "delayed"     #: After the time given by ``start_in``.


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

	@readonly
	def Location(self) -> str:
		"""
		Read-only property to return the place the element is written at, for a message.

		:returns: The file's name and the line, as ``.gitlab-ci.yml:42``, or ``line 42`` for an element outside a file.
		"""
		if self._pipelineFile is None:
			return f"line {self._line}"

		return f"{self._pipelineFile._path.name}:{self._line}"

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
	def _ItemLine(sequence: CommentedSeq, index: int) -> int:
		"""
		Return the line an item of a sequence is written at.

		:param sequence: The sequence read from the file.
		:param index:    Position of the item, starting at 0.
		:returns:        The line, starting at 1.
		"""
		return sequence.lc.item(index)[0] + 1

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
	"""
	A GitLab CI/CD configuration file.

	A top-level key names a job, unless it is a global keyword (:data:`RESERVED_KEYS`). A job whose name starts with a
	dot is a hidden job: GitLab doesn't run it, other jobs extend it.
	"""

	_path:       Path                       #: Path to the configuration file.
	_stages:     Nullable[tuple[str, ...]]  #: Stages, as the ``stages`` key declares them.
	_variables:  dict[str, Variable]        #: Default variables, by name, in file order.
	_jobs:       dict[str, Job]             #: Jobs, by name, in file order.
	_hiddenJobs: dict[str, Job]             #: Hidden jobs, by name, in file order.

	def __init__(
		self,
		path:      Path,
		stages:    Nullable[Iterable[str]]      = None,
		variables: Nullable[Iterable[Variable]] = None,
		jobs:      Nullable[Iterable[Job]]      = None
	) -> None:
		"""
		Initializes a configuration file.

		A variable or job is attached by passing it, or by constructing it with the configuration file as parent. Use
		:meth:`FromFile` to read a configuration file.

		:param path:        Path to the configuration file.
		:param stages:      Optional, stages as the ``stages`` key declares them. Default: ``None``, for a file without a
		                    ``stages`` key.
		:param variables:   Optional, default variables, which are attached to the file. Default: ``None``.
		:param jobs:        Optional, jobs and hidden jobs, which are attached to the file. Default: ``None``.
		:raises ValueError: If parameter 'path' is ``None``.
		:raises TypeError:  If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises TypeError:  If an element of parameter 'stages' is not of type :class:`str`.
		:raises TypeError:  If an element of parameter 'variables' is not of type :class:`Variable`.
		:raises TypeError:  If an element of parameter 'jobs' is not of type :class:`Job`.
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
		self._jobs =         {}
		self._hiddenJobs =   {}

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

		if jobs is not None:
			for job in jobs:
				if not isinstance(job, Job):
					ex = TypeError("An element of parameter 'jobs' is not of type 'Job'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(job)}'.")
					raise ex

				(self._hiddenJobs if job.IsHidden else self._jobs)[job._name] = job
				job.Parent = self

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

	@readonly
	def Jobs(self) -> dict[str, Job]:
		"""
		Read-only property to access the jobs (:attr:`_jobs`).

		:returns: The jobs, by name, in file order.
		"""
		return self._jobs

	@readonly
	def HiddenJobs(self) -> dict[str, Job]:
		"""
		Read-only property to access the hidden jobs (:attr:`_hiddenJobs`).

		:returns: The hidden jobs, by name, in file order.
		"""
		return self._hiddenJobs

	@readonly
	def JobCount(self) -> int:
		"""
		Read-only property to return the number of jobs, hidden jobs not counted.

		:returns: Number of jobs.
		"""
		return len(self._jobs)

	def ContainsJob(self, name: str) -> bool:
		"""
		Check whether the file has a job of that name.

		:param name: Name of the job, the key it is declared under.
		:returns:    ``True``, if the file has a job of that name. A hidden job isn't a job.
		"""
		return name in self._jobs

	def IterateJobs(self) -> Iterator[Job]:
		"""
		Iterate the jobs, hidden jobs not included.

		:returns: An iterator over the jobs, in file order.
		"""
		return iter(self._jobs.values())

	def IterateHiddenJobs(self) -> Iterator[Job]:
		"""
		Iterate the hidden jobs.

		:returns: An iterator over the hidden jobs, in file order.
		"""
		return iter(self._hiddenJobs.values())

	def __str__(self) -> str:
		"""
		Return the file's name.

		:returns: Name of the configuration file.
		"""
		return self._path.name

	@classmethod
	def FromFile(cls, path: Path) -> Self:
		"""
		Read a configuration file.

		A file may begin with a header document holding the ``spec`` key, separated from the configuration by ``---``.

		:param path:               Path to the configuration file.
		:returns:                  The configuration file, with its variables and jobs attached.
		:raises ValueError:        If parameter 'path' is ``None``.
		:raises TypeError:         If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises PipelineFileError: If the file doesn't exist.
		:raises PipelineFileError: If the file can't be read.
		:raises PipelineFileError: If the file is not a YAML document.
		:raises PipelineFileError: If the file holds more than two documents, or its first of two documents has no
		                           ``spec`` key.
		:raises PipelineFileError: If the configuration is not a mapping.
		:raises PipelineFileError: If a key holds a value of the wrong kind.
		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
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

		pipelineFile = cls._Parse(document, path)
		pipelineFile._Validate()

		return pipelineFile

	@classmethod
	def _Parse(cls, document: CommentedMap, path: Path) -> Self:
		"""
		Build a configuration file and the elements it contains from the configuration document read from it.

		:param document:           The configuration, a mapping.
		:param path:               Path to the configuration file.
		:returns:                  The configuration file, with its variables and jobs attached.
		:raises PipelineFileError: If key ``stages`` is not a list.
		:raises PipelineFileError: If key ``variables`` or a job is not a mapping.
		:raises PipelineFileError: If a key of a variable or a job holds a value of the wrong kind.
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

		jobs = []
		for name, job in document.items():
			name = str(name)
			if name in RESERVED_KEYS:
				continue

			line = Base._KeyLine(document, name)
			if not isinstance(job, CommentedMap):
				ex = PipelineFileError(f"Job '{name}' is not a mapping.", path, line)
				ex.add_note(f"Got type '{getFullyQualifiedName(job)}'.")
				raise ex

			jobs.append(Job._FromYAML(name, job, path, line))

		return cls(path, stages, variables, jobs)

	def _Validate(self) -> None:
		"""
		Validate the configuration read from a file.

		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
		"""
		self._ValidateStages()

	def _ValidateStages(self) -> None:
		"""
		Validate that every job is in a stage of the pipeline.

		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
		"""
		stages = self.Stages
		for job in self._jobs.values():
			if job._stage not in stages:
				ex = PipelineFileError(
					f"Job '{job._name}' is in stage '{job._stage}', which isn't declared.", self._path, job._line
				)
				ex.add_note(f"Stages: {', '.join(stages)}.")
				raise ex


@export
class Job(Base[PipelineFile]):
	"""
	A job of a configuration file, or a hidden job.

	A job runs :attr:`Script` in :attr:`Stage`, after the jobs of the earlier stages. A hidden job, whose name starts
	with a dot, isn't run; other jobs extend it.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = PipelineFile  #: A job is contained in a configuration file.

	_name:             str                   #: Name of the job, the key it is declared under.
	_stage:            str                   #: Stage the job runs in.
	_when:             Nullable[When]        #: When the job runs.
	_allowFailure:     Nullable[bool]        #: ``True``, if the pipeline continues when the job fails.
	_allowedExitCodes: tuple[int, ...]       #: Exit codes, with which the job may fail.
	_script:           tuple[str, ...]       #: Lines of the job's ``script``.
	_beforeScript:     tuple[str, ...]       #: Lines of the job's ``before_script``.
	_afterScript:      tuple[str, ...]       #: Lines of the job's ``after_script``.
	_image:            Nullable[str]         #: Image of the container the job runs in.
	_services:         tuple[str, ...]       #: Images of the service containers.
	_tags:             tuple[str, ...]       #: Tags selecting the runner.
	_environment:      Nullable[str]         #: Name of the environment the job deploys to.
	_variables:        dict[str, Variable]   #: Variables of the job, by name, in file order.

	def __init__(
		self,
		name:             str,
		line:             int,
		stage:            str                          = "test",
		when:             Nullable[When]               = None,
		allowFailure:     Nullable[bool]               = None,
		allowedExitCodes: Nullable[Iterable[int]]      = None,
		script:           Nullable[Iterable[str]]      = None,
		beforeScript:     Nullable[Iterable[str]]      = None,
		afterScript:      Nullable[Iterable[str]]      = None,
		image:            Nullable[str]                = None,
		services:         Nullable[Iterable[str]]      = None,
		tags:             Nullable[Iterable[str]]      = None,
		environment:      Nullable[str]                = None,
		variables:        Nullable[Iterable[Variable]] = None,
		*,
		parent:           Nullable[PipelineFile]       = None
	) -> None:
		"""
		Initializes a job.

		A variable is attached by passing it, or by constructing it with the job as parent.

		:param name:             Name of the job, the key it is declared under.
		:param line:             Line the job's name is written at, starting at 1.
		:param stage:            Optional, stage the job runs in. Default: ``test``.
		:param when:             Optional, when the job runs. Default: ``None``, for a job that doesn't say.
		:param allowFailure:     Optional, ``True``, if the pipeline continues when the job fails. Default: ``None``.
		:param allowedExitCodes: Optional, exit codes, with which the job may fail. Default: ``None``.
		:param script:           Optional, lines of the job's ``script``. Default: ``None``.
		:param beforeScript:     Optional, lines of the job's ``before_script``. Default: ``None``.
		:param afterScript:      Optional, lines of the job's ``after_script``. Default: ``None``.
		:param image:            Optional, image of the container the job runs in. Default: ``None``.
		:param services:         Optional, images of the service containers. Default: ``None``.
		:param tags:             Optional, tags selecting the runner. Default: ``None``.
		:param environment:      Optional, name of the environment the job deploys to. Default: ``None``.
		:param variables:        Optional, variables of the job, which are attached to the job. Default: ``None``.
		:param parent:           Optional, reference to the configuration file containing the job. Default: ``None``.
		:raises ValueError:      If parameter 'name' or 'stage' is ``None``.
		:raises TypeError:       If parameter 'name' or 'stage' is not of type :class:`str`.
		:raises ValueError:      If parameter 'name' or 'stage' is empty.
		:raises TypeError:       If parameter 'when' is not of type :class:`When`.
		:raises TypeError:       If parameter 'allowFailure' is not of type :class:`bool`.
		:raises TypeError:       If parameter 'image' or 'environment' is not of type :class:`str`.
		:raises TypeError:       If an element of parameter 'allowedExitCodes' is not of type :class:`int`.
		:raises TypeError:       If an element of parameter 'script', 'beforeScript', 'afterScript', 'services' or
		                         'tags' is not of type :class:`str`.
		:raises TypeError:       If an element of parameter 'variables' is not of type :class:`Variable`.
		"""
		super().__init__(line, parent=parent)

		for parameterName, text in (
			("name",  name),
			("stage", stage)
		):
			if text is None:
				raise ValueError(f"Parameter '{parameterName}' is None.")
			elif not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex
			elif text == "":
				raise ValueError(f"Parameter '{parameterName}' is empty.")

		if when is not None and not isinstance(when, When):
			ex = TypeError("Parameter 'when' is not of type 'When'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(when)}'.")
			raise ex

		if allowFailure is not None and not isinstance(allowFailure, bool):
			ex = TypeError("Parameter 'allowFailure' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(allowFailure)}'.")
			raise ex

		for parameterName, text in (
			("image",       image),
			("environment", environment)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		self._allowedExitCodes = () if allowedExitCodes is None else tuple(allowedExitCodes)
		for code in self._allowedExitCodes:
			if not isinstance(code, int) or isinstance(code, bool):
				ex = TypeError("An element of parameter 'allowedExitCodes' is not of type 'int'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(code)}'.")
				raise ex

		self._script =       () if script is None else tuple(script)
		self._beforeScript = () if beforeScript is None else tuple(beforeScript)
		self._afterScript =  () if afterScript is None else tuple(afterScript)
		self._services =     () if services is None else tuple(services)
		self._tags =         () if tags is None else tuple(tags)
		for parameterName, texts in (
			("script",       self._script),
			("beforeScript", self._beforeScript),
			("afterScript",  self._afterScript),
			("services",     self._services),
			("tags",         self._tags)
		):
			for text in texts:
				if not isinstance(text, str):
					ex = TypeError(f"An element of parameter '{parameterName}' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
					raise ex

		self._name =         name
		self._stage =        stage
		self._when =         when
		self._allowFailure = allowFailure
		self._image =        image
		self._environment =  environment
		self._variables =    {}

		if variables is not None:
			for variable in variables:
				if not isinstance(variable, Variable):
					ex = TypeError("An element of parameter 'variables' is not of type 'Variable'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(variable)}'.")
					raise ex

				self._variables[variable._name] = variable
				variable.Parent = self

		if parent is not None:
			(parent._hiddenJobs if self.IsHidden else parent._jobs)[name] = self

	@Base.Parent.setter
	def Parent(self, value: PipelineFile) -> None:
		Base.Parent.fset(self, value)

		for variable in self._variables.values():
			variable.Parent = self

	@readonly
	def Name(self) -> str:
		"""
		Read-only property to access the job's name, the key it is declared under (:attr:`_name`).

		:returns: Name of the job.
		"""
		return self._name

	@readonly
	def IsHidden(self) -> bool:
		"""
		Read-only property to return whether the job is a hidden job, which GitLab doesn't run.

		:returns: ``True``, if the job's name starts with a dot.
		"""
		return self._name.startswith(".")

	@readonly
	def Stage(self) -> str:
		"""
		Read-only property to access the stage the job runs in (:attr:`_stage`).

		:returns: The stage, ``test`` for a job that doesn't name one.
		"""
		return self._stage

	@readonly
	def When(self) -> Nullable[When]:
		"""
		Read-only property to access when the job runs (:attr:`_when`).

		:returns: The ``when`` key, or ``None`` if the job doesn't say - GitLab runs it on success then.
		"""
		return self._when

	@readonly
	def AllowFailure(self) -> Nullable[bool]:
		"""
		Read-only property to access whether the pipeline continues when the job fails (:attr:`_allowFailure`).

		:returns: The ``allow_failure`` key, ``True`` for a mapping of exit codes, or ``None`` if the job doesn't say.
		"""
		return self._allowFailure

	@readonly
	def AllowedExitCodes(self) -> tuple[int, ...]:
		"""
		Read-only property to access the exit codes, with which the job may fail (:attr:`_allowedExitCodes`).

		:returns: The exit codes of ``allow_failure.exit_codes``, in file order.
		"""
		return self._allowedExitCodes

	@readonly
	def Script(self) -> tuple[str, ...]:
		"""
		Read-only property to access the lines of the job's ``script`` (:attr:`_script`).

		:returns: The lines, nested lists flattened.
		"""
		return self._script

	@readonly
	def BeforeScript(self) -> tuple[str, ...]:
		"""
		Read-only property to access the lines of the job's ``before_script`` (:attr:`_beforeScript`).

		:returns: The lines, nested lists flattened.
		"""
		return self._beforeScript

	@readonly
	def AfterScript(self) -> tuple[str, ...]:
		"""
		Read-only property to access the lines of the job's ``after_script`` (:attr:`_afterScript`).

		:returns: The lines, nested lists flattened.
		"""
		return self._afterScript

	@readonly
	def Image(self) -> Nullable[str]:
		"""
		Read-only property to access the image of the container the job runs in (:attr:`_image`).

		:returns: The image, as ``python:3.14``, or ``None`` if the job names none.
		"""
		return self._image

	@readonly
	def Services(self) -> tuple[str, ...]:
		"""
		Read-only property to access the images of the service containers (:attr:`_services`).

		:returns: The images, in file order.
		"""
		return self._services

	@readonly
	def Tags(self) -> tuple[str, ...]:
		"""
		Read-only property to access the tags selecting the runner (:attr:`_tags`).

		:returns: The tags, in file order.
		"""
		return self._tags

	@readonly
	def Environment(self) -> Nullable[str]:
		"""
		Read-only property to access the name of the environment the job deploys to (:attr:`_environment`).

		:returns: The environment's name, or ``None`` if the job deploys to none.
		"""
		return self._environment

	@readonly
	def Variables(self) -> dict[str, Variable]:
		"""
		Read-only property to access the variables of the job (:attr:`_variables`).

		:returns: The variables, by name, in file order.
		"""
		return self._variables

	def __str__(self) -> str:
		"""
		Return the job's name.

		:returns: Name of the job.
		"""
		return self._name

	@staticmethod
	def _Lines(value: Any, key: str, name: str, mapping: CommentedMap, path: Path) -> list[str]:
		"""
		Read a script key: a line, or a list of lines and nested lists of lines.

		:param value:              The key's value.
		:param key:                The key, for a message.
		:param name:               Name of the job, for a message.
		:param mapping:            The job's mapping, for the key's line.
		:param path:               Path to the configuration file.
		:returns:                  The lines, nested lists flattened.
		:raises PipelineFileError: If the value is a mapping, or a list holds a mapping.
		"""
		if isinstance(value, CommentedSeq):
			lines = []
			for item in value:
				lines.extend(Job._Lines(item, key, name, mapping, path))

			return lines
		elif isinstance(value, CommentedMap):
			ex = PipelineFileError(f"Key '{key}' of job '{name}' is not a script.", path, Base._KeyLine(mapping, key))
			ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
			raise ex

		return [] if value is None else [Base._ToText(value)]

	@staticmethod
	def _Name(value: Any) -> Nullable[str]:
		"""
		Read a key naming something by a string or by the ``name`` of a mapping, as ``image`` and ``environment`` do.

		:param value: The key's value.
		:returns:     The name, or ``None``.
		"""
		if isinstance(value, CommentedMap):
			value = value.get("name", None)

		return None if value is None else Base._ToText(value)

	@classmethod
	def _FromYAML(cls, name: str, mapping: CommentedMap, path: Path, line: int) -> Self:
		"""
		Build a job and the elements it contains from its mapping in the configuration file.

		:param name:               Name of the job.
		:param mapping:            The job's mapping.
		:param path:               Path to the configuration file.
		:param line:               Line the job's name is written at, starting at 1.
		:returns:                  The job.
		:raises PipelineFileError: If key ``when`` is not a value GitLab knows. |br|
		                           The note lists the allowed values.
		:raises PipelineFileError: If a key of the job holds a value of the wrong kind.
		"""
		when = None
		if (whenValue := mapping.get("when", None)) is not None:
			try:
				when = When.Parse(Base._ToText(whenValue))
			except ValueError as cause:
				ex = PipelineFileError(
					f"Key 'when' of job '{name}' is not a known value.", path, Base._KeyLine(mapping, "when")
				)
				ex.add_note(f"Got '{whenValue}'.")
				ex.add_note(f"Allowed values: {', '.join(member.value for member in When)}.")
				raise ex from cause

		allowFailure = Base._ToPython(mapping.get("allow_failure", None))
		exitCodes = None
		if isinstance(allowFailure, dict):
			exitCodes = allowFailure.get("exit_codes", ())
			exitCodes = [exitCodes] if isinstance(exitCodes, int) else exitCodes
			allowFailure = True

		if allowFailure is not None and not isinstance(allowFailure, bool):
			ex = PipelineFileError(
				f"Key 'allow_failure' of job '{name}' is not a boolean.", path, Base._KeyLine(mapping, "allow_failure")
			)
			ex.add_note(f"Got '{allowFailure}'.")
			raise ex

		services = None
		if (serviceList := mapping.get("services", None)) is not None:
			if not isinstance(serviceList, CommentedSeq):
				ex = PipelineFileError(
					f"Key 'services' of job '{name}' is not a list.", path, Base._KeyLine(mapping, "services")
				)
				ex.add_note(f"Got type '{getFullyQualifiedName(serviceList)}'.")
				raise ex

			services = [service for item in serviceList if (service := cls._Name(item)) is not None]

		tags = None
		if (tagList := mapping.get("tags", None)) is not None:
			if not isinstance(tagList, CommentedSeq):
				ex = PipelineFileError(f"Key 'tags' of job '{name}' is not a list.", path, Base._KeyLine(mapping, "tags"))
				ex.add_note(f"Got type '{getFullyQualifiedName(tagList)}'.")
				raise ex

			tags = [Base._ToText(tag) for tag in tagList]

		variables = None
		if "variables" in mapping:
			keyLine = Base._KeyLine(mapping, "variables")
			variables = Variable._FromYAMLMapping(mapping["variables"], f"job '{name}'", path, keyLine)

		stage = mapping.get("stage", None)

		return cls(
			name, line,
			stage="test" if stage is None else Base._ToText(stage),
			when=when,
			allowFailure=allowFailure,
			allowedExitCodes=exitCodes,
			script=cls._Lines(mapping.get("script", None), "script", name, mapping, path),
			beforeScript=cls._Lines(mapping.get("before_script", None), "before_script", name, mapping, path),
			afterScript=cls._Lines(mapping.get("after_script", None), "after_script", name, mapping, path),
			image=cls._Name(mapping.get("image", None)),
			services=services,
			tags=tags,
			environment=cls._Name(mapping.get("environment", None)),
			variables=variables
		)


@export
class Variable(Base[Union[PipelineFile, Job]]):
	"""
	A CI/CD variable, declared in a ``variables`` key.

	A default variable - declared in the top-level ``variables`` - may carry a :attr:`Description`, which makes GitLab
	prefill it in the form running a pipeline by hand, and :attr:`Options` to select its value from.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = (PipelineFile, Job)  #: A variable is declared by a configuration file or a job.

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
		value:       Nullable[str]                      = None,
		description: Nullable[str]                      = None,
		options:     Nullable[Iterable[str]]            = None,
		expand:      Nullable[bool]                     = None,
		*,
		parent:      Nullable[Union[PipelineFile, Job]] = None
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
		:param parent:      Optional, reference to the configuration file or the job declaring the variable. Default:
		                    ``None``.
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

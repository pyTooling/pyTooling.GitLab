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
     - :class:`Input`      | an input of the header's ``spec:inputs``
     - :class:`Workflow`   | the ``workflow`` key
       - :class:`Rule`     | a rule deciding whether a pipeline is created
     - :class:`Include`    | an entry of ``include``
       - :class:`Rule`     | a rule deciding whether the file is included
     - :class:`Default`    | the ``default`` key
     - :class:`Variable`   | a default variable, declared in the top-level ``variables``
     - :class:`Job`        | a job or a hidden job, in file order
       - :class:`Need`     | an entry of the job's ``needs``
         - :class:`Parallel` | the matrix instances needed
       - :class:`Rule`     | a rule deciding whether the job is added to a pipeline
       - :class:`Variable` | a variable of the job
       - :class:`Input`    | an input of the job
       - :class:`Parallel` | the job's ``parallel``: how often it runs, or its matrix
       - :class:`Trigger`  | the child pipeline or other project's pipeline the job starts
         - :class:`Include` | a file of the child pipeline

Every element knows its parent, the file it belongs to and the line it starts at, so a consumer can name the place a
finding comes from, as ``.gitlab-ci.yml:42``.

The model is independent of :mod:`pyTooling.GitLab`, which models a pipeline *run* as the REST API reports it.
"""
from __future__               import annotations

from itertools                import product
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


__all__ = ["ValueT", "RESERVED_KEYS", "DEFAULT_STAGES", "MAX_EXTENDS_DEPTH", "MAX_REFERENCE_DEPTH"]

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

MAX_EXTENDS_DEPTH = 11
"""How many levels of ``extends`` GitLab resolves."""

MAX_REFERENCE_DEPTH = 10
"""How many levels of ``!reference`` tags GitLab resolves."""


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
class IncludeKind(StringEnum):
	"""Where an included file comes from, as the key of an ``include`` entry names it."""

	Local =     "local"      #: A file of the same repository.
	Project =   "project"    #: Files of another project.
	Remote =    "remote"     #: A file at a URL.
	Template =  "template"   #: A CI/CD template shipped with GitLab.
	Component = "component"  #: A CI/CD component.
	Artifact =  "artifact"   #: A file a job of the pipeline created, for a dynamic child pipeline.


@export
class InputType(StringEnum):
	"""The type of an input, as ``type`` names it."""

	String =  "string"   #: A string.
	Number =  "number"   #: A number.
	Boolean = "boolean"  #: ``true`` or ``false``.
	Array =   "array"    #: A list of values.


@export
class TriggerStrategy(StringEnum):
	"""How a trigger job's status follows the pipeline it starts, as ``trigger.strategy`` names it."""

	Depend = "depend"  #: The trigger job waits for the pipeline, and reports failed, success or running.
	Mirror = "mirror"  #: The trigger job waits for the pipeline, and mirrors its status exactly.


@export
class NeedKind(StringEnum):
	"""What an entry of ``needs`` refers to."""

	Job =            "job"              #: A job of the same pipeline.
	PipelineJob =    "pipeline-job"     #: A job of another pipeline in the same parent-child hierarchy.
	ProjectJob =     "project-job"      #: A job of another project's pipeline, whose artifacts are downloaded.
	PipelineStatus = "pipeline-status"  #: The status of another project's pipeline, which the job mirrors.


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

	_path:        Path                       #: Path to the configuration file.
	_stages:      Nullable[tuple[str, ...]]  #: Stages, as the ``stages`` key declares them.
	_variables:   dict[str, Variable]        #: Default variables, by name, in file order.
	_jobs:        dict[str, Job]             #: Jobs, by name, in file order.
	_hiddenJobs:  dict[str, Job]             #: Hidden jobs, by name, in file order.
	_workflow:    Nullable[Workflow]         #: The ``workflow`` key.
	_includes:    list[Include]              #: Entries of ``include``, in file order.
	_default:     Nullable[Default]          #: The ``default`` key.
	_inputs:      dict[str, Input]           #: Inputs of the header's ``spec:inputs``, by name, in file order.
	_description: Nullable[str]              #: Description of the header's ``spec:description``.

	def __init__(
		self,
		path:        Path,
		stages:      Nullable[Iterable[str]]      = None,
		variables:   Nullable[Iterable[Variable]] = None,
		jobs:        Nullable[Iterable[Job]]      = None,
		workflow:    Nullable[Workflow]           = None,
		includes:    Nullable[Iterable[Include]]  = None,
		default:     Nullable[Default]            = None,
		inputs:      Nullable[Iterable[Input]]    = None,
		description: Nullable[str]                = None
	) -> None:
		"""
		Initializes a configuration file.

		A variable, job, workflow, include, default or input is attached by passing it, or by constructing it with the
		configuration file as parent. Use :meth:`FromFile` to read a configuration file.

		:param path:        Path to the configuration file.
		:param stages:      Optional, stages as the ``stages`` key declares them. Default: ``None``, for a file without a
		                    ``stages`` key.
		:param variables:   Optional, default variables, which are attached to the file. Default: ``None``.
		:param jobs:        Optional, jobs and hidden jobs, which are attached to the file. Default: ``None``.
		:param workflow:    Optional, the ``workflow`` key, which is attached to the file. Default: ``None``.
		:param includes:    Optional, entries of ``include``, which are attached to the file. Default: ``None``.
		:param default:     Optional, the ``default`` key, which is attached to the file. Default: ``None``.
		:param inputs:      Optional, inputs of the header's ``spec:inputs``, which are attached to the file. Default:
		                    ``None``.
		:param description: Optional, description of the header's ``spec:description``. Default: ``None``.
		:raises ValueError: If parameter 'path' is ``None``.
		:raises TypeError:  If parameter 'path' is not of type :class:`~pathlib.Path`.
		:raises TypeError:  If an element of parameter 'stages' is not of type :class:`str`.
		:raises TypeError:  If an element of parameter 'variables' is not of type :class:`Variable`.
		:raises TypeError:  If an element of parameter 'jobs' is not of type :class:`Job`.
		:raises TypeError:  If parameter 'workflow' is not of type :class:`Workflow`.
		:raises TypeError:  If an element of parameter 'includes' is not of type :class:`Include`.
		:raises TypeError:  If parameter 'default' is not of type :class:`Default`.
		:raises TypeError:  If an element of parameter 'inputs' is not of type :class:`Input`.
		:raises TypeError:  If parameter 'description' is not of type :class:`str`.
		"""
		super().__init__(1)

		if path is None:
			raise ValueError("Parameter 'path' is None.")
		elif not isinstance(path, Path):
			ex = TypeError("Parameter 'path' is not of type 'Path'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(path)}'.")
			raise ex

		if description is not None and not isinstance(description, str):
			ex = TypeError("Parameter 'description' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(description)}'.")
			raise ex

		self._pipelineFile = self
		self._path =         path
		self._stages =       None
		self._variables =    {}
		self._jobs =         {}
		self._hiddenJobs =   {}
		self._workflow =     None
		self._includes =     []
		self._default =      None
		self._inputs =       {}
		self._description =  description

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

		if workflow is not None:
			if not isinstance(workflow, Workflow):
				ex = TypeError("Parameter 'workflow' is not of type 'Workflow'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(workflow)}'.")
				raise ex

			self._workflow = workflow
			workflow.Parent = self

		if includes is not None:
			for include in includes:
				if not isinstance(include, Include):
					ex = TypeError("An element of parameter 'includes' is not of type 'Include'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(include)}'.")
					raise ex

				self._includes.append(include)
				include.Parent = self

		if default is not None:
			if not isinstance(default, Default):
				ex = TypeError("Parameter 'default' is not of type 'Default'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(default)}'.")
				raise ex

			self._default = default
			default.Parent = self

		if inputs is not None:
			for parameter in inputs:
				if not isinstance(parameter, Input):
					ex = TypeError("An element of parameter 'inputs' is not of type 'Input'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(parameter)}'.")
					raise ex

				self._inputs[parameter._name] = parameter
				parameter.Parent = self

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
	def Inputs(self) -> dict[str, Input]:
		"""
		Read-only property to access the inputs of the header's ``spec:inputs`` (:attr:`_inputs`).

		:returns: The inputs, by name, in file order.
		"""
		return self._inputs

	@readonly
	def Description(self) -> Nullable[str]:
		"""
		Read-only property to access the description of the header's ``spec:description`` (:attr:`_description`).

		:returns: The description, or ``None`` if the file gives none.
		"""
		return self._description

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
	def Workflow(self) -> Nullable[Workflow]:
		"""
		Read-only property to access the ``workflow`` key (:attr:`_workflow`).

		:returns: The workflow, or ``None`` if the file has no ``workflow`` key.
		"""
		return self._workflow

	@readonly
	def Includes(self) -> list[Include]:
		"""
		Read-only property to access the entries of ``include`` (:attr:`_includes`).

		:returns: The entries, in file order.
		"""
		return self._includes

	@readonly
	def Default(self) -> Nullable[Default]:
		"""
		Read-only property to access the ``default`` key (:attr:`_default`).

		:returns: The default, or ``None`` if the file has neither a ``default`` key nor a global keyword it stands for.
		"""
		return self._default

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
		:raises PipelineFileError: If an input is malformed, or its default doesn't match its type or options.
		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
		:raises PipelineFileError: If a job needs a job the file doesn't have, or the jobs need each other in a cycle. |br|
		                           For an unknown job, the note lists the file's jobs.
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

		header = None
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

		pipelineFile = cls._Parse(document, path, header)
		pipelineFile._Validate()

		return pipelineFile

	@classmethod
	def _Parse(cls, document: CommentedMap, path: Path, header: Nullable[CommentedMap] = None) -> Self:
		"""
		Build a configuration file and the elements it contains from the documents read from it.

		:param document:           The configuration, a mapping.
		:param path:               Path to the configuration file.
		:param header:             Optional, the header document, a mapping with key ``spec``. Default: ``None``.
		:returns:                  The configuration file, with its variables, jobs, workflow, includes and default
		                           attached.
		:raises PipelineFileError: If key ``spec`` or ``spec:inputs`` of the header is not a mapping, or an input is
		                           malformed.
		:raises PipelineFileError: If key ``stages`` is not a list.
		:raises PipelineFileError: If key ``variables``, ``workflow`` or a job is not a mapping.
		:raises PipelineFileError: If a job extends a job, or a ``!reference`` tag refers to a key, the file doesn't have,
		                           though it includes no files.
		:raises PipelineFileError: If jobs extend each other in a cycle, or ``extends`` or ``!reference`` tags nest too
		                           deep.
		:raises PipelineFileError: If a key of a variable, a job, the workflow or an include holds a value of the wrong
		                           kind.
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
		for name, (mapping, unresolved) in cls._ResolveJobs(document, path).items():
			jobs.append(Job._FromYAML(name, mapping, path, Base._KeyLine(document, name), unresolved))

		workflow = None
		if "workflow" in document:
			workflow = Workflow._FromYAML(document["workflow"], path, Base._KeyLine(document, "workflow"))

		includes = None
		if "include" in document:
			includes = Include._FromYAMLEntries(document["include"], path, Base._KeyLine(document, "include"))

		default = Default._FromYAML(document, path)

		inputs = None
		description = None
		if header is not None:
			spec = header["spec"]
			if not isinstance(spec, CommentedMap):
				ex = PipelineFileError("Key 'spec' of the header is not a mapping.", path, Base._KeyLine(header, "spec"))
				ex.add_note(f"Got type '{getFullyQualifiedName(spec)}'.")
				raise ex

			if "inputs" in spec:
				inputs = Input._FromYAMLMapping(spec["inputs"], None, path, Base._KeyLine(spec, "inputs"))

			if (description := spec.get("description", None)) is not None:
				description = Base._ToText(description)

		return cls(path, stages, variables, jobs, workflow, includes, default, inputs, description)

	@classmethod
	def _ResolveJobs(cls, document: CommentedMap, path: Path) -> dict[str, tuple[CommentedMap, list[str]]]:
		"""
		Resolve the ``!reference`` tags, the ``extends`` and the ``default`` of every job, as GitLab merges them.

		A ``!reference`` tag is replaced by the value it refers to; one in a list of a list's items is spliced into it.
		A job's mapping is the deep merge of the jobs it extends, in order, and of its own keys: mappings merge, other
		values - lists included - replace, and ``null`` removes a key. A job then gets every key of ``default``, and of
		the global keywords standing for it, which it doesn't set, unless ``inherit.default`` says otherwise.

		Every key keeps the line it is written at. What a job refers to, but the file doesn't have, is an error - unless
		the file includes files, which may have it: then it is skipped and reported in the job's ``unresolved`` list.

		:param document:           The configuration.
		:param path:               Path to the configuration file.
		:returns:                  Every job's merged mapping, and what it refers to but the file doesn't have, by name, in
		                           file order.
		:raises PipelineFileError: If a job is not a mapping.
		:raises PipelineFileError: If a job extends a job, or a ``!reference`` tag refers to a key, the file doesn't have,
		                           though it includes no files.
		:raises PipelineFileError: If jobs extend each other in a cycle, or ``extends`` or ``!reference`` tags nest too
		                           deep.
		"""
		hasIncludes = "include" in document
		unresolved: dict[str, list[str]] = {}

		def resolve(value: Any, owner: Nullable[str], depth: int) -> Any:
			"""
			Nested function for recursion, resolving the ``!reference`` tags in a value.

			:param value:              The value.
			:param owner:              Name of the job the value belongs to, or ``None`` for ``default``.
			:param depth:              How many references were followed to reach the value.
			:returns:                  The resolved value, or ``None`` for a reference of a job the file can't resolve.
			:raises PipelineFileError: If a reference can't be resolved, though the file includes no files, or it is in
			                           ``default``.
			:raises PipelineFileError: If references nest deeper than :data:`MAX_REFERENCE_DEPTH` levels.
			"""
			if isinstance(value, CommentedSeq) and value.tag.value == "!reference":
				segments = ", ".join(str(segment) for segment in value)
				where = "the default" if owner is None else f"job '{owner}'"
				if depth >= MAX_REFERENCE_DEPTH:
					raise PipelineFileError(
						f"Reference [{segments}] of {where} nests more than {MAX_REFERENCE_DEPTH} levels.", path, value.lc.line + 1
					)

				target: Any = document
				for segment in (str(segment) for segment in value):
					if not isinstance(target, CommentedMap) or segment not in target:
						if not hasIncludes or owner is None:
							raise PipelineFileError(
								f"Reference [{segments}] of {where} refers to a key the file doesn't have.", path, value.lc.line + 1
							)

						unresolved.setdefault(owner, []).append(f"!reference [{segments}]")
						return None

					target = target[segment]

				return resolve(target, owner, depth + 1)
			elif isinstance(value, CommentedSeq):
				items = CommentedSeq()
				items.lc.line = value.lc.line
				for index, item in enumerate(value):
					isReference = isinstance(item, CommentedSeq) and item.tag.value == "!reference"
					resolved = resolve(item, owner, depth)
					if isReference and resolved is None:
						continue
					elif isReference and isinstance(resolved, CommentedSeq):
						for position, element in enumerate(resolved):
							items.append(element)
							items.lc.add_kv_line_col(len(items) - 1, resolved.lc.data[position])
					else:
						items.append(resolved)
						items.lc.add_kv_line_col(len(items) - 1, value.lc.data[index])

				return items
			elif isinstance(value, CommentedMap):
				for key in list(value):
					isReference = isinstance(value[key], CommentedSeq) and value[key].tag.value == "!reference"
					resolved = resolve(value[key], owner, depth)
					if resolved is None and isReference:
						del value[key]
					else:
						value[key] = resolved

			return value

		def merge(target: CommentedMap, source: CommentedMap) -> None:
			"""
			Nested function for recursion, merging a mapping deeply into another, keeping each key's line.

			:param target: The mapping merged into.
			:param source: The mapping merged.
			"""
			for key, value in source.items():
				if value is None:
					target.pop(key, None)
					continue
				elif isinstance(value, CommentedMap) and isinstance(target.get(key, None), CommentedMap):
					merged = copy(target[key])
					merge(merged, value)
					value = merged

				target[key] = value
				if key in (source.lc.data or {}):
					target.lc.add_kv_line_col(key, source.lc.data[key])

		def copy(mapping: CommentedMap) -> CommentedMap:
			"""
			Nested function copying a mapping with the lines of its keys.

			:param mapping: The mapping.
			:returns:       The copy.
			"""
			result = CommentedMap(mapping)
			result.lc.line = mapping.lc.line
			result.lc.col = mapping.lc.col
			for key in mapping:
				if key in (mapping.lc.data or {}):
					result.lc.add_kv_line_col(key, mapping.lc.data[key])

			return result

		mappings: dict[str, CommentedMap] = {}
		for name, job in document.items():
			name = str(name)
			if name in RESERVED_KEYS:
				continue
			elif not isinstance(job, CommentedMap):
				ex = PipelineFileError(f"Job '{name}' is not a mapping.", path, Base._KeyLine(document, name))
				ex.add_note(f"Got type '{getFullyQualifiedName(job)}'.")
				raise ex

			mappings[name] = resolve(job, name, 0)

		defaults = CommentedMap()
		if isinstance(document.get("default", None), CommentedMap):
			defaults = copy(resolve(document["default"], None, 0))

		for key in Default._KEYS:
			if key in document and key not in defaults:
				defaults[key] = document[key]
				defaults.lc.add_kv_line_col(key, document.lc.data[key])

		def extended(name: str, chain: tuple[str, ...]) -> CommentedMap:
			"""
			Nested function for recursion, merging the jobs a job extends and its own keys.

			:param name:               Name of the job.
			:param chain:              Names of the jobs extending this one, outermost first.
			:returns:                  The merged mapping.
			:raises PipelineFileError: If a job extends a job the file doesn't have, though it includes no files.
			:raises PipelineFileError: If jobs extend each other in a cycle, or nest deeper than
			                           :data:`MAX_EXTENDS_DEPTH` levels.
			"""
			own = mappings[name]
			names = own.get("extends", ())
			names = [names] if isinstance(names, str) else list(names)
			result = CommentedMap()
			result.lc.line = own.lc.line
			result.lc.col = own.lc.col
			for base in (str(base) for base in names):
				if base in chain or base == name:
					cycle = " -> ".join((*chain, name, base))
					raise PipelineFileError(f"Jobs extend each other in a cycle: {cycle}.", path, Base._KeyLine(document, name))
				elif len(chain) >= MAX_EXTENDS_DEPTH:
					raise PipelineFileError(
						f"Job '{name}' extends more than {MAX_EXTENDS_DEPTH} levels.", path, Base._KeyLine(document, name)
					)
				elif base not in mappings:
					if not hasIncludes:
						raise PipelineFileError(
							f"Job '{name}' extends job '{base}', which the file doesn't have.", path, Base._KeyLine(own, "extends")
						)

					unresolved.setdefault(chain[0] if len(chain) > 0 else name, []).append(f"extends {base}")
					continue

				merge(result, extended(base, (*chain, name)))

			merge(result, own)
			return result

		resolved = {}
		for name in mappings:
			mapping = extended(name, ())
			inherit = mapping.get("inherit", None)
			inherited = inherit.get("default", True) if isinstance(inherit, CommentedMap) else True
			if not name.startswith(".") and inherited is not False:
				for key, value in defaults.items():
					if key not in mapping and (inherited is True or key in inherited):
						mapping[key] = value
						mapping.lc.add_kv_line_col(key, defaults.lc.data[key])

			resolved[name] = (mapping, unresolved.get(name, []))

		return resolved

	def _Validate(self) -> None:
		"""
		Validate the configuration read from a file.

		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
		:raises PipelineFileError: If a job needs a job the file doesn't have. |br|
		                           The note lists the file's jobs.
		:raises PipelineFileError: If the jobs need each other in a cycle.
		"""
		self._ValidateStages()
		self._ValidateNeeds()
		self._ValidateAcyclic()

	def _ValidateStages(self) -> None:
		"""
		Validate that every job is in a stage of the pipeline.

		A stage interpolating an input, as ``$[[ inputs.stage ]]``, is known when the file is included only.

		:raises PipelineFileError: If a job is in a stage the pipeline doesn't have. |br|
		                           The note lists the stages.
		"""
		stages = self.Stages
		for job in self._jobs.values():
			if job._stage not in stages and "$[[" not in job._stage:
				ex = PipelineFileError(
					f"Job '{job._name}' is in stage '{job._stage}', which isn't declared.", self._path, job._line
				)
				ex.add_note(f"Stages: {', '.join(stages)}.")
				raise ex

	def _ValidateNeeds(self) -> None:
		"""
		Validate that every job needs only jobs of the file, unless the need is optional or refers to another pipeline.

		A job's name interpolating an input is known when the file is included only.

		:raises PipelineFileError: If a job needs a job the file doesn't have. |br|
		                           The note lists the file's jobs.
		"""
		for job in self._jobs.values():
			if job._needs is None:
				continue

			for need in job._needs:
				if need._kind is not NeedKind.Job or need._optional or need._job in self._jobs or "$[[" in need._job:
					continue

				ex = PipelineFileError(
					f"Job '{job._name}' needs job '{need._job}', which the file doesn't have.", self._path, need._line
				)
				ex.add_note(f"Jobs: {', '.join(self._jobs)}.")
				raise ex

	def _ValidateAcyclic(self) -> None:
		"""
		Validate that the jobs don't need each other in a cycle.

		:raises PipelineFileError: If the jobs need each other in a cycle.
		"""
		finished: set[str] = set()
		stack:    list[str] = []

		def visit(job: Job) -> None:
			"""
			Nested function for recursion.

			:param job:                The job whose needs are followed.
			:raises PipelineFileError: If the job is reached again while its needs are followed.
			"""
			if job._name in finished:
				return
			elif job._name in stack:
				cycle = stack[stack.index(job._name):] + [job._name]
				raise PipelineFileError(f"Jobs need each other in a cycle: {' -> '.join(cycle)}.", self._path, job._line)

			stack.append(job._name)
			for needed in job.NeededJobs:
				visit(needed)
			stack.pop()
			finished.add(job._name)

		for job in self._jobs.values():
			visit(job)


@export
class Job(Base[PipelineFile]):
	"""
	A job of a configuration file, or a hidden job.

	A job runs :attr:`Script` in :attr:`Stage`, after the jobs of the earlier stages - or, with a ``needs`` key, after
	the jobs in :attr:`Needs`. A hidden job, whose name starts with a dot, isn't run; other jobs extend it.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = PipelineFile  #: A job is contained in a configuration file.

	_name:             str                   #: Name of the job, the key it is declared under.
	_stage:            str                   #: Stage the job runs in.
	_needs:            Nullable[list[Need]]  #: Entries of the job's ``needs``, or ``None`` without a ``needs`` key.
	_rules:            list[Rule]            #: Rules deciding whether the job is added to a pipeline.
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
	_inputs:           dict[str, Input]      #: Inputs of the job, by name, in file order.
	_parallel:         Nullable[Parallel]    #: The job's ``parallel``.
	_trigger:          Nullable[Trigger]     #: The pipeline the job starts.
	_extends:          tuple[str, ...]       #: Names of the jobs this job extends.
	_unresolved:       tuple[str, ...]       #: What the job refers to, but its file doesn't have.

	def __init__(
		self,
		name:             str,
		line:             int,
		stage:            str                          = "test",
		needs:            Nullable[Iterable[Need]]     = None,
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
		rules:            Nullable[Iterable[Rule]]     = None,
		inputs:           Nullable[Iterable[Input]]    = None,
		parallel:         Nullable[Parallel]           = None,
		trigger:          Nullable[Trigger]            = None,
		extends:          Nullable[Iterable[str]]      = None,
		unresolved:       Nullable[Iterable[str]]      = None,
		*,
		parent:           Nullable[PipelineFile]       = None
	) -> None:
		"""
		Initializes a job.

		A need, a variable, a rule, an input, a parallel or a trigger is attached by passing it, or by constructing it with
		the job as parent.

		:param name:             Name of the job, the key it is declared under.
		:param line:             Line the job's name is written at, starting at 1.
		:param stage:            Optional, stage the job runs in. Default: ``test``.
		:param needs:            Optional, entries of the job's ``needs``, which are attached to the job; an empty
		                         iterable for ``needs: []``. Default: ``None``, for a job without a ``needs`` key.
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
		:param rules:            Optional, rules deciding whether the job is added to a pipeline, which are attached to
		                         the job. Default: ``None``.
		:param inputs:           Optional, inputs of the job, which are attached to the job. Default: ``None``.
		:param parallel:         Optional, the job's ``parallel``, which is attached to the job. Default: ``None``.
		:param trigger:          Optional, the pipeline the job starts, which is attached to the job. Default: ``None``.
		:param extends:          Optional, names of the jobs this job extends. Default: ``None``.
		:param unresolved:       Optional, what the job refers to with ``extends`` or a ``!reference`` tag, but its file
		                         doesn't have. Default: ``None``.
		:param parent:           Optional, reference to the configuration file containing the job. Default: ``None``.
		:raises ValueError:      If parameter 'name' or 'stage' is ``None``.
		:raises TypeError:       If parameter 'name' or 'stage' is not of type :class:`str`.
		:raises ValueError:      If parameter 'name' or 'stage' is empty.
		:raises TypeError:       If parameter 'when' is not of type :class:`When`.
		:raises TypeError:       If parameter 'allowFailure' is not of type :class:`bool`.
		:raises TypeError:       If parameter 'image' or 'environment' is not of type :class:`str`.
		:raises TypeError:       If an element of parameter 'allowedExitCodes' is not of type :class:`int`.
		:raises TypeError:       If an element of parameter 'script', 'beforeScript', 'afterScript', 'services', 'tags',
		                         'extends' or 'unresolved' is not of type :class:`str`.
		:raises TypeError:       If an element of parameter 'needs' is not of type :class:`Need`.
		:raises TypeError:       If an element of parameter 'variables' is not of type :class:`Variable`.
		:raises TypeError:       If an element of parameter 'rules' is not of type :class:`Rule`.
		:raises TypeError:       If an element of parameter 'inputs' is not of type :class:`Input`.
		:raises TypeError:       If parameter 'parallel' is not of type :class:`Parallel`.
		:raises TypeError:       If parameter 'trigger' is not of type :class:`Trigger`.
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
		self._extends =      () if extends is None else tuple(extends)
		self._unresolved =   () if unresolved is None else tuple(unresolved)
		for parameterName, texts in (
			("script",       self._script),
			("beforeScript", self._beforeScript),
			("afterScript",  self._afterScript),
			("services",     self._services),
			("tags",         self._tags),
			("extends",      self._extends),
			("unresolved",   self._unresolved)
		):
			for text in texts:
				if not isinstance(text, str):
					ex = TypeError(f"An element of parameter '{parameterName}' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
					raise ex

		self._name =         name
		self._stage =        stage
		self._needs =        None
		self._rules =        []
		self._inputs =       {}
		self._parallel =     None
		self._trigger =      None
		self._when =         when
		self._allowFailure = allowFailure
		self._image =        image
		self._environment =  environment
		self._variables =    {}

		if needs is not None:
			self._needs = []
			for need in needs:
				if not isinstance(need, Need):
					ex = TypeError("An element of parameter 'needs' is not of type 'Need'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(need)}'.")
					raise ex

				self._needs.append(need)
				need.Parent = self

		if variables is not None:
			for variable in variables:
				if not isinstance(variable, Variable):
					ex = TypeError("An element of parameter 'variables' is not of type 'Variable'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(variable)}'.")
					raise ex

				self._variables[variable._name] = variable
				variable.Parent = self

		if rules is not None:
			for rule in rules:
				if not isinstance(rule, Rule):
					ex = TypeError("An element of parameter 'rules' is not of type 'Rule'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(rule)}'.")
					raise ex

				self._rules.append(rule)
				rule.Parent = self

		if inputs is not None:
			for parameter in inputs:
				if not isinstance(parameter, Input):
					ex = TypeError("An element of parameter 'inputs' is not of type 'Input'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(parameter)}'.")
					raise ex

				self._inputs[parameter._name] = parameter
				parameter.Parent = self

		for parameterName, element, elementClass in (
			("parallel", parallel, Parallel),
			("trigger",  trigger,  Trigger)
		):
			if element is not None and not isinstance(element, elementClass):
				ex = TypeError(f"Parameter '{parameterName}' is not of type '{elementClass.__name__}'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(element)}'.")
				raise ex

		if parallel is not None:
			self._parallel = parallel
			parallel.Parent = self

		if trigger is not None:
			self._trigger = trigger
			trigger.Parent = self

		if parent is not None:
			(parent._hiddenJobs if self.IsHidden else parent._jobs)[name] = self

	@Base.Parent.setter
	def Parent(self, value: PipelineFile) -> None:
		Base.Parent.fset(self, value)

		for need in () if self._needs is None else self._needs:
			need.Parent = self

		for variable in self._variables.values():
			variable.Parent = self

		for rule in self._rules:
			rule.Parent = self

		for parameter in self._inputs.values():
			parameter.Parent = self

		for element in (self._parallel, self._trigger):
			if element is not None:
				element.Parent = self

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
	def Extends(self) -> tuple[str, ...]:
		"""
		Read-only property to access the names of the jobs this job extends (:attr:`_extends`).

		The job's keys are the merge of theirs and its own already.

		:returns: The names, in the order ``extends`` lists them.
		"""
		return self._extends

	@readonly
	def Unresolved(self) -> tuple[str, ...]:
		"""
		Read-only property to access what the job refers to, but its file doesn't have (:attr:`_unresolved`).

		A file including other files may extend or refer to their jobs; then the job lacks what they contribute.

		:returns: The jobs it extends and the ``!reference`` tags, as ``extends .base`` and ``!reference [.setup,
		          script]``, or an empty tuple if the job is complete.
		"""
		return self._unresolved

	@readonly
	def Stage(self) -> str:
		"""
		Read-only property to access the stage the job runs in (:attr:`_stage`).

		:returns: The stage, ``test`` for a job that doesn't name one.
		"""
		return self._stage

	@readonly
	def Needs(self) -> Nullable[tuple[Need, ...]]:
		"""
		Read-only property to return the entries of the job's ``needs`` (:attr:`_needs`).

		:returns: The entries, in file order; an empty tuple for ``needs: []``; or ``None`` for a job without a ``needs``
		          key, which runs after the jobs of the earlier stages.
		"""
		return None if self._needs is None else tuple(self._needs)

	@readonly
	def NeededJobs(self) -> tuple[Job, ...]:
		"""
		Read-only property to return the jobs of the same file this job needs, as its ``needs`` names them.

		An optional need of a job the file doesn't have is skipped, as are needs of other pipelines.

		:returns: The jobs, in the order the ``needs`` key lists them.
		"""
		if self._needs is None or self._pipelineFile is None:
			return ()

		jobs = self._pipelineFile._jobs
		return tuple(jobs[need._job] for need in self._needs if need._kind is NeedKind.Job and need._job in jobs)

	@readonly
	def Rules(self) -> list[Rule]:
		"""
		Read-only property to access the rules deciding whether the job is added to a pipeline (:attr:`_rules`).

		:returns: The rules, in the order GitLab evaluates them.
		"""
		return self._rules

	@readonly
	def Inputs(self) -> dict[str, Input]:
		"""
		Read-only property to access the inputs of the job (:attr:`_inputs`).

		:returns: The inputs, by name, in file order.
		"""
		return self._inputs

	@readonly
	def Parallel(self) -> Nullable[Parallel]:
		"""
		Read-only property to access the job's ``parallel`` (:attr:`_parallel`).

		:returns: How often the job runs, or its matrix, or ``None`` for a job running once.
		"""
		return self._parallel

	@readonly
	def Trigger(self) -> Nullable[Trigger]:
		"""
		Read-only property to access the pipeline the job starts (:attr:`_trigger`).

		:returns: The trigger, or ``None`` for a job running a script.
		"""
		return self._trigger

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
	def _Lines(value: Any, key: str, owner: str, mapping: CommentedMap, path: Path) -> list[str]:
		"""
		Read a script key: a line, or a list of lines and nested lists of lines.

		:param value:              The key's value.
		:param key:                The key, for a message.
		:param owner:              The element holding the key, for a message, as ``job 'build'``.
		:param mapping:            The job's mapping, for the key's line.
		:param path:               Path to the configuration file.
		:returns:                  The lines, nested lists flattened.
		:raises PipelineFileError: If the value is a mapping, or a list holds a mapping.
		"""
		if isinstance(value, CommentedSeq):
			lines = []
			for item in value:
				lines.extend(Job._Lines(item, key, owner, mapping, path))

			return lines
		elif isinstance(value, CommentedMap):
			ex = PipelineFileError(f"Key '{key}' of {owner} is not a script.", path, Base._KeyLine(mapping, key))
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
	def _FromYAML(
		cls,
		name:       str,
		mapping:    CommentedMap,
		path:       Path,
		line:       int,
		unresolved: Nullable[Iterable[str]] = None
	) -> Self:
		"""
		Build a job and the elements it contains from its mapping in the configuration file.

		:param name:               Name of the job.
		:param mapping:            The job's mapping, merged with the jobs it extends and the default.
		:param path:               Path to the configuration file.
		:param line:               Line the job's name is written at, starting at 1.
		:param unresolved:         Optional, what the job refers to, but the file doesn't have. Default: ``None``.
		:returns:                  The job.
		:raises PipelineFileError: If key ``when`` is not a value GitLab knows. |br|
		                           The note lists the allowed values.
		:raises PipelineFileError: If a key of the job holds a value of the wrong kind.
		:raises PipelineFileError: If an entry of key ``needs`` is malformed.
		"""
		needs = None
		if "needs" in mapping:
			needs = Need._FromYAMLEntries(mapping["needs"], name, path, Base._KeyLine(mapping, "needs"))

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

		rules = None
		if "rules" in mapping:
			rules = Rule._FromYAMLEntries(mapping["rules"], f"job '{name}'", path, Base._KeyLine(mapping, "rules"))

		inputs = None
		if "inputs" in mapping:
			inputs = Input._FromYAMLMapping(mapping["inputs"], name, path, Base._KeyLine(mapping, "inputs"))

		parallel = None
		if "parallel" in mapping:
			parallel = Parallel._FromYAML(mapping["parallel"], f"job '{name}'", path, Base._KeyLine(mapping, "parallel"))

		trigger = None
		if "trigger" in mapping:
			trigger = Trigger._FromYAML(mapping["trigger"], name, path, Base._KeyLine(mapping, "trigger"))

		extends = mapping.get("extends", ())
		extends = [extends] if isinstance(extends, str) else extends
		stage = mapping.get("stage", None)

		return cls(
			name, line,
			stage="test" if stage is None else Base._ToText(stage),
			needs=needs,
			when=when,
			allowFailure=allowFailure,
			allowedExitCodes=exitCodes,
			script=cls._Lines(mapping.get("script", None), "script", f"job '{name}'", mapping, path),
			beforeScript=cls._Lines(mapping.get("before_script", None), "before_script", f"job '{name}'", mapping, path),
			afterScript=cls._Lines(mapping.get("after_script", None), "after_script", f"job '{name}'", mapping, path),
			image=cls._Name(mapping.get("image", None)),
			services=services,
			tags=tags,
			environment=cls._Name(mapping.get("environment", None)),
			variables=variables,
			rules=rules,
			inputs=inputs,
			parallel=parallel,
			trigger=trigger,
			extends=[Base._ToText(base) for base in extends],
			unresolved=unresolved
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


@export
class Need(Base[Job]):
	"""
	An entry of a job's ``needs``.

	An entry names a job of the same pipeline, as a string or as ``job`` of a mapping; a job of another pipeline of
	the parent-child hierarchy, with ``pipeline`` and ``job``; a job of another project's pipeline, with ``project``,
	``job`` and ``ref``; or, with ``pipeline`` only, another project's pipeline, whose status the job mirrors.
	:attr:`Kind` says which.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = Job  #: A need is an entry of a job's ``needs``.

	_kind:      NeedKind            #: What the entry refers to.
	_job:       Nullable[str]       #: Name of the needed job.
	_artifacts: bool                #: ``True``, if the needed job's artifacts are downloaded.
	_optional:  bool                #: ``True``, if the needed job may be missing in the pipeline.
	_pipeline:  Nullable[str]       #: The other pipeline: its ID, or the project whose pipeline's status is mirrored.
	_project:   Nullable[str]       #: Path of the other project.
	_ref:       Nullable[str]       #: Reference of the other project, whose latest pipeline's artifacts are downloaded.
	_parallel:  Nullable[Parallel]  #: The matrix instances of the needed job, which are needed.

	_KEYS: ClassVar[tuple[str, ...]] = (
		"job", "artifacts", "optional", "pipeline", "project", "ref", "parallel"
	)  #: Keys of an entry as mapping.

	def __init__(
		self,
		job:       Nullable[str],
		line:      int,
		kind:      NeedKind           = NeedKind.Job,
		artifacts: bool               = True,
		optional:  bool               = False,
		pipeline:  Nullable[str]      = None,
		project:   Nullable[str]      = None,
		ref:       Nullable[str]      = None,
		parallel:  Nullable[Parallel] = None,
		*,
		parent:    Nullable[Job]      = None
	) -> None:
		"""
		Initializes an entry of a job's ``needs``.

		:param job:         Name of the needed job, or ``None`` for a need of kind :attr:`NeedKind.PipelineStatus`.
		:param line:        Line the entry is written at, starting at 1.
		:param kind:        Optional, what the entry refers to. Default: a job of the same pipeline.
		:param artifacts:   Optional, ``True``, if the needed job's artifacts are downloaded. Default: ``True``.
		:param optional:    Optional, ``True``, if the needed job may be missing in the pipeline. Default: ``False``.
		:param pipeline:    Optional, the other pipeline: its ID, or the project whose pipeline's status is mirrored.
		                    Default: ``None``.
		:param project:     Optional, path of the other project. Default: ``None``.
		:param ref:         Optional, reference of the other project. Default: ``None``.
		:param parallel:    Optional, the matrix instances of the needed job, which are needed, which is attached to
		                    the need. Default: ``None``, for every instance.
		:param parent:      Optional, reference to the job whose ``needs`` holds the entry. Default: ``None``.
		:raises ValueError: If parameter 'kind' is ``None``.
		:raises TypeError:  If parameter 'kind' is not of type :class:`NeedKind`.
		:raises TypeError:  If parameter 'job', 'pipeline', 'project' or 'ref' is not of type :class:`str`.
		:raises TypeError:  If parameter 'artifacts' or 'optional' is not of type :class:`bool`.
		:raises ValueError: If parameter 'job' is ``None``, but the kind names a job.
		:raises ValueError: If parameter 'pipeline' is ``None``, but the kind refers to another pipeline.
		:raises ValueError: If parameter 'project' or 'ref' is ``None``, but the kind refers to another project's job.
		:raises TypeError:  If parameter 'parallel' is not of type :class:`Parallel`.
		"""
		super().__init__(line, parent=parent)

		if kind is None:
			raise ValueError("Parameter 'kind' is None.")
		elif not isinstance(kind, NeedKind):
			ex = TypeError("Parameter 'kind' is not of type 'NeedKind'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(kind)}'.")
			raise ex

		for parameterName, text in (
			("job",      job),
			("pipeline", pipeline),
			("project",  project),
			("ref",      ref)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		for parameterName, flag in (
			("artifacts", artifacts),
			("optional",  optional)
		):
			if not isinstance(flag, bool):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'bool'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(flag)}'.")
				raise ex

		for parameterName, text, kinds in (
			("job",      job,      (NeedKind.Job, NeedKind.PipelineJob, NeedKind.ProjectJob)),
			("pipeline", pipeline, (NeedKind.PipelineJob, NeedKind.PipelineStatus)),
			("project",  project,  (NeedKind.ProjectJob, )),
			("ref",      ref,      (NeedKind.ProjectJob, ))
		):
			if text is None and kind in kinds:
				ex = ValueError(f"Parameter '{parameterName}' is None.")
				ex.add_note(f"A need of kind '{kind.value}' needs it.")
				raise ex

		self._kind =      kind
		self._job =       job
		self._artifacts = artifacts
		self._optional =  optional
		self._pipeline =  pipeline
		self._project =   project
		self._ref =       ref
		self._parallel =  None

		if parallel is not None:
			if not isinstance(parallel, Parallel):
				ex = TypeError("Parameter 'parallel' is not of type 'Parallel'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(parallel)}'.")
				raise ex

			self._parallel = parallel
			parallel.Parent = self

		if parent is not None:
			if parent._needs is None:
				parent._needs = []

			parent._needs.append(self)

	@Base.Parent.setter
	def Parent(self, value: Job) -> None:
		Base.Parent.fset(self, value)

		if self._parallel is not None:
			self._parallel.Parent = self

	@readonly
	def Parallel(self) -> Nullable[Parallel]:
		"""
		Read-only property to access the matrix instances of the needed job, which are needed (:attr:`_parallel`).

		:returns: The instances' matrix, or ``None`` if every instance is needed.
		"""
		return self._parallel

	@readonly
	def Kind(self) -> NeedKind:
		"""
		Read-only property to access what the entry refers to (:attr:`_kind`).

		:returns: The kind of the need.
		"""
		return self._kind

	@readonly
	def JobName(self) -> Nullable[str]:
		"""
		Read-only property to access the name of the needed job (:attr:`_job`).

		:returns: Name of the job, or ``None`` for a need mirroring another pipeline's status.
		"""
		return self._job

	@readonly
	def NeededJob(self) -> Nullable[Job]:
		"""
		Read-only property to return the needed job of the same file.

		:returns: The job, or ``None`` for a need of another pipeline, or of a job the file doesn't have.
		"""
		if self._kind is not NeedKind.Job or self._pipelineFile is None:
			return None

		return self._pipelineFile._jobs.get(self._job, None)

	@readonly
	def Artifacts(self) -> bool:
		"""
		Read-only property to access whether the needed job's artifacts are downloaded (:attr:`_artifacts`).

		:returns: ``True``, if the artifacts are downloaded.
		"""
		return self._artifacts

	@readonly
	def IsOptional(self) -> bool:
		"""
		Read-only property to access whether the needed job may be missing in the pipeline (:attr:`_optional`).

		:returns: ``True``, if the need is optional.
		"""
		return self._optional

	@readonly
	def Pipeline(self) -> Nullable[str]:
		"""
		Read-only property to access the other pipeline (:attr:`_pipeline`).

		:returns: The pipeline's ID, as ``$PARENT_PIPELINE_ID``, or the project whose pipeline's status is mirrored, or
		          ``None`` for a need of the same pipeline or of another project's job.
		"""
		return self._pipeline

	@readonly
	def Project(self) -> Nullable[str]:
		"""
		Read-only property to access the path of the other project (:attr:`_project`).

		:returns: The project's path, or ``None`` for a need of a job of the same project.
		"""
		return self._project

	@readonly
	def Ref(self) -> Nullable[str]:
		"""
		Read-only property to access the reference of the other project (:attr:`_ref`).

		:returns: The reference, or ``None`` for a need of a job of the same project.
		"""
		return self._ref

	def __str__(self) -> str:
		"""
		Return the needed job's name, or the pipeline whose status is mirrored.

		:returns: The job's name, prefixed by the project for another project's job.
		"""
		if self._kind is NeedKind.PipelineStatus:
			return f"pipeline {self._pipeline}"
		elif self._kind is NeedKind.ProjectJob:
			return f"{self._project}: {self._job}"

		return self._job

	@classmethod
	def _FromYAML(cls, entry: Any, jobName: str, path: Path, line: int) -> Self:
		"""
		Read an entry of a job's ``needs``: a job's name, or a mapping of the keys in :attr:`_KEYS`.

		:param entry:              The entry.
		:param jobName:            Name of the job, whose ``needs`` holds the entry, for a message.
		:param path:               Path to the configuration file.
		:param line:               Line the entry is written at, starting at 1.
		:returns:                  The need.
		:raises PipelineFileError: If the entry is neither a job's name nor a mapping.
		:raises PipelineFileError: If the mapping has a key GitLab doesn't know for a need. |br|
		                           The note lists the allowed keys.
		:raises PipelineFileError: If key ``artifacts`` or ``optional`` is not a boolean.
		:raises PipelineFileError: If the mapping lacks a key its kind needs: ``job``, or ``ref`` with ``project``.
		"""
		if isinstance(entry, CommentedSeq) or entry is None:
			ex = PipelineFileError(f"Need of job '{jobName}' is neither a job's name nor a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(entry)}'.")
			raise ex
		elif not isinstance(entry, CommentedMap):
			return cls(Base._ToText(entry), line)

		for key in entry:
			if key not in cls._KEYS:
				ex = PipelineFileError(f"Need of job '{jobName}' has unknown key '{key}'.", path, Base._KeyLine(entry, key))
				ex.add_note(f"Allowed keys: {', '.join(cls._KEYS)}.")
				raise ex

		flags = {}
		for key, default in (
			("artifacts", True),
			("optional",  False)
		):
			flags[key] = Base._ToPython(entry.get(key, default))
			if not isinstance(flags[key], bool):
				ex = PipelineFileError(
					f"Key '{key}' of a need of job '{jobName}' is not a boolean.", path, Base._KeyLine(entry, key)
				)
				ex.add_note(f"Got '{flags[key]}'.")
				raise ex

		texts = {}
		for key in ("job", "pipeline", "project", "ref"):
			texts[key] = None if entry.get(key, None) is None else Base._ToText(entry[key])

		if texts["project"] is not None:
			kind = NeedKind.ProjectJob
		elif texts["pipeline"] is not None:
			kind = NeedKind.PipelineStatus if texts["job"] is None else NeedKind.PipelineJob
		else:
			kind = NeedKind.Job

		if texts["job"] is None and kind is not NeedKind.PipelineStatus:
			raise PipelineFileError(f"Need of job '{jobName}' has no 'job' key.", path, line)
		elif texts["ref"] is None and kind is NeedKind.ProjectJob:
			raise PipelineFileError(f"Need of job '{jobName}' with key 'project' has no 'ref' key.", path, line)

		parallel = None
		if "parallel" in entry:
			keyLine = Base._KeyLine(entry, "parallel")
			parallel = Parallel._FromYAML(entry["parallel"], f"a need of job '{jobName}'", path, keyLine)
			if parallel._count is not None:
				raise PipelineFileError(f"Key 'parallel' of a need of job '{jobName}' has no 'matrix' key.", path, line)

		return cls(
			texts["job"], line, kind, flags["artifacts"], flags["optional"],
			texts["pipeline"], texts["project"], texts["ref"], parallel
		)

	@classmethod
	def _FromYAMLEntries(cls, value: Any, jobName: str, path: Path, line: int) -> list[Self]:
		"""
		Read a job's ``needs``: a list of entries, or a single mapping, as ``pipeline: other/project``.

		:param value:              The key's value.
		:param jobName:            Name of the job, for a message.
		:param path:               Path to the configuration file.
		:param line:               Line the ``needs`` key is written at, starting at 1.
		:returns:                  The needs, in file order.
		:raises PipelineFileError: If the value is neither a list nor a mapping.
		:raises PipelineFileError: If an entry is malformed.
		"""
		if isinstance(value, CommentedMap):
			return [cls._FromYAML(value, jobName, path, line)]
		elif not isinstance(value, CommentedSeq):
			ex = PipelineFileError(f"Key 'needs' of job '{jobName}' is neither a list nor a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
			raise ex

		return [cls._FromYAML(entry, jobName, path, Base._ItemLine(value, index)) for index, entry in enumerate(value)]


@export
class Workflow(Base[PipelineFile]):
	"""The ``workflow`` key of a configuration file: the pipeline's name and the rules deciding whether it is created."""

	_PARENT_TYPE: ClassVar[ParentTypes] = PipelineFile  #: A workflow belongs to a configuration file.

	_name:  Nullable[str]  #: Name of the pipeline.
	_rules: list[Rule]     #: Rules deciding whether a pipeline is created.

	def __init__(
		self,
		line:   int,
		name:   Nullable[str]            = None,
		rules:  Nullable[Iterable[Rule]] = None,
		*,
		parent: Nullable[PipelineFile]   = None
	) -> None:
		"""
		Initializes the ``workflow`` key.

		:param line:       Line the ``workflow`` key is written at, starting at 1.
		:param name:       Optional, name of the pipeline. Default: ``None``.
		:param rules:      Optional, rules deciding whether a pipeline is created, which are attached to the workflow.
		                   Default: ``None``.
		:param parent:     Optional, reference to the configuration file. Default: ``None``.
		:raises TypeError: If parameter 'name' is not of type :class:`str`.
		:raises TypeError: If an element of parameter 'rules' is not of type :class:`Rule`.
		"""
		super().__init__(line, parent=parent)

		if name is not None and not isinstance(name, str):
			ex = TypeError("Parameter 'name' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(name)}'.")
			raise ex

		self._name =  name
		self._rules = []

		if rules is not None:
			for rule in rules:
				if not isinstance(rule, Rule):
					ex = TypeError("An element of parameter 'rules' is not of type 'Rule'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(rule)}'.")
					raise ex

				self._rules.append(rule)
				rule.Parent = self

		if parent is not None:
			parent._workflow = self

	@Base.Parent.setter
	def Parent(self, value: PipelineFile) -> None:
		Base.Parent.fset(self, value)

		for rule in self._rules:
			rule.Parent = self

	@readonly
	def Name(self) -> Nullable[str]:
		"""
		Read-only property to access the pipeline's name (:attr:`_name`).

		:returns: The ``name`` key, as written, or ``None`` if the workflow gives none.
		"""
		return self._name

	@readonly
	def Rules(self) -> list[Rule]:
		"""
		Read-only property to access the rules deciding whether a pipeline is created (:attr:`_rules`).

		:returns: The rules, in the order GitLab evaluates them.
		"""
		return self._rules

	@classmethod
	def _FromYAML(cls, mapping: Any, path: Path, line: int) -> Self:
		"""
		Read the ``workflow`` key.

		:param mapping:            The key's value.
		:param path:               Path to the configuration file.
		:param line:               Line the ``workflow`` key is written at, starting at 1.
		:returns:                  The workflow.
		:raises PipelineFileError: If the value is not a mapping.
		:raises PipelineFileError: If a rule is malformed.
		"""
		if not isinstance(mapping, CommentedMap):
			ex = PipelineFileError("Key 'workflow' is not a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(mapping)}'.")
			raise ex

		rules = None
		if "rules" in mapping:
			rules = Rule._FromYAMLEntries(mapping["rules"], "the workflow", path, Base._KeyLine(mapping, "rules"))

		name = mapping.get("name", None)
		return cls(line, None if name is None else Base._ToText(name), rules)


@export
class Trigger(Base[Job]):
	"""
	A job's ``trigger``: the child pipeline, or the other project's pipeline, the job starts.

	A child pipeline runs the configuration of the files in :attr:`Includes`; another project's pipeline runs that
	project's configuration on :attr:`Branch`.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = Job  #: A trigger belongs to a job.

	_project:  Nullable[str]              #: Path of the other project, whose pipeline is started.
	_branch:   Nullable[str]              #: Branch of the other project.
	_strategy: Nullable[TriggerStrategy]  #: How the job's status follows the started pipeline.
	_includes: list[Include]              #: Files of the child pipeline's configuration.

	def __init__(
		self,
		line:     int,
		project:  Nullable[str]               = None,
		branch:   Nullable[str]               = None,
		strategy: Nullable[TriggerStrategy]   = None,
		includes: Nullable[Iterable[Include]] = None,
		*,
		parent:   Nullable[Job]               = None
	) -> None:
		"""
		Initializes a job's ``trigger``.

		:param line:       Line the ``trigger`` key is written at, starting at 1.
		:param project:    Optional, path of the other project, whose pipeline is started. Default: ``None``.
		:param branch:     Optional, branch of the other project. Default: ``None``, for its default branch.
		:param strategy:   Optional, how the job's status follows the started pipeline. Default: ``None``, for a job
		                   succeeding as soon as the pipeline is created.
		:param includes:   Optional, files of the child pipeline's configuration, which are attached to the trigger.
		                   Default: ``None``.
		:param parent:     Optional, reference to the job. Default: ``None``.
		:raises TypeError: If parameter 'project' or 'branch' is not of type :class:`str`.
		:raises TypeError: If parameter 'strategy' is not of type :class:`TriggerStrategy`.
		:raises TypeError: If an element of parameter 'includes' is not of type :class:`Include`.
		"""
		super().__init__(line, parent=parent)

		for parameterName, text in (
			("project", project),
			("branch",  branch)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		if strategy is not None and not isinstance(strategy, TriggerStrategy):
			ex = TypeError("Parameter 'strategy' is not of type 'TriggerStrategy'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(strategy)}'.")
			raise ex

		self._project =  project
		self._branch =   branch
		self._strategy = strategy
		self._includes = []

		if includes is not None:
			for include in includes:
				if not isinstance(include, Include):
					ex = TypeError("An element of parameter 'includes' is not of type 'Include'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(include)}'.")
					raise ex

				self._includes.append(include)
				include.Parent = self

		if parent is not None:
			parent._trigger = self

	@Base.Parent.setter
	def Parent(self, value: Job) -> None:
		Base.Parent.fset(self, value)

		for include in self._includes:
			include.Parent = self

	@readonly
	def Project(self) -> Nullable[str]:
		"""
		Read-only property to access the path of the other project, whose pipeline is started (:attr:`_project`).

		:returns: The project's path, or ``None`` for a child pipeline.
		"""
		return self._project

	@readonly
	def Branch(self) -> Nullable[str]:
		"""
		Read-only property to access the branch of the other project (:attr:`_branch`).

		:returns: The branch, or ``None`` for the project's default branch.
		"""
		return self._branch

	@readonly
	def Strategy(self) -> Nullable[TriggerStrategy]:
		"""
		Read-only property to access how the job's status follows the started pipeline (:attr:`_strategy`).

		:returns: The strategy, or ``None`` if the trigger doesn't say.
		"""
		return self._strategy

	@readonly
	def Includes(self) -> list[Include]:
		"""
		Read-only property to access the files of the child pipeline's configuration (:attr:`_includes`).

		:returns: The files, in file order; empty for another project's pipeline.
		"""
		return self._includes

	@readonly
	def IsChildPipeline(self) -> bool:
		"""
		Read-only property to return whether the job starts a child pipeline.

		:returns: ``True``, if the trigger includes files; ``False`` for another project's pipeline.
		"""
		return len(self._includes) > 0

	@classmethod
	def _FromYAML(cls, value: Any, jobName: str, path: Path, line: int) -> Self:
		"""
		Read a job's ``trigger``: another project's path, or a mapping with ``include`` or ``project``.

		:param value:              The key's value.
		:param jobName:            Name of the job, for a message.
		:param path:               Path to the configuration file.
		:param line:               Line the ``trigger`` key is written at, starting at 1.
		:returns:                  The trigger.
		:raises PipelineFileError: If the value is neither a project's path nor a mapping with ``include`` or
		                           ``project``.
		:raises PipelineFileError: If key ``strategy`` is not a value GitLab knows. |br|
		                           The note lists the allowed values.
		:raises PipelineFileError: If an include is malformed.
		"""
		if isinstance(value, (str, ScalarString)):
			return cls(line, project=Base._ToText(value))
		elif not isinstance(value, CommentedMap) or ("include" not in value and "project" not in value):
			ex = PipelineFileError(
				f"Key 'trigger' of job '{jobName}' is neither a project nor a mapping with 'include' or 'project'.", path, line
			)
			ex.add_note(f"Got '{Base._ToPython(value)}'.")
			raise ex

		strategy = None
		if (strategyValue := value.get("strategy", None)) is not None:
			try:
				strategy = TriggerStrategy.Parse(Base._ToText(strategyValue))
			except ValueError as cause:
				ex = PipelineFileError(
					f"Key 'strategy' of the trigger of job '{jobName}' is not a known value.",
					path, Base._KeyLine(value, "strategy")
				)
				ex.add_note(f"Got '{strategyValue}'.")
				ex.add_note(f"Allowed values: {', '.join(member.value for member in TriggerStrategy)}.")
				raise ex from cause

		includes = None
		if "include" in value:
			includes = Include._FromYAMLEntries(value["include"], path, Base._KeyLine(value, "include"))

		project = value.get("project", None)
		branch =  value.get("branch", None)
		return cls(
			line,
			project=None if project is None else Base._ToText(project),
			branch=None if branch is None else Base._ToText(branch),
			strategy=strategy,
			includes=includes
		)


@export
class Include(Base[Union[PipelineFile, Trigger]]):
	"""
	An entry of ``include``, which adds the configuration of other files.

	:attr:`Kind` says where the files come from, :attr:`Location` names them: a path of the same repository, a URL, a
	template's name, a component's reference, the path of another project, whose files are in :attr:`Files`, or the
	artifact of the job :attr:`ArtifactJob`.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = (PipelineFile, Trigger)  #: Included by a configuration file or a trigger.

	_kind:     IncludeKind        #: Where the included files come from.
	_location: str                #: Path, URL, template's name, component's reference, or project's path.
	_ref:      Nullable[str]      #: Reference of the project the files are read from.
	_files:    tuple[str, ...]    #: Paths of the files of another project.
	_job:      Nullable[str]      #: Name of the job, whose artifact is included.
	_inputs:   dict[str, ValueT]  #: Inputs passed to the included files, by name.
	_rules:    list[Rule]         #: Rules deciding whether the files are included.

	_KINDS: ClassVar[tuple[str, ...]] = tuple(member.value for member in IncludeKind)  #: Keys naming an include's kind.

	def __init__(
		self,
		kind:     IncludeKind,
		location: str,
		line:     int,
		files:    Nullable[Iterable[str]]                = None,
		ref:      Nullable[str]                          = None,
		inputs:   Nullable[Mapping[str, ValueT]]         = None,
		rules:    Nullable[Iterable[Rule]]               = None,
		job:      Nullable[str]                          = None,
		*,
		parent:   Nullable[Union[PipelineFile, Trigger]] = None
	) -> None:
		"""
		Initializes an entry of ``include``.

		:param kind:        Where the included files come from.
		:param location:    Path, URL, template's name, component's reference, or - for another project - its path.
		:param line:        Line the entry is written at, starting at 1.
		:param files:       Optional, paths of the files of another project. Default: ``None``.
		:param ref:         Optional, reference of the project the files are read from. Default: ``None``.
		:param inputs:      Optional, inputs passed to the included files, by name. Default: ``None``.
		:param rules:       Optional, rules deciding whether the files are included, which are attached to the entry.
		                    Default: ``None``.
		:param job:         Optional, name of the job, whose artifact is included. Default: ``None``.
		:param parent:      Optional, reference to the configuration file or the trigger. Default: ``None``.
		:raises ValueError: If parameter 'kind' or 'location' is ``None``.
		:raises TypeError:  If parameter 'kind' is not of type :class:`IncludeKind`.
		:raises TypeError:  If parameter 'location', 'ref' or 'job' is not of type :class:`str`.
		:raises ValueError: If parameter 'location' is empty.
		:raises TypeError:  If an element of parameter 'files' is not of type :class:`str`.
		:raises TypeError:  If an element of parameter 'rules' is not of type :class:`Rule`.
		"""
		super().__init__(line, parent=parent)

		if kind is None:
			raise ValueError("Parameter 'kind' is None.")
		elif not isinstance(kind, IncludeKind):
			ex = TypeError("Parameter 'kind' is not of type 'IncludeKind'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(kind)}'.")
			raise ex

		if location is None:
			raise ValueError("Parameter 'location' is None.")
		elif not isinstance(location, str):
			ex = TypeError("Parameter 'location' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(location)}'.")
			raise ex
		elif location == "":
			raise ValueError("Parameter 'location' is empty.")

		for parameterName, text in (
			("ref", ref),
			("job", job)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		self._files = () if files is None else tuple(files)
		for file in self._files:
			if not isinstance(file, str):
				ex = TypeError("An element of parameter 'files' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(file)}'.")
				raise ex

		self._kind =     kind
		self._location = location
		self._ref =      ref
		self._job =      job
		self._inputs =   {} if inputs is None else dict(inputs)
		self._rules =    []

		if rules is not None:
			for rule in rules:
				if not isinstance(rule, Rule):
					ex = TypeError("An element of parameter 'rules' is not of type 'Rule'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(rule)}'.")
					raise ex

				self._rules.append(rule)
				rule.Parent = self

		if parent is not None:
			parent._includes.append(self)

	@Base.Parent.setter
	def Parent(self, value: PipelineFile) -> None:
		Base.Parent.fset(self, value)

		for rule in self._rules:
			rule.Parent = self

	@readonly
	def Kind(self) -> IncludeKind:
		"""
		Read-only property to access where the included files come from (:attr:`_kind`).

		:returns: The kind of the include.
		"""
		return self._kind

	@readonly
	def Location(self) -> str:
		"""
		Read-only property to access what the entry includes (:attr:`_location`).

		:returns: A path, a URL, a template's name, a component's reference, or another project's path, as written.
		"""
		return self._location

	@readonly
	def Ref(self) -> Nullable[str]:
		"""
		Read-only property to access the reference of the project the files are read from (:attr:`_ref`).

		:returns: The ``ref`` key, or ``None`` - the project's default branch then.
		"""
		return self._ref

	@readonly
	def Files(self) -> tuple[str, ...]:
		"""
		Read-only property to access the paths of the files of another project (:attr:`_files`).

		:returns: The paths of ``file``, in file order.
		"""
		return self._files

	@readonly
	def ArtifactJob(self) -> Nullable[str]:
		"""
		Read-only property to access the name of the job, whose artifact is included (:attr:`_job`).

		:returns: The ``job`` key of an artifact's include, or ``None``.
		"""
		return self._job

	@readonly
	def Inputs(self) -> dict[str, ValueT]:
		"""
		Read-only property to access the inputs passed to the included files (:attr:`_inputs`).

		:returns: The inputs' values, by name, with the types they are written with.
		"""
		return self._inputs

	@readonly
	def Rules(self) -> list[Rule]:
		"""
		Read-only property to access the rules deciding whether the files are included (:attr:`_rules`).

		:returns: The rules, in the order GitLab evaluates them.
		"""
		return self._rules

	def __str__(self) -> str:
		"""
		Return the include's kind and location.

		:returns: The kind and the location, as ``local: /ci/build.yml``.
		"""
		return f"{self._kind.value}: {self._location}"

	@classmethod
	def _FromYAML(cls, entry: Any, path: Path, line: int) -> Self:
		"""
		Read an entry of ``include``: a path or a URL, or a mapping with one key of :attr:`_KINDS`.

		:param entry:              The entry.
		:param path:               Path to the configuration file.
		:param line:               Line the entry is written at, starting at 1.
		:returns:                  The include.
		:raises PipelineFileError: If the entry is neither a string nor a mapping.
		:raises PipelineFileError: If the mapping has none, or more than one, of the keys of :attr:`_KINDS`.
		:raises PipelineFileError: If key ``file`` of another project's include is missing, or not a path or a list.
		:raises PipelineFileError: If key ``inputs`` is not a mapping.
		:raises PipelineFileError: If a rule is malformed.
		"""
		if isinstance(entry, CommentedSeq) or entry is None:
			ex = PipelineFileError("Include is neither a path nor a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(entry)}'.")
			raise ex
		elif not isinstance(entry, CommentedMap):
			location = Base._ToText(entry)
			kind = IncludeKind.Remote if location.startswith(("https://", "http://")) else IncludeKind.Local
			return cls(kind, location, line)

		kinds = [key for key in cls._KINDS if key in entry]
		if len(kinds) != 1:
			count = "none" if len(kinds) == 0 else "more than one"
			ex = PipelineFileError(f"Include has {count} of its kinds' keys.", path, line)
			ex.add_note(f"Kinds: {', '.join(cls._KINDS)}.")
			raise ex

		kind = IncludeKind(kinds[0])
		files = None
		if kind is IncludeKind.Project:
			if (fileValue := entry.get("file", None)) is None:
				raise PipelineFileError("Include of another project has no 'file' key.", path, line)
			elif isinstance(fileValue, CommentedMap):
				ex = PipelineFileError("Key 'file' of an include is neither a path nor a list.", path, line)
				ex.add_note(f"Got type '{getFullyQualifiedName(fileValue)}'.")
				raise ex

			fileList = fileValue if isinstance(fileValue, CommentedSeq) else [fileValue]
			files = [Base._ToText(file) for file in fileList]

		inputs = entry.get("inputs", None)
		if inputs is not None and not isinstance(inputs, CommentedMap):
			ex = PipelineFileError("Key 'inputs' of an include is not a mapping.", path, Base._KeyLine(entry, "inputs"))
			ex.add_note(f"Got type '{getFullyQualifiedName(inputs)}'.")
			raise ex

		rules = None
		if "rules" in entry:
			rules = Rule._FromYAMLEntries(entry["rules"], "an include", path, Base._KeyLine(entry, "rules"))

		ref = entry.get("ref", None)
		job = entry.get("job", None)
		return cls(
			kind, Base._ToText(entry[kinds[0]]), line,
			files=files,
			ref=None if ref is None else Base._ToText(ref),
			inputs=None if inputs is None else Base._ToPython(inputs),
			rules=rules,
			job=None if job is None else Base._ToText(job)
		)

	@classmethod
	def _FromYAMLEntries(cls, value: Any, path: Path, line: int) -> list[Self]:
		"""
		Read the ``include`` key: an entry, or a list of entries.

		:param value:              The key's value.
		:param path:               Path to the configuration file.
		:param line:               Line the ``include`` key is written at, starting at 1.
		:returns:                  The includes, in file order.
		:raises PipelineFileError: If an entry is malformed.
		"""
		if not isinstance(value, CommentedSeq):
			return [cls._FromYAML(value, path, line)]

		return [cls._FromYAML(entry, path, Base._ItemLine(value, index)) for index, entry in enumerate(value)]


@export
class Rule(Base[Union[Job, Workflow, Include]]):
	"""
	A rule of ``rules``, deciding whether a job is added to a pipeline, a pipeline is created, or a file is included.

	GitLab evaluates the rules in order; the first one matching decides. A rule matches if its :attr:`Condition`, its
	:attr:`Changes` and its :attr:`Exists` match, as far as it has them.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = (Job, Workflow, Include)  #: A rule belongs to a job, a workflow or an include.

	_condition:    Nullable[str]    #: Expression of the rule's ``if``.
	_changes:      tuple[str, ...]  #: Paths of the rule's ``changes``.
	_compareTo:    Nullable[str]    #: Reference ``changes`` is compared to.
	_exists:       tuple[str, ...]  #: Paths of the rule's ``exists``.
	_when:         Nullable[When]   #: When the job runs, if the rule matches.
	_allowFailure: Nullable[bool]   #: ``True``, if the pipeline continues when the job fails, if the rule matches.
	_variables:    dict[str, str]   #: Variables set, if the rule matches, by name.

	def __init__(
		self,
		line:         int,
		condition:    Nullable[str]                           = None,
		changes:      Nullable[Iterable[str]]                 = None,
		compareTo:    Nullable[str]                           = None,
		exists:       Nullable[Iterable[str]]                 = None,
		when:         Nullable[When]                          = None,
		allowFailure: Nullable[bool]                          = None,
		variables:    Nullable[Mapping[str, str]]             = None,
		*,
		parent:       Nullable[Union[Job, Workflow, Include]] = None
	) -> None:
		"""
		Initializes a rule.

		:param line:         Line the rule is written at, starting at 1.
		:param condition:    Optional, expression of the rule's ``if``. Default: ``None``.
		:param changes:      Optional, paths of the rule's ``changes``. Default: ``None``.
		:param compareTo:    Optional, reference ``changes`` is compared to. Default: ``None``.
		:param exists:       Optional, paths of the rule's ``exists``. Default: ``None``.
		:param when:         Optional, when the job runs, if the rule matches. Default: ``None``.
		:param allowFailure: Optional, ``True``, if the pipeline continues when the job fails. Default: ``None``.
		:param variables:    Optional, variables set, if the rule matches, by name. Default: ``None``.
		:param parent:       Optional, reference to the job, workflow or include the rule belongs to. Default: ``None``.
		:raises TypeError:   If parameter 'condition' or 'compareTo' is not of type :class:`str`.
		:raises TypeError:   If an element of parameter 'changes' or 'exists' is not of type :class:`str`.
		:raises TypeError:   If parameter 'when' is not of type :class:`When`.
		:raises TypeError:   If parameter 'allowFailure' is not of type :class:`bool`.
		"""
		super().__init__(line, parent=parent)

		for parameterName, text in (
			("condition", condition),
			("compareTo", compareTo)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		self._changes = () if changes is None else tuple(changes)
		self._exists =  () if exists is None else tuple(exists)
		for parameterName, paths in (
			("changes", self._changes),
			("exists",  self._exists)
		):
			for path in paths:
				if not isinstance(path, str):
					ex = TypeError(f"An element of parameter '{parameterName}' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(path)}'.")
					raise ex

		if when is not None and not isinstance(when, When):
			ex = TypeError("Parameter 'when' is not of type 'When'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(when)}'.")
			raise ex

		if allowFailure is not None and not isinstance(allowFailure, bool):
			ex = TypeError("Parameter 'allowFailure' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(allowFailure)}'.")
			raise ex

		self._condition =    condition
		self._compareTo =    compareTo
		self._when =         when
		self._allowFailure = allowFailure
		self._variables =    {} if variables is None else dict(variables)

		if parent is not None:
			parent._rules.append(self)

	@readonly
	def Condition(self) -> Nullable[str]:
		"""
		Read-only property to access the expression of the rule's ``if`` (:attr:`_condition`).

		:returns: The expression, as written, or ``None`` if the rule has no ``if``.
		"""
		return self._condition

	@readonly
	def Changes(self) -> tuple[str, ...]:
		"""
		Read-only property to access the paths of the rule's ``changes`` (:attr:`_changes`).

		:returns: The paths, as written in ``changes`` or ``changes.paths``.
		"""
		return self._changes

	@readonly
	def CompareTo(self) -> Nullable[str]:
		"""
		Read-only property to access the reference ``changes`` is compared to (:attr:`_compareTo`).

		:returns: The reference of ``changes.compare_to``, or ``None``.
		"""
		return self._compareTo

	@readonly
	def Exists(self) -> tuple[str, ...]:
		"""
		Read-only property to access the paths of the rule's ``exists`` (:attr:`_exists`).

		:returns: The paths, as written in ``exists`` or ``exists.paths``.
		"""
		return self._exists

	@readonly
	def When(self) -> Nullable[When]:
		"""
		Read-only property to access when the job runs, if the rule matches (:attr:`_when`).

		:returns: The rule's ``when``, or ``None`` if the rule doesn't say.
		"""
		return self._when

	@readonly
	def AllowFailure(self) -> Nullable[bool]:
		"""
		Read-only property to access whether the pipeline continues when the job fails (:attr:`_allowFailure`).

		:returns: The rule's ``allow_failure``, or ``None`` if the rule doesn't say.
		"""
		return self._allowFailure

	@readonly
	def Variables(self) -> dict[str, str]:
		"""
		Read-only property to access the variables set, if the rule matches (:attr:`_variables`).

		:returns: The variables' values, by name.
		"""
		return self._variables

	@staticmethod
	def _Paths(value: Any, key: str, owner: str, entry: CommentedMap, path: Path) -> tuple[list[str], Nullable[str]]:
		"""
		Read the paths of ``changes`` or ``exists``: a list, or a mapping with ``paths``.

		:param value:              The key's value.
		:param key:                The key, for a message.
		:param owner:              The element the rule belongs to, for a message.
		:param entry:              The rule's mapping, for the key's line.
		:param path:               Path to the configuration file.
		:returns:                  The paths, and the reference of ``compare_to``.
		:raises PipelineFileError: If the value is neither a list nor a mapping with a list ``paths``.
		"""
		compareTo = None
		if isinstance(value, CommentedMap):
			compareTo = value.get("compare_to", None)
			value = value.get("paths", None)

		if not isinstance(value, CommentedSeq):
			ex = PipelineFileError(
				f"Key '{key}' of a rule of {owner} is not a list of paths.", path, Base._KeyLine(entry, key)
			)
			ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
			raise ex

		return [Base._ToText(item) for item in value], None if compareTo is None else Base._ToText(compareTo)

	@classmethod
	def _FromYAMLEntries(cls, value: Any, owner: str, path: Path, line: int) -> list[Self]:
		"""
		Read a ``rules`` key: a list of rules, each a mapping.

		:param value:              The key's value.
		:param owner:              The element the rules belong to, for a message, as ``job 'build'``.
		:param path:               Path to the configuration file.
		:param line:               Line the ``rules`` key is written at, starting at 1.
		:returns:                  The rules, in file order.
		:raises PipelineFileError: If the value is not a list, or a rule is not a mapping.
		:raises PipelineFileError: If key ``when`` of a rule is not a value GitLab knows. |br|
		                           The note lists the allowed values.
		:raises PipelineFileError: If a key of a rule holds a value of the wrong kind.
		"""
		if not isinstance(value, CommentedSeq):
			ex = PipelineFileError(f"Key 'rules' of {owner} is not a list.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(value)}'.")
			raise ex

		rules = []
		for index, entry in enumerate(value):
			entryLine = Base._ItemLine(value, index)
			if not isinstance(entry, CommentedMap):
				ex = PipelineFileError(f"Rule of {owner} is not a mapping.", path, entryLine)
				ex.add_note(f"Got type '{getFullyQualifiedName(entry)}'.")
				raise ex

			changes = None
			compareTo = None
			if "changes" in entry:
				changes, compareTo = cls._Paths(entry["changes"], "changes", owner, entry, path)

			exists = None
			if "exists" in entry:
				exists, _ = cls._Paths(entry["exists"], "exists", owner, entry, path)

			when = None
			if (whenValue := entry.get("when", None)) is not None:
				try:
					when = When.Parse(Base._ToText(whenValue))
				except ValueError as cause:
					ex = PipelineFileError(f"Key 'when' of a rule of {owner} is not a known value.", path, entryLine)
					ex.add_note(f"Got '{whenValue}'.")
					ex.add_note(f"Allowed values: {', '.join(member.value for member in When)}.")
					raise ex from cause

			allowFailure = Base._ToPython(entry.get("allow_failure", None))
			if allowFailure is not None and not isinstance(allowFailure, bool):
				ex = PipelineFileError(f"Key 'allow_failure' of a rule of {owner} is not a boolean.", path, entryLine)
				ex.add_note(f"Got '{allowFailure}'.")
				raise ex

			variables = entry.get("variables", None)
			if variables is not None and not isinstance(variables, CommentedMap):
				ex = PipelineFileError(f"Key 'variables' of a rule of {owner} is not a mapping.", path, entryLine)
				ex.add_note(f"Got type '{getFullyQualifiedName(variables)}'.")
				raise ex

			condition = entry.get("if", None)
			rules.append(cls(
				entryLine,
				condition=None if condition is None else Base._ToText(condition),
				changes=changes,
				compareTo=compareTo,
				exists=exists,
				when=when,
				allowFailure=allowFailure,
				variables=None if variables is None else {str(k): Base._ToText(v) for k, v in variables.items()}
			))

		return rules


@export
class Default(Base[PipelineFile]):
	"""
	The ``default`` key of a configuration file: keys every job gets, unless it sets them itself.

	The global keywords ``image``, ``services``, ``before_script`` and ``after_script`` - deprecated forms of
	``default`` - are read into it too, unless ``default`` sets them.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = PipelineFile  #: A default belongs to a configuration file.

	_image:        Nullable[str]    #: Image of the container a job runs in.
	_services:     tuple[str, ...]  #: Images of the service containers.
	_tags:         tuple[str, ...]  #: Tags selecting the runner.
	_beforeScript: tuple[str, ...]  #: Lines of ``before_script``.
	_afterScript:  tuple[str, ...]  #: Lines of ``after_script``.

	_KEYS: ClassVar[tuple[str, ...]] = ("image", "services", "before_script", "after_script")  #: The global keywords.

	def __init__(
		self,
		line:         int,
		image:        Nullable[str]           = None,
		services:     Nullable[Iterable[str]] = None,
		tags:         Nullable[Iterable[str]] = None,
		beforeScript: Nullable[Iterable[str]] = None,
		afterScript:  Nullable[Iterable[str]] = None,
		*,
		parent:       Nullable[PipelineFile]  = None
	) -> None:
		"""
		Initializes the ``default`` key.

		:param line:         Line the ``default`` key, or the first global keyword, is written at, starting at 1.
		:param image:        Optional, image of the container a job runs in. Default: ``None``.
		:param services:     Optional, images of the service containers. Default: ``None``.
		:param tags:         Optional, tags selecting the runner. Default: ``None``.
		:param beforeScript: Optional, lines of ``before_script``. Default: ``None``.
		:param afterScript:  Optional, lines of ``after_script``. Default: ``None``.
		:param parent:       Optional, reference to the configuration file. Default: ``None``.
		:raises TypeError:   If parameter 'image' is not of type :class:`str`.
		:raises TypeError:   If an element of parameter 'services', 'tags', 'beforeScript' or 'afterScript' is not of
		                     type :class:`str`.
		"""
		super().__init__(line, parent=parent)

		if image is not None and not isinstance(image, str):
			ex = TypeError("Parameter 'image' is not of type 'str'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(image)}'.")
			raise ex

		self._services =     () if services is None else tuple(services)
		self._tags =         () if tags is None else tuple(tags)
		self._beforeScript = () if beforeScript is None else tuple(beforeScript)
		self._afterScript =  () if afterScript is None else tuple(afterScript)
		for parameterName, texts in (
			("services",     self._services),
			("tags",         self._tags),
			("beforeScript", self._beforeScript),
			("afterScript",  self._afterScript)
		):
			for text in texts:
				if not isinstance(text, str):
					ex = TypeError(f"An element of parameter '{parameterName}' is not of type 'str'.")
					ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
					raise ex

		self._image = image

		if parent is not None:
			parent._default = self

	@readonly
	def Image(self) -> Nullable[str]:
		"""
		Read-only property to access the image of the container a job runs in (:attr:`_image`).

		:returns: The image, or ``None`` if the default names none.
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
	def BeforeScript(self) -> tuple[str, ...]:
		"""
		Read-only property to access the lines of ``before_script`` (:attr:`_beforeScript`).

		:returns: The lines, nested lists flattened.
		"""
		return self._beforeScript

	@readonly
	def AfterScript(self) -> tuple[str, ...]:
		"""
		Read-only property to access the lines of ``after_script`` (:attr:`_afterScript`).

		:returns: The lines, nested lists flattened.
		"""
		return self._afterScript

	@classmethod
	def _FromYAML(cls, document: CommentedMap, path: Path) -> Nullable[Self]:
		"""
		Read the ``default`` key and the global keywords standing for it.

		:param document:           The configuration.
		:param path:               Path to the configuration file.
		:returns:                  The default, or ``None`` if the configuration has neither.
		:raises PipelineFileError: If key ``default`` is not a mapping.
		:raises PipelineFileError: If a key holds a value of the wrong kind.
		"""
		mapping = CommentedMap()
		line = None
		if "default" in document:
			line = Base._KeyLine(document, "default")
			if not isinstance(document["default"], CommentedMap):
				ex = PipelineFileError("Key 'default' is not a mapping.", path, line)
				ex.add_note(f"Got type '{getFullyQualifiedName(document['default'])}'.")
				raise ex

			mapping = document["default"]

		globalKeys = {key: document[key] for key in cls._KEYS if key in document and key not in mapping}
		if line is None and len(globalKeys) == 0:
			return None
		elif line is None:
			line = min(Base._KeyLine(document, key) for key in globalKeys)

		def value(key: str) -> Any:
			"""
			Nested function returning a key of ``default``, or else the global keyword.

			:param key: The key.
			:returns:   The key's value, or ``None``.
			"""
			return mapping[key] if key in mapping else globalKeys.get(key, None)

		owner = mapping if "default" in document else document
		services = None
		if (serviceList := value("services")) is not None:
			if not isinstance(serviceList, CommentedSeq):
				ex = PipelineFileError("Key 'services' of the default is not a list.", path, line)
				ex.add_note(f"Got type '{getFullyQualifiedName(serviceList)}'.")
				raise ex

			services = [service for item in serviceList if (service := Job._Name(item)) is not None]

		tags = None
		if (tagList := value("tags")) is not None:
			if not isinstance(tagList, CommentedSeq):
				ex = PipelineFileError("Key 'tags' of the default is not a list.", path, line)
				ex.add_note(f"Got type '{getFullyQualifiedName(tagList)}'.")
				raise ex

			tags = [Base._ToText(tag) for tag in tagList]

		return cls(
			line,
			image=Job._Name(value("image")),
			services=services,
			tags=tags,
			beforeScript=Job._Lines(value("before_script"), "before_script", "the default", owner, path),
			afterScript=Job._Lines(value("after_script"), "after_script", "the default", owner, path)
		)


@export
class Parallel(Base[Union[Job, Need]]):
	"""
	A ``parallel`` key: how often a job runs, or the matrix of variables its instances run with.

	A job runs :attr:`Count` times, or once per combination of :attr:`Matrix`: an entry maps variables to values, and
	contributes the product of their lists. A need's ``parallel`` names the matrix instances it needs.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = (Job, Need)  #: A parallel belongs to a job or a need.

	_count:  Nullable[int]                           #: How often the job runs.
	_matrix: tuple[dict[str, tuple[str, ...]], ...]  #: Entries of the matrix: variables to their values.

	def __init__(
		self,
		line:   int,
		count:  Nullable[int]                                   = None,
		matrix: Nullable[Iterable[Mapping[str, Iterable[str]]]] = None,
		*,
		parent: Nullable[Union[Job, Need]]                      = None
	) -> None:
		"""
		Initializes a ``parallel`` key.

		:param line:        Line the ``parallel`` key is written at, starting at 1.
		:param count:       Optional, how often the job runs. Default: ``None``, for a matrix.
		:param matrix:      Optional, entries of the matrix, each mapping variables to their values. Default: ``None``,
		                    for a count.
		:param parent:      Optional, reference to the job or the need. Default: ``None``.
		:raises ValueError: If both or neither of parameters 'count' and 'matrix' are given.
		:raises TypeError:  If parameter 'count' is not of type :class:`int`.
		:raises ValueError: If parameter 'count' is out of range 1..200.
		:raises TypeError:  If an entry of parameter 'matrix' is not a mapping, or a variable's values are not strings.
		"""
		super().__init__(line, parent=parent)

		if (count is None) == (matrix is None):
			raise ValueError("Parameters 'count' and 'matrix' are both given, or both None.")
		elif count is not None and (not isinstance(count, int) or isinstance(count, bool)):
			ex = TypeError("Parameter 'count' is not of type 'int'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(count)}'.")
			raise ex
		elif count is not None and not (1 <= count <= 200):
			ex = ValueError("Parameter 'count' is out of range 1..200.")
			ex.add_note(f"Got value '{count}'.")
			raise ex

		entries = []
		for entry in () if matrix is None else matrix:
			if not isinstance(entry, Mapping):
				ex = TypeError("An entry of parameter 'matrix' is not a mapping.")
				ex.add_note(f"Got type '{getFullyQualifiedName(entry)}'.")
				raise ex

			variables = {}
			for variable, values in entry.items():
				variables[variable] = tuple(values)
				if not isinstance(variable, str) or any(not isinstance(value, str) for value in variables[variable]):
					ex = TypeError(f"Variable '{variable}' of parameter 'matrix' has values not of type 'str'.")
					ex.add_note(f"Got '{variables[variable]}'.")
					raise ex

			entries.append(variables)

		self._count =  count
		self._matrix = tuple(entries)

		if parent is not None:
			parent._parallel = self

	@readonly
	def Count(self) -> Nullable[int]:
		"""
		Read-only property to access how often the job runs (:attr:`_count`).

		:returns: The count of ``parallel: N``, or ``None`` for a matrix.
		"""
		return self._count

	@readonly
	def Matrix(self) -> tuple[dict[str, tuple[str, ...]], ...]:
		"""
		Read-only property to access the entries of the matrix (:attr:`_matrix`).

		:returns: The entries, each mapping variables to their values, in file order; empty for a count.
		"""
		return self._matrix

	@readonly
	def IsMatrix(self) -> bool:
		"""
		Read-only property to return whether the key is a matrix.

		:returns: ``True`` for ``parallel: matrix``, ``False`` for ``parallel: N``.
		"""
		return self._count is None

	@readonly
	def Combinations(self) -> list[dict[str, str]]:
		"""
		Read-only property to return the combinations of the matrix, one per instance.

		:returns: The combinations, each mapping the variables to a value, in the order GitLab creates the instances.
		"""
		combinations = []
		for entry in self._matrix:
			for values in product(*entry.values()):
				combinations.append(dict(zip(entry, values)))

		return combinations

	@readonly
	def InstanceNames(self) -> list[str]:
		"""
		Read-only property to return the names GitLab gives the instances.

		:returns: The names, as ``test 1/3`` for a count, or ``deploy: [aws, app1]`` for a matrix.
		"""
		if isinstance(self._parent, Need):
			name = self._parent._job
		else:
			name = "" if self._parent is None else self._parent._name

		if self._count is not None:
			return [self._InstanceName(name, self._count, {"CI_NODE_INDEX": index}) for index in range(1, self._count + 1)]

		return [self._InstanceName(name, None, combination) for combination in self.Combinations]

	@staticmethod
	def _InstanceName(name: str, count: Nullable[int], dimensions: Mapping[str, Any]) -> str:
		"""
		Return the name GitLab gives an instance.

		:param name:       Name of the job.
		:param count:      The count of ``parallel: N``, or ``None`` for a matrix.
		:param dimensions: The instance's variables, ``CI_NODE_INDEX`` for ``parallel: N``.
		:returns:          The name, as ``test 1/3`` for a count, or ``deploy: [aws, app1]`` for a matrix.
		"""
		if count is not None:
			return f"{name} {dimensions['CI_NODE_INDEX']}/{count}"

		return f"{name}: [{', '.join(str(value) for value in dimensions.values())}]"

	@classmethod
	def _FromYAML(cls, value: Any, owner: str, path: Path, line: int) -> Self:
		"""
		Read a ``parallel`` key: a count, or a mapping with key ``matrix``.

		:param value:              The key's value.
		:param owner:              The element holding the key, for a message, as ``job 'test'``.
		:param path:               Path to the configuration file.
		:param line:               Line the ``parallel`` key is written at, starting at 1.
		:returns:                  The parallel.
		:raises PipelineFileError: If the value is neither a count nor a mapping with key ``matrix``.
		:raises PipelineFileError: If the count is out of range 1..200.
		:raises PipelineFileError: If the matrix is not a list of mappings of variables to a value or a list of values.
		"""
		count = Base._ToPython(value)
		if isinstance(count, int) and not isinstance(count, bool):
			if not (1 <= count <= 200):
				ex = PipelineFileError(f"Key 'parallel' of {owner} is out of range 1..200.", path, line)
				ex.add_note(f"Got '{count}'.")
				raise ex

			return cls(line, count)
		elif not isinstance(value, CommentedMap) or "matrix" not in value:
			ex = PipelineFileError(f"Key 'parallel' of {owner} is neither a count nor a mapping with 'matrix'.", path, line)
			ex.add_note(f"Got '{count}'.")
			raise ex

		entries = value["matrix"]
		if not isinstance(entries, CommentedSeq) or any(not isinstance(entry, CommentedMap) for entry in entries):
			ex = PipelineFileError(f"Key 'parallel.matrix' of {owner} is not a list of mappings.", path, line)
			ex.add_note(f"Got '{Base._ToPython(entries)}'.")
			raise ex

		matrix = []
		for entry in entries:
			variables = {}
			for variable, values in entry.items():
				values = values if isinstance(values, CommentedSeq) else [values]
				if any(isinstance(item, (CommentedMap, CommentedSeq)) for item in values):
					ex = PipelineFileError(
						f"Variable '{variable}' of the matrix of {owner} is neither a value nor a list of values.",
						path, Base._KeyLine(entry, variable)
					)
					ex.add_note(f"Got '{Base._ToPython(values)}'.")
					raise ex

				variables[str(variable)] = [Base._ToText(item) for item in values]

			matrix.append(variables)

		return cls(line, matrix=matrix)


@export
class Input(Base[Union[PipelineFile, Job]]):
	"""
	An input of the header's ``spec:inputs``, or of a job's ``inputs``.

	An input of a file is a parameter of its configuration, which ``include:inputs`` or ``trigger:include:inputs`` set, or
	the form running a pipeline by hand; it is mandatory without a default. An input of a job is set when the job is
	run or retried by hand, and always has a default.
	"""

	_PARENT_TYPE: ClassVar[ParentTypes] = (PipelineFile, Job)  #: An input belongs to a configuration file or a job.

	_name:        str                            #: Name of the input.
	_type:        InputType                      #: Type of the input.
	_required:    bool                           #: ``True``, if the input has no default.
	_default:     ValueT                         #: Value of the input, if it isn't set.
	_description: Nullable[str]                  #: Description of the input.
	_options:     tuple[ValueT, ...]             #: Values the input may have.
	_regex:       Nullable[str]                  #: Regular expression the input's value must match.
	_rules:       tuple[dict[str, ValueT], ...]  #: Conditional options and defaults of ``rules``.

	_KEYS: ClassVar[tuple[str, ...]] = (
		"default", "type", "description", "options", "regex", "rules"
	)  #: Keys of an input as mapping.

	def __init__(
		self,
		name:        str,
		line:        int,
		inputType:   InputType                                = InputType.String,
		required:    bool                                     = True,
		default:     ValueT                                   = None,
		description: Nullable[str]                            = None,
		options:     Nullable[Iterable[ValueT]]               = None,
		regex:       Nullable[str]                            = None,
		rules:       Nullable[Iterable[Mapping[str, ValueT]]] = None,
		*,
		parent:      Nullable[Union[PipelineFile, Job]]       = None
	) -> None:
		"""
		Initializes an input.

		:param name:        Name of the input.
		:param line:        Line the input's name is written at, starting at 1.
		:param inputType:   Optional, type of the input. Default: :attr:`InputType.String`.
		:param required:    Optional, ``True``, if the input has no default. Default: ``True``.
		:param default:     Optional, value of the input, if it isn't set. Default: ``None``.
		:param description: Optional, description of the input. Default: ``None``.
		:param options:     Optional, values the input may have. Default: ``None``.
		:param regex:       Optional, regular expression the input's value must match. Default: ``None``.
		:param rules:       Optional, conditional options and defaults, each a mapping of ``if``, ``options`` and
		                    ``default``. Default: ``None``.
		:param parent:      Optional, reference to the configuration file or the job. Default: ``None``.
		:raises ValueError: If parameter 'name' is ``None``.
		:raises TypeError:  If parameter 'name' is not of type :class:`str`.
		:raises ValueError: If parameter 'name' is empty.
		:raises TypeError:  If parameter 'inputType' is not of type :class:`InputType`.
		:raises TypeError:  If parameter 'required' is not of type :class:`bool`.
		:raises TypeError:  If parameter 'description' or 'regex' is not of type :class:`str`.
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

		if not isinstance(inputType, InputType):
			ex = TypeError("Parameter 'inputType' is not of type 'InputType'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(inputType)}'.")
			raise ex

		if not isinstance(required, bool):
			ex = TypeError("Parameter 'required' is not of type 'bool'.")
			ex.add_note(f"Got type '{getFullyQualifiedName(required)}'.")
			raise ex

		for parameterName, text in (
			("description", description),
			("regex",       regex)
		):
			if text is not None and not isinstance(text, str):
				ex = TypeError(f"Parameter '{parameterName}' is not of type 'str'.")
				ex.add_note(f"Got type '{getFullyQualifiedName(text)}'.")
				raise ex

		self._name =        name
		self._type =        inputType
		self._required =    required
		self._default =     default
		self._description = description
		self._options =     () if options is None else tuple(options)
		self._regex =       regex
		self._rules =       () if rules is None else tuple(dict(rule) for rule in rules)

		if parent is not None:
			parent._inputs[name] = self

	@readonly
	def Name(self) -> str:
		"""
		Read-only property to access the input's name (:attr:`_name`).

		:returns: Name of the input.
		"""
		return self._name

	@readonly
	def Type(self) -> InputType:
		"""
		Read-only property to access the input's type (:attr:`_type`).

		:returns: The ``type`` key, :attr:`InputType.String` if the input doesn't say.
		"""
		return self._type

	@readonly
	def Required(self) -> bool:
		"""
		Read-only property to access whether the input has to be set (:attr:`_required`).

		:returns: ``True``, if the input has no ``default`` key.
		"""
		return self._required

	@readonly
	def Default(self) -> ValueT:
		"""
		Read-only property to access the input's value, if it isn't set (:attr:`_default`).

		:returns: The default, with the type it is written with, or ``None`` if the input has none.
		"""
		return self._default

	@readonly
	def Description(self) -> Nullable[str]:
		"""
		Read-only property to access the input's description (:attr:`_description`).

		:returns: The description, or ``None`` if the input gives none.
		"""
		return self._description

	@readonly
	def Options(self) -> tuple[ValueT, ...]:
		"""
		Read-only property to access the values the input may have (:attr:`_options`).

		:returns: The options, in file order; empty if the input may have any value.
		"""
		return self._options

	@readonly
	def Regex(self) -> Nullable[str]:
		"""
		Read-only property to access the regular expression the input's value must match (:attr:`_regex`).

		:returns: The expression, as written, or ``None``.
		"""
		return self._regex

	@readonly
	def Rules(self) -> tuple[dict[str, ValueT], ...]:
		"""
		Read-only property to access the input's conditional options and defaults (:attr:`_rules`).

		:returns: The rules, each mapping ``if``, ``options`` and ``default``, in the order GitLab evaluates them.
		"""
		return self._rules

	def __str__(self) -> str:
		"""
		Return the input's name.

		:returns: Name of the input.
		"""
		return self._name

	@classmethod
	def _FromYAML(cls, name: str, declaration: Any, jobName: Nullable[str], path: Path, line: int) -> Self:
		"""
		Read an input's declaration: empty, or a mapping of the keys in :attr:`_KEYS`.

		:param name:               Name of the input.
		:param declaration:        The declaration.
		:param jobName:            Name of the job declaring the input, or ``None`` for ``spec:inputs``.
		:param path:               Path to the configuration file.
		:param line:               Line the input's name is written at, starting at 1.
		:returns:                  The input.
		:raises PipelineFileError: If the declaration is neither empty nor a mapping.
		:raises PipelineFileError: If the mapping has a key GitLab doesn't know for an input. |br|
		                           The note lists the allowed keys.
		:raises PipelineFileError: If key ``type`` is not an input type. |br|
		                           The note lists the allowed values.
		:raises PipelineFileError: If an input of a job has no default.
		:raises PipelineFileError: If the default doesn't match the type, or isn't one of the options.
		:raises PipelineFileError: If key ``options`` or ``rules`` is not a list, or ``regex`` is used with a type other
		                           than ``string``.
		"""
		subject = f"input '{name}'" if jobName is None else f"input '{name}' of job '{jobName}'"
		if declaration is None:
			declaration = CommentedMap()
		elif not isinstance(declaration, CommentedMap):
			ex = PipelineFileError(f"I{subject[1:]} is not a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(declaration)}'.")
			raise ex

		for key in declaration:
			if key not in cls._KEYS:
				ex = PipelineFileError(f"I{subject[1:]} has unknown key '{key}'.", path, Base._KeyLine(declaration, key))
				ex.add_note(f"Allowed keys: {', '.join(cls._KEYS)}.")
				raise ex

		try:
			inputType = InputType.Parse(Base._ToText(declaration.get("type", "string")))
		except ValueError as cause:
			ex = PipelineFileError(f"Key 'type' of {subject} is not an input type.", path, line)
			ex.add_note(f"Got '{declaration['type']}'.")
			ex.add_note(f"Allowed values: {', '.join(member.value for member in InputType)}.")
			raise ex from cause

		required = "default" not in declaration
		if required and jobName is not None:
			raise PipelineFileError(f"I{subject[1:]} has no default.", path, line)

		for key in ("options", "rules"):
			if key in declaration and not isinstance(declaration[key], CommentedSeq):
				ex = PipelineFileError(
					f"Key '{key}' of {subject} is not a list.", path, Base._KeyLine(declaration, key)
				)
				ex.add_note(f"Got type '{getFullyQualifiedName(declaration[key])}'.")
				raise ex

		default = Base._ToPython(declaration.get("default", None))
		options = Base._ToPython(declaration.get("options", []))
		types = {
			InputType.String:  (str, ),
			InputType.Number:  (int, float),
			InputType.Boolean: (bool, ),
			InputType.Array:   (list, )
		}[inputType]
		if default is not None and (not isinstance(default, types) or (isinstance(default, bool) and bool not in types)):
			ex = PipelineFileError(f"Default of {subject} is not of type '{inputType.value}'.", path, line)
			ex.add_note(f"Got '{default}'.")
			raise ex
		elif default is not None and len(options) > 0 and default not in options:
			ex = PipelineFileError(f"Default of {subject} is not one of its options.", path, line)
			ex.add_note(f"Options: {', '.join(str(option) for option in options)}.")
			raise ex
		elif "regex" in declaration and inputType is not InputType.String:
			raise PipelineFileError(f"Key 'regex' of {subject} needs type 'string'.", path, line)

		description = declaration.get("description", None)
		regex = declaration.get("regex", None)
		return cls(
			name, line, inputType, required, default,
			description=None if description is None else Base._ToText(description),
			options=options,
			regex=None if regex is None else Base._ToText(regex),
			rules=Base._ToPython(declaration.get("rules", []))
		)

	@classmethod
	def _FromYAMLMapping(cls, mapping: Any, jobName: Nullable[str], path: Path, line: int) -> list[Self]:
		"""
		Read the inputs of ``spec:inputs`` or of a job's ``inputs``.

		:param mapping:            The key's value.
		:param jobName:            Name of the job declaring the inputs, or ``None`` for ``spec:inputs``.
		:param path:               Path to the configuration file.
		:param line:               Line the key is written at, starting at 1.
		:returns:                  The inputs, in file order.
		:raises PipelineFileError: If the value is not a mapping.
		:raises PipelineFileError: If an input is malformed.
		"""
		if not isinstance(mapping, CommentedMap):
			message = "Key 'spec:inputs'" if jobName is None else f"Key 'inputs' of job '{jobName}'"
			ex = PipelineFileError(f"{message} is not a mapping.", path, line)
			ex.add_note(f"Got type '{getFullyQualifiedName(mapping)}'.")
			raise ex

		return [
			cls._FromYAML(str(name), value, jobName, path, Base._KeyLine(mapping, name)) for name, value in mapping.items()
		]

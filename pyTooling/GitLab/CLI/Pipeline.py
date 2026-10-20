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
The :pycode:`pipeline` command: read a CI pipeline and write what it took.

.. rubric:: Usage

.. code-block:: bash

   pytooling-gitlab pipeline --gitlab-project=gitlab-org/gitlab-development-kit \
                             --gitlab-pipeline-id=2954836704 \
                             --trace-file=report/Pipeline.otlp.json

.. hint::

   See :ref:`high-level help <CLI/Pipeline>` for explanations and usage examples.
"""
from argparse                                 import Namespace
from os                                       import getenv
from pathlib                                  import Path
from typing                                   import ClassVar, Optional as Nullable

from pyTooling.Common                         import StringEnum
from pyTooling.Decorators                     import export
from pyTooling.MetaClasses                    import ExtendedType
from pyTooling.Attributes.ArgParse            import CommandHandler, splitFormat
from pyTooling.Attributes.ArgParse.Flag       import LongFlag
from pyTooling.Attributes.ArgParse.ValuedFlag import LongValuedFlag
from pyTooling.Tracing                        import Trace
from pyTooling.GitLab                         import GITLAB_API_URL
from pyTooling.GitLab.Tracing                 import PipelineReader, runnerCategory
from pyTooling.Tracing.Render                 import GanttLayout, ciSpanFilter


@export
class TraceFormat(StringEnum):
	"""The formats a trace can be written in, as ``--trace-file`` names them."""

	OTLPJSON = "otlp-json"  #: OpenTelemetry's OTLP/JSON encoding of a trace.

	DEFAULT = OTLPJSON      #: The format ``--trace-file`` writes when its value names none.


@export
class GanttFormat(StringEnum):
	"""The formats a Gantt chart can be drawn in, as ``--gantt`` names them: the backend and the file format."""

	MatplotlibPNG = "matplotlib-png"  #: A raster image, drawn by matplotlib.
	MatplotlibSVG = "matplotlib-svg"  #: A vector image, drawn by matplotlib.
	MatplotlibPDF = "matplotlib-pdf"  #: A PDF page, drawn by matplotlib.

	DEFAULT = MatplotlibPNG           #: The format ``--gantt`` draws when its value names none.


@export
class PipelineHandlers(metaclass=ExtendedType, mixin=True):
	"""
	Mixin-class contributing the :pycode:`pipeline` command to :class:`~pyTooling.GitLab.CLI.Application`.

	The command reads one CI pipeline into a :class:`~pyTooling.Tracing.Trace` and writes what was asked of it.
	Reading and writing are separate steps on purpose: the trace is the intermediate every output is derived from, so
	a further output is a further option and not a second reader.
	"""
	ENVIRONMENT_PROJECT:     ClassVar[str] = "CI_PROJECT_ID"   #: Variable naming the project inside a pipeline.
	ENVIRONMENT_PIPELINE_ID: ClassVar[str] = "CI_PIPELINE_ID"  #: Variable naming the pipeline inside a pipeline.
	ENVIRONMENT_API_URL:     ClassVar[str] = "CI_API_V4_URL"   #: Variable naming the REST API inside a pipeline.
	ENVIRONMENT_TOKEN:       ClassVar[str] = "GITLAB_TOKEN"    #: Variable holding the token to read the pipeline with.

	@CommandHandler(
		"pipeline",
		help="Read a CI pipeline and write what it took.",
		description="Read a CI pipeline and write what it took."
	)
	@LongValuedFlag(
		"--gitlab-project", dest="gitlabProject", metaName="path|ID", optional=True,
		help=f"Project the pipeline belongs to, as its path or identifier. Default: ${ENVIRONMENT_PROJECT}."
	)
	@LongValuedFlag(
		"--gitlab-pipeline-id", dest="gitlabPipelineID", metaName="ID", optional=True,
		help=f"Identifier of the GitLab pipeline. Default: ${ENVIRONMENT_PIPELINE_ID}."
	)
	@LongValuedFlag(
		"--gitlab-api-url", dest="gitlabAPIURL", metaName="URL", optional=True,
		help=f"GitLab's REST API. Default: ${ENVIRONMENT_API_URL}, else {GITLAB_API_URL}."
	)
	@LongValuedFlag(
		"--token", dest="token", metaName="token", optional=True,
		help=f"Token reading the pipeline, e.g. with scope 'read_api'. Default: ${ENVIRONMENT_TOKEN}."
	)
	@LongValuedFlag(
		"--trace-file", dest="traceFile", metaName="[format:]file", optional=True,
		help=f"Write the trace. Format: {', '.join(TraceFormat)}. Default: {TraceFormat.DEFAULT}."
	)
	@LongValuedFlag(
		"--gantt", dest="gantt", metaName="[format:]file", optional=True,
		help=f"Draw a Gantt chart. Format: {', '.join(GanttFormat)}. Default: {GanttFormat.DEFAULT}."
	)
	@LongFlag("--force", dest="force", help="Overwrite files that exist.")
	def HandlePipeline(self, args: Namespace) -> None:
		"""
		Handle program calls with command ``pipeline``.

		The outputs are checked **before** the pipeline is read, so a misspelled format or a file that exists is
		reported at once instead of after a network round-trip.

		:param args: The parsed command line.
		"""
		self._PrintHeadline()

		outputs = self._CheckOutputs(args)
		self.ExitOnPreviousErrors()

		trace = self._ReadPipeline(args)
		self._PrintSummary(trace)
		self._WriteOutputs(outputs, trace)

		self.ExitOnPreviousErrors()

	def _CheckOutputs(self, args: Namespace) -> list[tuple[str, StringEnum, Path]]:
		"""
		Read every output option, and report what can't be written before anything is read.

		:param args: The parsed command line.
		:returns:    One ``(option, format, file)`` per output that was asked for and can be written.
		"""
		outputs: list[tuple[str, StringEnum, Path]] = []
		for option, value, formats in self._Outputs(args):
			if value is None:
				continue

			try:
				fileFormat, file = splitFormat(value, formats)
			except ValueError as ex:
				self.WriteError(f"Option '{option}': {ex}")
				for note in ex.__notes__:
					self.WriteErrorNote(note)
				continue

			if option == "--gantt" and file.suffix.lower().lstrip(".") != (suffix := fileFormat.partition("-")[2]):
				self.WriteError(f"Option '--gantt': format '{fileFormat}' writes a '.{suffix}' file.")
				self.WriteErrorNote(f"Got '{file.name}'. Name the file '.{suffix}', or state the format it is in.")
				continue

			if file.exists() and not args.force:
				self.WriteError(f"File '{file}' exists.")
				self.WriteErrorNote("Use '--force' to overwrite it.")
				continue

			outputs.append((option, fileFormat, file))

		return outputs

	def _Outputs(self, args: Namespace) -> tuple[tuple[str, Nullable[str], type[StringEnum]], ...]:
		"""
		Return the output options this command offers, as ``(option, value, formats)``.

		A value naming no format gets the enumeration's ``DEFAULT``.

		:param args: The parsed command line.
		:returns:    One entry per output option, whether or not it was given.
		"""
		return (
			("--trace-file", args.traceFile, TraceFormat),
			("--gantt",      args.gantt,     GanttFormat),
		)

	def _WriteOutputs(self, outputs: list[tuple[str, StringEnum, Path]], trace: Trace) -> None:
		"""
		Write every output the command line asked for.

		:param outputs: The outputs, as :meth:`_CheckOutputs` returned them.
		:param trace:   The pipeline as a trace.
		"""
		for option, fileFormat, file in outputs:
			if option == "--trace-file":
				self.WriteVerbose(f"Writing the trace as '{fileFormat}' to '{file}' ...")
				trace.WriteJSONFile(file)
				self.WriteNormal(f"Trace:     {file}")
			elif option == "--gantt":
				self._WriteGantt(fileFormat, file, trace)

	def _WriteGantt(self, fileFormat: GanttFormat, file: Path, trace: Trace) -> None:
		"""
		Lay the trace out as a Gantt chart and draw it with the backend the format names.

		A job is colored by its runner, as :func:`~pyTooling.GitLab.Tracing.runnerCategory` names it.

		:param fileFormat:              The format, one of :class:`GanttFormat`.
		:param file:                    The file to write.
		:param trace:                   The pipeline as a trace.
		:raises MissingDependencyError: If *matplotlib* isn't installed. |br|
		                                :func:`~pyTooling.GitLab.CLI.main` prints it with the commands installing it.
		"""
		from pyTooling.Tracing.Render.Matplotlib import MatplotlibRenderer

		self.WriteVerbose(f"Drawing the Gantt chart as '{fileFormat}' to '{file}' ...")
		layout = GanttLayout(trace, spanFilter=ciSpanFilter(), categorize=runnerCategory)
		MatplotlibRenderer(layout).Write(file)
		self.WriteNormal(f"Gantt:     {file} ({layout.RowCount} rows)")

	def _ReadPipeline(self, args: Namespace) -> Trace:
		"""
		Read the pipeline the command line names into a trace.

		The token is ``--token``, else ``$GITLAB_TOKEN``; a public project's pipeline is read without one.

		:param args: The parsed command line.
		:returns:    The pipeline as a trace.
		"""
		project = args.gitlabProject if args.gitlabProject is not None else getenv(self.ENVIRONMENT_PROJECT)
		if project is None:
			self.WriteError("No project given.")
			self.WriteErrorNote(f"Set '--gitlab-project=group/project', or ${self.ENVIRONMENT_PROJECT}.")
			self.Exit(2)
		elif project.strip("/") == "" or "" in project.split("/"):
			self.WriteError(f"Project '{project}' is neither a path nor an identifier.")
			self.WriteErrorNote("E.g. '--gitlab-project=gitlab-org/gitlab-development-kit' or '--gitlab-project=74823'.")
			self.Exit(2)

		pipelineID = args.gitlabPipelineID if args.gitlabPipelineID is not None else getenv(self.ENVIRONMENT_PIPELINE_ID)
		if pipelineID is None:
			self.WriteError("No pipeline given.")
			self.WriteErrorNote(f"Set '--gitlab-pipeline-id=<ID>', or ${self.ENVIRONMENT_PIPELINE_ID}.")
			self.Exit(2)
		elif not pipelineID.isdigit():
			self.WriteError(f"Pipeline '{pipelineID}' isn't a number.")
			self.WriteErrorNote("It is the number in the pipeline's URL: .../-/pipelines/2954836704.")
			self.Exit(2)

		if (apiURL := args.gitlabAPIURL) is None:
			apiURL = getenv(self.ENVIRONMENT_API_URL, str(GITLAB_API_URL))

		token = args.token if args.token is not None else getenv(self.ENVIRONMENT_TOKEN)

		self.WriteVerbose(f"Reading pipeline {pipelineID} of '{project}' from '{apiURL}' ...")
		reader = PipelineReader(int(project) if project.isdigit() else project, token, apiURL=apiURL)

		return reader.ReadPipeline(int(pipelineID))

	def _PrintSummary(self, trace: Trace) -> None:
		"""
		Print what the pipeline took, so the command says something without being asked to write a file.

		:param trace: The pipeline as a trace.
		"""
		self.WriteNormal(f"Pipeline:  {trace.Name}")
		self.WriteNormal(f"Began:     {trace.StartTime}")
		self.WriteNormal(f"Wall time: {trace.DurationInSeconds:.0f} s")

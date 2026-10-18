.. _CLI:

pytooling-gitlab
################

pyTooling.GitLab installs a program: :program:`pytooling-gitlab`. It is the command line front-end to what the package
models - reading a GitLab CI/CD pipeline into a trace, writing that trace, rendering it - so a pipeline job can do those
things without a script of its own.

.. code-block:: bash

   pytooling-gitlab help              # what the program can do
   pytooling-gitlab help <command>    # what one command can do
   pytooling-gitlab version           # which pyTooling.GitLab is installed

The program is the ``console_scripts`` entry point :pycode:`pyTooling.GitLab.CLI:main`, which :file:`setup.py`
registers, so it is on the path after :pycode:`pip install pyTooling.GitLab`.

.. attention::

   **Drawing needs the** ``diagram`` **extra**: :pycode:`pip install pyTooling.GitLab[diagram]` installs
   *matplotlib*, which :pycode:`--gantt` draws with. Without it, :pycode:`--gantt` names the missing package and the
   command line installing it rather than failing on an import. *colorama*, which a
   :class:`~pyTooling.TerminalUI.TerminalApplication` needs to write anything at all, comes with the package's
   requirement ``pyTooling[terminal]``.


.. _CLI/Structure:

How a command is declared
*************************

The program is a :class:`~pyTooling.TerminalUI.TerminalApplication` **and** an
:class:`~pyTooling.Attributes.ArgParse.ArgParseHelperMixin`, so it prints like the first and parses like the
second: a command is a **method** marked with :class:`~pyTooling.Attributes.ArgParse.CommandHandler`, and the
arguments of that command are the attributes written above the method. See :ref:`ATTR/ArgParse` for the attributes
themselves.

.. code-block:: Python

   @CommandHandler("version", help="Display version information.")
   def HandleVersion(self, _: Namespace) -> None:
     ...

Two commands are always there: :pycode:`help`, which prints the help page of the program or of one command, and
:pycode:`version`. A call with no command prints the help page.

**A group of related commands is a mixin-class of its own.**
:class:`~pyTooling.GitLab.CLI.Application` inherits from all of them, and the attributes are found on the assembled
class, so adding a command means writing a mixin and adding one base-class - see :ref:`ATTR/ArgParse/Mixin`. That is the
same construction :program:`pyedaa-outputfilter` uses.

.. hint::

   The three global switches - ``-q`` / ``--quiet``, ``-v`` / ``--verbose`` and ``-d`` / ``--debug`` - are declared
   on the **default handler**, so they belong before the command: ``pytooling-gitlab --verbose version``, not
   ``pytooling-gitlab version --verbose``.


.. _CLI/Errors:

What a failure looks like
*************************

:func:`~pyTooling.GitLab.CLI.main` runs the program inside a ``try ... except``, so a user of the program sees a message
and a non-zero exit code rather than a traceback. A :exc:`~pyTooling.Exceptions.ToolingException` is printed with
its cause and with every note it carries, because the notes are where pyTooling puts the advice - *"check the
project's path or identifier"* rather than only *"404"*.

A :exc:`~pyTooling.Exceptions.MissingDependencyError` is not handled where it is raised. An output needing an
optional package - ``--gantt`` needs *matplotlib* - imports it where it draws and lets the exception travel to
:func:`~pyTooling.GitLab.CLI.main`, which hands it to
:meth:`~pyTooling.TerminalUI.TerminalApplication.PrintMissingDependencyError`: that printer names the missing
package and every command line installing it, and reports no bug, because nothing is wrong with the program.


.. _CLI/Pipeline:

The ``pipeline`` command
************************

:pycode:`pytooling-gitlab pipeline` reads one CI pipeline into a :class:`~pyTooling.Tracing.Trace` and writes what was
asked of it. Reading and writing are separate steps: the trace is the intermediate every output is derived from, so a
further output is a further option rather than a second reader.

.. code-block:: bash

   pytooling-gitlab pipeline --gitlab-project=gitlab-org/gitlab-development-kit \
                             --gitlab-pipeline-id=2954836704 \
                             --trace-file=report/Pipeline.otlp.json \
                             --gantt=report/Pipeline.png

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Option
     - Meaning
   * - ``--gitlab-project=<path|ID>``
     - The project the pipeline belongs to, as its path - ``group/subgroup/project`` - or its numeric identifier.
       Default: :pycode:`$CI_PROJECT_ID`, which a GitLab pipeline sets.
   * - ``--gitlab-pipeline-id=<ID>``
     - The pipeline to read - the number in its URL, :file:`.../-/pipelines/2954836704`. Default:
       :pycode:`$CI_PIPELINE_ID`, which a GitLab pipeline sets.
   * - ``--gitlab-api-url=<URL>``
     - GitLab's REST API, e.g. of a self-managed instance. Default: :pycode:`$CI_API_V4_URL`, which a GitLab pipeline
       sets, else ``https://gitlab.com/api/v4``.
   * - ``--token=<token>``
     - The token reading the pipeline. Default: :pycode:`$GITLAB_TOKEN`.
   * - ``--trace-file=[<format>:]<file>``
     - Write the trace. Default format: ``otlp-json``, currently the only one.
   * - ``--gantt=[<format>:]<file>``
     - Draw the pipeline as a Gantt chart: ``matplotlib-png``, ``matplotlib-svg`` or ``matplotlib-pdf``.
   * - ``--force``
     - Overwrite files that exist. Without it, an existing file is an error.

The token is ``--token``, else :pycode:`$GITLAB_TOKEN` - the option wins, e.g. to read another instance's pipeline from
inside a pipeline holding its own token. A public project's pipelines are read without one; a private project's need a
token with the ``read_api`` scope - inside a pipeline, e.g. a project access token stored as a masked CI/CD variable;
``$CI_JOB_TOKEN`` can't read pipelines - GitLab lets it update a pipeline's metadata only. The child pipelines are read
too; a multi-project pipeline's jobs aren't, as they belong to another project.

.. hint::

   **A job cannot see itself.** It is still running when it reads the pipeline, so a job that reports the pipeline's
   timing needs every other job - e.g. in a stage of its own, the last one - and runs last.


.. _CLI/Pipeline/Formats:

``[<format>:]<file>``
=====================

Every option that writes a file takes the format in front of the path, separated by a colon, and assumes a
default when none is given - :pycode:`--trace-file=report/Pipeline.otlp.json` and
:pycode:`--trace-file=otlp-json:report/Pipeline.otlp.json` are the same thing.

**A colon alone doesn't make a format.** A format is more than one character long and holds no path separator, so
a Windows drive (:file:`C:\\report\\trace.json`) and a colon deeper down a path are paths. A prefix that looks
like a format but isn't one is an error naming the formats that exist, rather than a file with a strange name.

None of that is the command's own: :func:`~pyTooling.Attributes.ArgParse.splitFormat` does the splitting for any
program declaring an option of this shape, and a value naming no format gets the enumeration's ``DEFAULT`` - see
`pyTooling's argument formats <https://pyTooling.github.io/pyTooling/Attributes/ArgParse.html#attr-argparse-formats>`__.

Both are checked **before** the pipeline is read, so a misspelled format or a file that exists is reported at once
instead of after a network round-trip.


.. _CLI/Pipeline/Gantt:

Drawing the pipeline
====================

``--gantt`` lays the trace out as a `Gantt chart <https://pyTooling.github.io/pyTooling/Tracing.html#tracing-render>`__
and draws it: one row per job, the time it was queued for a runner in light gray in front of the time it ran, and a line
for the pipeline, every matrix and every downstream pipeline. A job is colored by its runner - its first tag, or the
runner's description -, and the legend carries the statistics per runner (see :ref:`VIS/PipelineTrace/Gantt`).

A format is the backend and the file format - ``matplotlib-png``, ``matplotlib-svg``, ``matplotlib-pdf`` - and the
file's suffix has to agree with it. A value naming no format gets ``matplotlib-png``, so a PNG needs no format, and
any other file states it: :pycode:`--gantt=matplotlib-svg:report/Pipeline.svg`. A suffix that disagrees with the
format is reported rather than a file being written under a name that lies about its content.

matplotlib is an optional dependency. Without it, ``--gantt`` reports which extra installs it
(:pycode:`pyTooling[diagram]`) instead of failing on an import.

.. hint::

   In an SVG, every bar or line is a group named after the timespan it draws - ``span-<SpanID>`` - so a script can
   find the elements of a job.
   `pyTooling's rendering section <https://pyTooling.github.io/pyTooling/Tracing.html#tracing-render>`__ describes
   the identifiers.

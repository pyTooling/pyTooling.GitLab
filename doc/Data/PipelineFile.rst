.. _DATA/PipelineFile:

Pipeline File
#############

:mod:`pyTooling.GitLab.PipelineFile` models a **GitLab CI/CD configuration file** - the project's
:file:`.gitlab-ci.yml`, a file it includes, or the file of a child pipeline -, not a run of it (that's
:ref:`DATA/PipelineRun`):

.. code-block:: python

   from pathlib import Path
   from pyTooling.GitLab.PipelineFile import PipelineFile

   pipelineFile = PipelineFile.FromFile(Path(".gitlab-ci.yml"))

   print(f"{pipelineFile}: {pipelineFile.JobCount} jobs in stages {', '.join(pipelineFile.Stages)}")
   for job in pipelineFile.IterateJobs():
     print(f"  {job.Name:<24} {job.Stage:<10} {job.Image or ''}")

The file is read with ``ruamel.yaml``, a requirement of this package.


.. _DATA/PipelineFile/Tree:

The Tree
********

.. tree::

   - :class:`~pyTooling.GitLab.PipelineFile.PipelineFile` | a configuration file
     - :class:`~pyTooling.GitLab.PipelineFile.Workflow`   | the ``workflow`` key
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether a pipeline is created
     - :class:`~pyTooling.GitLab.PipelineFile.Include`    | an entry of ``include``
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether the file is included
     - :class:`~pyTooling.GitLab.PipelineFile.Default`    | the ``default`` key
     - :class:`~pyTooling.GitLab.PipelineFile.Variable`   | a default variable, declared in the top-level ``variables``
     - :class:`~pyTooling.GitLab.PipelineFile.Job`        | a job or a hidden job, in file order
       - :class:`~pyTooling.GitLab.PipelineFile.Need`     | an entry of the job's ``needs``
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether the job is added to a pipeline
       - :class:`~pyTooling.GitLab.PipelineFile.Variable` | a variable of the job

Every element knows its :attr:`~pyTooling.GitLab.PipelineFile.Base.Parent`, and holds a reference to the configuration
file it belongs to in :attr:`~pyTooling.GitLab.PipelineFile.Base.PipelineFile`.

A file may begin with a **header document**, separated from the configuration by ``---``, which holds the ``spec``
key. :meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.FromFile` accepts it and reads the configuration below it.


.. _DATA/PipelineFile/Stages:

Stages
******

:attr:`~pyTooling.GitLab.PipelineFile.PipelineFile.DeclaredStages` holds the ``stages`` key as written, or ``None``.
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFile.Stages` holds the stages the pipeline runs, in their order: the
declared ones, or ``build``, ``test`` and ``deploy`` (:data:`~pyTooling.GitLab.PipelineFile.DEFAULT_STAGES`) for a
file without ``stages``, always between ``.pre`` and ``.post``:

.. code-block:: yaml

   stages:              # Stages: .pre, lint, build, .post
     - lint
     - build


.. _DATA/PipelineFile/Variables:

Variables
*********

A variable of the top-level ``variables`` is a :class:`~pyTooling.GitLab.PipelineFile.Variable`. Its
:attr:`~pyTooling.GitLab.PipelineFile.Variable.Value` is the text GitLab reads - a number or a boolean written in the
file is its text, as ``3.14`` or ``true``. A variable declared as mapping may also carry:

* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Description` - GitLab prefills the variable in the form running a
  pipeline by hand, with the description beside it;
* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Options` - the values that form offers to select from;
* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Expand` - ``False``, if variables in the value aren't expanded.

.. code-block:: yaml

   variables:
     DEPLOY_ENVIRONMENT:
       value: "staging"
       description: "The deployment target."
       options: ["production", "staging"]


.. _DATA/PipelineFile/Jobs:

Jobs
****

A top-level key is a :class:`~pyTooling.GitLab.PipelineFile.Job`, unless it is a global keyword
(:data:`~pyTooling.GitLab.PipelineFile.RESERVED_KEYS`). A job whose name starts with a dot is a **hidden job**:
GitLab doesn't run it, other jobs extend it. The file keeps both apart, in file order:

.. code-block:: python

   pipelineFile.Jobs                       # the jobs, by name
   pipelineFile.HiddenJobs                 # the hidden jobs, by name
   pipelineFile.ContainsJob(".template")   # False: a hidden job isn't a job

A job runs in its :attr:`~pyTooling.GitLab.PipelineFile.Job.Stage` - ``test``, if it names none -, which
:meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.FromFile` checks against the pipeline's stages. The keys a job's
documentation needs are read too:

* :attr:`~pyTooling.GitLab.PipelineFile.Job.Script`, :attr:`~pyTooling.GitLab.PipelineFile.Job.BeforeScript` and
  :attr:`~pyTooling.GitLab.PipelineFile.Job.AfterScript` - the lines, a single line as a list of one, nested lists
  flattened;
* :attr:`~pyTooling.GitLab.PipelineFile.Job.When` - a :class:`~pyTooling.GitLab.PipelineFile.When`;
* :attr:`~pyTooling.GitLab.PipelineFile.Job.AllowFailure` and
  :attr:`~pyTooling.GitLab.PipelineFile.Job.AllowedExitCodes` - ``allow_failure`` as a boolean, or as a mapping of
  ``exit_codes``;
* :attr:`~pyTooling.GitLab.PipelineFile.Job.Image`, :attr:`~pyTooling.GitLab.PipelineFile.Job.Services` and
  :attr:`~pyTooling.GitLab.PipelineFile.Job.Environment` - the names, written as a string or as the ``name`` of a
  mapping; :attr:`~pyTooling.GitLab.PipelineFile.Job.Tags`;
* :attr:`~pyTooling.GitLab.PipelineFile.Job.Variables` - the job's variables.


.. _DATA/PipelineFile/Needs:

Dependencies Between Jobs
*************************

A job runs after the jobs of the earlier stages, unless it has a ``needs`` key: then it runs as soon as the jobs it
needs have run, and ``needs: []`` lets it start with the pipeline. :attr:`~pyTooling.GitLab.PipelineFile.Job.Needs`
tells the three apart - ``None``, the entries, or an empty tuple. Each entry is a
:class:`~pyTooling.GitLab.PipelineFile.Need`, whose :attr:`~pyTooling.GitLab.PipelineFile.Need.Kind` says what it
refers to:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - ``needs`` entry
     - :class:`~pyTooling.GitLab.PipelineFile.NeedKind`
   * - ``build`` or ``job: build``
     - ``Job`` - a job of the same pipeline
   * - ``pipeline: $PARENT_PIPELINE_ID`` and ``job``
     - ``PipelineJob`` - a job of another pipeline of the parent-child hierarchy
   * - ``project``, ``job`` and ``ref``
     - ``ProjectJob`` - a job of another project's pipeline, whose artifacts are downloaded
   * - ``pipeline: other/project`` alone
     - ``PipelineStatus`` - another project's pipeline, whose status the job mirrors

:attr:`~pyTooling.GitLab.PipelineFile.Need.Artifacts` and :attr:`~pyTooling.GitLab.PipelineFile.Need.IsOptional`
hold ``artifacts`` and ``optional``. :attr:`~pyTooling.GitLab.PipelineFile.Job.NeededJobs` resolves the needs of the
same pipeline to the jobs of the file:

.. code-block:: python

   for job in pipelineFile.IterateJobs():
     if job.Needs is not None:
       print(f"{job.Name} needs {', '.join(needed.Name for needed in job.NeededJobs)}")

:meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.FromFile` checks that a job needs only jobs of the file - an
optional need may name a missing job - and that the jobs don't need each other in a cycle.


.. _DATA/PipelineFile/Rules:

Rules and Workflow
******************

A job's ``rules`` decide whether it is added to a pipeline, the ``rules`` of the ``workflow`` key whether a pipeline
is created. GitLab evaluates them in order, and the first matching one decides; the model keeps them as written,
without evaluating them. A :class:`~pyTooling.GitLab.PipelineFile.Rule` holds:

* :attr:`~pyTooling.GitLab.PipelineFile.Rule.Condition` - the expression of ``if``;
* :attr:`~pyTooling.GitLab.PipelineFile.Rule.Changes` and :attr:`~pyTooling.GitLab.PipelineFile.Rule.CompareTo` -
  the paths of ``changes``, written as a list or as ``changes.paths``, and ``changes.compare_to``;
* :attr:`~pyTooling.GitLab.PipelineFile.Rule.Exists` - the paths of ``exists``, as a list or as ``exists.paths``;
* :attr:`~pyTooling.GitLab.PipelineFile.Rule.When`, :attr:`~pyTooling.GitLab.PipelineFile.Rule.AllowFailure` and
  :attr:`~pyTooling.GitLab.PipelineFile.Rule.Variables` - what applies, if the rule matches.

:attr:`PipelineFile.Workflow <pyTooling.GitLab.PipelineFile.PipelineFile.Workflow>` holds the
:class:`~pyTooling.GitLab.PipelineFile.Workflow` - the pipeline's :attr:`~pyTooling.GitLab.PipelineFile.Workflow.Name`
and its :attr:`~pyTooling.GitLab.PipelineFile.Workflow.Rules` -, or ``None`` for a file without ``workflow``:

.. code-block:: yaml

   workflow:
     name: "Pipeline for $CI_COMMIT_REF_NAME"
     rules:
       - if: $CI_COMMIT_TAG
         when: never
       - when: always


.. _DATA/PipelineFile/Includes:

Includes and Defaults
*********************

Each entry of ``include`` is an :class:`~pyTooling.GitLab.PipelineFile.Include`, whose
:attr:`~pyTooling.GitLab.PipelineFile.Include.Kind` says where the files come from and whose
:attr:`~pyTooling.GitLab.PipelineFile.Include.Location` names them, as written:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - ``include`` entry
     - :class:`~pyTooling.GitLab.PipelineFile.IncludeKind`, :attr:`~pyTooling.GitLab.PipelineFile.Include.Location`
   * - ``/ci/build.yml`` or ``local: /ci/build.yml``
     - ``Local``, the path
   * - ``https://example.com/ci.yml`` or ``remote: ...``
     - ``Remote``, the URL
   * - ``project: group/shared``, ``file``, ``ref``
     - ``Project``, the project's path; :attr:`~pyTooling.GitLab.PipelineFile.Include.Files` and
       :attr:`~pyTooling.GitLab.PipelineFile.Include.Ref`
   * - ``template: Auto-DevOps.gitlab-ci.yml``
     - ``Template``, the template's name
   * - ``component: $CI_SERVER_FQDN/group/components/lint@1.2``
     - ``Component``, the component's reference

An include's :attr:`~pyTooling.GitLab.PipelineFile.Include.Inputs` keep the types they are written with, and its
:attr:`~pyTooling.GitLab.PipelineFile.Include.Rules` decide whether the files are included. The included files
themselves aren't read.

:attr:`PipelineFile.Default <pyTooling.GitLab.PipelineFile.PipelineFile.Default>` holds the ``default`` key as a
:class:`~pyTooling.GitLab.PipelineFile.Default` - image, services, tags and the scripts around a job's script. The
global keywords ``image``, ``services``, ``before_script`` and ``after_script``, deprecated forms of ``default``, are
read into it too, unless ``default`` sets them.


.. _DATA/PipelineFile/Lines:

Source Lines
************

Every element keeps the :attr:`~pyTooling.GitLab.PipelineFile.Base.Line` it is written at, starting at 1, so a
consumer can point at the place a finding comes from. A malformed file raises
:exc:`~pyTooling.GitLab.PipelineFile.PipelineFileError`, which carries the file in
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFileError.Path` and the line in
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFileError.Line`, and names both in a note:

.. code-block:: text

   pyTooling.GitLab.PipelineFile.PipelineFileError: Variable 'A' has unknown key 'secret'.
     In '.gitlab-ci.yml:4'.

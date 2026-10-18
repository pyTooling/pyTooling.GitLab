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
     - :class:`~pyTooling.GitLab.PipelineFile.Input`      | an input of the header's ``spec:inputs``
     - :class:`~pyTooling.GitLab.PipelineFile.Workflow`   | the ``workflow`` key
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether a pipeline is created
     - :class:`~pyTooling.GitLab.PipelineFile.Include`    | an entry of ``include``
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether the file is included
     - :class:`~pyTooling.GitLab.PipelineFile.Default`    | the ``default`` key
     - :class:`~pyTooling.GitLab.PipelineFile.Variable`   | a default variable, declared in the top-level ``variables``
     - :class:`~pyTooling.GitLab.PipelineFile.Job`        | a job or a hidden job, in file order
       - :class:`~pyTooling.GitLab.PipelineFile.Need`     | an entry of the job's ``needs``
         - :class:`~pyTooling.GitLab.PipelineFile.Parallel` | the matrix instances needed
       - :class:`~pyTooling.GitLab.PipelineFile.Rule`     | a rule deciding whether the job is added to a pipeline
       - :class:`~pyTooling.GitLab.PipelineFile.Variable` | a variable of the job
       - :class:`~pyTooling.GitLab.PipelineFile.Input`    | an input of the job
       - :class:`~pyTooling.GitLab.PipelineFile.Parallel` | the job's ``parallel``: how often it runs, or its matrix
       - :class:`~pyTooling.GitLab.PipelineFile.Trigger`  | the child pipeline or other project's pipeline it starts
         - :class:`~pyTooling.GitLab.PipelineFile.Include` | a file of the child pipeline

Every element knows its :attr:`~pyTooling.GitLab.PipelineFile.Base.Parent`, and holds a reference to the configuration
file it belongs to in :attr:`~pyTooling.GitLab.PipelineFile.Base.PipelineFile`.

A file may begin with a **header document**, separated from the configuration by ``---``, which holds the ``spec``
key - see :ref:`DATA/PipelineFile/Inputs`.


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
* :attr:`~pyTooling.GitLab.PipelineFile.Job.When` - a :class:`~pyTooling.CI.RuleOutcome`;
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
:attr:`~pyTooling.GitLab.PipelineFile.Include.Rules` decide whether the files are included. The included files are
read only to resolve ``extends`` and ``!reference`` tags, with an
:class:`~pyTooling.GitLab.PipelineFile.IncludeResolver` - see :ref:`DATA/PipelineFile/Extends`.

:attr:`PipelineFile.Default <pyTooling.GitLab.PipelineFile.PipelineFile.Default>` holds the ``default`` key as a
:class:`~pyTooling.GitLab.PipelineFile.Default` - image, services, tags and the scripts around a job's script. The
global keywords ``image``, ``services``, ``before_script`` and ``after_script``, deprecated forms of ``default``, are
read into it too, unless ``default`` sets them.


.. _DATA/PipelineFile/Parallel:

Parallel Jobs and Triggers
**************************

A job's ``parallel`` is a :class:`~pyTooling.GitLab.PipelineFile.Parallel`: a
:attr:`~pyTooling.GitLab.PipelineFile.Parallel.Count`, or a :attr:`~pyTooling.GitLab.PipelineFile.Parallel.Matrix`
whose entries map variables to values. :attr:`~pyTooling.GitLab.PipelineFile.Parallel.Combinations` holds one
combination per instance, each entry contributing the product of its lists, and
:attr:`~pyTooling.GitLab.PipelineFile.Parallel.InstanceNames` the names GitLab gives the instances:

.. code-block:: yaml

   deploy:                      # deploy: [aws, monitoring], deploy: [aws, app1], deploy: [gcp, data]
     parallel:
       matrix:
         - PROVIDER: aws
           STACK: [monitoring, app1]
         - PROVIDER: gcp
           STACK: data
   test:                        # test 1/3, test 2/3, test 3/3
     parallel: 3

A need's :attr:`~pyTooling.GitLab.PipelineFile.Need.Parallel` names the matrix instances it needs, written as
``needs:parallel:matrix``.

A job's ``trigger`` is a :class:`~pyTooling.GitLab.PipelineFile.Trigger`. A trigger including files starts a **child
pipeline** - :attr:`~pyTooling.GitLab.PipelineFile.Trigger.Includes` holds the files as
:class:`~pyTooling.GitLab.PipelineFile.Include`\ s, also the ``artifact`` a job created for a dynamic child pipeline.
A trigger naming a :attr:`~pyTooling.GitLab.PipelineFile.Trigger.Project` - a string, or ``project`` of a mapping,
with an optional :attr:`~pyTooling.GitLab.PipelineFile.Trigger.Branch` - starts that **project's pipeline**.
:attr:`~pyTooling.GitLab.PipelineFile.Trigger.Strategy` says whether the job waits for the pipeline.


.. _DATA/PipelineFile/Extends:

Extends, References and Defaults
********************************

A job's keys are merged as GitLab merges them, before the job is built:

* ``!reference`` tags are replaced by what they refer to - in a list, a referred list is spliced in, as in
  ``script: [!reference [.setup, script], make]``. References nest up to 10 levels
  (:data:`~pyTooling.GitLab.PipelineFile.MAX_REFERENCE_DEPTH`).
* ``extends`` merges the jobs a job extends, in order, and then its own keys: mappings merge deeply, other values -
  lists included - replace, and ``null`` removes a key. Jobs extend each other up to 11 levels
  (:data:`~pyTooling.GitLab.PipelineFile.MAX_EXTENDS_DEPTH`). :attr:`~pyTooling.GitLab.PipelineFile.Job.Extends` keeps
  the names.
* A job gets every key of ``default``, and of the global keywords standing for it, which it doesn't set - unless
  ``inherit.default`` is ``false``, or lists the keys it inherits. Hidden jobs get none.

Every key keeps the line it is written at, also when another job contributes it.

A file may extend, or refer to, jobs of the files it includes. Read with an
:class:`~pyTooling.GitLab.PipelineFile.IncludeResolver`, the local files it includes - and those they include - are
read too, and their jobs and keys resolve; a key an included file contributes gets the line of the ``extends`` key or
the reference bringing it in. The included jobs aren't jobs of the file:

.. code-block:: python

   pipelineFile = PipelineFile.FromFile(Path(".gitlab-ci.yml"), IncludeResolver(Path(".")))

A missing job or key is an error, unless the file includes files that weren't read - another project's files, a URL,
a template, a component, or a local file without a resolver. Then the job is built from what was read, and
:attr:`~pyTooling.GitLab.PipelineFile.Job.Unresolved` names what it lacks, as ``extends .template`` or
``!reference [.setup, script]``.


.. _DATA/PipelineFile/Inputs:

Inputs
******

A CI/CD component's template, or a file included with inputs, declares its parameters in the header document's
``spec:inputs``. :attr:`PipelineFile.Inputs <pyTooling.GitLab.PipelineFile.PipelineFile.Inputs>` holds them as
:class:`~pyTooling.GitLab.PipelineFile.Input`\ s, and
:attr:`PipelineFile.Description <pyTooling.GitLab.PipelineFile.PipelineFile.Description>` holds ``spec:description``:

.. code-block:: yaml

   spec:
     description: "Lints a Python package."
     inputs:
       stage:
         default: test
         description: "Stage of the job."
       python:
         options: ["3.13", "3.14"]
         default: "3.14"
       version:
         regex: ^v\d+$
   ---
   lint:
     stage: $[[ inputs.stage ]]

An input has a :attr:`~pyTooling.GitLab.PipelineFile.Input.Type` - ``string``, if it doesn't say -, a
:attr:`~pyTooling.GitLab.PipelineFile.Input.Default` with the type it is written with, a
:attr:`~pyTooling.GitLab.PipelineFile.Input.Description`, :attr:`~pyTooling.GitLab.PipelineFile.Input.Options`, a
:attr:`~pyTooling.GitLab.PipelineFile.Input.Regex` and conditional :attr:`~pyTooling.GitLab.PipelineFile.Input.Rules`.
It is :attr:`~pyTooling.GitLab.PipelineFile.Input.Required` without a ``default`` key.
:meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.FromFile` checks that a default matches the type and the options.

A job's ``inputs`` - set when the job is run or retried by hand - are inputs too, in
:attr:`Job.Inputs <pyTooling.GitLab.PipelineFile.Job.Inputs>`; each needs a default.

A value interpolating an input, as ``$[[ inputs.stage ]]``, is kept as written: it is known when the file is included
only, so a stage or a needed job written that way isn't checked.


.. _DATA/PipelineFile/Pipeline:

Building a Pipeline
*******************

:meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.ToPipeline` builds the pipeline a file defines as a
:mod:`pyTooling.CI` model, as `pyTooling maps GitLab CI onto it
<https://pyTooling.github.io/pyTooling/CI/Pipeline.html#gitlab-ci>`__. Each element links back to the job it was built
from by :attr:`~pyTooling.GitLab.PipelineFile.DefinitionMixin.Definition`:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Job
     - Element
   * - a job running a script
     - :class:`~pyTooling.GitLab.PipelineFile.DefinedJob`
   * - a job with ``parallel``
     - :class:`~pyTooling.GitLab.PipelineFile.DefinedMatrix`, a :class:`~pyTooling.GitLab.PipelineFile.DefinedMatrixJob`
       per instance, whose dimensions are the matrix' variables, or ``CI_NODE_INDEX`` for ``parallel: N``, named as
       GitLab names it: ``test: [3.14, linux]``, ``test 1/3``
   * - a trigger job
     - :class:`~pyTooling.GitLab.PipelineFile.DefinedWorkflow`, whose reference is the other project or the child
       pipeline's files; with ``parallel``, a :class:`~pyTooling.GitLab.PipelineFile.DefinedMatrixWorkflow` per instance
   * - a hidden job
     - none

The pipeline is named by ``workflow:name``, or else by the file's name. A job without ``needs`` needs every element
of the nearest earlier stage holding elements; ``needs`` replaces that, and ``needs: []`` needs nothing. A need of
some instances of a matrix needs the whole matrix. A job's only rule is its
:attr:`~pyTooling.GitLab.PipelineFile.Job.Condition`. The result converts into a graph:

.. code-block:: python

   from pathlib import Path
   from pyTooling.GitLab.PipelineFile import IncludeResolver, PipelineFile

   pipelineFile = PipelineFile.FromFile(Path(".gitlab-ci.yml"))
   pipeline =     pipelineFile.ToPipeline(IncludeResolver(Path(".")))
   graph =        pipeline.ToGraph()

An :class:`~pyTooling.GitLab.PipelineFile.IncludeResolver` reads a trigger job's child pipeline from the repository's
directory, if its files are local; the workflow then holds the child pipeline's elements, and
:attr:`~pyTooling.GitLab.PipelineFile.ChildPipelineMixin.ChildFiles` the files. ``depth`` limits how many levels of
child pipelines are expanded.


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

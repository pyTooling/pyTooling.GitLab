.. _DATA/PipelineRun:

Pipeline Run
############

:mod:`pyTooling.GitLab` models a **GitLab CI/CD pipeline**, as GitLab's REST API reports it:

.. code-block:: python

   from pyTooling.GitLab import Pipeline

   pipeline = Pipeline.Parse(pipeline, jobs, bridges)  # the REST API's payloads

   print(f"{pipeline.Name}: {pipeline.Status} in {pipeline.Duration} s")
   for job in pipeline.IterateJobs():
     print(f"  {job.QualifiedName:<30} {job.Stage:<10} queued {job.QueuedDuration} s, ran {job.Duration} s")

.. contents:: Contents of this page
   :local:
   :depth: 1


.. _DATA/PipelineRun/Tree:

The Tree
********

.. tree::

   - :class:`~pyTooling.GitLab.PipelineGroup`                | every pipeline started for one commit
     - :class:`~pyTooling.GitLab.Pipeline`                   | a pipeline
       - :class:`~pyTooling.CI.Matrix`                       | ``parallel`` or ``parallel:matrix`` of a job
         - :class:`~pyTooling.GitLab.MatrixJob`              | one instance it produced
         - :class:`~pyTooling.GitLab.MatrixDownstreamPipeline` | one instance of a trigger job
       - :class:`~pyTooling.GitLab.Job`                      | a job that ran on a runner
       - :class:`~pyTooling.GitLab.DownstreamPipeline`       | a trigger job and the pipeline it started
         - :class:`~pyTooling.CI.Matrix`                     | the same elements a pipeline contains
         - :class:`~pyTooling.GitLab.Job`
         - :class:`~pyTooling.GitLab.DownstreamPipeline`

The tree is :mod:`pyTooling.CI`'s (see `pyTooling's pipeline model
<https://pyTooling.github.io/pyTooling/CI/Pipeline.html>`__, which maps GitLab CI onto it): a matrix is that model's
:class:`~pyTooling.CI.Matrix`, which this module imports, and the pipeline group, the pipeline, a job, a matrix
instance and a downstream pipeline derive from that model's classes. :class:`~pyTooling.GitLab.StatusMixin` adds what
GitLab reports about a pipeline, a downstream pipeline and a job - the :class:`~pyTooling.GitLab.Status`, the failure
reason and the URL - and the status is reported as the model's :attr:`~pyTooling.CI.Base.Outcome` too
(:meth:`Status.ToOutcome <pyTooling.GitLab.Status.ToOutcome>`). :class:`~pyTooling.GitLab.JobMixin` adds what GitLab
reports about a job and a trigger job: its identifier, its stage, whether it may fail, and how long it was queued.

Every element knows its :attr:`~pyTooling.CI.Base.Parent`, and holds a reference to the pipeline it belongs to in
:attr:`~pyTooling.CI.Base.Pipeline` - a job of a child pipeline the pipeline at the top, which started the child.

:meth:`~pyTooling.CI.JobGroup.IterateElements` yields what a group contains one level down: a pipeline its jobs, its
matrices and its downstream pipelines, a matrix its instances. To reach every job below a pipeline at once - those of
its matrices and of its child pipelines included - use :meth:`~pyTooling.CI.JobGroup.IterateJobs`:

.. code-block:: python

   for element in pipeline.IterateElements():  # one level: jobs, matrices, downstream pipelines
     print(f"{type(element).__name__}: {element}")

   for job in pipeline.IterateJobs():          # every job below the pipeline, at any depth
     print(job.QualifiedName)

An element is placed in its group **under its own name** - a downstream pipeline and a matrix as that key of
:attr:`~pyTooling.CI.Workflow.Workflows` respectively :attr:`~pyTooling.CI.Workflow.Matrices`, a job by its name -
so an element is asked for by that name:

.. code-block:: python

   pipeline.ContainsElement("build")              # a job, a matrix or a downstream pipeline of the pipeline
   matrix.ContainsElement("rspec: [3.4]")         # an instance carries the values telling it from its siblings
   pipeline.Workflows["components"].Jobs          # the jobs of a child pipeline

* **A matrix is not an element GitLab reports.** It names an instance after the job and the instance's values -
  ``rspec: [3.4]`` for ``parallel:matrix``, ``integration test 2/4`` for ``parallel: 4`` - and
  :meth:`~pyTooling.GitLab.Pipeline.Parse` reads the name back into the tree: a
  :class:`~pyTooling.GitLab.MatrixJob` below a :class:`~pyTooling.CI.Matrix` named ``rspec``.
* **A matrix instance's dimensions are named by position.** A job's name carries the values, not the variables'
  names - only the pipeline file names them. So :attr:`~pyTooling.CI.MatrixInstanceMixin.Dimensions` of
  ``test: [3.14, linux]`` is ``{"0": "3.14", "1": "linux"}``. An instance of ``parallel: N`` carries the variables
  GitLab sets for it: ``{"CI_NODE_INDEX": "2", "CI_NODE_TOTAL": "4"}``.
* The suffix is how GitLab names a job rather than a field, so a job genuinely named ``deploy 1/2`` by its pipeline
  file becomes a matrix of one instance.
* **A group iterates what it holds in the order it was created.** GitLab lists the newest job first;
  :meth:`~pyTooling.GitLab.Pipeline.Parse` adds the jobs by their identifier, which grows with a job's creation.
* A pipeline without a name - GitLab reports one only for a pipeline file setting ``workflow:name`` - is named by its
  number within the project, ``#47177``, as GitLab's interface shows it.
* **A job has no steps.** GitLab reports a job as a whole; its script's sections exist in the job's log only.
* :attr:`~pyTooling.GitLab.JobMixin.QueuedDuration` is the time GitLab reports a job was pending for a runner. The time
  a job waited for the jobs it depends on lies between :attr:`~pyTooling.CI.Base.CreatedAt` and
  :attr:`~pyTooling.CI.Base.StartedAt` as well, and isn't counted.


.. _DATA/PipelineRun/Downstream:

Downstream Pipelines
********************

A **trigger job** - GitLab calls it a *bridge* and lists it apart from the jobs - starts a downstream pipeline: a child
pipeline of the same project (``trigger:include``) or a pipeline of another project (``trigger:project``). It becomes
a :class:`~pyTooling.GitLab.DownstreamPipeline`, a :class:`~pyTooling.CI.Workflow` named after the trigger job:

.. code-block:: python

   pipeline = Pipeline.Parse(pipeline, jobs, bridges, downstream)

   child = pipeline.Workflows["components"]
   print(child.DownstreamID, child.DownstreamStatus, child.IsMultiProject)
   for job in child.Jobs:
     print(job.QualifiedName)                     # components / component:redis:test

* **It reports the downstream pipeline's own** :attr:`~pyTooling.GitLab.StatusMixin.Status`,
  :attr:`~pyTooling.GitLab.StatusMixin.URL` and times, and identifies it:
  :attr:`~pyTooling.GitLab.DownstreamPipeline.DownstreamID`,
  :attr:`~pyTooling.GitLab.DownstreamPipeline.DownstreamProjectID`. What GitLab reports about the trigger job is kept
  beside: :attr:`~pyTooling.GitLab.JobMixin.ID`, :attr:`~pyTooling.GitLab.JobMixin.Stage`,
  :attr:`~pyTooling.GitLab.DownstreamPipeline.TriggerStatus` and
  :attr:`~pyTooling.GitLab.DownstreamPipeline.TriggerURL`.
* **The downstream pipeline's contents are its jobs**, if its payloads are given in parameter ``downstream``: a mapping
  of the downstream pipeline's identifier to a JSON object with ``pipeline``, ``jobs``, ``bridges`` and its own
  ``downstream`` - the shape of :meth:`~pyTooling.GitLab.Pipeline.Parse`'s parameters, so a recorded pipeline is read
  with :pycode:`Pipeline.Parse(**recording)`. Its status, URL and times are those of its ``pipeline`` payload.
* A downstream pipeline whose payloads weren't read reports what the trigger job's ``downstream_pipeline`` summarizes:
  its status, URL and creation, and - once it ended - its last update as its completion. GitLab reports no start there.
* A multi-project pipeline names its project as :attr:`~pyTooling.CI.Workflow.Reference`, e.g.
  ``gitlab-org/ci-cd/tests/runner-incept``; its contents aren't read, as they belong to another project. A child
  pipeline has no reference: GitLab doesn't report the file the trigger job included.
* **A trigger job's status and its downstream pipeline's status differ** for a trigger job without
  ``strategy: depend``: it succeeds as soon as it started the downstream pipeline, whatever the downstream pipeline
  does later. A trigger job waiting to be started by hand hasn't started a pipeline: the downstream pipeline has no
  status and no times yet.
* A trigger job with ``parallel:matrix`` becomes a :class:`~pyTooling.GitLab.MatrixDownstreamPipeline` below a
  :class:`~pyTooling.CI.Matrix`, named like a matrix job: ``deploy: [staging]``.


.. _DATA/PipelineRun/Needs:

Stages and Needs
****************

**The REST API reports no dependencies.** A job reports its :attr:`~pyTooling.GitLab.JobMixin.Stage`, but GitLab
reports neither the order of the stages nor a job's ``needs:`` - both are in the pipeline file.
:meth:`~pyTooling.GitLab.PipelineContentsMixin.ApplyNeeds` adds the dependencies from them, as pyTooling's mapping of
GitLab CI describes it:

.. code-block:: python

   pipeline.ApplyNeeds(
     ["build", "test", "deploy"],                  # the pipeline file's 'stages:'
     {"unit": ["compile"], "release": []}          # the 'needs:' of the jobs having them
   )
   pipeline.Validate()

* An element named in the second parameter needs the siblings named there - a matrix or a downstream pipeline by its
  name -, and ``[]`` needs nothing.
* Every other element needs every element of the nearest earlier stage holding elements, so a stage without jobs is
  skipped.
* A downstream pipeline's contents have stages of their own: apply them to the downstream pipeline.


.. _DATA/PipelineRun/Strings:

Strings Become Enumerations
***************************

``status`` and ``source`` arrive as text. :class:`~pyTooling.GitLab.Status` and :class:`~pyTooling.GitLab.Source` turn
them into members, so a value GitLab doesn't document raises :exc:`~pyTooling.GitLab.GitLabError` instead of quietly
matching no comparison:

.. code-block:: python

   if pipeline.Source is Source.MergeRequestEvent:   # not: pipeline["source"] == "merge_request_event"
     ...

A status ending a pipeline or a job is an :class:`~pyTooling.CI.Outcome` too
(:data:`~pyTooling.GitLab.STATUS_TO_OUTCOME`), and a job failed for a timeout - failure reason
``job_execution_timeout`` or ``stuck_or_timeout_failure`` - has the outcome :attr:`~pyTooling.CI.Outcome.Timeout`. A
job waiting to be started by hand (:attr:`~pyTooling.GitLab.Status.Manual`) hasn't ended, so it has no outcome, and
neither has a matrix of such jobs.

Timestamps are parsed once, and a timestamp without a time zone is read as UTC, so every time of a pipeline can be
compared with every other.


.. _DATA/PipelineRun/Commit:

Several Pipelines per Commit
****************************

A commit can have several pipelines: one for the push of a branch, one for a merge request proposing it, one at a tag
of the same commit, a scheduled one. :class:`~pyTooling.GitLab.PipelineGroup` holds them. GitLab lists a project's
pipelines without its child pipelines, which belong to the pipeline that triggered them.

:attr:`~pyTooling.GitLab.Pipeline.GitReference` is a branch's or a tag's name, or a merge request's reference, and
:attr:`~pyTooling.GitLab.Pipeline.IsTag` tells a tag from a branch.
:meth:`~pyTooling.GitLab.PipelineGroup.ByGitReference` separates the pipelines by it:

.. code-block:: python

   group = PipelineGroup.Parse(pipelines)        # GET /projects/{id}/pipelines?sha=...

   for reference, pipelines in group.ByGitReference().items():
     print(f"{reference}: {len(pipelines)} pipeline(s)")

   # main: 1 pipeline(s)
   # refs/merge-requests/6293/merge: 1 pipeline(s)

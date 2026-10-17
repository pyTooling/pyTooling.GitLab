.. _DATA/PipelineRun:

Pipeline Run
############

:mod:`pyTooling.GitLab` models a **GitLab CI/CD pipeline**, as GitLab's REST API reports it:

.. code-block:: python

   from pyTooling.GitLab import Pipeline

   pipeline = Pipeline.Parse(pipeline, jobs)  # the REST API's payloads

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
       - :class:`~pyTooling.GitLab.Job`                      | a job that ran on a runner

The tree is :mod:`pyTooling.CI`'s (see `pyTooling's pipeline model
<https://pyTooling.github.io/pyTooling/CI/Pipeline.html>`__, which maps GitLab CI onto it): a matrix is that model's
:class:`~pyTooling.CI.Matrix`, which this module imports, and the pipeline group, the pipeline, a job and a matrix
instance derive from that model's classes. :class:`~pyTooling.GitLab.StatusMixin` adds what GitLab reports about a
pipeline and a job - the :class:`~pyTooling.GitLab.Status`, the failure reason and the URL - and the status is reported
as the model's :attr:`~pyTooling.CI.Base.Outcome` too (:meth:`Status.ToOutcome <pyTooling.GitLab.Status.ToOutcome>`).
:class:`~pyTooling.GitLab.JobMixin` adds what GitLab reports about a job: its identifier, its stage, whether it may
fail, and how long it was queued.

Every element knows its :attr:`~pyTooling.CI.Base.Parent`, and holds a reference to the pipeline it belongs to in
:attr:`~pyTooling.CI.Base.Pipeline`.

:meth:`~pyTooling.CI.JobGroup.IterateElements` yields what a group contains one level down: a pipeline its jobs and
its matrices, a matrix its instances. To reach every job below a pipeline at once - those of its matrices included -
use :meth:`~pyTooling.CI.JobGroup.IterateJobs`:

.. code-block:: python

   for element in pipeline.IterateElements():  # one level: jobs and matrices
     print(f"{type(element).__name__}: {element}")

   for job in pipeline.IterateJobs():          # every job below the pipeline, at any depth
     print(job.QualifiedName)

An element is placed in its group **under its own name** - a matrix as that key of
:attr:`~pyTooling.CI.Workflow.Matrices`, a job by its name - so an element is asked for by that name:

.. code-block:: python

   pipeline.ContainsElement("build")              # a job or a matrix of the pipeline
   matrix.ContainsElement("rspec: [3.4]")         # an instance carries the values telling it from its siblings

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

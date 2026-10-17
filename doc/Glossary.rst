.. _GLOSSARY:

Glossary
########

.. glossary::

   Bridge
   Trigger Job
     A :term:`job` with ``trigger``, which starts a :term:`downstream pipeline` instead of running a script on a
     :term:`runner`. GitLab's REST API lists it among a pipeline's
     `bridges <https://docs.gitlab.com/api/jobs/>`__. See GitLab's
     `downstream pipelines <https://docs.gitlab.com/ci/pipelines/downstream_pipelines/>`__.

   CI/CD Component
     A reusable unit of pipeline configuration, included with ``include:component`` and configured by its
     :term:`inputs <spec:inputs>`. See GitLab's `CI/CD components <https://docs.gitlab.com/ci/components/>`__.

   CI_JOB_TOKEN
     The token GitLab creates for every :term:`job`, with which a job reads the API of its own project. See GitLab's
     `CI/CD job token <https://docs.gitlab.com/ci/jobs/ci_job_token/>`__.

   Child Pipeline
     A :term:`downstream pipeline` of the same project, started by a :term:`trigger job` with ``trigger:include``.
     See GitLab's `downstream pipelines <https://docs.gitlab.com/ci/pipelines/downstream_pipelines/>`__.

   Domain
     A `Sphinx domain <https://www.sphinx-doc.org/en/master/usage/domains/index.html>`__ groups the directives and roles
     describing objects of one kind, under a name like ``py`` or ``glci``. See :ref:`GLCI`.

   DOT
     The `graph description language <https://graphviz.org/doc/info/lang.html>`__ of Graphviz, which the
     :ref:`pipeline graph <VIS/PipelineGraph>` is written in.

   Downstream Pipeline
     A :term:`pipeline` started by a :term:`trigger job` of another pipeline: a :term:`child pipeline` of the same
     project, or a multi-project pipeline of another project. See GitLab's
     `downstream pipelines <https://docs.gitlab.com/ci/pipelines/downstream_pipelines/>`__.

   Gantt Chart
     A bar chart of timespans on a time axis, a row per task. See :ref:`VIS/PipelineTrace`.

     Wikipedia: :wiki:`Gantt chart <Gantt_chart>`

   Include
     The ``include`` keyword, which adds the configuration of other YAML files - local, from another project, from a
     URL, a template or a :term:`CI/CD component` - to a :term:`pipeline file`. See GitLab's
     `includes <https://docs.gitlab.com/ci/yaml/includes/>`__.

   Job
     The script a :term:`runner` executes, or a :term:`trigger job`. Jobs of a :term:`stage` run in parallel; a job
     with :term:`needs` starts as soon as the jobs it needs are done. See GitLab's
     `jobs <https://docs.gitlab.com/ci/jobs/>`__.

   Matrix
     A job's ``parallel:matrix``: the job runs once per combination of the matrix' variables. ``parallel: N`` runs a
     job *N* times. See GitLab's `CI/CD YAML syntax <https://docs.gitlab.com/ci/yaml/>`__.

   Needs
     The jobs a :term:`job` depends on, which have to complete before it starts, regardless of its :term:`stage`. See
     GitLab's `CI/CD YAML syntax <https://docs.gitlab.com/ci/yaml/>`__.

   OTLP
     The `OpenTelemetry Protocol <https://opentelemetry.io/docs/specs/otlp/>`__, which carries :term:`traces <trace>`
     to a collector or viewer; its JSON encoding is OTLP/JSON. See :ref:`VIS/PipelineTrace`.

   Pipeline
     One run of a :term:`pipeline file`, with the jobs it ran, read from GitLab's REST API - its
     `pipelines <https://docs.gitlab.com/api/pipelines/>`__ and `jobs <https://docs.gitlab.com/api/jobs/>`__. See
     GitLab's `pipelines <https://docs.gitlab.com/ci/pipelines/>`__ and :ref:`DATA/PipelineRun`.

   Pipeline File
     The YAML file describing a project's pipeline, by default :file:`.gitlab-ci.yml`, and the files it
     :term:`includes <include>`: its :term:`stages <stage>`, :term:`jobs <job>`, variables and rules. See GitLab's
     `CI/CD YAML syntax <https://docs.gitlab.com/ci/yaml/>`__ and :ref:`DATA/PipelineFile`.

   Rules
     A job's ``rules``, deciding whether the job is added to a pipeline and how it runs, by conditions (``if``) on
     variables, changed files and existing files. See GitLab's
     `rules <https://docs.gitlab.com/ci/jobs/job_rules/>`__.

   Runner
     The application executing a :term:`job`, selected by the job's ``tags``. See GitLab's
     `runner <https://docs.gitlab.com/runner/>`__.

   Span
     A timespan of a :term:`trace`, with a name, a begin and an end, attributes, and the spans below it. See
     OpenTelemetry's `traces <https://opentelemetry.io/docs/concepts/signals/traces/>`__.

   spec:inputs
     The parameters of a :term:`pipeline file` or :term:`CI/CD component`, declared in a header document before
     ``---``: a name, a type, a default, a description, the allowed options. See GitLab's
     `CI/CD inputs <https://docs.gitlab.com/ci/inputs/>`__ and :ref:`GLCI/Pipeline`.

   Stage
     A group of :term:`jobs <job>`, listed in ``stages``. A stage's jobs start when the jobs of the earlier stages are
     done, unless they declare :term:`needs`. See GitLab's `CI/CD YAML syntax <https://docs.gitlab.com/ci/yaml/>`__.

   Trace
     A tree of :term:`spans <span>` recording where time went. The trace of a :term:`pipeline` has a span for every
     child pipeline, matrix and job, with the attributes of OpenTelemetry's
     `semantic conventions for CI/CD <https://opentelemetry.io/docs/specs/semconv/registry/attributes/cicd/>`__.
     See :ref:`VIS/PipelineTrace`.

   Variable
     A name-value pair a :term:`job` sees in its environment. A variable of a :term:`pipeline file` with a
     ``description`` is offered in the *Run pipeline* form. See GitLab's
     `CI/CD variables <https://docs.gitlab.com/ci/variables/>`__.

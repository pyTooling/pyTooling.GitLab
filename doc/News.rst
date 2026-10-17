.. _NEWS:

News
####

See :gh:`pyTooling.GitLab Release Pages <pyTooling/pyTooling.GitLab/releases>` for detail release notes on every
release.


Version 0.x (2026)
******************

.. topic:: :gh:`v0.1.0 - unreleased <pyTooling/pyTooling.GitLab/releases/v0.1.0>`

   .. rubric:: New Features

   * First release: pyTooling.GitLab, a sub-namespace of :doc:`pyTooling <pyTool:index>`, to work with GitLab CI/CD
     pipelines.
   * 🚧 Data models: :ref:`pipeline runs <DATA/PipelineRun>` read from the GitLab REST API, and :ref:`pipeline files
     <DATA/PipelineFile>` (:file:`.gitlab-ci.yml`).
   * 🚧 The Sphinx domain :ref:`glci <GLCI>` documents a pipeline file's inputs and variables from the file itself.
   * 🚧 Visualization: the :ref:`pipeline graph <VIS/PipelineGraph>` of a pipeline file, and the :ref:`trace of a
     pipeline <VIS/PipelineTrace>` as OTLP/JSON and as a Gantt chart.
   * 🚧 The program :ref:`pytooling-gitlab <CLI>` reads a pipeline into a trace, writes it, and draws it.

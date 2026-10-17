.. raw:: latex

   \part{Introduction}

.. shields::
   :github:                pyTooling/pyTooling.GitLab
   :pypi:                  pyTooling.GitLab
   :source-license:        github:LICENSE.md
   :documentation-license: CC-BY-4.0 github:doc/Doc-License.rst
   :github-action:         Pipeline.yml@main
   :documentation:         github-pages

   github, src-license, ghp-doc, doc-license
   pypi-tag, pypi-status, pypi-python
   github-action, lib-status, codecov-coverage

--------------------------------------------------------------------------------

The pyTooling.GitLab Documentation
##################################

**pyTooling.GitLab** works with GitLab CI/CD pipelines: it reads pipeline files (:file:`.gitlab-ci.yml`) into a data
model, reads the runs of a pipeline from GitLab's REST API, and converts them into traces - e.g. OpenTelemetry's
OTLP/JSON or a Gantt chart of the jobs. A Sphinx domain ``glci`` documents a pipeline file's inputs and variables
taken straight from the file.

It builds on :gh:`pyTooling <pyTooling/pyTooling>`'s generic CI pipeline model and tracing, and on
:gh:`pyTooling.Sphinx <pyTooling/pyTooling.Sphinx>` for its documentation extensions. Its sibling
:gh:`pyTooling.GitHub <pyTooling/pyTooling.GitHub>` does the same for GitHub Actions.


.. attention::

   The Sphinx domain ``glci`` requires :doc:`pyTooling.Sphinx <pyToolSphinx:index>`, and thus **Python 3.12 or
   newer**, because Sphinx 9.1 requires Python 3.12.

The package is installed from PyPI:

.. code-block:: bash

   pip install pyTooling.GitLab


.. _FEATURES:

Features
********

Data models
===========

🚧 :ref:`Pipeline runs <DATA/PipelineRun>`
  |rarr| A GitLab pipeline - its jobs, matrices and child pipelines with their times and outcomes - read from the
  GitLab REST API's payloads.
🚧 :ref:`Pipeline files <DATA/PipelineFile>`
  |rarr| A :file:`.gitlab-ci.yml` and the files it includes: stages, jobs with their needs and rules, variables and
  inputs, read with line numbers, and converted into a pipeline graph.

Sphinx domain ``glci``
======================

The domain needs the extra ``sphinx``, which installs pyTooling.Sphinx:

.. code-block:: bash

   pip install pyTooling.GitLab[sphinx]

🚧 :ref:`Pipelines and their parameters <GLCI/Pipeline>`
  |rarr| A pipeline file's ``spec:inputs`` and its described variables, taken straight from the file; roles to
  reference them.
🚧 :ref:`Summaries <GLCI/Summaries>`
  |rarr| Parameter tables, the interface, the dependencies and YAML excerpts of a pipeline file.

Visualization
=============

🚧 :ref:`Pipeline graph <VIS/PipelineGraph>`
  |rarr| The jobs of a pipeline file, their stages and ``needs`` as a Graphviz graph.
🚧 :ref:`Pipeline trace diagram <VIS/PipelineTrace>`
  |rarr| Reads a pipeline through the GitLab REST API into a trace, written as OpenTelemetry's OTLP/JSON or drawn as a
  Gantt chart.

Program
=======

Gantt charts need the extra ``diagram``, which installs matplotlib:

.. code-block:: bash

   pip install pyTooling.GitLab[diagram]

🚧 :ref:`pytooling-gitlab <CLI>`
  |rarr| The command ``pipeline`` reads a pipeline into a trace, writes it, and draws it as a Gantt chart.


.. _CONSUMERS:

Consumers
*********

This layer is used by:

* 🚧 No consumer yet.


.. _CONTRIBUTORS:

Contributors
************

* :gh:`Patrick Lehmann <Paebbels>` (Maintainer)
* :gh:`and more... <pyTooling/pyTooling.GitLab/graphs/contributors>`


.. _LICENSE:

License
*******

.. only:: html

   This Python package (source code) is licensed under `Apache License 2.0 <License.html>`__. |br|
   The accompanying documentation is licensed under
   `Creative Commons - Attribution 4.0 (CC-BY 4.0) <Doc-License.html>`__.

.. only:: latex

   This Python package (source code) is licensed under **Apache License 2.0**. |br|
   The accompanying documentation is licensed under **Creative Commons - Attribution 4.0 (CC-BY 4.0)**.


.. toctree::
   :hidden:

   Subnamespace of pyTooling ➚ <https://pyTooling.github.io/pyTooling/>

.. toctree::
   :caption: Introduction
   :hidden:

   News
   Installation
   Dependency
   CompetingSolutions

.. raw:: latex

   \part{Main Documentation}

.. toctree::
   :caption: Data Models
   :hidden:

   Data/PipelineRun
   Data/PipelineFile

.. toctree::
   :caption: glci Domain
   :hidden:

   GLCI/index
   GLCI/Pipelines
   GLCI/Summaries

.. toctree::
   :caption: Visualization
   :hidden:

   Visualization/PipelineGraph
   Visualization/PipelineTrace

.. toctree::
   :caption: Program
   :hidden:

   CLI

.. raw:: latex

   \part{References and Reports}

.. toctree::
   :caption: References and Reports
   :hidden:

   Python Class Reference <pyTooling.GitLab/pyTooling.GitLab>
   unittests/index
   coverage/index
   CodeCoverage
   Doc. Coverage Report <DocCoverage>
   Static Type Check Report ➚ <typing/index>

.. raw:: latex

   \part{Appendix}

.. toctree::
   :caption: Appendix
   :hidden:

   License
   Doc-License
   Glossary
   genindex
   Python Module Index <modindex>
   TODO

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

**pyTooling.GitLab** works with GitLab CI/CD pipelines: it reads pipeline configuration files (``.gitlab-ci.yml``) into
a data model, reads the runs of a pipeline from GitLab's REST API, and converts them into traces - e.g.
OpenTelemetry's OTLP/JSON or a Gantt chart of the jobs.

It builds on :gh:`pyTooling <pyTooling/pyTooling>`'s generic CI pipeline model and tracing, and on
:gh:`pyTooling.Sphinx <pyTooling/pyTooling.Sphinx>` for its documentation extensions.


.. _GOALS:

Goals
*****

* 🚧 Pipeline configuration files - a ``.gitlab-ci.yml`` file read into a data model.
* 🚧 Pipeline runs - a pipeline with its jobs, their times and outcomes, read from GitLab's REST API.
* 🚧 Traces - a pipeline run converted into a trace, written as OpenTelemetry's OTLP/JSON.


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

   Installation

.. raw:: latex

   \part{References}

.. toctree::
   :caption: References
   :hidden:

   Python Class Reference <pyTooling.GitLab/pyTooling.GitLab>

.. raw:: latex

   \part{Appendix}

.. toctree::
   :caption: Appendix
   :hidden:

   License
   Doc-License
   genindex
   Python Module Index <modindex>

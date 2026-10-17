.. _GLCI:

Overview
########

The Sphinx domain ``glci`` documents **GitLab CI/CD pipeline files** - above all files others include, a CI/CD
component's template or a shared configuration, whose inputs and described variables are the interface a caller uses.
What the pipeline file states - an input's type, whether it is required, its default and options - is read from the file
with :mod:`pyTooling.GitLab.PipelineFile`, so a page doesn't copy it and can't drift from it. What the file can't say
stays hand-written, as the content of a directive.

The domain is the Sphinx extension :mod:`pyTooling.GitLab.Sphinx`. It builds on
`pyTooling.Sphinx <https://pyTooling.github.io/pyTooling.Sphinx/>`__, which it sets up itself, and is installed with
the extra ``sphinx``: ``pyTooling.GitLab[sphinx]``.

.. code-block:: Python

   # doc/conf.py
   extensions = [
     ...,
     "pyTooling.GitLab.Sphinx",
   ]

The domain's directives are described on this page's siblings:

:ref:`GLCI/Pipeline`
  |rarr| ``glci:pipeline`` and the entries of its inputs and variables, and the roles referring to them.

.. contents:: Contents of this page
   :local:
   :depth: 1


.. _GLCI/Config:

Configuration
*************

.. code-block:: Python

   # doc/conf.py
   glci_project =            "group/project"   # the documented project
   glci_repository_root =    ".."              # relative to the Sphinx source directory
   glci_pipeline_directory = "../templates"    # relative to the Sphinx source directory

.. confval:: glci_pipeline_directory

   The directory holding the pipeline files, relative to the Sphinx source directory. A ``glci:pipeline`` without
   ``:file:`` reads ``<name>.yml``, ``<name>.yaml``, or a CI/CD component's ``<name>/template.yml`` from it. Without
   it, the files are read from :confval:`glci_repository_root`. Default: ``None``.

.. confval:: glci_repository_root

   The documented repository's root directory, relative to the Sphinx source directory. A local ``include`` - for
   ``extends`` and ``!reference`` - and a child pipeline's file are read from it, as GitLab reads them from the
   repository. Default: ``None``.

.. confval:: glci_project

   The documented project, as ``group/project`` or ``group/subgroup/project``. Default: ``None``.

.. confval:: glci_ref

   The ref - a branch or tag - of the documented project the documentation describes, as ``v1``. Default: ``None``.

.. confval:: glci_server

   The URL of the GitLab instance links point to: ``https://gitlab.com``, or a self-managed instance's, as
   ``https://gitlab.example.com``. Default: ``"https://gitlab.com"``.

.. confval:: glci_label_prefix

   The root of the ``:ref:`` labels the directives register besides their targets - see :ref:`GLCI/Labels`. ``None``
   registers none. Default: ``"PIPELINE"``.


.. _GLCI/Labels:

Labels
******

Besides its target, each directive registers a ``:ref:`` label - :confval:`glci_label_prefix` is their root - so a page
refers to an entry as it refers to any section:

.. code-block:: text

   PIPELINE/Package                          .. glci:pipeline:: Package
   PIPELINE/Package/Input/package_name       .. glci:input:: package_name
   PIPELINE/Package/Variable/DEPLOY_ENV      .. glci:variable:: DEPLOY_ENV

A parameter's section carries the anchor of its label, and the anchor docutils derives from its title, so a link into a
hand-written page converted to the domain lands on the same entry. A label still declared by hand next to the directive
is a duplicate.


.. _GLCI/Warnings:

Warnings
********

The page and the pipeline file are compared while the page is read. A difference is a warning of type ``glci.drift``,
so ``-W`` fails the build, and ``suppress_warnings = ["glci.drift"]`` silences it.

* A ``glci:input`` or ``glci:variable`` names a parameter the pipeline file doesn't have.
* A hand-written field repeats a fact of the pipeline file - *Type*, *Required* or *Default Value* of an input, and
  *Possible Values* or *Pattern* of an input stating ``options`` or ``regex``; *Type* and *Default Value* of a
  variable, and its *Possible Values* if it states ``options``. It is not shown; the file's value is.

A pipeline file that can't be found or read is a warning of type ``glci.pipeline`` at the place in the file, as
``Package.yml:8``, as is a ``glci:input`` or ``glci:variable`` without a preceding ``glci:pipeline``. A pipeline
documented twice is a warning of type ``glci.duplicate``.


.. _GLCI/API:

Extending the Domain
********************

A directive of another module reaches the domain with ``self.env.get_domain("glci")``, a
:class:`~pyTooling.GitLab.Sphinx.GitLabCIDomain`:

* :meth:`~pyTooling.GitLab.Sphinx.GitLabCIDomain.GetCurrentPipeline` returns the model of the document's current
  pipeline file, a :class:`pyTooling.GitLab.PipelineFile.PipelineFile`;
* :meth:`~pyTooling.GitLab.Sphinx.GitLabCIDomain.LoadPipelineFile` reads a pipeline file, every file once;
* :attr:`~pyTooling.GitLab.Sphinx.GitLabCIDomain.Resolver` reads local includes and child pipeline files from
  :confval:`glci_repository_root`;
* :meth:`~pyTooling.GitLab.Sphinx.GitLabCIDomain.ResolvePipeline` says where a pipeline is documented;
* :meth:`ParameterDirective.CreateEntry <pyTooling.GitLab.Sphinx.ParameterDirective.CreateEntry>` creates a parameter's
  entry and registers it.

A directive is added to the domain with
:meth:`Sphinx.add_directive_to_domain <sphinx.application.Sphinx.add_directive_to_domain>`.

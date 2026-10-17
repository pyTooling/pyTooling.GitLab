.. _VIS/PipelineGraph:

Pipeline Graph
##############

The jobs of a pipeline file and their dependencies form a graph. The ``glci`` domain draws it in a Sphinx documentation,
so the domain has to be enabled - see :ref:`GLCI`.

.. grid:: 2

   .. grid-item::
      :columns: 6

      The ``glci:pipeline-graph`` directive draws the pipeline a GitLab CI/CD pipeline file defines - its jobs and their
      dependencies - from the pipeline file itself:

      * a job is a node labelled with its name and its stage;
      * a job running a script is a grey box with square corners;
      * a job with a condition - its ``rules:if`` - is dashed, and in HTML its tooltip is the condition; a manual job is
        dashed and labelled *manual*;
      * a job with ``parallel:matrix`` is a cluster of its instances, labelled with the matrix' dimensions; one with
        ``parallel: N`` with the count;
      * a trigger job starting another project's pipeline is a white leaf naming that project;
      * a trigger job starting a child pipeline is a rounded box naming the child pipeline's files, and is expanded into
        a cluster of the child pipeline's jobs, as many levels deep as ``:depth:`` says;
      * the dependencies are the edges - a job's ``needs``, or for a job without them every job of the nearest earlier
        stage -, without those a longer path implies.

      The pipeline file is read with :mod:`pyTooling.GitLab.PipelineFile`, converted into a :mod:`pyTooling.CI` model
      and its :class:`~pyTooling.Graph.Graph` (:ref:`DATA/PipelineFile`), and drawn by :mod:`sphinx.ext.graphviz`.
      Every pipeline file drawn becomes a dependency of the page.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         .. glci:pipeline-graph:: Pipelines/Pipeline.yml
            :depth: 1
            :caption: The pipeline of Pipeline.yml.

This is how the example renders, drawn from :download:`Pipelines/Pipeline.yml` and :download:`Pipelines/ci/release.yml`:

.. glci:pipeline-graph:: Pipelines/Pipeline.yml
   :depth: 1
   :caption: The pipeline of Pipeline.yml.

.. rst:directive:: .. glci:pipeline-graph:: <path of a pipeline file>

   Draws the pipeline file the argument names, relative to the document.

   .. rst:directive:option:: depth: <levels>

      Levels of child pipelines to expand into clusters. Default: 0.

   .. rst:directive:option:: direction: LR | TB

      Whether the pipeline flows from left to right or from top to bottom. Default: ``LR``.

   .. rst:directive:option:: reduce: yes | no

      Whether an edge a longer path implies is dropped. Default: ``yes``.

   .. rst:directive:option:: link: yes | no

      Whether a trigger job links to the page documenting its child pipeline, in HTML. Default: ``yes``.

   .. rst:directive:option:: caption: <text>

      A caption under the graph.

   .. rst:directive:option:: name: <label>

      A label to reference the graph by.

   .. rst:directive:option:: align: left | center | right

      The graph's horizontal alignment.

   .. rst:directive:option:: alt: <text>

      The graph's alternative text. Default: ``Pipeline of <file name>``.


.. _VIS/PipelineGraph/Repository:

Child Pipelines and Links
*************************

A child pipeline's file is named by the trigger job's ``trigger:include``, as ``/ci/release.yml``: a path relative to
the repository's root. :file:`conf.py` says where that root is:

.. code-block:: Python

   # doc/conf.py
   glci_repository_root = ".."

The graph reads the configuration values of the domain (:ref:`GLCI/Config`), and its pipeline files through the domain,
which reads every file once per build:

* The child pipelines are read from :confval:`glci_repository_root`. Without it, they are read relative to the directory
  of the drawn pipeline file.
* A child pipeline from another project, a template, a remote file or a job's artifact isn't expanded.

A trigger job links to the page the ``glci`` domain documents its child pipeline on, as the pipeline named like the stem
of the child pipeline's first local file - ``release`` for ``/ci/release.yml``. Without such a page, and in a format
other than HTML, the job has no link.

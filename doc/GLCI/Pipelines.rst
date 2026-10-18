.. _GLCI/Pipeline:

Pipelines and Parameters
########################

.. _GLCI/Pipeline/Directive:

Pipelines
*********

.. rst:directive:: .. glci:pipeline:: <name>

   Registers the pipeline ``<name>`` with an index entry, and makes it the **current pipeline** of the document.

   The directive writes no visible output. Placed above the page's title, its target is the title, as a label is.

   .. rst:directive:option:: file: <path>

      Path to the pipeline file, relative to the document. Without it, the file is ``<name>.yml``, ``<name>.yaml``, or a
      CI/CD component's ``<name>/template.yml``, in :confval:`glci_pipeline_directory`.

.. code-block:: ReST

   .. glci:pipeline:: Package
      :file: ../../templates/Package/template.yml

   Package
   #######

   The ``Package`` component ...

A document using the pipeline is read again, when the pipeline file changed.


.. _GLCI/Roles:

Roles
*****

.. rst:role:: glci:pipeline

   Refers to a pipeline by its name:

   .. code-block:: ReST

      :glci:pipeline:`Package`

   A target that isn't documented is a warning.

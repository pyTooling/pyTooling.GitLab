.. _GLCI/Summaries:

Summaries
#########

The directives below summarize the current pipeline file. Like the entries, they read the pipeline file, so they can't
drift from it.


.. _GLCI/ParameterTable:

Parameter Tables
****************

.. grid:: 2

   .. grid-item::
      :columns: 6

      ``glci:parameter-table`` renders the summary tables of the current pipeline file's parameters - one per kind, the
      parameters in file order, each name linked to its entry:

      * **inputs** - *Parameter Name*, *Required*, *Type* and *Default*;
      * **variables** - *Variable Name*, *Default* - the ``value`` - and the ``description`` of the pipeline file.

      A default longer than 120 characters, or of several lines, is shortened in the table and followed by ``…``; the
      entry shows it in full.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         Parameter Summary
         *****************

         .. rubric:: Inputs

         .. glci:parameter-table::
            :kinds: inputs

         .. rubric:: Variables

         .. glci:parameter-table::
            :kinds: variables

.. rst:directive:: .. glci:parameter-table::

   .. rst:directive:option:: kinds: <kind> ...

      The kinds of parameters to summarize, from ``inputs`` and ``variables``, separated by spaces or commas. The tables
      are rendered in the order written. Without the option, a table is rendered for every kind the pipeline file has
      parameters of, in the order inputs, variables. A kind named here, of which the file has none, is a table saying
      so.


.. _GLCI/Interface:

Interface
*********

.. grid:: 2

   .. grid-item::
      :columns: 6

      ``glci:interface`` renders the contract of the current pipeline file with a pipeline including it, as a field
      list:

      * **Required Inputs** - the inputs without a default, which ``include:inputs`` has to set;
      * **Variables** - the default variables with a ``description``, which the form running a pipeline by hand
        prefills;
      * **Stages** - the stages the file's jobs run in. An included file's jobs need these stages in the including
        pipeline's ``stages``. A stage given by an input, as ``$[[ inputs.stage ]]``, is shown as written;
      * **Jobs** and **Hidden Jobs** - the jobs the file adds to a pipeline, and the hidden jobs another file may
        ``extends``.

      Inputs and variables are linked to their entries.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         .. topic:: Interface

            .. glci:interface::

.. rst:directive:: .. glci:interface::

   Summarizes the contract of the current pipeline file with a pipeline including it.

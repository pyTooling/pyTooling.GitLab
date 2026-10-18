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

      Inputs and variables are linked to their entries. What the file includes is listed by ``glci:dependencies``.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         .. topic:: Interface

            .. glci:interface::

.. rst:directive:: .. glci:interface::

   Summarizes the contract of the current pipeline file with a pipeline including it.


.. _GLCI/Dependencies:

Dependencies
************

.. grid:: 2

   .. grid-item::
      :columns: 6

      ``glci:dependencies`` renders what the current pipeline file uses, as a nested bullet list. From the pipeline
      file, and from the local files it includes and triggers, as far as they are found below
      :confval:`glci_repository_root`:

      * the files **included** - a local file, another project's files, a URL, a template, a component, a job's
        artifact -, each once. A local file is listed with its own dependencies, and links to GitLab when
        :confval:`glci_ref` is configured; another project, a URL and a component link to their place;
      * the **pipelines triggered** - a child pipeline with the files it runs, another project's pipeline with the
        project;
      * the **images** of the containers and service containers the jobs run in, those of ``default`` included.

      What a file can't tell - packages a script installs, tools it calls - is the directive's content: a bullet list
      merged into the derived one. An item whose text is the name of a derived item adds its nested list to that
      item, recursively; any other item is appended to its list. Content after the bullet list follows the list.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         .. topic:: Dependencies

            .. glci:dependencies::

               * /ci/build.yml

                 * GCC

               * pip

.. rst:directive:: .. glci:dependencies::

   Lists the files the current pipeline file includes, the pipelines it triggers and the container images it uses,
   merged with the hand-written items of its content. A derived item is named by:

   ================= ==============================================================================================
   Derived item      Names
   ================= ==============================================================================================
   include           the location as written, and without a component's version, the files of another project
   trigger job       ``trigger <job>``, the job's name
   image             ``image``, the image as written
   service container ``service``, the image as written
   ================= ==============================================================================================

   A local file that isn't a well-formed configuration is a warning of type ``glci.pipeline``, and its item has no
   nested list.


.. _GLCI/YAML:

YAML Excerpts
*************

.. grid:: 2

   .. grid-item::
      :columns: 6

      ``glci:yaml`` renders the current pipeline file, or a part of it, as a YAML code block. The lines are numbered as
      in the file, and the part is shifted left by the indentation of its first line.

      The caption names the file and the lines. When :confval:`glci_project`, :confval:`glci_ref` and
      :confval:`glci_repository_root` are configured, it links to these lines on GitLab:
      ``https://gitlab.com/<project>/-/blob/<ref>/<file>#L<first>-<last>``.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         .. glci:yaml::
            :section: inputs

         .. glci:yaml::
            :job: Build

.. rst:directive:: .. glci:yaml::

   .. rst:directive:option:: section: inputs | variables | stages | include | workflow | default

      The ``inputs`` of the header's ``spec``, or a top-level key of the configuration.

   .. rst:directive:option:: job: <name>

      One job or hidden job. Excludes ``:section:``. Without either option, the whole file is shown.

   .. rst:directive:option:: caption: <text>

      A caption replacing the file name and the lines.

   .. rst:directive:option:: name: <label>

      A label to reference the code block by.

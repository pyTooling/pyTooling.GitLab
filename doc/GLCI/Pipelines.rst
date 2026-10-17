.. _GLCI/Pipeline:

Pipelines and Parameters
########################

.. _GLCI/Pipeline/Directive:

Pipelines
*********

.. rst:directive:: .. glci:pipeline:: <name>

   Registers the pipeline ``<name>`` with an index entry, and makes it the **current pipeline** of the document: every
   ``glci:input`` and ``glci:variable`` following it belongs to it, and a role may name its parameters without the
   pipeline's name.

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


.. _GLCI/Parameters:

Inputs and Variables
********************

.. grid:: 2

   .. grid-item::
      :columns: 6

      Each of the two directives documents one parameter of the current pipeline, as a **section** titled by the
      parameter's name - so it is listed in the page's table of contents - holding a field list:

      #. the fields read from the pipeline file: *Type*, *Required* and *Default Value* for an input, where ``— — — —``
         says there is no default and a multi-line default is shown as a block, and its *Possible Values* and *Pattern*
         if it states ``options`` or ``regex``; *Type* - ``string`` - and *Default Value* for a variable, and its
         *Possible Values* if it states ``options``;
      #. the fields of the directive's content, in the order written, as *Possible Values*, *Description* or *Example*;
      #. without a hand-written *Description*, the ``description`` of the pipeline file, placed behind *Type*,
         *Required*, *Default Value*, *Possible Values* and *Pattern*.

      Content after the field list follows it.

   .. grid-item::
      :columns: 6

      .. code-block:: ReST

         Inputs
         ******

         .. glci:input:: package_name

            :Possible Values: Any valid Python package name.
            :Example:         ``myPackage``

         Variables
         *********

         .. glci:variable:: DEPLOY_ENV

.. rst:directive:: .. glci:input:: <name>

   Documents the input ``<name>`` of the current pipeline file's ``spec:inputs``. Its target is ``<Pipeline>.<name>``.

.. rst:directive:: .. glci:variable:: <name>

   Documents the default variable ``<name>`` of the current pipeline file's top-level ``variables``. A variable with a
   ``description`` is prefilled in the form running a pipeline by hand. Its target is ``<Pipeline>.<name>``.

.. rst:directive:: .. glci:autoinputs::

   Documents every input of the current pipeline file the document has no ``glci:input`` for - also those whose
   ``glci:input`` follows later in the document. An entry is what a ``glci:input`` without content creates: the facts
   of the pipeline file and its ``description``.

   .. code-block:: ReST

      Inputs
      ******

      .. glci:input:: package_name

         :Possible Values: Any valid Python package name.

      .. glci:autoinputs::


.. _GLCI/Roles:

Roles
*****

.. rst:role:: glci:pipeline
.. rst:role:: glci:input
.. rst:role:: glci:variable

   Refer to a pipeline by its name, and to a parameter as ``<Pipeline>.<name>`` - after a ``glci:pipeline``, the name
   alone refers to that pipeline's parameter. A leading ``~`` shows only the name:

   .. code-block:: ReST

      :glci:input:`package_name`            in the page of pipeline 'Package'
      :glci:input:`Package.package_name`    from anywhere
      :glci:input:`~Package.package_name`   shown as 'package_name'
      :glci:pipeline:`Package`

   A target that isn't documented is a warning.

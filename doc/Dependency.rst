.. _DEP:

Dependencies
############

.. _DEP/package:

pyTooling.GitLab Package (Mandatory)
************************************

.. rubric:: Manually Installing Package Requirements

Use the :file:`requirements.txt` file to install all dependencies via ``pip3`` or install the package directly from
PyPI (see :ref:`INSTALL`).

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         pip3 install -U -r requirements.txt

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         pip install -U -r requirements.txt

.. rubric:: Dependency List

.. dependency-table:: package
   :caption: Mandatory dependencies of the pyTooling.GitLab package.


.. _DEP/diagram:

Gantt Charts (Optional)
***********************

When installed as ``pyTooling.GitLab[diagram]``, which the :ref:`trace diagram <VIS/PipelineTrace>` and the program's
``--gantt`` option need:

.. The extra isn't on PyPI yet, which 'dependency-table' reads extras from. Replace this table by
   '.. dependency-table:: diagram' and an entry in 'conf.py' once a release contains the extra.

+-------------+---------+------------------------------+----------------------------------------------------------+
| Package     | Version | License                      | Dependencies                                             |
+=============+=========+==============================+==========================================================+
| matplotlib  | ≥3.10   | PSF-2.0 (matplotlib license) | contourpy, cycler, fonttools, kiwisolver, numpy,         |
|             |         |                              | packaging, pillow, pyparsing, python-dateutil            |
+-------------+---------+------------------------------+----------------------------------------------------------+


.. _DEP/sphinx:

Sphinx Domain ``glci`` (Optional)
*********************************

When installed as ``pyTooling.GitLab[sphinx]``, which the :ref:`glci domain <GLCI>` needs. pyTooling.Sphinx requires
Python 3.12 or newer, because Sphinx 9.1 does.

.. The extra isn't on PyPI yet, which 'dependency-table' reads extras from. Replace this table by
   '.. dependency-table:: sphinx' and an entry in 'conf.py' once a release contains the extra.

+------------------+---------+------------------------------+-----------------------------------------------------+
| Package          | Version | License                      | Dependencies                                        |
+==================+=========+==============================+=====================================================+
| pyTooling.Sphinx | ``dev`` | Apache-2.0                   | pyTooling[pypi], sphinx, xmlschema                  |
+------------------+---------+------------------------------+-----------------------------------------------------+


.. _DEP/testing:

Unit Testing / Coverage (Optional)
**********************************

Additional Python packages needed for testing and code coverage collection. These packages are only needed for
developers or on a CI server.

.. rubric:: Manually Installing Test Requirements

Use the :file:`tests/unit/requirements.txt` file to install all dependencies via ``pip3``. The file will recursively
install the mandatory dependencies too.

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         pip3 install -U -r tests/unit/requirements.txt

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         pip install -U -r tests\unit\requirements.txt

.. rubric:: Dependency List

.. dependency-table:: unittest
   :caption: Dependencies for unit testing and code coverage.


.. _DEP/documentation:

Sphinx Documentation (Optional)
*******************************

Additional Python packages needed for building the documentation. These packages are only needed for developers or on
a CI server.

.. rubric:: Manually Installing Documentation Requirements

Use the :file:`doc/requirements.txt` file to install all dependencies via ``pip3``. The file will recursively install
the mandatory dependencies too.

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         pip3 install -U -r doc/requirements.txt

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         pip install -U -r doc\requirements.txt

.. rubric:: Dependency List

.. dependency-table:: documentation
   :caption: Dependencies for building the documentation.

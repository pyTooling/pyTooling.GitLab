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

.. dependency-table:: diagram
   :caption: Dependencies added by the ``diagram`` extra.


.. _DEP/sphinx:

Sphinx Domain ``glci`` (Optional)
*********************************

When installed as ``pyTooling.GitLab[sphinx]``, which the :ref:`glci domain <GLCI>` needs. pyTooling.Sphinx requires
Python 3.12 or newer, because Sphinx 9.1 does.

.. dependency-table:: sphinx
   :caption: Dependencies added by the ``sphinx`` extra.


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

.. rubric:: Test Data

The pipeline run model's tests use pipelines of public projects on gitlab.com, as GitLab's REST API reported them,
reduced to the fields GitLab reports about the pipelines and jobs. They are in the repository only, not in the package;
:ghsrc:`NOTICE.md <NOTICE.md>` lists them too.

.. list-table::
   :header-rows: 1
   :widths: 25 30 25 20

   * - Content
     - Files
     - Source
     - License of the source project
   * - Pipeline 2954836704 with its jobs, its trigger job and its child pipeline
     - :file:`tests/data/Runs/GitLabDevelopmentKit.json`
     - `gitlab-org/gitlab-development-kit <https://gitlab.com/gitlab-org/gitlab-development-kit>`__
     - MIT
   * - Pipeline 2958343473 with its jobs and its trigger jobs
     - :file:`tests/data/Runs/GitLabRunner.json`
     - `gitlab-org/gitlab-runner <https://gitlab.com/gitlab-org/gitlab-runner>`__
     - MIT


.. _DEP/apptesting:

Application Testing (Optional)
******************************

Additional Python packages needed for testing the program :program:`pytooling-gitlab` as installed. These packages
are only needed for developers or on a CI server.

.. rubric:: Manually Installing Application Test Requirements

Use the :file:`tests/app/requirements.txt` file to install all dependencies via ``pip3``. The file will recursively
install the mandatory dependencies too.

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         pip3 install -U -r tests/app/requirements.txt

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         pip install -U -r tests\app\requirements.txt

.. rubric:: Dependency List

.. dependency-table:: apptest
   :caption: Dependencies for application testing.


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


.. _DEP/packaging:

Packaging (Optional)
********************

Additional Python packages needed for installation package generation. These packages are only needed for developers or
on a CI server.

.. rubric:: Building an Installation Package

:file:`pyproject.toml` lists them as build requirements (``[build-system]``), so ``build`` installs them into an
isolated build environment itself.

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         python3 -m build --wheel

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         python -m build --wheel

.. rubric:: Dependency List

.. dependency-table:: packaging
   :caption: Dependencies for generating an installation package.


.. _DEP/publishing:

Publishing (CI-Server only)
***************************

Additional Python packages needed for publishing the generated installation package to e.g, PyPI or any equivalent
services. These packages are only needed for maintainers or on a CI server.

.. rubric:: Manually Installing Publishing Requirements

Use the :file:`dist/requirements.txt` file to install all dependencies via ``pip3``. The file will recursively
install the mandatory dependencies too.

.. tab-set::

   .. tab-item:: Linux/macOS
      :sync: Linux

      .. code-block:: bash

         pip3 install -U -r dist/requirements.txt

   .. tab-item:: Windows
      :sync: Windows

      .. code-block:: powershell

         pip install -U -r dist\requirements.txt

.. rubric:: Dependency List

.. dependency-table:: publishing
   :caption: Dependencies for publishing the package.

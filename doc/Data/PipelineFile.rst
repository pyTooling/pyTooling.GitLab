.. _DATA/PipelineFile:

Pipeline File
#############

:mod:`pyTooling.GitLab.PipelineFile` models a **GitLab CI/CD configuration file** - the project's
:file:`.gitlab-ci.yml`, a file it includes, or the file of a child pipeline -, not a run of it (that's
:ref:`DATA/PipelineRun`):

.. code-block:: python

   from pathlib import Path
   from pyTooling.GitLab.PipelineFile import PipelineFile

   pipelineFile = PipelineFile.FromFile(Path(".gitlab-ci.yml"))

   print(f"{pipelineFile.Path.name}: stages {', '.join(pipelineFile.Stages)}")
   for variable in pipelineFile.Variables.values():
     print(f"  {variable.Name:<24} {variable.Value}")

The file is read with ``ruamel.yaml``, a requirement of this package.


.. _DATA/PipelineFile/Tree:

The Tree
********

.. tree::

   - :class:`~pyTooling.GitLab.PipelineFile.PipelineFile` | a configuration file
     - :class:`~pyTooling.GitLab.PipelineFile.Variable`   | a default variable, declared in the top-level ``variables``

Every element knows its :attr:`~pyTooling.GitLab.PipelineFile.Base.Parent`, and holds a reference to the configuration
file it belongs to in :attr:`~pyTooling.GitLab.PipelineFile.Base.PipelineFile`.

A file may begin with a **header document**, separated from the configuration by ``---``, which holds the ``spec``
key. :meth:`~pyTooling.GitLab.PipelineFile.PipelineFile.FromFile` accepts it and reads the configuration below it.


.. _DATA/PipelineFile/Stages:

Stages
******

:attr:`~pyTooling.GitLab.PipelineFile.PipelineFile.DeclaredStages` holds the ``stages`` key as written, or ``None``.
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFile.Stages` holds the stages the pipeline runs, in their order: the
declared ones, or ``build``, ``test`` and ``deploy`` (:data:`~pyTooling.GitLab.PipelineFile.DEFAULT_STAGES`) for a
file without ``stages``, always between ``.pre`` and ``.post``:

.. code-block:: yaml

   stages:              # Stages: .pre, lint, build, .post
     - lint
     - build


.. _DATA/PipelineFile/Variables:

Variables
*********

A variable of the top-level ``variables`` is a :class:`~pyTooling.GitLab.PipelineFile.Variable`. Its
:attr:`~pyTooling.GitLab.PipelineFile.Variable.Value` is the text GitLab reads - a number or a boolean written in the
file is its text, as ``3.14`` or ``true``. A variable declared as mapping may also carry:

* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Description` - GitLab prefills the variable in the form running a
  pipeline by hand, with the description beside it;
* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Options` - the values that form offers to select from;
* :attr:`~pyTooling.GitLab.PipelineFile.Variable.Expand` - ``False``, if variables in the value aren't expanded.

.. code-block:: yaml

   variables:
     DEPLOY_ENVIRONMENT:
       value: "staging"
       description: "The deployment target."
       options: ["production", "staging"]


.. _DATA/PipelineFile/Lines:

Source Lines
************

Every element keeps the :attr:`~pyTooling.GitLab.PipelineFile.Base.Line` it is written at, starting at 1, so a
consumer can point at the place a finding comes from. A malformed file raises
:exc:`~pyTooling.GitLab.PipelineFile.PipelineFileError`, which carries the file in
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFileError.Path` and the line in
:attr:`~pyTooling.GitLab.PipelineFile.PipelineFileError.Line`, and names both in a note:

.. code-block:: text

   pyTooling.GitLab.PipelineFile.PipelineFileError: Variable 'A' has unknown key 'secret'.
     In '.gitlab-ci.yml:4'.

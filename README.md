[![Sourcecode on GitHub](https://img.shields.io/badge/pyTooling-GitLab-63bf7f?longCache=true&style=flat-square&longCache=true&logo=GitHub)](https://GitHub.com/pyTooling/pyTooling.GitLab)
[![Sourcecode License](https://img.shields.io/pypi/l/pyTooling.GitLab?longCache=true&style=flat-square&logo=Apache&label=code)](LICENSE.md)
[![Documentation](https://img.shields.io/website?longCache=true&style=flat-square&label=pyTooling.github.io%2FpyTooling.GitLab&logo=GitHub&logoColor=fff&up_color=blueviolet&up_message=Read%20now%20%E2%9E%9A&url=https%3A%2F%2FpyTooling.github.io%2FpyTooling.GitLab%2Findex.html)](https://pyTooling.github.io/pyTooling.GitLab/)
[![Documentation License](https://img.shields.io/badge/doc-CC--BY%204.0-green?longCache=true&style=flat-square&logo=CreativeCommons&logoColor=fff)](doc/Doc-License.rst)  
[![PyPI](https://img.shields.io/pypi/v/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)](https://pypi.org/project/pyTooling.GitLab/)
![PyPI - Status](https://img.shields.io/pypi/status/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)  
[![GitHub Workflow - Build and Test Status](https://img.shields.io/github/actions/workflow/status/pyTooling/pyTooling.GitLab/Pipeline.yml?branch=main&longCache=true&style=flat-square&label=build%20and%20test&logo=GitHub%20Actions&logoColor=FFFFFF)](https://GitHub.com/pyTooling/pyTooling.GitLab/actions/workflows/Pipeline.yml)
[![Libraries.io status for latest release](https://img.shields.io/librariesio/release/pypi/pyTooling.GitLab?longCache=true&style=flat-square&logo=Libraries.io&logoColor=fff)](https://libraries.io/github/pyTooling/pyTooling.GitLab)
[![Codacy - Quality](https://img.shields.io/codacy/grade/dae89de7264d479daf8d6197c8ed2186?longCache=true&style=flat-square&logo=Codacy)](https://app.codacy.com/gh/pyTooling/pyTooling.GitLab/dashboard)
[![Codacy - Coverage](https://img.shields.io/codacy/coverage/dae89de7264d479daf8d6197c8ed2186?longCache=true&style=flat-square&logo=Codacy)](https://app.codacy.com/gh/pyTooling/pyTooling.GitLab/dashboard)
[![Codecov - Branch Coverage](https://img.shields.io/codecov/c/github/pyTooling/pyTooling.GitLab?longCache=true&style=flat-square&logo=Codecov)](https://codecov.io/gh/pyTooling/pyTooling.GitLab)

# pyTooling.GitLab

**pyTooling.GitLab** works with GitLab CI/CD pipelines: it reads pipeline files (`.gitlab-ci.yml`) into a data model,
reads the runs of a pipeline from GitLab's REST API, and converts them into traces - e.g. OpenTelemetry's OTLP/JSON or
a Gantt chart of the jobs. A Sphinx domain `glci` documents a pipeline file's inputs and variables taken straight from
the file.

It builds on [pyTooling](https://GitHub.com/pyTooling/pyTooling)'s generic CI pipeline model and tracing, and on
[pyTooling.Sphinx](https://GitHub.com/pyTooling/pyTooling.Sphinx) for its documentation extensions. Its sibling
[pyTooling.GitHub](https://GitHub.com/pyTooling/pyTooling.GitHub) does the same for GitHub Actions.


> [!IMPORTANT]
> The Sphinx domain `glci` in `pyTooling.GitLab.Sphinx` requires [pyTooling.Sphinx][pyTooling.Sphinx], and thus
> **Python 3.12 or newer**, because Sphinx 9.1 requires Python 3.12.

The package is installed from PyPI:

```bash
pip install pyTooling.GitLab
```


## Features

🚧 The features are in development.

### Data models

* 🚧 [Pipeline runs][PipelineRun] - A GitLab pipeline - its jobs, matrices and child pipelines with their times and
  outcomes - read from the GitLab REST API's payloads.
* 🚧 [Pipeline files][PipelineFile] - A `.gitlab-ci.yml` and the files it includes: stages, jobs with their needs and
  rules, variables and inputs, read with line numbers, and converted into a pipeline graph.

### Sphinx domain `glci`

The domain needs the extra `sphinx`, which installs pyTooling.Sphinx:

```bash
pip install pyTooling.GitLab[sphinx]
```

* 🚧 [Pipelines and their parameters][GLCIPipelines] - A pipeline file's `spec:inputs` and its described variables,
  taken straight from the file; roles to reference them.
* 🚧 [Summaries][GLCISummaries] - Parameter tables, the interface, the dependencies and YAML excerpts of a pipeline
  file.

### Visualization

* 🚧 [Pipeline graph][PipelineGraph] - The jobs of a pipeline file, their stages and `needs` as a Graphviz graph.
* 🚧 [Pipeline trace diagram][PipelineTrace] - Reads a pipeline through the GitLab REST API into a trace, written as
  OpenTelemetry's OTLP/JSON or drawn as a Gantt chart.

### Program

Gantt charts need the extra `diagram`, which installs matplotlib:

```bash
pip install pyTooling.GitLab[diagram]
```

* 🚧 [pytooling-gitlab][CLI] - The command `pipeline` reads a pipeline into a trace, writes it, and draws it as a
  Gantt chart.

[PipelineRun]: https://pyTooling.github.io/pyTooling.GitLab/Data/PipelineRun.html
[PipelineFile]: https://pyTooling.github.io/pyTooling.GitLab/Data/PipelineFile.html
[GLCIPipelines]: https://pyTooling.github.io/pyTooling.GitLab/GLCI/Pipelines.html
[GLCISummaries]: https://pyTooling.github.io/pyTooling.GitLab/GLCI/Summaries.html
[PipelineGraph]: https://pyTooling.github.io/pyTooling.GitLab/Visualization/PipelineGraph.html
[PipelineTrace]: https://pyTooling.github.io/pyTooling.GitLab/Visualization/PipelineTrace.html
[CLI]: https://pyTooling.github.io/pyTooling.GitLab/CLI.html
[pyTooling.Sphinx]: https://pyTooling.github.io/pyTooling.Sphinx/


## Contributors

* [Patrick Lehmann](https://GitHub.com/Paebbels) (Maintainer)
* [and more...](https://GitHub.com/pyTooling/pyTooling.GitLab/graphs/contributors)


## License

This Python package (source code) is licensed under [Apache License 2.0](LICENSE.md).  
The accompanying documentation is licensed under [Creative Commons - Attribution 4.0 (CC-BY 4.0)](doc/Doc-License.rst).


-------------------------

SPDX-License-Identifier: Apache-2.0

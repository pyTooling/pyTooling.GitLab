[![Sourcecode on GitHub](https://img.shields.io/badge/pyTooling-GitLab-63bf7f?longCache=true&style=flat-square&longCache=true&logo=GitHub)](https://GitHub.com/pyTooling/pyTooling.GitLab)
[![Sourcecode License](https://img.shields.io/pypi/l/pyTooling.GitLab?longCache=true&style=flat-square&logo=Apache&label=code)](LICENSE.md)
[![Documentation](https://img.shields.io/website?longCache=true&style=flat-square&label=pyTooling.github.io%2FpyTooling.GitLab&logo=GitHub&logoColor=fff&up_color=blueviolet&up_message=Read%20now%20%E2%9E%9A&url=https%3A%2F%2FpyTooling.github.io%2FpyTooling.GitLab%2Findex.html)](https://pyTooling.github.io/pyTooling.GitLab/)
[![Documentation License](https://img.shields.io/badge/doc-CC--BY%204.0-green?longCache=true&style=flat-square&logo=CreativeCommons&logoColor=fff)](doc/Doc-License.rst)  
[![PyPI](https://img.shields.io/pypi/v/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)](https://pypi.org/project/pyTooling.GitLab/)
![PyPI - Status](https://img.shields.io/pypi/status/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyTooling.GitLab?longCache=true&style=flat-square&logo=PyPI&logoColor=FBE072)  
[![GitHub Workflow - Build and Test Status](https://img.shields.io/github/actions/workflow/status/pyTooling/pyTooling.GitLab/Pipeline.yml?branch=main&longCache=true&style=flat-square&label=build%20and%20test&logo=GitHub%20Actions&logoColor=FFFFFF)](https://GitHub.com/pyTooling/pyTooling.GitLab/actions/workflows/Pipeline.yml)
[![Libraries.io status for latest release](https://img.shields.io/librariesio/release/pypi/pyTooling.GitLab?longCache=true&style=flat-square&logo=Libraries.io&logoColor=fff)](https://libraries.io/github/pyTooling/pyTooling.GitLab)
[![Codecov - Branch Coverage](https://img.shields.io/codecov/c/github/pyTooling/pyTooling.GitLab?longCache=true&style=flat-square&logo=Codecov)](https://codecov.io/gh/pyTooling/pyTooling.GitLab)

# pyTooling.GitLab

**pyTooling.GitLab** works with GitLab CI/CD pipelines: it reads pipeline configuration files (`.gitlab-ci.yml`)
into a data model, reads the runs of a pipeline from GitLab's REST API, and converts them into traces - e.g.
OpenTelemetry's OTLP/JSON or a Gantt chart of the jobs.

It builds on [pyTooling](https://GitHub.com/pyTooling/pyTooling)'s generic CI pipeline model and tracing, and on
[pyTooling.Sphinx](https://GitHub.com/pyTooling/pyTooling.Sphinx) for its documentation extensions.


## Contributors

* [Patrick Lehmann](https://GitHub.com/Paebbels) (Maintainer)
* [and more...](https://GitHub.com/pyTooling/pyTooling.GitLab/graphs/contributors)


## License

This Python package (source code) is licensed under [Apache License 2.0](LICENSE.md).  
The accompanying documentation is licensed under [Creative Commons - Attribution 4.0 (CC-BY 4.0)](doc/Doc-License.rst).


-------------------------

SPDX-License-Identifier: Apache-2.0

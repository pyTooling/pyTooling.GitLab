# Notices

pyTooling.GitLab is licensed under the [Apache License 2.0](LICENSE.md), its documentation under
[Creative Commons - Attribution 4.0 (CC-BY 4.0)](doc/Doc-License.rst). It contains content of other projects, listed
here with their licenses.


## Test data

Pipelines of public projects on gitlab.com, as GitLab's REST API reported them, as test fixtures of the pipeline run
model. The payloads are reduced to the fields GitLab reports about the pipelines and jobs; nested objects the model
doesn't read - the commit, the user, the project, the artifacts - are removed. They are in the repository only, not in
the package.

| Content | File | Source | License of the source project |
|---------|------|--------|-------------------------------|
| Pipeline 2954836704 with its jobs, its trigger job and its child pipeline 2954935189 | [`tests/data/Runs/GitLabDevelopmentKit.json`](tests/data/Runs/GitLabDevelopmentKit.json) | [gitlab-org/gitlab-development-kit](https://gitlab.com/gitlab-org/gitlab-development-kit/-/pipelines/2954836704) | MIT |
| Pipeline 2958343473 with its jobs and its trigger jobs | [`tests/data/Runs/GitLabRunner.json`](tests/data/Runs/GitLabRunner.json) | [gitlab-org/gitlab-runner](https://gitlab.com/gitlab-org/gitlab-runner/-/pipelines/2958343473) | MIT |

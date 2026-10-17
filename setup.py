# ==================================================================================================================== #
#             _____           _ _               ____ _ _   _          _                                                #
#  _ __  _   |_   _|__   ___ | (_)_ __   __ _  / ___(_) |_| |    __ _| |__                                             #
# | '_ \| | | || |/ _ \ / _ \| | | '_ \ / _` || |  _| | __| |   / _` | '_ \                                            #
# | |_) | |_| || | (_) | (_) | | | | | | (_| || |_| | | |_| |__| (_| | |_) |                                           #
# | .__/ \__, ||_|\___/ \___/|_|_|_| |_|\__, (_)____|_|\__|_____\__,_|_.__/                                            #
# |_|    |___/                          |___/                                                                          #
# ==================================================================================================================== #
# Authors:                                                                                                             #
#   Patrick Lehmann                                                                                                    #
#                                                                                                                      #
# License:                                                                                                             #
# ==================================================================================================================== #
# Copyright 2026-2026 Patrick Lehmann - Bötzingen, Germany                                                             #
#                                                                                                                      #
# Licensed under the Apache License, Version 2.0 (the "License");                                                      #
# you may not use this file except in compliance with the License.                                                     #
# You may obtain a copy of the License at                                                                              #
#                                                                                                                      #
#   http://www.apache.org/licenses/LICENSE-2.0                                                                         #
#                                                                                                                      #
# Unless required by applicable law or agreed to in writing, software                                                  #
# distributed under the License is distributed on an "AS IS" BASIS,                                                    #
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.                                             #
# See the License for the specific language governing permissions and                                                  #
# limitations under the License.                                                                                       #
#                                                                                                                      #
# SPDX-License-Identifier: Apache-2.0                                                                                  #
# ==================================================================================================================== #
#
"""
Package installer for 'Working with GitLab pipelines - pipeline configuration files, convert pipeline runs to (OTLP)
traces'.
"""
from setuptools          import setup

from pathlib             import Path
from pyTooling.Packaging import DescribePythonPackageHostedOnGitHub
from pyTooling.Warning   import WarningCollector

gitHubNamespace =        "pyTooling"
packageName =            "pyTooling.GitLab"
packageDirectory =       packageName.replace(".", "/")
packageInformationFile = Path(f"{packageDirectory}/__init__.py")

with WarningCollector() as warnings:
	setup(
		**DescribePythonPackageHostedOnGitHub(
			packageName=packageName,
			description="Working with GitLab pipelines - pipeline configuration files, convert pipeline runs to (OTLP) "
			            "traces.",
			gitHubNamespace=gitHubNamespace,
			unittestRequirementsFile=Path("tests/requirements.txt"),
			sourceFileWithVersion=packageInformationFile,
			developmentStatus="pre-alpha",
			pythonVersions=("3.11", "3.12", "3.13", "3.14", "3.15"),
			additionalRequirements={
				"diagram": ["matplotlib >= 3.10"],
				"sphinx":  ["pyTooling.Sphinx ~= 0.1.0rc3"],
			},
			dataFiles={
				packageName: ["py.typed"]
			},
			debug=True
		)
	)

for warning in warnings:
	print(f"[setup.py] WARNING: {warning}")

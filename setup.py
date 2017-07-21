"""
Copyright 2016 Google Inc. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Setup script for validator that checks for election common data best
practices.
"""
import sys
from setuptools import setup, find_packages

# if the version of python installed is less than 2.7.9
# install pyopenssl. Fixes issue #31
if (sys.version_info[0] == 2 and sys.version_info[1] <= 7):
    requests_version = 'requests[security]'
    if (sys.version_info[1] == 7 and sys.version_info[2] >=  9):
        requests_version = 'requests'
else:
    requests_version = 'requests'

ENTRY_POINTS = {
    'console_scripts': [
        'election_results_xml_validator = election_results_xml_validator.rules:main',
    ],
}

setup(
    name='election_results_xml_validator',
    version='0.2.7',
    author='Miano Njoka',
    author_email='election-results-xml-validator@google.com',
    maintainer='Google gTech Partners',
    maintainer_email='election-results-xml-validator@google.com',
    license='Apache License',
    description='Checks that an elections file follows best practices',
    long_description='election_results_xml_validator is a script that checks '
        'if a election data feed follows best practices and outputs errors, '
        'warnings and info messages for common issues.',
    url='https://github.com/google/election_results_xml_validator',
    install_requires=[
        'lxml>=3.3.4',
        'language-tags>=0.4.2',
        '%s>=2.10' % requests_version,
        'pygithub>=1.28'
    ],
    entry_points=ENTRY_POINTS,
    package_dir={'election_results_xml_validator': ''},
    packages=['election_results_xml_validator'],
)

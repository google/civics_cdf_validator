# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Validation rules for the CDF XML validator."""

from __future__ import print_function

import enum

from civics_cdf_validator.rulesets import committee_rules
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import election_dates_rules
from civics_cdf_validator.rulesets import election_rules
from civics_cdf_validator.rulesets import metadata_rules
from civics_cdf_validator.rulesets import officeholder_rules
from civics_cdf_validator.rulesets import voter_information_rules


class RuleSet(enum.Enum):
  """Names for sets of rules used to validate a particular feed type."""

  ELECTION = 1
  OFFICEHOLDER = 2
  COMMITTEE = 3
  ELECTION_DATES = 4
  ELECTION_RESULTS = 5
  METADATA = 6
  VOTER_INFORMATION = 7


# To add new rules, create a new class in the matching file under rulesets/,
# inherit the base rule, and add it to that file's rule list.
COMMON_RULES = common_rules.COMMON_RULES
ELECTION_RULES = election_rules.ELECTION_RULES
OFFICEHOLDER_RULES = officeholder_rules.OFFICEHOLDER_RULES
COMMITTEE_RULES = committee_rules.COMMITTEE_RULES
ELECTION_DATES_RULES = election_dates_rules.ELECTION_DATES_RULES
METADATA_RULES = metadata_rules.METADATA_RULES
VOTER_INFORMATION_RULES = voter_information_rules.VOTER_INFORMATION_RULES

ALL_RULES = frozenset(
    COMMON_RULES
    + ELECTION_RULES
    + OFFICEHOLDER_RULES
    + COMMITTEE_RULES
    + ELECTION_DATES_RULES
    + VOTER_INFORMATION_RULES
    + METADATA_RULES
)

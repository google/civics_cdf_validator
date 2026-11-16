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
"""Validation rules for election dates feeds of the CDF XML validator."""

from __future__ import print_function

from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import election_rules


class UnreferencedEntitiesElectionDates(common_rules.UnreferencedEntitiesBase):
  """CDF elections and contests are top-level in election dates feeds.

  All other entity types must be referenced.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(UnreferencedEntitiesElectionDates, self).__init__(
        election_tree,
        schema_tree,
        frozenset(["Election", "Contest"]),
        frozenset([]),
        **kwargs,
    )


ELECTION_DATES_RULES = election_rules.ELECTION_RULES + (
    UnreferencedEntitiesElectionDates,
)

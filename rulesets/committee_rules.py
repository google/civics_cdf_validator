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
"""Validation rules for committee feeds of the CDF XML validator."""

from __future__ import print_function

import re

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import rule_util
from lxml import etree


class CommitteeClassificationEndDateOccursAfterStartDate(base.DateRule):
  """CommitteeClassification elements should have end dates that occur after the start dates."""

  def elements(self) -> list[str]:
    return ["CommitteeClassification"]

  def check(self, element: etree._Element) -> None:
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class AffiliationEndDateOccursAfterStartDate(base.DateRule):
  """Affiliation elements should have end dates that occur after the start dates."""

  def elements(self) -> list[str]:
    return ["Affiliation"]

  def check(self, element: etree._Element) -> None:
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class EinMatchesFormat(base.BaseRule):
  """EIN id should be in the following format: XX-XXXXXXX."""

  def __init__(self, *args, **kwargs) -> None:
    super(EinMatchesFormat, self).__init__(*args, **kwargs)
    regex = r"\d{2}(-\d{7})?"
    self.ein_id_matcher = re.compile(regex, flags=re.U)

  def elements(self) -> list[str]:
    return ["Committee"]

  def check(self, element: etree._Element) -> None:
    external_identifiers = element.find("ExternalIdentifiers")
    if external_identifiers is not None:
      ein_ids = rule_util.get_external_id_values(external_identifiers, "ein")
      if ein_ids:
        e_id = ein_ids.pop()
        if not self.ein_id_matcher.match(e_id):
          raise loggers.ElectionError.from_message(
              f"EIN id '{e_id}' is not in the correct format.",
              [element],
          )


COMMITTEE_RULES = common_rules.COMMON_RULES + (
    # go/keep-sorted start
    AffiliationEndDateOccursAfterStartDate,
    CommitteeClassificationEndDateOccursAfterStartDate,
    EinMatchesFormat,
    common_rules.ProhibitElectionData,
    # go/keep-sorted end
)

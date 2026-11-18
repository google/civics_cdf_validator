# Copyright 2026 Google LLC
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
"""Validation rules for election results feeds of the CDF XML validator."""

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import election_rules
from lxml import etree

_REQUIRED_CONTEST_RESULTS_FIELDS = (
    "CurrentResultsReportingStage",
    "ResultsReportingStageCollection",
)

_SUB_UNITS_FIELD_NAMES = ("SubUnitsReported", "TotalSubUnits")


class RequiredContestResultsFieldsSet(base.SchemaRule):
  """Checks that every Contest sets its results reporting stage fields.

  Election results feeds must set CurrentResultsReportingStage and
  ResultsReportingStageCollection on every Contest.
  """

  def elements(self) -> list[str]:
    return ["Contest"] + list(self.get_all_subtypes("Contest"))

  def check(self, element: etree._Element) -> None:
    missing_fields = [
        field
        for field in _REQUIRED_CONTEST_RESULTS_FIELDS
        if element.find(field) is None
    ]
    if missing_fields:
      raise loggers.ElectionError.from_message(
          f"Contest {element.get('objectId')} is missing required field(s)"
          f" {', '.join(missing_fields)}. Election results feeds must set"
          f" {', '.join(_REQUIRED_CONTEST_RESULTS_FIELDS)} on every Contest.",
          [element],
      )


class DataSourcesRequired(base.BaseRule):
  """Checks that the ElectionReport sets a DataSourceCollection.

  Election results feeds must set a DataSourceCollection on the ElectionReport
  so that their results can be attributed to their data sources.
  """

  def elements(self) -> list[str]:
    return ["ElectionReport"]

  def check(self, element: etree._Element) -> None:
    if element.find("DataSourceCollection") is None:
      raise loggers.ElectionError.from_message(
          "ElectionReport is missing required field DataSourceCollection."
          " Election results feeds must set DataSourceCollection on the"
          " ElectionReport.",
          [element],
      )


class ValidatePercentReporting(base.SchemaRule):
  """Checks that every Contest sets the fields used for its percent reporting.

  Election results feeds must set either EstimatedExpectedVotePercentage or
  both SubUnitsReported and TotalSubUnits on every Contest.
  """

  def elements(self) -> list[str]:
    return ["Contest"] + list(self.get_all_subtypes("Contest"))

  def check(self, element: etree._Element) -> None:
    if element.find("EstimatedExpectedVotePercentage") is not None:
      return
    missing_sub_units_fields = [
        field for field in _SUB_UNITS_FIELD_NAMES if element.find(field) is None
    ]
    if missing_sub_units_fields:
      raise loggers.ElectionError.from_message(
          f"Contest {element.get('objectId')} is missing field(s)"
          " EstimatedExpectedVotePercentage,"
          f" {', '.join(missing_sub_units_fields)}."
          " Election results feeds must set either"
          " EstimatedExpectedVotePercentage or both SubUnitsReported and"
          " TotalSubUnits on every Contest.",
          [element],
      )


ELECTION_RESULTS_RULES = election_rules.ELECTION_RULES + (
    # go/keep-sorted start
    DataSourcesRequired,
    RequiredContestResultsFieldsSet,
    ValidatePercentReporting,
    # go/keep-sorted end
)

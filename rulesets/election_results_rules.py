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
from civics_cdf_validator.rulesets import rule_util
from lxml import etree

_REQUIRED_CONTEST_RESULTS_FIELDS = (
    "CurrentResultsReportingStage",
    "ResultsExpected",
    "ResultsReportingStageCollection",
)

_SUB_UNITS_FIELD_NAMES = ("SubUnitsReported", "TotalSubUnits")

_VOTE_TOTAL_TYPES = ("total", "total-percent")


def _get_vote_count_types(selection: etree._Element) -> set[str]:
  """Returns the types of the VoteCounts in a ballot selection."""
  return {
      rule_util.get_type_or_other_type(vote_counts)
      for vote_counts in selection.findall("VoteCountsCollection/VoteCounts")
  }


class RequiredContestResultsFieldsSet(base.SchemaRule):
  """Checks that every Contest sets its required results fields.

  Election results feeds must set CurrentResultsReportingStage, ResultsExpected,
  and ResultsReportingStageCollection on every Contest.
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


class CandidateAndBallotMeasureSelectionTotalsRequired(base.SchemaRule):
  """Checks that candidate and ballot measure selections report vote totals.

  Election results feeds must report total and total-percent VoteCounts for
  every CandidateSelection and BallotMeasureSelection, and for the
  AggregateBallotSelection of every CandidateContest and BallotMeasureContest.
  """

  def setup(self) -> None:
    self.aggregate_contest_types = {
        "BallotMeasureContest",
        "CandidateContest",
        *self.get_all_subtypes("BallotMeasureContest"),
        *self.get_all_subtypes("CandidateContest"),
    }

  def elements(self) -> list[str]:
    return [
        "AggregateBallotSelection",
        "BallotMeasureSelection",
        "CandidateSelection",
        *self.get_all_subtypes("BallotMeasureSelection"),
        *self.get_all_subtypes("CandidateSelection"),
    ]

  def check(self, element: etree._Element) -> None:
    element_class = self.get_element_class(element)
    if (
        element_class == "AggregateBallotSelection"
        and self.get_element_class(element.getparent())
        not in self.aggregate_contest_types
    ):
      return
    vote_count_types = _get_vote_count_types(element)
    missing_types = [
        vote_total_type
        for vote_total_type in _VOTE_TOTAL_TYPES
        if vote_total_type not in vote_count_types
    ]
    if missing_types:
      raise loggers.ElectionError.from_message(
          f"{element_class} {element.get('objectId')} is missing VoteCounts of"
          f" type(s) {', '.join(missing_types)}.",
          [element],
      )


ELECTION_RESULTS_RULES = election_rules.ELECTION_RULES + (
    # go/keep-sorted start
    CandidateAndBallotMeasureSelectionTotalsRequired,
    DataSourcesRequired,
    RequiredContestResultsFieldsSet,
    ValidatePercentReporting,
    # go/keep-sorted end
)

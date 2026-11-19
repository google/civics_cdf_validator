# -*- coding: utf-8 -*-
"""Unit test for election_results_rules.py."""

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import election_results_rules
from lxml import etree


class RequiredContestResultsFieldsSetTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = election_results_rules.RequiredContestResultsFieldsSet(
        schema_tree=etree.fromstring(
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        )
    )

  def test_elements_returns_contest_and_its_subtypes_at_any_depth(self):
    schema_string = """
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:complexType abstract="true" name="Contest">
          <xs:sequence>
            <xs:element name="Name" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
        <xs:complexType name="BallotMeasureContest">
          <xs:complexContent>
            <xs:extension base="Contest"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType name="CandidateContest">
          <xs:complexContent>
            <xs:extension base="Contest"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType name="RetentionContest">
          <xs:complexContent>
            <xs:extension base="BallotMeasureContest"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType abstract="true" name="GpUnit">
          <xs:sequence>
            <xs:element name="Name" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
        <xs:complexType name="ReportingUnit">
          <xs:complexContent>
            <xs:extension base="GpUnit"/>
          </xs:complexContent>
        </xs:complexType>
      </xs:schema>
    """
    validator = election_results_rules.RequiredContestResultsFieldsSet(
        schema_tree=etree.fromstring(schema_string)
    )

    elements = validator.elements()

    self.assertCountEqual(
        elements,
        [
            "Contest",
            "BallotMeasureContest",
            "CandidateContest",
            "RetentionContest",
        ],
    )

  def test_contest_with_all_fields_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <CurrentResultsReportingStage>preliminary</CurrentResultsReportingStage>
        <ResultsExpected>2026-11-03T21:00:00-05:00</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2026-11-03T21:00:00-05:00</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_contest_with_inherited_stage_collection_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <CurrentResultsReportingStage>preliminary</CurrentResultsReportingStage>
        <ResultsExpected>2026-11-03T21:00:00-05:00</ResultsExpected>
        <ResultsReportingStageCollection>
          <InheritFromComposedContest>true</InheritFromComposedContest>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  @parameterized.named_parameters(
      (
          "current_results_reporting_stage",
          """
          <Contest objectId="con1">
            <ResultsExpected>2026-11-03T21:00:00-05:00</ResultsExpected>
            <ResultsReportingStageCollection>
              <ResultsReportingStage>
                <StageType>preliminary</StageType>
                <ExpectedStartDateTime>2026-11-03T21:00:00-05:00</ExpectedStartDateTime>
              </ResultsReportingStage>
            </ResultsReportingStageCollection>
          </Contest>
          """,
          "CurrentResultsReportingStage",
      ),
      (
          "results_expected",
          """
          <Contest objectId="con1">
            <CurrentResultsReportingStage>preliminary</CurrentResultsReportingStage>
            <ResultsReportingStageCollection>
              <ResultsReportingStage>
                <StageType>preliminary</StageType>
                <ExpectedStartDateTime>2026-11-03T21:00:00-05:00</ExpectedStartDateTime>
              </ResultsReportingStage>
            </ResultsReportingStageCollection>
          </Contest>
          """,
          "ResultsExpected",
      ),
      (
          "results_reporting_stage_collection",
          """
          <Contest objectId="con1">
            <CurrentResultsReportingStage>preliminary</CurrentResultsReportingStage>
            <ResultsExpected>2026-11-03T21:00:00-05:00</ResultsExpected>
          </Contest>
          """,
          "ResultsReportingStageCollection",
      ),
  )
  def test_contest_missing_one_field_fails(
      self, contest_string: str, missing_field: str
  ):
    contest = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(contest)

    self.assertEqual(
        context.exception.log_entry[0].message,
        f"Contest con1 is missing required field(s) {missing_field}. Election"
        " results feeds must set CurrentResultsReportingStage,"
        " ResultsExpected, ResultsReportingStageCollection on every Contest.",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [contest])

  def test_contest_missing_all_fields_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <Name>Mayor</Name>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))

    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest con1 is missing required field(s)"
        " CurrentResultsReportingStage, ResultsExpected,"
        " ResultsReportingStageCollection. Election results feeds must set"
        " CurrentResultsReportingStage, ResultsExpected,"
        " ResultsReportingStageCollection on every Contest.",
    )

  def test_election_results_rules_extend_election_rules(self):
    self.assertIn(
        election_results_rules.RequiredContestResultsFieldsSet,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


class DataSourcesRequiredTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = election_results_rules.DataSourcesRequired()

  def test_elements_returns_election_report(self):
    elements = self.validator.elements()

    self.assertEqual(elements, ["ElectionReport"])

  def test_election_report_with_data_source_collection_succeeds(self):
    election_report_string = """
      <ElectionReport>
        <DataSourceCollection/>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))

  def test_election_report_without_data_source_collection_fails(self):
    election_report = etree.fromstring("<ElectionReport/>")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(election_report)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectionReport is missing required field DataSourceCollection."
        " Election results feeds must set DataSourceCollection on the"
        " ElectionReport.",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [election_report])

  def test_election_results_rules_include_data_sources_required(self):
    self.assertIn(
        election_results_rules.DataSourcesRequired,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


class ValidatePercentReportingTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = election_results_rules.ValidatePercentReporting(
        schema_tree=etree.fromstring(
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        )
    )

  def test_elements_returns_contest_and_its_subtypes_at_any_depth(self):
    schema_string = """
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:complexType name="BallotMeasureContest">
          <xs:complexContent>
            <xs:extension base="Contest"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType name="RetentionContest">
          <xs:complexContent>
            <xs:extension base="BallotMeasureContest"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType name="ReportingUnit">
          <xs:complexContent>
            <xs:extension base="GpUnit"/>
          </xs:complexContent>
        </xs:complexType>
      </xs:schema>
    """
    validator = election_results_rules.ValidatePercentReporting(
        schema_tree=etree.fromstring(schema_string)
    )

    elements = validator.elements()

    self.assertCountEqual(
        elements, ["Contest", "BallotMeasureContest", "RetentionContest"]
    )

  def test_contest_with_estimated_expected_vote_percentage_succeeds(self):
    contest_string = """
      <Contest>
        <EstimatedExpectedVotePercentage>24.2</EstimatedExpectedVotePercentage>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_contest_with_sub_units_reported_and_total_sub_units_succeeds(self):
    contest_string = """
      <Contest>
        <SubUnitsReported>48</SubUnitsReported>
        <TotalSubUnits>100</TotalSubUnits>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  @parameterized.named_parameters(
      (
          "no_percent_reporting_fields",
          '<Contest objectId="con1"/>',
          "EstimatedExpectedVotePercentage, SubUnitsReported, TotalSubUnits",
      ),
      (
          "only_sub_units_reported",
          """
          <Contest objectId="con1">
            <SubUnitsReported>48</SubUnitsReported>
          </Contest>
          """,
          "EstimatedExpectedVotePercentage, TotalSubUnits",
      ),
      (
          "only_total_sub_units",
          """
          <Contest objectId="con1">
            <TotalSubUnits>100</TotalSubUnits>
          </Contest>
          """,
          "EstimatedExpectedVotePercentage, SubUnitsReported",
      ),
  )
  def test_contest_missing_percent_reporting_fields_fails(
      self, contest_string: str, missing_fields: str
  ):
    contest = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(contest)

    self.assertEqual(
        context.exception.log_entry[0].message,
        f"Contest con1 is missing field(s) {missing_fields}. Election results"
        " feeds must set either EstimatedExpectedVotePercentage or both"
        " SubUnitsReported and TotalSubUnits on every Contest.",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [contest])

  def test_election_results_rules_include_validate_percent_reporting(self):
    self.assertIn(
        election_results_rules.ValidatePercentReporting,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


if __name__ == "__main__":
  absltest.main()

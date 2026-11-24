# -*- coding: utf-8 -*-
"""Unit test for election_results_rules.py."""

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import election_results_rules
from lxml import etree

_SCHEMA_TREE = etree.fromstring(b"""
  <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:complexType abstract="true" name="Contest"/>
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
    <xs:complexType name="PartyContest">
      <xs:complexContent>
        <xs:extension base="Contest"/>
      </xs:complexContent>
    </xs:complexType>
    <xs:complexType name="RetentionContest">
      <xs:complexContent>
        <xs:extension base="BallotMeasureContest"/>
      </xs:complexContent>
    </xs:complexType>
    <xs:complexType abstract="true" name="BallotSelection"/>
    <xs:complexType name="BallotMeasureSelection">
      <xs:complexContent>
        <xs:extension base="BallotSelection"/>
      </xs:complexContent>
    </xs:complexType>
    <xs:complexType name="CandidateSelection">
      <xs:complexContent>
        <xs:extension base="BallotSelection"/>
      </xs:complexContent>
    </xs:complexType>
    <xs:complexType name="PartySelection">
      <xs:complexContent>
        <xs:extension base="BallotSelection"/>
      </xs:complexContent>
    </xs:complexType>
  </xs:schema>
""")

_TOTAL_VOTE_COUNTS = """
  <VoteCounts>
    <Type>total</Type>
    <Count>120</Count>
  </VoteCounts>
"""

_TOTAL_PERCENT_VOTE_COUNTS = """
  <VoteCounts>
    <Type>other</Type>
    <OtherType>total-percent</OtherType>
    <Count>40</Count>
  </VoteCounts>
"""


def _other_type_vote_counts(*other_types: str) -> str:
  """Returns a VoteCounts element string for each of the given OtherTypes."""
  return "".join(
      f"""
      <VoteCounts>
        <Type>other</Type>
        <OtherType>{other_type}</OtherType>
        <Count>3</Count>
      </VoteCounts>
      """
      for other_type in other_types
  )


def _party_contest(
    contest_fields: str, *selection_other_types: tuple[str, ...]
) -> etree._Element:
  """Returns a PartyContest with a PartySelection for each OtherTypes tuple.

  The PartySelections have objectIds ps1, ps2, and so on.

  Args:
    contest_fields: XML for the PartyContest fields, such as NumberElected.
    *selection_other_types: The VoteCounts OtherTypes of each PartySelection.
  """
  selections = "".join(
      f"""
      <BallotSelection objectId="ps{index}" xsi:type="PartySelection">
        <VoteCountsCollection>
          {_other_type_vote_counts(*other_types)}
        </VoteCountsCollection>
      </BallotSelection>
      """
      for index, other_types in enumerate(selection_other_types, start=1)
  )
  return etree.fromstring(f"""
    <Contest objectId="con1" xsi:type="PartyContest"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      {selections}
      {contest_fields}
    </Contest>
  """)


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


class CandidateAndBallotMeasureSelectionTotalsRequiredTest(
    parameterized.TestCase
):

  def setUp(self):
    super().setUp()
    self.validator = (
        election_results_rules.CandidateAndBallotMeasureSelectionTotalsRequired(
            schema_tree=_SCHEMA_TREE
        )
    )
    self.validator.setup()

  def test_elements_returns_candidate_and_ballot_measure_selections(self):
    elements = self.validator.elements()

    self.assertCountEqual(
        elements,
        [
            "AggregateBallotSelection",
            "BallotMeasureSelection",
            "CandidateSelection",
        ],
    )

  def test_elements_includes_selection_subtypes(self):
    schema_tree = etree.fromstring(b"""
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:complexType name="CandidateSelection">
          <xs:complexContent>
            <xs:extension base="BallotSelection"/>
          </xs:complexContent>
        </xs:complexType>
        <xs:complexType name="WriteInCandidateSelection">
          <xs:complexContent>
            <xs:extension base="CandidateSelection"/>
          </xs:complexContent>
        </xs:complexType>
      </xs:schema>
    """)
    validator = (
        election_results_rules.CandidateAndBallotMeasureSelectionTotalsRequired(
            schema_tree=schema_tree
        )
    )

    elements = validator.elements()

    self.assertIn("WriteInCandidateSelection", elements)

  @parameterized.parameters("BallotMeasureSelection", "CandidateSelection")
  def test_selection_with_vote_totals_succeeds(self, selection_type):
    selection_string = f"""
      <BallotSelection objectId="bs1" xsi:type="{selection_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <VoteCountsCollection>
          {_TOTAL_VOTE_COUNTS}
          {_TOTAL_PERCENT_VOTE_COUNTS}
        </VoteCountsCollection>
      </BallotSelection>
    """

    self.validator.check(etree.fromstring(selection_string))

  @parameterized.named_parameters(
      (
          "no_vote_counts",
          "CandidateSelection",
          "",
          "total, total-percent",
      ),
      (
          "no_total",
          "BallotMeasureSelection",
          _TOTAL_PERCENT_VOTE_COUNTS,
          "total",
      ),
      (
          "no_total_percent",
          "CandidateSelection",
          _TOTAL_VOTE_COUNTS,
          "total-percent",
      ),
  )
  def test_selection_missing_vote_totals_fails(
      self, selection_type, vote_counts, missing_types
  ):
    selection = etree.fromstring(f"""
      <BallotSelection objectId="bs1" xsi:type="{selection_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <VoteCountsCollection>
          {vote_counts}
        </VoteCountsCollection>
      </BallotSelection>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(selection)

    self.assertEqual(
        context.exception.log_entry[0].message,
        f"{selection_type} bs1 is missing VoteCounts of type(s)"
        f" {missing_types}.",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [selection])

  def test_selection_without_vote_counts_collection_fails(self):
    selection = etree.fromstring("<CandidateSelection objectId='cs1'/>")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(selection)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateSelection cs1 is missing VoteCounts of type(s) total,"
        " total-percent.",
    )

  @parameterized.parameters(
      "BallotMeasureContest", "CandidateContest", "RetentionContest"
  )
  def test_aggregate_ballot_selection_with_vote_totals_succeeds(
      self, contest_type
  ):
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="{contest_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1">
          <VoteCountsCollection>
            {_TOTAL_VOTE_COUNTS}
            {_TOTAL_PERCENT_VOTE_COUNTS}
          </VoteCountsCollection>
        </AggregateBallotSelection>
      </Contest>
    """)

    self.validator.check(contest.find("AggregateBallotSelection"))

  @parameterized.parameters(
      "BallotMeasureContest", "CandidateContest", "RetentionContest"
  )
  def test_aggregate_ballot_selection_missing_vote_totals_fails(
      self, contest_type
  ):
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="{contest_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1">
          <VoteCountsCollection>
            {_TOTAL_VOTE_COUNTS}
          </VoteCountsCollection>
        </AggregateBallotSelection>
      </Contest>
    """)
    aggregate_selection = contest.find("AggregateBallotSelection")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(aggregate_selection)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "AggregateBallotSelection agg1 is missing VoteCounts of type(s)"
        " total-percent.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [aggregate_selection]
    )

  def test_aggregate_ballot_selection_in_party_contest_succeeds(self):
    contest = etree.fromstring("""
      <Contest objectId="con1" xsi:type="PartyContest"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1"/>
      </Contest>
    """)

    self.validator.check(contest.find("AggregateBallotSelection"))

  def test_election_results_rules_include_selection_totals_required(self):
    self.assertIn(
        election_results_rules.CandidateAndBallotMeasureSelectionTotalsRequired,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


class PartySelectionSeatCountsRequiredTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = election_results_rules.PartySelectionSeatCountsRequired(
        schema_tree=_SCHEMA_TREE
    )
    self.validator.setup()

  def test_elements_returns_party_selection_and_aggregate_selection(self):
    elements = self.validator.elements()

    self.assertCountEqual(
        elements, ["AggregateBallotSelection", "PartySelection"]
    )

  def test_party_selection_with_seat_counts_succeeds(self):
    vote_counts = _other_type_vote_counts(
        "seats-won", "seats-leading", "seats-total"
    )
    selection_string = f"""
      <BallotSelection objectId="ps1" xsi:type="PartySelection"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <VoteCountsCollection>
          {vote_counts}
        </VoteCountsCollection>
      </BallotSelection>
    """

    self.validator.check(etree.fromstring(selection_string))

  @parameterized.named_parameters(
      ("no_seat_counts", (), "seats-won, seats-leading, seats-total"),
      ("only_seats_won", ("seats-won",), "seats-leading, seats-total"),
      ("no_seats_total", ("seats-won", "seats-leading"), "seats-total"),
  )
  def test_party_selection_missing_seat_counts_fails(
      self, seat_types, missing_types
  ):
    selection = etree.fromstring(f"""
      <BallotSelection objectId="ps1" xsi:type="PartySelection"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <VoteCountsCollection>
          {_TOTAL_VOTE_COUNTS}
          {_other_type_vote_counts(*seat_types)}
        </VoteCountsCollection>
      </BallotSelection>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(selection)

    self.assertEqual(
        context.exception.log_entry[0].message,
        f"PartySelection ps1 is missing VoteCounts of type(s) {missing_types}.",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [selection])

  def test_aggregate_ballot_selection_with_seat_counts_succeeds(self):
    vote_counts = _other_type_vote_counts(
        "seats-won", "seats-leading", "seats-total"
    )
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="PartyContest"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1">
          <VoteCountsCollection>
            {vote_counts}
          </VoteCountsCollection>
        </AggregateBallotSelection>
      </Contest>
    """)

    self.validator.check(contest.find("AggregateBallotSelection"))

  def test_aggregate_ballot_selection_missing_seat_counts_fails(self):
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="PartyContest"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1">
          <VoteCountsCollection>
            {_other_type_vote_counts("seats-won")}
          </VoteCountsCollection>
        </AggregateBallotSelection>
      </Contest>
    """)
    aggregate_selection = contest.find("AggregateBallotSelection")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(aggregate_selection)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "AggregateBallotSelection agg1 is missing VoteCounts of type(s)"
        " seats-leading, seats-total.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [aggregate_selection]
    )

  @parameterized.parameters("BallotMeasureContest", "CandidateContest")
  def test_aggregate_ballot_selection_in_other_contest_succeeds(
      self, contest_type
  ):
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="{contest_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1"/>
      </Contest>
    """)

    self.validator.check(contest.find("AggregateBallotSelection"))

  def test_election_results_rules_include_seat_counts_required(self):
    self.assertIn(
        election_results_rules.PartySelectionSeatCountsRequired,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


class ValidateSeatsNoElectionTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = election_results_rules.ValidateSeatsNoElection(
        schema_tree=_SCHEMA_TREE
    )
    self.validator.setup()

  def _aggregate_selection_in_party_contest(
      self, number_elected: str, other_types: tuple[str, ...]
  ) -> etree._Element:
    """Returns the AggregateBallotSelection of a PartyContest with 5 seats."""
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="PartyContest"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1">
          <VoteCountsCollection>
            {_other_type_vote_counts(*other_types)}
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <TotalSeats>5</TotalSeats>
        <NumberElected>{number_elected}</NumberElected>
      </Contest>
    """)
    return contest.find("AggregateBallotSelection")

  def test_elements_returns_party_and_aggregate_selections(self):
    elements = self.validator.elements()

    self.assertCountEqual(
        elements, ["AggregateBallotSelection", "PartySelection"]
    )

  def test_seats_not_up_for_election_with_seats_no_election_succeeds(self):
    contest = _party_contest(
        "<TotalSeats>5</TotalSeats><NumberElected>3</NumberElected>",
        ("seats-won", "seats-no-election"),
    )

    self.validator.check(contest.find("BallotSelection"))

  def test_seats_not_up_for_election_without_seats_no_election_fails(self):
    contest = _party_contest(
        "<TotalSeats>5</TotalSeats><NumberElected>3</NumberElected>",
        ("seats-won",),
    )
    selection = contest.find("BallotSelection")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(selection)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartySelection ps1 is missing VoteCounts of type seats-no-election,"
        " which is required because PartyContest con1 has a NumberElected (3)"
        " different from its TotalSeats (5).",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [selection])

  def test_all_seats_up_for_election_without_seats_no_election_succeeds(self):
    contest = _party_contest(
        "<TotalSeats>5</TotalSeats><NumberElected>5</NumberElected>",
        ("seats-won",),
    )

    self.validator.check(contest.find("BallotSelection"))

  def test_all_seats_up_for_election_with_seats_no_election_fails(self):
    contest = _party_contest(
        "<TotalSeats>5</TotalSeats><NumberElected>5</NumberElected>",
        ("seats-won", "seats-no-election"),
    )
    selection = contest.find("BallotSelection")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(selection)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartySelection ps1 has VoteCounts of type seats-no-election, but"
        " PartyContest con1 has a NumberElected equal to its TotalSeats (5).",
    )
    self.assertEqual(context.exception.log_entry[0].elements, [selection])

  @parameterized.named_parameters(
      ("seats_not_up_for_election", "3", ("seats-won", "seats-no-election")),
      ("all_seats_up_for_election", "5", ("seats-won",)),
  )
  def test_aggregate_ballot_selection_succeeds(
      self, number_elected, other_types
  ):
    aggregate_selection = self._aggregate_selection_in_party_contest(
        number_elected, other_types
    )

    self.validator.check(aggregate_selection)

  @parameterized.named_parameters(
      (
          "seats_not_up_for_election_without_seats_no_election",
          "3",
          ("seats-won",),
          (
              "AggregateBallotSelection agg1 is missing VoteCounts of type"
              " seats-no-election, which is required because PartyContest"
              " con1 has a NumberElected (3) different from its TotalSeats"
              " (5)."
          ),
      ),
      (
          "all_seats_up_for_election_with_seats_no_election",
          "5",
          ("seats-won", "seats-no-election"),
          (
              "AggregateBallotSelection agg1 has VoteCounts of type"
              " seats-no-election, but PartyContest con1 has a NumberElected"
              " equal to its TotalSeats (5)."
          ),
      ),
  )
  def test_aggregate_ballot_selection_fails(
      self, number_elected, other_types, expected_message
  ):
    aggregate_selection = self._aggregate_selection_in_party_contest(
        number_elected, other_types
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(aggregate_selection)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(context.exception.log_entry[0].message, expected_message)
    self.assertEqual(
        context.exception.log_entry[0].elements, [aggregate_selection]
    )

  def test_aggregate_ballot_selection_outside_party_contest_succeeds(self):
    contest = etree.fromstring("""
      <Contest objectId="con1" xsi:type="CandidateContest"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <AggregateBallotSelection objectId="agg1"/>
        <TotalSeats>5</TotalSeats>
        <NumberElected>3</NumberElected>
      </Contest>
    """)

    self.validator.check(contest.find("AggregateBallotSelection"))

  @parameterized.parameters("BallotMeasureContest", "CandidateContest")
  def test_party_selection_outside_party_contest_succeeds(self, contest_type):
    contest = etree.fromstring(f"""
      <Contest objectId="con1" xsi:type="{contest_type}"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <BallotSelection objectId="ps1" xsi:type="PartySelection"/>
        <TotalSeats>5</TotalSeats>
        <NumberElected>3</NumberElected>
      </Contest>
    """)

    self.validator.check(contest.find("BallotSelection"))

  @parameterized.named_parameters(
      ("no_number_elected", "<TotalSeats>5</TotalSeats>"),
      ("no_total_seats", "<NumberElected>3</NumberElected>"),
      (
          "number_elected_not_an_integer",
          "<TotalSeats>5</TotalSeats><NumberElected>three</NumberElected>",
      ),
  )
  def test_contest_without_seat_numbers_succeeds(self, contest_fields):
    contest = _party_contest(contest_fields, ("seats-won",))

    self.validator.check(contest.find("BallotSelection"))

  def test_election_results_rules_include_validate_seats_no_election(self):
    self.assertIn(
        election_results_rules.ValidateSeatsNoElection,
        election_results_rules.ELECTION_RESULTS_RULES,
    )


if __name__ == "__main__":
  absltest.main()

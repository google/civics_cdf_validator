# -*- coding: utf-8 -*-
"""Unit test for election_rules.py."""

import datetime

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
from civics_cdf_validator.rulesets import election_rules
import freezegun
from lxml import etree
import networkx


class PercentSumTest(absltest.TestCase):

  def setUp(self):
    super(PercentSumTest, self).setUp()
    self.validator = election_rules.PercentSum(None, None)
    self.root_string = """
      <Contest>
        <BallotSelection>
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def test_contest_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Contest"])

  def test_zero_percent_total_is_valid_succeeds(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_one_hundred_percent_total_is_valid_succeeds(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>40.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_invalid_percents_fails(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_only_use_count_for_other_type_total_percent_regular_type_succeeds(
      self,
  ):
    vote_counts = """
      <VoteCounts>
        <Type>total-percent</Type>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <Type>total-percent</Type>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_only_use_count_for_other_type_total_percent_invalid_succeeds(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>percent-sum</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>percent-sum</OtherType>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)

    self.validator.check(element)


class PartisanPrimaryTest(absltest.TestCase):

  _base_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  # elements test
  def test_elections_succeeds(self):
    election_string = PartisanPrimaryTest._base_report
    election_tree = etree.fromstring(election_string)
    validator = election_rules.PartisanPrimary(election_tree, None)

    self.assertEqual(["Election"], validator.elements())

  # check tests
  def test_party_ids_are_present_and_non_empty_succeeds(self):
    election_details = """
      <Type>primary</Type>
      <Contest xsi:type="CandidateContest">
        <PrimaryPartyIds>abc123</PrimaryPartyIds>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")

    election_rules.PartisanPrimary(root, None).check(election)

  def test_party_ids_do_not_exist_no_party_partisan_primary_warns(
      self,
  ):
    election_details = """
      <Type>partisan-primary-closed</Type>
      <Contest xsi:type="CandidateContest">
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimary(root, None).check(election)

  def test_party_ids_do_not_exist_empty_party_partisan_primary_warns(
      self,
  ):
    election_details = """
      <Type>partisan-primary-closed</Type>
      <Contest xsi:type="CandidateContest">
        <PrimaryPartyIds></PrimaryPartyIds>
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimary(root, None).check(election)

  def test_party_ids_do_not_exist_white_space_partisan_primary_warns(
      self,
  ):
    election_details = """
      <Type>partisan-primary-closed</Type>
      <Contest xsi:type="CandidateContest">
        <PrimaryPartyIds>      </PrimaryPartyIds>
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimary(root, None).check(election)

  def test_party_ids_do_not_exist_no_party_open_primary_election_warns(
      self,
  ):
    election_details = """
      <Type>partisan-primary-open</Type>
      <Contest xsi:type="CandidateContest">
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimary(root, None).check(election)

  def test_missing_party_ids_general_election_succeeds(self):
    election_details = """
      <Type>general</Type>
      <Contest xsi:type="CandidateContest">
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    election_rules.PartisanPrimary(root, None).check(election)

  def test_missing_party_ids_nonpartisan_primary_succeeds(self):
    election_details = """
      <Type>primary</Type>
      <Contest xsi:type="CandidateContest">
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    election_rules.PartisanPrimary(root, None).check(election)

  def test_missing_party_ids_no_election_type_succeeds(self):
    election_details = """
      <Contest xsi:type="CandidateContest">
        <Name>2020 Election</Name>
      </Contest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)
    election = root.find("Election")
    election.sourceline = 7

    election_rules.PartisanPrimary(root, None).check(election)

  def test_handles_multiple_elections_succeeds(self):
    election_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <Type>primary</Type>
          <Contest xsi:type="CandidateContest">
            <PrimaryPartyIds>abc123</PrimaryPartyIds>
            <Name>2020 Primary Election</Name>
          </Contest>
        </Election>
        <Election>
          <Type>general</Type>
          <Contest xsi:type="CandidateContest">
            <Name>2020 General Election</Name>
          </Contest>
        </Election>
      </ElectionReport>
    """
    root = etree.fromstring(election_string)
    elections = root.findall("Election")
    for election in elections:
      election.sourceline = 7

      election_rules.PartisanPrimary(root, None).check(election)


class PartisanPrimaryHeuristicTest(absltest.TestCase):

  _base_election_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  _general_candidate_contest = """
    <Type>general</Type>
    <Contest xsi:type="CandidateContest">
      {}
    </Contest>
  """

  _base_candidate_contest = _base_election_report.format(
      _general_candidate_contest
  )

  def test_elections_succeeds(self):
    election_details = "<Name>2020 election</Name>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)
    validator = election_rules.PartisanPrimaryHeuristic(election_tree, None)

    self.assertEqual(["Election"], validator.elements())

  def test_contests_that_do_not_suggest_primary_no_name_succeeds(self):
    root_string = self._base_candidate_contest
    root = etree.fromstring(root_string)
    election = root.find("Election")

    election_rules.PartisanPrimaryHeuristic(root, None).check(election)

  def test_contests_that_do_not_suggest_primary_empty_name_succeeds(
      self,
  ):
    contest_details = """
      <Name></Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)
    election = root.find("Election").find("Contest")

    election_rules.PartisanPrimaryHeuristic(root, None).check(election)

  def test_possible_primary_detected_dem_warns(self):
    contest_details = """
      <Name>Might Be Primary (dem)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)
    election = root.find("Election")
    election.find("Contest").sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimaryHeuristic(root, None).check(election)

  def test_possible_primary_detected_rep_warns(self):
    contest_details = """
      <Name>Might Be Primary (rep)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)
    election = root.find("Election")
    election.find("Contest").sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimaryHeuristic(root, None).check(election)

  def test_possible_primary_detected_lib_warns(self):
    contest_details = """
      <Name>Might Be Primary (lib)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)
    election = root.find("Election")
    election.find("Contest").sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      election_rules.PartisanPrimaryHeuristic(root, None).check(election)


class CandidatesReferencedInRelatedContestsTest(absltest.TestCase):

  def setUp(self):
    super(CandidatesReferencedInRelatedContestsTest, self).setUp()
    self.validator = election_rules.CandidatesReferencedInRelatedContests(
        None, None
    )

  # elements test
  def test_election_report_succeeds(self):
    self.assertEqual(["ElectionReport"], self.validator.elements())

  # _register_person_to_candidate_to_contests tests
  def test_map_of_persons_to_candidates_to_contests_succeeds(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can002</CandidateIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)
    expected_mapping = {
        "per001": {
            "can001": ["con001", "con002"],
        },
        "per002": {
            "can002": ["con001"],
            "can003": ["con002"],
        },
    }

    actual_mapping = self.validator._register_person_to_candidate_to_contests(
        report_elem
    )

    self.assertEqual(actual_mapping, expected_mapping)

  def test_candidate_is_not_referenced_in_a_contest_fails(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per001</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can002</CandidateIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator._register_person_to_candidate_to_contests(report_elem)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "A Candidate should be referenced in a Contest. "
            "Candidate can004 is not referenced."
        ),
    )

  # _construct_contest_graph tests
  def test_creates_node_for_each_contest_no_relationships_succeeds(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001"/>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    expected_contest_nodes = ["con001", "con002", "con003"]

    self.validator._construct_contest_graph(report_elem)

    for node in expected_contest_nodes:
      found_node = node in self.validator.contest_graph.nodes()
      if not found_node:
        self.fail(
            ("No matching node found for id: {} and relative set: {}").format(
                node.id, node.relatives
            )
        )

  def test_composing_contests_are_connected_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002 con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
        <Contest objectId="con004">
          <ComposingContestIds>con005 con006</ComposingContestIds>
        </Contest>
        <Contest objectId="con005"/>
        <Contest objectId="con006"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    self.validator._construct_contest_graph(report_elem)

    self.assertTrue(
        networkx.has_path(self.validator.contest_graph, "con001", "con002")
    )
    self.assertTrue(
        networkx.has_path(self.validator.contest_graph, "con002", "con003")
    )

  def test_invalid_composing_contest_id_fails(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator._construct_contest_graph(report_elem)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Contest con001 contains a composing Contest Id "
            "(con004) that does not exist."
        ),
    )

  def test_tree_roots_are_connected_for_any_subsequent_relationship_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002 con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con002">
          <SubsequentContestId>con005</SubsequentContestId>
        </Contest>
        <Contest objectId="con003"/>
        <Contest objectId="con004">
          <ComposingContestIds>con005 con006</ComposingContestIds>
        </Contest>
        <Contest objectId="con005"/>
        <Contest objectId="con006"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    self.validator._construct_contest_graph(report_elem)

    # assert roots are connected for subsequent relationships
    self.assertTrue(
        networkx.has_path(self.validator.contest_graph, "con002", "con005")
    )

  def test_invalid_subsequent_contest_id_fails(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <SubsequentContestId>con004</SubsequentContestId>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator._construct_contest_graph(report_elem)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Contest con001 contains a subsequent Contest Id "
            "(con004) that does not exist."
        ),
    )

  def test_any_contest_in_given_list_not_related_parent_child_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    contest_id_list = ["con001", "con002", "con003"]

    self.validator._construct_contest_graph(report_elem)
    are_related = self.validator._check_candidate_contests_are_related(
        contest_id_list
    )

    self.assertFalse(are_related)

  def test_all_contests_in_given_list_are_related_composing_rel_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con003">
          <ComposingContestIds>con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con004"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    contest_id_list = ["con001", "con003", "con004"]

    self.validator._construct_contest_graph(report_elem)
    are_related = self.validator._check_candidate_contests_are_related(
        contest_id_list
    )

    self.assertTrue(are_related)

  def test_all_contests_in_given_list_are_related_subsequent_rel_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <SubsequentContestId>con003</SubsequentContestId>
        </Contest>
        <Contest objectId="con003">
          <SubsequentContestId>con004</SubsequentContestId>
        </Contest>
        <Contest objectId="con004"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    contest_id_list = ["con001", "con003", "con004"]

    self.validator._construct_contest_graph(report_elem)
    are_related = self.validator._check_candidate_contests_are_related(
        contest_id_list
    )

    self.assertTrue(are_related)

  def test_contest_trees_not_related_composing_rel_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003">
          <ComposingContestIds>con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con004"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    contest_id_list = ["con001", "con002", "con003", "con004"]

    self.validator._construct_contest_graph(report_elem)
    are_related = self.validator._check_candidate_contests_are_related(
        contest_id_list
    )

    self.assertFalse(are_related)

  # _check_separate_candidates_not_related tests
  def test_separate_candidates_belong_to_separate_contest_families_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003">
          <ComposingContestIds>con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con004"/>
        <Contest objectId="con005">
          <ComposingContestIds>con006</ComposingContestIds>
        </Contest>
        <Contest objectId="con006"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    # separate candidates for each contest family
    candidate_contest_mapping = {
        "can001": ["con001", "con002"],
        "can002": ["con003", "con004"],
        "can003": ["con005", "con006"],
    }

    self.validator._construct_contest_graph(report_elem)
    valid_cands = self.validator._check_separate_candidates_not_related(
        candidate_contest_mapping
    )

    self.assertTrue(valid_cands)

  def test_separate_candidates_belong_to_related_contest_families_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002 con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003">
          <ComposingContestIds>con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con004"/>
        <Contest objectId="con005">
          <ComposingContestIds>con006</ComposingContestIds>
        </Contest>
        <Contest objectId="con006"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    # separate candidates for each contest family
    candidate_contest_mapping = {
        "can001": ["con001", "con002"],
        "can002": ["con003", "con004"],
        "can003": ["con005", "con006"],
    }

    self.validator._construct_contest_graph(report_elem)
    valid_cands = self.validator._check_separate_candidates_not_related(
        candidate_contest_mapping
    )

    self.assertFalse(valid_cands)

  # check tests
  def test_same_person_candidates_in_unrelated_contests_succeeds(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can002 can004</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidates_valid_in_related_contests_composing_succeeds(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can002</CandidateIds>
            <ComposingContestIds>con002</ComposingContestIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can002</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidate_valid_in_sibling_composing_contests_succeeds(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="parent" type="CandidateContest">
            <ComposingContestIds>child1 child2</ComposingContestIds>
          </Contest>
          <Contest objectId="child1" type="CandidateContest">
            <BallotSelection objectId="one" type="CandidateSelection">
              <CandidateIds>can001</CandidateIds>
            </BallotSelection>
          </Contest>
          <Contest objectId="child2" type="CandidateContest">
            <BallotSelection objectId="two" type="CandidateSelection">
              <CandidateIds>can001</CandidateIds>
            </BallotSelection>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidates_valid_composing_multi_depth_succeeds(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
          <Person objectId="per003"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per003</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can002 can003</CandidateIds>
            <ComposingContestIds>con002</ComposingContestIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can002</CandidateIds>
            <ComposingContestIds>con003</ComposingContestIds>
          </Contest>
          <Contest objectId="con003">
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidates_valid_in_related_contests_subsequent_succeeds(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can002</CandidateIds>
            <SubsequentContestId>con002</SubsequentContestId>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can002</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidate_valid_in_related_contests_subsequent_of_subsequent_succeeds(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="rep" type="CandidateContest">
            <BallotSelection objectId="two" type="CandidateSelection">
              <CandidateIds>can001</CandidateIds>
            </BallotSelection>
            <SubsequentContestId>gen</SubsequentContestId>
          </Contest>
          <Contest objectId="dem" type="CandidateContest">
            <BallotSelection objectId="one" type="CandidateSelection">
              <CandidateIds>can001</CandidateIds>
            </BallotSelection>
            <SubsequentContestId>runoff</SubsequentContestId>
          </Contest>
          <Contest objectId="runoff" type="CandidateContest">
            <SubsequentContestId>gen</SubsequentContestId>
          </Contest>
          <Contest objectId="gen" type="CandidateContest">
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidate_valid_in_related_contests_subsequent_of_composing_succeeds(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="gen" type="CandidateContest">
            <ComposingContestIds>rep dem</ComposingContestIds>
            <SubsequentContestId>runoff</SubsequentContestId>
          </Contest>
          <Contest objectId="rep" type="CandidateContest">
            <BallotSelection objectId="one" type="CandidateSelection">
              <CandidateIds>can001</CandidateIds>
            </BallotSelection>
          </Contest>
          <Contest objectId="dem" type="CandidateContest">
            <BallotSelection objectId="two" type="CandidateSelection">
              <CandidateIds>can002</CandidateIds>
            </BallotSelection>
          </Contest>
          <Contest objectId="runoff" type="CandidateContest">
            <BallotSelection objectId="two_runoff" type="CandidateSelection">
              <CandidateIds>can002</CandidateIds>
            </BallotSelection>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidates_valid_repeat_subsequent_succeeds(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
          <Person objectId="per003"/>
          <Person objectId="per004"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per003</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per004</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <Name>New York Democratic Primary</Name>
            <CandidateIds>can001 can002 can004</CandidateIds>
            <SubsequentContestId>con003</SubsequentContestId>
          </Contest>
          <Contest objectId="con002">
            <Name>New York Republican Primary</Name>
            <CandidateIds>can003 can004</CandidateIds>
            <SubsequentContestId>con003</SubsequentContestId>
          </Contest>
          <Contest objectId="con003">
            <Name>General Election</Name>
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    # The winner of each primary go on to the general election
    # the general election contest is the subsequent contest for both primaries
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_repeat_candidates_valid_subsequent_multi_depth_succeeds(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
          <Person objectId="per003"/>
          <Person objectId="per004"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per003</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per004</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <Name>New York Democratic Primary</Name>
            <CandidateIds>can001 can002</CandidateIds>
            <SubsequentContestId>con003</SubsequentContestId>
          </Contest>
          <Contest objectId="con002">
            <Name>New York Republican Primary</Name>
            <CandidateIds>can003 can004</CandidateIds>
            <SubsequentContestId>con003</SubsequentContestId>
          </Contest>
          <Contest objectId="con003">
            <Name>General Election</Name>
            <CandidateIds>can001 can003</CandidateIds>
            <SubsequentContestId>con004</SubsequentContestId>
          </Contest>
          <Contest objectId="con004">
            <Name>General Runoff Election</Name>
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    # The winner of each primary go on to the general election
    # The general election contest is the subsequent contest for both primaries
    # The general election leads into the runoff as its subsequent contest
    report_elem = etree.fromstring(election_report)

    self.validator.check(report_elem)

  def test_same_candidate_in_unrelated_contests_fails(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can003</CandidateIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can001 can004</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(report_elem)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Candidate can001 appears in the following contests"
            " which are not all related: con001, con002"
        ),
    )

  def test_person_has_multiple_candidates_in_related_contests_fails(
      self,
  ):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can003</CandidateIds>
            <ComposingContestIds>con002</ComposingContestIds>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can002 can004</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(report_elem)
    self.assertLen(context.exception.log_entry, 2)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Person per001 has separate candidates in contests that are related.",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "Person per002 has separate candidates in contests that are related.",
    )

  def test_person_has_multiple_candidates_in_subsequent_contests_fails(self):
    election_report = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per001"/>
          <Person objectId="per002"/>
        </PersonCollection>
        <CandidateCollection>
          <Candidate objectId="can001">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can002">
            <PersonId>per001</PersonId>
          </Candidate>
          <Candidate objectId="can003">
            <PersonId>per002</PersonId>
          </Candidate>
          <Candidate objectId="can004">
            <PersonId>per002</PersonId>
          </Candidate>
        </CandidateCollection>
        <ContestCollection>
          <Contest objectId="con001">
            <CandidateIds>can001 can003</CandidateIds>
            <SubsequentContestId>con002</SubsequentContestId>
          </Contest>
          <Contest objectId="con002">
            <CandidateIds>can002 can004</CandidateIds>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(report_elem)
    self.assertLen(context.exception.log_entry, 2)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Person per001 has separate candidates in contests that are related.",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "Person per002 has separate candidates in contests that are related.",
    )


class ProperBallotSelectionTest(absltest.TestCase):

  def setUp(self):
    super(ProperBallotSelectionTest, self).setUp()
    self.validator = election_rules.ProperBallotSelection(None, None)

  def test_all_elements_listed_as_keys_in_selection_mapping_succeeds(
      self,
  ):
    self.assertEqual(
        list(self.validator.elements()),
        [
            "BallotMeasureContest",
            "CandidateContest",
            "PartyContest",
            "RetentionContest",
        ],
    )

  def test_all_selections_in_contest_are_of_matching_type_succeeds(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Contest objectId="cc20002" xsi:type="CandidateContest">
          <BallotSelection objectId="cs111" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs222" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs333" xsi:type="CandidateSelection"/>
        </Contest>
      </ElectionReport>
    """
    element = etree.fromstring(contest_string)

    self.validator.check(element.find("Contest"))

  def test_all_selections_in_contest_are_not_of_matching_type_fails(
      self,
  ):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Contest objectId="cc20002" xsi:type="CandidateContest">
          <BallotSelection objectId="cs111" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs222" xsi:type="PartySelection"/>
          <BallotSelection objectId="cs333" xsi:type="CandidateSelection"/>
        </Contest>
      </ElectionReport>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element.find("Contest"))


class CorrectCandidateSelectionCountTest(absltest.TestCase):

  def setUp(self):
    super(CorrectCandidateSelectionCountTest, self).setUp()
    self.validator = election_rules.CorrectCandidateSelectionCount(None, None)

  def test_candidate_selection_with_missing_candidate_ids_warns(self):
    contest_string = """
      <Contest objectId="con-1" type="CandidateContest">
        <BallotSelection objectId="bs-1" type="CandidateSelection"/>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element.find("BallotSelection"))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The CandidateSelection bs-1 does not reference any candidates.",
    )

  def test_candidate_selection_with_multiple_candidate_ids_warns(self):
    contest_string = """
      <Contest objectId="con-1" type="CandidateContest">
        <BallotSelection objectId="bs-1" type="CandidateSelection">
          <CandidateIds>cand-1</CandidateIds>
          <CandidateIds>cand-2</CandidateIds>
        </BallotSelection>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element.find("BallotSelection"))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The CandidateSelection bs-1 is expected to have one CandidateIds but 2"
        " were found.",
    )

  def test_candidate_selection_with_single_candidate_ids_and_multiple_candidates_warns(
      self,
  ):
    contest_string = """
      <Contest objectId="con-1" type="CandidateContest">
        <BallotSelection objectId="bs-1" type="CandidateSelection">
          <CandidateIds>cand-1 cand-2 cand-3</CandidateIds>
        </BallotSelection>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element.find("BallotSelection"))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateIds for CandidateSelection bs-1 is expected to reference one"
        " candidate but 3 candidates were found. This warning can be ignored"
        " for party list elections.",
    )

  def test_candidate_selection_with_correct_candidate_ids_succeeds(self):
    contest_string = """
      <Contest objectId="con-1" type="CandidateContest">
        <BallotSelection objectId="bs-1" type="CandidateSelection">
          <CandidateIds>cand-1</CandidateIds>
        </BallotSelection>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    self.validator.check(element.find("BallotSelection"))


class SingularPartySelectionTest(absltest.TestCase):

  def setUp(self):
    super(SingularPartySelectionTest, self).setUp()
    self.validator = election_rules.SingularPartySelection(None, None)

  def test_one_party_valid_succeeds(self):
    element_string = """
        <PartySelection objectId="ps-123">
          <PartyIds>par123</PartyIds>
        </PartySelection>
    """
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_multiple_parties_fails(self):
    element_string = """
        <PartySelection objectId="ps-456-789">
          <PartyIds>par456 par789</PartyIds>
        </PartySelection>
    """
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartySelection has more than one associated party.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "ps-456-789",
    )

  def test_no_parties_fails(self):
    # Internal string is missing
    element_string = """
        <PartySelection objectId="ps-none">
          <PartyIds />
        </PartySelection>
    """
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartySelection has no associated parties.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "ps-none",
    )
    # Internal string is just blank space
    element_string = """
        <PartySelection objectId="ps-blank">
          <PartyIds> </PartyIds>
        </PartySelection>
    """
    element = etree.fromstring(element_string)
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartySelection has no associated parties.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "ps-blank"
    )


class ValidateDuplicateColorsTest(absltest.TestCase):

  def setUp(self):
    super(ValidateDuplicateColorsTest, self).setUp()
    self.root_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="PartyContest">
              <BallotSelection objectId="ps1" xsi:type="PartySelection">
                <PartyIds>par0001</PartyIds>
              </BallotSelection>
              <BallotSelection objectId="ps2" xsi:type="PartySelection">
                <PartyIds>par0002</PartyIds>
              </BallotSelection>
            </Contest>
            <Contest objectId="con2" xsi:type="PartyContest">
              <BallotSelection objectId="ps3" xsi:type="PartySelection">
                <PartyIds>par0003</PartyIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
        <PartyCollection>
          <Party objectId="par0001">
            <Name>
              <Text language="en">Republican</Text>
            </Name>
            {0}
          </Party>
          <Party objectId="par0002">
            <Name>
              <Text language="en">Democratic</Text>
            </Name>
            {1}
          </Party>
          <Party objectId="par0003">
            <Name>
              <Text language="en">Green</Text>
            </Name>
            {2}
          </Party>
        </PartyCollection>
      </ElectionReport>
    """
    self._color_template = "<Color>{}</Color>"
    self._colors_template = """
      <Colors>
        <DarkThemeColor>{dark_theme_color}</DarkThemeColor>
        <LightThemeColor>{light_theme_color}</LightThemeColor>
      </Colors>
    """

  def test_contest_with_party_with_no_color_warns(self):
    test_string = self.root_string.format(
        self._color_template.format("ff0000"),
        self._color_template.format("0000ff"),
        "",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Party (par0003) in PartyContest should have either Color or"
        " Colors.DarkThemeColor and Colors.LightThemeColor set.",
    )

  def test_contest_with_party_with_dark_theme_color_but_no_light_theme_color_warns(
      self,
  ):
    test_string = self.root_string.format(
        self._color_template.format("ff0000"),
        self._color_template.format("0000ff"),
        "<Colors><DarkThemeColor>000000</DarkThemeColor></Colors>",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Party (par0003) in PartyContest should have either Color or"
        " Colors.DarkThemeColor and Colors.LightThemeColor set.",
    )

  def test_contest_with_party_with_light_theme_color_but_no_dark_theme_color_warns(
      self,
  ):
    test_string = self.root_string.format(
        self._color_template.format("ff0000"),
        self._color_template.format("0000ff"),
        "<Colors><LightThemeColor>000000</LightThemeColor></Colors>",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Party (par0003) in PartyContest should have either Color or"
        " Colors.DarkThemeColor and Colors.LightThemeColor set.",
    )

  def test_contest_with_parties_with_duplicate_colors_warns(self):
    test_string = self.root_string.format(
        self._color_template.format("ff0000"),
        self._color_template.format("ff0000"),
        self._color_template.format("ff0000"),
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Parties have the same Color ff0000.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)
    duplicated_parties = [
        context.exception.log_entry[0].elements[0].get("objectId"),
        context.exception.log_entry[0].elements[1].get("objectId"),
    ]
    self.assertEqual(duplicated_parties, ["par0001", "par0002"])

  def test_contest_with_parties_with_unique_colors_succeeds(self):
    test_string = self.root_string.format(
        self._color_template.format("ff0000"),
        self._color_template.format("0000ff"),
        self._color_template.format("ff0000"),
    )
    election_tree = etree.fromstring(test_string)

    election_rules.ValidateDuplicateColors(election_tree, None).check()

  def test_contest_with_parties_with_duplicate_dark_theme_colors_warns(self):
    test_string = self.root_string.format(
        self._colors_template.format(
            dark_theme_color="ff0000",
            light_theme_color="0000ff",
        ),
        self._colors_template.format(
            dark_theme_color="FF0000",
            light_theme_color="00ff00",
        ),
        self._color_template.format("000000"),
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Parties have the same DarkThemeColor ff0000.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)
    duplicated_parties = [
        context.exception.log_entry[0].elements[0].get("objectId"),
        context.exception.log_entry[0].elements[1].get("objectId"),
    ]
    self.assertEqual(duplicated_parties, ["par0001", "par0002"])

  def test_contest_with_parties_with_duplicate_light_theme_colors_warns(self):
    test_string = self.root_string.format(
        self._colors_template.format(
            dark_theme_color="0000ff",
            light_theme_color="ff0000",
        ),
        self._colors_template.format(
            dark_theme_color="00ff00",
            light_theme_color="FF0000",
        ),
        self._color_template.format("000000"),
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      election_rules.ValidateDuplicateColors(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Parties have the same LightThemeColor ff0000.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)
    duplicated_parties = [
        context.exception.log_entry[0].elements[0].get("objectId"),
        context.exception.log_entry[0].elements[1].get("objectId"),
    ]
    self.assertEqual(duplicated_parties, ["par0001", "par0002"])

  def test_contest_with_parties_with_unique_dark_and_light_theme_colors_succeeds(
      self,
  ):
    test_string = self.root_string.format(
        self._colors_template.format(
            dark_theme_color="000000",
            light_theme_color="111111",
        ),
        self._colors_template.format(
            dark_theme_color="222222",
            light_theme_color="333333",
        ),
        self._colors_template.format(
            dark_theme_color="444444",
            light_theme_color="555555",
        ),
    )
    election_tree = etree.fromstring(test_string)

    election_rules.ValidateDuplicateColors(election_tree, None).check()


class MultipleCandidatesPointToTheSamePersonInTheSameContestTest(
    absltest.TestCase
):

  base_string_multiple_contest = """
    <Election xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <CandidateCollection>
            <Candidate objectId="can1">
              <PersonId>{personid1}</PersonId>
            </Candidate>
            <Candidate objectId="can2">
              <PersonId>{personid2}</PersonId>
            </Candidate>
            <Candidate objectId="can3">
              <PersonId>{personid3}</PersonId>
            </Candidate>
            <Candidate objectId="can4">
              <PersonId>{personid4}</PersonId>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest xsi:type="CandidateContest" objectId="contest1">
              <BallotSelection xsi:type="CandidateSelection" objectId="cs1">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
              <BallotSelection xsi:type="CandidateSelection" objectId="cs2">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
              <BallotSelection xsi:type="CandidateSelection" objectId="cs3">
                <CandidateIds>can3</CandidateIds>
              </BallotSelection>
            </Contest>
            <Contest xsi:type="CandidateContest" objectId="contest2">
              <BallotSelection xsi:type="CandidateSelection" objectId="cs2b">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
              <BallotSelection xsi:type="CandidateSelection" objectId="cs3b">
                <CandidateIds>can3</CandidateIds>
              </BallotSelection>
              <BallotSelection xsi:type="CandidateSelection" objectId="cs4b">
                <CandidateIds>can4</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
    """

  def test_valid_multiple_candidates_not_point_to_the_same_person_in_same_contest_succeeds(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per3", personid4="per4"
    )
    election_tree = etree.fromstring(test_string)
    validator = (
        election_rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
            election_tree, None
        )
    )

    validator.check()

  def test_invalid_multiple_candidates_point_to_the_same_person_in_same_contest_fails(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per3", personid4="per3"
    )
    election_tree = etree.fromstring(test_string)
    validator = (
        election_rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
            election_tree, None
        )
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn(
        (
            "Multiple candidates in Contest contest2 reference the same Person"
            " per3. Candidates: ['can3', 'can4']"
        ),
        context.exception.log_entry[0].message,
    )

  def test_valid_multiple_candidates_different_person_in_different_contest_succeeds(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per3", personid4="per1"
    )
    election_tree = etree.fromstring(test_string)
    validator = (
        election_rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
            election_tree, None
        )
    )

    validator.check()

  def test_invalid_multiple_candidates_point_to_the_same_person_in_same_contest_with_two_contests_fails(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per1", personid4="per1"
    )
    election_tree = etree.fromstring(test_string)
    validator = (
        election_rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
            election_tree, None
        )
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn(
        (
            "Multiple candidates in Contest contest1 reference the same Person"
            " per1. Candidates: ['can1', 'can3']"
        ),
        context.exception.log_entry[0].message,
    )
    self.assertIn(
        (
            "Multiple candidates in Contest contest2 reference the same Person"
            " per1. Candidates: ['can3', 'can4']"
        ),
        context.exception.log_entry[1].message,
    )


class SelfDeclaredCandidateMethodTest(absltest.TestCase):

  def setUp(self):
    super(SelfDeclaredCandidateMethodTest, self).setUp()
    self.validator = election_rules.SelfDeclaredCandidateMethod(None, None)

  def test_valid_candidate_method_succeeds(self):
    self_declared_method = """
        <Candidate objectId="can-1001-kenyatta">
          <BallotName>
            <Text language="en">Uhuru Kenyatta</Text>
            <Text language="sw">Uhuru Kenyatta</Text>
          </BallotName>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>can-per-100</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
          <IsIncumbent>1</IsIncumbent>
          <IsTopTicket>1</IsTopTicket>
          <PartyId>par-jubilee</PartyId>
          <PersonId>per-001-kenyatta</PersonId>
          <PostElectionStatus>projected-winner</PostElectionStatus>
          <PreElectionStatus>self-declared</PreElectionStatus>
        </Candidate>
    """

    self.validator.check(etree.fromstring(self_declared_method))

  def test_valid_qualified_check_method_succeeds(self):
    self_declared_method = """
        <Candidate objectId="can-1001-kenyatta">
          <BallotName>
            <Text language="en">Uhuru Kenyatta</Text>
            <Text language="sw">Uhuru Kenyatta</Text>
          </BallotName>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>electoral-commission</OtherType>
              <Value>can-per-100</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
          <IsIncumbent>1</IsIncumbent>
          <IsTopTicket>1</IsTopTicket>
          <PartyId>par-jubilee</PartyId>
          <PersonId>per-001-kenyatta</PersonId>
          <PostElectionStatus>projected-winner</PostElectionStatus>
          <PreElectionStatus>qualified</PreElectionStatus>
        </Candidate>
    """

    self.validator.check(etree.fromstring(self_declared_method))

  def test_invalid_candidate_method_warns(self):
    self_declared_method = """
        <Candidate objectId="can-1001-kenyatta">
          <BallotName>
            <Text language="en">Uhuru Kenyatta</Text>
            <Text language="sw">Uhuru Kenyatta</Text>
          </BallotName>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>can-per-100</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>electoral-commission</OtherType>
              <Value>H2NY22097</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
          <IsIncumbent>1</IsIncumbent>
          <IsTopTicket>1</IsTopTicket>
          <PartyId>par-jubilee</PartyId>
          <PersonId>per-001-kenyatta</PersonId>
          <PostElectionStatus>projected-winner</PostElectionStatus>
          <PreElectionStatus>self-declared</PreElectionStatus>
        </Candidate>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(self_declared_method))
    self.assertIn(
        "A self declared candidate cannot have an electoral-commission id."
        " Please update the candidate Pre election Status.",
        context.exception.log_entry[0].message,
    )


class DuplicatedPartyAbbreviationTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyAbbreviationTest, self).setUp()
    self.validator = election_rules.DuplicatedPartyAbbreviation(None, None)

  def test_party_collection_without_party_raises_info(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<PartyCollection> does not have <Party> objects",
    )

  def test_party_without_internationalized_abbreviation_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<Party> does not have <InternationalizedAbbreviation> objects",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "par0001"
    )

  def test_duplicate_internationalized_abbreviation_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Parties have the same abbreviation in en.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)
    duplicated_parties = [
        context.exception.log_entry[0].elements[0].get("objectId"),
        context.exception.log_entry[0].elements[1].get("objectId"),
    ]
    self.assertEqual(duplicated_parties, ["par0001", "par0003"])

  def test_no_duplicated_internationalized_abbreviation_succeeds(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Green</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)


class DuplicatedPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyNameTest, self).setUp()
    self.validator = election_rules.DuplicatedPartyName(None, None)

  def test_party_collection_without_party_raises_info(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<PartyCollection> does not have <Party> objects",
    )

  def test_party_without_name_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<Party> does not have <Name> objects",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "par0001",
    )

  def test_duplicate_party_name_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Parties have the same name in en.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)
    duplicated_parties = [
        context.exception.log_entry[0].elements[0].get("objectId"),
        context.exception.log_entry[0].elements[1].get("objectId"),
    ]
    self.assertEqual(duplicated_parties, ["par0001", "par0003"])

  def test_unique_party_name_succeeds(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Green</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)


class MissingPartyNameTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyNameTranslationTest, self).setUp()
    self.validator = election_rules.MissingPartyNameTranslation(None, None)

  def test_party_collection_without_party_raises_info(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<PartyCollection> does not have <Party> objects",
    )

  def test_party_without_name_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<Party> does not have <Name> objects",
    )

  def test_missing_translation_at_the_beginning_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratico</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "The feed is missing names translation to ro for parties "
            ": {'par0001'}."
        ),
    )

  def test_missing_translation_in_the_middle_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertIn(
        "The party name is not translated to all feed languages",
        context.exception.log_entry[0].message,
    )
    self.assertIn("en", context.exception.log_entry[0].message)
    self.assertIn("ro", context.exception.log_entry[0].message)
    self.assertIn(
        "You did it only for the following languages : {'en'}.",
        context.exception.log_entry[0].message,
    )

  def test_with_all_good_translation_succeeds(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)


class MissingPartyAbbreviationTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyAbbreviationTranslationTest, self).setUp()
    self.validator = election_rules.MissingPartyAbbreviationTranslation(
        None, None
    )

  def test_party_collection_without_party_raises_info(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<PartyCollection> does not have <Party> objects",
    )

  def test_party_without_internationalized_abbreviation_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<Party> does not have <InternationalizedAbbreviation> objects",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "par0001"
    )

  def test_missing_translation_at_the_beginning_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratico</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "The feed is missing abbreviation translation to ro for "
            "parties : {'par0001'}."
        ),
    )

  def test_missing_translation_in_the_middle_raises_info(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertIn(
        "The party abbreviation is not translated to all feed languages ",
        context.exception.log_entry[0].message,
    )
    self.assertIn("en", context.exception.log_entry[0].message)
    self.assertIn("ro", context.exception.log_entry[0].message)
    self.assertIn(
        "You only did it for the following languages : {'en'}.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "par0002"
    )

  def test_with_all_good_translation_succeeds(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)


class DuplicateContestNamesTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateContestNamesTest, self).setUp()
    self.validator = election_rules.DuplicateContestNames(None, None)
    self._base_report = """
          <ContestCollection>
            <Contest objectId="cc11111">
              {}
            </Contest>
            <Contest objectId="cc22222">
              {}
            </Contest>
            <Contest objectId="cc33333">
              {}
            </Contest>
          </ContestCollection>
    """

  def test_every_contest_has_a_unique_name_succeeds(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    tres = "<Name>Treasurer</Name>"
    root_string = self._base_report.format(pres, sec, tres)
    election_tree = etree.fromstring(root_string)

    self.validator.check(election_tree)

  def test_contest_is_missing_name_or_name_is_empty_missing_fails(
      self,
  ):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    root_string = self._base_report.format(pres, sec, "")
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(election_tree)

  def test_contest_is_missing_name_or_name_is_empty_empty_fails(
      self,
  ):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    empty = "<Name></Name>"
    root_string = self._base_report.format(pres, sec, empty)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(election_tree)

  def test_name_is_not_unique_fails(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    duplicate = "<Name>President</Name>"
    root_string = self._base_report.format(pres, sec, duplicate)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(election_tree)


class DuplicateBallotTitleSeatPairTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateBallotTitleSeatPairTest, self).setUp()
    self.duplicate_validator = election_rules.DuplicateBallotTitleSeatPair(
        None, None
    )
    self._base_report = """
          <ContestCollection>
            <Contest objectId="cc0001">
              {}
            </Contest>
            <Contest objectId="cc0002">
              {}
            </Contest>
            <Contest objectId="cc0003">
              {}
            </Contest>
          </ContestCollection>
    """

  def testEveryBallotTitleSeatPairIsUniqueBySeat(self):
    seat1 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat different1</Seat>
    """
    seat2 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat different2</Seat>
    """
    seat3 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat different3</Seat>
    """
    root_string = self._base_report.format(seat1, seat2, seat3)
    election_tree = etree.fromstring(root_string)
    self.duplicate_validator.check(election_tree)

  def testEveryBallotTitleSeatPairIsUniqueByBallotTitle(self):
    seat1 = """
        <BallotTitle>
            <Text language="en">Ballot Title different1</Text>
        </BallotTitle>
        <Seat>seat same</Seat>
    """
    seat2 = """
        <BallotTitle>
            <Text language="en">Ballot Title different2</Text>
        </BallotTitle>
        <Seat>seat same</Seat>
    """
    seat3 = """
        <BallotTitle>
            <Text language="en">Ballot Title different3</Text>
        </BallotTitle>
        <Seat>seat same</Seat>
    """
    root_string = self._base_report.format(seat1, seat2, seat3)
    election_tree = etree.fromstring(root_string)
    self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfBallotTitleSeatPairIsDuplicated(self):
    seat1 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat1</Seat>
    """
    seat2 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>duplicate seat</Seat>
    """
    seat_dupelicate = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>duplicate seat</Seat>
    """
    root_string = self._base_report.format(seat1, seat2, seat_dupelicate)
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionError):
      self.duplicate_validator.check(election_tree)

  def testEmptyBallotTitleAndSeatIsValid(self):
    seat1 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat1</Seat>
    """
    seat2 = """

    """
    seat3 = """

    """
    root_string = self._base_report.format(seat1, seat2, seat3)
    election_tree = etree.fromstring(root_string)
    self.duplicate_validator.check(election_tree)

  def testEmptyBallotTitleButDuplicateSeatIsValid(self):
    seat1 = """
        <BallotTitle>
            <Text language="en">Ballot Title same</Text>
        </BallotTitle>
        <Seat>seat1</Seat>
    """
    seat2 = """
        <Seat>duplicate seat</Seat>
    """
    seat3 = """
        <Seat>duplicate seat</Seat>
    """
    root_string = self._base_report.format(seat1, seat2, seat3)
    election_tree = etree.fromstring(root_string)
    self.duplicate_validator.check(election_tree)


class ContestHasMultipleOfficesTest(absltest.TestCase):

  base_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con123" xsi:type="CandidateContest">
                {}
             </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
   """

  def setUp(self):
    super(ContestHasMultipleOfficesTest, self).setUp()
    self.validator = election_rules.ContestHasMultipleOffices(None, None)

  def test_one_office_valid_succeeds(self):
    root_string = self.base_string.format("<OfficeIds>off-ar1-arb</OfficeIds>")
    element = etree.fromstring(root_string)

    self.validator.check(element.find("Election//ContestCollection//Contest"))

  def test_multiple_offices_fail_warns(self):
    root_string = self.base_string.format(
        "<OfficeIds>off-ar1-ara off-ar1-arb</OfficeIds>"
    )
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element.find("Election//ContestCollection//Contest"))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest has more than one associated office.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "con123",
    )

  def test_no_offices_fail_warns(self):
    root_string = self.base_string.format("<OfficeIds></OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element.find("Election//ContestCollection//Contest"))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest has no associated offices.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "con123",
    )


class VoteCountTypesCoherencyTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountTypesCoherencyTest, self).setUp()
    self.validator = election_rules.VoteCountTypesCoherency(None, None)
    self.base_contest = """
      <Contest objectId="pc1" type="{}">
        <BallotSelection objectId="ps1-0">
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def test_invalid_not_in_party_contest_succeeds(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-leading</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("PartyContest", vote_counts)

    self.validator.check(etree.fromstring(contest))

  def test_invalid_not_in_party_contest_fails(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>candidate-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("PartyContest", vote_counts)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    for vc_type in election_rules.VoteCountTypesCoherency.CAND_VC_TYPES:
      self.assertIn(vc_type, context.exception.log_entry[0].message)

  def test_invalid_not_in_candidate_contest_succeeds(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>candidate-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)

    self.validator.check(etree.fromstring(contest))

  def test_non_invalid_vc_types_succeeds(self):
    # returns None if no VoteCount types
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>some-future-vote-count-type</OtherType>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)

    self.assertIsNone(self.validator.check(etree.fromstring(contest)))

  def test_invalid_not_in_candidate_contest_fails(self):
    # Checks Candidate parsing fails on all party types
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-won</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-leading</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>party-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-no-election</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-total</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta-mandate</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta-institutional</OtherType>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    for vc_type in election_rules.VoteCountTypesCoherency.PARTY_VC_TYPES:
      self.assertIn(vc_type, context.exception.log_entry[0].message)
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "pc1"
    )


class VoteCountValidSeatsDeltaTypesTest(parameterized.TestCase):

  def setUp(self):
    super(VoteCountValidSeatsDeltaTypesTest, self).setUp()
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="AggregateBallotSelection" type="SpecialBallotSelection"/>
        <xs:element name="BlankBallotSelection" type="SpecialBallotSelection"/>
        <xs:element name="NoneOfTheAboveBallotSelection" type="SpecialBallotSelection"/>
        <xs:element name="NullBallotSelection" type="SpecialBallotSelection"/>
      </xs:schema>
    """)
    self.validator = election_rules.VoteCountValidSeatsDeltaTypes(
        None, schema_tree
    )

  def test_elements_returns_expected_elements(self):
    self.assertCountEqual(
        self.validator.elements(),
        [
            "BallotSelection",
            "AggregateBallotSelection",
            "BlankBallotSelection",
            "NoneOfTheAboveBallotSelection",
            "NullBallotSelection",
        ],
    )

  def test_multiple_seats_delta_types_succeeds(self):
    ballot_selection = """
      <BallotSelection objectId="bs-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>seats-delta-mandate</OtherType>
            <Type>other</Type>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-delta-institutional</OtherType>
            <Type>other</Type>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    """

    self.validator.check(etree.fromstring(ballot_selection))

  @parameterized.parameters("seats-delta-mandate", "seats-delta-institutional")
  def test_single_valid_seats_delta_type_succeeds(self, seats_delta_type):
    ballot_selection = f"""
      <BallotSelection objectId="bs-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>{seats_delta_type}</OtherType>
            <Type>other</Type>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    """

    self.validator.check(etree.fromstring(ballot_selection))

  @parameterized.parameters(
      "BallotSelection",
      "AggregateBallotSelection",
      "BlankBallotSelection",
      "NoneOfTheAboveBallotSelection",
      "NullBallotSelection",
  )
  def test_legacy_seats_delta_type_fails(self, selection_tag):
    ballot_selection = f"""
      <{selection_tag} objectId="bs-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>seats-delta</OtherType>
            <Type>other</Type>
          </VoteCounts>
        </VoteCountsCollection>
      </{selection_tag}>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(ballot_selection))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Legacy VoteCounts type seats-delta is no longer supported as of"
        " July 1, 2026. Please update your implementation to use"
        " seats-delta-mandate and/or seats-delta-institutional.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "bs-0"
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, selection_tag
    )

  def test_valid_other_vote_count_types_succeeds(self):
    ballot_selection = """
      <BallotSelection objectId="bs-0">
        <VoteCountsCollection>
          <VoteCounts>
            <Type>total</Type>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-total</OtherType>
            <Type>other</Type>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    """

    self.validator.check(etree.fromstring(ballot_selection))

  def test_no_vote_counts_collection_succeeds(self):
    ballot_selection = '<BallotSelection objectId="bs-0" />'

    self.validator.check(etree.fromstring(ballot_selection))


class OfficeHasjurisdictionSameAsElectoralDistrictTest(absltest.TestCase):

  def setUp(self):
    super(OfficeHasjurisdictionSameAsElectoralDistrictTest, self).setUp()
    self.validator = (
        election_rules.OfficeHasjurisdictionSameAsElectoralDistrict(None, None)
    )

  def test_valid_jurisdiction_and_electoral_district_succeeds(self):
    test_string = """
          <Office objectId="off2">
            <ElectoralDistrictId>gp1222</ElectoralDistrictId>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>gp1222</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_invalid_jurisdiction_and_electoral_district_raises_info(self):
    test_string = """
          <Office objectId="off2">
            <ElectoralDistrictId>gp1222</ElectoralDistrictId>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>gp1234</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has electoral district different from jurisdiction.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )


class ContestHasValidContestStageTest(absltest.TestCase):

  def setUp(self):
    super(ContestHasValidContestStageTest, self).setUp()
    self.validator = election_rules.ContestHasValidContestStage(None, None)

  def test_contest_has_valid_contest_stage_succeeds(self):
    root_string = """
     <Contest objectId="con-1">
       <ExternalIdentifier>
         <Type>other</Type>
         <OtherType>contest-stage</OtherType>
         <Value>preliminary</Value>
       </ExternalIdentifier>
      </Contest>
      """

    self.validator.check(etree.fromstring(root_string))

  def test_contest_has_invalid_contest_stage_fails(self):
    root_string = """
     <Contest objectId="con-2">
       <ExternalIdentifier>
         <Type>other</Type>
         <OtherType>contest-stage</OtherType>
         <Value>invalidconteststage</Value>
       </ExternalIdentifier>
      </Contest>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The contest has invalid contest-stage 'invalidconteststage'.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "con-2"
    )


class GpUnitsHaveSingleRootTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveSingleRootTest, self).setUp()
    self.validator = election_rules.GpUnitsHaveSingleRoot(None, None)

  def test_single_root_valid_succeeds(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru000us">
          <ComposingGpUnitIds>ru_pre92426</ComposingGpUnitIds>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us</Value>
          </ExternalIdentifier>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ve</Value>
          </ExternalIdentifier>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ve/county:narok</Value>
          </ExternalIdentifier>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string)
    )

    self.validator.check()

  def test_multiple_root_tree_valid_succeeds(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru_germany">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:de</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>national-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
        <GpUnit objectId="ru000us">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:us</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>national-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:de/state:dh</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>state-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string)
    )

    self.validator.check()

  def test_multiple_root_tree_fails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru_germany">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:de</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>national-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:abc</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>national-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>stable-gu-0081</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              <Value>ocd-division/country:us/state:tx</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>state-level</Type>
              <Value>33</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string)
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check()
    self.assertIn(
        "GpUnits tree roots needs to be either a country or the EU region, "
        "please check the value ocd-division/country:abc.",
        context.exception.log_entry[0].message,
    )

  def test_no_roots_tree_fails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0003">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru0003</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ComposingGpUnitIds>ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string)
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check()
    self.assertIn(
        "GpUnits have no geo district root.",
        context.exception.log_entry[0].message,
    )


class ElectionContainsStartAndEndDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionContainsStartAndEndDatesTest, self).setUp()
    self.validator = election_rules.ElectionContainsStartAndEndDates(None, None)

  def test_election_with_missing_start_date_fails(self):
    election_string = """
      <Election objectId="election-1">
        <EndDate>2023-05-30</EndDate>
        <ContestCollection>
          <Contest objectId="contest-1" type="CandidateContest">
            <OfficeIds>office-1</OfficeIds>
            <StartDate>2023-05-20</StartDate>
            <EndDate>2023-05-30</EndDate>
          </Contest>
        </ContestCollection>
      </Election>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Election election-1 is missing a start date.",
    )

  def test_election_with_missing_end_date_fails(self):
    election_string = """
      <Election objectId="election-1">
        <StartDate>2023-05-20</StartDate>
        <ContestCollection>
          <Contest objectId="contest-1" type="CandidateContest">
            <OfficeIds>office-1</OfficeIds>
            <StartDate>2023-05-20</StartDate>
            <EndDate>2023-05-30</EndDate>
          </Contest>
        </ContestCollection>
      </Election>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Election election-1 is missing an end date.",
    )

  def test_election_with_start_and_end_dates_succeeds(self):
    election_string = """
      <Election objectId="election-1">
        <StartDate>2023-05-20</StartDate>
        <EndDate>2023-05-30</EndDate>
        <ContestCollection>
          <Contest objectId="contest-1" type="CandidateContest">
            <OfficeIds>office-1</OfficeIds>
            <StartDate>2023-05-30</StartDate>
            <EndDate>2023-05-30</EndDate>
          </Contest>
        </ContestCollection>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))
    self.assertEmpty(self.validator.error_log)


class ElectionStartDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionStartDatesTest, self).setUp()
    self.validator = election_rules.ElectionStartDates(None, None)
    self.today = datetime.datetime.now(datetime.timezone.utc).date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def test_election_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Election"])

  def test_start_dates_are_not_flagged_if_not_in_the_past_succeeds(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2),
    )
    election = etree.fromstring(election_string)

    self.validator.check(election)

  def test_a_warning_is_thrown_if_start_date_is_in_past_warns(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=-1),
        self.today + datetime.timedelta(days=2),
    )
    election = etree.fromstring(election_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(election)

  def test_elections_with_no_start_date_element_succeeds(self):
    election_string = """
      <Election></Election>
    """

    self.validator.check(etree.fromstring(election_string))


class ElectionEndDatesInThePastTest(absltest.TestCase):

  def setUp(self):
    super(ElectionEndDatesInThePastTest, self).setUp()
    self.validator = election_rules.ElectionEndDatesInThePast(None, None)
    self.today = datetime.datetime.now(datetime.timezone.utc).date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  @freezegun.freeze_time("2022-01-01")
  def test_subsequent_contest_id_is_not_present_end_date_not_in_past_succeeds(
      self,
  ):
    election_string = """
      <Election>
        <ContestCollection>
          <Contest objectId="cc_fr_999_2"/>
        </ContestCollection>
        <StartDate>2012-01-01</StartDate>
        <EndDate>2023-01-01</EndDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))

  def test_subsequent_contest_id_is_not_present_end_date_in_past_warns(self):
    election_string = """
        <Election>
          <ContestCollection>
            <Contest objectId="cc_fr_999_2"/>
          </ContestCollection>
          <StartDate>2012-01-01</StartDate>
          <EndDate>2018-01-01</EndDate>
        </Election>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertIn(
        "The date 2018-01-01 is in the past",
        context.exception.log_entry[0].message,
    )

  def test_subsequent_contest_id_is_present_end_date_in_past_succeeds(self):
    election_string = """
        <Election>
          <ContestCollection>
            <Contest objectId="cc_fr_999_2">
              <SubsequentContestId>cc_fr_999_3</SubsequentContestId>
            </Contest>
          </ContestCollection>
          <StartDate>2012-01-01</StartDate>
          <EndDate>2018-01-01</EndDate>
        </Election>
    """

    self.validator.check(etree.fromstring(election_string))

  @freezegun.freeze_time("2022-01-01")
  def test_subsequent_contest_id_is_present_end_date_not_in_past_succeeds(self):
    election_string = """
        <Election>
          <ContestCollection>
            <Contest objectId="cc_fr_999_2">
              <SubsequentContestId>cc_fr_999_3</SubsequentContestId>
            </Contest>
          </ContestCollection>
          <StartDate>2012-01-01</StartDate>
          <EndDate>2023-03-01</EndDate>
        </Election>
    """

    self.validator.check(etree.fromstring(election_string))

  @freezegun.freeze_time("2022-01-01")
  def test_bounded_election_end_date_not_in_past_succeeds(self):
    election_string = """
      <Election>
        <ElectionDateType>bounded</ElectionDateType>
        <StartDate>2012-01-01</StartDate>
        <EndDate>2023-01-01</EndDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))

  def test_bounded_election_end_date_in_past_fails(self):
    election_string = """
      <Election>
        <ElectionDateType>bounded</ElectionDateType>
        <StartDate>2012-01-01</StartDate>
        <EndDate>2018-01-01</EndDate>
      </Election>
    """

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(election_string))

  def test_bounded_election_end_date_in_past_canceled_election_succeeds(self):
    election_string = """
      <Election>
        <ElectionDateType>bounded</ElectionDateType>
        <ElectionDateStatus>canceled</ElectionDateStatus>
        <StartDate>2012-01-01</StartDate>
        <EndDate>2023-01-01</EndDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))

  def test_bounded_election_end_date_in_past_postponed_election_succeeds(self):
    election_string = """
      <Election>
        <ElectionDateType>bounded</ElectionDateType>
        <ElectionDateStatus>postponed</ElectionDateStatus>
        <StartDate>2012-01-01</StartDate>
        <EndDate>2023-01-01</EndDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))


class ElectionEndDatesOccurAfterStartDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionEndDatesOccurAfterStartDatesTest, self).setUp()
    self.validator = election_rules.ElectionEndDatesOccurAfterStartDates(
        None, None
    )
    self.today = datetime.datetime.now(datetime.timezone.utc).date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def test_election_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Election"])

  def test_end_dates_are_not_flagged_if_the_order_is_right_succeeds(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2),
    )
    election = etree.fromstring(election_string)

    self.validator.check(election)

  def test_an_error_is_thrown_if_end_date_is_before_start_date_fails(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=2),
        self.today + datetime.timedelta(days=1),
    )
    election = etree.fromstring(election_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(election)

  def test_elections_with_no_end_date_element_succeeds(self):
    election_string = """
      <Election>
        <StartDate>2012-01-01</StartDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election_string))


class ElectionDatesSpanContestDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionDatesSpanContestDatesTest, self).setUp()
    self.validator = election_rules.ElectionDatesSpanContestDates(None, None)

  def test_election_with_no_dates_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_elections_with_missing_dates_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-30</StartDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
            </Contest>
          </ContestCollection>
        </Election>
        <Election objectId="election-2">
          <EndDate>2023-05-20</EndDate>
          <ContestCollection>
            <Contest objectId="contest-2" xsi:type="CandidateContest">
              <OfficeIds>office-2</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_election_with_no_contest_dates_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-30</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_election_with_contest_missing_end_date_fails(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <StartDate>2023-05-19</StartDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest contest-1 with start date 2023-05-19 occurs before Election"
        " election-1 with start date 2023-05-20. Election start date should be"
        " on or before any Contest start date.",
    )

  def test_election_with_contest_missing_start_date_fails(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <EndDate>2023-05-31</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest contest-1 with end date 2023-05-31 occurs after Election"
        " election-1 with end date 2023-05-30. Election end date should be on"
        " or after any Contest end date.",
    )

  def test_election_with_invalid_contest_start_date_fails(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-30</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest contest-1 with start date 2023-05-19 occurs before Election"
        " election-1 with start date 2023-05-20. Election start date should be"
        " on or before any Contest start date.",
    )

  def test_election_with_invalid_contest_end_date_fails(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <StartDate>2023-05-20</StartDate>
              <EndDate>2023-05-31</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest contest-1 with end date 2023-05-31 occurs after Election"
        " election-1 with end date 2023-05-30. Election end date should be on"
        " or after any Contest end date.",
    )

  def test_election_with_canceled_contest_end_date_after_than_election_end_date_succeeds(
      self,
  ):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <ContestDateStatus>canceled</ContestDateStatus>
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <StartDate>2023-05-20</StartDate>
              <EndDate>2023-05-31</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_election_with_valid_contest_dates_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <StartDate>2023-05-20</StartDate>
          <EndDate>2023-05-30</EndDate>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <OfficeIds>office-1</OfficeIds>
              <PrimaryPartyIds>party-1</PrimaryPartyIds>
              <StartDate>2023-05-21</StartDate>
              <EndDate>2023-05-30</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)


class ElectionTypesTest(absltest.TestCase):

  def test_election_types_incompatible_primary_fails(self):
    election_string = """
      <Election>
        <Type>primary</Type>
        <Type>general</Type>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      election_rules.ElectionTypesAreCompatible(None, None).check(
          etree.fromstring(election_string)
      )
    self.assertIn(
        "Election element has incompatible election-type values.",
        context.exception.log_entry[0].message,
    )

  def test_election_types_incompatible_partisan_primary_open_fails(
      self,
  ):
    election_string = """
      <Election>
        <Type>partisan-primary-open</Type>
        <Type>general</Type>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      election_rules.ElectionTypesAreCompatible(None, None).check(
          etree.fromstring(election_string)
      )
    self.assertIn(
        "Election element has incompatible election-type values.",
        context.exception.log_entry[0].message,
    )

  def test_election_types_incompatible_partisan_primary_closed_fails(
      self,
  ):
    election_string = """
      <Election>
        <Type>partisan-primary-closed</Type>
        <Type>general</Type>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      election_rules.ElectionTypesAreCompatible(None, None).check(
          etree.fromstring(election_string)
      )
    self.assertIn(
        "Election element has incompatible election-type values.",
        context.exception.log_entry[0].message,
    )

  def test_allows_if_election_types_compatible_succeeds(self):
    election_string = """
      <Election>
        <Type>general</Type>
        <Type>runoff</Type>
      </Election>
      """

    election_rules.ElectionTypesAreCompatible(None, None).check(
        etree.fromstring(election_string)
    )


class ElectionTypesAndCandidateContestTypesAreCompatibleTest(absltest.TestCase):

  def setUp(self):
    super(ElectionTypesAndCandidateContestTypesAreCompatibleTest, self).setUp()
    self.validator = (
        election_rules.ElectionTypesAndCandidateContestTypesAreCompatible(
            None, None
        )
    )

  def test_election_includes_contest_with_no_types_succeeds(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <Type>primary</Type>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Contest with Missing Type</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election = etree.fromstring(election_report_string).find("Election")

    self.validator.check(election)

  def test_general_election_with_primary_contest_fails(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <Type>general</Type>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Primary Contest</Name>
              <Type>partisan-primary-closed</Type>
              <Type>runoff</Type>
            </Contest>
            <Contest objectId="contest-2" xsi:type="CandidateContest">
              <Name>Special General Contest</Name>
              <Type>special</Type>
              <Type>general</Type>
            </Contest>
            <Contest objectId="contest-3" xsi:type="BallotMeasureContest">
              <Name>Ballot Measure Contest</Name>
              <Type>ballot-measure</Type>
            </Contest>
            <Contest objectId="contest-4" xsi:type="PartyContest">
              <Name>Party Contest</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election = etree.fromstring(election_report_string).find("Election")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(election)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Election election-1 includes CandidateContest contest-1 with"
        " incompatible type(s). General elections cannot include primary"
        " contests.",
    )

  def test_primary_election_with_general_contest_fails(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <Type>special</Type>
          <Type>primary</Type>
          <Type>runoff</Type>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>General Runoff Contest</Name>
              <Type>general</Type>
              <Type>runoff</Type>
            </Contest>
            <Contest objectId="contest-2" xsi:type="CandidateContest">
              <Name>Open Primary Contest</Name>
              <Type>partisan-primary-open</Type>
            </Contest>
            <Contest objectId="contest-3" xsi:type="CandidateContest">
              <Name>Closed Primary Contest</Name>
              <Type>partisan-primary-closed</Type>
            </Contest>
            <Contest objectId="contest-4" xsi:type="CandidateContest">
              <Name>Primary Contest</Name>
              <Type>primary</Type>
            </Contest>
            <Contest objectId="contest-5" xsi:type="BallotMeasureContest">
              <Name>Ballot Measure Contest</Name>
              <Type>ballot-measure</Type>
            </Contest>
            <Contest objectId="contest-6" xsi:type="PartyContest">
              <Name>Party Contest</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election = etree.fromstring(election_report_string).find("Election")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(election)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Election election-1 includes CandidateContest contest-1 with"
        " incompatible type(s). Primary elections cannot include general"
        " contests.",
    )

  def test_primary_election_with_primary_contests_succeeds(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <Type>primary</Type>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Open Primary Contest</Name>
              <Type>partisan-primary-open</Type>
            </Contest>
            <Contest objectId="contest-2" xsi:type="CandidateContest">
              <Name>Closed Primary Contest</Name>
              <Type>partisan-primary-closed</Type>
            </Contest>
            <Contest objectId="contest-3" xsi:type="CandidateContest">
              <Name>Primary Contest</Name>
              <Type>primary</Type>
            </Contest>
            <Contest objectId="contest-4" xsi:type="BallotMeasureContest">
              <Name>Ballot Measure Contest</Name>
              <Type>ballot-measure</Type>
            </Contest>
            <Contest objectId="contest-5" xsi:type="PartyContest">
              <Name>Party Contest</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election = etree.fromstring(election_report_string).find("Election")

    self.validator.check(election)

  def test_general_election_with_general_contests_succeeds(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <Type>general</Type>
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>General Contest</Name>
              <Type>general</Type>
            </Contest>
            <Contest objectId="contest-2" xsi:type="CandidateContest">
              <Name>General Runoff Contest</Name>
              <Type>general</Type>
              <Type>runoff</Type>
            </Contest>
            <Contest objectId="contest-3" xsi:type="CandidateContest">
              <Name>Special Runoff Contest</Name>
              <Type>special</Type>
              <Type>runoff</Type>
            </Contest>
            <Contest objectId="contest-4" xsi:type="BallotMeasureContest">
              <Name>Ballot Measure Contest</Name>
              <Type>ballot-measure</Type>
            </Contest>
            <Contest objectId="contest-5" xsi:type="PartyContest">
              <Name>Party Contest</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election = etree.fromstring(election_report_string).find("Election")

    self.validator.check(election)


class DateStatusTest(absltest.TestCase):

  def setUp(self):
    super(DateStatusTest, self).setUp()
    self.validator = election_rules.DateStatusMatches(None, None)
    self.base_report = """
      <Election objectId="el_1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        {}
        <ElectionDateStatus>{}</ElectionDateStatus>
      </Election>
    """
    self.contest_collection = """
      <ContestCollection>
        <Contest xsi:type="CandidateContest">
          <ContestDateStatus>{}</ContestDateStatus>
        </Contest>
        <Contest>
          <ContestDateStatus>{}</ContestDateStatus>
        </Contest>
      </ContestCollection>
    """

  def test_election_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Election"])

  def test_election_with_no_status_succeeds(self):
    self.validator.check(etree.fromstring(self.base_report))

  def test_election_with_no_contests_succeeds(self):
    self.validator.check(
        etree.fromstring(self.base_report.format("", "canceled"))
    )

  def test_election_with_matching_contests_succeeds(self):
    contest_collection = self.contest_collection.format("canceled", "canceled")
    election_report = self.base_report.format(contest_collection, "canceled")

    self.validator.check(etree.fromstring(election_report))

  def test_handles_missing_status_as_confirmed_succeeds(self):
    contest_collection = self.contest_collection.format("confirmed", "")
    election_report = self.base_report.format(contest_collection, "confirmed")

    self.validator.check(etree.fromstring(election_report))

  def test_postponed_election_with_empty_contest_statuses_warns(self):
    contest_collection = self.contest_collection.format("", "")
    election_report = self.base_report.format(contest_collection, "postponed")

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(election_report))
    self.assertIn(
        "All contests on election el_1 have a date status of confirmed, but "
        "the election has a date status of postponed.",
        context.exception.log_entry[0].message,
    )

  def test_confirmed_election_with_canceled_contests_warns(self):
    contest_collection = self.contest_collection.format("canceled", "canceled")
    election_report = self.base_report.format(contest_collection, "confirmed")

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(election_report))
    self.assertIn(
        "All contests on election el_1 have a date status of canceled, but "
        "the election has a date status of confirmed.",
        context.exception.log_entry[0].message,
    )

  def test_contests_with_different_statuses_raises_info(self):
    contest_collection = self.contest_collection.format("confirmed", "canceled")
    election_report = self.base_report.format(contest_collection, "confirmed")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(election_report))
    self.assertIn(
        "There are multiple date statuses present for the contests on "
        "election el_1.  This may be correct, but is an unusal case.  Please "
        "confirm.",
        context.exception.log_entry[0].message,
    )


class ValidateInfoUriAnnotationTest(absltest.TestCase):

  def setUp(self):
    super(ValidateInfoUriAnnotationTest, self).setUp()
    self.validator = election_rules.ValidateInfoUriAnnotation(None, None)

  def test_make_sure_valid_info_uri_succeeds(self):
    contest_string = """
        <InfoUri Annotation="fulltext">
          https://example-government.gov/ballot-measures/California_Proposition_12_2018
        </InfoUri>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_invalid_info_uri_fails(self):
    contest_string = """
        <InfoUri Annotation="logo">
          https://example-government.gov/ballot-measures/California_Proposition_12_2018
        </InfoUri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message, "logo is an invalid annotation."
    )


class FullTextMaxLengthTest(absltest.TestCase):

  def setUp(self):
    super(FullTextMaxLengthTest, self).setUp()
    self.validator = election_rules.FullTextMaxLength(None, None)

  def test_full_text_is_below_limit_succeeds(self):
    contest_string = """
        <FullText>
          <Text language="en">Short full text of a ballot measure</Text>
          <Text language="it">Breve testo completo di un referendum</Text>
        </FullText>
    """
    element = etree.fromstring(contest_string)

    self.validator.check(element)

  def test_full_text_with_no_text_strings_succeeds(self):
    contest_string_no_full_text = """
      <FullText>
      </FullText>
    """
    element = etree.fromstring(contest_string_no_full_text)

    self.validator.check(element)

  def test_text_is_too_long_warns(self):
    contest_string = """
      <FullText>
        <Text language="en">Long text continues...{}</Text>
      </FullText>
        """.format("x" * 30000)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_any_text_is_too_long_warns(self):
    contest_string = """
      <FullText>
        <Text language="en">Short full text of a ballot measure</Text>
        <Text language="es">Long text continues...{}</Text>
      </FullText>
        """.format("x" * 30000)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))


class FullTextOrBallotTextTest(absltest.TestCase):

  def setUp(self):
    super(FullTextOrBallotTextTest, self).setUp()
    self.validator = election_rules.FullTextOrBallotText(None, None)

  def test_ballot_text_with_long_full_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
          <FullText>
            <Text language="en">Long ballot measure text continues... {}</Text>
          </FullText>
        </BallotMeasureContest>
    """.format("x" * 2500)

    self.validator.check(etree.fromstring(contest_string))

  def test_ballot_text_with_short_full_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
          <FullText>
            <Text language="en">Shorter but still valid full measure text</Text>
          </FullText>
        </BallotMeasureContest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_ballot_text_with_no_full_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_ballot_text_element_with_short_full_text_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <FullText>
            <Text language="en">Should the measure be enacted?</Text>
          </FullText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_language_mismatch_with_short_full_text_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
          <FullText>
            <Text language="es">¿Se debe promulgar la medida?</Text>
          </FullText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_language_mismatch_with_long_full_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
          <FullText>
            <Text language="es">El texto de medida continúa...{}</Text>
          </FullText>
        </BallotMeasureContest>
    """.format("x" * 2500)

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_ballot_text_with_short_full_text_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText></BallotText>
          <FullText>
            <Text language="en">Should the measure be enacted?</Text>
          </FullText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_missing_ballot_text_element_with_long_full_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <FullText>
            <Text language="en">Long ballot text continues... {}</Text>
          </FullText>
        </BallotMeasureContest>
    """.format("x" * 2500)

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_ballot_text_and_full_measure_text_elements_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
        </BallotMeasureContest>
    """

    self.validator.check(etree.fromstring(contest_string))


class BallotTitleTest(absltest.TestCase):

  def setUp(self):
    super(BallotTitleTest, self).setUp()
    self.validator = election_rules.BallotTitle(None, None)

  def test_ballot_title_shorter_than_ballot_text_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">State Consitution Minimum Wage Referendum 2020</Text>
          </BallotTitle>
          <BallotText>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_language_mismatch_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">State Consitution Minimum Wage Referendum 2020</Text>
          </BallotTitle>
          <BallotText>
            <Text language="es">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_extra_ballot_text_language_succeeds(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">State Consitution Minimum Wage Referendum 2020</Text>
          </BallotTitle>
          <BallotText>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
            <Text language="es">¿Debería modificarse la constitución estatal para establecer un salario mínimo de $ 12 / hora para 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_extra_ballot_title_language_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">State Consitution Minimum Wage Referendum 2020</Text>
            <Text language="es">Referéndum de Salario Mínimo de la Consorción Estatal 2020</Text>
          </BallotTitle>
          <BallotText>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_ballot_title_includes_ballot_text_warns(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotTitle>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(contest_string))

  def test_missing_ballot_title_fails(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(contest_string))


class ImproperCandidateContestTest(absltest.TestCase):

  _base_report = """
    <xml>
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="CandidateContest">
              <BallotSelection xsi:type="CandidateSelection">
                <CandidateIds>can123</CandidateIds>
              </BallotSelection>
              <BallotSelection xsi:type="CandidateSelection">
                <CandidateIds>can456</CandidateIds>
              </BallotSelection>
             </Contest>
          </ContestCollection>
          <CandidateCollection>
            <Candidate objectId="can123">
              <BallotName>
                <Text language="en">{}</Text>
              </BallotName>
            </Candidate>
            <Candidate objectId="can456">
              <BallotName>
                <Text language="en">{}</Text>
              </BallotName>
            </Candidate>
            <Candidate objectId="can789">
              <BallotName>
                <Text language="es">No</Text>
              </BallotName>
            </Candidate>
          </CandidateCollection>
        </Election>
      </ElectionReport>
    </xml>
  """

  # _gather_contest_candidates test
  def test_list_of_candidate_ids_in_given_contest_succeeds(self):
    contest = """
      <Contest objectId="con987">
        <BallotSelection>
          <CandidateIds>can123 can987</CandidateIds>
        </BallotSelection>
        <BallotSelection>
          <CandidateIds>can456</CandidateIds>
        </BallotSelection>
      </Contest>
    """
    contest_elem = etree.fromstring(contest)
    validator = election_rules.ImproperCandidateContest(None, None)
    expected_ids = ["can123", "can987", "can456"]
    actual_ids = validator._gather_contest_candidates(contest_elem)

    self.assertEqual(expected_ids, actual_ids)

  # _gather_invalid_candidates test
  def test_candidate_ids_that_appear_to_be_ballot_selections_succeeds(
      self,
  ):
    candidate_election = self._base_report.format("Yes", "Larry David")
    root = etree.fromstring(candidate_election)
    validator = election_rules.ImproperCandidateContest(root, None)
    expected_cand = ["can123"]
    actual_cand = validator._gather_invalid_candidates()

    self.assertEqual(expected_cand, actual_cand)

  # check tests
  def test_candidates_dont_have_typical_ballot_selection_options_as_name_succeeds(
      self,
  ):
    candidate_election = self._base_report.format(
        "Jerry Seinfeld", "Larry David"
    )
    root = etree.fromstring(candidate_election)
    validator = election_rules.ImproperCandidateContest(root, None)

    validator.check()

  def test_candidates_with_ballot_selections_options_get_flagged_warns(self):
    candidate_election = self._base_report.format("Yes", "No")
    root = etree.fromstring(candidate_election)
    validator = election_rules.ImproperCandidateContest(root, None)

    with self.assertRaises(loggers.ElectionWarning) as context:
      validator.check()

    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Candidates can123, can456 should be "
            "BallotMeasureSelection elements. Similarly, Contest "
            "con987 should be changed to a BallotMeasureContest "
            "instead of a CandidateContest."
        ),
    )


class WinnerCountLimitTest(absltest.TestCase):

  def test_winner_count_equals_number_elected_succeeds(self):
    election_string = """
      <ElectionReport>
        <Election>
          <CandidateCollection>
            <Candidate objectId="can1">
              <PostElectionStatus>winner</PostElectionStatus>
            </Candidate>
            <Candidate objectId="can2">
              <PostElectionStatus>projected-winner</PostElectionStatus>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest objectId="cc1" type="CandidateContest">
              <NumberElected>2</NumberElected>
              <BallotSelection objectId="bs1" type="CandidateSelection">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
              <BallotSelection objectId="bs2" type="CandidateSelection">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    validator.check(election_tree.find(".//Contest"))

  def test_winner_count_exceeds_number_elected_fails(self):
    election_string = """
      <ElectionReport>
        <Election>
          <CandidateCollection>
            <Candidate objectId="can1">
              <PostElectionStatus>winner</PostElectionStatus>
            </Candidate>
            <Candidate objectId="can2">
              <PostElectionStatus>projected-winner</PostElectionStatus>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest objectId="cc1" type="CandidateContest">
              <NumberElected>1</NumberElected>
              <BallotSelection objectId="bs1" type="CandidateSelection">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
              <BallotSelection objectId="bs2" type="CandidateSelection">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree.find(".//Contest"))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest cc1 has 2 candidates with PostElectionStatus of 'winner' or"
        " 'projected-winner', which exceeds NumberElected: 1.",
    )

  def test_number_elected_is_missing_succeeds(self):
    election_string = """
      <ElectionReport>
        <Election>
          <CandidateCollection>
            <Candidate objectId="can1">
              <PostElectionStatus>winner</PostElectionStatus>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest objectId="cc1" type="CandidateContest">
              <BallotSelection objectId="bs1" type="CandidateSelection">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    validator.check(election_tree.find(".//Contest"))

  def test_number_elected_is_missing_and_winner_count_exceeds_default_fails(
      self,
  ):
    election_string = """
      <ElectionReport>
        <Election>
          <CandidateCollection>
            <Candidate objectId="can1">
              <PostElectionStatus>winner</PostElectionStatus>
            </Candidate>
            <Candidate objectId="can2">
              <PostElectionStatus>projected-winner</PostElectionStatus>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest objectId="cc1" type="CandidateContest">
              <BallotSelection objectId="bs1" type="CandidateSelection">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
              <BallotSelection objectId="bs2" type="CandidateSelection">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree.find(".//Contest"))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest cc1 has 2 candidates with PostElectionStatus of 'winner' or"
        " 'projected-winner', which exceeds NumberElected: 1.",
    )

  def test_non_winner_statuses_succeeds(self):
    election_string = """
      <ElectionReport>
        <Election>
          <CandidateCollection>
            <Candidate objectId="can1">
              <PostElectionStatus>advanced-to-runoff</PostElectionStatus>
            </Candidate>
            <Candidate objectId="can2">
              <PostElectionStatus>withdrawn</PostElectionStatus>
            </Candidate>
            <Candidate objectId="can3">
              <PostElectionStatus>winner</PostElectionStatus>
            </Candidate>
          </CandidateCollection>
          <ContestCollection>
            <Contest objectId="cc1" type="CandidateContest">
              <NumberElected>1</NumberElected>
              <BallotSelection objectId="bs1" type="CandidateSelection">
                <CandidateIds>can1</CandidateIds>
              </BallotSelection>
              <BallotSelection objectId="bs2" type="CandidateSelection">
                <CandidateIds>can2</CandidateIds>
              </BallotSelection>
              <BallotSelection objectId="bs3" type="CandidateSelection">
                <CandidateIds>can3</CandidateIds>
              </BallotSelection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    validator.check(election_tree.find(".//Contest"))


class SubsequentContestIdIsValidRelatedContestTest(absltest.TestCase):

  _base_election_report = """
    <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election>
        <ContestCollection>
          <Contest objectId="cc_001" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
        </ContestCollection>
        <StartDate>2020-02-03</StartDate>
        <EndDate>2020-02-03</EndDate>
      </Election>
      <Election>
        <ContestCollection>
          <Contest objectId="cc_123">
            <SubsequentContestId>{}</SubsequentContestId>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
        </ContestCollection>
        <StartDate>2020-03-03</StartDate>
        <EndDate>2020-03-03</EndDate>
      </Election>
      <Election>
        <ContestCollection>
          {}
        </ContestCollection>
        <StartDate>2020-11-03</StartDate>
        <EndDate>2020-11-03</EndDate>
      </Election>
    </ElectionReport>
    """

  def test_valid_subsequent_contest_succeeds(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    validator.check(election_tree)

  def test_subsequent_contest_with_mismatched_office_ids_fails(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office2</OfficeIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with a different "
        "office id",
        context.exception.log_entry[0].message,
    )

  def test_subsequent_contest_with_mismatched_primary_party_ids_fails(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with different primary "
        "party ids",
        context.exception.log_entry[0].message,
    )

  def test_subsequent_contest_with_no_primary_party_ids_succeeds(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office1</OfficeIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    validator.check(election_tree)

  def test_subsequent_contest_with_earlier_end_date_from_election_fails(self):
    root_string = self._base_election_report.format("cc_001", "")
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with an earlier end "
        "date.",
        context.exception.log_entry[0].message,
    )

  def test_subsequent_contest_with_earlier_end_date_from_contest_fails(self):
    contest_string = """
          <Contest objectId="cc_002" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
            <StartDate>2020-02-03</StartDate>
            <EndDate>2020-02-03</EndDate>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_002", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with an earlier end "
        "date.",
        context.exception.log_entry[0].message,
    )

  def test_subsequent_contest_contains_original_in_composing_contest_ids_fails(
      self,
  ):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <ComposingContestIds>cc_123</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)
    election_tree = etree.fromstring(root_string)
    validator = election_rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "Contest cc_123 is listed as a composing contest for its subsequent "
        "contest. Two contests can be linked by SubsequentContestId or "
        "ComposingContestId, but not both.",
        context.exception.log_entry[0].message,
    )


class ComposingContestIdsTest(absltest.TestCase):

  _base_election_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election>
        <ContestCollection>
          {}
        </ContestCollection>
      </Election>
      <Election>
        <ContestCollection>
          <Contest objectId="cc_123">
            <ComposingContestIds>{}</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
        </ContestCollection>
      </Election>
    </ElectionReport>
    """

  def test_valid_composing_contests_succeeds(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          <Contest objectId="cc_789">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(
        contest_string, "cc_456 cc_789"
    )

    election_tree = etree.fromstring(root_string)
    validator = election_rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    validator.check(election_tree)

  def test_composing_contest_appears_multiple_times_fails(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          <Contest objectId="cc_789" xsi:type="CandidateContest">
            <ComposingContestIds>cc_456</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")
    election_tree = etree.fromstring(root_string)
    validator = election_rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertIn(
        "Contest cc_456 is listed as a ComposingContest for more than one "
        "parent contest.  ComposingContests should be a strict hierarchy",
        context.exception.log_entry[0].message,
    )

  def test_composing_contest_with_mismatched_office_ids_fails(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office2</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")
    election_tree = etree.fromstring(root_string)
    validator = election_rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 and composing contest cc_456 have different office ids",
        context.exception.log_entry[0].message,
    )

  def test_composing_contest_with_mismatched_primary_party_ids_fails(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")
    election_tree = etree.fromstring(root_string)
    validator = election_rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 and composing contest cc_456 have different primary "
        "party ids",
        context.exception.log_entry[0].message,
    )

  def test_composing_contests_reference_each_other_fails(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <ComposingContestIds>cc_123</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")
    election_tree = etree.fromstring(root_string)
    validator = election_rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertIn(
        "Contest cc_456 and contest cc_123 reference each other as composing "
        "contests",
        context.exception.log_entry[0].message,
    )


class ContestContainsValidStartDateTest(absltest.TestCase):

  def setUp(self):
    super(ContestContainsValidStartDateTest, self).setUp()
    self.validator = election_rules.ContestContainsValidStartDate(None, None)
    self.today_date = datetime.datetime.now(datetime.timezone.utc)

  def test_contest_with_no_start_date_succeeds(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
      </Contest>
      """

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)
    self.assertIsNone(self.validator.end_date)
    self.assertIsNone(self.validator.start_date)

  def test_contest_with_start_date_in_the_past_warns(self):
    yesterday_date = self.today_date - datetime.timedelta(days=1)
    start_date = yesterday_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>{}</StartDate>
      </Contest>
      """.format(start_date)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The date {} is in the past.".format(start_date),
    )

  def test_contest_with_start_date_in_the_future_succeeds(self):
    tomorrow_date = self.today_date + datetime.timedelta(days=1)
    start_date = tomorrow_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>{}</StartDate>
      </Contest>
      """.format(start_date)

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_bad_formatted_start_date_fails(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>blah</StartDate>
      </Contest>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The StartDate text should be of the formats: yyyy-mm-dd, or yyyy, or"
        " yyyy-mm",
    )


class ContestContainsValidEndDateTest(absltest.TestCase):

  def setUp(self):
    super(ContestContainsValidEndDateTest, self).setUp()
    self.validator = election_rules.ContestContainsValidEndDate(None, None)
    self.today_date = datetime.datetime.now(datetime.timezone.utc)

  def test_contest_with_no_end_date_succeeds(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
      </Contest>
      """

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)
    self.assertIsNone(self.validator.end_date)
    self.assertIsNone(self.validator.start_date)

  def test_contest_with_end_date_in_the_past_warns(self):
    yesterday_date = self.today_date - datetime.timedelta(days=1)
    end_date = yesterday_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <EndDate>{}</EndDate>
      </Contest>
      """.format(end_date)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The date {} is in the past.".format(end_date),
    )

  def test_contest_with_end_date_in_the_future_succeeds(self):
    tomorrow_date = self.today_date + datetime.timedelta(days=1)
    end_date = tomorrow_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <EndDate>{}</EndDate>
      </Contest>
      """.format(end_date)

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_bad_formatted_end_date_fails(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <EndDate>blah</EndDate>
      </Contest>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The EndDate text should be of the formats: yyyy-mm-dd, or yyyy, or"
        " yyyy-mm",
    )


class ContestEndDateOccursAfterStartDateTest(absltest.TestCase):

  def setUp(self):
    super(ContestEndDateOccursAfterStartDateTest, self).setUp()
    self.validator = election_rules.ContestEndDateOccursAfterStartDate(
        None, None
    )
    self.today_date = datetime.datetime.now(datetime.timezone.utc)

  def test_contest_with_no_dates_succeeds(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
      </Contest>
      """

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)
    self.assertIsNone(self.validator.end_date)
    self.assertIsNone(self.validator.start_date)

  def test_contest_with_end_date_before_start_date_fails(self):
    yesterday_date = self.today_date - datetime.timedelta(days=1)
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = yesterday_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </Contest>
      """.format(start_date, end_date)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        """The dates (start: {}, end: {}) are invalid.
      The end date must be the same or after the start date.""".format(
            start_date, end_date
        ),
    )

  def test_contest_with_same_start_and_end_date_succeeds(self):
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = self.today_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </Contest>
      """.format(start_date, end_date)

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_end_date_after_start_date_succeeds(self):
    tomorrow_date = self.today_date + datetime.timedelta(days=1)
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = tomorrow_date.strftime("%Y-%m-%d")
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </Contest>
      """.format(start_date, end_date)

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)


class ContestEndDateOccursBeforeSubsequentContestStartDateTest(
    absltest.TestCase
):

  def setUp(self):
    super(
        ContestEndDateOccursBeforeSubsequentContestStartDateTest, self
    ).setUp()
    self.validator = (
        election_rules.ContestEndDateOccursBeforeSubsequentContestStartDate(
            None, None
        )
    )

  def test_contest_with_no_subsequent_contest_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_non_existent_subsequent_contest_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <SubsequentContestId>FakeContest</SubsequentContestId>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_subsequent_contest_with_no_dates_succeeds(self):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <SubsequentContestId>con2</SubsequentContestId>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
            <Contest objectId="con2" xsi:type="CandidateContest">
              <OfficeIds>office2</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_end_date_same_as_subsequent_contest_start_date_succeeds(
      self,
  ):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <SubsequentContestId>con2</SubsequentContestId>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
            <Contest objectId="con2" xsi:type="CandidateContest">
              <OfficeIds>office2</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_end_date_before_subsequent_contest_start_date_succeeds(
      self,
  ):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <SubsequentContestId>con2</SubsequentContestId>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
            <Contest objectId="con2" xsi:type="CandidateContest">
              <OfficeIds>office2</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <StartDate>2023-05-20</StartDate>
              <EndDate>2023-05-20</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    self.validator.check(etree.fromstring(election_report_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_end_date_after_subsequent_contest_start_date_fails(
      self,
  ):
    election_report_string = """
      <ElectionReport  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con1" xsi:type="CandidateContest">
              <OfficeIds>office1</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <SubsequentContestId>con2</SubsequentContestId>
              <StartDate>2023-05-20</StartDate>
              <EndDate>2023-05-20</EndDate>
            </Contest>
            <Contest objectId="con2" xsi:type="CandidateContest">
              <OfficeIds>office2</OfficeIds>
              <PrimaryPartyIds>party1</PrimaryPartyIds>
              <StartDate>2023-05-19</StartDate>
              <EndDate>2023-05-19</EndDate>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest con1 with end date 2023-05-20 does not occur before subsequent"
        " contest con2 with start date 2023-05-19",
    )


class ContestStartDateContainsCorrespondingEndDateTest(absltest.TestCase):

  def setUp(self):
    super(ContestStartDateContainsCorrespondingEndDateTest, self).setUp()
    self.validator = (
        election_rules.ContestStartDateContainsCorrespondingEndDate(None, None)
    )

  def test_contest_with_no_dates_succeeds(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
      </Contest>
      """

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)

  def test_contest_with_only_start_date_fails(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>2023-05-26</StartDate>
      </Contest>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest has a StartDate but is missing an EndDate. Every StartDate"
        " must have a corresponding EndDate.",
    )

  def test_contest_with_only_end_date_fails(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <EndDate>2023-05-26</EndDate>
      </Contest>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest has an EndDate but is missing a StartDate. Every EndDate"
        " must have a corresponding StartDate.",
    )

  def test_contest_with_start_and_end_date_succeeds(self):
    contest_string = """
      <Contest objectId="con1" type="CandidateContest">
        <OfficeIds>office1</OfficeIds>
        <PrimaryPartyIds>party1</PrimaryPartyIds>
        <StartDate>2023-05-26</StartDate>
        <EndDate>2023-05-26</EndDate>
      </Contest>
      """

    self.validator.check(etree.fromstring(contest_string))
    self.assertEmpty(self.validator.error_log)


class CandidateContestTypesAreCompatibleTest(absltest.TestCase):

  def setUp(self):
    super(CandidateContestTypesAreCompatibleTest, self).setUp()
    self.validator = election_rules.CandidateContestTypesAreCompatible(
        None, None
    )

  def test_contest_with_general_and_primary_types_fails(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Fake Contest</Name>
              <Type>GENERAL</Type>
              <Type>PRIMARY</Type>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    contest_element = etree.fromstring(election_report_string).find(
        ".//ContestCollection/Contest"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(contest_element)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateContest contest-1 has incompatible type values. A contest"
        " cannot have both a general and primary type.",
    )

  def test_contest_with_general_and_partisan_primary_open_types_fails(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Fake Contest</Name>
              <Type>GENERAL</Type>
              <Type>PARTISAN-PRIMARY-OPEN</Type>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    contest_element = etree.fromstring(election_report_string).find(
        ".//ContestCollection/Contest"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(contest_element)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateContest contest-1 has incompatible type values. A contest"
        " cannot have both a general and primary type.",
    )

  def test_contest_with_general_and_partisan_primary_closed_types_fails(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Fake Contest</Name>
              <Type>GENERAL</Type>
              <Type>PARTISAN-PRIMARY-CLOSED</Type>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    contest_element = etree.fromstring(election_report_string).find(
        ".//ContestCollection/Contest"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(contest_element)
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateContest contest-1 has incompatible type values. A contest"
        " cannot have both a general and primary type.",
    )

  def test_contest_with_compatible_types_succeeds(self):
    election_report_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election objectId="election-1">
          <ContestCollection>
            <Contest objectId="contest-1" xsi:type="CandidateContest">
              <Name>Fake Contest</Name>
              <Type>GENERAL</Type>
              <Type>RUNOFF</Type>
              <Type>SPECIAL</Type>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    contest_element = etree.fromstring(election_report_string).find(
        ".//ContestCollection/Contest"
    )

    self.validator.check(contest_element)


class ValidatePollsCloseDatetimesTest(absltest.TestCase):

  def setUp(self):
    super(ValidatePollsCloseDatetimesTest, self).setUp()
    self.validator = election_rules.ValidatePollsCloseDatetimes(None, None)

  def test_latest_after_earliest_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00Z</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T20:00:00Z</LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_latest_equals_earliest_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00Z</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T18:00:00Z</LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_latest_before_earliest_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T20:00:00Z</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T18:00:00Z</LatestPollsClose>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "LatestPollsClose (2023-11-07T18:00:00Z) must not be before"
        " EarliestPollsClose (2023-11-07T20:00:00Z) for Contest con1.",
    )

  def test_missing_latest_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00Z</EarliestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_earliest_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <LatestPollsClose>2023-11-07T20:00:00Z</LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_invalid_earliest_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>invalid-date</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T20:00:00Z</LatestPollsClose>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid PollsClose datetime format in Contest con1: Invalid isoformat"
        " string: 'invalid-date'",
    )

  def test_invalid_latest_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00Z</EarliestPollsClose>
        <LatestPollsClose>invalid-date</LatestPollsClose>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid PollsClose datetime format in Contest con1: Invalid isoformat"
        " string: 'invalid-date'",
    )

  def test_valid_datetimes_with_no_timezone_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T20:00:00</LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_valid_datetimes_with_timezone_offset_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose>2023-11-07T18:00:00-05:00</EarliestPollsClose>
        <LatestPollsClose>2023-11-07T20:00:00-05:00</LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_valid_datetimes_with_space_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <EarliestPollsClose> 2023-11-07T18:00:00Z </EarliestPollsClose>
        <LatestPollsClose> 2023-11-07T20:00:00Z </LatestPollsClose>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))


class ValidateResultsExpectedTest(absltest.TestCase):

  def setUp(self):
    super(ValidateResultsExpectedTest, self).setUp()
    self.validator = election_rules.ValidateResultsExpected(None, None)

  def test_missing_results_expected_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_stage_collection_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T22:00:00Z</ResultsExpected>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_stage_expected_start_date_time_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T22:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_invalid_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>invalid-date</ResultsExpected>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid ResultsExpected datetime format in Contest con1: Invalid"
        " isoformat string: 'invalid-date'",
    )

  def test_only_no_results_stages_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T18:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>no-results</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_results_expected_after_earliest_stage_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T22:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>no-results</StageType>
            <ExpectedStartDateTime>2023-11-07T18:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-15T10:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_results_expected_equals_earliest_stage_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T20:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>no-results</StageType>
            <ExpectedStartDateTime>2023-11-07T18:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-15T10:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_results_expected_before_earliest_stage_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T19:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>no-results</StageType>
            <ExpectedStartDateTime>2023-11-07T18:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-15T10:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ResultsExpected (2023-11-07T19:00:00Z) must not be before the"
        " ExpectedStartDateTime (2023-11-07T20:00:00Z) of the earliest"
        " ResultsReportingStage for Contest con1.",
    )

  def test_invalid_stage_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsExpected>2023-11-07T20:00:00Z</ResultsExpected>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>invalid-date</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid ExpectedStartDateTime datetime format for the"
        " 'preliminary' ResultsReportingStage in Contest con1:"
        " Invalid isoformat string: 'invalid-date'",
    )


class ValidateResultsEmbargoEndTest(absltest.TestCase):

  def setUp(self):
    super(ValidateResultsEmbargoEndTest, self).setUp()
    self.validator = election_rules.ValidateResultsEmbargoEnd(None, None)

  def test_missing_results_embargo_end_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_stage_collection_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T22:00:00Z</ResultsEmbargoEnd>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_official_stage_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T22:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_missing_official_stage_expected_start_date_time_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T22:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_invalid_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>invalid-date</ResultsEmbargoEnd>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid ResultsEmbargoEnd datetime format in Contest con1: Invalid"
        " isoformat string: 'invalid-date'",
    )

  def test_results_embargo_end_before_official_stage_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T18:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_results_embargo_end_equals_official_stage_succeeds(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T20:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest_string))

  def test_results_embargo_end_after_official_stage_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T21:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ResultsEmbargoEnd (2023-11-07T21:00:00Z) must not be after the"
        " ExpectedStartDateTime (2023-11-07T20:00:00Z) of the official"
        " ResultsReportingStage for Contest con1.",
    )

  def test_invalid_official_stage_datetime_fails(self):
    contest_string = """
      <Contest objectId="con1">
        <ResultsEmbargoEnd>2023-11-07T21:00:00Z</ResultsEmbargoEnd>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <StageType>official</StageType>
            <ExpectedStartDateTime>invalid-date</ExpectedStartDateTime>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid ExpectedStartDateTime datetime format for the 'official'"
        " ResultsReportingStage in Contest con1: Invalid isoformat string: "
        "'invalid-date'",
    )


class ResultsReportingStagesMustHaveUniqueTypeTest(absltest.TestCase):

  def setUp(self):
    super(ResultsReportingStagesMustHaveUniqueTypeTest, self).setUp()
    self.validator = election_rules.ResultsReportingStagesMustHaveUniqueType(
        None, None
    )

  def test_empty_collection_succeeds(self):
    collection_string = """
      <ResultsReportingStageCollection>
      </ResultsReportingStageCollection>
    """

    self.validator.check(etree.fromstring(collection_string))

  def test_unique_stage_types_succeeds(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>official</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """

    self.validator.check(etree.fromstring(collection_string))

  def test_duplicate_stage_types_fails(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(collection_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Duplicate ResultsReportingStage StageType 'preliminary' found in the"
        " same ResultsReportingStageCollection.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 3)

  def test_multiple_duplicate_stage_types_fails(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>official</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>official</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(collection_string))
    self.assertLen(context.exception.log_entry, 2)

  def test_missing_stage_type_succeeds(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """

    self.validator.check(etree.fromstring(collection_string))

  def test_empty_stage_type_succeeds(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType> </StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """

    self.validator.check(etree.fromstring(collection_string))


class ValidateResultReportingStagesTest(parameterized.TestCase):
  _EMPTY_STAGES_ERROR = (
      "ResultsReportingStageCollection must contain at least one"
      " ResultsReportingStage element when InheritFromComposedContest is"
      " not true."
  )
  _MISSING_REQUIRED_STAGES_WARNING = (
      "ResultsReportingStageCollection should contain at least two"
      " ResultsReportingStage elements, including one of StageType"
      " 'no-results' and at least one of StageType 'preliminary' or"
      " 'official', when InheritFromComposedContest is not true."
  )

  def setUp(self):
    super().setUp()
    self.validator = election_rules.ValidateResultReportingStages(None, None)

  def test_registered_in_election_rules(self):
    self.assertIn(
        election_rules.ValidateResultReportingStages, rules.ELECTION_RULES
    )

  def _setup_election_with_composed_contest(self, collection_string):
    election_string = f"""
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="c-parent" xsi:type="CandidateContest">
              <ComposingContestIds>c-child</ComposingContestIds>
            </Contest>
            <Contest objectId="c-child" xsi:type="CandidateContest">
              {collection_string}
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    self.validator = election_rules.ValidateResultReportingStages(
        election_tree, None
    )
    self.validator.setup()
    return election_tree.find(".//ResultsReportingStageCollection")

  @parameterized.parameters("true", "1")
  def test_inherit_true_without_stages_succeeds(self, inherit):
    collection_element = self._setup_election_with_composed_contest(f"""
        <ResultsReportingStageCollection>
          <InheritFromComposedContest>{inherit}</InheritFromComposedContest>
        </ResultsReportingStageCollection>
    """)

    self.validator.check(collection_element)

  @parameterized.parameters("true", "1")
  def test_inherit_true_with_stages_fails(self, inherit):
    collection_element = self._setup_election_with_composed_contest(f"""
        <ResultsReportingStageCollection>
          <InheritFromComposedContest>{inherit}</InheritFromComposedContest>
          <ResultsReportingStage>
            <StageType>preliminary</StageType>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ResultsReportingStageCollection must not contain any"
        " ResultsReportingStage elements when InheritFromComposedContest is"
        " true.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  def test_inherit_true_not_composing_contest_fails(self):
    election_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="c-orphan" xsi:type="CandidateContest">
              <ResultsReportingStageCollection>
                <InheritFromComposedContest>true</InheritFromComposedContest>
              </ResultsReportingStageCollection>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_string)
    validator = election_rules.ValidateResultReportingStages(
        election_tree, None
    )
    validator.setup()
    collection_element = election_tree.find(
        ".//ResultsReportingStageCollection"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest c-orphan sets InheritFromComposedContest to true but is not"
        " listed in the ComposingContestIds of any other Contest.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements,
        [collection_element.getparent()],
    )

  @parameterized.parameters(
      ("false", "preliminary"),
      ("false", "official"),
      ("0", "preliminary"),
      ("0", "official"),
  )
  def test_inherit_false_with_stages_succeeds(self, inherit, result_stage):
    collection_string = f"""
      <ResultsReportingStageCollection>
        <InheritFromComposedContest>{inherit}</InheritFromComposedContest>
        <ResultsReportingStage>
          <StageType>no-results</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>{result_stage}</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    self.validator.check(collection_element)

  @parameterized.parameters("false", "0")
  def test_inherit_false_without_stages_fails(self, inherit):
    collection_string = f"""
      <ResultsReportingStageCollection>
        <InheritFromComposedContest>{inherit}</InheritFromComposedContest>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._EMPTY_STAGES_ERROR,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  @parameterized.parameters("preliminary", "official")
  def test_inherit_omitted_with_stages_succeeds(self, result_stage):
    collection_string = f"""
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>no-results</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>{result_stage}</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    self.validator.check(collection_element)

  def test_multiple_stages_including_intermediate_stage_succeeds(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>no-results</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>exit-polls</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>official</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    self.validator.check(collection_element)

  def test_inherit_omitted_without_stages_fails(self):
    collection_string = """
      <ResultsReportingStageCollection>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._EMPTY_STAGES_ERROR,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  def test_inherit_empty_without_stages_fails(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <InheritFromComposedContest> </InheritFromComposedContest>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._EMPTY_STAGES_ERROR,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  @parameterized.parameters("no-results", "preliminary", "official")
  def test_single_stage_warns(self, stage_type):
    collection_string = f"""
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>{stage_type}</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._MISSING_REQUIRED_STAGES_WARNING,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  def test_missing_no_results_stage_warns(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>preliminary</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>official</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._MISSING_REQUIRED_STAGES_WARNING,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  def test_missing_preliminary_and_official_stage_warns(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>no-results</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType>exit-polls</StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._MISSING_REQUIRED_STAGES_WARNING,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )

  def test_stage_with_empty_stage_type_warns(self):
    collection_string = """
      <ResultsReportingStageCollection>
        <ResultsReportingStage>
          <StageType>no-results</StageType>
        </ResultsReportingStage>
        <ResultsReportingStage>
          <StageType> </StageType>
        </ResultsReportingStage>
      </ResultsReportingStageCollection>
    """
    collection_element = etree.fromstring(collection_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(collection_element)

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        self._MISSING_REQUIRED_STAGES_WARNING,
    )
    self.assertEqual(
        context.exception.log_entry[0].elements, [collection_element]
    )


class NotEmptyUniqueDataSourceUrisTest(absltest.TestCase):

  def setUp(self):
    super(NotEmptyUniqueDataSourceUrisTest, self).setUp()
    self.validator = election_rules.NotEmptyUniqueDataSourceUris(None, None)

  def test_valid_unique_uris_succeeds(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <Uri language="en">http://source1.com</Uri>
          <Uri language="es">http://source1.com</Uri>
        </DataSource>
        <DataSource objectId="ds2">
          <Uri language="en">http://source2.com</Uri>
        </DataSource>
      </DataSourceCollection>
    """

    self.validator.check(etree.fromstring(xml_string))

  def test_duplicate_uris_across_data_sources_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <Uri language="en">http://duplicate.com</Uri>
        </DataSource>
        <DataSource objectId="ds2">
          <Uri language="en">http://duplicate.com</Uri>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource entities ds1, ds2 have duplicate Uri"
        " 'http://duplicate.com'.",
    )

  def test_empty_uri_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <Uri language="en">   </Uri>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource ds1 has an empty Uri.",
    )


class UniqueDataSourceDisplayNamesTest(absltest.TestCase):

  def setUp(self):
    super(UniqueDataSourceDisplayNamesTest, self).setUp()
    self.validator = election_rules.UniqueDataSourceDisplayNames(None, None)

  def test_valid_unique_display_names_succeeds(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <DisplayName>
            <Text language="en">Source 1</Text>
            <Text language="es">Origen 1</Text>
          </DisplayName>
        </DataSource>
        <DataSource objectId="ds2">
          <DisplayName>
            <Text language="en">Source 2</Text>
          </DisplayName>
        </DataSource>
      </DataSourceCollection>
    """

    self.validator.check(etree.fromstring(xml_string))

  def test_duplicate_display_names_across_data_sources_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <DisplayName><Text language="en">Duplicate Name</Text></DisplayName>
        </DataSource>
        <DataSource objectId="ds2">
          <DisplayName><Text language="es">Duplicate Name</Text></DisplayName>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource entities ds1, ds2 have duplicate DisplayName"
        " 'Duplicate Name'.",
    )

  def test_display_name_without_text_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <DisplayName><Text language="en">   </Text></DisplayName>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource ds1 has a DisplayName element without text.",
    )


class UniqueDataSourceLanguagesTest(absltest.TestCase):

  def setUp(self):
    super(UniqueDataSourceLanguagesTest, self).setUp()
    self.validator = election_rules.UniqueDataSourceLanguages(None, None)

  def test_valid_languages_succeeds(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <DisplayName>
            <Text language="en">Source 1</Text>
            <Text language="es">Origen 1</Text>
          </DisplayName>
          <Uri language="en">http://source1.com</Uri>
          <Uri language="es">http://source1.com</Uri>
        </DataSource>
      </DataSourceCollection>
    """

    self.validator.check(etree.fromstring(xml_string))

  def test_duplicate_uri_languages_within_same_data_source_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <Uri language="en">http://source1.com</Uri>
          <Uri language="en">http://source2.com</Uri>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource ds1 has multiple Uri elements with the same language 'en'.",
    )

  def test_uri_without_language_fails(self):
    xml_string = """
      <DataSourceCollection>
        <DataSource objectId="ds1">
          <Uri>http://source1.com</Uri>
        </DataSource>
      </DataSourceCollection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "DataSource ds1 has a Uri element without a language.",
    )


class LimitAttributionRecursionTest(absltest.TestCase):

  def setUp(self):
    super(LimitAttributionRecursionTest, self).setUp()
    self.validator = election_rules.AttributionDepthLimit(None, None)

  def test_nesting_depth_one_succeeds(self):
    xml_string = """
      <ResultsReportingStage>
        <StageType>preliminary</StageType>
        <Description><Text language="en">Stage</Text></Description>
        <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
        <Attribution>
          <DataSourceId>ds1</DataSourceId>
        </Attribution>
      </ResultsReportingStage>
    """

    self.validator.check(etree.fromstring(xml_string))

  def test_nesting_depth_three_succeeds(self):
    xml_string = """
      <ResultsReportingStage>
        <StageType>preliminary</StageType>
        <Description><Text language="en">Stage</Text></Description>
        <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
        <Attribution>
          <DataSourceId>ds1</DataSourceId>
          <Attribution>
            <DataSourceId>ds2</DataSourceId>
            <Attribution>
              <DataSourceId>ds3</DataSourceId>
            </Attribution>
          </Attribution>
        </Attribution>
      </ResultsReportingStage>
    """

    self.validator.check(etree.fromstring(xml_string))

  def test_nesting_depth_four_with_depth_limit_fails(self):
    xml_string = """
      <ResultsReportingStage>
        <StageType>preliminary</StageType>
        <Description><Text language="en">Stage</Text></Description>
        <ExpectedStartDateTime>2023-11-07T20:00:00Z</ExpectedStartDateTime>
        <Attribution>
          <DataSourceId>ds1</DataSourceId>
          <Attribution>
            <DataSourceId>ds2</DataSourceId>
            <Attribution>
              <DataSourceId>ds3</DataSourceId>
              <Attribution>
                <DataSourceId>ds4</DataSourceId>
              </Attribution>
            </Attribution>
          </Attribution>
        </Attribution>
      </ResultsReportingStage>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(xml_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Attribution starting with DataSourceId 'ds1' has a depth of 4,"
        " exceeding the limit of 3.",
    )


class AttributionCyclesValidationTest(absltest.TestCase):

  def test_attribution_graph_without_cycles_succeeds(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds2</DataSourceId>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    validator.check()

  def test_direct_cycle_fails(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds1</DataSourceId>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Cycle detected in Attribution: ds1 -> ds1",
    )

  def test_indirect_cycle_fails(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds2</DataSourceId>
                <Attribution>
                  <DataSourceId>ds1</DataSourceId>
                </Attribution>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Cycle detected in Attribution: ds1 -> ds2 -> ds1",
    )

  def test_cycle_across_multiple_attributions_fails(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds2</DataSourceId>
              </Attribution>
            </Attribution>
            <Attribution>
              <DataSourceId>ds2</DataSourceId>
              <Attribution>
                <DataSourceId>ds1</DataSourceId>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Cycle detected in Attribution: ds1 -> ds2 -> ds1",
    )

  def test_three_node_cycle_fails(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds2</DataSourceId>
                <Attribution>
                  <DataSourceId>ds3</DataSourceId>
                  <Attribution>
                    <DataSourceId>ds1</DataSourceId>
                  </Attribution>
                </Attribution>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Cycle detected in Attribution: ds1 -> ds2 -> ds3 -> ds1",
    )

  def test_multiple_cycles_with_shared_node_fails(self):
    xml_string = """
      <ElectionReport>
        <ResultsReportingStageCollection>
          <ResultsReportingStage>
            <Attribution>
              <DataSourceId>ds1</DataSourceId>
              <Attribution>
                <DataSourceId>ds2</DataSourceId>
                <Attribution>
                  <DataSourceId>ds1</DataSourceId>
                </Attribution>
              </Attribution>
              <Attribution>
                <DataSourceId>ds3</DataSourceId>
                <Attribution>
                  <DataSourceId>ds1</DataSourceId>
                </Attribution>
              </Attribution>
            </Attribution>
          </ResultsReportingStage>
        </ResultsReportingStageCollection>
      </ElectionReport>
    """
    tree = etree.fromstring(xml_string)

    validator = election_rules.AttributionContainsNoCycles(tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()

    self.assertLen(context.exception.log_entry, 2)
    messages = {entry.message for entry in context.exception.log_entry}
    self.assertEqual(
        messages,
        {
            "Cycle detected in Attribution: ds1 -> ds2 -> ds1",
            "Cycle detected in Attribution: ds1 -> ds3 -> ds1",
        },
    )


class ValidateSpecialBallotSelectionCountedInTotalTest(parameterized.TestCase):

  def setUp(self):
    super(ValidateSpecialBallotSelectionCountedInTotalTest, self).setUp()
    self.validator = (
        election_rules.ValidateSpecialBallotSelectionCountedInTotal(
            None,
            None,
        )
    )

  @parameterized.parameters(
      ("BlankBallotSelection", "true"),
      ("BlankBallotSelection", "false"),
      ("NullBallotSelection", "true"),
      ("NullBallotSelection", "false"),
      ("NoneOfTheAboveBallotSelection", "true"),
      ("NoneOfTheAboveBallotSelection", "false"),
  )
  def test_special_ballot_selections_with_counted_in_total_succeeds(
      self,
      tag,
      counted_in_total,
  ):
    element_string = f"""
      <{tag}>
        <CountedInTotal>{counted_in_total}</CountedInTotal>
      </{tag}>
    """

    self.validator.check(etree.fromstring(element_string))

  @parameterized.parameters(
      "BlankBallotSelection",
      "NullBallotSelection",
      "NoneOfTheAboveBallotSelection",
  )
  def test_special_ballot_selections_missing_counted_in_total_fails(self, tag):
    element_string = f"<{tag}></{tag}>"

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(element_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        f"{tag} must have an explicit value for CountedInTotal.",
    )

  def test_aggregate_ballot_selection_without_counted_in_total_succeeds(self):
    element_string = "<AggregateBallotSelection></AggregateBallotSelection>"

    self.validator.check(etree.fromstring(element_string))

  @parameterized.parameters("true", "false")
  def test_aggregate_ballot_selection_with_counted_in_total_fails(
      self,
      counted_in_total,
  ):
    element_string = f"""
      <AggregateBallotSelection>
        <CountedInTotal>{counted_in_total}</CountedInTotal>
      </AggregateBallotSelection>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(element_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "AggregateBallotSelection must not have CountedInTotal set.",
    )


class ValidateIncludeInAggregationBallotSelectionsTest(parameterized.TestCase):

  def setUp(self):
    super(ValidateIncludeInAggregationBallotSelectionsTest, self).setUp()
    self.validator = (
        election_rules.ValidateIncludeInAggregationBallotSelections(None, None)
    )

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_no_included_in_aggregation_selections_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>false</IncludedInAggregation>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_missing_aggregate_ballot_selection_fails(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
        </{selection_tag}>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Contest con0 has selections marked as IncludedInAggregation but is"
        " missing AggregateBallotSelection.",
    )

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_missing_vote_counts_collection_in_aggregate_fails(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <Selection>
            <Text language="en">Aggregate</Text>
          </Selection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>10</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "In Contest con0, the sum of vote counts (10.0) for selections marked"
        " as IncludedInAggregation exceeds the vote count (0.0) for the"
        " AggregateBallotSelection for vote count type='total' (GpUnit: '').",
    )

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_missing_count_element_succeeds(self, contest_type, selection_tag):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>10</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
            </VoteCounts>
            <VoteCounts>
              <Type>total</Type>
              <Count>5</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_equals_aggregate_count_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>60</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>40</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_equals_aggregate_count_for_other_type_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>60</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>40</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_less_than_aggregate_count_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>50</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>40</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_less_than_aggregate_count_for_other_type_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>50</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>seats-won</OtherType>
              <Count>40</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_exceeds_aggregate_count_fails(self, contest_type, selection_tag):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>60</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <Count>50</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "In Contest con0, the sum of vote counts (110.0) for selections marked"
        " as IncludedInAggregation exceeds the vote count (100.0) for the"
        " AggregateBallotSelection for vote count type='total' (GpUnit: '').",
    )

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_exceeds_aggregate_count_with_other_type_fails(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>total-percent</OtherType>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>total-percent</OtherType>
              <Count>60</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>other</Type>
              <OtherType>total-percent</OtherType>
              <Count>50</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(contest))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "In Contest con0, the sum of vote counts (110.0) for selections marked"
        " as IncludedInAggregation exceeds the vote count (100.0) for the"
        " AggregateBallotSelection for vote count type='total-percent' "
        "(GpUnit: '').",
    )

  @parameterized.parameters(
      ("CandidateContest", "CandidateSelection"),
      ("PartyContest", "PartySelection"),
  )
  def test_sum_equals_aggregate_count_with_breakdown_by_type_and_gp_unit_succeeds(
      self, contest_type, selection_tag
  ):
    contest = f"""
      <Contest objectId="con0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{contest_type}">
        <AggregateBallotSelection>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>100</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>100</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>100</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>100</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </AggregateBallotSelection>
        <{selection_tag} objectId="sel0">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>90</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>80</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>70</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>60</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
        <{selection_tag} objectId="sel1">
          <IncludedInAggregation>true</IncludedInAggregation>
          <VoteCountsCollection>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>10</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>total</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>20</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp0</GpUnitId>
              <Count>30</Count>
            </VoteCounts>
            <VoteCounts>
              <Type>early</Type>
              <GpUnitId>gp1</GpUnitId>
              <Count>40</Count>
            </VoteCounts>
          </VoteCountsCollection>
        </{selection_tag}>
      </Contest>
    """

    self.validator.check(etree.fromstring(contest))


if __name__ == "__main__":
  absltest.main()

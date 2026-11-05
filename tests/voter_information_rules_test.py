# -*- coding: utf-8 -*-
"""Unit test for voter_information_rules.py."""

from absl.testing import absltest
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import voter_information_rules
from lxml import etree


class ElectoralCommissionCollectionExistsTest(absltest.TestCase):

  def setUp(self):
    super(ElectoralCommissionCollectionExistsTest, self).setUp()
    self.validator = (
        voter_information_rules.ElectoralCommissionCollectionExists(None, None)
    )

  def test_election_report_without_electoral_commission_collection_fails(self):
    election_report_string = """
      <ElectionReport></ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectoralCommissionCollection should exist.",
    )

  def test_election_report_with_electoral_commission_collection_succeeds(self):
    election_report_string = """
      <ElectionReport>
        <ElectoralCommissionCollection></ElectoralCommissionCollection>
      </ElectionReport>
      """

    self.validator.check(etree.fromstring(election_report_string))


class VoterInformationCollectionExistsTest(absltest.TestCase):

  def setUp(self):
    super(VoterInformationCollectionExistsTest, self).setUp()
    self.validator = voter_information_rules.VoterInformationCollectionExists(
        None, None
    )

  def test_election_report_without_voter_information_collection_warns(self):
    election_report_string = """
      <ElectionReport></ElectionReport>
      """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "VoterInformationCollection should exist.",
    )

  def test_election_report_with_voter_information_collection_succeeds(self):
    election_report_string = """
      <ElectionReport>
        <VoterInformationCollection></VoterInformationCollection>
      </ElectionReport>
      """

    self.validator.check(etree.fromstring(election_report_string))


class NoExtraElectionElementsTest(absltest.TestCase):
  """Elections should not have inappropriate elements."""

  def setUp(self):
    super(NoExtraElectionElementsTest, self).setUp()
    self.validator = voter_information_rules.NoExtraElectionElements(None, None)

  def test_election_without_extra_elements_succeeds(self):
    election_report_string = """<Election></Election>"""

    self.validator.check(etree.fromstring(election_report_string))

  def test_election_with_ballot_style_collection_fails(self):
    election_report_string = """
      <Election>
        <BallotStyleCollection></BallotStyleCollection>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "BallotStyleCollection should not exist.",
    )

  def test_election_with_candidate_collection_fails(self):
    election_report_string = """
      <Election>
        <CandidateCollection></CandidateCollection>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CandidateCollection should not exist.",
    )

  def test_election_with_contest_collection_fails(self):
    election_report_string = """
      <Election>
        <ContestCollection></ContestCollection>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ContestCollection should not exist.",
    )

  def test_election_with_count_status_fails(self):
    election_report_string = """
      <Election>
        <CountStatus></CountStatus>
      </Election>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CountStatus should not exist.",
    )


class WarnOnElementsNotRecommendedForElectionTest(absltest.TestCase):
  """Elections should warn on elements that are not recommended."""

  def setUp(self):
    super(WarnOnElementsNotRecommendedForElectionTest, self).setUp()
    self.validator = (
        voter_information_rules.WarnOnElementsNotRecommendedForElection(
            None, None
        )
    )

  def test_election_without_contact_information_succeeds(self):
    election_report_string = """<Election></Election>"""

    self.validator.check(etree.fromstring(election_report_string))

  def test_election_with_contact_information_warns(self):
    election_report_string = """
      <Election>
        <ContactInformation></ContactInformation>
      </Election>
      """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ContactInformation is not recommended for Election, prefer using an"
        " ElectionAdministration.",
    )


class NoExtraElectionReportCollectionsTest(absltest.TestCase):
  """ElectionReports should not have inappropriate elements."""

  def setUp(self):
    super(NoExtraElectionReportCollectionsTest, self).setUp()
    self.validator = voter_information_rules.NoExtraElectionReportCollections(
        None, None
    )

  def test_election_report_without_extra_elements_succeeds(self):
    election_report_string = """<ElectionReport></ElectionReport>"""

    self.validator.check(etree.fromstring(election_report_string))

  def test_election_report_with_committee_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <CommitteeCollection></CommitteeCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "CommitteeCollection should not exist.",
    )

  def test_election_report_with_government_body_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <GovernmentBodyCollection></GovernmentBodyCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GovernmentBodyCollection should not exist.",
    )

  def test_election_report_with_office_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <OfficeCollection></OfficeCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "OfficeCollection should not exist.",
    )

  def test_election_report_with_office_holder_tenure_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <OfficeHolderTenureCollection></OfficeHolderTenureCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "OfficeHolderTenureCollection should not exist.",
    )

  def test_election_report_with_party_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <PartyCollection></PartyCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PartyCollection should not exist.",
    )

  def test_election_report_with_person_collection_fails(self):
    election_report_string = """
      <ElectionReport>
        <PersonCollection></PersonCollection>
      </ElectionReport>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_report_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "PersonCollection should not exist.",
    )


if __name__ == "__main__":
  absltest.main()

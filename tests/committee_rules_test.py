# -*- coding: utf-8 -*-
"""Unit test for committee_rules.py."""

import datetime

from absl.testing import absltest
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import committee_rules
from lxml import etree


class CommitteeClassificationEndDateOccursAfterStartDateTest(absltest.TestCase):

  def setUp(self):
    super(CommitteeClassificationEndDateOccursAfterStartDateTest, self).setUp()
    self.validator = (
        committee_rules.CommitteeClassificationEndDateOccursAfterStartDate(
            None, None
        )
    )
    self.today_date = datetime.datetime.now(datetime.timezone.utc)

  def test_committee_classification_with_no_dates_succeeds(self):
    committee_string = """
      <CommitteeClassification objectId="com1">
        <ScopeLevel>ru-123</ScopeLevel>
      </CommitteeClassification>
      """

    self.validator.check(etree.fromstring(committee_string))
    self.assertEmpty(self.validator.error_log)
    self.assertIsNone(self.validator.end_date)
    self.assertIsNone(self.validator.start_date)

  def test_committee_classification_with_end_date_before_start_date_fails(self):
    yesterday_date = self.today_date - datetime.timedelta(days=1)
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = yesterday_date.strftime("%Y-%m-%d")
    committee_string = """
      <CommitteeClassification objectId="com1">
        <ScopeLevel>ru-123</ScopeLevel>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </CommitteeClassification>
      """.format(start_date, end_date)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(committee_string))
    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        """The dates (start: {}, end: {}) are invalid.
      The end date must be the same or after the start date.""".format(
            start_date, end_date
        ),
    )

  def test_committee_classification_with_same_start_and_end_date_succeeds(self):
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = self.today_date.strftime("%Y-%m-%d")
    committee_string = """
      <CommitteeClassification objectId="com1">
        <ScopeLevel>ru-123</ScopeLevel>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </CommitteeClassification>
      """.format(start_date, end_date)

    self.validator.check(etree.fromstring(committee_string))
    self.assertEmpty(self.validator.error_log)

  def test_committee_classification_with_end_date_after_start_date_succeeds(
      self,
  ):
    tomorrow_date = self.today_date + datetime.timedelta(days=1)
    start_date = self.today_date.strftime("%Y-%m-%d")
    end_date = tomorrow_date.strftime("%Y-%m-%d")
    committee_string = """
      <CommitteeClassification objectId="com1">
        <ScopeLevel>ru-123</ScopeLevel>
        <StartDate>{}</StartDate>
        <EndDate>{}</EndDate>
      </CommitteeClassification>
      """.format(start_date, end_date)

    self.validator.check(etree.fromstring(committee_string))
    self.assertEmpty(self.validator.error_log)

  def test_valid_dates_after_invalid_dates_on_same_validator_succeeds(self):
    invalid_committee_string = """
      <CommitteeClassification objectId="com-fake-1">
        <StartDate>2024-05-02</StartDate>
        <EndDate>2024-05-01</EndDate>
      </CommitteeClassification>
      """
    valid_committee_string = """
      <CommitteeClassification objectId="com-fake-2">
        <StartDate>2024-05-01</StartDate>
        <EndDate>2024-05-01</EndDate>
      </CommitteeClassification>
      """

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(invalid_committee_string))

    self.validator.check(etree.fromstring(valid_committee_string))

    self.assertEmpty(self.validator.error_log)


class AffiliationEndDateOccursAfterStartDateTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = committee_rules.AffiliationEndDateOccursAfterStartDate(
        None, None
    )

  def test_elements_returns_affiliation(self):
    self.assertEqual(self.validator.elements(), ["Affiliation"])

  def test_affiliation_with_no_dates_succeeds(self):
    affiliation_string = """
      <Affiliation>
        <PersonId>per-fake</PersonId>
      </Affiliation>
      """

    self.validator.check(etree.fromstring(affiliation_string))

    self.assertEmpty(self.validator.error_log)

  def test_affiliation_with_end_date_before_start_date_fails(self):
    affiliation_string = """
      <Affiliation>
        <PersonId>per-fake</PersonId>
        <StartDate>2024-05-02</StartDate>
        <EndDate>2024-05-01</EndDate>
      </Affiliation>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(affiliation_string))

    self.assertLen(context.exception.log_entry, 1)
    self.assertEqual(
        context.exception.log_entry[0].message,
        """The dates (start: 2024-05-02, end: 2024-05-01) are invalid.
      The end date must be the same or after the start date.""",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "EndDate")

  def test_affiliation_with_same_start_and_end_date_succeeds(self):
    affiliation_string = """
      <Affiliation>
        <PersonId>per-fake</PersonId>
        <StartDate>2024-05-01</StartDate>
        <EndDate>2024-05-01</EndDate>
      </Affiliation>
      """

    self.validator.check(etree.fromstring(affiliation_string))

    self.assertEmpty(self.validator.error_log)

  def test_valid_dates_after_invalid_dates_on_same_validator_succeeds(self):
    invalid_affiliation_string = """
      <Affiliation>
        <PersonId>per-fake-1</PersonId>
        <StartDate>2024-05-02</StartDate>
        <EndDate>2024-05-01</EndDate>
      </Affiliation>
      """
    valid_affiliation_string = """
      <Affiliation>
        <PersonId>per-fake-2</PersonId>
        <StartDate>2024-05-01</StartDate>
        <EndDate>2024-05-03</EndDate>
      </Affiliation>
      """

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(invalid_affiliation_string))

    self.validator.check(etree.fromstring(valid_affiliation_string))

    self.assertEmpty(self.validator.error_log)


class EinMatchesFormatTest(absltest.TestCase):

  def setUp(self):
    super(EinMatchesFormatTest, self).setUp()
    self.root_string = """
      <Committee>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>{}</Type>
            {}
            <Value>{}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Committee>
    """
    self.ein_string = "<OtherType>ein</OtherType>"
    self.validator = committee_rules.EinMatchesFormat(None, None)

  def test_valid_ein_id_succeeds(self):
    test_string = self.root_string.format(
        "other", self.ein_string, "12-3456789"
    )

    self.validator.check(etree.fromstring(test_string))

  def test_invalid_ein_id_fails(self):
    test_string = self.root_string.format(
        "other", self.ein_string, "cand-2013-va-obama!"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "EIN id 'cand-2013-va-obama!' is not in the correct format.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "Committee"
    )

  def test_empty_ein_id_fails(self):
    test_string = self.root_string.format("other", self.ein_string, "   ")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "EIN id '   ' is not in the correct format.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "Committee"
    )

  def test_committee_without_external_identifiers_succeeds(self):
    committee_string = """
      <Committee objectId="com-fake">
        <Name>Fake Committee</Name>
      </Committee>
    """

    self.validator.check(etree.fromstring(committee_string))

  def test_committee_without_ein_external_identifier_succeeds(self):
    test_string = self.root_string.format(
        "other", "<OtherType>fec-id</OtherType>", "not-an-ein"
    )

    self.validator.check(etree.fromstring(test_string))


class AffiliationHasEitherPartyOrPersonTest(absltest.TestCase):

  def setUp(self):
    super(AffiliationHasEitherPartyOrPersonTest, self).setUp()
    self.validator = committee_rules.AffiliationHasEitherPartyOrPerson(
        None, None
    )

  def test_valid_affiliation_succeeds(self):
    test_string = """
      <Affiliation>
        <PersonId>per-123</PersonId>
        <StartDate>2023-05-20</StartDate>
        <EndDate>2023-05-30</EndDate>
      </Affiliation>
    """

    self.validator.check(etree.fromstring(test_string))

  def test_affiliation_with_party_and_person_fails(self):
    test_string = """
      <Affiliation>
        <PartyId>par-123</PartyId>
        <PersonId>per-123</PersonId>
        <StartDate>2023-05-20</StartDate>
        <EndDate>2023-05-30</EndDate>
      </Affiliation>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Affiliation must have one of: PartyId, PersonId. Cannot include both.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "Affiliation"
    )

  def test_empty_affiliation_fails(self):
    test_string = """
      <Affiliation>
        <StartDate>2023-05-20</StartDate>
        <EndDate>2023-05-30</EndDate>
      </Affiliation>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Affiliation must have one of: PartyId, PersonId. Cannot include both.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "Affiliation"
    )


if __name__ == "__main__":
  absltest.main()

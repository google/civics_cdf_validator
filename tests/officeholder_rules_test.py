# -*- coding: utf-8 -*-
"""Unit test for officeholder_rules.py."""

import datetime
import hashlib
import io

from absl.testing import absltest
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import officeholder_rules
import freezegun
from lxml import etree
from mock import MagicMock


class PersonHasOfficeTest(absltest.TestCase):

  _base_xml = """
    <xml>
      <PersonCollection>
        <Person objectId="p1" />
        <Person objectId="p2" />
        <Person objectId="p3" />
      </PersonCollection>
      {}
    </xml>
  """

  # _gather_reference_values tests
  def test_person_ids_from_person_collection_succeeds(self):
    root_string = self._base_xml.format("")
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = officeholder_rules.PersonHasOffice(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"p1", "p2", "p3"})

  # _gather_defined_values tests
  def test_party_leader_and_office_holder_ids_succeeds(self):
    defined_collections = """
      <OfficeHolderTenureCollection>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p1</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p2</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p3</OfficeHolderPersonId>
        </OfficeHolderTenure>
      </OfficeHolderTenureCollection>
      <PartyCollection>
        <Party>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>party-leader-id</OtherType>
              <Value>p4</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Party>
        <Party>
          <Leadership>
            <PartyLeaderId>p5</PartyLeaderId>
            <Type>party-chair</Type>
          </Leadership>
          <Leadership>
            <PartyLeaderId>p6</PartyLeaderId>
            <Type>party-leader</Type>
          </Leadership>
        </Party>
      </PartyCollection>
    """
    root_string = self._base_xml.format(defined_collections)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = officeholder_rules.PersonHasOffice(election_tree, None)
    defined_values = validator._gather_defined_values()
    expected_defined_values = {"p1", "p2", "p3", "p4", "p5", "p6"}

    self.assertEqual(defined_values, expected_defined_values)

  # check tests
  def test_party_leaders_do_not_require_offices_succeeds(self):
    office_party_collections = """
      <PartyCollection>
        <Party>
          <Name>Republican Socialists</Name>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>Other</Type>
              <OtherType>party-leader-id</OtherType>
              <Value>p1</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>Other</Type>
              <OtherType>party-leader-id</OtherType>
              <Value>p2</Value>
            </ExternalIdentifier>
            <ExternalIdentifier>
              <Type>Other</Type>
              <OtherType>party-chair-id</OtherType>
              <Value>p3</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Party>
      </PartyCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_party_collections).encode())
    )
    election_tree = etree.parse(root_string)
    validator = officeholder_rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_no_roots_succeeds(self):
    no_root_string = io.BytesIO(b"<OfficeHolderTenureCollection/>")
    election_tree = etree.parse(no_root_string)
    validator = officeholder_rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_no_person_collection_succeeds(self):
    no_collection_string = io.BytesIO(b"""
      <xml>
        <OfficeHolderTenureCollection/>
      </xml>
    """)
    election_tree = etree.parse(no_collection_string)
    validator = officeholder_rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_each_person_referenced_by_an_office_holder_tenure_succeeds(self):
    office_collection = """
      <OfficeHolderTenureCollection>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p1</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p2</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p3</OfficeHolderPersonId>
        </OfficeHolderTenure>
      </OfficeHolderTenureCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)
    validator = officeholder_rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_extra_person_referenced_by_an_office_holder_tenure_succeeds(
      self,
  ):
    # NOTE: That all offices have valid Persons is
    # checked by testOfficeMissingOfficeHolderPersonData
    office_collection = """
      <OfficeHolderTenureCollection>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p1</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p2</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p3</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p4</OfficeHolderPersonId>
        </OfficeHolderTenure>
      </OfficeHolderTenureCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)

    officeholder_rules.PersonHasOffice(election_tree, None).check()

  def test_person_not_referenced_by_an_office_holder_tenure_fails(self):
    office_collection = """
      <OfficeHolderTenureCollection>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p1</OfficeHolderPersonId>
        </OfficeHolderTenure>
        <OfficeHolderTenure>
          <OfficeHolderPersonId>p2</OfficeHolderPersonId>
        </OfficeHolderTenure>
      </OfficeHolderTenureCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as context:
      officeholder_rules.PersonHasOffice(election_tree, None).check()
    self.assertIn(
        "No defined data for p3 found in the feed.",
        context.exception.log_entry[0].message,
    )

  def test_each_person_in_a_collection_is_referenced_by_an_office_succeeds(
      self,
  ):
    office_collection = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)
    validator = officeholder_rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_extra_person_referenced_by_an_office_succeeds(self):
    # NOTE: That all offices have valid Persons is
    # checked by testOfficeMissingOfficeHolderPersonData
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
          <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
          <OfficeHolderPersonIds>p2</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o3">
          <OfficeHolderPersonIds>p3</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o4">
          <OfficeHolderPersonIds>p4</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)

    officeholder_rules.PersonHasOffice(election_tree, None).check()

  def test_person_not_referenced_by_an_office_fails(self):
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
          <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
          <OfficeHolderPersonIds>p2</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as context:
      officeholder_rules.PersonHasOffice(election_tree, None).check()
    self.assertIn(
        "No defined data for p3 found in the feed.",
        context.exception.log_entry[0].message,
    )

  def test_office_has_one_person_fails(self):
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
           <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
           <OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode())
    )
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as context:
      officeholder_rules.PersonHasOffice(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has 2 OfficeHolders. Must have exactly one.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "o2"
    )


class DateOfBirthIsInPastTest(absltest.TestCase):

  def setUp(self):
    super(DateOfBirthIsInPastTest, self).setUp()
    self.date_of_birth_string = """
      <PersonCollection>
        <Person objectId="per_gb_6456562">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>{}</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    self.validator = officeholder_rules.DateOfBirthIsInPast(None, None)

  @freezegun.freeze_time("2023-01-01")
  def test_valid_date_of_birth_succeeds(self):
    date_of_birth_string = self.date_of_birth_string.format("1975-01-15")
    element = etree.fromstring(date_of_birth_string)

    self.validator.check(element)
    self.assertEmpty(self.validator.error_log)

  @freezegun.freeze_time("2023-01-01")
  def test_invalid_date_of_birth_fails(self):
    date_of_birth_string = self.date_of_birth_string.format("2100-11-11")
    element = etree.fromstring(date_of_birth_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertLen(context.exception.log_entry, 1)
    self.assertIn(
        "The date 2100-11-11 is not in the past.",
        context.exception.log_entry[0].message,
    )


class OfficeSelectionMethodMatchTest(absltest.TestCase):

  def setUp(self):
    super(OfficeSelectionMethodMatchTest, self).setUp()
    root_string = """
      <Report>
        <OfficeCollection>
          <Office objectId="off0">
            <SelectionMethod>appointed</SelectionMethod>
            <SelectionMethod>directly-elected</SelectionMethod>
          </Office>
        </OfficeCollection>
        <OfficeHolderTenureCollection>
          <OfficeHolderTenure>
          </OfficeHolderTenure>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.validator = officeholder_rules.OfficeSelectionMethodMatch(
        element_tree, None
    )

  def test_office_selection_method_match_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["OfficeHolderTenure"])

  def test_matching_office_selection_method_succeeds(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <OfficeId>off0</OfficeId>
        <OfficeSelectionMethod>directly-elected</OfficeSelectionMethod>
      </OfficeHolderTenure>
    """

    self.validator.check(etree.fromstring(office_holder_tenure))

  def test_mismatched_office_selection_method_fails(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <OfficeId>off0</OfficeId>
        <OfficeSelectionMethod>succession</OfficeSelectionMethod>
      </OfficeHolderTenure>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(office_holder_tenure))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "OfficeSelectionMethod does not have a matching SelectionMethod"
        " in the corresponding Office element.",
    )


class OfficeHolderTenureTermDatesTest(absltest.TestCase):

  def setUp(self):
    super(OfficeHolderTenureTermDatesTest, self).setUp()
    self.validator = officeholder_rules.OfficeHolderTenureTermDates(None, None)

  def test_correct_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["OfficeHolderTenure"])

  def test_no_term_dates_succeeds(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
      </OfficeHolderTenure>
    """

    self.validator.check(etree.fromstring(office_holder_tenure))

  def test_start_date_only_succeeds(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <StartDate>2025-03-23</StartDate>
      </OfficeHolderTenure>
    """

    self.validator.check(etree.fromstring(office_holder_tenure))

  def test_start_date_is_empty_succeeds(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <StartDate></StartDate>
      </OfficeHolderTenure>
    """

    self.validator.check(etree.fromstring(office_holder_tenure))

  def test_valid_term_dates_succeeds(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <StartDate>2025-03-23</StartDate>
        <EndDate>2026-06-21</EndDate>
      </OfficeHolderTenure>
    """

    self.validator.check(etree.fromstring(office_holder_tenure))

  def test_invalid_term_dates_fails(self):
    office_holder_tenure = """
      <OfficeHolderTenure objectId="offten0">
        <StartDate>2026-06-22</StartDate>
        <EndDate>2026-06-21</EndDate>
      </OfficeHolderTenure>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(office_holder_tenure))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "OfficeHolderTenure element has an EndDate that is before the"
        " StartDate.",
    )


class OfficeTermDatesTest(absltest.TestCase):

  def setUp(self):
    super(OfficeTermDatesTest, self).setUp()
    root_string = """
      <Report>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.date_validator = officeholder_rules.OfficeTermDates(element_tree, None)
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_date_validator = officeholder_rules.OfficeTermDates(
        element_tree, None
    )
    self.office_string = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
          <StartDate>{}</StartDate>
          <EndDate>{}</EndDate>
        </Term>
      </Office>
    """

  def test_office_elements_succeeds(self):
    self.assertEqual(self.date_validator.elements(), ["Office"])

  def test_offices_with_no_office_holder_person_ids_succeeds(self):
    empty_office = """
      <Office>
      </Office>
    """

    self.date_validator.check(etree.fromstring(empty_office))

  def test_offices_with_office_holder_person_ids_but_no_term_warns(
      self,
  ):
    empty_office = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per1</OfficeHolderPersonIds>
      </Office>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.date_validator.check(etree.fromstring(empty_office))
    self.assertEqual(
        context.exception.log_entry[0].message, "The Office is missing a Term."
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_end_date_is_after_start_date_succeeds(self):
    office_string = self.office_string.format("2020-01-01", "2020-01-02")

    self.date_validator.check(etree.fromstring(office_string))

  def test_end_date_is_before_start_date_fails(self):
    office_string = self.office_string.format("2020-01-03", "2020-01-02")

    with self.assertRaises(loggers.ElectionError) as context:
      self.date_validator.check(etree.fromstring(office_string))
    self.assertIn(
        "The dates (start: 2020-01-03, end: 2020-01-02) are invalid",
        context.exception.log_entry[0].message,
    )
    self.assertIn(
        "The end date must be the same or after the start date.",
        context.exception.log_entry[0].message,
    )

  def test_start_date_not_assigned_warns(self):
    office_string = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
        </Term>
      </Office>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.date_validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The Office is missing a Term > StartDate.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_start_date_assigned_but_not_end_date_succeeds(self):
    office_string = """
      <Office>
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
          <StartDate>2012-01-01</StartDate>
        </Term>
      </Office>
    """

    self.date_validator.check(etree.fromstring(office_string))

  def test_post_office_split_feed_office_without_term_element_succeeds(self):
    office = """
      <Office objectId="off1">
      </Office>
    """

    self.post_office_split_date_validator.check(etree.fromstring(office))

  def test_post_office_split_feed_office_with_term_element_fails(self):
    office = """
      <Office objectId="off1">
        <Term>
        </Term>
      </Office>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.post_office_split_date_validator.check(etree.fromstring(office))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office should not contain Term data in post Office split feed.",
    )


class RemovePersonAndOfficeHolderId60DaysAfterEndDateTest(absltest.TestCase):

  def setUp(self):
    super(RemovePersonAndOfficeHolderId60DaysAfterEndDateTest, self).setUp()
    self.base_string = """
     <ElectionReport>
      <OfficeCollection>
        <Office objectId="off0">
          <OfficeHolderPersonIds>{}</OfficeHolderPersonIds>
          <Term>
          <StartDate>{}</StartDate>
          <EndDate>{}</EndDate>
          </Term>
        </Office>
        <Office objectId="off1">
          <OfficeHolderPersonIds>{}</OfficeHolderPersonIds>
          <Term>
            <StartDate>{}</StartDate>
            <EndDate>{}</EndDate>
          </Term>
        </Office>
        <Office objectId="off2">
          <OfficeHolderPersonIds>{}</OfficeHolderPersonIds>
          <Term>
            <StartDate>{}</StartDate>
            <EndDate>{}</EndDate>
          </Term>
        </Office>
        <Office objectId="off3">
          <OfficeHolderPersonIds>{}</OfficeHolderPersonIds>
          <Term>
            <StartDate>{}</StartDate>
            <EndDate>{}</EndDate>
          </Term>
        </Office>
      </OfficeCollection>
      <PersonCollection>
        <Person objectId="per0"></Person>
        <Person objectId="per1"></Person>
        <Person objectId="per2"></Person>
      </PersonCollection>
    </ElectionReport>
    """

    self.post_office_split_base_string = """
    <ElectionReport>
      <OfficeCollection>
        <Office objectId="off0">
        </Office>
        <Office objectId="off1">
        </Office>
      </OfficeCollection>
      <OfficeHolderTenureCollection>
        <OfficeHolderTenure objectId="offten0">
          <StartDate>{}</StartDate>
          <EndDate>{}</EndDate>
          <OfficeHolderPersonId>per0</OfficeHolderPersonId>
          <OfficeId>off0</OfficeId>
          <OfficeSelectionMethod>directly-elected</OfficeSelectionMethod>
        </OfficeHolderTenure>
        <OfficeHolderTenure objectId="offten1">
          <StartDate>{}</StartDate>
          <EndDate>{}</EndDate>
          <OfficeHolderPersonId>per1</OfficeHolderPersonId>
          <OfficeId>off1</OfficeId>
          <OfficeSelectionMethod>directly-elected</OfficeSelectionMethod>
        </OfficeHolderTenure>
      </OfficeHolderTenureCollection>
      <PersonCollection>
        <Person objectId="per0"></Person>
        <Person objectId="per1"></Person>
      </PersonCollection>
    </ElectionReport>
    """

  def test_end_date_office_holder_raises_info(self):
    office_string = self.base_string.format(
        "per0",
        "2019-01-02",
        "2021-01-20",
        "per1",
        "2019-01-02",
        "",
        "per0",
        "2019-09-02",
        "2021-02-20",
        "per2",
        "2019-09-02",
        "",
    )
    election_tree = etree.fromstring(office_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
          election_tree, None
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The officeholder mandates ended more than 60 days ago. "
        "Therefore, you can remove the person and the related offices "
        "from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "per0"
    )

  def test_end_date_office_holder_for_multiple_persons_raises_info(
      self,
  ):
    office_string = self.base_string.format(
        "per0",
        "2019-01-02",
        "2021-01-20",
        "per1",
        "2019-01-02",
        "2021-02-24",
        "per0",
        "2019-09-02",
        "2021-02-20",
        "per2",
        "2019-09-02",
        "",
    )
    election_tree = etree.fromstring(office_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
          election_tree, None
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The officeholder mandates ended more than 60 days ago. "
        "Therefore, you can remove the person and the related offices "
        "from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "The officeholder mandates ended more than 60 days ago. "
        "Therefore, you can remove the person and the related offices "
        "from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "per0"
    )
    self.assertEqual(
        context.exception.log_entry[1].elements[0].get("objectId"), "per1"
    )

  def test_post_office_split_end_date_office_holder_raises_info(
      self,
  ):
    test_string = self.post_office_split_base_string.format(
        "2019-01-02", "", "2019-10-02", "2023-06-21"
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
          election_tree, None
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The officeholder tenure end date is more than 60 days"
        " in the past; this OfficeHolderTenure element can be removed"
        " from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "offten1"
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "All officeholder tenures ended more than 60 days ago. "
        "Therefore, you can remove the person and the related "
        "officeholder tenures from the feed.",
    )
    self.assertEqual(context.exception.log_entry[1].elements[0].text, "per1")

  def test_end_date_office_holder_for_multiple_office_holder_tenures_raises_info(
      self,
  ):
    test_string = self.post_office_split_base_string.format(
        "2019-01-02", "2021-12-21", "2019-10-02", "2023-06-21"
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
          election_tree, None
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The officeholder tenure end date is more than 60 days"
        " in the past; this OfficeHolderTenure element can be removed"
        " from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "offten0"
    )
    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
          election_tree, None
      ).check()
    self.assertEqual(
        context.exception.log_entry[1].message,
        "The officeholder tenure end date is more than 60 days"
        " in the past; this OfficeHolderTenure element can be removed"
        " from the feed.",
    )
    self.assertEqual(
        context.exception.log_entry[1].elements[0].get("objectId"), "offten1"
    )

  @freezegun.freeze_time("2022-01-01")
  def test_end_date_office_holder_succeeds(self):
    office_string = self.base_string.format(
        "per0",
        "2019-01-31",
        "2023-04-16",
        "per1",
        "2019-01-22",
        "2023-05-12",
        "per0",
        "2019-09-02",
        "2020-03-20",
        "per2",
        "2019-09-02",
        "",
    )
    election_tree = etree.fromstring(office_string)

    officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
        election_tree, None
    ).check()

  @freezegun.freeze_time("2022-01-01")
  def test_post_office_split_end_date_office_holder_succeeds(
      self,
  ):
    test_string = self.post_office_split_base_string.format(
        "2019-01-02", "2021-12-01", "2020-10-02", "2023-01-01"
    )
    election_tree = etree.fromstring(test_string)

    officeholder_rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
        election_tree, None
    ).check()


class UniqueStartDatesForOfficeRoleAndJurisdictionTest(absltest.TestCase):

  def setUp(self):
    super(UniqueStartDatesForOfficeRoleAndJurisdictionTest, self).setUp()
    self.validator = (
        officeholder_rules.UniqueStartDatesForOfficeRoleAndJurisdiction(
            None, None
        )
    )

  _office_string = """
    <Office>
      <Term>
        <StartDate>{info[date]}</StartDate>
      </Term>
      <AdditionalData type="jurisdiction-id">{info[juris]}</AdditionalData>
      <AdditionalData type="office-role">{info[role]}</AdditionalData>
    </Office>
  """

  def test_office_collection_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["OfficeCollection"])

  # _filter_out_past_end_dates tests
  def test_all_offices_with_end_date_not_in_past_succeeds(self):
    office_string = """
      <Office>
        <Term>
          <EndDate>{}</EndDate>
        </Term>
      </Office>
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    tomorrow = today + datetime.timedelta(days=1)
    yesterday = today - datetime.timedelta(days=1)
    office_one = etree.fromstring(office_string.format(today))
    office_two = etree.fromstring(office_string.format(tomorrow))
    office_three = etree.fromstring(office_string.format(yesterday))
    offices = [office_one, office_two, office_three]

    actual_valid = self.validator._filter_out_past_end_dates(offices)

    self.assertEqual(actual_valid, [office_one, office_two])

  def test_offices_with_no_term_are_invalid_succeeds(self):
    office_string = """
      <Office>
        <EndDate>{}</EndDate>
      </Office>
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    office_one = etree.fromstring(office_string.format(today))
    offices = [office_one]

    actual_valid = self.validator._filter_out_past_end_dates(offices)

    self.assertEqual(actual_valid, [])

  def test_poorly_formatted_offices_are_invalid_succeeds(self):
    office_string = """
      <Office>
        <Term>
          <EndDate>abcdefghijk</EndDate>
        </Term>
      </Office>
    """
    office_one = etree.fromstring(office_string)
    offices = [office_one]

    actual_valid = self.validator._filter_out_past_end_dates(offices)

    self.assertEqual(actual_valid, [])

  def test_offices_with_no_end_date_are_valid_succeeds(self):
    office_string = """
      <Office>
        <Term>
          <StartDate>2020-01-01</StartDate>
        </Term>
      </Office>
    """
    office_one = etree.fromstring(office_string)
    offices = [office_one]

    actual_valid = self.validator._filter_out_past_end_dates(offices)

    self.assertEqual(actual_valid, offices)

  # _count_start_dates_by_jurisdiction_role tests
  def test_a_map_of_jurisdiction_id_office_role_start_date_counts_succeeds(
      self,
  ):
    office_coll_string = """
      <OfficeCollection>
        {}
        {}
        {}
      </OfficeCollection>
    """
    o1_info = {"date": "2020-01-01", "juris": "ru-gpu1", "role": "Upper house"}
    office_one = self._office_string.format(info=o1_info)
    o2_info = {"date": "2020-02-02", "juris": "ru-gpu2", "role": "Middle house"}
    office_two = self._office_string.format(info=o2_info)
    o3_info = {"date": "2020-03-03", "juris": "ru-gpu3", "role": "Lower house"}
    office_three = self._office_string.format(info=o3_info)

    office_collection_str = office_coll_string.format(
        office_one, office_two, office_three
    )
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 3)
    o1_hash = hashlib.sha256(
        (o1_info["role"] + o1_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: {office_collection.findall("Office")[0]},
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])
    o2_hash = hashlib.sha256(
        (o2_info["role"] + o2_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: {office_collection.findall("Office")[1]},
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])
    o3_hash = hashlib.sha256(
        (o3_info["role"] + o3_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o3_mapping = {
        "jurisdiction_id": o3_info["juris"],
        "office_role": o3_info["role"],
        "start_dates": {
            o3_info["date"]: {office_collection.findall("Office")[2]},
        },
    }
    self.assertIn(o3_hash, mapping.keys())
    self.assertEqual(expected_o3_mapping, mapping[o3_hash])

  def test_offices_with_no_start_date_defined_succeeds(self):
    office_coll_string = """
      <OfficeCollection>
        {}
        {}
        {}
      </OfficeCollection>
    """
    o1_info = {"date": "2020-01-01", "juris": "ru-gpu1", "role": "Upper house"}
    office_one = self._office_string.format(info=o1_info)
    o2_info = {"date": "", "juris": "ru-gpu2", "role": "Middle house"}
    office_two = self._office_string.format(info=o2_info)
    o3_info = {"date": "2020-03-03", "juris": "ru-gpu3", "role": "Lower house"}
    office_three = self._office_string.format(info=o3_info)

    office_collection_str = office_coll_string.format(
        office_one, office_two, office_three
    )
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 2)
    o1_hash = hashlib.sha256(
        (o1_info["role"] + o1_info["juris"]).encode("utf-8")
    ).hexdigest()
    self.assertIn(o1_hash, mapping.keys())
    o2_hash = hashlib.sha256(
        (o2_info["role"] + o2_info["juris"]).encode("utf-8")
    ).hexdigest()
    self.assertNotIn(o2_hash, mapping.keys())
    o3_hash = hashlib.sha256(
        (o3_info["role"] + o3_info["juris"]).encode("utf-8")
    ).hexdigest()
    self.assertIn(o3_hash, mapping.keys())

  def test_updates_the_count_for_duplicate_jurisdiction_role_date_succeeds(
      self,
  ):
    office_coll_string = """
      <OfficeCollection>
        {}
        {}
        {}
      </OfficeCollection>
    """
    o1_info = {"date": "2020-01-01", "juris": "ru-gpu1", "role": "Upper house"}
    office_one = self._office_string.format(info=o1_info)
    o2_info = {"date": "2020-02-02", "juris": "ru-gpu2", "role": "Middle house"}
    office_two = self._office_string.format(info=o2_info)
    # office three same as office one
    o3_info = {"date": "2020-01-01", "juris": "ru-gpu1", "role": "Upper house"}
    office_three = self._office_string.format(info=o3_info)

    office_collection_str = office_coll_string.format(
        office_one, office_two, office_three
    )
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 2)
    o1_hash = hashlib.sha256(
        (o1_info["role"] + o1_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: {
                office_collection.findall("Office")[0],
                office_collection.findall("Office")[2],
            },
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])
    o2_hash = hashlib.sha256(
        (o2_info["role"] + o2_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: {office_collection.findall("Office")[1]},
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])

  def test_missing_role_or_jurisdiction_counted_as_blank_succeeds(self):
    office_coll_string = """
      <OfficeCollection>
        {}
        {}
        {}
      </OfficeCollection>
    """
    # o1 and o2 share same role but o1 missing jurisdiction
    # o3 and o2 share same jurisdiction but o2 missing role
    o1_info = {"date": "2020-01-01", "juris": "", "role": "Middle house"}
    office_one = self._office_string.format(info=o1_info)
    o2_info = {"date": "2020-02-02", "juris": "ru-gpu2", "role": "Middle house"}
    office_two = self._office_string.format(info=o2_info)
    o3_info = {"date": "2020-01-01", "juris": "ru-gpu2", "role": ""}
    office_three = self._office_string.format(info=o3_info)

    office_collection_str = office_coll_string.format(
        office_one, office_two, office_three
    )
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 3)
    o1_hash = hashlib.sha256(
        (o1_info["role"] + o1_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: {office_collection.findall("Office")[0]},
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])
    o2_hash = hashlib.sha256(
        (o2_info["role"] + o2_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: {office_collection.findall("Office")[1]},
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])
    o3_hash = hashlib.sha256(
        (o3_info["role"] + o3_info["juris"]).encode("utf-8")
    ).hexdigest()
    expected_o3_mapping = {
        "jurisdiction_id": o3_info["juris"],
        "office_role": o3_info["role"],
        "start_dates": {
            o3_info["date"]: {office_collection.findall("Office")[2]},
        },
    }
    self.assertIn(o3_hash, mapping.keys())
    self.assertEqual(expected_o3_mapping, mapping[o3_hash])

  # check tests
  def test_duplicate_start_dates_for_jurisdiction_and_role_succeeds(
      self,
  ):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": {etree.fromstring("<Office></Office>")},
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": {etree.fromstring("<Office></Office>")},
            },
        },
    }
    mock_counts = MagicMock(return_value=start_counts)
    self.validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")

    self.validator.check(office_coll)

  def test_all_start_dates_for_jurisdiction_and_role_same_warns(
      self,
  ):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": {etree.fromstring("<Office></Office>")},
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": {
                    etree.fromstring("<Office></Office>"),
                    etree.fromstring("<Office></Office>"),
                },
            },
        },
    }
    mock_counts = MagicMock(return_value=start_counts)
    self.validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(office_coll)

    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Only one unique StartDate found for each "
            "jurisdiction-id: ru-gpu2 and office-role: Lower house. "
            "2020-01-02 appears 2 times."
        ),
    )

  def test_allows_duplicates_as_long_as_duplicated_date_is_not_only_date_succeeds(
      self,
  ):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": {etree.fromstring("<Office></Office>")},
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": {
                    etree.fromstring("<Office></Office>"),
                    etree.fromstring("<Office></Office>"),
                },
                "2020-01-04": {etree.fromstring("<Office></Office>")},
            },
        },
    }
    mock_counts = MagicMock(return_value=start_counts)
    self.validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")

    self.validator.check(office_coll)


class UnreferencedEntitiesOfficeholdersTest(absltest.TestCase):
  _base_schema = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    </xs:schema>
  """)

  def test_unreferenced_top_level_gp_unit_raises_info(self):
    test_string = """
    <GpUnit objectId="gpunit-id">
      <ComposingGpUnitIds>child-gpunit child-gpunit-2</ComposingGpUnitIds>
    </GpUnit>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="ComposingGpUnitIds" type="xs:IDREFS" />
    </xs:schema>
  """

    with self.assertRaises(loggers.ElectionInfo) as context:
      officeholder_rules.UnreferencedEntitiesOfficeholders(
          etree.fromstring(test_string), etree.fromstring(schema_string)
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit with object id gpunit-id is not referenced by anything"
        " else in the feed. This is ok for top-level GpUnits that"
        " contain others; please ensure this GpUnit is still required in"
        " the feed.",
    )

  def test_unreferenced_child_gp_unit_fails(self):
    test_string = """
    <GpUnit objectId="gpunit-id">
    </GpUnit>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      officeholder_rules.UnreferencedEntitiesOfficeholders(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type GpUnit with object id gpunit-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_person_fails(self):
    test_string = """
    <Person objectId="person-id">
    </Person>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      officeholder_rules.UnreferencedEntitiesOfficeholders(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type Person with object id person-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_party_warns(self):
    test_string = """
    <Party objectId="party-id">
    </Party>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      officeholder_rules.UnreferencedEntitiesOfficeholders(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type Party with object id party-id is not"
        " referenced by anything else in the feed. This is only ok if"
        " there are explicit instructions to include this entity anyways.",
    )

  def test_unreferenced_top_level_office_succeeds(self):
    test_string = """
    <Office objectId="office-id">
    </Office>
    """

    officeholder_rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_unreferenced_party_leadership_succeeds(self):
    test_string = """
    <Leadership objectId="leadership-id">
    </Leadership>
    """

    officeholder_rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_unreferenced_top_level_office_holder_tenure_succeeds(self):
    test_string = """
    <OfficeHolderCollection>
      <OfficeHolderTenure objectId="office-ten-id">
      </OfficeHolderTenure>
    </OfficeHolderCollection>
    """

    officeholder_rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_external_id_referenced_person_succeeds(self):
    test_string = """
    <ElectionReport xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <PersonCollection>
        <Person objectId="per-1">
          <PartyId>party-1</PartyId>
        </Person>
        <Person objectId="party-chair">
        </Person>
      </PersonCollection>
      <OfficeCollection>
        <Office objectId="office-holder-office">
          <OfficeHolderPersonIds>per-1</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
      <PartyCollection>
        <Party objectId="party-1">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>party-chair-id</OtherType>
              <Value>party-chair</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Party>
      </PartyCollection>
    </ElectionReport>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="PartyId" type="xs:IDREF" />
      <xs:element minOccurs="0" name="OfficeHolderPersonIds" type="xs:IDREFS" />
    </xs:schema>
  """

    officeholder_rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()


if __name__ == "__main__":
  absltest.main()

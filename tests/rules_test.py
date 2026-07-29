# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import hashlib
import io

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
import freezegun
from lxml import etree
from mock import MagicMock
import networkx


class HelpersTest(absltest.TestCase):

  # get_external_id_values tests
  def test_get_external_id_values_returns_values(self):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_id = "ocd-division/country:us/state:ma"
    expected_other_stable = "stable-gpu-abc123"

    actual_ocd_ids = rules.get_external_id_values(gp_unit_elem, "ocd-id")
    actual_stable_ids = rules.get_external_id_values(gp_unit_elem, "stable")

    self.assertEqual(actual_ocd_ids, [expected_ocd_id])
    self.assertEqual(actual_stable_ids, [expected_other_stable])

  def test_get_external_id_values_with_return_elements_returns_elements(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_id = b"<Value>ocd-division/country:us/state:ma</Value>"
    expected_other_stable = b"<Value>stable-gpu-abc123</Value>"

    actual_ocd_ids = rules.get_external_id_values(gp_unit_elem, "ocd-id", True)
    actual_stable = rules.get_external_id_values(gp_unit_elem, "stable", True)

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(etree.tostring(actual_ocd_ids[0]).strip(), expected_ocd_id)
    self.assertLen(actual_stable, 1)
    self.assertEqual(
        etree.tostring(actual_stable[0]).strip(), expected_other_stable
    )

  def test_get_external_id_values_with_invalid_types_returns_empty_list(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>blamo</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>ocd-id</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)

    invalid_type_values = rules.get_external_id_values(gp_unit_elem, "blamo")
    other_type_values = rules.get_external_id_values(gp_unit_elem, "ocd-id")

    self.assertEmpty(invalid_type_values)
    self.assertEmpty(other_type_values)

  # get_additional_type_values tests
  def test_get_additional_type_values_returns_values(self):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">ocd-division/country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)
    expected_ocd_id = "ocd-division/country:us"

    actual_ocd_ids = rules.get_additional_type_values(office_elem, "ocd-id")

    self.assertEqual(actual_ocd_ids, [expected_ocd_id])

  def test_get_additional_type_values_with_return_elements_returns_elements(
      self,
  ):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)
    expected = b'<AdditionalData type="ocd-id">country:us</AdditionalData>'

    actual_ocd_ids = rules.get_additional_type_values(
        office_elem, "ocd-id", True
    )
    actual_ocd_id = etree.tostring(actual_ocd_ids[0]).strip()

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(actual_ocd_id, expected)

  def test_get_additional_type_values_with_missing_elements_returns_empty_list(
      self,
  ):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id"></AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)

    actual_ocd_ids = rules.get_additional_type_values(office_elem, "ocd-id")
    not_found = rules.get_additional_type_values(office_elem, "not-found")

    self.assertEmpty(actual_ocd_ids)
    self.assertEmpty(not_found)

  # get_entity_info_for_value_type tests
  def test_get_entity_info_for_value_type_returns_values(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>external-id-ocd-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <AdditionalData type="ocd-id">addtl-data-ocd-id</AdditionalData>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_ids = ["addtl-data-ocd-id", "external-id-ocd-id"]

    actual_ocd_ids = rules.get_entity_info_for_value_type(
        gp_unit_elem, "ocd-id"
    )

    self.assertEqual(actual_ocd_ids, expected_ocd_ids)

  def test_get_entity_info_for_value_type_with_return_elements_returns_elements(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>external-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <AdditionalData type="ocd-id">addtl-data</AdditionalData>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_data = b'<AdditionalData type="ocd-id">addtl-data</AdditionalData>'
    expected_external = b"<Value>external-id</Value>"

    actual_ocd_ids = rules.get_entity_info_for_value_type(
        gp_unit_elem, "ocd-id", True
    )
    actual_data = etree.tostring(actual_ocd_ids[0]).strip()
    actual_external = etree.tostring(actual_ocd_ids[1]).strip()

    self.assertEqual(actual_data, expected_data)
    self.assertEqual(actual_external, expected_external)

  # element_has_text tests
  def test_element_has_text_returns_true(self):
    element_string = "<FirstName>Jerry</FirstName>"

    elem_has_text = rules.element_has_text(etree.fromstring(element_string))

    self.assertTrue(elem_has_text)

  def test_element_has_text_when_element_is_none_returns_false(self):
    elem_has_text = rules.element_has_text(None)

    self.assertFalse(elem_has_text)

  def test_element_has_text_when_element_is_empty_returns_false(self):
    element_string = "<FirstName></FirstName>"

    elem_has_text = rules.element_has_text(etree.fromstring(element_string))

    self.assertFalse(elem_has_text)

  def test_element_has_text_when_element_is_whitespace_returns_false(self):
    element_string = "<FirstName>   </FirstName>"

    elem_has_text = rules.element_has_text(etree.fromstring(element_string))

    self.assertFalse(elem_has_text)


class SchemaTest(absltest.TestCase):

  _schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Report"/>
      <xs:complexType name="Person">
        <xs:sequence>
          <xs:element minOccurs="1" type="xs:string" name="FirstName" />
          <xs:element minOccurs="1" type="xs:string" name="LastName" />
          <xs:element minOccurs="0" type="xs:integer" name="Age" />
        </xs:sequence>
      </xs:complexType>
    </xs:schema>
  """)

  def test_valid_schema_and_tree_succeeds(self):
    root_string = """
      <Report>
        <Person>
          <FirstName>Jerry</FirstName>
          <LastName>Seinfeld</LastName>
          <Age>38</Age>
        </Person>
      </Report>
    """
    election_tree = etree.fromstring(root_string)
    validator = rules.Schema(election_tree, SchemaTest._schema_tree)

    validator.check()

  def test_schema_parse_failure_fails(self):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType"/>
      </xs:schema>
    """)
    election_tree = etree.fromstring("<Report/>")
    validator = rules.Schema(election_tree, schema_tree)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn(
        "The schema file could not be parsed correctly",
        context.exception.log_entry[0].message,
    )

  def test_invalid_tree_fails(self):
    root_string = """
      <Person>
        <FirstName>Jerry</FirstName>
        <LastName>Seinfeld</LastName>
        <Age>38</Age>
      </Person>
    """
    election_tree = etree.fromstring(root_string)
    validator = rules.Schema(election_tree, SchemaTest._schema_tree)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn(
        "The election file didn't validate against schema",
        context.exception.log_entry[0].message,
    )


class OptionalAndEmptyTest(absltest.TestCase):

  def setUp(self):
    super(OptionalAndEmptyTest, self).setUp()
    self.validator = rules.OptionalAndEmpty(None, None)

  def test_optional_elements_succeeds(self):
    schema_tree = etree.fromstring(b"""
      <element>
        <element minOccurs="0" name="ThingOne" />
        <element minOccurs="1" name="ThingTwo" />
        <element minOccurs="0" name="ThingThree" />
        <simpleType minOccurs="0" />
      </element>
    """)
    self.validator = rules.OptionalAndEmpty(None, schema_tree)
    eligible_elements = self.validator.elements()

    self.assertEqual(eligible_elements, ["ThingOne", "ThingThree"])

  def test_element_is_same_as_previous_succeeds(self):
    root_string = """
      <ThingOne></ThingOne>
    """
    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7
    self.validator.previous = non_empty_element

    self.validator.check(non_empty_element)

  def test_non_empty_elements_succeeds(self):
    root_string = """
      <ThingOne>BoomShakalaka</ThingOne>
    """
    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7

    self.validator.check(non_empty_element)

  def test_empty_elements_warns(self):
    empty_string = """
      <ThingOne></ThingOne>
    """
    empty_element = etree.fromstring(empty_string)
    empty_element.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(empty_element)

  def test_space_only_elements_warns(self):
    space_string = """
      <ThingOne>  </ThingOne>
    """
    space_element = etree.fromstring(space_string)
    space_element.sourceline = 7

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(space_element)


class EncodingTest(absltest.TestCase):

  def test_utf8_encoding_succeeds(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <Report/>
    """)
    election_tree = etree.parse(root_string)
    validator = rules.Encoding(election_tree, None)

    validator.check()

  def test_non_utf8_encoding_fails(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="us-ascii"?>
      <Report/>
    """)
    election_tree = etree.parse(root_string)
    validator = rules.Encoding(election_tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message, "Encoding on file is not UTF-8"
    )


class HungarianStyleNotationTest(absltest.TestCase):

  def setUp(self):
    super(HungarianStyleNotationTest, self).setUp()
    self.validator = rules.HungarianStyleNotation(None, None)

  def test_all_elements_with_prefixes_succeeds(self):
    elements = self.validator.elements()

    self.assertEqual(elements, self.validator.elements_prefix.keys())

  def test_elements_with_no_object_id_succeeds(self):
    element_string = """
      <Party/>
    """
    party_element = etree.fromstring(element_string)

    self.validator.check(party_element)

  def test_object_ids_use_accepted_prefix_succeeds(self):
    elements_prefix = {
        "BallotMeasureContest": "bmc",
        "BallotMeasureSelection": "bms",
        "BallotStyle": "bs",
        "Candidate": "can",
        "CandidateContest": "cc",
        "CandidateSelection": "cs",
        "Coalition": "coa",
        "ContactInformation": "ci",
        "Hours": "hours",
        "Office": "off",
        "OfficeGroup": "og",
        "Party": "par",
        "PartyContest": "pc",
        "PartySelection": "ps",
        "Person": "per",
        "ReportingDevice": "rd",
        "ReportingUnit": "ru",
        "RetentionContest": "rc",
        "Schedule": "sched",
    }
    for elem in elements_prefix:
      element_string = """
        <{} objectId="{}0"/>
      """.format(elem, elements_prefix[elem])
      party_element = etree.fromstring(element_string)

      self.validator.check(party_element)

  def test_invalid_prefix_raises_info(self):
    element_string = """
      <Party objectId="pax0"/>
    """
    party_element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionInfo):
      self.validator.check(party_element)

  def test_an_unlisted_element_fails(self):
    element_string = """
      <Blamo objectId="pax0"/>
    """
    party_element = etree.fromstring(element_string)

    with self.assertRaises(KeyError):
      self.validator.check(party_element)


class LanguageCodeTest(absltest.TestCase):

  def setUp(self):
    super(LanguageCodeTest, self).setUp()
    self.validator = rules.LanguageCode(None, None)

  def test_target_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Text", "Uri"])

  def test_elements_without_language_attribute_succeeds(self):
    element_string = """
      <Text>BoomShakalaka</Text>
    """
    text_element = etree.fromstring(element_string)

    self.validator.check(text_element)

  def test_language_attribute_is_valid_tag_succeeds(self):
    element_string = """
      <Text language="en">BoomShakalaka</Text>
    """
    text_element = etree.fromstring(element_string)

    self.validator.check(text_element)

  def test_invalid_language_attributes_invalid_fails(self):
    invalid_string = """
      <Text language="zzz">BoomShakalaka</Text>
    """
    invalid_element = etree.fromstring(invalid_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(invalid_element)

  def test_invalid_language_attributes_empty_fails(self):
    empty_string = """
      <Text language="">BoomShakalaka</Text>
    """
    empty_element = etree.fromstring(empty_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(empty_element)

  def test_uri_without_language_attribute_succeeds(self):
    element_string = """
      <Uri>http://example.com</Uri>
    """
    uri_element = etree.fromstring(element_string)

    self.validator.check(uri_element)

  def test_uri_with_valid_language_attribute_succeeds(self):
    element_string = """
      <Uri language="es">http://example.com/es</Uri>
    """
    uri_element = etree.fromstring(element_string)

    self.validator.check(uri_element)

  def test_uri_with_invalid_language_attributes_fails(self):
    invalid_string = """
      <Uri language="zzz">http://example.com</Uri>
    """
    invalid_element = etree.fromstring(invalid_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(invalid_element)

  def test_uri_with_empty_language_attributes_fails(self):
    empty_string = """
      <Uri language="">http://example.com</Uri>
    """
    empty_element = etree.fromstring(empty_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(empty_element)


class PercentSumTest(absltest.TestCase):

  def setUp(self):
    super(PercentSumTest, self).setUp()
    self.validator = rules.PercentSum(None, None)
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


class EmptyTextTest(absltest.TestCase):

  def setUp(self):
    super(EmptyTextTest, self).setUp()
    self.validator = rules.EmptyText(None, None)

  def test_text_elements_succeeds(self):
    self.assertEqual(["Text"], self.validator.elements())

  def test_non_empty_text_succeeds(self):
    element_string = """
      <Text>Boomshakalaka</Text>
    """
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_empty_text_fails(self):
    element_string = """
      <Text></Text>
    """
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_space_only_text_fails(self):
    empty_string = """
      <Text>   </Text>
    """
    element = etree.fromstring(empty_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_empty_text_with_language_fails(self):
    element_string = """
      <Text language="en" />
    """
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)


class EmptyStringTest(absltest.TestCase):

  def setUp(self):
    super(EmptyStringTest, self).setUp()
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="FirstName" type="xs:string" />
              <xs:element name="LastName" type="xs:string" />
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:schema>
    """)
    self.validator = rules.EmptyString(None, schema_tree)

  def test_non_empty_string_succeeds(self):
    element_string = "<FirstName>Jerry</FirstName>"
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_empty_string_fails(self):
    element_string = "<FirstName></FirstName>"
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_whitespace_string_fails(self):
    element_string = "<FirstName>   </FirstName>"
    element = etree.fromstring(element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)


class DuplicateIDTest(absltest.TestCase):

  def test_valid_if_no_object_id_values_are_the_same_succeeds(self):
    root_string = """
      <Report objectId="1">
        <Person>
          <FirstName objectId="">Jerry</FirstName>
          <LastName objectId="">Seinfeld</LastName>
          <Age objectId="5">38</Age>
        </Person>
      </Report>
    """
    election_tree = etree.fromstring(root_string)
    validator = rules.DuplicateID(election_tree, None)

    validator.check()

  def test_object_ids_are_the_same_fails(self):
    root_string = """
      <Report objectId="1">
        <Person objectId="2">
          <FirstName objectId="3">Jerry</FirstName>
          <LastName objectId="4">Seinfeld</LastName>
          <Age objectId="4">38</Age>
        </Person>
      </Report>
    """
    election_tree = etree.fromstring(root_string)
    validator = rules.DuplicateID(election_tree, None)

    with self.assertRaises(loggers.ElectionError):
      validator.check()


class GpUnitOcdIdTest(parameterized.TestCase):
  """GpUnit OCD ID validation tests."""

  def setUp(self):
    super(GpUnitOcdIdTest, self).setUp()
    self.ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        country_code="us",
        local_file=None,
        ocd_id_list=["ocd-division/country:us/state:va"],
    )
    self.gp_unit_ocd_id_validator = rules.GpUnitOcdId(
        None,
        None,
        ocd_id_validator=self.ocd_id_validator,
    )

  def test_gp_unit_without_ocd_id_fails(self):
    ocd_id_string = """
    <GpUnit objectId="1234567890">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>1234567890</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Missing OCD ID</Name>
      <Type>state</Type>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.gp_unit_ocd_id_validator.check(elements)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The GpUnit 1234567890 does not have an ocd-id.",
    )

  def test_gp_unit_with_invalid_ocd_id_fails(self):
    ocd_id_string = """
    <GpUnit objectId="1234567890">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>1234567890</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>invalid-ocd-id</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Invalid OCD ID</Name>
      <Type>state</Type>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.gp_unit_ocd_id_validator.check(elements)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The GpUnit 1234567890 does not have a valid ocd-id: 'invalid-ocd-id'.",
    )

  def test_gp_unit_with_valid_ocd_id_succeeds(self):
    ocd_id_string = """
    <GpUnit objectId="1234567890">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>1234567890</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Virginia</Name>
      <Type>state</Type>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    self.gp_unit_ocd_id_validator.check(elements)

  def test_reporting_device_without_ocd_id_succeeds(self):
    ocd_id_string = """
    <GpUnit objectId="1234567890" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ReportingDevice">
      <Name>Reporting Device</Name>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    self.gp_unit_ocd_id_validator.check(elements)

  @parameterized.parameters(*rules._GPUNIT_TYPES_WITHOUT_OCD_IDS)
  def test_gp_unit_without_ocd_id_is_valid_for_type_succeeds(self, gpunit_type):
    ocd_id_string = f"""
    <GpUnit objectId="1234567890">
      <Name>GpUnit of type: {gpunit_type}</Name>
      <Type>{gpunit_type}</Type>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    self.gp_unit_ocd_id_validator.check(elements)


class DuplicatedGpUnitOcdIdTest(absltest.TestCase):
  """2 GPUnits should not have same OCD ID."""

  def setUp(self):
    super(DuplicatedGpUnitOcdIdTest, self).setUp()
    self.validator = rules.DuplicatedGpUnitOcdId(None, None)

  def test_gp_unit_collection_ocd_id_duplicate_fails(self):
    ocd_id_string = """
    <GpUnitCollection>
     <GpUnit objectId="ru25538">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>2525538</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>ocd-division/country:in/state:wb/cd:bardhaman-durgapur</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Bardhaman Purba</Name>
      <Type>congressional</Type>
    </GpUnit>
    <GpUnit objectId="ru25539">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>2525539</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>ocd-division/country:in/state:wb/cd:bardhaman-durgapur</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Burdwan - Durgapur</Name>
      <Type>congressional</Type>
    </GpUnit>
   </GpUnitCollection>
    """
    elements = etree.fromstring(ocd_id_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(elements)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnits ru25538 and ru25539 have the same ocd-id "
        "ocd-division/country:in/state:wb/cd:bardhaman-durgapur",
    )

  def test_gp_unit_collection_ocd_id_valid_succeeds(self):
    ocd_id_string = """
   <GpUnitCollection>
    <GpUnit objectId="ru-gpu0">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>ocd-division/country:us/state:tx</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>stable-gpu-2lkjg1zsv9j</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <Name>Texas</Name>
      <Type>state</Type>
    </GpUnit>
    <GpUnit objectId="ru-gpu1">
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>ocd-division/country:us/state:vt</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>stable-gpu-wlkj2oijg2g</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      <InternationalizedName>
        <Text language="en">Vermont</Text>
        <Text language="bg">Върмонт</Text>
      </InternationalizedName>
      <Type>state</Type>
    </GpUnit>
   </GpUnitCollection>
   """
    elements = etree.fromstring(ocd_id_string)

    self.validator.check(elements)


class ValidIDREFTest(absltest.TestCase):

  _schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Report"/>
      <xs:complexType name="Office">
        <xs:sequence>
            <xs:element minOccurs="0" name="ElectoralDistrictId" type="xs:IDREF" />
            <xs:element minOccurs="0" name="FilingDeadline" type="xs:date" />
            <xs:element minOccurs="0" name="IsPartisan" type="xs:boolean" />
            <xs:element minOccurs="0" name="OfficeHolderPersonIds" type="xs:IDREFS" />
        </xs:sequence>
      </xs:complexType>
      <xs:complexType name="Contest">
        <xs:sequence>
            <xs:element minOccurs="0" name="ElectoralDistrictId" type="xs:IDREF" />
            <xs:element minOccurs="0" name="BallotTitle" type="InternationalText" />
        </xs:sequence>
      </xs:complexType>
      <xs:complexType name="PartyLeadership">
        <xs:sequence>
            <xs:element maxOccurs="1" minOccurs="1" name="PartyLeaderId" type="xs:IDREF"/>
        </xs:sequence>
      </xs:complexType>
    </xs:schema>
  """)

  _root_string = """
    <Report>
      <PersonCollection>
        <Person objectId="per001">
          <FirstName>Jerry</FirstName>
          <LastName>Seinfeld</LastName>
        </Person>
        <Person objectId="per002">
          <FirstName>George</FirstName>
          <LastName>Costanza</LastName>
        </Person>
        <Person objectId="">
          <FirstName>Elaine</FirstName>
          <LastName>Benes</LastName>
        </Person>
      </PersonCollection>
      <CandidateCollection>
        <Candidate objectId="can001">
          <FirstName>George</FirstName>
          <LastName>Costanza</LastName>
          <PersonId>per002</PersonId>
        </Candidate>
      </CandidateCollection>
    </Report>
  """

  # setup test
  def test_generates_two_mappings_and_sets_them_as_instance_variables_succeeds(
      self,
  ):
    expected_obj_id_mapping = {
        "Person": {"per0001"},
        "Candidate": {"can0001"},
    }
    expected_elem_ref_mapping = {
        "PersonId": "Person",
        "ElectoralDistrictId": "GpUnit",
    }
    validator = rules.ValidIDREF(None, None)
    obj_id_mock = MagicMock(return_value=expected_obj_id_mapping)
    validator._gather_object_ids_by_type = obj_id_mock
    elem_ref_mock = MagicMock(return_value=expected_elem_ref_mapping)
    validator._gather_reference_mapping = elem_ref_mock
    validator.setup()

    self.assertEqual(validator.object_id_mapping, expected_obj_id_mapping)
    self.assertEqual(
        validator.element_reference_mapping, expected_elem_ref_mapping
    )

  # _gather_object_ids_by_type test
  def test_map_of_element_types_to_set_of_object_ids_succeeds(self):
    element_tree = etree.fromstring(self._root_string)
    validator = rules.ValidIDREF(element_tree, None)
    expected_id_mapping = {
        "Person": {"per001", "per002"},
        "Candidate": {"can001"},
    }

    actual_id_mapping = validator._gather_object_ids_by_type()

    self.assertEqual(actual_id_mapping, expected_id_mapping)

  # _gather_reference_mapping test
  def test_map_of_idrefs_to_reference_types_succeeds(self):
    validator = rules.ValidIDREF(None, ValidIDREFTest._schema_tree)
    validator.object_id_mapping = {
        "Person": {"per001", "per002"},
        "Candidate": {"can001"},
    }
    expected_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
        "PartyLeaderId": "Person",
    }
    actual_reference_mapping = validator._gather_reference_mapping()

    self.assertEqual(actual_reference_mapping, expected_reference_mapping)

  # _determine_reference_type test
  def test_the_name_of_the_reference_type_for_given_element_name_succeeds(
      self,
  ):
    validator = rules.ValidIDREF(None, None)
    validator.object_id_mapping = {
        "GpUnit": ["gp001"],
        "Party": ["par001"],
        "Person": ["per001"],
        "Office": ["off001"],
        "Candidate": ["can001"],
        "Contest": ["con001"],
        "BallotSelection": ["bs001"],
    }
    ref_type_mappings = {
        "GpUnitId": "GpUnit",
        "GpUnitIds": "GpUnit",
        "ElectoralDistrictId": "GpUnit",
        "ElectionScopeId": "GpUnit",
        "ComposingGpUnitIds": "GpUnit",
        "PartyScopeGpUnitIds": "GpUnit",
        "PartyId": "Party",
        "PartyIds": "Party",
        "PrimaryPartyIds": "Party",
        "EndorsementPartyIds": "Party",
        "PersonId": "Person",
        "ElectionOfficialPersonIds": "Person",
        "OfficeHolderPersonIds": "Person",
        "AuthorityId": "Person",
        "AuthorityIds": "Person",
        "OfficeId": "Office",
        "OfficeIds": "Office",
        "CandidateId": "Candidate",
        "CandidateIds": "Candidate",
        "ContestId": "Contest",
        "ContestIds": "Contest",
        "OrderedBallotSelectionIds": "BallotSelection",
        "ElementIsIncorrectlyIDREF": None,
    }
    for ref_elem, expected_ref_type in ref_type_mappings.items():
      actual_ref_type = validator._determine_reference_type(ref_elem)
      try:
        self.assertEqual(actual_ref_type, expected_ref_type)
      except AssertionError:
        self.fail(
            (
                "Expected {} to have a reference type of {}. Instead got {}"
            ).format(ref_elem, expected_ref_type, actual_ref_type)
        )

  # elements test
  def test_list_of_keys_from_element_reference_mapping_succeeds(self):
    validator = rules.ValidIDREF(None, None)
    validator.element_reference_mapping = {
        "PersonId": "Person",
        "ElectoralDistrictId": "GpUnit",
    }

    self.assertEqual(validator.elements(), ["PersonId", "ElectoralDistrictId"])

  # check test
  def test_idref_elements_reference_the_proper_type_succeeds(self):
    validator = rules.ValidIDREF(None, None)
    validator.object_id_mapping = {
        "Person": {"per001", "per002"},
        "GpUnit": {"gp001", "gp002"},
    }
    validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
        "PartyLeaderId": "Person",
    }
    idref_element = etree.fromstring("""
      <ElectoralDistrictId>gp001</ElectoralDistrictId>
    """)
    party_leader_id_element = etree.fromstring("""
      <PartyLeaderId>per001</PartyLeaderId>
    """)
    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per001 per002</OfficeHolderPersonIds>
    """)
    empty_element = etree.fromstring("""
      <ElectoralDistrictId></ElectoralDistrictId>
    """)

    validator.check(idref_element)
    validator.check(party_leader_id_element)
    validator.check(idrefs_element)
    validator.check(empty_element)

  def test_idref_elements_fail_to_reference_the_proper_type_fails(
      self,
  ):
    validator = rules.ValidIDREF(None, None)
    validator.object_id_mapping = {
        "Person": {"per001", "per002"},
        "GpUnit": {"gp001", "gp002"},
    }
    validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }
    idref_element = etree.fromstring("""
      <ElectoralDistrictId>gp004</ElectoralDistrictId>
    """)
    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per004 per005</OfficeHolderPersonIds>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(idref_element)
    self.assertIn(
        (
            "gp004 is not a valid IDREF. ElectoralDistrictId should contain an "
            "objectId from a GpUnit element."
        ),
        context.exception.log_entry[0].message,
    )
    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(idrefs_element)
    self.assertIn(
        (
            "per004 is not a valid IDREF. OfficeHolderPersonIds should contain"
            " an objectId from a Person element."
        ),
        context.exception.log_entry[0].message,
    )
    self.assertIn(
        (
            "per005 is not a valid IDREF. OfficeHolderPersonIds should contain"
            " an objectId from a Person element."
        ),
        context.exception.log_entry[1].message,
    )

  def test_reference_type_not_present_fails(self):
    validator = rules.ValidIDREF(None, None)
    validator.object_id_mapping = {
        "GpUnit": {"gp001", "gp002"},
    }
    validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }
    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per004 per005</OfficeHolderPersonIds>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(idrefs_element)
    self.assertIn(
        (
            "per004 is not a valid IDREF. OfficeHolderPersonIds should contain"
            " an objectId from a Person element."
        ),
        context.exception.log_entry[0].message,
    )
    self.assertIn(
        (
            "per005 is not a valid IDREF. OfficeHolderPersonIds should contain"
            " an objectId from a Person element."
        ),
        context.exception.log_entry[1].message,
    )


class BadCharactersInPersonFullNameTest(absltest.TestCase):

  def setUp(self):
    super(BadCharactersInPersonFullNameTest, self).setUp()
    self.validator = rules.BadCharactersInPersonFullName(None, None)

  def test_person_fullname_valid_succeeds(self):
    root_string = """
       <Person>
         <FullName>
           <Text language="en">Richard J. Washburne</Text>
         </FullName>
       </Person>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)

  def test_person_fullname_valid_alias_succeeds(self):
    root_string = """
      <Person>
        <FullName>
          <Text language="en">Jidalias Dos Anjos Pinto</Text>
        </FullName>
      </Person>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)

  def test_person_fullname_in_valid_special_characters_warns(self):
    root_string = """
        <Person>
          <FullName>
            <Text language="en">Richard J@ Washburne</Text>
          </FullName>
        </Person>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Person has known bad characters in FullName field.",
    )

  def test_person_fullname_in_valid_alias_warns(self):
    root_string = """
        <Person>
          <FullName>
            <Text language="en">Richard J Alias Washburne</Text>
          </FullName>
        </Person>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Person has known bad characters in FullName field."
        " Aliases should be included in Nickname field.",
    )


class DuplicateGpUnitsTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateGpUnitsTest, self).setUp()
    self.validator = rules.DuplicateGpUnits(None, None)
    self.root_string = """
    <GpUnitCollection>
    {}
    </GpUnitCollection>
    """

  def test_no_gp_units_succeeds(self):
    self.validator.check(etree.fromstring(self.root_string))

  def test_no_object_ids_succeeds(self):
    test_string = """
      <GpUnit>
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <ComposingGpUnitIds>xyz987</ComposingGpUnitIds>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """

    self.validator.check(etree.fromstring(self.root_string.format(test_string)))

  def test_no_composing_gp_units_succeeds(self):
    test_string = """
      <GpUnit>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """

    self.validator.check(etree.fromstring(self.root_string.format(test_string)))

  def test_no_composing_gp_units_text_succeeds(self):
    test_string = """
      <GpUnit>
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """

    self.validator.check(etree.fromstring(self.root_string.format(test_string)))

  def test_processes_collection_and_does_not_find_duplicates_succeeds(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0003">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <ComposingGpUnitIds>xyz987</ComposingGpUnitIds>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """

    self.validator.check(etree.fromstring(self.root_string.format(test_string)))

  def test_processes_collection_and_finds_duplicate_paths_fails(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="abc123">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0004">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(
          etree.fromstring(self.root_string.format(test_string))
      )
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnits ('ru0002', 'ru0004') are duplicates",
    )

  def test_processes_collection_and_finds_duplicate_object_ids_fails(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="abc123">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc124</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(
          etree.fromstring(self.root_string.format(test_string))
      )
    self.assertEqual(
        context.exception.log_entry[0].message, "GpUnit is duplicated"
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "ru0002",
    )

  def test_finds_duplicate_object_ids_and_duplicate_paths_fails(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0004">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(
          etree.fromstring(self.root_string.format(test_string))
      )
    self.assertEqual(
        context.exception.log_entry[0].message, "GpUnit is duplicated"
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "ru0002",
    )
    self.assertIn(
        "GpUnits ('ru0002', 'ru0004') are duplicates",
        context.exception.log_entry[1].message,
    )


class OtherTypeTest(absltest.TestCase):

  def setUp(self):
    super(OtherTypeTest, self).setUp()
    self.validator = rules.OtherType(None, None)

  def test_complex_types_that_contain_other_type_element_succeeds(
      self,
  ):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report"/>
        <xs:complexType name="Device">
          <xs:sequence>
              <xs:element minOccurs="0" name="Manufacturer" type="xs:string" />
              <xs:element minOccurs="0" name="Model" type="xs:string" />
              <xs:element minOccurs="0" name="Type" type="DeviceType" />
              <xs:element minOccurs="0" name="OtherType" type="xs:string" />
          </xs:sequence>
        </xs:complexType>
      </xs:schema>
    """)
    validator = rules.OtherType(None, schema_tree)
    eligible_elements = validator.elements()

    self.assertEqual(eligible_elements, ["Device"])

  def test_other_type_succeeds(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
        <OtherType>Best phone ever</OtherType>
      </Device>
    """
    complex_element = etree.fromstring(complex_element_string)

    self.validator.check(complex_element)

  def test_elements_with_no_type_succeeds(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
      </Device>
    """
    complex_element = etree.fromstring(complex_element_string)

    self.validator.check(complex_element)

  def test_other_type_not_present_fails(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
      </Device>
    """
    complex_element = etree.fromstring(complex_element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(complex_element)

  def test_other_type_set_but_type_not_set_to_other_fails(
      self,
  ):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>phone</Type>
        <OtherType>Best phone ever</OtherType>
      </Device>
    """
    complex_element = etree.fromstring(complex_element_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(complex_element)


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
    validator = rules.PartisanPrimary(election_tree, None)

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

    rules.PartisanPrimary(root, None).check(election)

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
      rules.PartisanPrimary(root, None).check(election)

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
      rules.PartisanPrimary(root, None).check(election)

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
      rules.PartisanPrimary(root, None).check(election)

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
      rules.PartisanPrimary(root, None).check(election)

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

    rules.PartisanPrimary(root, None).check(election)

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

    rules.PartisanPrimary(root, None).check(election)

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

    rules.PartisanPrimary(root, None).check(election)

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

      rules.PartisanPrimary(root, None).check(election)


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
    validator = rules.PartisanPrimaryHeuristic(election_tree, None)

    self.assertEqual(["Election"], validator.elements())

  def test_contests_that_do_not_suggest_primary_no_name_succeeds(self):
    root_string = self._base_candidate_contest
    root = etree.fromstring(root_string)
    election = root.find("Election")

    rules.PartisanPrimaryHeuristic(root, None).check(election)

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

    rules.PartisanPrimaryHeuristic(root, None).check(election)

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
      rules.PartisanPrimaryHeuristic(root, None).check(election)

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
      rules.PartisanPrimaryHeuristic(root, None).check(election)

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
      rules.PartisanPrimaryHeuristic(root, None).check(election)


class CoalitionPartiesTest(absltest.TestCase):

  _base_election_coalition = """
      <Coalition>
        {}
      </Coalition>
  """

  def test_each_coalition_has_defined_party_id_succeeds(self):
    coalition_details = "<PartyIds>abc123</PartyIds>"
    defined_party_string = self._base_election_coalition.format(
        coalition_details
    )
    element = etree.fromstring(defined_party_string)

    rules.CoalitionParties(None, None).check(element)

  def test_coalition_does_not_define_party_id_no_party_id_fails(
      self,
  ):
    no_party_string = self._base_election_coalition.format("")
    element = etree.fromstring(no_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)

  def test_coalition_does_not_define_party_id_empty_party_id_fails(
      self,
  ):
    coalition_details = "<PartyIds></PartyIds>"
    empty_party_string = self._base_election_coalition.format(coalition_details)
    element = etree.fromstring(empty_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)

  def test_coalition_does_not_define_party_id_whitespace_fails(
      self,
  ):
    coalition_details = "<PartyIds>     </PartyIds>"
    all_space_party_string = self._base_election_coalition.format(
        coalition_details
    )
    element = etree.fromstring(all_space_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)


class UniqueLabelTest(absltest.TestCase):

  def test_elements_with_type_internationalized_text_succeeds(self):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType">
          <xs:complexType name="ContactInformation">
            <xs:sequence>
                <xs:element maxOccurs="unbounded" minOccurs="0" name="AddressLine" type="xs:string" />
                <xs:element maxOccurs="1" minOccurs="0" name="Directions" type="InternationalizedText" />
            </xs:sequence>
          </xs:complexType>
          <xs:complexType name="PollingInformation">
            <xs:sequence>
                <xs:element maxOccurs="unbounded" minOccurs="0" name="AddressLine" type="xs:string" />
                <xs:element maxOccurs="1" minOccurs="0" name="Directions" type="InternationalizedText" />
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:schema>
    """)
    validator = rules.UniqueLabel(None, schema_tree)

    self.assertEqual(["Directions"], validator.elements())

  def test_all_labels_are_unique_succeeds(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    validator = rules.UniqueLabel(None, None)

    validator.check(element)
    no_element_label_string = """
      <Directions/>
    """
    element = etree.fromstring(no_element_label_string)
    validator = rules.UniqueLabel(None, None)
    validator.check(element)

  def test_not_all_labels_are_unique_fails(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    validator = rules.UniqueLabel(None, None)
    validator.labels = {"us-standard"}

    with self.assertRaises(loggers.ElectionError):
      validator.check(element)


class CandidatesReferencedInRelatedContestsTest(absltest.TestCase):

  def setUp(self):
    super(CandidatesReferencedInRelatedContestsTest, self).setUp()
    self.validator = rules.CandidatesReferencedInRelatedContests(None, None)

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

  def test_contest_trees_not_related_subsequent_rel_succeeds(
      self,
  ):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <SubsequentContestId>con002</SubsequentContestId>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003">
          <SubsequentContestId>con004</SubsequentContestId>
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
          <SubsequentContestId>con002</SubsequentContestId>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003">
          <SubsequentContestId>con004</SubsequentContestId>
        </Contest>
        <Contest objectId="con004"/>
        <Contest objectId="con005">
          <SubsequentContestId>con006</SubsequentContestId>
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
          <ComposingContestIds>con002</ComposingContestIds>
          <SubsequentContestId>con003</SubsequentContestId>
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

  def test_repeat_candidates_in_composing_contests_fails(self):
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

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(report_elem)
    self.assertLen(context.exception.log_entry, 2)
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Candidate can001 appears in the following contests"
            " which are not all related: con001, con002"
        ),
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        (
            "Candidate can002 appears in the following contests"
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
    self.validator = rules.ProperBallotSelection(None, None)

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
    self.validator = rules.CorrectCandidateSelectionCount(None, None)

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
    self.validator = rules.SingularPartySelection(None, None)

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
      rules.ValidateDuplicateColors(election_tree, None).check()
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
      rules.ValidateDuplicateColors(election_tree, None).check()
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
      rules.ValidateDuplicateColors(election_tree, None).check()
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
      rules.ValidateDuplicateColors(election_tree, None).check()
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

    rules.ValidateDuplicateColors(election_tree, None).check()

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
      rules.ValidateDuplicateColors(election_tree, None).check()
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
      rules.ValidateDuplicateColors(election_tree, None).check()
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

    rules.ValidateDuplicateColors(election_tree, None).check()


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
    validator = rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
        election_tree, None
    )

    validator.check()

  def test_invalid_multiple_candidates_point_to_the_same_person_in_same_contest_fails(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per3", personid4="per3"
    )
    election_tree = etree.fromstring(test_string)
    validator = rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
        election_tree, None
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
    validator = rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
        election_tree, None
    )

    validator.check()

  def test_invalid_multiple_candidates_point_to_the_same_person_in_same_contest_with_two_contests_fails(
      self,
  ):
    test_string = self.base_string_multiple_contest.format(
        personid1="per1", personid2="per2", personid3="per1", personid4="per1"
    )
    election_tree = etree.fromstring(test_string)
    validator = rules.MultipleCandidatesPointToTheSamePersonInTheSameContest(
        election_tree, None
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
    self.validator = rules.SelfDeclaredCandidateMethod(None, None)

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
    self.validator = rules.DuplicatedPartyAbbreviation(None, None)

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


class PersonHasUniqueFullNameTest(absltest.TestCase):

  def setUp(self):
    super(PersonHasUniqueFullNameTest, self).setUp()
    self.validator = rules.PersonHasUniqueFullName(None, None)

  def test_empty_person_collection_raises_info(self):
    root_string = """
      <PersonCollection>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "<PersonCollection> does not have <Person> objects",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "PersonCollection"
    )

  def test_person_collection_with_duplicated_full_name_without_birthday_raises_info(
      self,
  ):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6459172">
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
        </Person>
        <Person objectId="per_gb_6436252">
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertIn(
        "Person has same full name", context.exception.log_entry[0].message
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "per_gb_6436252",
    )

  def test_person_collection_with_duplicated_full_name_with_birthday_raises_info(
      self,
  ):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6456562">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
        <Person objectId="per_gb_64201052">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(element)
    self.assertIn(
        "Person has same full name", context.exception.log_entry[0].message
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "per_gb_64201052",
    )

  def test_person_collection_with_duplicated_full_name_but_different_birthday_succeeds(
      self,
  ):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_600452">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
        <Person objectId="per_gb_6456322">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1972-11-20</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)

  def test_person_collection_without_any_succeeds(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_64532">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1992-12-20</DateOfBirth>
        </Person>
        <Person objectId="per_gb_647752">
          <FirstName>Arthur</FirstName>
          <FullName>
            <Text language="en">Arthur Maupassant Maurice</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Maurice</LastName>
          <MiddleName>Maupassant</MiddleName>
          <DateOfBirth>1972-11-20</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)

    self.validator.check(element)


class DuplicatedPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyNameTest, self).setUp()
    self.validator = rules.DuplicatedPartyName(None, None)

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
    self.validator = rules.MissingPartyNameTranslation(None, None)

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
    self.validator = rules.MissingPartyAbbreviationTranslation(None, None)

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


class IndependentPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(IndependentPartyNameTest, self).setUp()
    self.validator = rules.IndependentPartyName(None, None)

  def test_independent_party_warns(self):
    party = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Independent</Text>
          </Name>
        </Party>
        """
    party_elem = etree.fromstring(party)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(party_elem)

  def test_nonpartisan_party_warns(self):
    party = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">nonpartisan</Text>
          </Name>
        </Party>
        """
    party_elem = etree.fromstring(party)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(party_elem)

  def test_no_warn_on_party_with_is_independent_succeeds(self):
    party = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Independent</Text>
          </Name>
          <IsIndependent>true</IsIndependent>
        </Party>
        """
    party_elem = etree.fromstring(party)

    self.validator.check(party_elem)


class DuplicateContestNamesTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateContestNamesTest, self).setUp()
    self.validator = rules.DuplicateContestNames(None, None)
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
    self.duplicate_validator = rules.DuplicateBallotTitleSeatPair(None, None)
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


class ValidStableIDTest(absltest.TestCase):

  def setUp(self):
    super(ValidStableIDTest, self).setUp()
    self.root_string = """
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>{}</Type>
          {}
          <Value>{}</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """
    self.stable_string = "<OtherType>stable</OtherType>"
    self.validator = rules.ValidStableID(None, None)

  def test_valid_stable_id_succeeds(self):
    test_string = self.root_string.format(
        "other", self.stable_string, "vageneral-cand-2013-va-obama"
    )

    self.validator.check(etree.fromstring(test_string))

  def test_non_stable_id_other_types_dont_throw_succeeds(self):
    test_string = self.root_string.format(
        "other",
        "<OtherType>anothertype</OtherType>",
        "vageneral-cand-2013-va-obama",
    )

    self.validator.check(etree.fromstring(test_string))

  def test_non_stable_id_types_dont_throw_succeeds(self):
    test_string = self.root_string.format(
        "ocd-id", "", "ocd-id/country/state/thing"
    )

    self.validator.check(etree.fromstring(test_string))

  def test_invalid_stable_id_fails(self):
    test_string = self.root_string.format(
        "other", self.stable_string, "cand-2013-va-obama!"
    )

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Stable id 'cand-2013-va-obama!' is not in the correct format.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "ExternalIdentifiers"
    )

  def test_empty_stable_id_fails(self):
    test_string = self.root_string.format("other", self.stable_string, "   ")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(test_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Stable id '   ' is not in the correct format.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "ExternalIdentifiers"
    )


class UniqueStableIDTest(absltest.TestCase):

  def setUp(self):
    super(UniqueStableIDTest, self).setUp()
    self.root_string = """
    <ElectionReport>
      <Election objectId="el0110">
        <OfficeCollection>
          <Office objectId="off04_AS">
            <ExternalIdentifiers>
              <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>stable</OtherType>
              <Value>{office_obj_off04_AS}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
          <Office objectId= "off04_A">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>stable</OtherType>
                <Value>{office_obj_off04_A}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        </OfficeCollection>
        <CandidateCollection>
          <Candidate objectId="can1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>stable</OtherType>
                <Value>{candidate_obj_can1}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Candidate>
          <Candidate objectId="can2">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>stable</OtherType>
                <Value>{candidate_obj_can2}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Candidate>
          <Candidate objectId="can3">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>stable</OtherType>
                <Value>{candidate_obj_can3}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Candidate>
        </CandidateCollection>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>{election_obj_el0110}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Election>
      <Election>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>{election_obj_pangaea}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <Name>
          <Text language="en">Pangaea election</Text>
        </Name>
      </Election>
     </ElectionReport>
  """

  def test_unique_stable_id_pass_succeeds(self):
    test_string = self.root_string.format(
        office_obj_off04_AS="04_AS",
        office_obj_off04_A="04_A",
        candidate_obj_can1="stable-can-1",
        candidate_obj_can2="stable-can-2",
        candidate_obj_can3="stable-can-3",
        election_obj_el0110="election-1",
        election_obj_pangaea="election-2",
    )
    election_tree = etree.fromstring(test_string)

    rules.UniqueStableID(election_tree, None).check()

  def test_unique_stable_id_fails(self):
    test_string = self.root_string.format(
        office_obj_off04_AS="04_AS",
        office_obj_off04_A="04_A",
        candidate_obj_can1="04_AS",
        candidate_obj_can2="stable-can-2",
        candidate_obj_can3="stable-can-3",
        election_obj_el0110="election-1",
        election_obj_pangaea="election-2",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      rules.UniqueStableID(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Stable ID 04_AS is not unique as it is mapped in ['off04_AS', 'can1']",
    )

  def test_unique_stable_id_fail_multiple_elements_fails(self):
    test_string = self.root_string.format(
        office_obj_off04_AS="04_AS",
        office_obj_off04_A="04_A",
        candidate_obj_can1="04_AS",
        candidate_obj_can2="stable-can-2",
        candidate_obj_can3="stable-can-3",
        election_obj_el0110="election-1",
        election_obj_pangaea="election-1",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      rules.UniqueStableID(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Stable ID 04_AS is not unique as it is mapped in ['off04_AS', 'can1']",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "Stable ID election-1 is not unique as it is mapped in ['el0110',"
        " 'Pangaea election']",
    )

  def test_unique_stable_id_fail_three_elements_fails(self):
    test_string = self.root_string.format(
        office_obj_off04_AS="04_AS",
        office_obj_off04_A="04_A",
        candidate_obj_can1="04_AS",
        candidate_obj_can2="04_A",
        candidate_obj_can3="04_A",
        election_obj_el0110="election-1",
        election_obj_pangaea="election-2",
    )
    election_tree = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      rules.UniqueStableID(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Stable ID 04_AS is not unique as it is mapped in ['off04_AS', 'can1']",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "Stable ID 04_A is not unique as it is mapped in ['off04_A', 'can2',"
        " 'can3']",
    )


class MissingStableIdsTest(parameterized.TestCase):

  def setUp(self):
    super(MissingStableIdsTest, self).setUp()
    self.validator = rules.MissingStableIds(None, None)

  def test_elements_succeeds(self):
    self.assertEqual(
        self.validator.elements(),
        rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS,
    )

  @parameterized.parameters(*rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS)
  def test_stable_id_present_succeeds(self, element_name):
    element = etree.fromstring(f"""
      <{element_name} objectId='obj1'>
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>stable</OtherType>
          <Value>stable1</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      </{element_name}>
    """)

    self.validator.check(element)

  @parameterized.parameters(*rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS)
  def test_stable_id_missing_fails(self, element_name):
    element = etree.fromstring(f"""
      <{element_name} objectId='obj1'></{element_name}>
    """)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element is missing a stable id",
    )


class PersonsMissingPartyDataTest(absltest.TestCase):

  def setUp(self):
    super(PersonsMissingPartyDataTest, self).setUp()
    self.validator = rules.PersonsMissingPartyData(None, None)

  def test_person_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Person"])

  def test_given_person_element_has_party_id_with_a_value_in_it_succeeds(self):
    element_string = """
      <Person objectId="p1">
        <PartyId>par1</PartyId>
      </Person>
    """

    self.validator.check(etree.fromstring(element_string))

  def test_missing_or_empty_party_id_warns(self):
    element_string = """
      <Person objectId="p1">
        <PartyId></PartyId>
      </Person>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(etree.fromstring(element_string))


class AllCapsTest(absltest.TestCase):

  def setUp(self):
    super(AllCapsTest, self).setUp()
    self.validator = rules.AllCaps(None, None)

  def test_listed_elements_succeeds(self):
    expected_elements = [
        "Candidate",
        "CandidateContest",
        "PartyContest",
        "Person",
    ]

    self.assertEqual(self.validator.elements(), expected_elements)

  def test_candidate_ballot_names_not_all_caps_succeeds(
      self,
  ):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>Deandra Reynolds</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    self.validator.check(element)

  def test_candidate_elements_with_no_ballot_name_succeeds(self):
    no_ballot_name_string = """
      <Candidate/>
    """
    element = etree.fromstring(no_ballot_name_string)

    self.validator.check(element)

  def test_candidate_elements_with_no_text_succeeds(self):
    no_text_string = """
      <Candidate>
        <BallotName/>
      </Candidate>
    """
    element = etree.fromstring(no_text_string)

    self.validator.check(element)

  def test_candidate_ballot_name_is_all_caps_warns(self):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>DEANDRA REYNOLDS</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(element)

  def test_candidate_contest_names_not_all_caps_succeeds(
      self,
  ):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="CandidateContest">
                <Name>Deandra Reynolds</Name>
             </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    self.validator.check(
        root_element.find("Election//ContestCollection//Contest")
    )

  def test_candidate_contest_elements_with_no_name_succeeds(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="CandidateContest">
             </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    self.validator.check(
        root_element.find("Election//ContestCollection//Contest")
    )

  def test_candidate_contest_name_is_all_caps_warns(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="CandidateContest">
                <Name>DEANDRA REYNOLDS</Name>
             </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(
          root_element.find("Election//ContestCollection//Contest")
      )

  def test_party_contest_names_not_all_caps_succeeds(
      self,
  ):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="PartyContest">
                <Name>Deandra Reynolds</Name>
             </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    self.validator.check(
        root_element.find("Election//ContestCollection//Contest")
    )

  def test_party_contest_elements_with_no_name_succeeds(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="PartyContest">
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    self.validator.check(
        root_element.find("Election//ContestCollection//Contest")
    )

  def test_party_contest_name_is_all_caps_warns(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <ContestCollection>
            <Contest objectId="con987" xsi:type="PartyContest">
              <Name>DEANDRA REYNOLDS</Name>
            </Contest>
          </ContestCollection>
        </Election>
      </ElectionReport>
    """
    root_element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(
          root_element.find("Election//ContestCollection//Contest")
      )

  def test_person_elements_with_no_full_name_succeeds(self):
    no_full_name_string = """
      <Person/>
    """
    element = etree.fromstring(no_full_name_string)

    self.validator.check(element)

  def test_person_elements_with_no_text_succeeds(self):
    no_text_string = """
      <Person>
        <FullName/>
      </Person>
    """
    element = etree.fromstring(no_text_string)

    self.validator.check(element)

  def test_full_names_all_caps_warns(self):
    person_string = """
      <Person>
        <FullName>
          <Text>DEANDRA REYNOLDS</Text>
        </FullName>
      </Person>
    """
    element = etree.fromstring(person_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.validator.check(element)


class AllLanguagesTest(absltest.TestCase):

  def setUp(self):
    super(AllLanguagesTest, self).setUp()
    self.validator = rules.AllLanguages(None, None)

  def test_listed_elements_succeeds(self):
    expected_elements = ["BallotName", "BallotTitle", "FullName", "Name"]

    self.assertEqual(self.validator.elements(), expected_elements)

  def test_given_element_has_text_for_each_required_language_succeeds(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.validator.required_languages = ["en", "es", "nl"]

    self.validator.check(etree.fromstring(root_string))

  def test_given_element_can_support_more_than_required_languages_succeeds(
      self,
  ):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.validator.required_languages = ["en"]

    self.validator.check(etree.fromstring(root_string))

  def test_required_language_is_missing_fails(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
      </FullName>
    """
    self.validator.required_languages = ["en", "es", "nl"]

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(root_string))

  def test_elements_without_text_elements_succeeds(self):
    empty_element_string = """
      <BallotName/>
    """

    self.validator.check(etree.fromstring(empty_element_string))


class ValidEnumerationsTest(absltest.TestCase):

  def setUp(self):
    super(ValidEnumerationsTest, self).setUp()
    self.validator = rules.ValidEnumerations(None, None)

  def test_elements_with_other_type_succeeds(
      self,
  ):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report"/>
        <xs:simpleType name="BallotMeasureType">
          <xs:restriction base="xs:string">
              <xs:enumeration value="ballot-measure" />
              <xs:enumeration value="initiative" />
              <xs:enumeration value="referendum" />
              <xs:enumeration value="other" />
          </xs:restriction>
        </xs:simpleType>
        <xs:complexType name="Person">
          <xs:sequence>
            <xs:element minOccurs="1" type="xs:string" name="FirstName" />
            <xs:element minOccurs="1" type="xs:string" name="LastName" />
            <xs:element minOccurs="0" type="xs:integer" name="Age" />
            <xs:element minOccurs="0" type="xs:string" name="OtherType" />
          </xs:sequence>
        </xs:complexType>
      </xs:schema>
    """)
    validator = rules.ValidEnumerations(None, schema_tree)
    expected_enumerations = ["ballot-measure", "initiative", "referendum"]
    elements = validator.elements()

    self.assertEqual(validator.valid_enumerations, expected_enumerations)
    self.assertEqual(elements, ["Person"])

  def test_elements_of_type_other_do_not_use_valid_enumeration_in_other_type_field_succeeds(
      self,
  ):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>state</Type>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.validator.valid_enumerations = ["state"]

    self.validator.check(element)

  def test_other_type_field_has_valid_enumeration_as_a_value_fails(
      self,
  ):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>other</Type>
      <OtherType>state</OtherType>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.validator.valid_enumerations = ["state"]

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_elements_of_type_other_for_external_identifier_elements_succeeds(
      self,
  ):
    type_other_string = """
      <ExternalIdentifier>
        <Type>stable</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.validator.valid_enumerations = ["stable"]

    self.validator.check(element)

  def test_external_identifier_for_valid_enumeration_set_as_other_type_fails(
      self,
  ):
    type_other_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <OtherType>stable</OtherType>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.validator.valid_enumerations = ["stable"]

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(element)

  def test_elements_with_no_type_or_other_type_succeeds(self):
    no_type_string = """
      <ExternalIdentifier>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_type_string)

    self.validator.check(element)
    no_other_type_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_other_type_string)
    self.validator.check(element)


class ValidateOcdidLowerCaseTest(absltest.TestCase):

  def setUp(self):
    super(ValidateOcdidLowerCaseTest, self).setUp()
    self.validator = rules.ValidateOcdidLowerCase(None, None)
    self.ext_ids_str = """
    <ExternalIdentifiers>
      <ExternalIdentifier>
       {}
       {}
      </ExternalIdentifier>
    </ExternalIdentifiers>
    """

  def test_external_identifiers_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["ExternalIdentifiers"])

  def test_ocd_ids_are_all_lower_case_succeeds(self):
    valid_id_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>", "<Value>ocd-division/country:us/state:va</Value>"
    )

    self.validator.check(etree.fromstring(valid_id_string))

  def test_ocd_id_has_upper_case_letter_warns(self):
    uppercase_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>", "<Value>ocd-division/country:us/state:VA</Value>"
    )

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(uppercase_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "OCD-ID ocd-division/country:us/state:VA is not in all "
            "lower case letters. Valid OCD-IDs should be all "
            "lowercase."
        ),
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "ExternalIdentifiers"
    )

  def test_elements_without_valid_ocd_id_xml_succeeds(self):
    no_type_string = self.ext_ids_str.format("", "")

    self.validator.check(etree.fromstring(no_type_string))
    non_ocd_id_string = self.ext_ids_str.format("<Type>not-ocd-id</Type>", "")
    self.validator.check(etree.fromstring(non_ocd_id_string))
    ocd_id_missing_value_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>", ""
    )
    self.validator.check(etree.fromstring(ocd_id_missing_value_string))
    empty_value_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>", "<Value></Value>"
    )
    self.validator.check(etree.fromstring(empty_value_string))


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
    self.validator = rules.ContestHasMultipleOffices(None, None)

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
    validator = rules.PersonHasOffice(election_tree, None)
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
    validator = rules.PersonHasOffice(election_tree, None)
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
    validator = rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_no_roots_succeeds(self):
    no_root_string = io.BytesIO(b"<OfficeHolderTenureCollection/>")
    election_tree = etree.parse(no_root_string)
    validator = rules.PersonHasOffice(election_tree, None)

    validator.check()

  def test_no_person_collection_succeeds(self):
    no_collection_string = io.BytesIO(b"""
      <xml>
        <OfficeHolderTenureCollection/>
      </xml>
    """)
    election_tree = etree.parse(no_collection_string)
    validator = rules.PersonHasOffice(election_tree, None)

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
    validator = rules.PersonHasOffice(election_tree, None)

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

    rules.PersonHasOffice(election_tree, None).check()

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
      rules.PersonHasOffice(election_tree, None).check()
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
    validator = rules.PersonHasOffice(election_tree, None)

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

    rules.PersonHasOffice(election_tree, None).check()

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
      rules.PersonHasOffice(election_tree, None).check()
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
      rules.PersonHasOffice(election_tree, None).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has 2 OfficeHolders. Must have exactly one.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "o2"
    )


class PartyLeadershipMustExistTest(absltest.TestCase):

  _party_collection = """
    <PartyCollection>
      <Party>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>Other</Type>
            <OtherType>party-leader-id</OtherType>
            <Value>p2</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
      <Party>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>Other</Type>
            <OtherType>party-chair-id</OtherType>
            <Value>p3</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
    </PartyCollection>
  """

  # _gather_reference_values tests
  def test_set_of_party_leader_ids_succeeds(self):
    root_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.PartyLeadershipMustExist(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"p2", "p3"})

  # _gather_defined_values tests
  def test_set_of_person_object_ids_succeeds(self):
    root_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p4" />
          <Person objectId="p5" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.PartyLeadershipMustExist(election_tree, None)
    defined_values = validator._gather_defined_values()

    self.assertEqual(defined_values, {"p4", "p5"})

  # check tests
  def test_party_leadership_exists_succeeds(self):
    xml_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    election_tree = etree.parse(root_string)

    rules.PartyLeadershipMustExist(election_tree, None).check()

  def test_party_leadership_exists_fails(self):
    xml_string = """
      <xml>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError):
      rules.PartyLeadershipMustExist(election_tree, None).check()


class ProhibitElectionDataTest(absltest.TestCase):

  def test_election_element_is_not_present_succeeds(self):
    root_string = io.BytesIO(b"""
      <xml>
        <PersonCollection/>
      </xml>
    """)
    election_tree = etree.parse(root_string)

    rules.ProhibitElectionData(election_tree, None).check()

  def test_election_element_is_present_fails(self):
    root_string = io.BytesIO(b"""
      <xml>
        <Election/>
      </xml>
    """)
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as context:
      rules.ProhibitElectionData(election_tree, None).check()
    self.assertIn(
        "Election data is prohibited", context.exception.log_entry[0].message
    )


class PersonsHaveValidGenderTest(absltest.TestCase):

  def setUp(self):
    super(PersonsHaveValidGenderTest, self).setUp()
    self.validator = rules.PersonsHaveValidGender(None, None)

  def test_only_gender_elements_are_checked_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Gender"])

  def test_all_persons_have_valid_gender_succeeds(self):
    root_string = """
      <Gender>Female</Gender>
    """
    gender_element = etree.fromstring(root_string)

    self.validator.check(gender_element)

  def test_validation_is_case_insensitive_succeeds(self):
    root_string = """
      <Gender>female</Gender>
    """
    gender_element = etree.fromstring(root_string)

    self.validator.check(gender_element)

  def test_empty_value_succeeds(self):
    root_string = """
      <Gender></Gender>
    """
    gender_element = etree.fromstring(root_string)

    self.validator.check(gender_element)

  def test_invalid_value_fails(self):
    root_string = """
      <Gender>blamo</Gender>
    """
    gender_element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(gender_element)


class VoteCountTypesCoherencyTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountTypesCoherencyTest, self).setUp()
    self.validator = rules.VoteCountTypesCoherency(None, None)
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
    for vc_type in rules.VoteCountTypesCoherency.CAND_VC_TYPES:
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
    for vc_type in rules.VoteCountTypesCoherency.PARTY_VC_TYPES:
      self.assertIn(vc_type, context.exception.log_entry[0].message)
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "pc1"
    )


class VoteCountValidSeatsDeltaTypesTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountValidSeatsDeltaTypesTest, self).setUp()
    self.validator = rules.VoteCountValidSeatsDeltaTypes(None, None)
    self.base_contest = """
        <Contest objectId="pc1" type="PartyContest">
            <BallotSelection objectId="ps1-0">
            <VoteCountsCollection>
                {}
            </VoteCountsCollection>
            </BallotSelection>
        </Contest>
        """

  def test_valid_two_delta_types_succeeds(self):
    # Ensure VoteCountsCollection that contains both seats delta types is valid.
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-delta-mandate</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta-institutional</OtherType>
      </VoteCounts>
    """
    party_contest = self.base_contest.format(vote_counts)

    self.validator.check(etree.fromstring(party_contest))

  def test_invalid_two_mandate_delta_types_warns(self):
    # Ensure VoteCountsCollection that contains both mandate seats delta types
    # is invalid.
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-delta</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta-mandate</OtherType>
      </VoteCounts>
    """
    party_contest = self.base_contest.format(vote_counts)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(party_contest))
    self.assertIn(
        "The VoteCount types seats-delta and seats-delta-mandate should"
        " not coexist within the same BallotSelection (objectId=ps1-0)."
        " They represent the same data, and seats-delta is scheduled"
        " for deprecation.",
        context.exception.log_entry[0].message,
    )

  def test_invalid_only_institutional_delta_types_fails(self):
    # Ensure VoteCountsCollection with only institutional seats delta type is
    # invalid.
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-delta-institutional</OtherType>
      </VoteCounts>
    """
    party_contest = self.base_contest.format(vote_counts)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(party_contest))
    self.assertIn(
        "Missing required field VoteCount type seats-delta-mandate must"
        " be included whenever VoteCount type seats-delta-institutional"
        " is present. (BallotSelection objectId=ps1-0)",
        context.exception.log_entry[0].message,
    )

  @freezegun.freeze_time("2026-06-30")
  def test_info_deprecated_delta_type_warns(self):
    # Ensure VoteCountsCollection with seats-delta type before July 1st, 2026
    # raises an Info message.
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-delta</OtherType>
      </VoteCounts>
    """
    party_contest = self.base_contest.format(vote_counts)

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(party_contest))
    self.assertIn(
        "VoteCount type seats-delta is deprecated and will be removed"
        " on July 1, 2026. Please update your implementation to use"
        " seats-delta-mandate. (BallotSelection objectId=ps1-0)",
        context.exception.log_entry[0].message,
    )

  @freezegun.freeze_time("2026-07-01")
  def test_error_deprecated_delta_type_fails(self):
    # Ensure VoteCountsCollection that contains seats-delta type on and after
    # July 1st, 2026 throws an Error.
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-delta</OtherType>
      </VoteCounts>
    """
    party_contest = self.base_contest.format(vote_counts)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(party_contest))
    self.assertIn(
        "VoteCount type seats-delta is deprecated and was removed on"
        " July 1, 2026. Please update your implementation to use"
        " seats-delta-mandate. (BallotSelection objectId=ps1-0)",
        context.exception.log_entry[0].message,
    )


class URIValidatorTest(absltest.TestCase):

  def setUp(self):
    super(URIValidatorTest, self).setUp()
    self.validator = rules.URIValidator(None, None)
    self.uri_element = "<Uri>{}</Uri>"

  def test_uri_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["Uri"])

  def test_valid_uri_succeeds(self):
    valid_url = self.uri_element.format("http://www.whitehouse.gov")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_non_www_uri_succeeds(self):
    valid_url = self.uri_element.format(
        "https://zh.wikipedia.org/zh-tw/Fake_Page"
    )

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_with_parentheses_succeeds(self):
    valid_url = self.uri_element.format(
        "https://en.wikipedia.org/wiki/Thomas_Jefferson_(Virginia)"
    )

    self.validator.check(etree.fromstring(valid_url))

  def test_uri_not_provided_fails(self):
    invalid_scheme = self.uri_element.format("")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("Missing URI value.", context.exception.log_entry[0].message)

  def test_no_scheme_provided_fails(self):
    missing_scheme = self.uri_element.format("www.whitehouse.gov")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(missing_scheme))
    self.assertIn("protocol - invalid", context.exception.log_entry[0].message)

  def test_scheme_is_not_in_approved_list_fails(self):
    invalid_scheme = self.uri_element.format("tps://www.whitehouse.gov")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("protocol - invalid", context.exception.log_entry[0].message)

  def test_net_location_not_provided_fails(self):
    missing_netloc = self.uri_element.format("missing/loc.md")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(missing_netloc))
    self.assertIn("domain - missing", context.exception.log_entry[0].message)

  def test_uri_not_ascii_fails(self):
    unicode_url = self.uri_element.format("https://nahnah.com/nopê")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(unicode_url))
    self.assertIn("not ascii encoded", context.exception.log_entry[0].message)

  def test_allows_query_params_to_be_included_succeeds(self):
    contains_query = self.uri_element.format(
        "http://www.whitehouse.gov?filter=yesplease"
    )

    self.validator.check(etree.fromstring(contains_query))

  def test_aggregates_errors_fails(self):
    multiple_issues = self.uri_element.format("missing/loc.md?filter=yesplease")

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(multiple_issues))
    self.assertIn("protocol - invalid", context.exception.log_entry[0].message)
    self.assertIn("domain - missing", context.exception.log_entry[0].message)

  def test_valid_uri_https_face_succeeds(self):
    valid_url = self.uri_element.format("https://www.facebook.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_wiki_succeeds(self):
    valid_url = self.uri_element.format("https://www.wikipedia.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_twit_succeeds(self):
    valid_url = self.uri_element.format("https://www.twitter.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_ins_succeeds(self):
    valid_url = self.uri_element.format("https://www.instagram.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_you_succeeds(self):
    valid_url = self.uri_element.format("https://www.youtube.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_tiktok_succeeds(self):
    valid_url = self.uri_element.format("https://www.tiktok.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_web_succeeds(self):
    valid_url = self.uri_element.format("https://www.website.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_lin_succeeds(self):
    valid_url = self.uri_element.format("https://www.linkedin.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_line_succeeds(self):
    valid_url = self.uri_element.format("https://www.line.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_https_ball_succeeds(self):
    valid_url = self.uri_element.format("https://www.ballotpedia.com")

    self.validator.check(etree.fromstring(valid_url))

  def test_valid_uri_http_face_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.facebook.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.facebook.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_wiki_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.wikipedia.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.wikipedia.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_twit_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.twitter.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.twitter.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_ins_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.instagram.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.instagram.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_you_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.youtube.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.youtube.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_web_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.website.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.website.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_lin_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.linkedin.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.linkedin.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_line_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.line.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.line.com'.",
        context.exception.log_entry[0].message,
    )

  def test_valid_uri_http_ball_invalid_raises_info(self):
    invalid_url = self.uri_element.format("http://www.ballotpedia.com")

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(invalid_url))
    self.assertIn(
        "It is recommended to use https instead of http. "
        "The provided URI, 'http://www.ballotpedia.com'.",
        context.exception.log_entry[0].message,
    )


class UniqueURIPerAnnotationCategoryTest(absltest.TestCase):

  _base_person_collection = """
    <PersonCollection>
      <Person objectId="per1">
        <ContactInformation>
          <Uri Annotation="personal-facebook">{0[facebook]}</Uri>
          <Uri Annotation="campaign-website">{0[website]}</Uri>
          <Uri Annotation="wikipedia">{0[wikipedia]}</Uri>
        </ContactInformation>
      </Person>
      <Person objectId="per2">
        <ContactInformation>
          <Uri Annotation="personal-facebook">{1[facebook]}</Uri>
          <Uri Annotation="campaign-website">{1[website]}</Uri>
          <Uri Annotation="wikipedia">{1[wikipedia]}</Uri>
        </ContactInformation>
      </Person>
    </PersonCollection>
  """

  _base_party_collection = """
    <PartyCollection>
      <Party objectId="par1">
        <ContactInformation>
          <Uri Annotation="party-facebook">{0[facebook]}</Uri>
          <Uri Annotation="campaign-website">{0[website]}</Uri>
          <Uri Annotation="wikipedia">{0[wikipedia]}</Uri>
        </ContactInformation>
      </Party>
      <Party objectId="par2">
        <ContactInformation>
          <Uri Annotation="party-facebook">{1[facebook]}</Uri>
          <Uri Annotation="campaign-website">{1[website]}</Uri>
          <Uri Annotation="wikipedia">{1[wikipedia]}</Uri>
        </ContactInformation>
      </Party>
    </PartyCollection>
  """

  _office_collection = """
    <OfficeCollection>
      <Office objectId="off1">
        <ContactInformation>
          <Uri Annotation="wikipedia">https://wikipedia.com/ignorethisdup</Uri>
        </ContactInformation>
      </Office>
      <Office objectId="off2">
        <ContactInformation>
          <Uri Annotation="wikipedia">https://wikipedia.com/ignorethisdup</Uri>
        </ContactInformation>
      </Office>
    </OfficeCollection>
  """

  # _extract_uris_by_category_type
  def test_a_dict_with_empty_paths_for_each_annotation_platform_and_value_succeeds(
      self,
  ):
    facebook_uri = "<Uri Annotation='personal-facebook'>{}</Uri>"
    person_website_uri = "<Uri Annotation='personal-website'>{}</Uri>"
    party_website_uri = "<Uri Annotation='party-website'>{}</Uri>"
    wikipedia_uri = "<Uri Annotation='wikipedia'>{}</Uri>"
    fb_one = etree.fromstring(
        facebook_uri.format("www.facebook.com/michael_scott")
    )
    fb_two = etree.fromstring(
        facebook_uri.format("www.facebook.com/dwight_shrute")
    )
    personal_one = etree.fromstring(
        person_website_uri.format("www.michaelscott.com")
    )
    personal_two = etree.fromstring(
        person_website_uri.format("www.dwightshrute.com")
    )
    party_one = etree.fromstring(
        party_website_uri.format("www.dundermifflin.com")
    )
    party_two = etree.fromstring(party_website_uri.format("www.sabre.com"))
    wiki_one = etree.fromstring(
        wikipedia_uri.format("www.wikipedia.com/dundermifflin")
    )
    wiki_two = etree.fromstring(
        wikipedia_uri.format("www.wikipedia.com/dundermifflin")
    )
    uri_elements = [
        fb_one,
        fb_two,
        personal_one,
        personal_two,
        party_one,
        party_two,
        wiki_one,
        wiki_two,
    ]
    expected_mapping = {
        "facebook": {
            "www.facebook.com/michael_scott": [fb_one],
            "www.facebook.com/dwight_shrute": [fb_two],
        },
        "website": {
            "www.michaelscott.com": [personal_one],
            "www.dwightshrute.com": [personal_two],
            "www.dundermifflin.com": [party_one],
            "www.sabre.com": [party_two],
        },
        "wikipedia": {
            "www.wikipedia.com/dundermifflin": [wiki_one, wiki_two],
        },
    }
    validator = rules.UniqueURIPerAnnotationCategory(None, None)

    actual_mapping = validator._extract_uris_by_category(uri_elements)

    self.assertEqual(actual_mapping, expected_mapping)

  def test_uris_with_no_annotation_succeeds(self):
    uri_element = "<Uri>{}</Uri>"
    uri_one = etree.fromstring(
        uri_element.format("www.facebook.com/michael_scott")
    )
    uri_two = etree.fromstring(
        uri_element.format("www.facebook.com/dwight_shrute")
    )
    uri_three = etree.fromstring(
        uri_element.format("www.facebook.com/dwight_shrute")
    )
    uri_elements = [uri_one, uri_two, uri_three]
    expected_mapping = {
        "": {
            "www.facebook.com/michael_scott": [uri_one],
            "www.facebook.com/dwight_shrute": [uri_two, uri_three],
        },
    }
    validator = rules.UniqueURIPerAnnotationCategory(None, None)

    actual_mapping = validator._extract_uris_by_category(uri_elements)

    self.assertEqual(actual_mapping, expected_mapping)

  # check tests
  def test_uris_are_unique_within_each_category_succeeds(self):
    person_one = {
        "facebook": "https://www.facebook.com/michael_scott",
        "website": "https://michaelscott2020.com",
        "wikipedia": "https://wikipedia.com/miachel_scott",
    }
    person_two = {
        "facebook": "https://www.facebook.com/dwight_shrute",
        "website": "https://dwightshrute2020.com",
        "wikipedia": "https://wikipedia.com/dwight_shrute",
    }
    party_one = {
        "facebook": "https://www.facebook.com/dunder_mifflin",
        "website": "https://dundermifflin2020.com",
        "wikipedia": "https://wikipedia.com/dunder_mifflin",
    }
    party_two = {
        "facebook": "https://www.facebook.com/sabre",
        "website": "https://sabre2020.com",
        "wikipedia": "https://wikipedia.com/sabre",
    }
    person_feed = self._base_person_collection.format(person_one, person_two)
    party_feed = self._base_party_collection.format(party_one, party_two)
    election_feed = """
      <ElectionReport>
        {}
        {}
        {}
      </ElectionReport>
    """.format(person_feed, party_feed, self._office_collection)
    election_tree = etree.fromstring(election_feed)
    validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)

    validator.check()

  def test_duplicate_uris_of_different_annotations_are_valid_succeeds(self):
    # personal-facebook and party-facebook are different annotation types
    person_one = {
        "facebook": "https://www.facebook.com/michael_scott",
        "website": "https://michaelscott2020.com",
        "wikipedia": "https://wikipedia.com/miachel_scott",
    }
    person_two = {
        "facebook": "https://www.facebook.com/dwight_shrute",
        "website": "https://dwightshrute2020.com",
        "wikipedia": "https://wikipedia.com/dwight_shrute",
    }
    party_one = {
        "facebook": "https://www.facebook.com/dunder_mifflin",
        "website": "https://dundermifflin2020.com",
        "wikipedia": "https://facebook.com/dunder_mifflin",
    }
    party_two = {
        "facebook": "https://www.facebook.com/sabre",
        "website": "https://sabre2020.com",
        "wikipedia": "https://www.facebook.com/sabre",
    }
    person_feed = self._base_person_collection.format(person_one, person_two)
    party_feed = self._base_party_collection.format(party_one, party_two)
    election_feed = """
      <ElectionReport>
        {}
        {}
      </ElectionReport>
    """.format(person_feed, party_feed)
    election_tree = etree.fromstring(election_feed)
    validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)

    validator.check()

  def test_there_are_duplicates_within_category_warns(self):
    person_one = {
        "facebook": "https://www.facebook.com/michael_scott",
        "website": "https://michaelscott2020.com",
        "wikipedia": "https://wikipedia.com/dunder_mifflin",
    }
    person_two = {
        "facebook": "https://www.facebook.com/dwight_shrute",
        "website": "https://dwightshrute2020.com",
        "wikipedia": "https://wikipedia.com/dunder_mifflin",
    }
    party_one = {
        "facebook": "https://www.facebook.com/dunder_mifflin",
        "website": "https://dundermifflin2020.com",
        "wikipedia": "https://wikipedia.com/dunder_mifflin",
    }
    party_two = {
        "facebook": "https://www.facebook.com/sabre",
        "website": "https://sabre2020.com",
        "wikipedia": "https://wikipedia.com/dunder_mifflin",
    }
    person_feed = self._base_person_collection.format(person_one, person_two)
    party_feed = self._base_party_collection.format(party_one, party_two)
    election_feed = """
      <ElectionReport>
        {}
        {}
      </ElectionReport>
    """.format(person_feed, party_feed)
    election_tree = etree.fromstring(election_feed)
    validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)

    with self.assertRaises(loggers.ElectionWarning) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "The Uris contain the annotation type 'wikipedia' with "
            "the same value 'https://wikipedia.com/dunder_mifflin'."
        ),
    )
    self.assertLen(context.exception.log_entry[0].elements, 4)

  def test_office_uris_are_not_included_in_check_succeeds(self):
    election_feed = """
      <ElectionReport>
        {}
      </ElectionReport>
    """.format(self._office_collection)
    election_tree = etree.fromstring(election_feed)
    validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)

    validator.check()


class ValidYoutubeURLTest(absltest.TestCase):

  def setUp(self):
    super(ValidYoutubeURLTest, self).setUp()
    self.validator = rules.ValidYoutubeURL(None, None)

  def test_yt_channel_url_succeeds(self):
    root_string = """
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com/channel/UCJzLUhdhkdfkepeTGJu2nOg]]>
        </Uri>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_yt_watch_url_fails(self):
    root_string = """
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com/watch?v=k-F_qYKkqaVxbA]]>
        </Uri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'https://www.youtube.com/watch?v=k-F_qYKkqaVxbA' is not an expected"
        " value for a youtube channel.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_yt_playlist_url_fails(self):
    root_string = """
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com/playlist?list=PLCvVBOK6lIHsfkBVt0oCFMSRz_grSwC4N]]>
        </Uri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'https://www.youtube.com/playlist?list=PLCvVBOK6lIHsfkBVt0oCFMSRz_grSwC4N'"
        " is not an expected value for a youtube channel.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_yt_hashtag_url_fails(self):
    root_string = """
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com/hashtag/xyz]]>
        </Uri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'https://www.youtube.com/hashtag/xyz' is not an expected value for a"
        " youtube channel.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_basic_yt_url_fails(self):
    root_string = """
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com/]]>
        </Uri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'https://www.youtube.com/' is not an expected value for a youtube"
        " channel.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")


class ValidTikTokURLTest(parameterized.TestCase):

  def setUp(self):
    super(ValidTikTokURLTest, self).setUp()
    self.validator = rules.ValidTiktokURL(None, None)

  def test_valid_tiktok_url_succeeds(self):
    root_string = """
        <Uri Annotation="personal-tiktok">
          <![CDATA[https://www.tiktok.com/@haxyehhshz-123_456.789]]>
        </Uri>
    """

    self.validator.check(etree.fromstring(root_string))

  @parameterized.parameters(
      "https://www.tiktok.com/",
      "https://www.tiktok.com/@",
      "https://www.tiktok.com/haxyehhshz",
      "https://www.tiktok.com/@haxye@hhshz",
      "https://www.tiktok.com/@haxyehhshz/other",
      "https://www.tiktok.com/@haxyehhshz?other",
      "https://www.tiktok.com/@haxyehhshz#other",
  )
  def test_invalid_tiktok_url_fails(self, url):
    root_string = f"""
        <Uri Annotation="official-tiktok">
          <![CDATA[{url}]]>
        </Uri>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        f"'{url}' is not an expected value for a tiktok account.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")


class ValidURIAnnotationTest(absltest.TestCase):

  def setUp(self):
    super(ValidURIAnnotationTest, self).setUp()
    self.validator = rules.ValidURIAnnotation(None, None)

  def test_contact_information_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["ContactInformation"])

  def test_platform_only_valid_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://de.wikipedia.org/]]>
        </Uri>
        <Uri Annotation="ballotpedia">
          <![CDATA[http://ballotpedia.org/George_Washington]]>
        </Uri>
        <Uri Annotation="opensecrets">
          <![CDATA[https://www.opensecrets.org/pres12]]>
        </Uri>
        <Uri Annotation="fec">
          <![CDATA[https://www.fec.gov/data/committee/C00813436/]]>
        </Uri>
        <Uri Annotation="followthemoney">
          <![CDATA[https://www.followthemoney.org]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_wikipedia_alternate_writing_system_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://zh.wikipedia.org/zh-cn/Fake_Page]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_type_platform_valid_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-facebook">
          <![CDATA[https://www.facebook.com]]>
        </Uri>
        <Uri Annotation="official-twitter">
          <![CDATA[https://twitter.com]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
        <Uri Annotation="campaign-line">
          <![CDATA[https://line.me/ti/p/@kmtonline]]>
        </Uri>
        <Uri Annotation="personal-instagram">
          <![CDATA[https://www.instagram.com]]>
        </Uri>
        <Uri Annotation="personal-linkedin">
          <![CDATA[https://www.linkedin.com/michael]]>
        </Uri>
        <Uri Annotation="campaign-tiktok">
          <![CDATA[https://www.tiktok.com/@ksncndjs]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_type_platform_no_annotation_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri>
          <![CDATA[https://twitter.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "URI {0} is missing annotation.".format(
            "https://twitter.com".encode("ascii", "ignore")
        ),
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_no_type_when_type_platform_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Annotation 'website' missing usage type.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_no_platform_has_usage_type_fails(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="campaign">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Annotation 'campaign' has usage type, missing platform.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_incorrect_platform_fails(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="personal-twitter">
          <![CDATA[https://www.youtube.com/SmithForGov]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "Annotation 'personal-twitter' is incorrect for URI {0}.".format(
                "https://www.youtube.com/SmithForGov".encode("ascii", "ignore")
            )
        ),
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_non_existent_platform_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="campaign-netsite">
          <![CDATA[http://www.smithforgovernor2020.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'campaign-netsite' is not a valid annotation.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_fb_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-facebook">
          <![CDATA[https://www.fb.com/example]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_incorrect_fb_annotation_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-fb">
          <![CDATA[https://www.facebook.com]]>
        </Uri>
        <Uri Annotation="personal-fb">
          <![CDATA[http://www.facebook.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'official-fb' is not a valid annotation.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_x_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-twitter">
          <![CDATA[https://www.x.com/example]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_incorrect_x_annotation_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-x">
          <![CDATA[https://www.x.com]]>
        </Uri>
        <Uri Annotation="personal-x">
          <![CDATA[http://www.twitter.com]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'official-x' is not a valid annotation.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_whatsapp_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-whatsapp">
          <![CDATA[https://www.whatsapp.com/example]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_office_contact_form_annotation_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="office-contact_form">
          <![CDATA[https://www.whitehouse.gov/contact-us]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_candidate_image_in_contact_information_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="candidate-image">
          <![CDATA[https://www.parlament.gv.at/test.jpg]]>
        </Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "'candidate-image' is not a valid annotation.",
    )


class OnlyOneCandidateImagePerPersonTest(absltest.TestCase):

  def setUp(self):
    super(OnlyOneCandidateImagePerPersonTest, self).setUp()
    self.validator = rules.OnlyOneCandidateImagePerPerson(None, None)

  def test_valid_person_one_candidate_image_succeeds(self):
    root_string = """
      <Person objectId="per1">
        <ImageUri Annotation="candidate-image">https://fake.com/1.jpg</ImageUri>
        <ImageUri Annotation="other-image">https://fake.com/2.jpg</ImageUri>
      </Person>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_invalid_person_multiple_candidate_images_fails(self):
    root_string = """
      <Person objectId="per1">
        <ImageUri Annotation="candidate-image">https://fake.com/1.jpg</ImageUri>
        <ImageUri Annotation="candidate-image">https://fake.com/2.jpg</ImageUri>
      </Person>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Person has 2 ImageUri fields annotated as 'candidate-image'."
        " Must have at most one.",
    )


class UniqueCandidateImageUrisTest(absltest.TestCase):

  def test_valid_unique_candidate_image_uris_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ImageUri Annotation="candidate-image">https://fake.com/1.jpg</ImageUri>
          </Person>
          <Person objectId="per2">
            <ImageUri Annotation="candidate-image">https://fake.com/2.jpg</ImageUri>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_invalid_duplicate_candidate_image_uris_fails(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ImageUri Annotation="candidate-image">https://fake.com/1.jpg</ImageUri>
          </Person>
          <Person objectId="per2">
            <ImageUri Annotation="candidate-image">https://fake.com/1.jpg</ImageUri>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Candidate image URI 'https://fake.com/1.jpg' is shared by multiple"
        " people: [per1, per2].",
    )

  def test_image_uris_without_candidate_image_annotation_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ImageUri Annotation="other-image">https://fake.com/1.jpg</ImageUri>
          </Person>
          <Person objectId="per2">
            <ImageUri Annotation="other-image">https://fake.com/1.jpg</ImageUri>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_empty_image_uri_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ImageUri Annotation="candidate-image"></ImageUri>
          </Person>
          <Person objectId="per2">
            <ImageUri Annotation="candidate-image"></ImageUri>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_whitespace_image_uri_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ImageUri Annotation="candidate-image">   </ImageUri>
          </Person>
          <Person objectId="per2">
            <ImageUri Annotation="candidate-image">   </ImageUri>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_election_report_with_no_person_collection_is_valid_succeeds(self):
    root_string = "<ElectionReport></ElectionReport>"
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_election_report_with_empty_person_collection_is_valid_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()


class OfficesHaveJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveJurisdictionIDTest, self).setUp()
    self.validator = rules.OfficesHaveJurisdictionID(None, None)

  def test_office_has_jurisdiction_id_by_additional_data_succeeds(self):
    test_string = """
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_has_post_office_split_jurisdiction_id_succeeds(self):
    test_string = """
          <Office objectId="off1">
            <JurisdictionId>ru-gpu2</JurisdictionId>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_has_jurisdiction_id_by_external_identifier_succeeds(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_999</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_does_not_have_jurisdiction_id_by_additional_data_fails(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData>ru-gpu4</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_does_not_have_jurisdiction_id_text_by_additional_data_fails(
      self,
  ):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id"></AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_has_more_than_one_jurisdiction_id_by_additional_data_fails(
      self,
  ):
    test_string = """
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
            <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has more than one jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_does_not_have_jurisdiction_id_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>ru-gpu3</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_does_not_have_jurisdiction_id_text_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value></Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_has_more_than_one_jurisdiction_id_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_900</Value>
             </ExternalIdentifier>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_800</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has more than one jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_jurisdiction_id_text_is_whitespace_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_jurisdiction_id_text_is_whitespace_by_additional_data_fails(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id">    </AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing a jurisdiction ID.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )


class ValidJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(ValidJurisdictionIDTest, self).setUp()
    self.root_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnitCollection>
          {}
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu2"/>
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu3"/>
        </GpUnitCollection>
        <OfficeCollection>
          {}
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>
          <Office objectId="off2">
            <AdditionalData>ru-gpu4</AdditionalData>
          </Office>
          <Office>
            <ExternalIdentifiers>
              {}
            </ExternalIdentifiers>
          </Office>
        </OfficeCollection>
      </ElectionReport>
    """

  # _gather_reference_values tests
  def test_a_set_of_jurisdiction_ids_from_given_tree_additional_data_succeeds(
      self,
  ):
    root_string = self.root_string.format(
        "",
        """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""",
        "",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu1", "ru-gpu2"})

  def test_a_set_of_jurisdiction_ids_from_given_tree_external_identifier_succeeds(
      self,
  ):
    root_string = self.root_string.format(
        "",
        "",
        """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu2", "ru-gpu3"})

  def test_external_identifier_without_type_succeeds(self):
    root_string = self.root_string.format(
        "",
        "",
        """
          <ExternalIdentifier>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu2"})

  def test_external_identifier_without_other_type_not_jurisdiction_id_succeeds(
      self,
  ):
    root_string = self.root_string.format(
        "",
        "",
        """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>district-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu2"})

  def test_external_identifier_without_value_element_succeeds(self):
    root_string = self.root_string.format(
        "",
        "",
        """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
          </ExternalIdentifier>""",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu2"})

  def test_removes_duplicates_if_multiple_offices_have_same_jurisdiction_succeeds(
      self,
  ):
    root_string = self.root_string.format(
        "",
        """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>""",
        "",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()

    self.assertEqual(reference_values, {"ru-gpu2"})

  # _gather_defined_values test
  def test_a_set_of_gp_units_from_given_tree_succeeds(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""",
        "",
        "",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_defined_values()

    self.assertEqual(reference_values, {"ru-gpu1", "ru-gpu2", "ru-gpu3"})

  # check tests
  def test_every_jurisdiction_id_references_a_valid_gp_unit_succeeds(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""",
        """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""",
        """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))

    rules.ValidJurisdictionID(election_tree, None).check()

  def test_raises_an_election_error_if_jurisdiction_id_is_not_a_gp_unit_id_fails(
      self,
  ):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""",
        """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu99</AdditionalData>
          </Office>""",
        "",
    )
    election_tree = etree.ElementTree(etree.fromstring(root_string))

    with self.assertRaises(loggers.ElectionError) as context:
      rules.ValidJurisdictionID(election_tree, None).check()
    self.assertIn("ru-gpu99", context.exception.log_entry[0].message)


class OfficesHaveValidOfficeLevelTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveValidOfficeLevelTest, self).setUp()
    self.root_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <OfficeCollection>
          {}
        </OfficeCollection>
      </ElectionReport>
    """
    self.validator = rules.OfficesHaveValidOfficeLevel(None, None)

  def test_office_has_office_level_by_external_identifier_succeeds(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>District</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_has_post_office_split_office_level_succeeds(self):
    test_string = """
          <Office objectId="off1">
             <Level>District</Level>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_does_not_have_office_level_by_external_identifier_fails(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>Region</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing an office level.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_does_not_have_office_level_text_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value></Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing an office level.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_office_has_more_than_one_office_levels_by_external_identifier_fails(
      self,
  ):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>Country</Value>
             </ExternalIdentifier>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>International</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has more than one office level.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_level_text_is_whitespace_by_external_identifier_fails(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing an office level.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )

  def test_invalid_office_level_fails(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>invalid level</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has an invalid office level: 'invalid level'.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off2"
    )


class OfficeHasjurisdictionSameAsElectoralDistrictTest(absltest.TestCase):

  def setUp(self):
    super(OfficeHasjurisdictionSameAsElectoralDistrictTest, self).setUp()
    self.validator = rules.OfficeHasjurisdictionSameAsElectoralDistrict(
        None, None
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


class OfficesHaveValidOfficeRoleTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveValidOfficeRoleTest, self).setUp()
    self.validator = rules.OfficesHaveValidOfficeRole(None, None)

  def test_office_has_valid_office_role_succeeds(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>upper house</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_post_office_split_office_has_valid_office_role_succeeds(self):
    test_string = """
          <Office objectId="off1">
            <Role>upper house</Role>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_has_valid_office_role_combination_succeeds(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>head of state</Value>
              </ExternalIdentifier>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>head of government</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_office_does_not_have_office_role_fails(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <Value>Region</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing an office role.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_does_not_have_office_role_text_fails(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value></Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office is missing an office role.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_has_invalid_office_role_combination_fails(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>upper house</Value>
              </ExternalIdentifier>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>lower house</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertStartsWith(
        context.exception.log_entry[0].message,
        "Office has an invalid combination of office roles: "
        "['upper house', 'lower house']. Valid combinations are ",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_has_more_than_two_office_roles_fails(self):
    test_string = """
          <Office objectId="off1">
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>head of state</Value>
              </ExternalIdentifier>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>head of government</Value>
              </ExternalIdentifier>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>deputy head of government</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has more than two office roles.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_office_role_text_is_whitespace_fails(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has an invalid office role: ''.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )

  def test_invalid_office_role_fails(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>invalid role</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office has an invalid office role: 'invalid role'.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "off1"
    )


class ContestHasValidContestStageTest(absltest.TestCase):

  def setUp(self):
    super(ContestHasValidContestStageTest, self).setUp()
    self.validator = rules.ContestHasValidContestStage(None, None)

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
    self.validator = rules.GpUnitsHaveSingleRoot(None, None)

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


class GpUnitsCyclesRefsValidationTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsCyclesRefsValidationTest, self).setUp()
    self.validator = rules.GpUnitsCyclesRefsValidation(None, None)

  def test_cycles_formed_fails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
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
        "Cycle detected at node", context.exception.log_entry[0].message
    )

  def test_valid_tree_succeeds(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string)
    )

    self.validator.check()


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
    self.validator = rules.DateOfBirthIsInPast(None, None)

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


class ElectionContainsStartAndEndDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionContainsStartAndEndDatesTest, self).setUp()
    self.validator = rules.ElectionContainsStartAndEndDates(None, None)

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
    self.validator = rules.ElectionStartDates(None, None)
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
    self.validator = rules.ElectionEndDatesInThePast(None, None)
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
    self.validator = rules.ElectionEndDatesOccurAfterStartDates(None, None)
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


class ValidPartyLeadershipDatesTest(absltest.TestCase):

  def setUp(self):
    super(ValidPartyLeadershipDatesTest, self).setUp()
    self.validator = rules.ValidPartyLeadershipDates(None, None)
    self.today = datetime.datetime.now(datetime.timezone.utc).date()
    self.party_leadership_string = """
    <PartyLeadership>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </PartyLeadership>
    """

  def test_party_leadership_elements_succeeds(self):
    self.assertEqual(self.validator.elements(), ["PartyLeadership"])

  def test_invalid_start_date_fails(self):
    party_leadership_string = self.party_leadership_string.format(
        "I am invalid!", self.today
    )
    party_leadership = etree.fromstring(party_leadership_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(party_leadership)

  def test_invalid_end_date_fails(self):
    party_leadership_string = self.party_leadership_string.format(
        self.today, "I am invalid!"
    )
    party_leadership = etree.fromstring(party_leadership_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(party_leadership)

  def test_end_date_after_start_date_succeeds(self):
    party_leadership_string = self.party_leadership_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2),
    )
    party_leadership = etree.fromstring(party_leadership_string)

    self.validator.check(party_leadership)

  def test_end_date_before_start_date_fails(self):
    party_leadership_string = self.party_leadership_string.format(
        self.today + datetime.timedelta(days=2),
        self.today + datetime.timedelta(days=1),
    )
    party_leadership = etree.fromstring(party_leadership_string)

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(party_leadership)

  def test_order_without_both_dates_succeeds(self):
    self.validator.check(etree.fromstring("""
      <PartyLeadership>
        <StartDate>2012-01-01</StartDate>
      </PartyLeadership>
    """))
    self.validator.check(etree.fromstring("""
      <PartyLeadership>
      </PartyLeadership>
    """))
    self.validator.check(etree.fromstring("""
      <PartyLeadership>
        <EndDate>2012-01-01</EndDate>
      </PartyLeadership>
    """))


class ElectionDatesSpanContestDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionDatesSpanContestDatesTest, self).setUp()
    self.validator = rules.ElectionDatesSpanContestDates(None, None)

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
      rules.ElectionTypesAreCompatible(None, None).check(
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
      rules.ElectionTypesAreCompatible(None, None).check(
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
      rules.ElectionTypesAreCompatible(None, None).check(
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

    rules.ElectionTypesAreCompatible(None, None).check(
        etree.fromstring(election_string)
    )


class ElectionTypesAndCandidateContestTypesAreCompatibleTest(absltest.TestCase):

  def setUp(self):
    super(ElectionTypesAndCandidateContestTypesAreCompatibleTest, self).setUp()
    self.validator = rules.ElectionTypesAndCandidateContestTypesAreCompatible(
        None, None
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
    self.validator = rules.DateStatusMatches(None, None)
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
    self.validator = rules.OfficeSelectionMethodMatch(element_tree, None)

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
    self.validator = rules.OfficeHolderTenureTermDates(None, None)

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
    self.date_validator = rules.OfficeTermDates(element_tree, None)
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_date_validator = rules.OfficeTermDates(
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
      rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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
      rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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
      rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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
      rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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
      rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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

    rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
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

    rules.RemovePersonAndOfficeHolderId60DaysAfterEndDate(
        election_tree, None
    ).check()


class UniqueStartDatesForOfficeRoleAndJurisdictionTest(absltest.TestCase):

  def setUp(self):
    super(UniqueStartDatesForOfficeRoleAndJurisdictionTest, self).setUp()
    self.validator = rules.UniqueStartDatesForOfficeRoleAndJurisdiction(
        None, None
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


class GpUnitsHaveInternationalizedNameTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveInternationalizedNameTest, self).setUp()
    self.validator = rules.GpUnitsHaveInternationalizedName(None, None)

  def test_has_exactly_one_internationalized_name_with_text_succeeds(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Wisconsin District 7</Text>
      </InternationalizedName>
    </GpUnit>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_has_exactly_one_internationalized_name_with_multiple_text_elements_succeeds(
      self,
  ):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Wisconsin District 7</Text>
        <Text language="ru">Монгольский округ 7</Text>
      </InternationalizedName>
    </GpUnit>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_no_internationalized_name_element_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit is required to have exactly one InterationalizedName element.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "ru0002"
    )

  def test_internationalized_name_element_no_subelements_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName/>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        (
            "GpUnit InternationalizedName is required to have one or "
            "more Text elements."
        ),
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "InternationalizedName"
    )

  def test_internationalized_name_no_text_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en"></Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit InternationalizedName does not have a text value.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Text")

  def test_internationalized_name_text_value_is_whitespace_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">                 </Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit InternationalizedName does not have a text value.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Text")

  def test_one_text_element_does_not_have_value_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Russia</Text>
        <Text language="ru"></Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit InternationalizedName does not have a text value.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Text")

  def test_more_than_one_internationalized_name_fails(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en"></Text>
      </InternationalizedName>
      <InternationalizedName>
        <Text language="en">USA</Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit is required to have exactly one InterationalizedName element.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "ru0002"
    )


class GetAdditionalTypeValuesTest(absltest.TestCase):

  def setUp(self):
    super(GetAdditionalTypeValuesTest, self).setUp()
    self.root_string = """
    <OfficeCollection>
      <Office>
      {}
      </Office>
      <Office>
      {}
      </Office>
    </OfficeCollection>
    """

  def test_get_additional_type_values_with_no_elements_returns_empty_list(self):
    root = etree.fromstring(self.root_string.format("", ""))
    elements = rules.get_additional_type_values(
        root, "jurisdiction-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_no_values_returns_empty_list(self):
    add_data = """
        <AdditionalData type="jurisdiction-id"></AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_whitespace_value_returns_empty_list(
      self,
  ):
    add_data = """
        <AdditionalData type="jurisdiction-id">      </AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_no_type_attribute_returns_empty_list(
      self,
  ):
    add_data = """
        <AdditionalData>ru-gpu2</AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_return_elements_returns_elements(
      self,
  ):
    add_data_1 = """
        <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
        <AdditionalData type="government-body">US House</AdditionalData>
        <AdditionalData type="office-level">Country</AdditionalData>
        <AdditionalData type="office-role">Upper house</AdditionalData>
    """
    add_data_2 = """
        <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
        <AdditionalData type="government-body">US Senate</AdditionalData>
        <AdditionalData type="office-level">Country</AdditionalData>
        <AdditionalData type="office-role">Lower house</AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data_1, add_data_2))
    elements = rules.get_additional_type_values(
        root, "jurisdiction-id", return_elements=True
    )
    self.assertLen(elements, 2)
    for el in elements:
      self.assertNotIsInstance(el, str)

  def test_get_additional_type_values_returns_values(self):
    values = {"ru-gpu2", "ru-gpu3"}
    add_data_1 = """
        <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
        <AdditionalData type="government-body">US Senate</AdditionalData>
        <AdditionalData type="office-level">Country</AdditionalData>
        <AdditionalData type="office-role">Upper house</AdditionalData>
    """
    add_data_2 = """
        <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
        <AdditionalData type="government-body">US House</AdditionalData>
        <AdditionalData type="office-level">Country</AdditionalData>
        <AdditionalData type="office-role">Lower house</AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data_1, add_data_2))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")

    self.assertLen(elements, 2)
    for el in elements:
      self.assertIsInstance(el, str)
      self.assertIn(el, values)


class GetExternalIDValuesTest(absltest.TestCase):

  def setUp(self):
    super(GetExternalIDValuesTest, self).setUp()
    self.gpunit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          {}
        </ExternalIdentifiers>
      </GpUnit>
    """

  def test_get_external_id_values_with_empty_type_and_no_ids_returns_empty_list(
      self,
  ):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_no_ids_returns_empty_list(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_no_type_element_returns_empty_list(self):
    missing_type = """
    <ExternalIdentifier>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_type))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_missing_text_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type></Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_is_whitespace_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>                   </Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_value_is_missing_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value></Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_empty_type_and_no_ids_returns_empty_elements(
      self,
  ):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "", return_elements=True)

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_no_ids_returns_empty_elements(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_no_type_element_returns_empty_elements(
      self,
  ):
    missing_type = """
    <ExternalIdentifier>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_type))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_missing_text_returns_empty_elements(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type></Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_is_whitespace_returns_empty_elements(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>                   </Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_value_is_missing_returns_empty_elements(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value></Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_missing_returns_empty_list(
      self,
  ):
    missing_element = """
    <ExternalIdentifier>
      <Type>other</Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_element))
    elements = rules.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_missing_text_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType></OtherType>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_is_whitespace_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType>          </OtherType>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_mismatched_other_type_returns_empty_list(
      self,
  ):
    missing_text = """
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType>ocd-id</OtherType>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_value_is_whitespace_returns_non_empty_list(
      self,
  ):
    has_whitespace = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value>       </Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(has_whitespace))
    elements = rules.get_external_id_values(root, "ocd-id")

    self.assertLen(elements, 1)
    for el in elements:
      self.assertIsInstance(el, str)

  def test_get_external_id_values_when_other_type_value_is_whitespace_returns_non_empty_list(
      self,
  ):
    has_whitespace = """
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType>something-else</OtherType>
      <Value>    </Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(has_whitespace))
    elements = rules.get_external_id_values(root, "something-else")

    self.assertLen(elements, 1)
    for el in elements:
      self.assertIsInstance(el, str)

  def get_type_string(self):
    type_string = """
    <ExternalIdentifier>
      <Type>{}</Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    <ExternalIdentifier>
      <Type>{}</Type>
      <Value>ocd-division/country:us/state:ma</Value>
    </ExternalIdentifier>
    """
    return type_string

  def get_other_type_strings(self):
    test_values = {"hi", "there"}
    type_string = """
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType>{}</OtherType>
      <Value>hi</Value>
    </ExternalIdentifier>
    <ExternalIdentifier>
      <Type>other</Type>
      <OtherType>{}</OtherType>
      <Value>there</Value>
    </ExternalIdentifier>
    """
    return [test_values, type_string]

  def test_get_external_id_values_with_return_elements_returns_all_valid_elements(
      self,
  ):
    type_string = self.get_type_string()
    for en_type in rules._IDENTIFIER_TYPES:
      full_string = self.gpunit.format(type_string.format(en_type, en_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(
          root, en_type, return_elements=True
      )
      self.assertLen(elements, 2)
      for el in elements:
        self.assertNotIsInstance(el, str)

  def test_get_external_id_values_returns_all_valid_values(self):
    type_string = self.get_type_string()
    test_values = {
        "ocd-division/country:us/state:va",
        "ocd-division/country:us/state:ma",
    }
    for en_type in rules._IDENTIFIER_TYPES:
      full_string = self.gpunit.format(type_string.format(en_type, en_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(root, en_type)

      self.assertLen(elements, 2)
      for el in elements:
        self.assertIsInstance(el, str)
        self.assertIn(el, test_values)

  def test_get_external_id_values_with_return_elements_returns_other_type_elements(
      self,
  ):
    test_values, other_type_str = self.get_other_type_strings()
    for other_type in test_values:
      full_string = self.gpunit.format(
          other_type_str.format(other_type, other_type)
      )
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(
          root, other_type, return_elements=True
      )
      self.assertLen(elements, 2)
      for el in elements:
        self.assertNotIsInstance(el, str)

  def test_get_external_id_values_returns_other_type_values(self):
    test_values, other_type_str = self.get_other_type_strings()
    for other_type in test_values:
      full_string = self.gpunit.format(
          other_type_str.format(other_type, other_type)
      )
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(root, other_type)

      self.assertLen(elements, 2)
      for el in elements:
        self.assertIsInstance(el, str)
        self.assertIn(el, test_values)


class ValidateInfoUriAnnotationTest(absltest.TestCase):

  def setUp(self):
    super(ValidateInfoUriAnnotationTest, self).setUp()
    self.validator = rules.ValidateInfoUriAnnotation(None, None)

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
    self.validator = rules.FullTextMaxLength(None, None)

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
    self.validator = rules.FullTextOrBallotText(None, None)

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
    self.validator = rules.BallotTitle(None, None)

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
    validator = rules.ImproperCandidateContest(None, None)
    expected_ids = ["can123", "can987", "can456"]
    actual_ids = validator._gather_contest_candidates(contest_elem)

    self.assertEqual(expected_ids, actual_ids)

  # _gather_invalid_candidates test
  def test_candidate_ids_that_appear_to_be_ballot_selections_succeeds(
      self,
  ):
    candidate_election = self._base_report.format("Yes", "Larry David")
    root = etree.fromstring(candidate_election)
    validator = rules.ImproperCandidateContest(root, None)
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
    validator = rules.ImproperCandidateContest(root, None)

    validator.check()

  def test_candidates_with_ballot_selections_options_get_flagged_warns(self):
    candidate_election = self._base_report.format("Yes", "No")
    root = etree.fromstring(candidate_election)
    validator = rules.ImproperCandidateContest(root, None)

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
    validator = rules.WinnerCountLimit(election_tree, None)
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
    validator = rules.WinnerCountLimit(election_tree, None)
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
    validator = rules.WinnerCountLimit(election_tree, None)
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
    validator = rules.WinnerCountLimit(election_tree, None)
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
    validator = rules.WinnerCountLimit(election_tree, None)
    validator.setup()

    validator.check(election_tree.find(".//Contest"))


class MissingFieldsErrorTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsErrorTest, self).setUp()
    self.validator = rules.MissingFieldsError(None, None)
    self.validator.setup()

  def test_get_severity_returns_error_level(self):
    self.assertEqual(2, self.validator.get_severity())

  def test_required_field_is_present_person_succeeds(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text>Chris Rock</Text>
        </FullName>
      </Person>
    """

    self.validator.check(etree.fromstring(person))

  def test_missing_field_person_fails(self):
    person = """
      <Person objectId="123">
      </Person>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_required_field_is_present_candidate_succeeds(self):
    candidate = """
      <Candidate objectId="123">
        <PersonId>per1</PersonId>
      </Candidate>
    """

    self.validator.check(etree.fromstring(candidate))

  def test_missing_field_candidate_fails(self):
    candidate = """
      <Candidate objectId="123">
        <PersonId></PersonId>
      </Candidate>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(candidate))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Candidate is missing field PersonId.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_required_field_is_present_party_succeeds(self):
    party = """
      <Party objectId="par0">
        <PartyScopeGpUnitIds>ru-gpu2</PartyScopeGpUnitIds>
      </Party>
    """

    self.validator.check(etree.fromstring(party))

  def test_missing_field_party_fails(self):
    party = """
      <Party objectId="par0">
      </Party>
    """
    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(party))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Party is missing field PartyScopeGpUnitIds.",
    )

  def test_required_field_is_present_election_succeeds(self):
    election = """
      <Election objectId="123">
        <StartDate>2020-01-01</StartDate>
        <EndDate>2020-01-01</EndDate>
      </Election>
    """

    self.validator.check(etree.fromstring(election))

  def test_missing_field_election_fails(self):
    election = """
      <Election objectId="123">
      </Election>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election))

    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Election is missing field StartDate.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "The element Election is missing field EndDate.",
    )
    self.assertEqual(
        context.exception.log_entry[1].elements[0].get("objectId"), "123"
    )


class MissingFieldsWarningTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsWarningTest, self).setUp()
    self.validator = rules.MissingFieldsWarning(None, None)
    self.validator.setup()

  def test_sets_severity_level_to_succeeds(self):
    self.assertEqual(1, self.validator.get_severity())

  def test_required_field_is_present_candidate_succeeds(self):
    candidate = """
      <Candidate objectId="123">
        <PartyId>par1</PartyId>
      </Candidate>
    """

    self.validator.check(etree.fromstring(candidate))

  def test_missing_field_candidate_warns(self):
    candidate = """
      <Candidate objectId="123">
      </Candidate>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(candidate))

    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Candidate is missing field PartyId.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )


class MissingFieldsInfoTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsInfoTest, self).setUp()
    self.validator = rules.MissingFieldsInfo(None, None)
    self.validator.setup()

  def test_sets_severity_level_to_succeeds(self):
    self.assertEqual(0, self.validator.get_severity())


class PartySpanMultipleCountriesTest(absltest.TestCase):

  def setUp(self):
    super(PartySpanMultipleCountriesTest, self).setUp()
    self.validator = rules.DuplicateGpUnits(None, None)
    self.base_report = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Election>
          <GpUnitCollection>
            <GpUnit objectId="ru0001">
              <ExternalIdentifiers>
                <ExternalIdentifier>
                  <Type>ocd-id</Type>
                  <Value>ocd-division/country:us</Value>
                </ExternalIdentifier>
              </ExternalIdentifiers>
             </GpUnit>
             <GpUnit objectId="ru0002">
               <ExternalIdentifiers>
                  <ExternalIdentifier>
                    <Type>ocd-id</Type>
                    <Value>ocd-division/country:us/state:va</Value>
                  </ExternalIdentifier>
               </ExternalIdentifiers>
             </GpUnit>
             <GpUnit objectId="ru0003">
               <ExternalIdentifiers>
                  <ExternalIdentifier>
                    <Type>ocd-id</Type>
                    <Value>ocd-division/country:fr</Value>
                  </ExternalIdentifier>
                </ExternalIdentifiers>
             </GpUnit>
             <GpUnit objectId="ru0004">
             </GpUnit>
          </GpUnitCollection>
          <PartyCollection>
            <Party>
              <PartyScopeGpUnitIds>{}</PartyScopeGpUnitIds>
            </Party>
          </PartyCollection>
        </Election>
      </ElectionReport>
  """

  def test_gp_unit_list_succeeds(self):
    referenced_gpunits = "ru0001 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    expected_map = {
        "ru0001": "country:us",
        "ru0002": "country:us",
        "ru0003": "country:fr",
    }

    self.assertEqual(validator.existing_gpunits, expected_map)

  def test_no_warning_if_same_country_succeeds(self):
    referenced_gpunits = "ru0001 ru0002"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_no_warning_if_gp_unit_without_country_succeeds(self):
    referenced_gpunits = "ru0001 ru0004"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_no_warning_if_one_gp_unit_succeeds(self):
    referenced_gpunits = "ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_multiple_countries_are_referenced_warns(self):
    referenced_gpunits = "ru0001 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )
    with self.assertRaises(loggers.ElectionWarning) as context:
      validator.check(element)
    self.assertIn("ru0001", context.exception.log_entry[0].message)
    self.assertIn("ru0003", context.exception.log_entry[0].message)

  def test_multiple_countries_are_referenced_with_composition_warns(
      self,
  ):
    referenced_gpunits = "ru0002 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )
    with self.assertRaises(loggers.ElectionWarning) as context:
      validator.check(element)
    self.assertIn("ru0002", context.exception.log_entry[0].message)
    self.assertIn("ru0003", context.exception.log_entry[0].message)


class NonExecutiveOfficeShouldHaveGovernmentBodyTest(absltest.TestCase):

  def setUp(self):
    super(NonExecutiveOfficeShouldHaveGovernmentBodyTest, self).setUp()
    root_string = """
      <Report>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.gov_validator = rules.NonExecutiveOfficeShouldHaveGovernmentBody(
        element_tree,
        None,
    )
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_validator = (
        rules.NonExecutiveOfficeShouldHaveGovernmentBody(
            element_tree,
            None,
        )
    )

  def test_office_elements_succeeds(self):
    self.assertEqual(self.gov_validator.elements(), ["Office"])

  def test_post_split_office_elements_succeeds(self):
    self.assertEqual(self.post_office_split_validator.elements(), ["Office"])

  def test_non_exec_office_without_government_body_raises_info(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>senate</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Office>
    """

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.gov_validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Non-Head of Government/State Office element is missing a government"
        " body.",
    )

  def test_post_split_non_exec_office_without_government_body_raises_info(
      self,
  ):
    office_string = """
      <Office>
        <Role>senate</Role>
      </Office>
    """

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.post_office_split_validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Non-Head of Government/State Office element is missing a government"
        " body.",
    )

  def test_non_exec_office_with_empty_government_body_ids_raises_info(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>senate</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <GovernmentBodyIds>   </GovernmentBodyIds>
      </Office>
    """

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.gov_validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Non-Head of Government/State Office element is missing a government"
        " body.",
    )

  def test_post_split_non_exec_office_with_empty_government_body_ids_raises_info(
      self,
  ):
    office_string = """
      <Office>
        <GovernmentBodyIds>   </GovernmentBodyIds>
        <Role>senate</Role>
      </Office>
    """

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.post_office_split_validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Non-Head of Government/State Office element is missing a government"
        " body.",
    )

  def test_non_exec_office_with_government_body_ids_is_valid_succeeds(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>senate</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <GovernmentBodyIds>gov_body_1</GovernmentBodyIds>
      </Office>
    """

    self.gov_validator.check(etree.fromstring(office_string))

  def test_post_split_non_exec_office_with_government_body_ids_is_valid_succeeds(
      self,
  ):
    office_string = """
      <Office>
        <GovernmentBodyIds>gov_body_1</GovernmentBodyIds>
        <Role>senate</Role>
      </Office>
    """

    self.post_office_split_validator.check(etree.fromstring(office_string))


class ExecutiveOfficeShouldNotHaveGovernmentBodyTest(absltest.TestCase):

  def setUp(self):
    super(ExecutiveOfficeShouldNotHaveGovernmentBodyTest, self).setUp()
    root_string = """
      <Report>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.gov_validator = rules.ExecutiveOfficeShouldNotHaveGovernmentBody(
        element_tree,
        None,
    )
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_validator = (
        rules.ExecutiveOfficeShouldNotHaveGovernmentBody(
            element_tree,
            None,
        )
    )

  def test_executive_office_with_government_body_ids_fails(self):
    for office_role in rules._EXECUTIVE_OFFICE_ROLES:
      with self.subTest(office_role=office_role):
        office_string = f"""
          <Office>
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>other</Type>
                <OtherType>office-role</OtherType>
                <Value>{office_role}</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
            <GovernmentBodyIds>gov_body_1</GovernmentBodyIds>
          </Office>
        """

        with self.assertRaises(loggers.ElectionError) as context:
          self.gov_validator.check(etree.fromstring(office_string))
        self.assertEqual(
            context.exception.log_entry[0].message,
            f"Head of Government/State Office element (roles: {office_role})"
            " has a government body. Head of Government/State offices should"
            " not have government bodies.",
        )

  def test_post_split_executive_office_with_government_body_ids_fails(
      self,
  ):
    for office_role in rules._EXECUTIVE_OFFICE_ROLES:
      with self.subTest(office_role=office_role):
        office_string = f"""
          <Office>
            <GovernmentBodyIds>gov_body_1</GovernmentBodyIds>
            <Role>{office_role}</Role>
          </Office>
        """

        with self.assertRaises(loggers.ElectionError) as context:
          self.post_office_split_validator.check(
              etree.fromstring(office_string)
          )
        self.assertEqual(
            context.exception.log_entry[0].message,
            f"Head of Government/State Office element (roles: {office_role})"
            " has a government body. Head of Government/State offices should"
            " not have government bodies.",
        )

  def test_executive_office_without_government_body_is_valid_succeeds(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>head of state</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Office>
    """

    self.gov_validator.check(etree.fromstring(office_string))

  def test_post_split_executive_office_without_government_body_is_valid_succeeds(
      self,
  ):
    office_string = """
      <Office>
        <Role>head of state</Role>
      </Office>
    """

    self.post_office_split_validator.check(etree.fromstring(office_string))


class OfficeSelectionMethodTest(absltest.TestCase):

  def setUp(self):
    super(OfficeSelectionMethodTest, self).setUp()
    self.validator = rules.MissingOfficeSelectionMethod(None, None)

  def test_valid_selection_method_succeeds(self):
    office_string = """
        <Office>
          <SelectionMethod>directly-elected</SelectionMethod>
        </Office>
    """

    self.validator.check(etree.fromstring(office_string))

  def test_missing_selection_method_warns(self):
    office_string = """
        <Office>
        </Office>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(office_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office element is missing its SelectionMethod.",
    )


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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None
    )

    validator.check(election_tree)

  def test_subsequent_contest_with_earlier_end_date_from_election_fails(self):
    root_string = self._base_election_report.format("cc_001", "")
    election_tree = etree.fromstring(root_string)
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.SubsequentContestIdIsValidRelatedContest(
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
    validator = rules.ComposingContestIdsAreValidRelatedContests(
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
    validator = rules.ComposingContestIdsAreValidRelatedContests(
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
    validator = rules.ComposingContestIdsAreValidRelatedContests(
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
    validator = rules.ComposingContestIdsAreValidRelatedContests(
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
    validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None
    )

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check(election_tree)
    self.assertIn(
        "Contest cc_456 and contest cc_123 reference each other as composing "
        "contests",
        context.exception.log_entry[0].message,
    )


class MultipleInternationalizedTextWithSameLanguageCodeTest(absltest.TestCase):

  def setUp(self):
    super(MultipleInternationalizedTextWithSameLanguageCodeTest, self).setUp()
    self.validator = rules.MultipleInternationalizedTextWithSameLanguageCode(
        None, None
    )

  def test_multiple_texts_with_same_language_code_fails(self):
    election_string = """
      <Name>
        <Text language="en">
          <![CDATA[Jamaica General Election, 2022]]>
        </Text>
        <Text language="en">
          <![CDATA[Other Jamaica General Election, 2022]]>
        </Text>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </Name>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        'Multiple "en" texts found for "Jamaica General Election, 2022"',
    )

  def test_one_text_per_language_code_succeeds(self):
    election_string = """
      <Name>
        <Text language="en">
          <![CDATA[Jamaica General Election, 2022]]>
        </Text>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </Name>
    """

    self.validator.check(etree.fromstring(election_string))


class AllInternationalizedTextHaveEnVersionTest(absltest.TestCase):

  def setUp(self):
    super(AllInternationalizedTextHaveEnVersionTest, self).setUp()
    self.validator = rules.AllInternationalizedTextHaveEnVersion(None, None)

  def test_internationalized_text_without_en_version_raises_info(self):
    election_string = """
      <Name>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </Name>
    """

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        'No "english" version found for the InternationalizedText.',
    )

  def test_internationalized_text_with_en_version_succeeds(self):
    election_string = """
      <Name>
        <Text language="en">
          <![CDATA[Jamaica General Election, 2022]]>
        </Text>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </Name>
    """

    self.validator.check(etree.fromstring(election_string))


class ContestContainsValidStartDateTest(absltest.TestCase):

  def setUp(self):
    super(ContestContainsValidStartDateTest, self).setUp()
    self.validator = rules.ContestContainsValidStartDate(None, None)
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
    self.validator = rules.ContestContainsValidEndDate(None, None)
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
    self.validator = rules.ContestEndDateOccursAfterStartDate(None, None)
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
    self.validator = rules.ContestEndDateOccursBeforeSubsequentContestStartDate(
        None, None
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
    self.validator = rules.ContestStartDateContainsCorrespondingEndDate(
        None, None
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
    self.validator = rules.CandidateContestTypesAreCompatible(None, None)

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
    self.validator = rules.ValidatePollsCloseDatetimes(None, None)

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
    self.validator = rules.ValidateResultsExpected(None, None)

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
    self.validator = rules.ValidateResultsEmbargoEnd(None, None)

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
    self.validator = rules.ResultsReportingStagesMustHaveUniqueType(None, None)

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


class CommitteeClassificationEndDateOccursAfterStartDateTest(absltest.TestCase):

  def setUp(self):
    super(CommitteeClassificationEndDateOccursAfterStartDateTest, self).setUp()
    self.validator = rules.CommitteeClassificationEndDateOccursAfterStartDate(
        None, None
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
    self.validator = rules.EinMatchesFormat(None, None)

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


class AffiliationHasEitherPartyOrPersonTest(absltest.TestCase):

  def setUp(self):
    super(AffiliationHasEitherPartyOrPersonTest, self).setUp()
    self.validator = rules.AffiliationHasEitherPartyOrPerson(None, None)

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


class UnreferencedEntitiesElectionDatesTest(absltest.TestCase):
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
      rules.UnreferencedEntitiesElectionDates(
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
      rules.UnreferencedEntitiesElectionDates(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type GpUnit with object id gpunit-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_office_fails(self):
    test_string = """
    <Office objectId="office-id">
    </Office>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      rules.UnreferencedEntitiesElectionDates(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type Office with object id office-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_top_level_election_and_contest_succeeds(self):
    test_string = """
    <Election objectId="election-id">
      <ContestCollection>
        <Contest objectId="ballot-measure-contest-id">
        </Contest>
      </ContestCollection>
    </Election>
    """

    rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_referenced_office_succeeds(self):
    test_string = """
    <ElectionReport xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election objectId="election-id">
        <ContestCollection>
          <Contest objectId="ballot-measure-contest-id" xsi:type="BallotMeasureContest">
            <OfficeIds>office-id</OfficeIds>
          </Contest>
        </ContestCollection>
      </Election>
      <OfficeCollection>
        <Office objectId="office-id">
        </Office>
      </OfficeCollection>
    </ElectionReport>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="OfficeIds" type="xs:IDREFS" />
    </xs:schema>
  """

    rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()

  def test_external_id_referenced_gp_unit_succeeds(self):
    test_string = """
    <ElectionReport xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election objectId="election-id">
        <ContestCollection>
          <Contest objectId="ballot-measure-contest-id" xsi:type="BallotMeasureContest">
            <OfficeIds>office-id</OfficeIds>
          </Contest>
        </ContestCollection>
      </Election>
      <GpUnitCollection>
        <GpUnit objectId="gpunit-1">
        </GpUnit>
      </GpUnitCollection>
      <OfficeCollection>
        <Office objectId="office-id">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>jurisdiction-id</OtherType>
              <Value>gpunit-1</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Office>
      </OfficeCollection>
    </ElectionReport>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="OfficeIds" type="xs:IDREFS" />
    </xs:schema>
  """

    rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()


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
      rules.UnreferencedEntitiesOfficeholders(
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
      rules.UnreferencedEntitiesOfficeholders(
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
      rules.UnreferencedEntitiesOfficeholders(
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
      rules.UnreferencedEntitiesOfficeholders(
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

    rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_unreferenced_party_leadership_succeeds(self):
    test_string = """
    <Leadership objectId="leadership-id">
    </Leadership>
    """

    rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_unreferenced_top_level_office_holder_tenure_succeeds(self):
    test_string = """
    <OfficeHolderCollection>
      <OfficeHolderTenure objectId="office-ten-id">
      </OfficeHolderTenure>
    </OfficeHolderCollection>
    """

    rules.UnreferencedEntitiesOfficeholders(
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

    rules.UnreferencedEntitiesOfficeholders(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()


class FeedTypeHasValidFeedLongevityTest(absltest.TestCase):

  def setUp(self):
    super(FeedTypeHasValidFeedLongevityTest, self).setUp()
    self.validator = rules.FeedTypeHasValidFeedLongevity(None, None)

  def test_feed_with_valid_type_and_longevity_succeeds(self):
    feed_string = """
      <Feed>
        <FeedType>pre-election</FeedType>
        <FeedLongevity>limited</FeedLongevity>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_feed_with_invalid_type_and_longevity_fails(self):
    feed_string = """
      <Feed>
        <FeedType>pre-election</FeedType>
        <FeedLongevity>evergreen</FeedLongevity>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Feed type pre-election has invalid feed longevity evergreen. Valid"
        " feed longevities for this type are ['limited', 'yearly']",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class FeedIdsAreUniqueTest(absltest.TestCase):

  def setUp(self):
    super(FeedIdsAreUniqueTest, self).setUp()
    self.validator = rules.FeedIdsAreUnique(None, None)

  def test_unique_feed_ids_succeeds(self):
    feed_collection_string = """
      <FeedCollection>
        <Feed>
          <FeedId>111</FeedId>
        </Feed>
        <Feed>
          <FeedId>222</FeedId>
        </Feed>
        <Feed>
          <FeedId>333</FeedId>
        </Feed>
      </FeedCollection>
      """

    self.validator.check(etree.fromstring(feed_collection_string))

  def test_duplicate_feed_ids_fails(self):
    feed_collection_string = """
      <FeedCollection>
        <Feed>
          <FeedId>111</FeedId>
        </Feed>
        <Feed>
          <FeedId>222</FeedId>
        </Feed>
        <Feed>
          <FeedId>111</FeedId>
        </Feed>
      </FeedCollection>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_collection_string))
    self.assertEqual(
        "FeedId 111 appears multiple times in the metadata feed. Feed ids must"
        " be unique.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class SourceDirPathsAreUniqueTest(absltest.TestCase):

  def setUp(self):
    super(SourceDirPathsAreUniqueTest, self).setUp()
    self.validator = rules.SourceDirPathsAreUnique(None, None)

  def test_unique_source_dir_paths_succeeds(self):
    feed_collection_string = """
      <FeedCollection>
        <Feed>
          <SourceDirPath>test_path_1</SourceDirPath>
        </Feed>
        <Feed>
          <SourceDirPath>test_path_2</SourceDirPath>
        </Feed>
        <Feed>
          <SourceDirPath>test_path_3</SourceDirPath>
        </Feed>
      </FeedCollection>
      """

    self.validator.check(etree.fromstring(feed_collection_string))

  def test_duplicate_source_dir_paths_fails(self):
    feed_collection_string = """
      <FeedCollection>
        <Feed>
          <SourceDirPath>test_path_1</SourceDirPath>
        </Feed>
        <Feed>
          <SourceDirPath>test_path_2</SourceDirPath>
        </Feed>
        <Feed>
          <SourceDirPath>test_path_1</SourceDirPath>
        </Feed>
      </FeedCollection>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_collection_string))
    self.assertEqual(
        "SourceDirPath test_path_1 appears multiple times in the metadata feed."
        " SourceDirPaths must be unique.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class SqsQueueNameRequiresS3SourceDirPathTest(absltest.TestCase):

  def setUp(self):
    super(SqsQueueNameRequiresS3SourceDirPathTest, self).setUp()
    self.validator = rules.SqsQueueNameRequiresS3SourceDirPath(None, None)

  def test_no_sqs_queue_name_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SourceDirPath>https://example.com/feed</SourceDirPath>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_sqs_queue_name_with_s3_source_dir_path_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SourceDirPath>s3://my-bucket/feed</SourceDirPath>
        <SqsQueueName>my-queue</SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_sqs_queue_name_missing_source_dir_path_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "If SqsQueueName is set, SourceDirPath must also be set and must be an"
        " s3 path for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_sqs_queue_name_non_s3_source_dir_path_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SourceDirPath>https://example.com/feed</SourceDirPath>
        <SqsQueueName>my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "If SqsQueueName is set, SourceDirPath must also be set and must be an"
        " s3 path for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class ElectionEventDatesAreSequentialTest(absltest.TestCase):

  def setUp(self):
    super(ElectionEventDatesAreSequentialTest, self).setUp()
    self.validator = rules.ElectionEventDatesAreSequential(None, None)

  def test_sequential_start_and_end_dates_succeeds(self):
    election_event_string = """
      <ElectionEvent>
        <StartDate>2024-01-01</StartDate>
        <EndDate>2024-01-02</EndDate>
      </ElectionEvent>
      """

    self.validator.check(etree.fromstring(election_event_string))

  def test_invalid_start_and_end_dates_fails(self):
    election_event_string = """
      <ElectionEvent>
        <StartDate>2024-01-02</StartDate>
        <EndDate>2024-01-01</EndDate>
      </ElectionEvent>
      """

    with self.assertRaises(loggers.ElectionError):
      self.validator.check(etree.fromstring(election_event_string))

  def test_invalid_start_and_full_delivery_dates_fails(self):
    election_event_string = """
      <ElectionEvent>
        <StartDate>2024-01-01</StartDate>
        <FullDeliveryDate>2024-01-02</FullDeliveryDate>
      </ElectionEvent>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_event_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "StartDate is older than FullDeliveryDate",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "ElectionEvent"
    )

  def test_invalid_initial_and_full_delivery_dates_fails(self):
    election_event_string = """
      <ElectionEvent>
        <InitialDeliveryDate>2024-01-02</InitialDeliveryDate>
        <FullDeliveryDate>2024-01-01</FullDeliveryDate>
      </ElectionEvent>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_event_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FullDeliveryDate is older than InitialDeliveryDate",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "ElectionEvent"
    )


class SourceDirPathMustBeSetAfterInitialDeliveryDateTest(absltest.TestCase):

  def setUp(self):
    super(SourceDirPathMustBeSetAfterInitialDeliveryDateTest, self).setUp()
    self.validator = rules.SourceDirPathMustBeSetAfterInitialDeliveryDate(
        None, None
    )

  @freezegun.freeze_time("2024-08-26")
  def test_no_initial_delivery_date_has_source_dir_path_succeeds(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2024-08-26")
  def test_initial_delivery_date_in_past_has_source_dir_path_succeeds(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <InitialDeliveryDate>2023-12-01</InitialDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <OfficeholderSubFeed>
          <InitialDeliveryDate>2027-01-02</InitialDeliveryDate>
        </OfficeholderSubFeed>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2024-08-26")
  def test_all_initial_delivery_date_in_future_has_source_dir_path_succeeds(
      self,
  ):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <InitialDeliveryDate>2027-12-01</InitialDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <OfficeholderSubFeed>
          <InitialDeliveryDate>2027-01</InitialDeliveryDate>
        </OfficeholderSubFeed>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2025-01-01")
  def test_no_initial_delivery_date_no_source_dir_path_succeeds(self):
    feed_string = """<Feed></Feed>"""

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2024-08-26")
  def test_all_initial_delivery_date_in_future_no_source_dir_path_succeeds(
      self,
  ):
    feed_string = """
      <Feed>
        <ElectionEventCollection>
          <ElectionEvent>
            <InitialDeliveryDate>2027-12-01</InitialDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <OfficeholderSubFeed>
          <InitialDeliveryDate>2027-01</InitialDeliveryDate>
        </OfficeholderSubFeed>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2024-08-26")
  def test_initial_delivery_date_in_past_no_source_dir_path_fails(self):
    feed_string = """
      <Feed>
        <FeedId>fake_feed_id</FeedId>
        <ElectionEventCollection>
          <ElectionEvent>
            <InitialDeliveryDate>2023-12-01</InitialDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <OfficeholderSubFeed>
          <InitialDeliveryDate>2027-01</InitialDeliveryDate>
        </OfficeholderSubFeed>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "SourceDirPath is not set but an InitialDeliveryDate is in the past "
        "for feed fake_feed_id.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class OfficeholderSubFeedDatesAreSequentialTest(absltest.TestCase):

  def setUp(self):
    super(OfficeholderSubFeedDatesAreSequentialTest, self).setUp()
    self.validator = rules.OfficeholderSubFeedDatesAreSequential(None, None)

  def test_sequential_initial_and_full_delivery_dates_succeeds(self):
    office_holder_sub_feed_string = """
      <OfficeholderSubFeed>
        <InitialDeliveryDate>2024-01-01</InitialDeliveryDate>
        <FullDeliveryDate>2024-01-02</FullDeliveryDate>
      </OfficeholderSubFeed>
      """

    self.validator.check(etree.fromstring(office_holder_sub_feed_string))

  def test_invalid_initial_and_full_delivery_dates_fails(self):
    office_holder_sub_feed_string = """
      <OfficeholderSubFeed>
        <InitialDeliveryDate>2024-01-02</InitialDeliveryDate>
        <FullDeliveryDate>2024-01-01</FullDeliveryDate>
      </OfficeholderSubFeed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(office_holder_sub_feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FullDeliveryDate is older than InitialDeliveryDate",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, "OfficeholderSubFeed"
    )


class FeedInactiveDateIsLatestDateTest(absltest.TestCase):

  def setUp(self):
    super(FeedInactiveDateIsLatestDateTest, self).setUp()
    self.validator = rules.FeedInactiveDateIsLatestDate(None, None)

  def test_sequential_inactive_and_full_delivery_dates_succeeds(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <FullDeliveryDate>2023-12-01</FullDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <OfficeholderSubFeed>
          <FullDeliveryDate>2023-01-02</FullDeliveryDate>
        </OfficeholderSubFeed>
        <FeedInactiveDate>2024-01-01</FeedInactiveDate>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_invalid_inactive_and_full_delivery_dates_election_event_fails(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <FullDeliveryDate>2023-12-01</FullDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate is older than FullDeliveryDate",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_invalid_inactive_and_full_delivery_dates_officeholder_sub_feed_fails(
      self,
  ):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <OfficeholderSubFeed>
          <FullDeliveryDate>2023-01-02</FullDeliveryDate>
        </OfficeholderSubFeed>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate is older than FullDeliveryDate",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_invalid_inactive_and_end_dates_fails(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <EndDate>2023-12-01</EndDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate is older than EndDate",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_cancelled_election_event_date_succeeds(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <EndDate>2023-12-01</EndDate>
            <ElectionDateStatus>canceled</ElectionDateStatus>
          </ElectionEvent>
        </ElectionEventCollection>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_other_election_date_status_fails(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <ElectionEventCollection>
          <ElectionEvent>
            <EndDate>2023-12-01</EndDate>
            <ElectionDateStatus>postponed</ElectionDateStatus>
          </ElectionEvent>
        </ElectionEventCollection>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate is older than EndDate",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_is_test_feed_older_inactive_date_succeeds(self):
    feed_string = """
      <Feed>
        <SourceDirPath>test_path_1</SourceDirPath>
        <IsTest>true</IsTest>
        <ElectionEventCollection>
          <ElectionEvent>
            <EndDate>2023-12-01</EndDate>
            <FullDeliveryDate>2023-12-01</FullDeliveryDate>
          </ElectionEvent>
        </ElectionEventCollection>
        <FeedInactiveDate>2022-01-01</FeedInactiveDate>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))


class FeedHasValidCountryCodeTest(absltest.TestCase):

  def setUp(self):
    super(FeedHasValidCountryCodeTest, self).setUp()
    self.validator = rules.FeedHasValidCountryCode(None, None)

  def test_valid_country_code_succeeds(self):
    feed_string = """
      <Feed>
        <CountryCode>US</CountryCode>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_valid_election_dates_succeeds(self):
    feed_string = """
      <Feed>
        <FeedType>election-dates</FeedType>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_valid_voter_information_succeeds(self):
    feed_string = """
      <Feed>
        <FeedType>voter-information</FeedType>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_invalid_country_code_fails(self):
    feed_string = """
      <Feed>
        <CountryCode>XX</CountryCode>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Invalid country code XX.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_missing_country_code_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <FeedType>pre-election</FeedType>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Feed test-feed is missing CountryCode.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class FeedInactiveDateSetForNonEvergreenFeedTest(absltest.TestCase):

  def setUp(self):
    super(FeedInactiveDateSetForNonEvergreenFeedTest, self).setUp()
    self.validator = rules.FeedInactiveDateSetForNonEvergreenFeed(None, None)

  def test_evergreen_feed_without_inactive_date_succeeds(self):
    feed_string = """
      <Feed>
        <FeedLongevity>evergreen</FeedLongevity>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_evergreen_feed_with_inactive_date_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <FeedLongevity>pre-election</FeedLongevity>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate is not set for non-evergreen feed with FeedId"
        " test-feed.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class DeprecatedPartyLeadershipSchemaTest(absltest.TestCase):

  def setUp(self):
    super(DeprecatedPartyLeadershipSchemaTest, self).setUp()
    self.validator = rules.DeprecatedPartyLeadershipSchema(None, None)

  def test_new_party_leadership_schema_succeeds(self):
    party_string = """
      <Party objectId="party-id">
        <Leadership objectId="party-leadership-id">
          <PartyLeaderId>person-id</PartyLeaderId>
          <Type>party-leader</Type>
        </Leadership>
      </Party>
      """

    self.validator.check(etree.fromstring(party_string))

  def test_deprecated_party_leader_schema_fails(self):
    party_string = """
      <Party objectId="party-id">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>party-leader-id</OtherType>
            <Value>person-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(party_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Specifying party leadership via external identifiers is deprecated."
        " Please use the PartyLeadership element instead.",
    )

  def test_deprecated_party_chair_schema_fails(self):
    party_string = """
      <Party objectId="party-id">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>party-chair-id</OtherType>
            <Value>person-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(party_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Specifying party leadership via external identifiers is deprecated."
        " Please use the PartyLeadership element instead.",
    )


class ElectoralCommissionCollectionExistsTest(absltest.TestCase):

  def setUp(self):
    super(ElectoralCommissionCollectionExistsTest, self).setUp()
    self.validator = rules.ElectoralCommissionCollectionExists(None, None)

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
    self.validator = rules.VoterInformationCollectionExists(None, None)

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
    self.validator = rules.NoExtraElectionElements(None, None)

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
    self.validator = rules.WarnOnElementsNotRecommendedForElection(None, None)

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
    self.validator = rules.NoExtraElectionReportCollections(None, None)

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


class FeedElementsShouldHaveSubElementsBasedOnTypeTest(parameterized.TestCase):
  """Feeds should have certain elements based on feed type."""

  def setUp(self):
    super(FeedElementsShouldHaveSubElementsBasedOnTypeTest, self).setUp()
    self.validator = rules.FeedElementsShouldHaveSubElementsBasedOnType(
        None, None
    )

  def test_officeholder_feed_with_officeholder_sub_feed_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>officeholder</FeedType>
        <OfficeholderSubFeed></OfficeholderSubFeed>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_officeholder_feed_without_officeholder_sub_feed_fails(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>officeholder</FeedType>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "OfficeholderSubFeed should exist for officeholder feed 123.",
    )

  def test_pre_election_feed_with_empty_election_event_collection_fails(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>pre-election</FeedType>
        <ElectionEventCollection></ElectionEventCollection>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectionEventCollection should have at least one ElectionEvent for"
        " pre-election feed 123.",
    )

  def test_pre_election_feed_with_election_event_collection_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>pre-election</FeedType>
        <ElectionEventCollection>
          <ElectionEvent></ElectionEvent>
        </ElectionEventCollection>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_pre_election_feed_without_election_event_collection_fails(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>pre-election</FeedType>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectionEventCollection should exist for pre-election feed 123.",
    )

  def test_election_results_feed_with_empty_election_event_collection_fails(
      self,
  ):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>election-results</FeedType>
        <ElectionEventCollection></ElectionEventCollection>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectionEventCollection should have at least one ElectionEvent for"
        " election-results feed 123.",
    )

  def test_election_results_feed_with_election_event_collection_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>election-results</FeedType>
        <ElectionEventCollection>
          <ElectionEvent></ElectionEvent>
        </ElectionEventCollection>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_election_results_feed_without_election_event_collection_fails(self):
    feed_string = """
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>election-results</FeedType>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "ElectionEventCollection should exist for election-results feed 123.",
    )

  @parameterized.parameters("committee", "election-dates", "voter-information")
  def test_other_feed_type_without_specific_sub_elements_succeeds(
      self, feed_type
  ):
    feed_string = f"""
      <Feed>
        <FeedId>123</FeedId>
        <FeedType>{feed_type}</FeedType>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))


class NotEmptyUniqueDataSourceUrisTest(absltest.TestCase):

  def setUp(self):
    super(NotEmptyUniqueDataSourceUrisTest, self).setUp()
    self.validator = rules.NotEmptyUniqueDataSourceUris(None, None)

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
    self.validator = rules.UniqueDataSourceDisplayNames(None, None)

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
    self.validator = rules.UniqueDataSourceLanguages(None, None)

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
    self.validator = rules.AttributionDepthLimit(None, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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

    validator = rules.AttributionContainsNoCycles(tree, None)

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
    self.validator = rules.ValidateSpecialBallotSelectionCountedInTotal(
        None,
        None,
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
    self.validator = rules.ValidateIncludeInAggregationBallotSelections(
        None, None
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


class RulesTest(absltest.TestCase):

  def test_all_rules_included_succeeds(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    possible_rules.remove(base.MissingFieldRule)
    possible_rules.remove(rules.UnreferencedEntitiesBase)

    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()

# -*- coding: utf-8 -*-
"""Unit test for common_rules.py."""

import datetime
import io
from unittest.mock import MagicMock

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import common_rules
from lxml import etree


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
    validator = common_rules.Schema(election_tree, SchemaTest._schema_tree)

    validator.check()

  def test_schema_parse_failure_fails(self):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType"/>
      </xs:schema>
    """)
    election_tree = etree.fromstring("<Report/>")
    validator = common_rules.Schema(election_tree, schema_tree)

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
    validator = common_rules.Schema(election_tree, SchemaTest._schema_tree)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn(
        "The election file didn't validate against schema",
        context.exception.log_entry[0].message,
    )


class OptionalAndEmptyTest(absltest.TestCase):

  def setUp(self):
    super(OptionalAndEmptyTest, self).setUp()
    self.validator = common_rules.OptionalAndEmpty(None, None)

  def test_optional_elements_succeeds(self):
    schema_tree = etree.fromstring(b"""
      <element>
        <element minOccurs="0" name="ThingOne" />
        <element minOccurs="1" name="ThingTwo" />
        <element minOccurs="0" name="ThingThree" />
        <simpleType minOccurs="0" />
      </element>
    """)
    self.validator = common_rules.OptionalAndEmpty(None, schema_tree)
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
    validator = common_rules.Encoding(election_tree, None)

    validator.check()

  def test_non_utf8_encoding_fails(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="us-ascii"?>
      <Report/>
    """)
    election_tree = etree.parse(root_string)
    validator = common_rules.Encoding(election_tree, None)

    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertEqual(
        context.exception.log_entry[0].message, "Encoding on file is not UTF-8"
    )


class LanguageCodeTest(absltest.TestCase):

  def setUp(self):
    super(LanguageCodeTest, self).setUp()
    self.validator = common_rules.LanguageCode(None, None)

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


class EmptyTextTest(absltest.TestCase):

  def setUp(self):
    super(EmptyTextTest, self).setUp()
    self.validator = common_rules.EmptyText(None, None)

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
    self.validator = common_rules.EmptyString(None, schema_tree)

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

  def test_element_with_child_elements_and_no_whitespace_succeeds(self):
    element_string = '<Name><Text language="en">Jerry</Text></Name>'
    element = etree.fromstring(element_string)

    self.validator.check(element)

  def test_element_with_child_elements_and_whitespace_succeeds(self):
    element_string = """
      <Name>
        <Text language="en">Jerry</Text>
      </Name>
    """
    element = etree.fromstring(element_string)

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
    validator = common_rules.DuplicateID(election_tree, None)

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
    validator = common_rules.DuplicateID(election_tree, None)

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
    self.gp_unit_ocd_id_validator = common_rules.GpUnitOcdId(
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

  @parameterized.parameters(*common_rules._GPUNIT_TYPES_WITHOUT_OCD_IDS)
  def test_gp_unit_without_ocd_id_is_valid_for_type_succeeds(self, gpunit_type):
    ocd_id_string = f"""
    <GpUnit objectId="1234567890">
      <Name>GpUnit of type: {gpunit_type}</Name>
      <Type>{gpunit_type}</Type>
    </GpUnit>
    """
    elements = etree.fromstring(ocd_id_string)

    self.gp_unit_ocd_id_validator.check(elements)

  def test_elements_includes_gp_unit_and_reporting_unit_succeeds(self):
    self.assertEqual(
        self.gp_unit_ocd_id_validator.elements(),
        ["GpUnit", "ReportingUnit"],
    )


class DuplicatedGpUnitOcdIdTest(absltest.TestCase):
  """2 GPUnits should not have same OCD ID."""

  def setUp(self):
    super(DuplicatedGpUnitOcdIdTest, self).setUp()
    self.validator = common_rules.DuplicatedGpUnitOcdId(None, None)

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
            <xs:element minOccurs="0" name="DiplomatReceivingStateId" type="xs:IDREF" />
            <xs:element minOccurs="0" name="DiplomatSendingStateId" type="xs:IDREF" />
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
    validator = common_rules.ValidIDREF(None, None)
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
    validator = common_rules.ValidIDREF(element_tree, None)
    expected_id_mapping = {
        "Person": {"per001", "per002"},
        "Candidate": {"can001"},
    }

    actual_id_mapping = validator._gather_object_ids_by_type()

    self.assertEqual(actual_id_mapping, expected_id_mapping)

  # _gather_reference_mapping test
  def test_map_of_idrefs_to_reference_types_succeeds(self):
    validator = common_rules.ValidIDREF(None, ValidIDREFTest._schema_tree)
    validator.object_id_mapping = {
        "Person": {"per001", "per002"},
        "Candidate": {"can001"},
    }
    expected_reference_mapping = {
        "DiplomatReceivingStateId": "GpUnit",
        "DiplomatSendingStateId": "GpUnit",
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
    validator = common_rules.ValidIDREF(None, None)
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
        "DiplomatReceivingStateId": "GpUnit",
        "DiplomatSendingStateId": "GpUnit",
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
    validator = common_rules.ValidIDREF(None, None)
    validator.element_reference_mapping = {
        "PersonId": "Person",
        "ElectoralDistrictId": "GpUnit",
    }

    self.assertEqual(validator.elements(), ["PersonId", "ElectoralDistrictId"])

  # check test
  def test_idref_elements_reference_the_proper_type_succeeds(self):
    validator = common_rules.ValidIDREF(None, None)
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
    validator = common_rules.ValidIDREF(None, None)
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
    validator = common_rules.ValidIDREF(None, None)
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
    self.validator = common_rules.BadCharactersInPersonFullName(None, None)

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
    self.validator = common_rules.DuplicateGpUnits(None, None)
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
    self.validator = common_rules.OtherType(None, None)

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
    validator = common_rules.OtherType(None, schema_tree)
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
    validator = common_rules.UniqueLabel(None, schema_tree)

    self.assertEqual(["Directions"], validator.elements())

  def test_all_labels_are_unique_succeeds(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    validator = common_rules.UniqueLabel(None, None)

    validator.check(element)
    no_element_label_string = """
      <Directions/>
    """
    element = etree.fromstring(no_element_label_string)
    validator = common_rules.UniqueLabel(None, None)
    validator.check(element)

  def test_not_all_labels_are_unique_fails(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    validator = common_rules.UniqueLabel(None, None)
    validator.labels = {"us-standard"}

    with self.assertRaises(loggers.ElectionError):
      validator.check(element)


class PersonHasUniqueFullNameTest(absltest.TestCase):

  def setUp(self):
    super(PersonHasUniqueFullNameTest, self).setUp()
    self.validator = common_rules.PersonHasUniqueFullName(None, None)

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


class IndependentPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(IndependentPartyNameTest, self).setUp()
    self.validator = common_rules.IndependentPartyName(None, None)

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
    self.validator = common_rules.ValidStableID(None, None)

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

    common_rules.UniqueStableID(election_tree, None).check()

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
      common_rules.UniqueStableID(election_tree, None).check()
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
      common_rules.UniqueStableID(election_tree, None).check()
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
      common_rules.UniqueStableID(election_tree, None).check()
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
    self.validator = common_rules.MissingStableIds(None, None)

  def test_elements_succeeds(self):
    self.assertEqual(
        self.validator.elements(),
        common_rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS,
    )

  @parameterized.parameters(
      *common_rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS
  )
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

  @parameterized.parameters(
      *common_rules.MissingStableIds._ELEMENTS_WITH_STABLE_IDS
  )
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
    self.validator = common_rules.PersonsMissingPartyData(None, None)

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
    self.validator = common_rules.AllCaps(None, None)

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
    self.validator = common_rules.AllLanguages(None, None)

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
    self.validator = common_rules.ValidEnumerations(None, None)

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
    validator = common_rules.ValidEnumerations(None, schema_tree)
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
    self.validator = common_rules.ValidateOcdidLowerCase(None, None)
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
    validator = common_rules.PartyLeadershipMustExist(election_tree, None)
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
    validator = common_rules.PartyLeadershipMustExist(election_tree, None)
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

    common_rules.PartyLeadershipMustExist(election_tree, None).check()

  def test_party_leadership_exists_fails(self):
    xml_string = """
      <xml>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError):
      common_rules.PartyLeadershipMustExist(election_tree, None).check()


class ProhibitElectionDataTest(absltest.TestCase):

  def test_election_element_is_not_present_succeeds(self):
    root_string = io.BytesIO(b"""
      <xml>
        <PersonCollection/>
      </xml>
    """)
    election_tree = etree.parse(root_string)

    common_rules.ProhibitElectionData(election_tree, None).check()

  def test_election_element_is_present_fails(self):
    root_string = io.BytesIO(b"""
      <xml>
        <Election/>
      </xml>
    """)
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as context:
      common_rules.ProhibitElectionData(election_tree, None).check()
    self.assertIn(
        "Election data is prohibited", context.exception.log_entry[0].message
    )


class PersonsHaveValidGenderTest(absltest.TestCase):

  def setUp(self):
    super(PersonsHaveValidGenderTest, self).setUp()
    self.validator = common_rules.PersonsHaveValidGender(None, None)

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


class URIValidatorTest(absltest.TestCase):

  def setUp(self):
    super(URIValidatorTest, self).setUp()
    self.validator = common_rules.URIValidator(None, None)
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
    validator = common_rules.UniqueURIPerAnnotationCategory(None, None)

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
    validator = common_rules.UniqueURIPerAnnotationCategory(None, None)

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
    validator = common_rules.UniqueURIPerAnnotationCategory(election_tree, None)

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
    validator = common_rules.UniqueURIPerAnnotationCategory(election_tree, None)

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
    validator = common_rules.UniqueURIPerAnnotationCategory(election_tree, None)

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
    validator = common_rules.UniqueURIPerAnnotationCategory(election_tree, None)

    validator.check()


class ValidYoutubeURLTest(absltest.TestCase):

  def setUp(self):
    super(ValidYoutubeURLTest, self).setUp()
    self.validator = common_rules.ValidYoutubeURL(None, None)

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
    self.validator = common_rules.ValidTiktokURL(None, None)

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
    self.validator = common_rules.ValidURIAnnotation(None, None)

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

  def test_candidate_image_in_contact_information_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="candidate-image">
          <![CDATA[https://www.parlament.gv.at/test.jpg]]>
        </Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))


class CandidateImageInContactInformationTest(absltest.TestCase):

  def setUp(self):
    super(CandidateImageInContactInformationTest, self).setUp()
    self.validator = common_rules.CandidateImageInContactInformation(None, None)

  def test_valid_contact_information_without_candidate_image_succeeds(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-website">https://example.com</Uri>
      </ContactInformation>
    """

    self.validator.check(etree.fromstring(root_string))

  def test_empty_contact_information_succeeds(self):
    root_string = '<ContactInformation label="ci_par_at_1" />'

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
        "Annotation 'candidate-image' in ContactInformation.Uri is"
        " deprecated. Please use Person.ImageUri instead.",
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Uri")

  def test_multiple_candidate_images_in_contact_information_warns(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="candidate-image">https://fake.com/1.jpg</Uri>
        <Uri Annotation="candidate-image">https://fake.com/2.jpg</Uri>
      </ContactInformation>
    """

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(root_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Annotation 'candidate-image' in ContactInformation.Uri is"
        " deprecated. Please use Person.ImageUri instead.",
    )
    self.assertLen(context.exception.log_entry[0].elements, 2)


class OnlyOneCandidateImagePerPersonTest(absltest.TestCase):

  def setUp(self):
    super(OnlyOneCandidateImagePerPersonTest, self).setUp()
    self.validator = common_rules.OnlyOneCandidateImagePerPerson(None, None)

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
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

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
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

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
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

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
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

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
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_election_report_with_no_person_collection_is_valid_succeeds(self):
    root_string = "<ElectionReport></ElectionReport>"
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()

  def test_election_report_with_empty_person_collection_is_valid_succeeds(self):
    root_string = """
      <ElectionReport>
        <PersonCollection>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = common_rules.UniqueCandidateImageUris(election_tree, None)

    validator.check()


class OfficesHaveJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveJurisdictionIDTest, self).setUp()
    self.validator = common_rules.OfficesHaveJurisdictionID(None, None)

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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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
    validator = common_rules.ValidJurisdictionID(election_tree, None)
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

    common_rules.ValidJurisdictionID(election_tree, None).check()

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
      common_rules.ValidJurisdictionID(election_tree, None).check()
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
    self.validator = common_rules.OfficesHaveValidOfficeLevel(None, None)

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


class OfficesHaveValidOfficeRoleTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveValidOfficeRoleTest, self).setUp()
    self.validator = common_rules.OfficesHaveValidOfficeRole(None, None)

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


class DiplomaticOfficesHaveCorrespondingGpUnitsSetTest(absltest.TestCase):

  def setUp(self):
    super(DiplomaticOfficesHaveCorrespondingGpUnitsSetTest, self).setUp()
    self.validator = common_rules.DiplomaticOfficesHaveCorrespondingGpUnitsSet(
        None, None
    )

  def test_diplomat_office_with_sending_state_succeeds(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>diplomat</Role>
        <DiplomatSendingStateId>gpunit-fake-sending</DiplomatSendingStateId>
      </Office>
    """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_diplomat_office_with_receiving_state_succeeds(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>diplomat</Role>
        <DiplomatReceivingStateId>gpunit-fake-receiving</DiplomatReceivingStateId>
      </Office>
    """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_diplomat_office_with_both_states_succeeds(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>diplomat</Role>
        <DiplomatSendingStateId>gpunit-fake-sending</DiplomatSendingStateId>
        <DiplomatReceivingStateId>gpunit-fake-receiving</DiplomatReceivingStateId>
      </Office>
    """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_non_diplomat_office_without_states_succeeds(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>upper house</Role>
      </Office>
    """
    element = etree.fromstring(test_string)

    self.validator.check(element)

  def test_diplomat_office_without_states_fails(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>diplomat</Role>
      </Office>
    """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office with role 'diplomat' must have at least one of"
        " DiplomatSendingStateId or DiplomatReceivingStateId set.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "off-fake-1",
    )

  def test_diplomat_office_with_empty_states_fails(self):
    test_string = """
      <Office objectId="off-fake-1">
        <Role>diplomat</Role>
        <DiplomatSendingStateId>   </DiplomatSendingStateId>
        <DiplomatReceivingStateId></DiplomatReceivingStateId>
      </Office>
    """
    element = etree.fromstring(test_string)

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(element)

    self.assertEqual(
        context.exception.log_entry[0].message,
        "Office with role 'diplomat' must have at least one of"
        " DiplomatSendingStateId or DiplomatReceivingStateId set.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"),
        "off-fake-1",
    )


class GpUnitsCyclesRefsValidationTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsCyclesRefsValidationTest, self).setUp()
    self.validator = common_rules.GpUnitsCyclesRefsValidation(None, None)

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


class ValidPartyLeadershipDatesTest(absltest.TestCase):

  def setUp(self):
    super(ValidPartyLeadershipDatesTest, self).setUp()
    self.validator = common_rules.ValidPartyLeadershipDates(None, None)
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


class GpUnitsHaveInternationalizedNameTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveInternationalizedNameTest, self).setUp()
    self.validator = common_rules.GpUnitsHaveInternationalizedName(None, None)

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


class MissingFieldsErrorTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsErrorTest, self).setUp()
    self.validator = common_rules.MissingFieldsError(None, None)
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
    self.validator = common_rules.MissingFieldsWarning(None, None)
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
    self.validator = common_rules.MissingFieldsInfo(None, None)
    self.validator.setup()

  def test_sets_severity_level_to_succeeds(self):
    self.assertEqual(0, self.validator.get_severity())


class PartySpanMultipleCountriesTest(absltest.TestCase):

  def setUp(self):
    super(PartySpanMultipleCountriesTest, self).setUp()
    self.validator = common_rules.DuplicateGpUnits(None, None)
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
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
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
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_no_warning_if_gp_unit_without_country_succeeds(self):
    referenced_gpunits = "ru0001 ru0004"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_no_warning_if_one_gp_unit_succeeds(self):
    referenced_gpunits = "ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds"
    )

    validator.check(element)

  def test_multiple_countries_are_referenced_warns(self):
    referenced_gpunits = "ru0001 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
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
    validator = common_rules.PartySpanMultipleCountries(election_tree, None)
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
    self.gov_validator = (
        common_rules.NonExecutiveOfficeShouldHaveGovernmentBody(
            element_tree,
            None,
        )
    )
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_validator = (
        common_rules.NonExecutiveOfficeShouldHaveGovernmentBody(
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
    self.gov_validator = (
        common_rules.ExecutiveOfficeShouldNotHaveGovernmentBody(
            element_tree,
            None,
        )
    )
    root_string = """
      <Report>
        <OfficeHolderTenureCollection>
        </OfficeHolderTenureCollection>
      </Report>
    """
    element_tree = etree.fromstring(root_string)
    self.post_office_split_validator = (
        common_rules.ExecutiveOfficeShouldNotHaveGovernmentBody(
            element_tree,
            None,
        )
    )

  def test_executive_office_with_government_body_ids_fails(self):
    for office_role in common_rules._EXECUTIVE_OFFICE_ROLES:
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
    for office_role in common_rules._EXECUTIVE_OFFICE_ROLES:
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
    self.validator = common_rules.MissingOfficeSelectionMethod(None, None)

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


class AllInternationalizedTextHaveEnVersionTest(absltest.TestCase):

  def setUp(self):
    super(AllInternationalizedTextHaveEnVersionTest, self).setUp()
    self.validator = common_rules.AllInternationalizedTextHaveEnVersion(
        None, None
    )

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


class MultipleInternationalizedTextWithSameLanguageCodeTest(
    parameterized.TestCase
):

  def setUp(self):
    super(MultipleInternationalizedTextWithSameLanguageCodeTest, self).setUp()
    self.validator = (
        common_rules.MultipleInternationalizedTextWithSameLanguageCode(
            None, None
        )
    )

  @parameterized.parameters(
      *common_rules._INTERNATIONALIZED_TEXT_ELEMENTS_WITH_ONLY_ONE_TEXT_PER_LANGUAGE
  )
  def test_multiple_texts_with_same_language_code_fails(self, element_name):
    election_string = f"""
      <{element_name}>
        <Text language="en">
          <![CDATA[Jamaica General Election, 2022]]>
        </Text>
        <Text language="en">
          <![CDATA[Other Jamaica General Election, 2022]]>
        </Text>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </{element_name}>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(election_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        'Multiple "en" texts found for "Jamaica General Election, 2022"',
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].tag, element_name
    )

  @parameterized.parameters(
      *common_rules._INTERNATIONALIZED_TEXT_ELEMENTS_WITH_ONLY_ONE_TEXT_PER_LANGUAGE
  )
  def test_one_text_per_language_code_succeeds(self, element_name):
    election_string = f"""
      <{element_name}>
        <Text language="en">
          <![CDATA[Jamaica General Election, 2022]]>
        </Text>
        <Text language="es">
          <![CDATA[Elecciones Generales de Jamaica, 2022]]>
        </Text>
      </{element_name}>
    """

    self.validator.check(etree.fromstring(election_string))


class DeprecatedPartyLeadershipSchemaTest(absltest.TestCase):

  def setUp(self):
    super(DeprecatedPartyLeadershipSchemaTest, self).setUp()
    self.validator = common_rules.DeprecatedPartyLeadershipSchema(None, None)

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
    validator = common_rules.CoalitionParties(None, None)

    validator.check(element)

  def test_coalition_does_not_define_party_id_no_party_id_fails(
      self,
  ):
    no_party_string = self._base_election_coalition.format("")
    element = etree.fromstring(no_party_string)
    validator = common_rules.CoalitionParties(None, None)

    with self.assertRaises(loggers.ElectionError):
      validator.check(element)

  def test_coalition_does_not_define_party_id_empty_party_id_fails(
      self,
  ):
    coalition_details = "<PartyIds></PartyIds>"
    empty_party_string = self._base_election_coalition.format(coalition_details)
    element = etree.fromstring(empty_party_string)
    validator = common_rules.CoalitionParties(None, None)

    with self.assertRaises(loggers.ElectionError):
      validator.check(element)

  def test_coalition_does_not_define_party_id_whitespace_fails(
      self,
  ):
    coalition_details = "<PartyIds>     </PartyIds>"
    all_space_party_string = self._base_election_coalition.format(
        coalition_details
    )
    element = etree.fromstring(all_space_party_string)
    validator = common_rules.CoalitionParties(None, None)

    with self.assertRaises(loggers.ElectionError):
      validator.check(element)


if __name__ == "__main__":
  absltest.main()

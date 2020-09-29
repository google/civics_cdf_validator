# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import hashlib
import inspect
import io

from absl.testing import absltest
import anytree
from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
from lxml import etree
from mock import MagicMock


class HelpersTest(absltest.TestCase):

  # get_external_id_values tests
  def testReturnsTextValueOfExternalIdentifiersForGivenType(self):
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
    actual_ocd_ids = rules.get_external_id_values(gp_unit_elem, "ocd-id")

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(expected_ocd_id, actual_ocd_ids[0])

    expected_other_stable = "stable-gpu-abc123"
    actual_stable_ids = rules.get_external_id_values(gp_unit_elem, "stable")

    self.assertLen(actual_stable_ids, 1)
    self.assertEqual(expected_other_stable, actual_stable_ids[0])

  def testReturnsValueElementOfExternalIdIfReturnElementsSpecified(self):
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
    actual_ocd_ids = rules.get_external_id_values(gp_unit_elem, "ocd-id", True)

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(
        expected_ocd_id, etree.tostring(actual_ocd_ids[0]).strip())

    expected_other_stable = b"<Value>stable-gpu-abc123</Value>"
    actual_stable = rules.get_external_id_values(gp_unit_elem, "stable", True)

    self.assertLen(actual_stable, 1)
    self.assertEqual(
        expected_other_stable, etree.tostring(actual_stable[0]).strip())

  def testIgnoresInvalidTypesAndOtherTypesThatShouldBeRegularType(self):
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
    self.assertEmpty(invalid_type_values)

    other_type_values = rules.get_external_id_values(gp_unit_elem, "ocd-id")
    self.assertEmpty(other_type_values)

  # get_additional_type_values tests
  def testReturnsTextValueOfAdditionalDataForGivenType(self):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">ocd-division/country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)

    expected_ocd_id = "ocd-division/country:us"
    actual_ocd_ids = rules.get_additional_type_values(office_elem, "ocd-id")

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(expected_ocd_id, actual_ocd_ids[0])

  def testAdditionalDataElementForGivenType(self):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)

    expected = b'<AdditionalData type="ocd-id">country:us</AdditionalData>'
    actual_ocd_ids = rules.get_additional_type_values(
        office_elem, "ocd-id", True)

    self.assertLen(actual_ocd_ids, 1)
    actual_ocd_id = etree.tostring(actual_ocd_ids[0]).strip()
    self.assertEqual(expected, actual_ocd_id)

  def testIgnoresElementsNotFoundOrMissingText(self):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id"></AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)

    actual_ocd_ids = rules.get_additional_type_values(office_elem, "ocd-id")
    self.assertEmpty(actual_ocd_ids)

    not_found = rules.get_additional_type_values(office_elem, "not-found")
    self.assertEmpty(not_found)

  # get_entity_info_for_value_type tests
  def testReturnsValuesForTypeFromExternalIdentifierAndAdditionalData(self):
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
        gp_unit_elem, "ocd-id")
    self.assertEqual(expected_ocd_ids, actual_ocd_ids)

  def testReturnsElementsForTypeFromExternalIdentifierAndAdditionalData(self):
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

    actual_ocd_ids = rules.get_entity_info_for_value_type(
        gp_unit_elem, "ocd-id", True)

    expected_data = b'<AdditionalData type="ocd-id">addtl-data</AdditionalData>'
    actual_data = etree.tostring(actual_ocd_ids[0]).strip()
    self.assertEqual(expected_data, actual_data)

    expected_external = b"<Value>external-id</Value>"
    actual_external = etree.tostring(actual_ocd_ids[1]).strip()
    self.assertEqual(expected_external, actual_external)

  # element_has_text tests
  def testReturnsTrueIfElementHasText(self):
    element_string = "<FirstName>Jerry</FirstName>"
    elem_has_text = rules.element_has_text(etree.fromstring(element_string))
    self.assertTrue(elem_has_text)

  def testReturnsFalseIfElementIsNone(self):
    elem_has_text = rules.element_has_text(None)
    self.assertFalse(elem_has_text)

  def testReturnsFalseIfElementHasNoText(self):
    element_string = "<FirstName></FirstName>"
    elem_has_text = rules.element_has_text(etree.fromstring(element_string))
    self.assertFalse(elem_has_text)

  def testReturnsFalseIfElementHasAllWhiteSpace(self):
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

  def testNoErrorForValidSchemaAndTree(self):
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
    schema_validator = rules.Schema(election_tree, SchemaTest._schema_tree)
    schema_validator.check()

  def testRaisesErrorForSchemaParseFailure(self):
    schema_tree = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType"/>
      </xs:schema>
    """)

    election_tree = etree.fromstring("<Report/>")
    schema_validator = rules.Schema(election_tree, schema_tree)

    with self.assertRaises(loggers.ElectionError) as ee:
      schema_validator.check()
    self.assertIn("The schema file could not be parsed correctly",
                  ee.exception.log_entry[0].message)

  def testRaisesErrorForInvalidTree(self):
    root_string = """
      <Person>
        <FirstName>Jerry</FirstName>
        <LastName>Seinfeld</LastName>
        <Age>38</Age>
      </Person>
    """

    election_tree = etree.fromstring(root_string)
    schema_validator = rules.Schema(election_tree, SchemaTest._schema_tree)

    with self.assertRaises(loggers.ElectionError) as ete:
      schema_validator.check()
    self.assertIn("The election file didn't validate against schema",
                  ete.exception.log_entry[0].message)


class OptionalAndEmptyTest(absltest.TestCase):

  def setUp(self):
    super(OptionalAndEmptyTest, self).setUp()
    self.optionality_validator = rules.OptionalAndEmpty(None, None)

  def testOnlyChecksOptionalElements(self):
    schema_tree = etree.fromstring(b"""
      <element>
        <element minOccurs="0" name="ThingOne" />
        <element minOccurs="1" name="ThingTwo" />
        <element minOccurs="0" name="ThingThree" />
        <simpleType minOccurs="0" />
      </element>
    """)

    self.optionality_validator = rules.OptionalAndEmpty(None, schema_tree)
    eligible_elements = self.optionality_validator.elements()

    self.assertLen(eligible_elements, 2)
    self.assertEqual(eligible_elements[0], "ThingOne")
    self.assertEqual(eligible_elements[1], "ThingThree")

  def testIgnoresIfElementIsSameAsPrevious(self):
    root_string = """
      <ThingOne></ThingOne>
    """

    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7
    self.optionality_validator.previous = non_empty_element
    self.optionality_validator.check(non_empty_element)

  def testIgnoresNonEmptyElements(self):
    root_string = """
      <ThingOne>BoomShakalaka</ThingOne>
    """

    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7
    self.optionality_validator.check(non_empty_element)

  def testThrowsWarningForEmptyElements_Null(self):
    empty_string = """
      <ThingOne></ThingOne>
    """

    empty_element = etree.fromstring(empty_string)
    empty_element.sourceline = 7
    with self.assertRaises(loggers.ElectionWarning):
      self.optionality_validator.check(empty_element)

  def testThrowsWarningForEmptyElements_Space(self):
    space_string = """
      <ThingOne>  </ThingOne>
    """

    space_element = etree.fromstring(space_string)
    space_element.sourceline = 7
    with self.assertRaises(loggers.ElectionWarning):
      self.optionality_validator.check(space_element)


class EncodingTest(absltest.TestCase):

  def testNoErrorForUTF8Encoding(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <Report/>
    """)

    election_tree = etree.parse(root_string)
    encoding_validator = rules.Encoding(election_tree, None)
    encoding_validator.check()

  def testRaisesErrorForNonUTF8Encoding(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="us-ascii"?>
      <Report/>
    """)

    election_tree = etree.parse(root_string)
    encoding_validator = rules.Encoding(election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      encoding_validator.check()
    self.assertEqual(ee.exception.log_entry[0].message,
                     "Encoding on file is not UTF-8")


class HungarianStyleNotationTest(absltest.TestCase):

  def setUp(self):
    super(HungarianStyleNotationTest, self).setUp()
    self.notation_validator = rules.HungarianStyleNotation(None, None)

  def testChecksAllElementsWithPrefixes(self):
    elements = self.notation_validator.elements()
    self.assertEqual(elements, self.notation_validator.elements_prefix.keys())

  def testIgnoresElementsWithNoObjectId(self):
    element_string = """
      <Party/>
    """

    party_element = etree.fromstring(element_string)
    self.notation_validator.check(party_element)

  def testObjectIdsUseAcceptedPrefix(self):
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
      self.notation_validator.check(party_element)

  def testRaisesExceptionForInvalidPrefix(self):
    element_string = """
      <Party objectId="pax0"/>
    """

    party_element = etree.fromstring(element_string)
    with self.assertRaises(loggers.ElectionInfo):
      self.notation_validator.check(party_element)

  def testRaisesAnErrorForAnUnlistedElement(self):
    element_string = """
      <Blamo objectId="pax0"/>
    """

    party_element = etree.fromstring(element_string)
    with self.assertRaises(KeyError):
      self.notation_validator.check(party_element)


class LanguageCodeTest(absltest.TestCase):

  def setUp(self):
    super(LanguageCodeTest, self).setUp()
    self.language_code_validator = rules.LanguageCode(None, None)

  def testOnlyChecksTextElements(self):
    self.assertEqual(self.language_code_validator.elements(), ["Text"])

  def testIgnoresElementsWithoutLanguageAttribute(self):
    element_string = """
      <Text>BoomShakalaka</Text>
    """

    text_element = etree.fromstring(element_string)
    self.language_code_validator.check(text_element)

  def testLanguageAttributeIsValidTag(self):
    element_string = """
      <Text language="en">BoomShakalaka</Text>
    """

    text_element = etree.fromstring(element_string)
    self.language_code_validator.check(text_element)

  def testRaiseErrorForInvalidLanguageAttributes_Invalid(self):
    invalid_string = """
      <Text language="zzz">BoomShakalaka</Text>
    """

    invalid_element = etree.fromstring(invalid_string)
    with self.assertRaises(loggers.ElectionError):
      self.language_code_validator.check(invalid_element)

  def testRaiseErrorForInvalidLanguageAttributes_Empty(self):
    empty_string = """
      <Text language="">BoomShakalaka</Text>
    """

    empty_element = etree.fromstring(empty_string)
    with self.assertRaises(loggers.ElectionError):
      self.language_code_validator.check(empty_element)


class PercentSumTest(absltest.TestCase):

  def setUp(self):
    super(PercentSumTest, self).setUp()
    self.percent_validator = rules.PercentSum(None, None)
    self.root_string = """
      <Contest>
        <BallotSelection>
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def testOnlyChecksContestElements(self):
    self.assertEqual(["Contest"], self.percent_validator.elements())

  def testZeroPercentTotalIsValid(self):
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
    self.percent_validator.check(element)

  def testOneHundredPercentTotalIsValid(self):
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
    self.percent_validator.check(element)

  def testThrowsAnErrorForInvalidPercents(self):
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
      self.percent_validator.check(element)

  def testOnlyUseCountForOtherTypeTotalPercent_RegularType(self):
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
    self.percent_validator.check(element)

  def testOnlyUseCountForOtherTypeTotalPercent_Invalid(self):
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
    self.percent_validator.check(element)


class EmptyTextTest(absltest.TestCase):

  def setUp(self):
    super(EmptyTextTest, self).setUp()
    self.empty_text_validator = rules.EmptyText(None, None)

  def testOnlyChecksTextElements(self):
    self.assertEqual(["Text"], self.empty_text_validator.elements())

  def testIgnoresNonEmptyElements(self):
    element_string = """
      <Text>Boomshakalaka</Text>
    """

    element = etree.fromstring(element_string)
    self.empty_text_validator.check(element)

  def testIgnoresEmptyElements(self):
    element_string = """
      <Text></Text>
    """

    element = etree.fromstring(element_string)
    self.empty_text_validator.check(element)

  def testThrowsWarningForSpaceOnlyElements(self):
    empty_string = """
      <Text>   </Text>
    """

    element = etree.fromstring(empty_string)
    with self.assertRaises(loggers.ElectionWarning):
      self.empty_text_validator.check(element)


class DuplicateIDTest(absltest.TestCase):

  def testValidIfNoObjectIDValuesAreTheSame(self):
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
    duplicate_id_validator = rules.DuplicateID(election_tree, None)
    duplicate_id_validator.check()

  def testThrowErrorIfObjectIDsAreTheSame(self):
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
    duplicate_id_validator = rules.DuplicateID(election_tree, None)
    with self.assertRaises(loggers.ElectionError):
      duplicate_id_validator.check()


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
  def testGeneratesTwoMappingsAndSetsThemAsInstanceVariables(self):
    expected_obj_id_mapping = {
        "Person": set(["per0001"]),
        "Candidate": set(["can0001"]),
    }
    expected_elem_ref_mapping = {
        "PersonId": "Person",
        "ElectoralDistrictId": "GpUnit",
    }

    id_ref_validator = rules.ValidIDREF(None, None)

    obj_id_mock = MagicMock(return_value=expected_obj_id_mapping)
    id_ref_validator._gather_object_ids_by_type = obj_id_mock

    elem_ref_mock = MagicMock(return_value=expected_elem_ref_mapping)
    id_ref_validator._gather_reference_mapping = elem_ref_mock

    id_ref_validator.setup()
    self.assertEqual(
        expected_obj_id_mapping, id_ref_validator.object_id_mapping
    )
    self.assertEqual(
        expected_elem_ref_mapping, id_ref_validator.element_reference_mapping
    )

  # _gather_object_ids_by_type test
  def testReturnsMapOfElementTypesToSetOfObjectIds(self):
    element_tree = etree.fromstring(self._root_string)
    id_ref_validator = rules.ValidIDREF(element_tree, None)
    expected_id_mapping = {
        "Person": set(["per001", "per002"]),
        "Candidate": set(["can001"])
    }
    actual_id_mapping = id_ref_validator._gather_object_ids_by_type()

    self.assertEqual(expected_id_mapping, actual_id_mapping)

  # _gather_reference_mapping test
  def testReturnsMapOfIDREFsToReferenceTypes(self):
    id_ref_validator = rules.ValidIDREF(None, ValidIDREFTest._schema_tree)
    id_ref_validator.object_id_mapping = {
        "Person": set(["per001", "per002"]),
        "Candidate": set(["can001"])
    }

    expected_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }
    actual_reference_mapping = id_ref_validator._gather_reference_mapping()

    self.assertEqual(expected_reference_mapping, actual_reference_mapping)

  # _determine_reference_type test
  def testReturnsTheNameOfTheReferenceTypeForGivenElementName(self):
    id_ref_validator = rules.ValidIDREF(None, None)

    id_ref_validator.object_id_mapping = {
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
      actual_ref_type = id_ref_validator._determine_reference_type(ref_elem)
      try:
        self.assertEqual(expected_ref_type, actual_ref_type)
      except AssertionError:
        self.fail(("Expected {} to have a reference type of "
                   "{}. Instead got {}").format(ref_elem, expected_ref_type,
                                                actual_ref_type))

  # elements test
  def testReturnsListOfKeysFromElementReferenceMapping(self):
    id_ref_validator = rules.ValidIDREF(None, None)
    id_ref_validator.element_reference_mapping = {
        "PersonId": "Person",
        "ElectoralDistrictId": "GpUnit",
    }
    self.assertEqual(
        ["PersonId", "ElectoralDistrictId"], id_ref_validator.elements()
    )

  # check test
  def testIDREFElementsReferenceTheProperType(self):
    id_ref_validator = rules.ValidIDREF(None, None)
    id_ref_validator.object_id_mapping = {
        "Person": set(["per001", "per002"]),
        "GpUnit": set(["gp001", "gp002"]),
    }
    id_ref_validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }

    idref_element = etree.fromstring("""
      <ElectoralDistrictId>gp001</ElectoralDistrictId>
    """)
    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per001 per002</OfficeHolderPersonIds>
    """)
    empty_element = etree.fromstring("""
      <ElectoralDistrictId></ElectoralDistrictId>
    """)

    id_ref_validator.check(idref_element)
    id_ref_validator.check(idrefs_element)
    id_ref_validator.check(empty_element)

  def testThrowsErrorIfIDREFElementsFailToReferenceTheProperType(self):
    id_ref_validator = rules.ValidIDREF(None, None)
    id_ref_validator.object_id_mapping = {
        "Person": set(["per001", "per002"]),
        "GpUnit": set(["gp001", "gp002"]),
    }
    id_ref_validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }

    idref_element = etree.fromstring("""
      <ElectoralDistrictId>gp004</ElectoralDistrictId>
    """)
    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per004 per005</OfficeHolderPersonIds>
    """)

    with self.assertRaises(loggers.ElectionError) as ee:
      id_ref_validator.check(idref_element)
    self.assertIn(
        ("gp004 is not a valid IDREF. ElectoralDistrictId should contain an "
         "objectId from a GpUnit element."), ee.exception.log_entry[0].message
    )

    with self.assertRaises(loggers.ElectionError) as ee:
      id_ref_validator.check(idrefs_element)
    self.assertIn(
        ("per004 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.log_entry[0].message
    )
    self.assertIn(
        ("per005 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.log_entry[1].message
    )

  def testThrowsErrorIfReferenceTypeNotPresent(self):
    id_ref_validator = rules.ValidIDREF(None, None)
    id_ref_validator.object_id_mapping = {
        "GpUnit": set(["gp001", "gp002"]),
    }
    id_ref_validator.element_reference_mapping = {
        "ElectoralDistrictId": "GpUnit",
        "OfficeHolderPersonIds": "Person",
    }

    idrefs_element = etree.fromstring("""
      <OfficeHolderPersonIds>per004 per005</OfficeHolderPersonIds>
    """)

    with self.assertRaises(loggers.ElectionError) as ee:
      id_ref_validator.check(idrefs_element)
    self.assertIn(
        ("per004 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.log_entry[0].message
    )
    self.assertIn(
        ("per005 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.log_entry[1].message
    )


class ElectoralDistrictOcdIdTest(absltest.TestCase):

  def setUp(self):
    super(ElectoralDistrictOcdIdTest, self).setUp()
    self.root_string = """
      <ElectionReport>
        <GpUnitCollection>
          {}
        </GpUnitCollection>
      </ElectionReport>
    """

    open_mod = inspect.getmodule(open)
    self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = MagicMock(
        return_value=io.StringIO(downloaded_ocdid_file))

  # check tests
  def testThatGivenElectoralDistrictIdReferencesGpUnitWithValidOCDID(self):
    element = etree.fromstring(
        "<ElectoralDistrictId>ru0002</ElectoralDistrictId>")

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    election_tree = etree.fromstring(self.root_string.format(gp_unit))
    ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock

    ocdid_validator.check(element)

  def testItRaisesAnErrorIfTheOcdidLabelIsNotAllLowerCase(self):
    element = etree.fromstring(
        "<ElectoralDistrictId>ru0002</ElectoralDistrictId>")

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>oCd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    election_tree = etree.fromstring(self.root_string.format(gp_unit))
    ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock

    with self.assertRaises(loggers.ElectionError) as ee:
      ocdid_validator.check(element)
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The referenced GpUnit ru0002 does not have an ocd-id")
    self.assertEqual(ee.exception.log_entry[0].elements[0].tag,
                     "ElectoralDistrictId")

  def testItRaisesAnErrorIfTheReferencedGpUnitDoesNotExist(self):
    element = etree.fromstring(
        "<ElectoralDistrictId>ru9999</ElectoralDistrictId>")

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    election_tree = etree.fromstring(self.root_string.format(gp_unit))
    ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock

    with self.assertRaises(loggers.ElectionError) as ee:
      ocdid_validator.check(element)
    self.assertEqual(ee.exception.log_entry[0].message,
                     ("The ElectoralDistrictId element not refer to a GpUnit. "
                      "Every ElectoralDistrictId MUST reference a GpUnit"))
    self.assertEqual(ee.exception.log_entry[0].elements[0].tag,
                     "ElectoralDistrictId")

  def testItRaisesAnErrorIfTheReferencedGpUnitHasNoOCDID(self):
    element = etree.fromstring(
        "<ElectoralDistrictId>ru0002</ElectoralDistrictId>")

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
        </ExternalIdentifiers>
      </GpUnit>
    """
    election_tree = etree.fromstring(self.root_string.format(gp_unit))
    ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock

    with self.assertRaises(loggers.ElectionError) as ee:
      ocdid_validator.check(element)
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The referenced GpUnit ru0002 does not have an ocd-id")
    self.assertEqual(ee.exception.log_entry[0].elements[0].tag,
                     "ElectoralDistrictId")

  def testItRaisesAnErrorIfTheReferencedOcdidIsNotValid(self):
    element = etree.fromstring(
        "<ElectoralDistrictId>ru0002</ElectoralDistrictId>")

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    election_tree = etree.fromstring(self.root_string.format(gp_unit))
    ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    mock = MagicMock(return_value=False)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock

    with self.assertRaises(loggers.ElectionError) as ee:
      ocdid_validator.check(element)
    self.assertEqual(ee.exception.log_entry[0].message,
                     ("The ElectoralDistrictId refers to GpUnit ru0002 that"
                      " does not have a valid OCD ID "
                      "(ocd-division/country:us/state:ma)"))
    self.assertEqual(ee.exception.log_entry[0].elements[0].tag,
                     "ElectoralDistrictId")


class GpUnitOcdIdTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitOcdIdTest, self).setUp()
    root_string = """
      <ElectionReport>
        <GpUnitCollection>
          <GpUnit/>
          <GpUnit/>
          <GpUnit/>
        </GpUnitCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(root_string)
    self.gp_unit_validator = rules.GpUnitOcdId(election_tree, None)

    self.base_reporting_unit = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnit objectId="ru0030" xsi:type="ReportingUnit">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              {}
            </ExternalIdentifier>
          </ExternalIdentifiers>
          <Name>Middlesex County</Name>
          <Number>3</Number>
          <Type>{}</Type>
        </GpUnit>
      </ElectionReport>
    """

  def testItOnlyChecksReportingUnitElements(self):
    self.assertEqual(["ReportingUnit"], self.gp_unit_validator.elements())

  def testItChecksTheGivenReportingUnitHasAValidOcdid(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ma/county:middlesex</Value>",
        "county")
    report = etree.fromstring(reporting_unit)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithNoObjectId(self):
    reporting_unit = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnit xsi:type="ReportingUnit"/>
      </ElectionReport>
    """
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithoutProperDistrictType(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ma/county:middlesex</Value>",
        "county-council",
    )
    report = etree.fromstring(reporting_unit)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithNoOcdIdValue(self):
    reporting_unit = self.base_reporting_unit.format("", "county")
    report = etree.fromstring(reporting_unit)

    mock = MagicMock(return_value=True)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItRaisesAWarningIfOcdIdNotInListOfValidIds(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ny/county:nassau</Value>",
        "county",
    )
    report = etree.fromstring(reporting_unit)

    mock = MagicMock(return_value=False)
    gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd = mock
    with self.assertRaises(loggers.ElectionWarning):
      self.gp_unit_validator.check(report.find("GpUnit"))


class DuplicateGpUnitsTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateGpUnitsTest, self).setUp()
    self.gp_unit_validator = rules.DuplicateGpUnits(None, None)
    self.root_string = """
    <GpUnitCollection>
    {}
    </GpUnitCollection>
    """

  def testNoGpUnitsReturnsNone(self):
    self.gp_unit_validator.check(etree.fromstring(self.root_string))

  def testNoObjectIdsReturnsNone(self):
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
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testNoComposingGpUnitsReturnsNone(self):
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
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testNoComposingGpUnitsTextReturnsNone(self):
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
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testItProcessesCollectionAndDoesNotFindDuplicates(self):
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
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testItProcessesCollectionAndFindsDuplicatePaths(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertEqual("GpUnits ('ru0002', 'ru0004') are duplicates",
                     str(cm.exception.log_entry[0].message))

  def testItProcessesCollectionAndFindsDuplicateObjectIds(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertEqual("GpUnit is duplicated",
                     str(cm.exception.log_entry[0].message))
    self.assertEqual("ru0002",
                     str(cm.exception.log_entry[0].elements[0].get("objectId")))

  def testItFindsDuplicateObjectIdsAndDuplicatePaths(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertEqual("GpUnit is duplicated",
                     str(cm.exception.log_entry[0].message))
    self.assertEqual("ru0002",
                     str(cm.exception.log_entry[0].elements[0].get("objectId")))
    self.assertIn("GpUnits ('ru0002', 'ru0004') are duplicates",
                  str(cm.exception.log_entry[1].message))


class OtherTypeTest(absltest.TestCase):

  def setUp(self):
    super(OtherTypeTest, self).setUp()
    self.other_type_validator = rules.OtherType(None, None)

  def testOnlyChecksComplexTypesThatContainOtherTypeElement(self):
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

    expected_elements = ["Device"]
    eligible_elements = validator.elements()

    self.assertEqual(expected_elements, eligible_elements)

  def testItChecksForExistenceOfOtherType(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
        <OtherType>Best phone ever</OtherType>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    self.other_type_validator.check(complex_element)

  def testItIgnoresElementsWithNoType(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    self.other_type_validator.check(complex_element)

  def testItRaisesErrorIfOtherTypeNotPresent(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    with self.assertRaises(loggers.ElectionError):
      self.other_type_validator.check(complex_element)


class PartisanPrimaryTest(absltest.TestCase):

  _base_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  # elements test
  def testElections(self):
    election_string = PartisanPrimaryTest._base_report
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["Election"], prim_part_validator.elements())

  # check tests
  def testPartyIdsArePresentAndNonEmpty(self):
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

  def testRaisesErrorIfPartyIdsDoNotExist_NoParty_PartisanPrimary(self):
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

  def testRaisesErrorIfPartyIdsDoNotExist_EmptyParty_PartisanPrimary(self):
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

  def testRaisesErrorIfPartyIdsDoNotExist_WhiteSpace_PartisanPrimary(self):
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

  def testRaisesErrorIfPartyIdsDoNotExist_NoParty_OpenPrimaryElection(self):
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

  def testIgnoresMissingPartyIds_GeneralElection(self):
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

  def testIgnoresMissingPartyIds_NonpartisanPrimary(self):
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

  def testIgnoresMissingPartyIds_NoElectionType(self):
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

  def testHandlesMultipleElections(self):
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
      _general_candidate_contest)

  def testChecksElections(self):
    election_details = "<Name>2020 election</Name>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual(["Election"], prim_part_validator.elements())

  def testIgnoresContestsThatDoNotSuggestPrimary_NoName(self):
    root_string = self._base_candidate_contest
    root = etree.fromstring(root_string)

    election = root.find("Election")
    rules.PartisanPrimaryHeuristic(root, None).check(election)

  def testIgnoresContestsThatDoNotSuggestPrimary_EmptyName(self):
    contest_details = """
      <Name></Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    election = root.find("Election").find("Contest")
    rules.PartisanPrimaryHeuristic(root, None).check(election)

  def testThrowsWarningIfPossiblePrimaryDetected_Dem(self):
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

  def testThrowsWarningIfPossiblePrimaryDetected_Rep(self):
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

  def testThrowsWarningIfPossiblePrimaryDetected_Lib(self):
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

  def testEachCoalitionHasDefinedPartyId(self):
    coalition_details = "<PartyIds>abc123</PartyIds>"
    defined_party_string = self._base_election_coalition.format(
        coalition_details)
    element = etree.fromstring(defined_party_string)
    rules.CoalitionParties(None, None).check(element)

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_NoPartyId(self):
    no_party_string = self._base_election_coalition.format("")
    element = etree.fromstring(no_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_EmptyPartyId(self):
    coalition_details = "<PartyIds></PartyIds>"
    empty_party_string = self._base_election_coalition.format(coalition_details)
    element = etree.fromstring(empty_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_Whitespace(self):
    coalition_details = "<PartyIds>     </PartyIds>"
    all_space_party_string = self._base_election_coalition.format(
        coalition_details)
    element = etree.fromstring(all_space_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(None, None).check(element)


class UniqueLabelTest(absltest.TestCase):

  def testChecksElementsWithTypeInternationalizedText(self):
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

    label_validator = rules.UniqueLabel(None, schema_tree)
    self.assertEqual(["Directions"], label_validator.elements())

  def testMakesSureAllLabelsAreUnique(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.check(element)

    no_element_label_string = """
      <Directions/>
    """
    element = etree.fromstring(no_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.check(element)

  def testRaisesErrorIfNotAllLabelsAreUnique(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.labels = set(["us-standard"])
    with self.assertRaises(loggers.ElectionError):
      label_validator.check(element)


class CandidatesReferencedInRelatedContestsTest(absltest.TestCase):

  def setUp(self):
    super(CandidatesReferencedInRelatedContestsTest, self).setUp()
    self.cand_validator = rules.CandidatesReferencedInRelatedContests(
        None, None)

  # elements test
  def testChecksElectinReport(self):
    self.assertEqual(["ElectionReport"], self.cand_validator.elements())

  # _find_contest_node_by_object_id tests
  def testReturnsTreeNodeForGivenContestId(self):
    self.cand_validator.contest_tree_nodes = [
        anytree.AnyNode(id="con001"),
        anytree.AnyNode(id="con002"),
        anytree.AnyNode(id="con003"),
    ]
    expected_node = self.cand_validator.contest_tree_nodes[1]
    actual_node = self.cand_validator._find_contest_node_by_object_id("con002")
    self.assertEqual(expected_node, actual_node)

  def testReturnsNoneIfGivenIdDoesNotExist(self):
    self.cand_validator.contest_tree_nodes = [
        anytree.AnyNode(id="con001"),
        anytree.AnyNode(id="con002"),
        anytree.AnyNode(id="con003"),
    ]
    result = self.cand_validator._find_contest_node_by_object_id("con004")
    self.assertIsNone(result)

  # _register_person_to_candidate_to_contests tests
  def testReturnsMapOfPersonsToCandidatesToContests(self):
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
        }
    }
    actual_mapping = self.cand_validator._register_person_to_candidate_to_contests(
        report_elem)
    self.assertEqual(expected_mapping, actual_mapping)

  def testRaisesErrorIfCandidateIsNotReferencedInAContest(self):
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
    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator._register_person_to_candidate_to_contests(
          report_elem)
    self.assertEqual(("A Candidate should be referenced in a Contest. "
                      "Candidate can004 is not referenced."),
                     ee.exception.log_entry[0].message)

  # _construct_contest_trees tests
  def testCreatesNodeForEachContest_NoRelationships(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001"/>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    expected_contest_nodes = [
        anytree.AnyNode(id="con001", relatives=set()),
        anytree.AnyNode(id="con002", relatives=set()),
        anytree.AnyNode(id="con003", relatives=set()),
    ]
    self.cand_validator._construct_contest_trees(report_elem)

    for node in expected_contest_nodes:
      found_node = False
      for validator_node in self.cand_validator.contest_tree_nodes:
        if (node.id == validator_node.id and
            node.relatives == validator_node.relatives):
          found_node = True
      if not found_node:
        self.fail(("No matching node found for id: {} and "
                   "relative set: {}").format(node.id, node.relatives))

  def testAssignsParentForComposingContests(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002 con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)
    self.cand_validator._construct_contest_trees(report_elem)

    # assert each contest has a node created for it
    for con_id in ["con001", "con002", "con003"]:
      found_node = False
      for validator_node in self.cand_validator.contest_tree_nodes:
        if con_id == validator_node.id:
          found_node = True
      if not found_node:
        self.fail(("No matching node found for id: {}").format(con_id))

    # assert parent child relationships were created
    for node in self.cand_validator.contest_tree_nodes:
      if node.id == "con001":
        self.assertEqual("con002", node.children[0].id)
        self.assertEqual("con003", node.children[1].id)
      if node.id == "con002" or node.id == "con003":
        self.assertEqual("con001", node.parent.id)

  def testTreeRootsAreConnectedForAnySubsequentRelationship(self):
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
    self.cand_validator._construct_contest_trees(report_elem)

    # assert each contest has a node created for it
    for con_id in [
        "con001", "con002", "con003",
        "con004", "con005", "con006",
    ]:
      found_node = False
      for validator_node in self.cand_validator.contest_tree_nodes:
        if con_id == validator_node.id:
          found_node = True
      if not found_node:
        self.fail(("No matching node found for id: {}").format(con_id))

    # assert parent child relationships were created
    for node in self.cand_validator.contest_tree_nodes:
      if node.id == "con001":
        self.assertEqual("con002", node.children[0].id)
        self.assertEqual("con003", node.children[1].id)
      if node.id == "con002" or node.id == "con003":
        self.assertEqual("con001", node.parent.id)
      if node.id == "con004":
        self.assertEqual("con005", node.children[0].id)
        self.assertEqual("con006", node.children[1].id)
      if node.id == "con005" or node.id == "con006":
        self.assertEqual("con004", node.parent.id)

    # assert roots are connected for subsequent relationships
    tree_roots = set()
    for node in self.cand_validator.contest_tree_nodes:
      tree_roots.add(node.root)
    tree_roots_list = list(tree_roots)

    self.assertLen(tree_roots_list, 2)
    self.assertIn("con004", [node.id for node in tree_roots_list])
    self.assertIn("con001", [node.id for node in tree_roots_list])
    self.assertIn(tree_roots_list[1], tree_roots_list[0].relatives)
    self.assertIn(tree_roots_list[0], tree_roots_list[1].relatives)

  def testRaisesErrorIfInvalidComposingContestId(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con002 con004</ComposingContestIds>
        </Contest>
        <Contest objectId="con002"/>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator._construct_contest_trees(report_elem)
    self.assertEqual(("Contest con001 contains a composing Contest Id "
                      "(con004) that does not exist."),
                     ee.exception.log_entry[0].message)

  def testRaisesErrorIfContestHasMultipleParents(self):
    election_report = """
      <ContestCollection>
        <Contest objectId="con001">
          <ComposingContestIds>con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con002">
          <ComposingContestIds>con003</ComposingContestIds>
        </Contest>
        <Contest objectId="con003"/>
      </ContestCollection>
    """
    report_elem = etree.fromstring(election_report)

    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator._construct_contest_trees(report_elem)
    self.assertEqual(("Contest con003 is listed as a composing contest for "
                      "multiple contests (con002 and con001). A contest should"
                      " have no more than one parent."),
                     ee.exception.log_entry[0].message)

  def testRaisesErrorIfInvalidSubsequentContestId(self):
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

    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator._construct_contest_trees(report_elem)
    self.assertEqual(("Contest con001 contains a subsequent Contest Id "
                      "(con004) that does not exist."),
                     ee.exception.log_entry[0].message)

  # _check_candidate_contests_are_related tests
  def testReturnsTrueIfAllContestsInGivenListAreRelated_ParentChild(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_two.parent = node_one
    node_three.parent = node_one
    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three,
    ]

    contest_id_list = ["con001", "con002", "con003"]
    are_related = self.cand_validator._check_candidate_contests_are_related(
        contest_id_list
    )
    self.assertTrue(are_related)

  def testReturnsFalseIfAnyContestInGivenListNotRelated_ParentChild(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_two.parent = node_one
    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three,
    ]

    contest_id_list = ["con001", "con002", "con003"]
    are_related = self.cand_validator._check_candidate_contests_are_related(
        contest_id_list
    )
    self.assertFalse(are_related)

  def testReturnsTrueIfAllContestsInGivenListAreRelated_SubsequentRel(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_four = anytree.AnyNode(id="con004", relatives=set())

    # nodes one-two and three-four have parent-child rel
    # nodes one-three are relatives
    node_two.parent = node_one
    node_four.parent = node_three
    node_one.relatives.add(node_three)
    node_three.relatives.add(node_one)

    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three, node_four
    ]

    contest_id_list = ["con001", "con002", "con003", "con004"]
    are_related = self.cand_validator._check_candidate_contests_are_related(
        contest_id_list
    )
    self.assertEqual(node_one, node_two.root)
    self.assertEqual(node_three, node_four.root)
    self.assertTrue(are_related)

  def testReturnsFalseIfContestTreesNotRelated_SubsequentRel(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_four = anytree.AnyNode(id="con004", relatives=set())

    # nodes one-two and three-four have parent-child rel
    # nodes one-three are not relatives
    node_two.parent = node_one
    node_four.parent = node_three

    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three, node_four
    ]

    contest_id_list = ["con001", "con002", "con003", "con004"]
    are_related = self.cand_validator._check_candidate_contests_are_related(
        contest_id_list
    )
    self.assertEqual(node_one, node_two.root)
    self.assertEqual(node_three, node_four.root)
    self.assertFalse(are_related)

  # _check_separate_candidates_not_related tests
  def testReturnsTrueIfSeparateCandidatesBelongToSeparateContestFamilies(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_four = anytree.AnyNode(id="con004", relatives=set())
    node_five = anytree.AnyNode(id="con005", relatives=set())
    node_six = anytree.AnyNode(id="con006", relatives=set())

    # nodes one-two three-four five-six have parent-child rel
    # none of three families are related
    node_two.parent = node_one
    node_four.parent = node_three
    node_six.parent = node_five

    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three, node_four, node_five, node_six,
    ]

    # separate candidates for each contest family
    candidate_contest_mapping = {
        "can001": ["con001", "con002"],
        "can002": ["con003", "con004"],
        "can003": ["con005", "con006"],
    }

    valid_cands = self.cand_validator._check_separate_candidates_not_related(
        candidate_contest_mapping
    )
    self.assertTrue(valid_cands)

  def testReturnsFalseIfParentChildBelongToSeparateCandidates(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_four = anytree.AnyNode(id="con004", relatives=set())
    node_five = anytree.AnyNode(id="con005", relatives=set())
    node_six = anytree.AnyNode(id="con006", relatives=set())

    # nodes one-two three-four five-six have parent-child rel
    node_two.parent = node_one
    node_four.parent = node_three
    node_six.parent = node_five

    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three, node_four, node_five, node_six,
    ]

    # a separate candidate is used for con001 and con002
    # con001 is parent of con002 so this should be invalid
    candidate_contest_mapping = {
        "can001": ["con001"],
        "can002": ["con002", "con003", "con004"],
        "can003": ["con005", "con006"],
    }

    valid_cands = self.cand_validator._check_separate_candidates_not_related(
        candidate_contest_mapping
    )
    self.assertFalse(valid_cands)

  def testReturnsFalseIfSeparateCandidatesBelongToRelatedContestFamilies(self):
    node_one = anytree.AnyNode(id="con001", relatives=set())
    node_two = anytree.AnyNode(id="con002", relatives=set())
    node_three = anytree.AnyNode(id="con003", relatives=set())
    node_four = anytree.AnyNode(id="con004", relatives=set())
    node_five = anytree.AnyNode(id="con005", relatives=set())
    node_six = anytree.AnyNode(id="con006", relatives=set())

    # nodes one-two three-four five-six have parent-child rel
    # two of the families are related
    node_two.parent = node_one
    node_four.parent = node_three
    node_six.parent = node_five
    node_one.relatives.add(node_three)
    node_three.relatives.add(node_one)

    self.cand_validator.contest_tree_nodes = [
        node_one, node_two, node_three, node_four, node_five, node_six,
    ]

    # separate candidates for each contest family
    candidate_contest_mapping = {
        "can001": ["con001", "con002"],
        "can002": ["con003", "con004"],
        "can003": ["con005", "con006"],
    }

    valid_cands = self.cand_validator._check_separate_candidates_not_related(
        candidate_contest_mapping
    )
    self.assertFalse(valid_cands)

  # check tests
  def testChecksSamePersonCandidatesInUnrelatedContests(self):
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
    self.cand_validator.check(report_elem)

  def testChecksRepeatCandidatesValidInRelatedContests_Subsequent(self):
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
    self.cand_validator.check(report_elem)

  def testChecksRepeatCandidatesValidInRelatedContests_Composing(self):
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
    self.cand_validator.check(report_elem)

  def testChecksRepeatCandidatesValid_Composing_MultiDepth(self):
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
    # con003 is a "grandchild" of con001 and includes the same candidates
    self.cand_validator.check(report_elem)

  def testChecksRepeatCandidatesValid_RepeatSubsequent(self):
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
    self.cand_validator.check(report_elem)

  def testChecksRepeatCandidatesValid_Subsequent_MultiDepth(self):
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
    self.cand_validator.check(report_elem)

  def testRaisesErrorIfSameCandidateInUnrelatedContests(self):
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
    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator.check(report_elem)
    self.assertLen(ee.exception.log_entry, 1)
    self.assertEqual(("Candidate can001 appears in the following contests"
                      " which are not all related: con001, con002"),
                     ee.exception.log_entry[0].message)

  def testRaisesErrorIfPersonHasMultipleCandidatesInRelatedContests(self):
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
    with self.assertRaises(loggers.ElectionError) as ee:
      self.cand_validator.check(report_elem)
    self.assertLen(ee.exception.log_entry, 2)
    self.assertEqual(("Person per001 has separate candidates in contests "
                      "that are related."), ee.exception.log_entry[0].message)
    self.assertEqual(("Person per002 has separate candidates in contests "
                      "that are related."), ee.exception.log_entry[1].message)


class ProperBallotSelectionTest(absltest.TestCase):

  def setUp(self):
    super(ProperBallotSelectionTest, self).setUp()
    self.ballot_selection_validator = rules.ProperBallotSelection(None, None)

  def testItShouldCheckAllElementsListedAsKeysInSelectionMapping(self):
    elements = self.ballot_selection_validator.elements()

    self.assertLen(elements, 4)
    self.assertIn("BallotMeasureContest", elements)
    self.assertIn("CandidateContest", elements)
    self.assertIn("PartyContest", elements)
    self.assertIn("RetentionContest", elements)

  def testAllSelectionsInContestAreOfMatchingType(self):
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
    self.ballot_selection_validator.check(element.find("Contest"))

  def testRaisesAnErrorIfAllSelectionsInContestAreNotOfMatchingType(self):
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
      self.ballot_selection_validator.check(element.find("Contest"))


class PartiesHaveValidColorsTest(absltest.TestCase):

  def setUp(self):
    super(PartiesHaveValidColorsTest, self).setUp()
    self._base_string = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
          {}
        </Party>
    """
    self._color_str = "<Color>{}</Color>"
    self.color_validator = rules.PartiesHaveValidColors(None, None)

  def testPartiesHaveValidColorsLowercase(self):
    root_string = self._base_string.format(self._color_str.format("ff0000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)

  def testPartiesHaveValidColorsUppercase(self):
    root_string = self._base_string.format(self._color_str.format("FF0000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)

  def testColorHasPoundSign(self):
    root_string = self._base_string.format(self._color_str.format("#0000ff"))
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "#0000ff is not a valid hex color.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Color")

  def testColorTagMissingValue(self):
    root_string = self._base_string.format(self._color_str.format(""))
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Color tag is missing a value.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Color")

  def testPartiesHaveNonHex(self):
    root_string = self._base_string.format(self._color_str.format("green"))
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "green is not a valid hex color.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Color")

  def testPartyHasMoreThanOneColor(self):
    root_string = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
          <Color>ff0000</Color>
          <Color>008800</Color>
        </Party>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The Party has more than one color.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "par0001")


class ValidateDuplicateColorsTest(absltest.TestCase):

  def setUp(self):
    super(ValidateDuplicateColorsTest, self).setUp()
    self._base_string = """
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
    """
    self._color_str = "<Color>{}</Color>"
    self.color_validator = rules.ValidateDuplicateColors(None, None)

  def testPartiesHaveDuplicateColors(self):
    root_string = self._base_string.format(
        self._color_str.format("ff0000"),
        self._color_str.format("ff0000"),
        self._color_str.format("ff0000"),
    )
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.color_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Parties has the same color ff0000.")
    self.assertLen(cm.exception.log_entry[0].elements, 3)
    duplicated_parties = [cm.exception.log_entry[0].elements[0].get("objectId"),
                          cm.exception.log_entry[0].elements[1].get("objectId"),
                          cm.exception.log_entry[0].elements[2].get("objectId")]
    self.assertIn("par0001", duplicated_parties)
    self.assertIn("par0002", duplicated_parties)
    self.assertIn("par0003", duplicated_parties)

  def testPartiesHaveUniqueColors(self):
    root_string = self._base_string.format(
        self._color_str.format("ff0000"), self._color_str.format("0000ff"),
        self._color_str.format("008000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)


class DuplicatedPartyAbbreviationTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyAbbreviationTest, self).setUp()
    self.parties_validator = rules.DuplicatedPartyAbbreviation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual("<PartyCollection> does not have <Party> objects",
                     cm.exception.log_entry[0].message)

  def testPartyWithoutInternationalizedAbbreviation(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(str(cm.exception.log_entry[0].message),
                     ("<Party> does not have <InternationalizedAbbreviation> "
                      "objects"))
    self.assertEqual(str(cm.exception.log_entry[0].elements[0].get("objectId")),
                     "par0001")

  def testDuplicateInternationalizedAbbreviation(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Parties have the same abbreviation in en.")
    self.assertLen(cm.exception.log_entry[0].elements, 2)
    duplicated_parties = [cm.exception.log_entry[0].elements[0].get("objectId"),
                          cm.exception.log_entry[0].elements[1].get("objectId")]
    self.assertIn("par0003", duplicated_parties)
    self.assertIn("par0001", duplicated_parties)

  def testNoDuplicatedInternationalizedAbbreviation(self):
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
    self.parties_validator.check(element)


class PersonHasUniqueFullNameTest(absltest.TestCase):

  def setUp(self):
    super(PersonHasUniqueFullNameTest, self).setUp()
    self.people_validator = rules.PersonHasUniqueFullName(None, None)

  def testEmptyPersonCollection(self):
    root_string = """
      <PersonCollection>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.people_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "<PersonCollection> does not have <Person> objects")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].tag, "PersonCollection")

  def testPersonCollectionWithDuplicatedFullNameWithoutBirthday(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("Person has same full name",
                  cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "per_gb_6436252")

  def testPersonCollectionWithDuplicatedFullNameWithBirthday(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("Person has same full name",
                  cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "per_gb_64201052")

  def testPersonCollectionWithDuplicatedFullNameButDifferentBirthday(self):
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
    self.people_validator.check(element)

  def testPersonCollectionWithoutFullNameButSameName(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_647452">
          <FirstName>Jamie</FirstName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
        </Person>
        <Person objectId="per_gb_640052">
          <FirstName>Jamie</FirstName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("Person has same full name",
                  cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "per_gb_640052")

  def testPersonCollectionWithoutInformation(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6455552">
          <Gender>M</Gender>
        </Person>
        <Person objectId="per_gb_6456322">
          <Gender>M</Gender>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("Person has same full name",
                  cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "per_gb_6456322")

  def testPersonCollectionWithoutAnyWarning(self):
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
    self.people_validator.check(element)


class DuplicatedPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyNameTest, self).setUp()
    self.parties_validator = rules.DuplicatedPartyName(None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(str(cm.exception.log_entry[0].message),
                     "<PartyCollection> does not have <Party> objects")

  def testPartyWithoutName(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(str(cm.exception.log_entry[0].message),
                     "<Party> does not have <Name> objects")
    self.assertEqual(str(cm.exception.log_entry[0].elements[0].get("objectId")),
                     "par0001")

  def testDuplicatePartyName(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Parties have the same name in en.")
    self.assertLen(cm.exception.log_entry[0].elements, 2)
    duplicated_parties = [cm.exception.log_entry[0].elements[0].get("objectId"),
                          cm.exception.log_entry[0].elements[1].get("objectId")]
    self.assertIn("par0003", duplicated_parties)
    self.assertIn("par0001", duplicated_parties)

  def testUniquePartyName(self):
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
    self.parties_validator.check(element)


class MissingPartyNameTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyNameTranslationTest, self).setUp()
    self.parties_validator = rules.MissingPartyNameTranslation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "<PartyCollection> does not have <Party> objects")

  def testPartyWithoutName(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "<Party> does not have <Name> objects")

  def testMissingTranslationAtTheBeginning(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(("The feed is missing names translation to ro for parties "
                      ": {'par0001'}."), cm.exception.log_entry[0].message)

  def testMissingTranslationInTheMiddle(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The party name is not translated to all feed languages",
                  cm.exception.log_entry[0].message)
    self.assertIn("en", cm.exception.log_entry[0].message)
    self.assertIn("ro", cm.exception.log_entry[0].message)
    self.assertIn("You did it only for the following languages : {'en'}.",
                  cm.exception.log_entry[0].message)

  def testWithAllGoodTranslation(self):
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
    self.parties_validator.check(element)


class MissingPartyAbbreviationTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyAbbreviationTranslationTest, self).setUp()
    self.parties_validator = rules.MissingPartyAbbreviationTranslation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "<PartyCollection> does not have <Party> objects")

  def testPartyWithoutInternationalizedAbbreviation(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("<Party> does not have <InternationalizedAbbreviation> "
                      "objects"))
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "par0001")

  def testMissingTranslationAtTheBeginning(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("The feed is missing abbreviation translation to ro for "
                      "parties : {'par0001'}."))

  def testMissingTranslationInTheMiddle(self):
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
    with self.assertRaises(loggers.ElectionInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The party abbreviation is not translated to all feed "
                  "languages ", cm.exception.log_entry[0].message)
    self.assertIn("en", cm.exception.log_entry[0].message)
    self.assertIn("ro", cm.exception.log_entry[0].message)
    self.assertIn("You only did it for the following languages : {'en'}.",
                  cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "par0002")

  def testWithAllGoodTranslation(self):
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
    self.parties_validator.check(element)


class DuplicateContestNamesTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateContestNamesTest, self).setUp()
    self.duplicate_validator = rules.DuplicateContestNames(None, None)
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

  def testEveryContestHasAUniqueName(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    tres = "<Name>Treasurer</Name>"
    root_string = self._base_report.format(pres, sec, tres)
    election_tree = etree.fromstring(root_string)
    self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfContestIsMissingNameOrNameIsEmpty_Missing(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    root_string = self._base_report.format(pres, sec, "")
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionError):
      self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfContestIsMissingNameOrNameIsEmpty_Empty(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    empty = "<Name></Name>"
    root_string = self._base_report.format(pres, sec, empty)
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionError):
      self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfNameIsNotUnique(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    duplicate = "<Name>President</Name>"
    root_string = self._base_report.format(pres, sec, duplicate)
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionError):
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
    self.stable_id_validator = rules.ValidStableID(None, None)

  def testValidStableID(self):

    test_string = self.root_string.format("other", self.stable_string,
                                          "vageneral-cand-2013-va-obama")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testNonStableIDOtherTypesDontThrowError(self):

    test_string = self.root_string.format("other",
                                          "<OtherType>anothertype</OtherType>",
                                          "vageneral-cand-2013-va-obama")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testNonStableIDTypesDontThrowError(self):
    test_string = self.root_string.format("ocd-id", "",
                                          "ocd-id/country/state/thing")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testInvalidStableID(self):

    test_string = self.root_string.format("other", self.stable_string,
                                          "cand-2013-va-obama!")
    with self.assertRaises(loggers.ElectionError) as cm:
      self.stable_id_validator.check(etree.fromstring(test_string))
    self.assertEqual(
        cm.exception.log_entry[0].message,
        "Stable id 'cand-2013-va-obama!' is not in the correct format.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag,
                     "ExternalIdentifiers")

  def testEmptyStableIDFails(self):

    test_string = self.root_string.format("other", self.stable_string, "   ")
    with self.assertRaises(loggers.ElectionError) as cm:
      self.stable_id_validator.check(etree.fromstring(test_string))
    self.assertEqual(
        cm.exception.log_entry[0].message,
        "Stable id '   ' is not in the correct format.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag,
                     "ExternalIdentifiers")


class MissingStableIdsTest(absltest.TestCase):

  def setUp(self):
    super(MissingStableIdsTest, self).setUp()
    self.missing_ids_validator = rules.MissingStableIds(None, None)
    self.root_string = """
      {}
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>{}</OtherType>
          <Value>{}</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
      {}
    """

  def testStableIdPresentForOffice(self):
    test_string = self.root_string.format(
        "<Office objectId='off1'>", "stable", "stable-off0", "</Office>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForCandidate(self):
    test_string = self.root_string.format(
        "<Candidate objectId='can1'>", "stable", "stable-can1", "</Candidate>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForContest(self):
    test_string = self.root_string.format(
        "<Contest objectId='cont1'>", "stable", "stable-cont1", "</Contest>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForParty(self):
    test_string = self.root_string.format(
        "<Party objectId='par1'>", "stable", "stable-par1", "</Party>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForPerson(self):
    test_string = self.root_string.format(
        "<Person objectId='off1'>", "stable", "stable-per0", "</Person>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForBallotMeasureSelection(self):
    test_string = self.root_string.format(
        "<BallotSelection objectId='bms1'>",
        "stable", "stable-bms1", "</BallotSelection>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForReportingUnit(self):
    test_string = self.root_string.format(
        "<GpUnit objectId='ru0001'>", "stable",
        "stable-ru0001", "</GpUnit>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdPresentForCoalition(self):
    test_string = self.root_string.format(
        "<Coalition objectId='coa01'>", "stable",
        "stable-coa01", "</Coalition>")
    element = etree.fromstring(test_string)
    self.missing_ids_validator.check(element)

  def testStableIdMissingForOffice(self):
    test_string = self.root_string.format("<Office objectId='off1'>",
                                          "some-other-id", "some-other-value",
                                          "</Office>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForCandidate(self):
    test_string = self.root_string.format("<Candidate objectId='can1'>",
                                          "some-other-id", "some-other-value",
                                          "</Candidate>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForContest(self):
    test_string = self.root_string.format("<Contest objectId='con1'>",
                                          "some-other-id", "some-other-value",
                                          "</Contest>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForParty(self):
    test_string = self.root_string.format("<Party objectId='par1'>",
                                          "some-other-id", "some-other-value",
                                          "</Party>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForPerson(self):
    test_string = self.root_string.format("<Person objectId='per1'>",
                                          "some-other-id", "some-other-value",
                                          "</Person>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForCoalition(self):
    test_string = self.root_string.format("<Coalition objectId='coa1'>",
                                          "some-other-id", "some-other-value",
                                          "</Coalition>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForBallotSelection(self):
    test_string = self.root_string.format("<BallotSelection objectId='bms1'>",
                                          "some-other-id", "some-other-value",
                                          "</BallotSelection>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdMissingForGpUnit(self):
    test_string = self.root_string.format("<GpUnit objectId='off1'>",
                                          "some-other-id", "some-other-value",
                                          "</GpUnit>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForOffice(self):
    test_string = self.root_string.format(
        "<Office objectId='off1'>", "stable", "", "</Office>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForCandidate(self):
    test_string = self.root_string.format(
        "<Candidate objectId='can1'>", "stable", "", "</Candidate>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForContest(self):
    test_string = self.root_string.format(
        "<Contest objectId='con1'>", "stable", "", "</Contest>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForParty(self):
    test_string = self.root_string.format(
        "<Party objectId='par1'>", "stable", "", "</Party>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForPerson(self):
    test_string = self.root_string.format(
        "<Person objectId='per1'>", "stable", "", "</Person>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForCoalition(self):
    test_string = self.root_string.format(
        "<Coalition objectId='coa1'>", "stable", "", "</Coalition>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForBallotMeasureSelection(self):
    test_string = self.root_string.format(
        "<BallotSelection objectId='bms1'>", "stable", "", "</BallotSelection>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testStableIdEmptyTextForReportingUnit(self):
    test_string = self.root_string.format(
        "<GpUnit objectId='ru001'>", "stable", "", "</GpUnit>")
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForOffice(self):
    test_string = """
      <Office objectId="off0">
      </Office>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForCoalition(self):
    test_string = """
      <Coalition objectId="coa1">
      </Coalition>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForBallotMeasureSelection(self):
    test_string = """
      <BallotSelection objectId="bms">
      </BallotSelection>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForReportingUnit(self):
    test_string = """
      <GpUnit objectId="ru001">
      </GpUnit>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForCandidate(self):
    test_string = """
      <Candidate objectId="can1">
      </Candidate>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForContest(self):
    test_string = """
      <Contest objectId="con1">
      </Contest>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForParty(self):
    test_string = """
      <Party objectId="par1">
      </Party>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)

  def testMissingIdentifierBlockForPerson(self):
    test_string = """
      <Person objectId="off0">
      </Person>
    """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError):
      self.missing_ids_validator.check(element)


class PersonsMissingPartyDataTest(absltest.TestCase):

  def setUp(self):
    super(PersonsMissingPartyDataTest, self).setUp()
    self.party_validator = rules.PersonsMissingPartyData(None, None)

  def testChecksPersonElements(self):
    self.assertEqual(["Person"], self.party_validator.elements())

  def testGivenPersonElementHasPartyIdWithAValueInIt(self):
    element_string = """
      <Person objectId="p1">
        <PartyId>par1</PartyId>
      </Person>
    """
    self.party_validator.check(etree.fromstring(element_string))

  def testRaisesErrorForMissingOrEmptyPartyId(self):
    element_string = """
      <Person objectId="p1">
        <PartyId></PartyId>
      </Person>
    """

    with self.assertRaises(loggers.ElectionWarning):
      self.party_validator.check(etree.fromstring(element_string))


class AllCapsTest(absltest.TestCase):

  def setUp(self):
    super(AllCapsTest, self).setUp()
    self.caps_validator = rules.AllCaps(None, None)

  def testOnlyChecksListedElements(self):
    expected_elements = [
        "Candidate", "CandidateContest", "PartyContest", "Person"
    ]

    self.assertEqual(expected_elements, self.caps_validator.elements())

  def testMakesSureCandidateBallotNamesAreNotAllCapsIfTheyExist(self):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>Deandra Reynolds</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    self.caps_validator.check(element)

  def testIgnoresCandidateElementsWithNoBallotName(self):
    no_ballot_name_string = """
      <Candidate/>
    """
    element = etree.fromstring(no_ballot_name_string)

    self.caps_validator.check(element)

  def testIgnoresCandidateElementsWithNoText(self):
    no_text_string = """
      <Candidate>
        <BallotName/>
      </Candidate>
    """
    element = etree.fromstring(no_text_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfCandidateBallotNameIsAllCaps(self):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>DEANDRA REYNOLDS</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.caps_validator.check(element)

  def testMakesSureCandidateContestNamesAreNotAllCapsIfTheyExist(self):
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
    self.caps_validator.check(root_element.find(
        "Election//ContestCollection//Contest"))

  def testIgnoresCandidateContestElementsWithNoName(self):
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
    self.caps_validator.check(root_element.find(
        "Election//ContestCollection//Contest"))

  def testRaisesWarningIfCandidateContestNameIsAllCaps(self):
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
      self.caps_validator.check(root_element.find(
          "Election//ContestCollection//Contest"))

  def testMakesSurePartyContestNamesAreNotAllCapsIfTheyExist(self):
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
    self.caps_validator.check(root_element.find(
        "Election//ContestCollection//Contest"))

  def testIgnoresPartyContestElementsWithNoName(self):
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
    self.caps_validator.check(root_element.find(
        "Election//ContestCollection//Contest"))

  def testRaisesWarningIfPartyContestNameIsAllCaps(self):
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
      self.caps_validator.check(root_element.find(
          "Election//ContestCollection//Contest"))

  def testIgnoresPersonElementsWithNoFullName(self):
    no_full_name_string = """
      <Person/>
    """
    element = etree.fromstring(no_full_name_string)

    self.caps_validator.check(element)

  def testIgnoresPersonElementsWithNoText(self):
    no_text_string = """
      <Person>
        <FullName/>
      </Person>
    """
    element = etree.fromstring(no_text_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfFullNamesAreAllCaps_Person(self):
    person_string = """
      <Person>
        <FullName>
          <Text>DEANDRA REYNOLDS</Text>
        </FullName>
      </Person>
    """
    element = etree.fromstring(person_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.caps_validator.check(element)


class AllLanguagesTest(absltest.TestCase):

  def setUp(self):
    super(AllLanguagesTest, self).setUp()
    self.language_validator = rules.AllLanguages(None, None)

  def testOnlyChecksListedElements(self):
    expected_elements = ["BallotName", "BallotTitle", "FullName", "Name"]
    self.assertEqual(expected_elements, self.language_validator.elements())

  def testGivenElementHasTextForEachRequiredLanguage(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en", "es", "nl"]
    self.language_validator.check(etree.fromstring(root_string))

  def testGivenElementCanSupportMoreThanRequiredLanguages(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en"]
    self.language_validator.check(etree.fromstring(root_string))

  def testRaisesAnErrorIfRequiredLanguageIsMissing(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en", "es", "nl"]
    with self.assertRaises(loggers.ElectionError):
      self.language_validator.check(etree.fromstring(root_string))

  def testIgnoresElementsWithoutTextElements(self):
    empty_element_string = """
      <BallotName/>
    """
    self.language_validator.check(etree.fromstring(empty_element_string))


class ValidEnumerationsTest(absltest.TestCase):

  def setUp(self):
    super(ValidEnumerationsTest, self).setUp()
    self.enum_validator = rules.ValidEnumerations(None, None)

  def testElementsGathersValidEnumerationsAndReturnsElementsWithOtherType(self):
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
    enum_validator = rules.ValidEnumerations(None, schema_tree)
    expected_enumerations = ["ballot-measure", "initiative", "referendum"]
    expected_elements = ["Person"]

    elements = enum_validator.elements()
    self.assertEqual(expected_enumerations, enum_validator.valid_enumerations)
    self.assertEqual(expected_elements, elements)

  def testElementsOfTypeOtherDoNotUseValidEnumerationInOtherTypeField(self):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>state</Type>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["state"]
    self.enum_validator.check(element)

  def testRaisesAnErrorIfOtherTypeFieldHasValidEnumerationAsAValue(self):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>other</Type>
      <OtherType>state</OtherType>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["state"]
    with self.assertRaises(loggers.ElectionError):
      self.enum_validator.check(element)

  def testElementsOfTypeOtherForExternalIdentifierElements(self):
    type_other_string = """
      <ExternalIdentifier>
        <Type>stable</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["stable"]
    self.enum_validator.check(element)

  def testExternalIdentifierForValidEnumerationSetAsOtherType(self):
    type_other_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <OtherType>stable</OtherType>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["stable"]
    with self.assertRaises(loggers.ElectionError):
      self.enum_validator.check(element)

  def testIgnoresElementsWithNoTypeOrOtherType(self):
    no_type_string = """
      <ExternalIdentifier>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_type_string)

    self.enum_validator.check(element)

    no_other_type_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_other_type_string)

    self.enum_validator.check(element)


class ValidateOcdidLowerCaseTest(absltest.TestCase):

  def setUp(self):
    super(ValidateOcdidLowerCaseTest, self).setUp()
    self.ocdid_validator = rules.ValidateOcdidLowerCase(None, None)
    self.ext_ids_str = """
    <ExternalIdentifiers>
      <ExternalIdentifier>
       {}
       {}
      </ExternalIdentifier>
    </ExternalIdentifiers>
    """

  def testItChecksExternalIdentifiersElements(self):
    self.assertEqual(["ExternalIdentifiers"], self.ocdid_validator.elements())

  def testItMakesSureOcdidsAreAllLowerCase(self):
    valid_id_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>",
        "<Value>ocd-division/country:us/state:va</Value>")
    self.ocdid_validator.check(etree.fromstring(valid_id_string))

  def testRaisesWarningIfOcdidHasUpperCaseLetter(self):
    uppercase_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>",
        "<Value>ocd-division/country:us/state:VA</Value>")
    with self.assertRaises(loggers.ElectionWarning) as ew:
      self.ocdid_validator.check(etree.fromstring(uppercase_string))
    self.assertEqual(ew.exception.log_entry[0].message,
                     ("OCD-ID ocd-division/country:us/state:VA is not in all "
                      "lower case letters. Valid OCD-IDs should be all "
                      "lowercase."))
    self.assertEqual(ew.exception.log_entry[0].elements[0].tag,
                     "ExternalIdentifiers")

  def testIgnoresElementsWithoutValidOcdidXml(self):
    no_type_string = self.ext_ids_str.format("", "")
    self.ocdid_validator.check(etree.fromstring(no_type_string))

    non_ocdid_string = self.ext_ids_str.format("<Type>not-ocdid</Type>", "")
    self.ocdid_validator.check(etree.fromstring(non_ocdid_string))

    ocdid_missing_value_string = self.ext_ids_str.format(
        "<Type>ocd-id</Type>", "")
    self.ocdid_validator.check(etree.fromstring(ocdid_missing_value_string))

    empty_value_string = self.ext_ids_str.format("<Type>ocd-id</Type>",
                                                 "<Value></Value>")
    self.ocdid_validator.check(etree.fromstring(empty_value_string))


class ContestHasMultipleOfficesTest(absltest.TestCase):

  base_string = """<Contest objectId="con123">{}</Contest>"""

  def setUp(self):
    super(ContestHasMultipleOfficesTest, self).setUp()
    self.contest_offices_validator = rules.ContestHasMultipleOffices(None, None)

  def testOneOfficeValid(self):
    root_string = self.base_string.format("<OfficeIds>off-ar1-arb</OfficeIds>")
    element = etree.fromstring(root_string)
    self.contest_offices_validator.check(element)

  def testMultipleOfficesFail(self):
    root_string = self.base_string.format(
        "<OfficeIds>off-ar1-ara off-ar1-arb</OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.contest_offices_validator.check(element)
    self.assertEqual("Contest has more than one associated office.",
                     str(cm.exception.log_entry[0].message))
    self.assertEqual("con123",
                     str(cm.exception.log_entry[0].elements[0].get("objectId")))

  def testNoOfficesFail(self):
    root_string = self.base_string.format("<OfficeIds></OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.contest_offices_validator.check(element)
    self.assertEqual("Contest has no associated offices.",
                     str(cm.exception.log_entry[0].message))
    self.assertEqual("con123",
                     str(cm.exception.log_entry[0].elements[0].get("objectId")))


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
  def testReturnsPersonIdsFromPersonCollection(self):
    root_string = self._base_xml.format("")
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.PersonHasOffice(election_tree, None)

    reference_values = office_validator._gather_reference_values()
    expected_reference_values = set(["p1", "p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsPartyLeaderAndOfficeHolderIds(self):
    defined_collections = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
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
      </PartyCollection>
    """
    root_string = self._base_xml.format(defined_collections)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.PersonHasOffice(election_tree, None)

    defined_values = office_validator._gather_defined_values()
    expected_defined_values = set(["p1", "p2", "p3", "p4"])
    self.assertEqual(expected_defined_values, defined_values)

  # check tests
  def testEachPersonInACollectionIsReferencedByAnOffice(self):
    office_collection = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testIgnoresTreesWithNoRoots(self):
    no_root_string = io.BytesIO(b"<OfficeCollection/>")
    election_tree = etree.parse(no_root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testIgnoresRootsWithNoPersonCollection(self):
    no_collection_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection/>
      </xml>
    """)
    election_tree = etree.parse(no_collection_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testRaisesErrorIfPersonIsNotReferencedInAnyOffice(self):
    office_collection = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office/>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    with self.assertRaises(loggers.ElectionError):
      office_validator.check()

  def testRaisesErrorIfTheresAPersonCollectionButNoOfficeCollection(self):
    root_string = io.BytesIO(bytes(self._base_xml.encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    with self.assertRaises(loggers.ElectionError):
      office_validator.check()

  def testPartyLeadersDoNotRequireOffices(self):
    office_party_collections = """
      <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <PartyCollection>
          <Party>
            <Name>Republican Socialists</Name>
            <ExternalIdentifiers>
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
        bytes(self._base_xml.format(office_party_collections).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testPersonHasOneOffice(self):
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
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    rules.PersonHasOffice(election_tree, None).check()

  def testPersonHasOneOffice_fails(self):
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
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as cm:
      rules.PersonHasOffice(election_tree, None).check()

    self.assertIn("No defined data for p3 found in the feed.",
                  cm.exception.log_entry[0].message)

  def testOfficeHasOnePerson_fails(self):
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
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(loggers.ElectionError) as cm:
      rules.PersonHasOffice(election_tree, None).check()

    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office has 2 OfficeHolders. Must have exactly one.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "o2")


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
  def testReturnsSetOfPartyLeaderIds(self):
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
    leadership_validator = rules.PartyLeadershipMustExist(election_tree, None)

    reference_values = leadership_validator._gather_reference_values()
    expected_reference_values = set(["p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsSetOfPersonObjectIds(self):
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
    leadership_validator = rules.PartyLeadershipMustExist(election_tree, None)

    defined_values = leadership_validator._gather_defined_values()
    expected_defined_values = set(["p4", "p5"])
    self.assertEqual(expected_defined_values, defined_values)

  # check tests
  def testPartyLeadershipExists(self):
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

  def testPartyLeadershipExists_fails(self):
    xml_string = """
      <xml>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    with self.assertRaises(loggers.ElectionError):
      election_tree = etree.parse(root_string)
      rules.PartyLeadershipMustExist(election_tree, None).check()


class ProhibitElectionDataTest(absltest.TestCase):

  def testElectionElementIsNotPresent(self):
    root_string = io.BytesIO(b"""
      <xml>
        <PersonCollection/>
      </xml>
    """)
    election_tree = etree.parse(root_string)
    rules.ProhibitElectionData(election_tree, None).check()

  def testRaisesErrorIfElectionElementIsPresent(self):
    root_string = io.BytesIO(b"""
      <xml>
        <Election/>
      </xml>
    """)
    election_tree = etree.parse(root_string)
    with self.assertRaises(loggers.ElectionError) as ee:
      rules.ProhibitElectionData(election_tree, None).check()
    self.assertIn("Election data is prohibited",
                  ee.exception.log_entry[0].message)


class PersonsHaveValidGenderTest(absltest.TestCase):

  def setUp(self):
    super(PersonsHaveValidGenderTest, self).setUp()
    self.gender_validator = rules.PersonsHaveValidGender(None, None)

  def testOnlyGenderElementsAreChecked(self):
    self.assertEqual(["Gender"], self.gender_validator.elements())

  def testAllPersonsHaveValidGender(self):
    root_string = """
      <Gender>Female</Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIsCaseInsensitive(self):
    root_string = """
      <Gender>female</Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIgnoresEmptyValue(self):
    root_string = """
      <Gender></Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationFailsForInvalidValue(self):
    root_string = """
      <Gender>blamo</Gender>
    """
    gender_element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionError):
      self.gender_validator.check(gender_element)


class VoteCountTypesCoherencyTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountTypesCoherencyTest, self).setUp()
    self.vc_coherency = rules.VoteCountTypesCoherency(None, None)
    self.base_contest = """
      <Contest objectId="pc1" type="{}">
        <BallotSelection objectId="ps1-0">
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def testInvalidNotInPartyContest(self):
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
    self.vc_coherency.check(etree.fromstring(contest))

  def testInvalidNotInPartyContest_fails(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.vc_coherency.check(etree.fromstring(contest))

    for vc_type in rules.VoteCountTypesCoherency.CAND_VC_TYPES:
      self.assertIn(vc_type, str(cm.exception.log_entry[0].message))

  def testInvalidNotInCandidateContest(self):
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
    self.vc_coherency.check(etree.fromstring(contest))

  def testNonInvalidVCTypesDoNotFail(self):
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
    self.assertIsNone(self.vc_coherency.check(etree.fromstring(contest)))

  def testInvalidNotInCandidateContest_fails(self):
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
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)

    with self.assertRaises(loggers.ElectionError) as cm:
      self.vc_coherency.check(etree.fromstring(contest))

    for vc_type in rules.VoteCountTypesCoherency.PARTY_VC_TYPES:
      self.assertIn(vc_type, cm.exception.log_entry[0].message)
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "pc1")


class URIValidatorTest(absltest.TestCase):

  def setUp(self):
    super(URIValidatorTest, self).setUp()
    self.uri_validator = rules.URIValidator(None, None)
    self.uri_element = u"<Uri>{}</Uri>"

  def testOnlyChecksUriElements(self):
    self.assertEqual(["Uri"], self.uri_validator.elements())

  def testChecksForValidUri(self):
    valid_url = self.uri_element.format("http://www.whitehouse.gov")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testChecksForValidNonWwwUri(self):
    valid_url = self.uri_element.format(
        "https://zh.wikipedia.org/zh-tw/Fake_Page")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testChecksForValidUriWithParentheses(self):
    valid_url = self.uri_element.format(
        "http://en.wikipedia.org/wiki/Thomas_Jefferson_(Virginia)")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testRaisesAnErrorIfUriNotProvided(self):
    invalid_scheme = self.uri_element.format("")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("Missing URI value.", ee.exception.log_entry[0].message)

  def testRaisesAnErrorIfNoSchemeProvided(self):
    missing_scheme = self.uri_element.format("www.whitehouse.gov")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_scheme))
    self.assertIn("protocol - invalid", ee.exception.log_entry[0].message)

  def testRaisesAnErrorIfSchemeIsNotInApprovedList(self):
    invalid_scheme = self.uri_element.format("tps://www.whitehouse.gov")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("protocol - invalid", ee.exception.log_entry[0].message)

  def testRaisesAnErrorIfNetLocationNotProvided(self):
    missing_netloc = self.uri_element.format("missing/loc.md")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_netloc))
    self.assertIn("domain - missing", ee.exception.log_entry[0].message)

  def testRaisesAnErrorIfUriNotAscii(self):
    unicode_url = self.uri_element.format(u"https://nahnah.com/nopê")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(unicode_url))
    self.assertIn("not ascii encoded", ee.exception.log_entry[0].message)

  def testAllowsQueryParamsToBeIncluded(self):
    contains_query = self.uri_element.format(
        "http://www.whitehouse.gov?filter=yesplease")
    self.uri_validator.check(etree.fromstring(contains_query))

  def testAggregatesErrors(self):
    multiple_issues = self.uri_element.format("missing/loc.md?filter=yesplease")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(multiple_issues))
    self.assertIn("protocol - invalid", ee.exception.log_entry[0].message)
    self.assertIn("domain - missing", ee.exception.log_entry[0].message)


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
  def testReturnsADictWithEmptyPathsForEachAnnotationPlatformAndValue(self):
    facebook_uri = "<Uri Annotation='personal-facebook'>{}</Uri>"
    person_website_uri = "<Uri Annotation='personal-website'>{}</Uri>"
    party_website_uri = "<Uri Annotation='party-website'>{}</Uri>"
    wikipedia_uri = "<Uri Annotation='wikipedia'>{}</Uri>"

    fb_one = etree.fromstring(facebook_uri.format(
        "www.facebook.com/michael_scott"))
    fb_two = etree.fromstring(facebook_uri.format(
        "www.facebook.com/dwight_shrute"))
    personal_one = etree.fromstring(person_website_uri.format(
        "www.michaelscott.com"))
    personal_two = etree.fromstring(person_website_uri.format(
        "www.dwightshrute.com"))
    party_one = etree.fromstring(party_website_uri.format(
        "www.dundermifflin.com"))
    party_two = etree.fromstring(party_website_uri.format("www.sabre.com"))
    wiki_one = etree.fromstring(wikipedia_uri.format(
        "www.wikipedia.com/dundermifflin"))
    wiki_two = etree.fromstring(wikipedia_uri.format(
        "www.wikipedia.com/dundermifflin"))

    uri_elements = [
        fb_one, fb_two, personal_one, personal_two, party_one, party_two,
        wiki_one, wiki_two
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
        }
    }
    uri_validator = rules.UniqueURIPerAnnotationCategory(None, None)
    actual_mapping = uri_validator._extract_uris_by_category(uri_elements)

    self.assertEqual(expected_mapping, actual_mapping)

  def testChecksURIsWithNoAnnotation(self):
    uri_element = "<Uri>{}</Uri>"

    uri_one = etree.fromstring(uri_element.format(
        "www.facebook.com/michael_scott"))
    uri_two = etree.fromstring(uri_element.format(
        "www.facebook.com/dwight_shrute"))
    uri_three = etree.fromstring(uri_element.format(
        "www.facebook.com/dwight_shrute"))

    uri_elements = [uri_one, uri_two, uri_three]

    expected_mapping = {
        "": {
            "www.facebook.com/michael_scott": [uri_one],
            "www.facebook.com/dwight_shrute": [uri_two, uri_three],
        },
    }
    uri_validator = rules.UniqueURIPerAnnotationCategory(None, None)
    actual_mapping = uri_validator._extract_uris_by_category(uri_elements)

    self.assertEqual(expected_mapping, actual_mapping)

  # check tests
  def testURIsAreUniqueWithinEachCategory(self):
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

    uri_validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)
    uri_validator.check()

  def testDuplicateURIsOfDifferentAnnotationsAreValid(self):
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

    uri_validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)
    uri_validator.check()

  def testThrowsWarningIfThereAreDuplicatesWithinCategory(self):
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

    uri_validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)
    with self.assertRaises(loggers.ElectionWarning) as ew:
      uri_validator.check()
    self.assertEqual(("The Uris contain the annotation type 'wikipedia' with "
                      "the same value 'https://wikipedia.com/dunder_mifflin'."),
                     ew.exception.log_entry[0].message)
    self.assertLen(ew.exception.log_entry[0].elements, 4)

  def testOfficeURIsAreNotIncludedInCheck(self):
    election_feed = """
      <ElectionReport>
        {}
      </ElectionReport>
    """.format(self._office_collection)
    election_tree = etree.fromstring(election_feed)

    uri_validator = rules.UniqueURIPerAnnotationCategory(election_tree, None)
    uri_validator.check()


class ValidURIAnnotationTest(absltest.TestCase):

  def setUp(self):
    super(ValidURIAnnotationTest, self).setUp()
    self.valid_annotation = rules.ValidURIAnnotation(None, None)

  def testOnlyChecksContactInformationElements(self):
    self.assertEqual(["ContactInformation"], self.valid_annotation.elements())

  def testPlatformOnlyValidAnnotation(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://de.wikipedia.org/]]>
        </Uri>
        <Uri Annotation="ballotpedia">
          <![CDATA[http://ballotpedia.org/George_Washington]]>
        </Uri>
        <Uri Annotation="candidate-image">
          <![CDATA[https://www.parlament.gv.at/test.jpg]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testWikipediaAlternateWritingSystem(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://zh.wikipedia.org/zh-cn/Fake_Page]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testTypePlatformValidAnnotation(self):
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
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testTypePlatformNoAnnotationWarning(self):
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
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     "URI {0} is missing annotation.".format(
                         "https://twitter.com".encode("ascii", "ignore")))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")

  def testNoTypeWhenTypePlatformWarning(self):
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
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Annotation 'website' missing usage type.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")

  def testNoPlatformHasUsageTypeWarning(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Annotation 'campaign' has usage type, missing platform.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")

  def testIncorrectPlatformFails(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("Annotation 'personal-twitter' is incorrect for URI {0}."
                      .format("https://www.youtube.com/SmithForGov"
                              .encode("ascii", "ignore"))))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")

  def testNonExistentPlatformFails(self):
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
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("'campaign-netsite' is not a valid annotation."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")

  def testFBAnnotation(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-facebook">
          <![CDATA[https://www.fb.com/juanjomalvinas]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testIncorrectFBAnnotationFails(self):
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
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("'official-fb' is not a valid annotation."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Uri")


class OfficesHaveJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveJurisdictionIDTest, self).setUp()
    self.offices_validator = rules.OfficesHaveJurisdictionID(None, None)

  def testOfficeHasJurisdictionIDByAdditionalData(self):
    test_string = """
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    self.offices_validator.check(element)

  def testOfficeHasJurisdictionIDByExternalIdentifier(self):
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
    self.offices_validator.check(element)

  def testOfficeDoesNotHaveJurisdictionIDByAdditionalData(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData>ru-gpu4</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeDoesNotHaveJurisdictionIDTextByAdditionalData(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id"></AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeHasMoreThanOneJurisdictionIDbyAdditionalData(self):
    test_string = """
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
            <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office has more than one jurisdiction-id.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off1")

  def testOfficeDoesNotHaveJurisdictionIDByExternalIdentifier(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>ru-gpu3</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeDoesNotHaveJurisdictionIDTextByExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeHasMoreThanOneJurisdictionIDbyExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office has more than one jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off1")

  def testJurisdictionIDTextIsWhitespaceByExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testJurisdictionIDTextIsWhitespaceByAdditionalData(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id">    </AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing a jurisdiction-id.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off2")


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
  def testReturnsASetOfJurisdictionIdsFromGivenTree_AdditionalData(self):
    root_string = self.root_string.format(
        "", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu1", "ru-gpu2"]), reference_values)

  def testReturnsASetOfJurisdictionIdsFromGivenTree_ExternalIdentifier(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2", "ru-gpu3"]), reference_values)

  def testIgnoresExternalIdentifierWithoutType(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testIgnoresExternalIdentifierWithoutOtherTypeNotJurisdictionId(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>district-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testIgnoresExternalIdentifierWithoutValueElement(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testItRemovesDuplicatesIfMulitpleOfficesHaveSameJurisdiction(self):
    root_string = self.root_string.format(
        "", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  # _gather_defined_values test
  def testReturnsASetOfGpUnitsFromGivenTree(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", "", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_defined_values()
    self.assertEqual(set(["ru-gpu1", "ru-gpu2", "ru-gpu3"]), reference_values)

  # check tests
  def testEveryJurisdictionIdReferencesAValidGpUnit(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    rules.ValidJurisdictionID(election_tree, None).check()

  def testRaisesAnElectionErrorIfJurisdictionIdIsNotAGpUnitId(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu99</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    with self.assertRaises(loggers.ElectionError) as ee:
      rules.ValidJurisdictionID(election_tree, None).check()
    self.assertIn("ru-gpu99", ee.exception.log_entry[0].message)


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
    self.offices_validator = rules.OfficesHaveValidOfficeLevel(None, None)

  def testOfficeHasOfficeLevelByExternalIdentifier(self):
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
    self.offices_validator.check(element)

  def testOfficeDoesNotHaveOfficeLevelByExternalIdentifier(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>Region</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing an office-level.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeDoesNotHaveOfficeLevelTextByExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing an office-level.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testOfficeHasMoreThanOneOfficeLevelsbyExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office has more than one office-level.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off1")

  def testOfficeLevelTextIsWhitespaceByExternalIdentifier(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office is missing an office-level.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")

  def testInvalidOfficeLevel(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>invalidvalue</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "Office has invalid office-level invalidvalue.")
    self.assertEqual(
        cm.exception.log_entry[0].elements[0].get("objectId"), "off2")


class OfficesHaveValidOfficeRoleTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveValidOfficeRoleTest, self).setUp()
    self.offices_validator = rules.OfficesHaveValidOfficeRole(None, None)

  def testOfficeHasOfficeRole(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>upper house</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    self.offices_validator.check(element)

  def testOfficeDoesNotHaveOfficeRole(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>Region</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The office is missing an office-role.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off2")

  def testOfficeDoesNotHaveOfficeRoleText(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value></Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The office is missing an office-role.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off2")

  def testOfficeHasMoreThanOneOfficeRoles(self):
    test_string = """
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>upper house</Value>
             </ExternalIdentifier>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>head of state</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The office has more than one office-role.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off1")

  def testOfficeRoleTextIsWhitespace(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The office has invalid office-role ''.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off2")

  def testInvalidOfficeRole(self):
    test_string = """
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-role</OtherType>
               <Value>invalidvalue</Value>
             </ExternalIdentifier>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertEqual(cm.exception.log_entry[0].message,
                     "The office has invalid office-role 'invalidvalue'.")
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "off2")


class GpUnitsHaveSingleRootTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveSingleRootTest, self).setUp()
    self.gpunits_tree_validator = rules.GpUnitsHaveSingleRoot(None, None)

  def testSingleRoot(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru0002</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.gpunits_tree_validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string))
    self.gpunits_tree_validator.check()

  def testMultipleRootTreeFails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("GpUnits tree has more than one root",
                  cm.exception.log_entry[0].message)

  def testNoRootsTreeFails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru0002</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ComposingGpUnitIds>ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("GpUnits have no geo district root.",
                  cm.exception.log_entry[0].message)


class GpUnitsCyclesRefsValidationTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsCyclesRefsValidationTest, self).setUp()
    self.gpunits_tree_validator = rules.GpUnitsCyclesRefsValidation(None, None)

  def testValidationFailsIfCyclesFormed(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("Cycle detected at node",
                  str(cm.exception.log_entry[0].message))

  def testValidationForValidTree(self):
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
    self.gpunits_tree_validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string))
    self.gpunits_tree_validator.check()


class ElectionStartDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionStartDatesTest, self).setUp()
    self.date_validator = rules.ElectionStartDates(None, None)
    self.today = datetime.datetime.now().date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def testChecksElectionElements(self):
    self.assertEqual(["Election"], self.date_validator.elements())

  def testStartDatesAreNotFlaggedIfNotInThePast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    self.date_validator.check(election)

  def testAWarningIsThrownIfStartDateIsInPast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=-1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionWarning):
      self.date_validator.check(election)

  def testIgnoresElectionsWithNoStartDateElement(self):
    election_string = """
      <Election></Election>
    """
    self.date_validator.check(etree.fromstring(election_string))


class ElectionEndDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionEndDatesTest, self).setUp()
    self.date_validator = rules.ElectionEndDates(None, None)
    self.today = datetime.datetime.now().date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def testChecksElectionElements(self):
    self.assertEqual(["Election"], self.date_validator.elements())

  def testEndDatesAreNotFlaggedIfNotInThePast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    self.date_validator.check(election)

  def testAnErrorIsThrownIfEndDateIsInPast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=-2))
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionError):
      self.date_validator.check(election)

  def testAnErrorIsThrownIfEndDateIsBeforeStartDate(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=2),
        self.today + datetime.timedelta(days=1))
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionError):
      self.date_validator.check(election)

  def testThrowsErrorForPastEndDatesWithNoStartDateElement(self):
    election_string = """
      <Election>
        <EndDate>2012-01-01</EndDate>
      </Election>
    """
    with self.assertRaises(loggers.ElectionError):
      self.date_validator.check(etree.fromstring(election_string))

  def testIgnoresElectionsWithNoEndDateElement(self):
    election_string = """
      <Election>
        <StartDate>2012-01-01</StartDate>
      </Election>
    """
    self.date_validator.check(etree.fromstring(election_string))


class OfficeTermDatesTest(absltest.TestCase):

  def setUp(self):
    super(OfficeTermDatesTest, self).setUp()
    self.date_validator = rules.OfficeTermDates(None, None)
    self.office_string = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
          <StartDate>{}</StartDate>
          <EndDate>{}</EndDate>
        </Term>
      </Office>
    """

  def testChecksOfficeElements(self):
    self.assertEqual(["Office"], self.date_validator.elements())

  def testIgnoresOfficesWithNoOfficeHolderPersonIds(self):
    empty_office = """
      <Office>
      </Office>
    """
    self.date_validator.check(etree.fromstring(empty_office))

  def testRaisesWarningForOfficesWithOfficeHolderPersonIdsButNoTerm(self):
    empty_office = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per1</OfficeHolderPersonIds>
      </Office>
    """
    with self.assertRaises(loggers.ElectionWarning) as ew:
      self.date_validator.check(etree.fromstring(empty_office))
    self.assertEqual("The Office is missing a Term.",
                     ew.exception.log_entry[0].message)
    self.assertEqual("off1",
                     ew.exception.log_entry[0].elements[0].get("objectId"))

  def testChecksEndDateIsAfterStartDate(self):
    office_string = self.office_string.format("2020-01-01", "2020-01-02")
    self.date_validator.check(etree.fromstring(office_string))

  def testRaisesErrorIfEndDateIsBeforeStartDate(self):
    office_string = self.office_string.format("2020-01-03", "2020-01-02")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.date_validator.check(etree.fromstring(office_string))
    self.assertIn("The dates (start: 2020-01-03, end: 2020-01-02) are invalid",
                  ee.exception.log_entry[0].message)
    self.assertIn("The end date must be the same or after the start date.",
                  ee.exception.log_entry[0].message)

  def testRaisesWarningIfStartDateNotAssigned(self):
    office_string = """
      <Office objectId="off1">
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
        </Term>
      </Office>
    """
    with self.assertRaises(loggers.ElectionWarning) as ee:
      self.date_validator.check(etree.fromstring(office_string))
    self.assertEqual("The Office is missing a Term > StartDate.",
                     ee.exception.log_entry[0].message)
    self.assertEqual("off1",
                     ee.exception.log_entry[0].elements[0].get("objectId"))

  def testIgnoresIfStartDateAssignedButNotEndDate(self):
    office_string = """
      <Office>
        <OfficeHolderPersonIds>per0</OfficeHolderPersonIds>
        <Term>
          <StartDate>2012-01-01</StartDate>
        </Term>
      </Office>
    """
    self.date_validator.check(etree.fromstring(office_string))


class UniqueStartDatesForOfficeRoleAndJurisdictionTest(absltest.TestCase):

  def setUp(self):
    super(UniqueStartDatesForOfficeRoleAndJurisdictionTest, self).setUp()
    self.date_validator = rules.UniqueStartDatesForOfficeRoleAndJurisdiction(
        None, None)

  _office_string = """
    <Office>
      <Term>
        <StartDate>{info[date]}</StartDate>
      </Term>
      <AdditionalData type="jurisdiction-id">{info[juris]}</AdditionalData>
      <AdditionalData type="office-role">{info[role]}</AdditionalData>
    </Office>
  """

  def testChecksOfficeCollectionElements(self):
    self.assertEqual(["OfficeCollection"], self.date_validator.elements())

  # _filter_out_past_end_dates tests
  def testReturnsAllOfficesWithEndDateNotInPast(self):
    office_string = """
      <Office>
        <Term>
          <EndDate>{}</EndDate>
        </Term>
      </Office>
    """
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    yesterday = today - datetime.timedelta(days=1)

    office_one = etree.fromstring(office_string.format(today))
    office_two = etree.fromstring(office_string.format(tomorrow))
    office_three = etree.fromstring(office_string.format(yesterday))

    offices = [office_one, office_two, office_three]
    expected_valid = [office_one, office_two]
    actual_valid = self.date_validator._filter_out_past_end_dates(offices)
    self.assertEqual(expected_valid, actual_valid)

  def testOfficesWithNoTermAreInvalid(self):
    office_string = """
      <Office>
        <EndDate>{}</EndDate>
      </Office>
    """
    today = datetime.datetime.now().date()

    office_one = etree.fromstring(office_string.format(today))
    offices = [office_one]

    expected_valid = []
    actual_valid = self.date_validator._filter_out_past_end_dates(offices)
    self.assertEqual(expected_valid, actual_valid)

  def testPoorlyFormattedOfficesAreInvalid(self):
    office_string = """
      <Office>
        <Term>
          <EndDate>abcdefghijk</EndDate>
        </Term>
      </Office>
    """

    office_one = etree.fromstring(office_string)
    offices = [office_one]

    expected_valid = []
    actual_valid = self.date_validator._filter_out_past_end_dates(offices)
    self.assertEqual(expected_valid, actual_valid)

  def testOfficesWithNoEndDateAreValid(self):
    office_string = """
      <Office>
        <Term>
          <StartDate>2020-01-01</StartDate>
        </Term>
      </Office>
    """

    office_one = etree.fromstring(office_string)
    offices = [office_one]

    actual_valid = self.date_validator._filter_out_past_end_dates(offices)
    self.assertEqual(offices, actual_valid)

  # _count_start_dates_by_jurisdiction_role tests
  def testReturnsAMapOfJurisdictionIdOfficeRoleStartDateCounts(self):
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
        office_one, office_two, office_three)
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.date_validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 3)

    o1_hash = hashlib.sha256((
        o1_info["role"] + o1_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: set([
                office_collection.findall("Office")[0],
            ]),
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])

    o2_hash = hashlib.sha256((
        o2_info["role"] + o2_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: set([
                office_collection.findall("Office")[1]
            ]),
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])

    o3_hash = hashlib.sha256((
        o3_info["role"] + o3_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o3_mapping = {
        "jurisdiction_id": o3_info["juris"],
        "office_role": o3_info["role"],
        "start_dates": {
            o3_info["date"]: set([
                office_collection.findall("Office")[2]
            ]),
        },
    }
    self.assertIn(o3_hash, mapping.keys())
    self.assertEqual(expected_o3_mapping, mapping[o3_hash])

  def testIgnoresOfficesWithNoStartDateDefined(self):
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
        office_one, office_two, office_three)
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.date_validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 2)

    o1_hash = hashlib.sha256((
        o1_info["role"] + o1_info["juris"]
    ).encode("utf-8")).hexdigest()
    self.assertIn(o1_hash, mapping.keys())

    o2_hash = hashlib.sha256((
        o2_info["role"] + o2_info["juris"]
    ).encode("utf-8")).hexdigest()
    self.assertNotIn(o2_hash, mapping.keys())

    o3_hash = hashlib.sha256((
        o3_info["role"] + o3_info["juris"]
    ).encode("utf-8")).hexdigest()
    self.assertIn(o3_hash, mapping.keys())

  def testUpdatesTheCountForDuplicateJurisdictionRoleDate(self):
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
        office_one, office_two, office_three)
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.date_validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 2)

    o1_hash = hashlib.sha256((
        o1_info["role"] + o1_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: set([
                office_collection.findall("Office")[0],
                office_collection.findall("Office")[2],
            ]),
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])

    o2_hash = hashlib.sha256((
        o2_info["role"] + o2_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: set([
                office_collection.findall("Office")[1],
            ]),
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])

  def testMissingRoleOrJurisdictionCountedAsBlank(self):
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
        office_one, office_two, office_three)
    office_collection = etree.fromstring(office_collection_str)

    mapping = self.date_validator._count_start_dates_by_jurisdiction_role(
        office_collection
    )

    self.assertLen(mapping.keys(), 3)

    o1_hash = hashlib.sha256((
        o1_info["role"] + o1_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o1_mapping = {
        "jurisdiction_id": o1_info["juris"],
        "office_role": o1_info["role"],
        "start_dates": {
            o1_info["date"]: set([
                office_collection.findall("Office")[0]
            ]),
        },
    }
    self.assertIn(o1_hash, mapping.keys())
    self.assertEqual(expected_o1_mapping, mapping[o1_hash])

    o2_hash = hashlib.sha256((
        o2_info["role"] + o2_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o2_mapping = {
        "jurisdiction_id": o2_info["juris"],
        "office_role": o2_info["role"],
        "start_dates": {
            o2_info["date"]: set([
                office_collection.findall("Office")[1]
            ]),
        },
    }
    self.assertIn(o2_hash, mapping.keys())
    self.assertEqual(expected_o2_mapping, mapping[o2_hash])

    o3_hash = hashlib.sha256((
        o3_info["role"] + o3_info["juris"]
    ).encode("utf-8")).hexdigest()
    expected_o3_mapping = {
        "jurisdiction_id": o3_info["juris"],
        "office_role": o3_info["role"],
        "start_dates": {
            o3_info["date"]: set([
                office_collection.findall("Office")[2]
            ]),
        },
    }
    self.assertIn(o3_hash, mapping.keys())
    self.assertEqual(expected_o3_mapping, mapping[o3_hash])

  # check tests
  def testChecksThereAreNoDuplicateStartDatesForJurisdictionAndRole(self):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": set([
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": set([
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
    }

    mock_counts = MagicMock(return_value=start_counts)
    self.date_validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")
    self.date_validator.check(office_coll)

  def testRaisesWarningIfAllStartDatesForJurisdictionAndRoleSame(self):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": set([
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": set([
                    etree.fromstring("<Office></Office>"),
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
    }

    mock_counts = MagicMock(return_value=start_counts)
    self.date_validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")

    with self.assertRaises(loggers.ElectionWarning) as ew:
      self.date_validator.check(office_coll)

    self.assertEqual(("Only one unique StartDate found for each "
                      "jurisdiction-id: ru-gpu2 and office-role: Lower house. "
                      "2020-01-02 appears 2 times."),
                     ew.exception.log_entry[0].message)

  def testAllowsDuplicatesAsLongAsDuplicatedDateIsNotOnlyDate(self):
    start_counts = {
        "abcdefg": {
            "jurisdiction_id": "ru-gpu1",
            "office_role": "Upper house",
            "start_dates": {
                "2020-01-01": set([
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
        "zyxwtuv": {
            "jurisdiction_id": "ru-gpu2",
            "office_role": "Lower house",
            "start_dates": {
                "2020-01-02": set([
                    etree.fromstring("<Office></Office>"),
                    etree.fromstring("<Office></Office>"),
                ]),
                "2020-01-04": set([
                    etree.fromstring("<Office></Office>"),
                ]),
            },
        },
    }

    mock_counts = MagicMock(return_value=start_counts)
    self.date_validator._count_start_dates_by_jurisdiction_role = mock_counts
    office_coll = etree.fromstring("<OfficeCollection></OfficeCollection>")
    self.date_validator.check(office_coll)


class GpUnitsHaveInternationalizedNameTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveInternationalizedNameTest, self).setUp()
    self.gpunits_intl_name_validator = rules.GpUnitsHaveInternationalizedName(
        None, None)

  def testHasExactlyOneInternationalizedNameWithText(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Wisconsin District 7</Text>
      </InternationalizedName>
    </GpUnit>
    """
    self.gpunits_intl_name_validator.check(etree.fromstring(root_string))

  def testHasExactlyOneInternationalizedNameWithMultipleTextElements(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Wisconsin District 7</Text>
        <Text language="ru">Монгольский округ 7</Text>
      </InternationalizedName>
    </GpUnit>
    """
    self.gpunits_intl_name_validator.check(etree.fromstring(root_string))

  def testNoInternationalizedNameElement(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit is required to have exactly one "
                      "InterationalizedName element."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "ru0002")

  def testInternationalizedNameElementNoSubelements(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName/>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit InternationalizedName is required to have one or "
                      "more Text elements."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag,
                     "InternationalizedName")

  def testInternationalizedNameNoText(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en"></Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit InternationalizedName does not have a text "
                      "value."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Text")

  def testInternationalizedNameTextValueIsWhitespace(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">                 </Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit InternationalizedName does not have a text "
                      "value."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Text")

  def testOneTextElementDoesNotHaveValue(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName>
        <Text language="en">Russia</Text>
        <Text language="ru"></Text>
      </InternationalizedName>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit InternationalizedName does not have a text "
                      "value."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].tag, "Text")

  def testMoreThanOneInternationalizedNameFails(self):
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
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertEqual(cm.exception.log_entry[0].message,
                     ("GpUnit is required to have exactly one "
                      "InterationalizedName element."))
    self.assertEqual(cm.exception.log_entry[0].elements[0].get("objectId"),
                     "ru0002")


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

  def testNoAdditionalDataElementsReturnsAnEmptyList(self):
    root = etree.fromstring(self.root_string.format("", ""))
    elements = rules.get_additional_type_values(
        root, "jurisdiction-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testNoAdditionalDataValuesReturnsAnEmptyList(self):
    add_data = """
        <AdditionalData type="jurisdiction-id"></AdditionalData>
    """

    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")
    self.assertEmpty(elements, 0)

  def testAdditionalDataWhitespaceValueReturnsAnEmptyList(self):
    add_data = """
        <AdditionalData type="jurisdiction-id">      </AdditionalData>
    """

    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")
    self.assertEmpty(elements, 0)

  def testAdditionalDataWithNoTypeReturnsAnEmptyList(self):
    add_data = """
        <AdditionalData>ru-gpu2</AdditionalData>
    """
    root = etree.fromstring(self.root_string.format(add_data, ""))
    elements = rules.get_additional_type_values(root, "jurisdiction-id")
    self.assertEmpty(elements, 0)

  def testAdditionalDataReturnsElementsList(self):
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
        root, "jurisdiction-id", return_elements=True)
    self.assertLen(elements, 2)
    for el in elements:
      self.assertNotIsInstance(el, str)

  def testAdditionalDataReturnsValuesList(self):
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

  def testEmptyValueTypeAndNoExternalIdsReturnsEmptyList(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "")
    self.assertEmpty(elements, 0)

  def testNoExternalIdsReturnsEmptyList(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "ocd-id")
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenNoTypeElement(self):
    missing_type = """
    <ExternalIdentifier>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_type))
    elements = rules.get_external_id_values(root, "ocd-id")
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenTypeElementMissingText(self):
    missing_text = """
    <ExternalIdentifier>
      <Type></Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenTypeElementTextIsWhitespace(self):
    missing_text = """
    <ExternalIdentifier>
      <Type>                   </Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenTypeElementValueIsMissing(self):
    missing_text = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value></Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(root, "ocd-id")
    self.assertEmpty(elements, 0)

  def testEmptyValueTypeAndNoExternalIdsReturnsEmptyElementsList(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(root, "", return_elements=True)
    self.assertEmpty(elements, 0)

  def testNoExternalIdsReturnsEmptyElementsList(self):
    root = etree.fromstring(self.gpunit.format(""))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testReturnsEmptyElementsListWhenNoTypeElement(self):
    missing_type = """
    <ExternalIdentifier>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_type))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testReturnsEmptyElementsListWhenTypeElementMissingText(self):
    missing_text = """
    <ExternalIdentifier>
      <Type></Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testReturnsEmptyElementsListWhenTypeElementTextIsWhitespace(self):
    missing_text = """
    <ExternalIdentifier>
      <Type>                   </Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testReturnsEmptyElementsListWhenTypeElementValueIsMissing(self):
    missing_text = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value></Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_text))
    elements = rules.get_external_id_values(
        root, "ocd-id", return_elements=True)
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenOtherTypeElementMissing(self):
    missing_element = """
    <ExternalIdentifier>
      <Type>other</Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    root = etree.fromstring(self.gpunit.format(missing_element))
    elements = rules.get_external_id_values(root, "something-else")
    self.assertEmpty(elements, 0)

  def testReturnsEmptyListWhenOtherTypeElementMissingText(self):
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

  def testReturnsEmptyListWhenOtherTypeElementTextIsWhitespace(self):
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

  def testEnumeratedTypeAsOtherTypeReturnsEmptyList(self):
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

  def testReturnsNonEmptyListWhenTypeElementValueIsWhitespace(self):
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

  def testReturnsNonEmptyListWhenOtherTypeElementValueIsWhitespace(self):
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

  def testReturnsAllValidEnumeratedTypeElements(self):
    type_string = self.get_type_string()
    for en_type in rules._IDENTIFIER_TYPES:
      full_string = self.gpunit.format(type_string.format(en_type, en_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(
          root, en_type, return_elements=True)
      self.assertLen(elements, 2)
      for el in elements:
        self.assertNotIsInstance(el, str)

  def testReturnsAllValidEnumeratedTypeElementValues(self):
    type_string = self.get_type_string()
    test_values = {
        "ocd-division/country:us/state:va", "ocd-division/country:us/state:ma"
    }
    for en_type in rules._IDENTIFIER_TYPES:
      full_string = self.gpunit.format(type_string.format(en_type, en_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(root, en_type)
      self.assertLen(elements, 2)
      for el in elements:
        self.assertIsInstance(el, str)
        self.assertIn(el, test_values)

  def testReturnsOtherTypeElements(self):
    test_values, other_type_str = self.get_other_type_strings()
    for other_type in test_values:
      full_string = self.gpunit.format(
          other_type_str.format(other_type, other_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(
          root, other_type, return_elements=True)
      self.assertLen(elements, 2)
      for el in elements:
        self.assertNotIsInstance(el, str)

  def testReturnsOtherTypeElementValues(self):
    test_values, other_type_str = self.get_other_type_strings()
    for other_type in test_values:
      full_string = self.gpunit.format(
          other_type_str.format(other_type, other_type))
      root = etree.fromstring(full_string)
      elements = rules.get_external_id_values(root, other_type)
      self.assertLen(elements, 2)
      for el in elements:
        self.assertIsInstance(el, str)
        self.assertIn(el, test_values)


class FullTextMaxLengthTest(absltest.TestCase):

  def setUp(self):
    super(FullTextMaxLengthTest, self).setUp()
    self.length_validator = rules.FullTextMaxLength(None, None)

  def testMakesSureFullTextIsBelowLimit(self):
    contest_string = """
        <FullText>
          <Text language="en">Short full text of a ballot measure</Text>
          <Text language="it">Breve testo completo di un referendum</Text>
        </FullText>
    """
    element = etree.fromstring(contest_string)

    self.length_validator.check(element)

  def testIgnoresFullTextWithNoTextStrings(self):
    contest_string_no_full_text = """
      <FullText>
      </FullText>
    """
    element = etree.fromstring(contest_string_no_full_text)

    self.length_validator.check(element)

  def testRaisesWarningIfTextIsTooLong(self):
    contest_string = """
      <FullText>
        <Text language="en">Long text continues...{}</Text>
      </FullText>
        """.format("x" * 30000)

    with self.assertRaises(loggers.ElectionWarning):
      self.length_validator.check(etree.fromstring(contest_string))

  def testRaisesWarningIfAnyTextIsTooLong(self):
    contest_string = """
      <FullText>
        <Text language="en">Short full text of a ballot measure</Text>
        <Text language="es">Long text continues...{}</Text>
      </FullText>
        """.format("x" * 30000)

    with self.assertRaises(loggers.ElectionWarning):
      self.length_validator.check(etree.fromstring(contest_string))


class FullTextOrBallotTextTest(absltest.TestCase):

  def setUp(self):
    super(FullTextOrBallotTextTest, self).setUp()
    self.text_validator = rules.FullTextOrBallotText(None, None)

  def testBallotTextWithLongFullText(self):
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
    self.text_validator.check(etree.fromstring(contest_string))

  def testBallotTextWithShortFullText(self):
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
    self.text_validator.check(etree.fromstring(contest_string))

  def testBallotTextWithNoFullText(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the measure be enacted?</Text>
          </BallotText>
        </BallotMeasureContest>
    """
    self.text_validator.check(etree.fromstring(contest_string))

  def testMissingBallotTextElementWithShortFullText(self):
    contest_string = """
        <BallotMeasureContest>
          <FullText>
            <Text language="en">Should the measure be enacted?</Text>
          </FullText>
        </BallotMeasureContest>
    """
    with self.assertRaises(loggers.ElectionWarning):
      self.text_validator.check(etree.fromstring(contest_string))

  def testLanguageMismatchWithShortFullText(self):
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
      self.text_validator.check(etree.fromstring(contest_string))

  def testLanguageMismatchWithLongFullText(self):
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
    self.text_validator.check(etree.fromstring(contest_string))

  def testMissingBallotTextWithShortFullText(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText></BallotText>
          <FullText>
            <Text language="en">Should the measure be enacted?</Text>
          </FullText>
        </BallotMeasureContest>
    """
    with self.assertRaises(loggers.ElectionWarning):
      self.text_validator.check(etree.fromstring(contest_string))

  def testMissingBallotTextElementWithLongFullText(self):
    contest_string = """
        <BallotMeasureContest>
          <FullText>
            <Text language="en">Long ballot text continues... {}</Text>
          </FullText>
        </BallotMeasureContest>
    """.format("x" * 2500)
    self.text_validator.check(etree.fromstring(contest_string))

  def testMissingBallotTextAndFullMeasureTextElements(self):
    contest_string = """
        <BallotMeasureContest>
        </BallotMeasureContest>
    """
    self.text_validator.check(etree.fromstring(contest_string))


class BallotTitleTest(absltest.TestCase):

  def setUp(self):
    super(BallotTitleTest, self).setUp()
    self.text_validator = rules.BallotTitle(None, None)

  def testBallotTitleShorterThanBallotText(self):
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
    self.text_validator.check(etree.fromstring(contest_string))

  def testLanguageMismatch(self):
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
      self.text_validator.check(etree.fromstring(contest_string))

  def testExtraBallotTextLanguage(self):
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
    self.text_validator.check(etree.fromstring(contest_string))

  def testExtraBallotTitleLanguage(self):
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
      self.text_validator.check(etree.fromstring(contest_string))

  def testBallotTitleIncludesBallotText(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotTitle>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotTitle>
        </BallotMeasureContest>
    """
    with self.assertRaises(loggers.ElectionWarning):
      self.text_validator.check(etree.fromstring(contest_string))

  def testMissingBallotTitle(self):
    contest_string = """
        <BallotMeasureContest>
          <BallotText>
            <Text language="en">Should the state constitution be ammended to establish a minimum wage of $12/hour by 2030?</Text>
          </BallotText>
        </BallotMeasureContest>
    """
    with self.assertRaises(loggers.ElectionError):
      self.text_validator.check(etree.fromstring(contest_string))


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
  def testReturnsListOfCandidateIdsInGiventContest(self):
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
    contest_validator = rules.ImproperCandidateContest(None, None)

    expected_ids = ["can123", "can987", "can456"]
    actual_ids = contest_validator._gather_contest_candidates(contest_elem)

    self.assertEqual(expected_ids, actual_ids)

  # _gather_invalid_candidates test
  def testReturnsCandidateIdsThatAppearToBeBallotSelections(self):
    candidate_election = self._base_report.format(
        "Yes", "Larry David")
    root = etree.fromstring(candidate_election)
    contest_validator = rules.ImproperCandidateContest(root, None)

    expected_cand = ["can123"]
    actual_cand = contest_validator._gather_invalid_candidates()

    self.assertEqual(expected_cand, actual_cand)

  # check tests
  def testCandidatesDontHaveTypicalBallotSelectionOptionsAsName(self):
    candidate_election = self._base_report.format(
        "Jerry Seinfeld", "Larry David")
    root = etree.fromstring(candidate_election)
    contest_validator = rules.ImproperCandidateContest(root, None)

    contest_validator.check()

  def testCandidatesWithBallotSelectionsOptionsGetFlagged(self):
    candidate_election = self._base_report.format(
        "Yes", "No")
    root = etree.fromstring(candidate_election)
    contest_validator = rules.ImproperCandidateContest(root, None)

    with self.assertRaises(loggers.ElectionWarning) as ew:
      contest_validator.check()

    self.assertEqual(("Candidates can123, can456 should be "
                      "BallotMeasureSelection elements. Similarly, Contest "
                      "con987 should be changed to a BallotMeasureContest "
                      "instead of a CandidateContest."),
                     ew.exception.log_entry[0].message)


class MissingFieldsErrorTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsErrorTest, self).setUp()
    self.field_validator = rules.MissingFieldsError(None, None)
    self.field_validator.setup()

  def testSetsSeverityLevelToError(self):
    self.assertEqual(2, self.field_validator.get_severity())

  def testRequiredFieldIsPresent_Person(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text>Chris Rock</Text>
        </FullName>
      </Person>
    """
    self.field_validator.check(etree.fromstring(person))

  def testRaisesErrorForMissingField_Person(self):
    person = """
      <Person objectId="123">
      </Person>
    """

    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(person))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ee.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testRequiredFieldIsPresent_Candidate(self):
    candidate = """
      <Candidate objectId="123">
        <PersonId>per1</PersonId>
      </Candidate>
    """
    self.field_validator.check(etree.fromstring(candidate))

  def testRaisesErrorForMissingField_Candidate(self):
    candidate = """
      <Candidate objectId="123">
        <PersonId></PersonId>
      </Candidate>
    """

    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(candidate))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Candidate is missing field PersonId.")
    self.assertEqual(
        ee.exception.log_entry[0].elements[0].get("objectId"), "123")

  def testRequiredFieldIsPresent_Election(self):
    election = """
      <Election objectId="123">
        <StartDate>2020-01-01</StartDate>
        <EndDate>2020-01-01</EndDate>
      </Election>
    """
    self.field_validator.check(etree.fromstring(election))

  def testRaisesErrorForMissingField_Election(self):
    election = """
      <Election objectId="123">
      </Election>
    """

    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(election))

    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Election is missing field StartDate.")
    self.assertEqual(
        ee.exception.log_entry[0].elements[0].get("objectId"), "123")
    self.assertEqual(ee.exception.log_entry[1].message,
                     "The element Election is missing field EndDate.")
    self.assertEqual(
        ee.exception.log_entry[1].elements[0].get("objectId"), "123")


class MissingFieldsWarningTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsWarningTest, self).setUp()
    self.field_validator = rules.MissingFieldsWarning(None, None)
    self.field_validator.setup()

  def testSetsSeverityLevelToWarning(self):
    self.assertEqual(1, self.field_validator.get_severity())

  def testRequiredFieldIsPresent_Candidate(self):
    candidate = """
      <Candidate objectId="123">
        <PartyId>par1</PartyId>
      </Candidate>
    """
    self.field_validator.check(etree.fromstring(candidate))

  def testRaisesWarningForMissingField_Candidate(self):
    candidate = """
      <Candidate objectId="123">
      </Candidate>
    """

    with self.assertRaises(loggers.ElectionWarning) as ew:
      self.field_validator.check(etree.fromstring(candidate))

    self.assertEqual(ew.exception.log_entry[0].message,
                     "The element Candidate is missing field PartyId.")
    self.assertEqual(
        ew.exception.log_entry[0].elements[0].get("objectId"), "123")


class MissingFieldsInfoTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldsInfoTest, self).setUp()
    self.field_validator = rules.MissingFieldsInfo(None, None)
    self.field_validator.setup()

  def testSetsSeverityLevelToWarning(self):
    self.assertEqual(0, self.field_validator.get_severity())

  def testRequiredFieldIsPresent_Candidate(self):
    office = """
      <Office objectId="123">
        <ElectoralDistrictId>ru_2343</ElectoralDistrictId>
      </Office>
    """
    self.field_validator.check(etree.fromstring(office))

  def testRaisesInfoForMissingField_Candidate(self):
    office = """
      <Office objectId="123">
      </Office>
    """

    with self.assertRaises(loggers.ElectionInfo) as ew:
      self.field_validator.check(etree.fromstring(office))

    self.assertEqual(ew.exception.log_entry[0].message,
                     "The element Office is missing field ElectoralDistrictId.")
    self.assertEqual(
        ew.exception.log_entry[0].elements[0].get("objectId"), "123")


class PartySpanMultipleCountriesTest(absltest.TestCase):

  def setUp(self):
    super(PartySpanMultipleCountriesTest, self).setUp()
    self.gp_unit_validator = rules.DuplicateGpUnits(None, None)
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

  def testGpUnitList(self):
    referenced_gpunits = "ru0001 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    expected_map = {
        "ru0001": "country:us",
        "ru0002": "country:us",
        "ru0003": "country:fr",
    }
    self.assertEqual(party_validator.existing_gpunits, expected_map)

  def testNoWarningIfSameCountry(self):
    referenced_gpunits = "ru0001 ru0002"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds")
    party_validator.check(element)

  def testNoWarningIfGpUnitWithoutCountry(self):
    referenced_gpunits = "ru0001 ru0004"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds")
    party_validator.check(element)

  def testNoWarningIfOneGpUnit(self):
    referenced_gpunits = "ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds")
    party_validator.check(element)

  def testThrowWarningIfMultipleCountriesAreReferenced(self):
    referenced_gpunits = "ru0001 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds")
    with self.assertRaises(loggers.ElectionWarning) as ee:
      party_validator.check(element)
    self.assertIn("ru0001", ee.exception.log_entry[0].message)
    self.assertIn("ru0003", ee.exception.log_entry[0].message)

  def testThrowWarningIfMultipleCountriesAreReferencedWithComposition(self):
    referenced_gpunits = "ru0002 ru0003"
    election_string = self.base_report.format(referenced_gpunits)
    election_tree = etree.fromstring(election_string)
    party_validator = rules.PartySpanMultipleCountries(election_tree, None)
    element = election_tree.find(
        "Election//PartyCollection//Party//PartyScopeGpUnitIds")
    with self.assertRaises(loggers.ElectionWarning) as ee:
      party_validator.check(element)
    self.assertIn("ru0002", ee.exception.log_entry[0].message)
    self.assertIn("ru0003", ee.exception.log_entry[0].message)


class OfficeMissingGovernmentBodyTest(absltest.TestCase):

  def setUp(self):
    super(OfficeMissingGovernmentBodyTest, self).setUp()
    self.gov_validator = rules.OfficeMissingGovernmentBody(None, None)

  def testChecksOfficeElements(self):
    self.assertEqual(["Office"], self.gov_validator.elements())

  # test exempt office list to ensure a double check if/when list is changed
  def testExemptOfficesList(self):
    expected_exempt_offices = [
        "head of state", "head of government", "president", "vice president",
        "state executive", "deputy state executive",
    ]
    self.assertEqual(
        expected_exempt_offices, self.gov_validator._EXEMPT_OFFICES)

  def testIgnoresExemptOffices(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>{}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Office>
    """

    exempt_office = etree.fromstring(office_string.format("head of state"))
    self.gov_validator.check(exempt_office)

    non_exempt_office = etree.fromstring(office_string.format("senate"))
    with self.assertRaises(loggers.ElectionInfo):
      self.gov_validator.check(non_exempt_office)

  def testOfficeElementHasGovernmentBodyDefined(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>senate</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>{}</OtherType>
            <Value>United States Senate</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Office>
    """

    government_body_office = etree.fromstring(
        office_string.format("government-body"))
    self.gov_validator.check(government_body_office)

    governmental_body_office = etree.fromstring(
        office_string.format("governmental-body"))
    self.gov_validator.check(governmental_body_office)

  def testRaisesInfoIfNoGovernmentBodyDefined(self):
    office_string = """
      <Office>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>office-role</OtherType>
            <Value>senate</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>{}</OtherType>
            <Value>United States Senate</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Office>
    """

    government_body_office = etree.fromstring(
        office_string.format("body"))
    with self.assertRaises(loggers.ElectionInfo) as ei:
      self.gov_validator.check(government_body_office)
    self.assertEqual("Office element is missing an external identifier of "
                     "other-type government-body.",
                     str(ei.exception.log_entry[0].message))


class SubsequentContestIdTest(absltest.TestCase):

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

  def testValidSubsequentContest(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    subsequent_validator.check(election_tree)

  def testSubsequentContestWithMismatchedOfficeIds(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office2</OfficeIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      subsequent_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with a different "
        "office id", str(ee.exception.log_entry[0].message))

  def testSubsequentContestWithMismatchedPrimaryPartyIds(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      subsequent_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with different primary "
        "party ids", str(ee.exception.log_entry[0].message))

  def testSubsequentContestWithNoPrimaryPartyIds(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office1</OfficeIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    subsequent_validator.check(election_tree)

  def testSubsequentContestWithEarlierEndDate(self):
    root_string = self._base_election_report.format("cc_001", "")

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      subsequent_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 references a subsequent contest with an earlier end "
        "date.", str(ee.exception.log_entry[0].message))

  def testSubsequentContestContainsOriginalInComposingContestIds(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <ComposingContestIds>cc_123</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format("cc_456", contest_string)

    election_tree = etree.fromstring(root_string)
    subsequent_validator = rules.SubsequentContestIdIsValidRelatedContest(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      subsequent_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 is listed as a composing contest for its subsequent "
        "contest.  Two contests can be linked by SubsequentContestId or "
        "ComposingContestId, but not both.",
        str(ee.exception.log_entry[0].message))


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

  def testValidComposingContests(self):
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
    root_string = self._base_election_report.format(contest_string,
                                                    "cc_456 cc_789")

    election_tree = etree.fromstring(root_string)
    composing_validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None)

    composing_validator.check(election_tree)

  def testComposingContestAppearsMultipleTimes(self):
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
    composing_validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      composing_validator.check(election_tree)
    self.assertIn(
        "Contest cc_456 is listed as a ComposingContest for more than one "
        "parent contest.  ComposingContests should be a strict hierarchy",
        str(ee.exception.log_entry[0].message))

  def testComposingContestWithMismatchedOfficeIds(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <OfficeIds>office2</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")

    election_tree = etree.fromstring(root_string)
    composing_validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      composing_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 and composing contest cc_456 have different office ids",
        str(ee.exception.log_entry[0].message))

  def testComposingContestWithMismatchedPrimaryPartyIds(self):
    contest_string = """
          <Contest objectId="cc_456">
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party2</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")

    election_tree = etree.fromstring(root_string)
    composing_validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      composing_validator.check(election_tree)
    self.assertIn(
        "Contest cc_123 and composing contest cc_456 have different primary "
        "party ids", str(ee.exception.log_entry[0].message))

  def testComposingContestsReferenceEachOther(self):
    contest_string = """
          <Contest objectId="cc_456" xsi:type="CandidateContest">
            <ComposingContestIds>cc_123</ComposingContestIds>
            <OfficeIds>office1</OfficeIds>
            <PrimaryPartyIds>party1</PrimaryPartyIds>
          </Contest>
          """
    root_string = self._base_election_report.format(contest_string, "cc_456")

    election_tree = etree.fromstring(root_string)
    composing_validator = rules.ComposingContestIdsAreValidRelatedContests(
        election_tree, None)

    with self.assertRaises(loggers.ElectionError) as ee:
      composing_validator.check(election_tree)
    self.assertIn(
        "Contest cc_456 and contest cc_123 reference each other as composing "
        "contests", str(ee.exception.log_entry[0].message))


class RulesTest(absltest.TestCase):

  def testAllRulesIncluded(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    possible_rules.remove(base.MissingFieldRule)
    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()

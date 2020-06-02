# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import inspect
import io

from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
import github
from lxml import etree
from mock import MagicMock
from mock import mock_open
from mock import patch


class HelpersTest(absltest.TestCase):

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
    self.assertIn("schema file could not be parsed correctly",
                  str(ee.exception))

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

    with self.assertRaises(loggers.ElectionTreeError) as ete:
      schema_validator.check()
    self.assertIn("election file didn't validate against schema",
                  str(ete.exception))


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
    self.assertEqual(str(ee.exception), "'Encoding on file is not UTF-8'")


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


class OnlyOneElectionTest(absltest.TestCase):

  def setUp(self):
    super(OnlyOneElectionTest, self).setUp()
    self.election_count_validator = rules.OnlyOneElection(None, None)

  def testOnlyChecksElectionReportElements(self):
    self.assertEqual(["ElectionReport"],
                     self.election_count_validator.elements())

  def testShouldHaveExactlyOneElection(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
    </ElectionReport>
    """

    self.election_count_validator.check(etree.fromstring(root_string))

  def testThrowsErrorForMoreThanOneElection(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
      <Election></Election>
    </ElectionReport>
    """

    with self.assertRaises(loggers.ElectionError):
      self.election_count_validator.check(etree.fromstring(root_string))


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
    with self.assertRaises(loggers.ElectionTreeError):
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
    self.assertEqual(
        "'There are 1 invalid IDREF elements present.'", str(ee.exception)
    )
    self.assertIn(
        ("gp004 is not a valid IDREF. ElectoralDistrictId should contain an "
         "objectId from a GpUnit element."), ee.exception.error_log[0].message
    )

    with self.assertRaises(loggers.ElectionError) as ee:
      id_ref_validator.check(idrefs_element)
    self.assertEqual(
        "'There are 2 invalid IDREF elements present.'", str(ee.exception)
    )
    self.assertIn(
        ("per004 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.error_log[0].message
    )
    self.assertIn(
        ("per005 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.error_log[1].message
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
    self.assertEqual(
        "'There are 2 invalid IDREF elements present.'", str(ee.exception)
    )
    self.assertIn(
        ("per004 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.error_log[0].message
    )
    self.assertIn(
        ("per005 is not a valid IDREF. OfficeHolderPersonIds should contain an "
         "objectId from a Person element."), ee.exception.error_log[1].message
    )


class ElectoralDistrictOcdIdTest(absltest.TestCase):

  def setUp(self):
    super(ElectoralDistrictOcdIdTest, self).setUp()
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
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    open_mod = inspect.getmodule(open)
    if "__builtins__" not in open_mod.__dict__.keys():
      # '__builtin__' for python2
      self.builtins_name = open_mod.__name__
    else:
      # 'builtins' for python3
      self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = mock_open(read_data=downloaded_ocdid_file)

  def testSetsDefaultValuesUponCreation(self):
    self.assertTrue(self.ocdid_validator.check_github)
    self.assertIsNone(self.ocdid_validator.country_code)
    self.assertIsNone(self.ocdid_validator.github_file)
    self.assertIsNone(self.ocdid_validator.github_repo)
    self.assertIsNone(self.ocdid_validator.local_file)
    self.assertLen(self.ocdid_validator.gpunits, 3)

  # setup tests
  def testSetOCDsToResultOfGetOcdData(self):
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_validator._get_ocd_data = mock
    self.ocdid_validator.local_file = "://file/path"
    self.ocdid_validator.setup()

    self.assertEqual(None, self.ocdid_validator.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, self.ocdid_validator.ocds)

  def testSetsGithubFileIfNoLocalFile(self):
    self.ocdid_validator.country_code = "us"
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_validator._get_ocd_data = mock
    self.ocdid_validator.setup()

    self.assertEqual("country-us.csv", self.ocdid_validator.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, self.ocdid_validator.ocds)

  # _get_latest_commit_date tests
  def testReturnsTheLatestCommitDateForTheCountryCSV(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator.github_repo = github.Repository.Repository(
        None, [], [], None)

    now = datetime.datetime.now()
    formatted_commit_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = github.Commit.Commit(
        None, {},
        dict({
            "commit": dict({"committer": dict({"date": formatted_commit_date})})
        }), None)

    mock_get_commits = MagicMock(return_value=[commit])
    self.ocdid_validator.github_repo.get_commits = mock_get_commits

    latest_commit_date = self.ocdid_validator._get_latest_commit_date()
    self.assertEqual(now.replace(microsecond=0), latest_commit_date)
    mock_get_commits.assert_called_with(path="identifiers/country-ar.csv")

  # _download_data tests
  def testItCopiesDownloadedDataToCacheFileWhenValid(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator._verify_data = MagicMock(return_value=True)
    mock_request = MagicMock()
    mock_io_open = MagicMock()
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", mock_request), \
         patch("io.open", mock_io_open), \
         patch("shutil.copy", mock_copy):
      self.ocdid_validator._download_data("/usr/cache")

    request_url = "https://raw.github.com/{0}/master/{1}/country-ar.csv".format(
        self.ocdid_validator.GITHUB_REPO, self.ocdid_validator.GITHUB_DIR)
    mock_request.assert_called_with(request_url)
    mock_io_open.assert_called_with("/usr/cache.tmp", "wb")
    mock_copy.assert_called_with("/usr/cache.tmp", "/usr/cache")

  def testItRaisesAnErrorAndDoesNotCopyDataWhenTheDataIsInvalid(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator._verify_data = MagicMock(return_value=False)
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", MagicMock()), \
         patch("io.open", MagicMock()), \
         patch("shutil.copy", mock_copy), \
         self.assertRaises(loggers.ElectionError):
      self.ocdid_validator._download_data("/usr/cache")

    self.assertEqual(0, mock_copy.call_count)

  # _get_latest_file_blob_sha tests
  def testItReturnsTheBlobShaOfTheGithubFileWhenFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({
            "name": "country-ar.csv",
            "sha": "abc123"
        }), None)
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_contents = MagicMock(return_value=[content_file])
    self.ocdid_validator.github_repo = repo
    self.ocdid_validator.github_file = "country-ar.csv"

    blob_sha = self.ocdid_validator._get_latest_file_blob_sha()
    self.assertEqual("abc123", blob_sha)

  def testItReturnsNoneIfTheFileCantBeFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({
            "name": "country-ar.csv",
            "sha": "abc123"
        }), None)
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_contents = MagicMock(return_value=[content_file])
    self.ocdid_validator.github_repo = repo
    self.ocdid_validator.github_file = "country-us.csv"

    blob_sha = self.ocdid_validator._get_latest_file_blob_sha()
    self.assertIsNone(blob_sha)

  # _encode_ocdid_value tests
  def testItReturnsTheProvidedValueIfTypeString(self):
    ocdid = str("my-cool-ocdid")
    result = self.ocdid_validator._encode_ocdid_value(ocdid)
    self.assertEqual("my-cool-ocdid", result)

  def testItReturnsEncodedValueIfTypeUnicode(self):
    ocdid = u"regionalwahlkreis:burgenland_süd"
    result = self.ocdid_validator._encode_ocdid_value(ocdid)

    encoded = "regionalwahlkreis:burgenland_süd"
    self.assertEqual(encoded, result)

  def testItReturnsEmptyStringIfOtherType(self):
    ocdid = 1
    result = self.ocdid_validator._encode_ocdid_value(ocdid)
    self.assertEqual("", result)

  # elements test
  def testItOnlyChecksElectoralDistrictIdElements(self):
    self.assertEqual(["ElectoralDistrictId"], self.ocdid_validator.elements())

  # check tests
  def testThatGivenElectoralDistrictIdReferencesGpUnitWithValidOCDID(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

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
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testIgnoresElementsWhoDontHaveContestParent(self):
    parent_string = """
      <Party><ElectoralDistrictId/></Party>
    """
    element = etree.fromstring(parent_string)

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testIgnoresElementsWhoseParentHasNoObjectId(self):
    parent_string = """
      <Contest><ElectoralDistrictId/></Contest>
    """
    element = etree.fromstring(parent_string)

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testItRaisesAnErrorIfTheOcdidLabelIsNotAllLowerCase(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

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
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(loggers.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("does not have an ocd-id", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedGpUnitDoesNotExist(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru9999</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

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
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(loggers.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("con123 does not refer to a GpUnit", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedGpUnitHasNoOCDID(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(loggers.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("does not have an ocd-id", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedOcdidIsNotValid(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

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
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(loggers.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(ee.exception))

  def testUnicodeOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testCountryOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:la"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testLongOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:us/state:la"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testUnicodeOCDIDsAreValid_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:kärnten_west"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)

    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(
        ["ocd-division/country:la"
         "/regionalwahlkreis:burgenland_süd"])
    with self.assertRaises(loggers.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidUnicodeOCDIDs_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd/"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    with self.assertRaises(loggers.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidNonUnicodeOCDIDs_fails(self):
    ocd_value = "regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(["regionalwahlkreis:karnten_west"])
    with self.assertRaises(loggers.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidNonUnicodeOCDIDsWithAnInvalidCharacter_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland*d"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    with self.assertRaises(loggers.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testNonUnicodeOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:to/regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testNonUnicodeOCDIDsAreValid_fails(self):
    ocd_value = "ocd-division/country:to/regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(
        ["ocd-division/country:to"
         "/regionalwahlkreis:karnten_west"])
    with self.assertRaises(loggers.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))


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

    open_mod = inspect.getmodule(open)
    if "__builtins__" not in open_mod.__dict__.keys():
      # '__builtin__' for python2
      self.builtins_name = open_mod.__name__
    else:
      # 'builtins' for python3
      self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = mock_open(read_data=downloaded_ocdid_file)

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

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
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

    self.gp_unit_validator.ocds = set(["ocd-division/country:us"])
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithNoOcdIdValue(self):
    reporting_unit = self.base_reporting_unit.format("", "county")
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItRaisesAWarningIfOcdIdNotInListOfValidIds(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ny/county:nassau</Value>",
        "county",
    )
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
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
    self.assertIn("GpUnits ('ru0002', 'ru0004') are duplicates",
                  str(cm.exception))

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
    self.assertIn("GpUnit with object_id ru0002 is duplicated",
                  str(cm.exception))

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
    self.assertIn("GpUnit with object_id ru0002 is duplicated",
                  str(cm.exception))
    self.assertIn("GpUnits ('ru0002', 'ru0004') are duplicates",
                  str(cm.exception))


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
    <ElectionReport>
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  def testSetsElectionTypeOnCreation_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual("primary", prim_part_validator.election_type)

  def testSetsElectionTypeOnCreation_None(self):
    election_string = """
      <ElectionReport/>
    """
    election_tree = etree.fromstring(election_string)
    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertIsNone(prim_part_validator.election_type)

  def testSetsElectionTypeOnCreation_NoType(self):
    election_details = """
      <Name>
        <Text language="en">2020 New York City Mayor</Text>
      </Name>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertIsNone(prim_part_validator.election_type)

  # elements tests
  def testOnlyChecksCandidateContestsForSpecificElections_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_Open(self):
    election_details = "<Type>partisan-primary-open</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_Closed(self):
    election_details = "<Type>partisan-primary-closed</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_General(self):
    election_details = "<Type>general</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual([], prim_part_validator.elements())

  # check tests
  def testPartyIdsArePresentAndNonEmpty(self):
    election_details = """
      <CandidateContest>
        <PrimaryPartyIds>abc123</PrimaryPartyIds>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_NoParty(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_EmptyParty(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <PrimaryPartyIds></PrimaryPartyIds>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_WhiteSpace(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <PrimaryPartyIds>      </PrimaryPartyIds>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)


class PartisanPrimaryHeuristicTest(absltest.TestCase):

  _base_election_report = """
    <ElectionReport>
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  _general_candidate_contest = """
    <Type>general</Type>
    <CandidateContest>
      {}
    </CandidateContest>
  """

  _base_candidate_contest = _base_election_report.format(
      _general_candidate_contest)

  def testChecksNonPrimaryCandidateContests_NoType(self):
    election_details = "<Name>2020 election</Name>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testChecksNonPrimaryCandidateContests_General(self):
    election_details = "<Type>general</Type>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testChecksNonPrimaryCandidateContests_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual([], prim_part_validator.elements())

  def testIgnoresContestsThatDoNotSuggestPrimary_NoName(self):
    contest_details = "<PrimaryPartyIds>abc123</PrimaryPartyIds>"
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    no_name_contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(no_name_contest)

  def testIgnoresContestsThatDoNotSuggestPrimary_EmptyName(self):
    contest_details = """
      <Name></Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    empty_name_contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(empty_name_contest)

  def testIgnoresContestsThatDoNotSuggestPrimary_NotPrimary(self):
    contest_details = """
      <Name>for sure not a primary</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Dem(self):
    contest_details = """
      <Name>Might Be Primary (dem)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    dem_contest = root.find("Election").find("CandidateContest")
    dem_contest.sourceline = 7
    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(dem_contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Rep(self):
    contest_details = """
      <Name>Might Be Primary (rep)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    rep_contest = root.find("Election").find("CandidateContest")
    rep_contest.sourceline = 7
    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(rep_contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Lib(self):
    contest_details = """
      <Name>Might Be Primary (lib)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    lib_contest = root.find("Election").find("CandidateContest")
    lib_contest.sourceline = 7
    with self.assertRaises(loggers.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(lib_contest)


class CoalitionPartiesTest(absltest.TestCase):

  _base_election_coalition = """
    <Election>
      <Coalition>
        {}
      </Coalition>
    </Election>
  """

  def testEachCoalitionHasDefinedPartyId(self):
    root_string = """
      <Election>
        <Coalition>
          <PartyIds>abc123</PartyIds>
        </Coalition>
        <Coalition>
          <PartyIds>def456</PartyIds>
        </Coalition>
      </Election>
    """
    election_tree = etree.fromstring(root_string)
    rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_NoPartyId(self):
    no_party_string = self._base_election_coalition.format("")
    election_tree = etree.fromstring(no_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_EmptyPartyId(self):
    coalition_details = "<PartyIds></PartyIds>"
    empty_party_string = self._base_election_coalition.format(coalition_details)
    election_tree = etree.fromstring(empty_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_Whitespace(self):
    coalition_details = "<PartyIds>     </PartyIds>"
    all_space_party_string = self._base_election_coalition.format(
        coalition_details)
    election_tree = etree.fromstring(all_space_party_string)

    with self.assertRaises(loggers.ElectionError):
      rules.CoalitionParties(election_tree, None).check()


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


class CandidatesReferencedOnceTest(absltest.TestCase):

  def setUp(self):
    super(CandidatesReferencedOnceTest, self).setUp()
    self.cand_validator = rules.CandidatesReferencedOnce(None, None)
    self._election_report = """
        <Election>
          <ContestCollection>
            {}
          </ContestCollection>
            {}
         </Election>
    """
    self._candidate_collection = """
      <CandidateCollection>
        <Candidate objectId="can99999a"/>
        <Candidate objectId="can99999b" />
        <Candidate objectId="can11111a" />
        <Candidate objectId="can11111b" />
        <Candidate objectId="can45678a" />
        {}
      </CandidateCollection>
    """
    self._base_candidate_contest = """
      <Contest objectId="con1234">
        <BallotSelection objectId="cs12345">
          <CandidateIds>can99999a can99999b</CandidateIds>
        </BallotSelection>
        <BallotSelection objectId="cs98765">
          <CandidateIds>can11111a can11111b</CandidateIds>
        </BallotSelection>
        <BallotSelection>
          <CandidateIds>can45678a</CandidateIds>
        </BallotSelection>
      </Contest>
    """
    self._base_retention_contest = """
      <Contest objectId="con5678">
        <CandidateId>can99999a</CandidateId>
        <BallotSelection objectId="cs12345">
          <Selection>
            <Text language="en">Yes</Text>
          </Selection>
        </BallotSelection>
        <BallotSelection objectId="cs98765">
          <Selection>
            <Text language="en">No</Text>
          </Selection>
        </BallotSelection>
      </Contest>
    """

  # _register_candidates test
  def testMapsCandIdsToTheContestsThatReferenceThem_CandContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_candidate_contest, candidate_string)
    election_tree = etree.fromstring(root_string)
    expected_seen_candidates = dict({
        "can99999a": ["con1234"],
        "can99999b": ["con1234"],
        "can11111a": ["con1234"],
        "can11111b": ["con1234"],
        "can45678a": ["con1234"],
        "can54321": [],
    })
    candidate_registry = self.cand_validator._register_candidates(election_tree)
    self.assertEqual(expected_seen_candidates, candidate_registry)

  def testMapsCandIdsToTheContestsThatReferenceThem_RetentionContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_retention_contest, candidate_string)
    election_tree = etree.fromstring(root_string)

    expected_seen_candidates = dict({
        "can99999a": ["con5678"],
        "can99999b": [],
        "can11111a": [],
        "can11111b": [],
        "can45678a": [],
        "can54321": [],
    })
    candidate_registry = self.cand_validator._register_candidates(election_tree)
    self.assertEqual(expected_seen_candidates, candidate_registry)

  def testMapsCandIdsToTheContestsThatReferenceThem_MultiContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    two_contests = self._base_candidate_contest + self._base_retention_contest
    root_string = self._election_report.format(two_contests, candidate_string)
    election_tree = etree.fromstring(root_string)

    expected_seen_candidates = dict({
        "can99999a": ["con1234", "con5678"],
        "can99999b": ["con1234"],
        "can11111a": ["con1234"],
        "can11111b": ["con1234"],
        "can45678a": ["con1234"],
        "can54321": [],
    })
    candidate_registry = self.cand_validator._register_candidates(election_tree)
    self.assertEqual(expected_seen_candidates, candidate_registry)

  # check tests
  def testItChecksThatEachCandidateOnlyMapsToOneContest(self):
    root_string = self._election_report.format(
        self._base_candidate_contest, self._candidate_collection)
    election_tree = etree.fromstring(root_string)
    self.cand_validator.check(election_tree)

  def testRaisesAnErrorIfACandidateMapsToMultipleContests(self):
    two_contests = self._base_candidate_contest + self._base_retention_contest
    root_string = self._election_report.format(
        two_contests, self._candidate_collection)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionTreeError) as ete:
      self.cand_validator.check(election_tree)
    self.assertIn(
        "The Election File contains invalid Candidate references",
        str(ete.exception))
    self.assertIn("can99999a", ete.exception.error_log[0].message)
    self.assertIn("con1234", ete.exception.error_log[0].message)
    self.assertIn("con5678", ete.exception.error_log[0].message)

  def testRaisesAnErrorIfACandidateIsNotReferencedInAContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_candidate_contest, candidate_string)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionTreeError) as ete:
      self.cand_validator.check(election_tree)
    self.assertIn(
        "The Election File contains invalid Candidate references",
        str(ete.exception))
    self.assertIn("can54321 is not referenced",
                  ete.exception.error_log[0].message)

  def testRaisesAnErrorIfAContestreferToANonExistingCandidate(self):
    incomplete_candidate_string = """
      <CandidateCollection>
        <Candidate objectId="can99999a"/>
        <Candidate objectId="can11111a" />
        <Candidate objectId="can11111b" />
        <Candidate objectId="can45678a" />
      </CandidateCollection>
    """
    root_string = self._election_report.format(
        self._base_candidate_contest, incomplete_candidate_string)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionTreeError) as ete:
      self.cand_validator.check(election_tree)
    self.assertIn(
        "The Election File contains invalid Candidate references",
        str(ete.exception))
    self.assertIn("Contest con1234 refer to a non existing candidate can99999b",
                  ete.exception.error_log[0].message)


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
    self.assertIn("is not a valid hex color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

  def testColorTagMissingValue(self):
    root_string = self._base_string.format(self._color_str.format(""))
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("is missing a value", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

  def testPartiesHaveNonHex(self):
    root_string = self._base_string.format(self._color_str.format("green"))
    element = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("is not a valid hex color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

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
    self.assertIn("has more than one color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))


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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.color_validator.check(element)
    self.assertIn("parties with duplicate colors", str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

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
    with self.assertRaises(loggers.ElectionTreeError):
      self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfContestIsMissingNameOrNameIsEmpty_Empty(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    empty = "<Name></Name>"
    root_string = self._base_report.format(pres, sec, empty)
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionTreeError):
      self.duplicate_validator.check(election_tree)

  def testRaisesAnErrorIfNameIsNotUnique(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    duplicate = "<Name>President</Name>"
    root_string = self._base_report.format(pres, sec, duplicate)
    election_tree = etree.fromstring(root_string)
    with self.assertRaises(loggers.ElectionTreeError):
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
    self.assertIn("is not in the correct format.", str(cm.exception))

  def testEmptyStableIDFails(self):

    test_string = self.root_string.format("other", self.stable_string, "   ")
    with self.assertRaises(loggers.ElectionError) as cm:
      self.stable_id_validator.check(etree.fromstring(test_string))
    self.assertIn("is not in the correct format.", str(cm.exception))


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

  def testMakesSureContestNamesAreNotAllCapsIfTheyExist(self):
    contest_string = """
      <Contest>
        <Name>Deandra Reynolds</Name>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    self.caps_validator.check(element)

  def testIgnoresContestElementsWithNoName(self):
    no_name_string = """
      <Contest/>
    """
    element = etree.fromstring(no_name_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfContestNameIsAllCaps(self):
    contest_string = """
      <Contest>
        <Name>DEANDRA REYNOLDS</Name>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(loggers.ElectionWarning):
      self.caps_validator.check(element)

  def testMakesSureFullNamesAreNotAllCapsIfTheyExist(self):
    party_contest_string = """
      <PartyContest>
        <FullName>
          <Text>World's Cutest Dog</Text>
        </FullName>
      </PartyContest>
    """
    element = etree.fromstring(party_contest_string)

    self.caps_validator.check(element)

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

  def testRaisesWarningIfFullNamesAreAllCaps_PartyContest(self):
    party_contest_string = """
      <PartyContest>
        <FullName>
          <Text>DEANDRA REYNOLDS</Text>
        </FullName>
      </PartyContest>
    """
    element = etree.fromstring(party_contest_string)

    with self.assertRaises(loggers.ElectionWarning):
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
    self.assertIn("Valid OCD-IDs should be all lowercase", str(ew.exception))

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

  base_string = """<Contest>{}</Contest>"""

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
    self.assertIn("has more than one associated office.", str(cm.exception))

  def testNoOfficesFail(self):
    root_string = self.base_string.format("<OfficeIds></OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(loggers.ElectionWarning) as cm:
      self.contest_offices_validator.check(element)
    self.assertIn("has no associated offices.", str(cm.exception))


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
                  str(cm.exception))

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

    self.assertIn("OfficeHolders. Must have exactly one.", str(cm.exception))


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
    self.assertIn("Election data is prohibited", str(ee.exception))


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
      self.assertIn(vc_type, str(cm.exception))

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
      self.assertIn(vc_type, str(cm.exception))


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
    self.assertIn("Missing URI value.", str(ee.exception))

  def testRaisesAnErrorIfNoSchemeProvided(self):
    missing_scheme = self.uri_element.format("www.whitehouse.gov")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_scheme))
    self.assertIn("protocol - invalid", str(ee.exception))

  def testRaisesAnErrorIfSchemeIsNotInApprovedList(self):
    invalid_scheme = self.uri_element.format("tps://www.whitehouse.gov")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("protocol - invalid", str(ee.exception))

  def testRaisesAnErrorIfNetLocationNotProvided(self):
    missing_netloc = self.uri_element.format("missing/loc.md")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_netloc))
    self.assertIn("domain - missing", str(ee.exception))

  def testRaisesAnErrorIfUriNotAscii(self):
    unicode_url = self.uri_element.format(u"https://nahnah.com/nopê")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(unicode_url))
    self.assertIn("not ascii encoded", str(ee.exception))

  def testAllowsQueryParamsToBeIncluded(self):
    contains_query = self.uri_element.format(
        "http://www.whitehouse.gov?filter=yesplease")
    self.uri_validator.check(etree.fromstring(contains_query))

  def testAggregatesErrors(self):
    multiple_issues = self.uri_element.format("missing/loc.md?filter=yesplease")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(multiple_issues))
    self.assertIn("protocol - invalid", str(ee.exception))
    self.assertIn("domain - missing", str(ee.exception))


class ParentHierarchyObjectIdStrTest(absltest.TestCase):

  def testParentHierarchyIsEmpty(self):
    uri = "<Uri>www.facebook.com/michael_scott</Uri>"
    uri_element = etree.fromstring(uri)
    actual_value = rules.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Uri", actual_value)

  def testParentHierarchyStopWhenObjectIdIsdefined(self):
    election_feed = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ContactInformation>
              <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
              </Uri>
            </ContactInformation>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find(
        "PersonCollection/Person/ContactInformation/Uri")

    actual_value = rules.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Person:per1 > ContactInformation > Uri", actual_value)

  def testParentHierarchyToTheTopIfNoObjectIdIsdefined(self):
    election_feed = """
      <ElectionReport>
        <Election>
          <ContactInformation>
            <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
            </Uri>
          </ContactInformation>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find("Election/ContactInformation/Uri")

    actual_value = rules.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("ElectionReport > Election > ContactInformation > Uri",
                     actual_value)


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

    fb_one = facebook_uri.format("www.facebook.com/michael_scott")
    fb_two = facebook_uri.format("www.facebook.com/dwight_shrute")
    personal_one = person_website_uri.format("www.michaelscott.com")
    personal_two = person_website_uri.format("www.dwightshrute.com")
    party_one = party_website_uri.format("www.dundermifflin.com")
    party_two = party_website_uri.format("www.sabre.com")
    wiki_one = wikipedia_uri.format("www.wikipedia.com/dundermifflin")
    wiki_two = wikipedia_uri.format("www.wikipedia.com/dundermifflin")

    uri_elements = [
        etree.fromstring(fb_one), etree.fromstring(fb_two),
        etree.fromstring(personal_one), etree.fromstring(personal_two),
        etree.fromstring(party_one), etree.fromstring(party_two),
        etree.fromstring(wiki_one), etree.fromstring(wiki_two),
    ]

    expected_mapping = {
        "facebook": {
            "www.facebook.com/michael_scott": ["Uri"],
            "www.facebook.com/dwight_shrute": ["Uri"],
        },
        "website": {
            "www.michaelscott.com": ["Uri"],
            "www.dwightshrute.com": ["Uri"],
            "www.dundermifflin.com": ["Uri"],
            "www.sabre.com": ["Uri"],
        },
        "wikipedia": {
            "www.wikipedia.com/dundermifflin": ["Uri", "Uri"],
        }
    }
    uri_validator = rules.UniqueURIPerAnnotationCategory(None, None)
    actual_mapping = uri_validator._extract_uris_by_category(uri_elements)

    self.assertEqual(expected_mapping, actual_mapping)

  def testChecksURIsWithNoAnnotation(self):
    uri_element = "<Uri>{}</Uri>"

    uri_one = uri_element.format("www.facebook.com/michael_scott")
    uri_two = uri_element.format("www.facebook.com/dwight_shrute")
    uri_three = uri_element.format("www.facebook.com/dwight_shrute")

    uri_elements = [
        etree.fromstring(uri_one), etree.fromstring(uri_two),
        etree.fromstring(uri_three)
    ]

    expected_mapping = {
        "": {
            "www.facebook.com/michael_scott": ["Uri"],
            "www.facebook.com/dwight_shrute": ["Uri", "Uri"],
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

  def testThrowsErrorIfThereAreDuplicatesWithinCategory(self):
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
    with self.assertRaises(loggers.ElectionError) as ee:
      uri_validator.check()
    self.assertEqual(("'There are duplicate URIs in the feed. URIs should be "
                      "unique for each category.'"), str(ee.exception))
    self.assertIn(("The annotation type wikipedia contains duplicate"
                   " value: https://wikipedia.com/dunder_mifflin. "
                   "It appears 4 times in the following elements:"),
                  ee.exception.error_log[0].message)
    self.assertIn(("'Party:par2 > ContactInformation > Uri'"),
                  ee.exception.error_log[0].message)
    self.assertIn(("'Person:per1 > ContactInformation > Uri'"),
                  ee.exception.error_log[0].message)
    self.assertIn(("'Person:per2 > ContactInformation > Uri'"),
                  ee.exception.error_log[0].message)
    self.assertIn(("'Party:par1 > ContactInformation > Uri'"),
                  ee.exception.error_log[0].message)

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
    self.assertIn("missing annotation", str(cm.exception))

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
    self.assertIn("missing usage type.", str(cm.exception))

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
    self.assertIn("has usage type, missing platform.", str(cm.exception))

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
    self.assertIn("incorrect for URI", str(cm.exception))

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
    self.assertIn("is not a valid annotation.", str(cm.exception))

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
    self.assertIn("official-fb is not a valid annotation", str(cm.exception))


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
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))

  def testOfficeDoesNotHaveJurisdictionIDTextByAdditionalData(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id"></AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))

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
    self.assertIn("Office off1 has more than one jurisdiction-id",
                  str(cm.exception))

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
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))

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
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))

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
    self.assertIn("Office off1 has more than one jurisdiction-id",
                  str(cm.exception))

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
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))

  def testJurisdictionIDTextIsWhitespaceByAdditionalData(self):
    test_string = """
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id">    </AdditionalData>
          </Office>
        """
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("Office off2 is missing a jurisdiction-id", str(cm.exception))


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
    self.assertIn("ru-gpu99", str(ee.exception))


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
    test_string = self.root_string.format("""
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>District</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    self.offices_validator.check(element)

  def testOfficeDoesNotHaveOfficeLevelByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>Region</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing an office-level", str(cm.exception))

  def testOfficeDoesNotHaveOfficeLevelTextByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value></Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing an office-level", str(cm.exception))

  def testOfficeHasMoreThanOneOfficeLevelsbyExternalIdentifier(self):
    test_string = self.root_string.format("""
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
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("has more than one office-level", str(cm.exception))

  def testOfficeLevelTextIsWhitespaceByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing an office-level", str(cm.exception))

  def testInvalidOfficeLevel(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>office-level</OtherType>
               <Value>invalidvalue</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(loggers.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("has invalid office-level", str(cm.exception))


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
    self.assertIn("GpUnits tree has more than one root", str(cm.exception))

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
    self.assertIn("GpUnits have no geo district root.", str(cm.exception))


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
    self.assertIn("Cycle detected at node", str(cm.exception))

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
    self.assertEqual("'Office (objectId: off1) is missing a Term'",
                     str(ew.exception))

  def testChecksEndDateIsAfterStartDate(self):
    office_string = self.office_string.format("2020-01-01", "2020-01-02")
    self.date_validator.check(etree.fromstring(office_string))

  def testRaisesErrorIfEndDateIsBeforeStartDate(self):
    office_string = self.office_string.format("2020-01-03", "2020-01-02")
    with self.assertRaises(loggers.ElectionError) as ee:
      self.date_validator.check(etree.fromstring(office_string))
    self.assertEqual("'The Office term dates are invalid.'", str(ee.exception))
    self.assertIn("The dates (start: 2020-01-03, end: 2020-01-02) are invalid",
                  ee.exception.error_log[0].message)
    self.assertIn("The end date must be the same or after the start date.",
                  ee.exception.error_log[0].message)

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
    self.assertEqual(("'Office (objectId: off1) is missing a Term > "
                      "StartDate.'"), str(ee.exception))

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
    self.assertIn(
        "GpUnit ru0002 is required to have exactly one InterationalizedName"
        " element.", str(cm.exception))

  def testInternationalizedNameElementNoSubelements(self):
    root_string = """
    <GpUnit objectId="ru0002">
      <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
      <InternationalizedName/>
    </GpUnit>
    """
    with self.assertRaises(loggers.ElectionError) as cm:
      self.gpunits_intl_name_validator.check(etree.fromstring(root_string))
    self.assertIn("GpUnit ru0002", str(cm.exception))
    self.assertIn(
        "is required to have one or more Text elements.",
        str(cm.exception))

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
    self.assertIn("GpUnit ru0002", str(cm.exception))
    self.assertIn("does not have a text value", str(cm.exception))

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
    self.assertIn("GpUnit ru0002", str(cm.exception))
    self.assertIn("does not have a text value", str(cm.exception))

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
    self.assertIn("GpUnit ru0002", str(cm.exception))
    self.assertIn("does not have a text value", str(cm.exception))

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
    self.assertIn("GpUnit ru0002 is required to have exactly one "
                  "InterationalizedName element.", str(cm.exception))


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

    self.assertIn("There are misformatted contests.", str(ew.exception))
    self.assertIn("can123", ew.exception.error_log[0].message)
    self.assertIn("can456", ew.exception.error_log[0].message)
    self.assertIn("con987", ew.exception.error_log[0].message)


class RequiredFieldsTest(absltest.TestCase):

  def setUp(self):
    super(RequiredFieldsTest, self).setUp()
    self.field_validator = rules.RequiredFields(None, None)

  def testEachElementHasCorrespondingRequiredField(self):
    elements = self.field_validator.elements()
    registered_elements = self.field_validator._element_field_mapping.keys()

    for registered_element in registered_elements:
      self.assertIn(registered_element, elements)

  def testRequiredFieldIsPresent_Person(self):
    person = """
      <Person>
        <FullName>
          <Text language="en">Michael Scott</Text>
         </FullName>
      </Person>
    """
    self.field_validator.check(etree.fromstring(person))

  def testRequiredFieldIsPresent_Candidate(self):
    candidate = """
      <Candidate>
        <PersonId>per12345</PersonId>
      </Candidate>
    """
    self.field_validator.check(etree.fromstring(candidate))

  def testThrowsErrorIfFieldIsMissing_Person(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(person))
    self.assertIn(("Element Person (objectId: 123) is missing required field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))

  def testThrowsErrorIfFieldIsMissing_Candidate(self):
    candidate = """
      <Candidate objectId="123">
      </Candidate>
    """
    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(candidate))
    self.assertIn(("Element Candidate (objectId: 123) is missing required field"
                   " PersonId."), str(ee.exception.error_log[0].message))

  def testThrowsErrorIfFieldIsEmpty(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text language="en"></Text>
         </FullName>
      </Person>
    """
    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(person))
    self.assertIn(("Element Person (objectId: 123) is missing required field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))

  def testThrowsErrorIfFieldIsWhiteSpace(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text language="en">   </Text>
        </FullName>
      </Person>
    """
    with self.assertRaises(loggers.ElectionError) as ee:
      self.field_validator.check(etree.fromstring(person))
    self.assertIn(("Element Person (objectId: 123) is missing required field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))


class RulesTest(absltest.TestCase):

  def testAllRulesIncluded(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()

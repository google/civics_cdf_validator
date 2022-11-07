# -*- coding: utf-8 -*-
"""Unit test for base.py."""

import io
import sys
from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from lxml import etree
from mock import MagicMock
from mock import patch


class ValidReferenceRuleTest(absltest.TestCase):

  def testItExtendsTreeRule(self):
    self.assertTrue(issubclass(base.ValidReferenceRule, base.TreeRule))

  def testMockGatherValidReference(self):
    return set(["id-1", "id-2"])

  def testMockGatherInvalidReference(self):
    return set(["id-1", "id-5", "id-6"])

  def testMockGatherDefined(self):
    return set(["id-1", "id-2", "id-3", "id-4"])

  @patch.object(base.ValidReferenceRule, "_gather_reference_values",
                testMockGatherValidReference)
  @patch.object(base.ValidReferenceRule, "_gather_defined_values",
                testMockGatherDefined)
  def testMakesSureEachReferenceIDIsValid(self):
    base.ValidReferenceRule(None, None).check()

  @patch.object(base.ValidReferenceRule, "_gather_reference_values",
                testMockGatherInvalidReference)
  @patch.object(base.ValidReferenceRule, "_gather_defined_values",
                testMockGatherDefined)
  def testRaisesAnErrorIfAValueDoesNotReferenceADefinedValue(self):
    with self.assertRaises(loggers.ElectionError) as ee:
      base.ValidReferenceRule(None, None).check()
    self.assertIn("id-5", ee.exception.log_entry[0].message)
    self.assertIn("id-6", ee.exception.log_entry[0].message)


class MissingFieldRuleTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldRuleTest, self).setUp()
    self.validator = base.MissingFieldRule(None, None)

  # get_severity test
  def testShouldReturnSeverityLevelOfException(self):
    with self.assertRaises(NotImplementedError):
      self.validator.get_severity()

  # element_field_mapping test
  def testShouldReturnADictOfEntitiesToRequiredFields(self):
    with self.assertRaises(NotImplementedError):
      self.validator.element_field_mapping()

  # setup tests
  def testSetsExceptionWhenSeverityProperlySet_Info(self):
    self.validator.get_severity = MagicMock(return_value=0)
    self.validator.setup()
    self.assertEqual(loggers.ElectionInfo, self.validator.exception)

  def testSetsExceptionWhenSeverityProperlySet_Warning(self):
    self.validator.get_severity = MagicMock(return_value=1)
    self.validator.setup()
    self.assertEqual(loggers.ElectionWarning, self.validator.exception)

  def testSetsExceptionWhenSeverityProperlySet_Error(self):
    self.validator.get_severity = MagicMock(return_value=2)
    self.validator.setup()
    self.assertEqual(loggers.ElectionError, self.validator.exception)

  def testRaisesExceptionWhenGivenInvalidSeverity(self):
    self.validator.get_severity = MagicMock(return_value=-1)
    with self.assertRaises(Exception):
      self.validator.setup()

    self.validator.get_severity = MagicMock(return_value=-3)
    with self.assertRaises(Exception):
      self.validator.setup()

  # elements test
  def testElementsReturnsKeysFromFieldMapping(self):
    elements = {
        "Person": ["PartyId", "CandidateId"],
        "Office": ["Term//StartDate"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    registered_elements = self.validator.elements()

    for registered_element in registered_elements:
      self.assertIn(registered_element, elements.keys())

  # check tests
  def testRequiredFieldIsPresent(self):
    person = """
      <Person>
        <FullName>
          <Text language="en">Michael Scott</Text>
         </FullName>
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.check(etree.fromstring(person))

  # check tests
  def testRaisesExceptionIfFieldIsMissing_Error(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as ee:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ee.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testRaisesExceptionIfFieldIsMissing_Warning(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionWarning

    with self.assertRaises(loggers.ElectionWarning) as ew:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ew.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ew.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testRaisesExceptionIfFieldIsMissing_Info(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionInfo

    with self.assertRaises(loggers.ElectionInfo) as ei:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ei.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ei.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testRaisesExceptionIfFieldIsEmpty(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text></Text>
        </FullName>
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as ee:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ee.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testRaisesExceptionIfFieldIsWhiteSpace(self):
    person = """
      <Person objectId="123">
        <FullName>
          <Text>   </Text>
        </FullName>
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as ee:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ee.exception.log_entry[0].elements[0].get("objectId"),
                     "123")

  def testHandlesMultipleFieldsPerEntity(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text", "PartyId"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as ee:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(ee.exception.log_entry[0].message,
                     "The element Person is missing field FullName//Text.")
    self.assertEqual(ee.exception.log_entry[0].elements[0].get("objectId"),
                     "123")
    self.assertEqual(ee.exception.log_entry[1].message,
                     "The element Person is missing field PartyId.")
    self.assertEqual(ee.exception.log_entry[1].elements[0].get("objectId"),
                     "123")


class RulesRegistryTest(absltest.TestCase):

  def setUp(self):
    super(RulesRegistryTest, self).setUp()
    self.registry = base.RulesRegistry("test.xml", "schema.xsd", [], [])
    root_string = """
      <ElectionReport>
        <PartyCollection>
          <Party objectId="par0001">
            <InternationalizedAbbreviation>
              <Text language="en">Republican</Text>
            </InternationalizedAbbreviation>
            <Name>
              <Text language="en">Republican</Text>
            </Name>
            <Color>e30413</Color>
          </Party>
          <Party objectId="par0002">
            <Name>
              <Text language="en">Democratic</Text>
            </Name>
          </Party>
        </PartyCollection>
        <PersonCollection>
          <Person objectId="p1">
            <PartyId>par0001</PartyId>
          </Person>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        <CandidateCollection>
          <Candidate>
            <PartyId>par0003</PartyId>
          </Candidate>
        </CandidateCollection>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
          <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <GpUnitCollection>
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
        </GpUnitCollection>
        <ContestCollection>
          <Contest objectId="cc11111">
           <Name>Test</Name>
          </Contest>
          <Contest objectId="cc22222">
            <Name>Test1</Name>
          </Contest>
          <Contest objectId="cc33333">
            <Name>Test2</Name>
            <BallotSelection objectId="cs-br1-alckmin">
              <VoteCountsCollection>
                <VoteCounts><Type>total</Type><Count>0</Count></VoteCounts>
              </VoteCountsCollection>
            </BallotSelection>
          </Contest>
        </ContestCollection>
      </ElectionReport>
    """
    self.registry.election_tree = etree.fromstring(root_string)

  def testCountAndPrintEntityStats(self):
    if sys.version_info.major < 3:
      out = io.BytesIO()
    else:
      out = io.StringIO()
    sys.stdout = out
    self.registry.count_stats()
    output = out.getvalue().strip()
    expected_entity_counts = {
        "Party": 2,
        "Person": 3,
        "Candidate": 1,
        "Office": 2,
        "GpUnit": 3,
        "Contest": 3
    }

    # Value: (found_in_n_entities, missing_in_m_entities).
    expected_attr_counts = {
        "ComposingGpUnitIds": (3, 0),
        "Color": (1, 1),
        "BallotSelection": (1, 2),
        "InternationalizedAbbreviation": (1, 1)
    }

    for entity, count in expected_entity_counts.items():
      self.assertIn("{0} (Total: {1})".format(entity, count), output)

    for attr, stat in expected_attr_counts.items():
      count, missing_in = stat
      self.assertIn(
          "{:<30s}{:^8s}{:>15s}".format(attr, str(count), str(missing_in)),
          output)


if __name__ == "__main__":
  absltest.main()

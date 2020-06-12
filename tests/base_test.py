# -*- coding: utf-8 -*-
"""Unit test for base.py."""

import datetime
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
    self.assertIn("id-5", str(ee.exception))
    self.assertIn("id-6", str(ee.exception))


class DateRuleTest(absltest.TestCase):

  def setUp(self):
    super(DateRuleTest, self).setUp()
    self.date_validator = base.DateRule(None, None)
    self.today = datetime.datetime.now().date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  # reset_instance_vars test
  def testResetsInstanceVarsToInitialState(self):
    start_elem = etree.fromstring("<StartDate>2020-01-01</StartDate>")
    end_elem = etree.fromstring("<EndDate>2020-01-03</EndDate>")
    start_date = self.today + datetime.timedelta(days=1)
    end_date = self.today + datetime.timedelta(days=2)

    validator_with_values = base.DateRule(None, None)
    validator_with_values.start_elem = start_elem
    validator_with_values.start_date = start_date
    validator_with_values.end_elem = end_elem
    validator_with_values.end_date = end_date
    validator_with_values.error_log = ["This is no longer empty"]

    fresh_validator = base.DateRule(None, None)

    self.assertNotEqual(
        validator_with_values.start_elem, fresh_validator.start_elem)
    self.assertNotEqual(
        validator_with_values.start_date, fresh_validator.start_date)
    self.assertNotEqual(
        validator_with_values.end_elem, fresh_validator.end_elem)
    self.assertNotEqual(
        validator_with_values.end_date, fresh_validator.end_date)
    self.assertNotEqual(
        validator_with_values.error_log, fresh_validator.error_log)

    validator_with_values.reset_instance_vars()

    self.assertEqual(
        validator_with_values.start_elem, fresh_validator.start_elem)
    self.assertEqual(
        validator_with_values.start_date, fresh_validator.start_date)
    self.assertEqual(
        validator_with_values.end_elem, fresh_validator.end_elem)
    self.assertEqual(
        validator_with_values.end_date, fresh_validator.end_date)
    self.assertEqual(
        validator_with_values.error_log, fresh_validator.error_log)

  # gather_dates tests
  def testSetStartAndEndDatesAsInstanceVariables(self):
    start_date = self.today + datetime.timedelta(days=1)
    end_date = self.today + datetime.timedelta(days=2)

    election_string = self.election_string.format(
        start_date, end_date)
    election = etree.fromstring(election_string)
    self.date_validator.gather_dates(election)

    self.assertEqual(start_date, self.date_validator.start_date)
    self.assertEqual(end_date, self.date_validator.end_date)

  def testRaisesErrorForInvalidDateFormats(self):
    start_date_time = datetime.datetime.now() + datetime.timedelta(days=1)
    end_date_time = datetime.datetime.now() + datetime.timedelta(days=2)

    election_string = self.election_string.format(
        start_date_time, end_date_time)
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionError):
      self.date_validator.gather_dates(election)

  def testDoesNotAssignDatesIfElementsNotFound(self):
    election_string = "<Election></Election>"
    self.date_validator.gather_dates(etree.fromstring(election_string))
    self.assertEqual(None, self.date_validator.start_date)
    self.assertEqual(None, self.date_validator.start_elem)
    self.assertEqual(None, self.date_validator.end_date)
    self.assertEqual(None, self.date_validator.end_elem)

  # check_for_date_not_in_past tests
  def testProvidedDateIsNotInThePast(self):
    future_date = self.today + datetime.timedelta(days=1)
    self.date_validator.check_for_date_not_in_past(future_date, None)

    self.assertEmpty(self.date_validator.error_log)

  def testAddsToErrorLogIfDateInPast(self):
    past_date = self.today - datetime.timedelta(days=1)
    date_elem = etree.fromstring("<StartDate>2012-01-01</StartDate>")
    self.date_validator.check_for_date_not_in_past(past_date, date_elem)

    self.assertLen(self.date_validator.error_log, 1)
    self.assertEqual("The date {} is in the past.".format(past_date),
                     self.date_validator.error_log[0].message)

  # check_end_after_start tests
  def testEndDateComesAfterStartDate(self):
    self.date_validator.start_date = self.today + datetime.timedelta(days=1)
    self.date_validator.end_date = self.today + datetime.timedelta(days=2)
    self.date_validator.check_end_after_start()

    self.assertEmpty(self.date_validator.error_log)

  def testAddsToErrorLogIfEndDateIsBeforeStartDate(self):
    self.date_validator.start_date = self.today + datetime.timedelta(days=3)
    self.date_validator.end_date = self.today + datetime.timedelta(days=2)
    end_elem_string = "<EndDate>2012-01-01</EndDate>"
    self.date_validator.end_elem = etree.fromstring(end_elem_string)
    self.date_validator.check_end_after_start()

    self.assertLen(self.date_validator.error_log, 1)
    self.assertIn("The end date must be the same or after the start date.",
                  self.date_validator.error_log[0].message)


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
    self.assertEqual("'Person is missing fields.'", str(ee.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))

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
    self.assertEqual("'Person is missing fields.'", str(ew.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ew.exception.error_log[0].message))

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
    self.assertEqual("'Person is missing fields.'", str(ei.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ei.exception.error_log[0].message))

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
    self.assertEqual("'Person is missing fields.'", str(ee.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))

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
    self.assertEqual("'Person is missing fields.'", str(ee.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))

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
    self.assertEqual("'Person is missing fields.'", str(ee.exception))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " FullName//Text."), str(ee.exception.error_log[0].message))
    self.assertIn(("Element Person (objectId: 123) is missing field"
                   " PartyId."), str(ee.exception.error_log[1].message))


class RulesRegistryTest(absltest.TestCase):

  def setUp(self):
    super(RulesRegistryTest, self).setUp()
    self.registry = base.RulesRegistry("test.xml", "schema.xsd", [], [])
    root_string = """
      <ElectionReport>
        <PartyCollection>
          <Party objectId="par0001">
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
        "BallotSelection": (1, 2)
    }

    for entity, count in expected_entity_counts.items():
      self.assertIn("{0} (Total: {1})".format(entity, count), output)

    for attr, stat in expected_attr_counts.items():
      count, missing_in = stat
      self.assertIn(
          "{:<22s}{:^8s}{:>15s}".format(attr, str(count), str(missing_in)),
          output)


if __name__ == "__main__":
  absltest.main()

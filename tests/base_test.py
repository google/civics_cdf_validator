# -*- coding: utf-8 -*-
"""Unit test for base.py."""

from collections.abc import Callable
import contextlib
import datetime
import io
import sys
from unittest.mock import MagicMock
from unittest.mock import patch

from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import stats
import freezegun
from lxml import etree

_TEST_US_OCD_ID_1 = "ocd-division/country:us"
_TEST_US_OCD_ID_2 = "ocd-division/country:us/state:ny"
_TEST_CA_OCD_ID_1 = "ocd-division/country:ca"
_TEST_CA_OCD_ID_2 = "ocd-division/country:ca/cd:1207/district:0"


class _FakeOptionRule(base.BaseRule):
  """Fake rule with a configurable option, checking Party elements."""

  def __init__(
      self,
      election_tree: etree._ElementTree | None,
      schema_tree: etree._ElementTree | None,
      ocd_id_validator: object | None = None,
  ) -> None:
    super().__init__(election_tree, schema_tree, ocd_id_validator)
    self.fake_option = "default-value"

  def elements(self) -> list[str]:
    return ["Party"]

  def check(self, element: etree._Element) -> None:
    pass


class _FakePartyRule(base.BaseRule):
  """Fake rule raising an error for every Party element."""

  def elements(self) -> list[str]:
    return ["Party", "Party"]

  def check(self, element: etree._Element) -> None:
    raise loggers.ElectionError.from_message(
        f"Fake error for {element.get('objectId')}.", [element]
    )


class _FakeTreeRule(base.TreeRule):
  """Fake tree rule always raising a warning."""

  def check(self) -> None:
    raise loggers.ElectionWarning.from_message("Fake tree warning.")


class SchemaHandlerTest(absltest.TestCase):

  def test_get_element_class_none_element_returns_none(self):
    schema_handler = base.SchemaHandler()

    element_class = schema_handler.get_element_class(None)

    self.assertIsNone(element_class)


class BaseRuleTest(absltest.TestCase):

  def test_set_option_existing_attribute_sets_value(self):
    validator = _FakeOptionRule(None, None)
    option = base.RuleOption("fake_option", "fake-value")

    validator.set_option(option)

    self.assertEqual(validator.fake_option, "fake-value")

  def test_set_option_unknown_attribute_raises_election_exception(self):
    validator = _FakeOptionRule(None, None)
    option = base.RuleOption("unknown_option", "fake-value")

    with self.assertRaises(loggers.ElectionException) as context:
      validator.set_option(option)

    self.assertFalse(hasattr(validator, "unknown_option"))
    self.assertIsInstance(context.exception, loggers.ElectionException)


class ValidReferenceRuleTest(absltest.TestCase):

  def test_extends_tree_rule_returns_true(self):
    self.assertTrue(issubclass(base.ValidReferenceRule, base.TreeRule))

  def _mock_gather_valid_reference(self):
    return {"id-1", "id-2"}

  def _mock_gather_invalid_reference(self):
    return {"id-1", "id-5", "id-6"}

  def _mock_gather_defined(self):
    return {"id-1", "id-2", "id-3", "id-4"}

  @patch.object(
      base.ValidReferenceRule,
      "_gather_reference_values",
      _mock_gather_valid_reference,
  )
  @patch.object(
      base.ValidReferenceRule, "_gather_defined_values", _mock_gather_defined
  )
  def test_valid_references_succeeds(self):
    base.ValidReferenceRule(None, None).check()

  @patch.object(
      base.ValidReferenceRule,
      "_gather_reference_values",
      _mock_gather_invalid_reference,
  )
  @patch.object(
      base.ValidReferenceRule, "_gather_defined_values", _mock_gather_defined
  )
  def test_invalid_reference_fails(self):
    validator = base.ValidReferenceRule(None, None)
    with self.assertRaises(loggers.ElectionError) as context:
      validator.check()
    self.assertIn("id-5", context.exception.log_entry[0].message)
    self.assertIn("id-6", context.exception.log_entry[0].message)


class DateRuleTest(absltest.TestCase):

  def setUp(self):
    super(DateRuleTest, self).setUp()
    self.date_validator = base.DateRule(None, None)
    self.today = datetime.datetime.now(datetime.timezone.utc).date()
    self.today_partial_date = base.PartialDate(
        self.today.year, self.today.month, self.today.day
    )

    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  # __init__ test
  def test_init_stores_election_and_schema_trees(self):
    election_tree = etree.fromstring("<ElectionReport/>")
    schema_tree = etree.fromstring("<schema/>")

    validator = base.DateRule(election_tree, schema_tree)

    self.assertIs(election_tree, validator.election_tree)
    self.assertIs(schema_tree, validator.schema_tree)
    self.assertEmpty(validator.error_log)

  # reset_instance_vars test
  def test_reset_instance_vars_resets_state(self):
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
        validator_with_values.start_elem, fresh_validator.start_elem
    )
    self.assertNotEqual(
        validator_with_values.start_date, fresh_validator.start_date
    )
    self.assertNotEqual(
        validator_with_values.end_elem, fresh_validator.end_elem
    )
    self.assertNotEqual(
        validator_with_values.end_date, fresh_validator.end_date
    )
    self.assertNotEqual(
        validator_with_values.error_log, fresh_validator.error_log
    )

    validator_with_values.reset_instance_vars()

    self.assertEqual(
        validator_with_values.start_elem, fresh_validator.start_elem
    )
    self.assertEqual(
        validator_with_values.start_date, fresh_validator.start_date
    )
    self.assertEqual(validator_with_values.end_elem, fresh_validator.end_elem)
    self.assertEqual(validator_with_values.end_date, fresh_validator.end_date)
    self.assertEqual(validator_with_values.error_log, fresh_validator.error_log)

  # gather_dates tests
  def test_gather_dates_sets_start_and_end_dates(self):
    start_date = "2021-12-20"
    end_date = "2021-12-22"
    election_string = self.election_string.format(start_date, end_date)
    election = etree.fromstring(election_string)
    self.date_validator.gather_dates(election)
    self.assertEqual(self.date_validator.start_date.day, 20)
    self.assertEqual(self.date_validator.start_date.month, 12)
    self.assertEqual(self.date_validator.start_date.year, 2021)
    self.assertEqual(self.date_validator.end_date.month, 12)
    self.assertEqual(self.date_validator.end_date.year, 2021)
    self.assertEqual(self.date_validator.end_date.day, 22)

  def test_invalid_date_formats_raises_error(self):
    start_date_invalid = "2022-01-32"
    end_date_invalid = "05-29"

    election_string = self.election_string.format(
        start_date_invalid, end_date_invalid
    )
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionError) as context:
      self.date_validator.gather_dates(election)
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The StartDate text should be of the formats: yyyy-mm-dd, or yyyy,"
        " or yyyy-mm",
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "The EndDate text should be of the formats: "
        "yyyy-mm-dd, or yyyy, or yyyy-mm",
    )

  def test_gather_dates_missing_elements_remains_none(self):
    election_string = "<Election></Election>"
    self.date_validator.gather_dates(etree.fromstring(election_string))
    self.assertIsNone(None, self.date_validator.start_date)
    self.assertIsNone(None, self.date_validator.start_elem)
    self.assertIsNone(None, self.date_validator.end_date)
    self.assertIsNone(None, self.date_validator.end_elem)

  # check_for_date_not_in_past tests
  def test_future_date_does_not_log_error(self):
    tomorrow = self.today + datetime.timedelta(days=1)
    future_date = base.PartialDate(tomorrow.year, tomorrow.month, tomorrow.day)
    self.date_validator.check_for_date_not_in_past(future_date, None)

    self.assertEmpty(self.date_validator.error_log)

  def test_past_date_logs_error(self):
    past_date = base.PartialDate(2012, 1)
    date_elem = etree.fromstring("<StartDate>2012-01</StartDate>")
    self.date_validator.check_for_date_not_in_past(past_date, date_elem)
    self.assertLen(self.date_validator.error_log, 1)
    self.assertEqual(
        self.date_validator.error_log[0].message,
        "The date 2012-01 is in the past.",
    )

  # check_for_date_in_past tests
  @freezegun.freeze_time("2023-01-01")
  def test_past_date_does_not_log_error(self):
    date_elem = etree.fromstring("<DateOfBirth>1975-01-01</DateOfBirth>")
    date = base.PartialDate.init_partial_date(date_elem.text)

    self.date_validator.check_for_date_in_past(date, date_elem)
    self.assertEmpty(self.date_validator.error_log)

  @freezegun.freeze_time("2023-01-01")
  def test_future_date_logs_error(self):
    date_elem = etree.fromstring("<DateOfBirth>2100-01-01</DateOfBirth>")
    date = base.PartialDate.init_partial_date(date_elem.text)

    self.date_validator.check_for_date_in_past(date, date_elem)
    self.assertLen(self.date_validator.error_log, 1)
    self.assertEqual(
        self.date_validator.error_log[0].message,
        "The date 2100-01-01 is not in the past.",
    )

  # check_end_after_start tests
  def test_end_after_start_does_not_log_error(self):
    self.date_validator.start_date = self.today_partial_date
    self.date_validator.end_date = self.date_validator.start_date
    self.date_validator.end_date.day = self.date_validator.start_date.day + 1
    self.date_validator.check_end_after_start()

    self.assertEmpty(self.date_validator.error_log)

  def test_end_before_start_logs_error(self):
    start_date_year_month = "2021-09"
    end_date_year_month = "2021-01"
    election_string = self.election_string.format(
        start_date_year_month, end_date_year_month
    )
    election = etree.fromstring(election_string)
    self.date_validator.gather_dates(election)
    self.date_validator.check_end_after_start()
    self.assertLen(self.date_validator.error_log, 1)
    self.assertIn(
        "The end date must be the same or after the start date.",
        self.date_validator.error_log[0].message,
    )


class PartialDateTest(absltest.TestCase):

  def test_init_year_sets_year(self):
    partial_date_validator = base.PartialDate.init_partial_date("2021")
    self.assertEqual(partial_date_validator.year, 2021)
    self.assertIsNone(partial_date_validator.month)
    self.assertIsNone(partial_date_validator.day)

  def test_init_year_month_sets_year_and_month(self):
    partial_date_validator = base.PartialDate.init_partial_date("2021-04")
    self.assertEqual(partial_date_validator.year, 2021)
    self.assertEqual(partial_date_validator.month, 4)
    self.assertIsNone(partial_date_validator.day)

  def test_init_full_date_sets_all_attributes(self):
    partial_date_validator = base.PartialDate.init_partial_date("2021-10-19")
    self.assertEqual(partial_date_validator.day, 19)
    self.assertEqual(partial_date_validator.month, 10)
    self.assertEqual(partial_date_validator.year, 2021)

  def test_init_invalid_day_returns_none(self):
    partial_date = base.PartialDate.init_partial_date("2022-2-30")
    self.assertIsNone(partial_date)

  def test_less_than_year_only_returns_true(self):
    self.assertLess(base.PartialDate(2020), base.PartialDate(2021))

  def test_less_than_year_month_returns_true(self):
    self.assertLess(base.PartialDate(2020, 1), base.PartialDate(2020, 2))

  def test_less_than_complete_date_returns_true(self):
    self.assertLess(base.PartialDate(2020, 1, 1), base.PartialDate(2020, 1, 2))

  def test_greater_than_year_only_returns_true(self):
    self.assertGreater(base.PartialDate(2021), base.PartialDate(2020))

  def test_greater_than_year_month_returns_true(self):
    self.assertGreater(base.PartialDate(2020, 2), base.PartialDate(2020, 1))

  def test_greater_than_complete_date_returns_true(self):
    self.assertGreater(
        base.PartialDate(2020, 1, 2), base.PartialDate(2020, 1, 1)
    )

  def test_equal_to_year_only_returns_true(self):
    self.assertEqual(base.PartialDate(2020), base.PartialDate(2020))

  def test_equal_to_year_month_returns_true(self):
    self.assertEqual(base.PartialDate(2020, 1), base.PartialDate(2020, 1))

  def test_equal_to_complete_date_returns_true(self):
    self.assertEqual(base.PartialDate(2020, 1, 1), base.PartialDate(2020, 1, 1))

  def test_is_older_than_returns_difference_in_months(self):
    partial_date_older = base.PartialDate(2021, 3, 12)
    partial_date_younger = base.PartialDate(2021, 11, 2)
    self.assertEqual(partial_date_older.is_older_than(partial_date_younger), 8)

  def test_year_only_is_older_than_complete_date_returns_difference_in_years(
      self,
  ):
    partial_date_year = base.PartialDate(2020, None, None)
    complete_date = base.PartialDate(2021, 12, 21)
    self.assertEqual(partial_date_year.is_older_than(complete_date), 1)

  def test_complete_date_is_older_than_partial_date_returns_difference_in_months(
      self,
  ):
    complete_start_date = base.PartialDate(2021, 6, 30)
    partial_end_date = base.PartialDate(2021, 11, None)
    self.assertEqual(complete_start_date.is_older_than(partial_end_date), 5)

  def test_year_only_is_older_than_partial_date_returns_difference_in_years(
      self,
  ):
    year_only_start_date = base.PartialDate(2020, None, None)
    partial_end_date = base.PartialDate(2021, 11, None)
    self.assertEqual(year_only_start_date.is_older_than(partial_end_date), 1)

  def test_is_only_year_date_returns_true(self):
    partial_date_year = base.PartialDate(2021, None, None)
    self.assertTrue(partial_date_year.is_only_year_date())

  def test_is_only_year_date_complete_date_returns_false(self):
    complete_date = base.PartialDate(2021, 11, 2)
    self.assertFalse(complete_date.is_only_year_date())

  def test_is_only_year_date_year_month_returns_false(self):
    partial_date_year_month = base.PartialDate(2021, 12, None)
    self.assertFalse(partial_date_year_month.is_only_year_date())

  def test_is_month_date_returns_true(self):
    partial_date_year_month = base.PartialDate(2021, 11, None)
    self.assertTrue(partial_date_year_month.is_month_date())

  def test_is_month_date_year_only_returns_false(self):
    partial_date_year = base.PartialDate(2021, None, None)
    self.assertFalse(partial_date_year.is_month_date())

  def test_is_month_date_complete_date_returns_false(self):
    partial_date_day = base.PartialDate(2021, 11, 2)
    self.assertFalse(partial_date_day.is_month_date())

  def test_init_invalid_month_returns_none(self):
    partial_date = base.PartialDate.init_partial_date("2022-32-24")
    self.assertIsNone(partial_date)

  def test_init_invalid_year_returns_none(self):
    partial_date = base.PartialDate.init_partial_date("20313")
    self.assertIsNone(partial_date)

  def test_init_year_month_with_month_above_twelve_returns_none(self):
    partial_date = base.PartialDate.init_partial_date("2022-13")

    self.assertIsNone(partial_date)

  def test_init_year_month_with_december_returns_date(self):
    partial_date = base.PartialDate.init_partial_date("2022-12")

    self.assertEqual(partial_date.month, 12)

  def test_str_year_only_returns_year(self):
    partial_date = base.PartialDate(2020)

    self.assertEqual(str(partial_date), "2020")

  def test_str_year_month_returns_padded_month(self):
    partial_date = base.PartialDate(2020, 5)

    self.assertEqual(str(partial_date), "2020-05")

  def test_str_complete_date_returns_padded_date(self):
    partial_date = base.PartialDate(2020, 5, 7)

    self.assertEqual(str(partial_date), "2020-05-07")

  def test_str_undefined_date_returns_not_defined(self):
    partial_date = base.PartialDate()

    self.assertEqual(str(partial_date), "Not defined")

  def test_year_only_is_older_than_complete_date_in_same_year_returns_zero(
      self,
  ):
    year_only_date = base.PartialDate(2021)
    complete_date = base.PartialDate(2021, 6, 30)

    self.assertEqual(year_only_date.is_older_than(complete_date), 0)
    self.assertEqual(complete_date.is_older_than(year_only_date), 0)

  def test_month_date_is_older_than_complete_date_in_same_month_returns_zero(
      self,
  ):
    month_date = base.PartialDate(2021, 6)
    complete_date = base.PartialDate(2021, 6, 30)

    self.assertEqual(month_date.is_older_than(complete_date), 0)
    self.assertEqual(complete_date.is_older_than(month_date), 0)


class MissingFieldRuleTest(absltest.TestCase):

  def setUp(self):
    super(MissingFieldRuleTest, self).setUp()
    self.validator = base.MissingFieldRule(None, None)

  # get_severity test
  def test_get_severity_raises_not_implemented_error(self):
    with self.assertRaises(NotImplementedError):
      self.validator.get_severity()

  # element_field_mapping test
  def test_element_field_mapping_raises_not_implemented_error(self):
    with self.assertRaises(NotImplementedError):
      self.validator.element_field_mapping()

  # setup tests
  def test_setup_info_severity_sets_election_info(self):
    self.validator.get_severity = MagicMock(return_value=0)
    self.validator.setup()
    self.assertEqual(self.validator.exception, loggers.ElectionInfo)

  def test_setup_warning_severity_sets_election_warning(self):
    self.validator.get_severity = MagicMock(return_value=1)
    self.validator.setup()
    self.assertEqual(self.validator.exception, loggers.ElectionWarning)

  def test_setup_error_severity_sets_election_error(self):
    self.validator.get_severity = MagicMock(return_value=2)
    self.validator.setup()
    self.assertEqual(self.validator.exception, loggers.ElectionError)

  def test_setup_invalid_severity_raises_exception(self):
    self.validator.get_severity = MagicMock(return_value=-1)
    with self.assertRaises(Exception):
      self.validator.setup()

    self.validator.get_severity = MagicMock(return_value=-3)
    with self.assertRaises(Exception):
      self.validator.setup()

  # elements test
  def test_elements_returns_mapping_keys(self):
    elements = {
        "Person": ["PartyId", "CandidateId"],
        "Office": ["Term//StartDate"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    registered_elements = self.validator.elements()

    for registered_element in registered_elements:
      self.assertIn(registered_element, elements.keys())

  # check tests
  def test_required_field_present_succeeds(self):
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
  def test_missing_field_fails(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_missing_field_warns(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionWarning

    with self.assertRaises(loggers.ElectionWarning) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_missing_field_raises_info(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionInfo

    with self.assertRaises(loggers.ElectionInfo) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_empty_field_fails(self):
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

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_whitespace_field_fails(self):
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

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )

  def test_multiple_missing_fields_fails(self):
    person = """
      <Person objectId="123">
      </Person>
    """
    elements = {
        "Person": ["FullName//Text", "PartyId"],
    }
    self.validator.element_field_mapping = MagicMock(return_value=elements)
    self.validator.exception = loggers.ElectionError

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(person))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "The element Person is missing field FullName//Text.",
    )
    self.assertEqual(
        context.exception.log_entry[0].elements[0].get("objectId"), "123"
    )
    self.assertEqual(
        context.exception.log_entry[1].message,
        "The element Person is missing field PartyId.",
    )
    self.assertEqual(
        context.exception.log_entry[1].elements[0].get("objectId"), "123"
    )


class RulesRegistryTest(absltest.TestCase):

  def setUp(self):
    super(RulesRegistryTest, self).setUp()
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, [_TEST_US_OCD_ID_1]
    )
    self.registry = base.RulesRegistry(
        "test.xml", "schema.xsd", [], [], ocd_id_validator
    )
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

  def test_count_stats_prints_expected_output(self):
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
        "Contest": 3,
    }

    # Value: (found_in_n_entities, missing_in_m_entities).
    expected_attr_counts = {
        "ComposingGpUnitIds": (3, 0),
        "Color": (1, 1),
        "BallotSelection": (1, 2),
        "InternationalizedAbbreviation": (1, 1),
    }

    for entity, count in expected_entity_counts.items():
      self.assertIn("{0} (Total: {1})".format(entity, count), output)

    for attr, stat in expected_attr_counts.items():
      count, missing_in = stat
      self.assertIn(
          "{:<30s}{:^8s}{:>15s}".format(attr, str(count), str(missing_in)),
          output,
      )

  def _capture_output(
      self, function: Callable[..., object], *args: object
  ) -> str:
    """Returns everything printed to stdout while calling `function`."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      function(*args)
    return output.getvalue()

  def test_count_stats_prints_header(self):
    output = self._capture_output(self.registry.count_stats)

    self.assertTrue(
        output.startswith("\n     Entity and Attribute Counts:\n"), output
    )

  def test_count_stats_skips_entities_missing_from_feed(self):
    self.registry.election_tree = etree.fromstring("""
      <ElectionReport>
        <PartyCollection>
          <Party objectId="par-fake"/>
        </PartyCollection>
      </ElectionReport>
    """)

    output = self._capture_output(self.registry.count_stats)

    self.assertIn("Party (Total: 1)", output)
    self.assertNotIn("Office (Total", output)
    self.assertNotIn("Person (Total", output)

  def test_count_stats_without_election_tree_prints_nothing(self):
    registry = base.RulesRegistry("test.xml", "schema.xsd", [], {}, None)

    output = self._capture_output(registry.count_stats)

    self.assertEmpty(output)

  def test_register_rules_applies_rule_options(self):
    rule_options = {
        "_FakeOptionRule": [base.RuleOption("fake_option", "fake-value")]
    }
    registry = base.RulesRegistry(
        "test.xml", "schema.xsd", [_FakeOptionRule], rule_options, None
    )
    registry.schema_tree = None

    registry.register_rules()

    self.assertEqual(registry.registry["Party"][0].fake_option, "fake-value")

  def test_register_rules_without_rule_options_keeps_defaults(self):
    registry = base.RulesRegistry(
        "test.xml", "schema.xsd", [_FakeOptionRule], {}, None
    )
    registry.schema_tree = None

    registry.register_rules()

    self.assertEqual(registry.registry["Party"][0].fake_option, "default-value")

  def test_register_rules_registers_every_rule_for_shared_element(self):
    registry = base.RulesRegistry(
        "test.xml", "schema.xsd", [_FakeOptionRule, _FakePartyRule], {}, None
    )
    registry.schema_tree = None

    registry.register_rules()

    registered_rule_types = [type(rule) for rule in registry.registry["Party"]]
    self.assertEqual(registered_rule_types, [_FakeOptionRule, _FakePartyRule])

  def test_check_rules_records_tree_and_element_rule_exceptions(self):
    election_file = self.create_tempfile(content="""<ElectionReport>
  <PartyCollection>
    <Party objectId="par-fake-1"/>
    <Party objectId="par-fake-2"/>
  </PartyCollection>
</ElectionReport>""").full_path
    schema_file = self.create_tempfile(content="<schema/>").full_path
    registry = base.RulesRegistry(
        election_file, schema_file, [_FakeTreeRule, _FakePartyRule], {}, None
    )

    registry.check_rules()

    all_exceptions = registry.exceptions_wrapper.get_all_exceptions()
    warning_messages = [
        log_entry.message
        for log_entry in all_exceptions[loggers.ElectionWarning][
            "_FakeTreeRule"
        ]
    ]
    error_messages = [
        log_entry.message
        for log_entry in all_exceptions[loggers.ElectionError]["_FakePartyRule"]
    ]
    self.assertEqual(warning_messages, ["Fake tree warning."])
    self.assertEqual(
        error_messages,
        ["Fake error for par-fake-1.", "Fake error for par-fake-2."],
    )

  def test_print_exceptions_prints_recorded_exceptions(self):
    self.registry.exceptions_wrapper.exception_handler(
        loggers.ElectionFatal.from_message("Fake fatal."), "FakeRule"
    )

    output = self._capture_output(self.registry.print_exceptions, 3, True)

    self.assertEqual(
        output,
        "     1 Fatal message found\n"
        "         1 FakeRule Fatal message\n"
        "                  * Fake fatal.\n",
    )

  def test_multiple_instances_restrict_validation_to_configured_ocd_ids(self):
    us_ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, [_TEST_US_OCD_ID_1, _TEST_US_OCD_ID_2]
    )
    ca_ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, [_TEST_CA_OCD_ID_1, _TEST_CA_OCD_ID_2]
    )

    self.assertFalse(us_ocd_id_validator.is_valid_ocd_id(_TEST_CA_OCD_ID_1))
    self.assertFalse(ca_ocd_id_validator.is_valid_ocd_id(_TEST_US_OCD_ID_1))
    self.assertTrue(us_ocd_id_validator.is_valid_ocd_id(_TEST_US_OCD_ID_2))
    self.assertTrue(ca_ocd_id_validator.is_valid_ocd_id(_TEST_CA_OCD_ID_2))

  def test_get_all_exceptions_returns_recorded_exceptions(self):
    election_file = self.create_tempfile(content="""<ElectionReport>
  <PartyCollection>
    <Party objectId="par-fake-1"/>
  </PartyCollection>
</ElectionReport>""").full_path
    schema_file = self.create_tempfile(content="<schema/>").full_path
    registry = base.RulesRegistry(
        election_file, schema_file, [_FakePartyRule], {}, None
    )
    registry.check_rules()

    all_exceptions = registry.get_all_exceptions()

    error_messages = [
        log_entry.message
        for log_entry in all_exceptions[loggers.ElectionError]["_FakePartyRule"]
    ]
    self.assertEqual(error_messages, ["Fake error for par-fake-1."])


class BaseEntityStatsTest(absltest.TestCase):

  def test_str_prints_attribute_table_sorted_by_count(self):
    party_stats = stats.Party(3)
    for _ in range(3):
      party_stats.increment_attribute("Name", 1)
    party_stats.increment_attribute("Color", 2)
    party_stats.increment_attribute("Abbreviation", 0)
    party_stats.increment_attribute("UnknownAttribute", 1)

    output = str(party_stats)

    separator = " " * 8 + "-" * 65
    self.assertEqual(
        "\n".join([
            "\n" + separator,
            (
                "        Party (Total: 3)               | # with attribute |"
                " # missing attribute"
            ),
            separator,
            "        Name                             3                  0",
            "        Color                            1                  2",
            "        Abbreviation                     0                  3",
            "        ExternalIdentifiers              0                  3",
            "        InternationalizedAbbreviation    0                  3",
        ]),
        output,
    )


if __name__ == "__main__":
  absltest.main()

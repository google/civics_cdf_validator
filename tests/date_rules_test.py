# -*- coding: utf-8 -*-
"""Unit test for date_rules.py."""

import datetime
from absl.testing import absltest
from civics_cdf_validator import date_rules
from civics_cdf_validator import loggers
from lxml import etree
from mock import MagicMock


class DateRuleTest(absltest.TestCase):

  def setUp(self):
    super(DateRuleTest, self).setUp()
    self.date_validator = date_rules.DateRule(None, None)
    self.today = datetime.datetime.now().date()
    self.today_partial_date = date_rules.PartialDate(self.today.year,
                                                     self.today.month,
                                                     self.today.day)

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

    validator_with_values = date_rules.DateRule(None, None)
    validator_with_values.start_elem = start_elem
    validator_with_values.start_date = start_date
    validator_with_values.end_elem = end_elem
    validator_with_values.end_date = end_date
    validator_with_values.error_log = ["This is no longer empty"]

    fresh_validator = date_rules.DateRule(None, None)

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
    start_date = "2021-12-20"
    end_date = "2021-12-22"
    election_string = self.election_string.format(
        start_date, end_date)
    election = etree.fromstring(election_string)
    self.date_validator.gather_dates(election)
    self.assertEqual(20, self.date_validator.start_date.day)
    self.assertEqual(12, self.date_validator.start_date.month)
    self.assertEqual(2021, self.date_validator.start_date.year)
    self.assertEqual(12, self.date_validator.end_date.month)
    self.assertEqual(2021, self.date_validator.end_date.year)
    self.assertEqual(22, self.date_validator.end_date.day)

  def testRaisesErrorForInvalidDateFormatsInvalidDay(self):
    start_date_invalid = "2022-01-32"
    end_date_invalid = "05-29"

    election_string = self.election_string.format(
        start_date_invalid, end_date_invalid)
    election = etree.fromstring(election_string)
    with self.assertRaises(loggers.ElectionError) as ee:
      self.date_validator.gather_dates(election)
    self.assertEqual(
        "The StartDate text should be of the formats: yyyy-mm-dd, or yyyy,"
        " or yyyy-mm", ee.exception.log_entry[0].message)
    self.assertEqual(
        "The EndDate text should be of the formats: "
        "yyyy-mm-dd, or yyyy, or yyyy-mm", ee.exception.log_entry[1].message)

  def testDoesNotAssignDatesIfElementsNotFound(self):
    election_string = "<Election></Election>"
    self.date_validator.gather_dates(etree.fromstring(election_string))
    self.assertIsNone(None, self.date_validator.start_date)
    self.assertIsNone(None, self.date_validator.start_elem)
    self.assertIsNone(None, self.date_validator.end_date)
    self.assertIsNone(None, self.date_validator.end_elem)

  # check_for_date_not_in_past tests
  def testProvidedDateIsNotInThePast(self):
    tomorrow = self.today + datetime.timedelta(days=1)
    future_date = date_rules.PartialDate(tomorrow.year, tomorrow.month,
                                         tomorrow.day)
    self.date_validator.check_for_date_not_in_past(future_date, None)

    self.assertEmpty(self.date_validator.error_log)

  def testAddsToErrorLogIfDateInPast(self):
    past_date = date_rules.PartialDate(2012, 1)
    date_elem = etree.fromstring("<StartDate>2012-01</StartDate>")
    self.date_validator.check_for_date_not_in_past(past_date, date_elem)
    self.assertLen(self.date_validator.error_log, 1)
    self.assertEqual("The date 2012-01 is in the past.",
                     self.date_validator.error_log[0].message)

  # check_end_after_start tests
  def testEndDateComesAfterStartDate(self):
    self.date_validator.start_date = self.today_partial_date
    self.date_validator.end_date = self.date_validator.start_date
    self.date_validator.end_date.day = self.date_validator.start_date.day + 1
    self.date_validator.check_end_after_start()

    self.assertEmpty(self.date_validator.error_log)

  def testAddsToErrorLogIfEndDateMonthIsBeforeStartDate(self):
    start_date_year_month = "2021-09"
    end_date_year_month = "2021-01"
    election_string = self.election_string.format(start_date_year_month,
                                                  end_date_year_month)
    election = etree.fromstring(election_string)
    self.date_validator.gather_dates(election)
    self.date_validator.check_end_after_start()
    self.assertLen(self.date_validator.error_log, 1)
    self.assertIn(
        "The end date must be the same or after the start date.",
        self.date_validator.error_log[0].message)

  def testEndDateNoneForEndDateAfterStartDate(self):
    test_string = """
    <Election>
      <StartDate>2022-01-01</StartDate>
    </Election>
    """
    end_date_mock = MagicMock(return_value=None)
    self.date_validator.check_end_after_start = end_date_mock
    election = etree.fromstring(test_string)
    self.date_validator.gather_dates(election)
    self.assertIsNone(self.date_validator.end_date)
    actual_return = self.date_validator.check_end_after_start()
    self.assertIsNone(actual_return)

  def testStartDateNoneForEndDateAfterStartDate(self):
    test_string = """
    <Election>
      <EndDate>2022-01-01</EndDate>
    </Election>
    """
    start_date_mock = MagicMock(return_value=None)
    self.date_validator.check_end_after_start = start_date_mock
    election = etree.fromstring(test_string)
    self.date_validator.gather_dates(election)
    self.assertIsNone(self.date_validator.start_date)
    actual_return = self.date_validator.check_end_after_start()
    self.assertIsNone(actual_return)


class PartialDateTest(absltest.TestCase):

  def testShouldCheckYear(self):
    partial_date_validator = date_rules.PartialDate.init_partial_date(
        "2021")
    self.assertEqual(2021, partial_date_validator.year)
    self.assertIsNone(partial_date_validator.month)
    self.assertIsNone(partial_date_validator.day)

  def testShouldCheckYearMonth(self):
    partial_date_validator = date_rules.PartialDate.init_partial_date(
        "2021-04")
    self.assertEqual(2021, partial_date_validator.year)
    self.assertEqual(4, partial_date_validator.month)
    self.assertIsNone(partial_date_validator.day)

  def testShouldCheckDayMonthYear(self):
    partial_date_validator = date_rules.PartialDate.init_partial_date(
        "2021-10-19")
    self.assertEqual(19, partial_date_validator.day)
    self.assertEqual(10, partial_date_validator.month)
    self.assertEqual(2021, partial_date_validator.year)

  def testReturnsNoneInvalidDay(self):
    partial_date = date_rules.PartialDate.init_partial_date(
        "2022-2-30")
    self.assertIsNone(partial_date)

  def testShouldCheckIsOlderThan(self):
    partial_date_older = date_rules.PartialDate(2021, 3, 12)
    partial_date_younger = date_rules.PartialDate(2021, 11, 2)
    self.assertEqual(
        8,
        partial_date_older.is_older_than(partial_date_younger))

  def testShouldCheckYearDateIsOlderThanCompleteDate(self):
    partial_date_year = date_rules.PartialDate(2020, None, None)
    complete_date = date_rules.PartialDate(2021, 12, 21)
    self.assertEqual(1, partial_date_year.is_older_than(complete_date))

  def testShouldCheckCompleteDateIsOlderThanYearDate(self):
    partial_date_year = date_rules.PartialDate(2020, None, None)
    complete_date = date_rules.PartialDate(2019, 12, 21)
    self.assertEqual(1, complete_date.is_older_than(partial_date_year))

  def testShouldCheckCompleteDateIsOlderThanCompleteOtherDate(self):
    partial_date_year = date_rules.PartialDate(2020, None, None)
    complete_date = date_rules.PartialDate(2020, 12, 21)
    self.assertEqual(
        0, date_rules.PartialDate.is_older_than(partial_date_year,
                                                complete_date))

  def testShouldCheckSameMonthButDifferentDay(self):
    complete_year_day_late = date_rules.PartialDate(2021, 9, 20)
    complete_year_day_early = date_rules.PartialDate(2021, 9, 15)
    self.assertEqual(
        5, complete_year_day_early.is_older_than(complete_year_day_late))

  def testShouldCheckSameYearButDifferentMonth(self):
    complete_date = date_rules.PartialDate(2021, 9, 20)
    partial_month_date = date_rules.PartialDate(2021, 8, None)
    self.assertEqual(
        1, partial_month_date.is_older_than(complete_date))

  def testShouldCheckDifferentYearForMonthDate(self):
    partial_month_date_late = date_rules.PartialDate(2021, 9, None)
    partial_month_date_early = date_rules.PartialDate(2020, 8, None)
    self.assertEqual(
        1, partial_month_date_early.is_older_than(partial_month_date_late))

  def testShouldCheckIsOnlyYearTrue(self):
    partial_date_year = date_rules.PartialDate(2021, None, None)
    self.assertTrue(partial_date_year.is_only_year_date())

  def testShouldCheckIsOnlyYearFalseForCompleteDate(self):
    complete_date = date_rules.PartialDate(2021, 11, 2)
    self.assertFalse(complete_date.is_only_year_date())

  def testShouldCheckIsOnlyYearFalseForYearMonth(self):
    partial_date_year_month = date_rules.PartialDate(2021, 12, None)
    self.assertFalse(partial_date_year_month.is_only_year_date())

  def testShouldCheckIsOnlyYearMonthTrue(self):
    partial_date_year_month = date_rules.PartialDate(2021, 11, None)
    self.assertTrue(
        partial_date_year_month.is_month_date())

  def testShouldCheckIsOnlyYearMonthFalseYear(self):
    partial_date_year = date_rules.PartialDate(2021, None, None)
    self.assertFalse(partial_date_year.is_month_date())

  def testShouldCheckIsOnlyYearMonthFalseDay(self):
    partial_date_day = date_rules.PartialDate(2021, 11, 2)
    self.assertFalse(partial_date_day.is_month_date())

  def testReturnsNoneInvalidMonth(self):
    partial_date = date_rules.PartialDate.init_partial_date("2022-32-24")
    self.assertIsNone(partial_date)

  def testReturnsNoneInvalidYear(self):
    partial_date = date_rules.PartialDate.init_partial_date("20313")
    self.assertIsNone(partial_date)

if __name__ == "__main__":
  absltest.main()

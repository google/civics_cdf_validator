"""Copyright 2020 Google Inc.

All Rights Reserved.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import print_function

import datetime
import re
from civics_cdf_validator import base
from civics_cdf_validator import loggers


class DateRule(base.BaseRule):
  """Base rule used for date validations.

  When validating dates, this rule can be used to gather start and
  end date values.
  """

  def __init__(self, election_tree, schema_file):
    super(DateRule, self).__init__(election_tree, schema_file)
    self.start_elem = None
    self.start_date = None
    self.end_elem = None
    self.end_date = None
    self.error_log = []

  def reset_instance_vars(self):
    """Reset instance variables to initial state.

    Due to ordered procedure of validator, instance vars created in init
    are not getting reset when same rule is run on different elements.
    """
    self.start_elem = None
    self.start_date = None
    self.end_elem = None
    self.end_date = None
    self.error_log = []

  def gather_dates(self, element):
    """Gather StartDate and EndDate values for the provided element.

    An election element should have a start and end date in the desired format.
    These dates should be extracted and set as instance variables to be used
    in validation checks.

    Args:
      element: A parent element that contains StartDate and EndDate children.

    Raises:
      ElectionError: dates need to be properly formatted.
    """
    error_log = []

    self.start_elem = element.find("StartDate")
    if self.start_elem is not None and self.start_elem.text is not None:
      self.start_date = PartialDate.init_partial_date(self.start_elem.text)
      if self.start_date is None:
        error_message = (
            "The StartDate text should be of the formats: yyyy-mm-dd, or yyyy,"
            " or yyyy-mm")
        error_log.append(loggers.LogEntry(error_message, [self.start_elem]))
    self.end_elem = element.find("EndDate")
    if self.end_elem is not None and self.end_elem.text is not None:
      self.end_date = PartialDate.init_partial_date(self.end_elem.text)
      if self.end_date is None:
        error_message = ("The EndDate text should be of the formats: "
                         "yyyy-mm-dd, or yyyy, or yyyy-mm")
        error_log.append(loggers.LogEntry(error_message, [self.end_elem]))

    if error_log:
      raise loggers.ElectionError(error_log)

  def check_for_date_not_in_past(self, date, date_elem):
    """Check if given date is not in past and add an error message to the error log if the date is in past."""
    if date is not None:
      today = datetime.datetime.now()
      today_partial_date = PartialDate(today.year, today.month, today.day)
      delta = date.is_older_than(today_partial_date)
      if delta > 0:
        error_message = """The date {} is in the past.""".format(date)
        self.error_log.append(loggers.LogEntry(error_message, [date_elem]))

  def check_end_after_start(self):
    """Checks if EndDate is after StartDate and add an error message to the error log if the EndDate is before StartDate."""
    if self.start_date is not None and self.end_date is not None:
      start_end_delta = self.start_date.is_older_than(self.end_date)
      if start_end_delta < 0:
        error_message = """The dates (start: {}, end: {}) are invalid.
      The end date must be the same or after the start date.""".format(
          self.start_date, self.end_date)
        self.error_log.append(loggers.LogEntry(error_message, [self.end_elem]))


class PartialDate():
  """Check for PartialDate."""

  REGEX_PATTERN = re.compile(
      r"^(?P<year>[0-9]{4})(?:-(?P<month>[0-9]{2}))?(?:-(?P<day>[0-9]{2}))?$")

  def __init__(self, year=None, month=None, day=None):
    self.year = year
    self.month = month
    self.day = day

  def __str__(self):
    if self.is_only_year_date():
      return "%s" % self.year
    elif self.is_month_date():
      return "%s-%s" %(self.year, str(self.month).zfill(2))
    elif self.is_complete_date():
      return "%s-%s-%s" % (self.year, str(self.month).zfill(2), str(
          self.day).zfill(2))
    else:
      return "Not defined"

  @classmethod
  def init_partial_date(cls, date_string):
    """Initializing partial date."""
    match_object = re.match(cls.REGEX_PATTERN, date_string)
    if match_object is None:
      return None
    else:
      partial_date_year = int(match_object.groupdict().get(
          "year")) if match_object.groupdict().get("year") is not None else None
      partial_date_month = int(
          match_object.groupdict().get("month")
      ) if match_object.groupdict().get("month") is not None else None
      if partial_date_month is not None and partial_date_month > 12:
        return None
      partial_date_day = int(match_object.groupdict().get(
          "day")) if match_object.groupdict().get("day") is not None else None
      partial_date = PartialDate(partial_date_year, partial_date_month,
                                 partial_date_day)
      if partial_date.is_complete_date():
        try:
          datetime.datetime(partial_date_year, partial_date_month,
                            partial_date_day)
        except ValueError:
          return None
      return partial_date

  def is_older_than(self, other_date):
    """Compares 2 dates/partial dates.

    Args:
      other_date: date to be compared.

    Returns:
      The difference between the years if the given dates only contains a year.
      The difference between the years if the given dates contains year and
      month, then when the years of both dates aren't same.
      The difference between the months, if the years of both dates are same.
      The difference between the days if the given dates contain complete day,
      and if the year and month of both dates are the same.

    """

    if self.is_only_year_date() or other_date.is_only_year_date():
      return other_date.year - self.year
    elif self.is_month_date() or self.is_month_date():
      if other_date.year - self.year != 0:
        return other_date.year - self.year
      return other_date.month - self.month
    else:
      if other_date.year - self.year != 0:
        return other_date.year - self.year
      elif other_date.month - self.month != 0:
        return other_date.month - self.month
      return other_date.day - self.day

  def is_only_year_date(self):
    return self.year is not None and self.month is None and self.day is None

  def is_month_date(self):
    return self.year is not None and self.month is not None and self.day is None

  def is_complete_date(self):
    return self.year is not None and self.month is not None and self.day is not None

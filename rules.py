# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Validation rules for the CDF XML validator."""

from __future__ import print_function

import datetime
import enum

from botocore import utils as botocore_utils
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import committee_rules
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import election_dates_rules
from civics_cdf_validator.rulesets import election_rules
from civics_cdf_validator.rulesets import officeholder_rules
from civics_cdf_validator.rulesets import rule_util
from civics_cdf_validator.rulesets import voter_information_rules
import dateutil
from frozendict import frozendict


_VALID_FEED_LONGEVITY_BY_FEED_TYPE = frozendict({
    "committee": ["evergreen"],
    "election-dates": ["evergreen"],
    "election-results": ["limited"],
    "officeholder": ["evergreen"],
    "pre-election": ["limited", "yearly"],
})


class FeedTypeHasValidFeedLongevity(base.BaseRule):
  """Feeds types should have valid corresponding FeedLongevity."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_type_element = element.find("FeedType")
    feed_longevity_element = element.find("FeedLongevity")
    if rule_util.element_has_text(
        feed_type_element
    ) and rule_util.element_has_text(feed_longevity_element):
      feed_type = feed_type_element.text.lower().replace("_", "-")
      feed_longevity = feed_longevity_element.text.lower().replace("_", "-")
      if (
          feed_type in _VALID_FEED_LONGEVITY_BY_FEED_TYPE
          and feed_longevity
          not in _VALID_FEED_LONGEVITY_BY_FEED_TYPE[feed_type]
      ):
        raise loggers.ElectionError.from_message(
            "Feed type {} has invalid feed longevity {}. Valid feed"
            " longevities for this type are {}".format(
                feed_type,
                feed_longevity,
                _VALID_FEED_LONGEVITY_BY_FEED_TYPE[feed_type],
            ),
            [element],
        )


class FeedIdsAreUnique(base.BaseRule):
  """FeedId should be unique."""

  def elements(self):
    return ["FeedCollection"]

  def check(self, element):
    feed_ids = set()
    error_log = []
    for feed_element in element.findall("Feed"):
      if rule_util.element_has_text(feed_element.find("FeedId")):
        feed_id = feed_element.find("FeedId").text
        if feed_id in feed_ids:
          msg = (
              "FeedId {} appears multiple times in the metadata feed. Feed ids"
              " must be unique.".format(feed_id)
          )
          error_log.append(
              loggers.LogEntry(
                  msg,
                  [feed_element],
              )
          )
        feed_ids.add(feed_id)

    if error_log:
      raise loggers.ElectionError(error_log)


class SourceDirPathsAreUnique(base.BaseRule):
  """All SourceDirPaths should be unique."""

  def elements(self):
    return ["FeedCollection"]

  def check(self, element):
    source_dir_paths = set()
    error_log = []
    for feed_element in element.findall("Feed"):
      if rule_util.element_has_text(feed_element.find("SourceDirPath")):
        source_dir_path = feed_element.find("SourceDirPath").text
        if source_dir_path in source_dir_paths:
          msg = (
              "SourceDirPath {} appears multiple times in the metadata feed."
              " SourceDirPaths must be unique.".format(source_dir_path)
          )
          error_log.append(
              loggers.LogEntry(
                  msg,
                  [feed_element],
              )
          )
        source_dir_paths.add(source_dir_path)

    if error_log:
      raise loggers.ElectionError(error_log)


_ARN_PARSER = botocore_utils.ArnParser()


class SqsQueueNameIsFullyQualifiedArn(base.BaseRule):
  """SqsQueueName must be a valid fully qualified ARN.

  Only AWS region ARNs are supported.
  """

  def elements(self):
    return ["Feed"]

  def check(self, element):
    sqs_queue_name = element.find("SqsQueueName")
    if not rule_util.element_has_text(sqs_queue_name):
      return
    queue_name = sqs_queue_name.text.strip()
    feed_id_element = element.find("FeedId")
    feed_id = (
        feed_id_element.text.strip()
        if rule_util.element_has_text(feed_id_element)
        else ""
    )

    is_valid = False
    if queue_name.startswith("arn:"):
      try:
        arn_dict = _ARN_PARSER.parse_arn(queue_name)
        is_valid = bool(
            arn_dict.get("partition") == "aws"
            and arn_dict.get("service", "").lower() == "sqs"
            and arn_dict.get("region")
            and arn_dict.get("account")
            and arn_dict.get("resource")
        )
      except botocore_utils.InvalidArnException:
        is_valid = False

    if not is_valid:
      if feed_id:
        error_message = (
            f"SqsQueueName '{queue_name}' is not a valid fully qualified ARN"
            f" for feed {feed_id}."
        )
      else:
        error_message = (
            f"SqsQueueName '{queue_name}' is not a valid fully qualified ARN."
        )
      raise loggers.ElectionError.from_message(
          error_message,
          [element],
          [sqs_queue_name.sourceline],
      )


class SqsQueueNameRequiresS3SourceDirPath(base.BaseRule):
  """If SqsQueueName is set, SourceDirPath must also be set and must be an s3 path."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    sqs_queue_name = element.find("SqsQueueName")
    if not rule_util.element_has_text(sqs_queue_name):
      return
    source_dir_path = element.find("SourceDirPath")
    if not rule_util.element_has_text(
        source_dir_path
    ) or not source_dir_path.text.strip().lower().startswith("s3://"):
      raise loggers.ElectionError.from_message(
          "If SqsQueueName is set, SourceDirPath must also be set and must be"
          " an s3 path for feed {}.".format(element.find("FeedId").text),
          [element],
      )


class ElectionEventDatesAreSequential(base.DateRule):
  """Dates in an ElectionEvent element should be sequential."""

  def elements(self):
    return ["ElectionEvent"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)
    self.check_end_after_start()
    if (
        rule_util.element_has_text(element.find("FullDeliveryDate"))
        and self.start_date
    ):
      full_delivery_date = base.PartialDate.init_partial_date(
          element.find("FullDeliveryDate").text
      )
      if self.start_date < full_delivery_date:
        self.error_log.append(
            loggers.LogEntry(
                "StartDate is older than FullDeliveryDate",
                [element],
            )
        )
    if rule_util.element_has_text(
        element.find("InitialDeliveryDate")
    ) and rule_util.element_has_text(element.find("FullDeliveryDate")):
      initial_delivery_date = base.PartialDate.init_partial_date(
          element.find("InitialDeliveryDate").text
      )
      full_delivery_date = base.PartialDate.init_partial_date(
          element.find("FullDeliveryDate").text
      )
      if full_delivery_date < initial_delivery_date:
        self.error_log.append(
            loggers.LogEntry(
                "FullDeliveryDate is older than InitialDeliveryDate",
                [element],
            )
        )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class SourceDirPathMustBeSetAfterInitialDeliveryDate(base.BaseRule):
  """SourceDirPath must be set if any InitialDeliveryDate is in the past."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    if rule_util.element_has_text(element.find("SourceDirPath")):
      return
    today = datetime.date.today()
    today_partial_date = base.PartialDate(
        year=today.year, month=today.month, day=today.day
    )
    initial_deliveries = element.findall(".//InitialDeliveryDate") or []
    for initial_delivery in initial_deliveries:
      initial_delivery_date = (
          base.PartialDate.init_partial_date(initial_delivery.text)
          if rule_util.element_has_text(initial_delivery)
          else None
      )
      if initial_delivery_date and initial_delivery_date < today_partial_date:
        raise loggers.ElectionError.from_message(
            "SourceDirPath is not set but an InitialDeliveryDate is in the "
            f"past for feed {element.find('FeedId').text}.",
            [element],
        )


class OfficeholderSubFeedDatesAreSequential(base.DateRule):
  """Dates in an OfficeholderSubFeed element should be sequential."""

  def elements(self):
    return ["OfficeholderSubFeed"]

  def check(self, element):
    if rule_util.element_has_text(
        element.find("InitialDeliveryDate")
    ) and rule_util.element_has_text(element.find("FullDeliveryDate")):
      initial_delivery_date = base.PartialDate.init_partial_date(
          element.find("InitialDeliveryDate").text
      )
      full_delivery_date = base.PartialDate.init_partial_date(
          element.find("FullDeliveryDate").text
      )
      if full_delivery_date < initial_delivery_date:
        raise loggers.ElectionError.from_message(
            "FullDeliveryDate is older than InitialDeliveryDate",
            [element],
        )


class FeedInactiveDateIsLatestDate(base.BaseRule):
  """Partner feeds should have a FeedInactiveDate that occurs after the FullDeliveryDate and EndDate."""

  ignorable_election_date_statuses = frozenset(["canceled"])

  def elements(self):
    return ["Feed"]

  def check(self, element):
    # Skip this rule for test feeds.
    if rule_util.is_xml_true(element.find("IsTest")):
      return

    if rule_util.element_has_text(element.find("FeedInactiveDate")):
      feed_inactive_date = base.PartialDate.init_partial_date(
          element.find("FeedInactiveDate").text
      )
      for full_delivery_date_element in element.iter("FullDeliveryDate"):
        full_delivery_date = base.PartialDate.init_partial_date(
            full_delivery_date_element.text
        )
        if feed_inactive_date < full_delivery_date:
          raise loggers.ElectionError.from_message(
              "FeedInactiveDate is older than FullDeliveryDate",
              [element],
          )
      for election_event_element in element.iter("ElectionEvent"):
        if rule_util.element_has_text(
            election_event_element.find("ElectionDateStatus")
        ) and (
            election_event_element.find("ElectionDateStatus").text
            in self.ignorable_election_date_statuses
        ):
          continue
        if rule_util.element_has_text(election_event_element.find("EndDate")):
          end_date_element = election_event_element.find("EndDate")
          end_date = base.PartialDate.init_partial_date(end_date_element.text)
          if feed_inactive_date < end_date:
            raise loggers.ElectionError.from_message(
                "FeedInactiveDate is older than EndDate",
                [element],
            )


class FeedHasValidCountryCode(base.BaseRule):
  """Feeds should have valid country code."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    country_code_element = element.find("CountryCode")
    if rule_util.element_has_text(country_code_element):
      country_code = country_code_element.text.upper()
      if not rule_util.country_code_is_valid(country_code):
        raise loggers.ElectionError.from_message(
            "Invalid country code {}.".format(country_code),
            [element],
        )
    else:
      feed_type = element.find("FeedType")
      if rule_util.element_has_text(feed_type) and (
          feed_type.text.lower().replace("_", "-") == "election-dates"
          or feed_type.text.lower().replace("_", "-") == "voter-information"
      ):
        return
      raise loggers.ElectionError.from_message(
          "Feed {} is missing CountryCode.".format(element.find("FeedId").text),
          [element],
      )


class FeedInactiveDateNotOlderThanOneYear(base.BaseRule):
  """Feeds should not have a FeedInactiveDate older than 1 year."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_inactive_date_element = element.find("FeedInactiveDate")
    if not rule_util.element_has_text(feed_inactive_date_element):
      return
    feed_inactive_date = datetime.date.fromisoformat(
        feed_inactive_date_element.text
    )
    one_year_ago = datetime.date.today() - dateutil.relativedelta.relativedelta(
        years=1
    )
    if feed_inactive_date < one_year_ago:
      feed_id_element = element.find("FeedId")
      raise loggers.ElectionError.from_message(
          f"FeedInactiveDate '{feed_inactive_date_element.text}' is older than"
          f" 1 year for feed '{feed_id_element.text}'.",
          [element],
      )


class FeedInactiveDateSetForNonEvergreenFeed(base.BaseRule):
  """All non-evergreen feeds should have a FeedInactiveDate set."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_longevity = element.find("FeedLongevity")
    if (
        rule_util.element_has_text(feed_longevity)
        and feed_longevity.text.lower() != "evergreen"
        and not rule_util.element_has_text(element.find("FeedInactiveDate"))
    ):
      raise loggers.ElectionError.from_message(
          "FeedInactiveDate is not set for non-evergreen feed with FeedId {}."
          .format(element.find("FeedId").text),
          [element],
      )


class FeedElementsShouldHaveSubElementsBasedOnType(base.BaseRule):
  """Feeds should have certain elements based on feed type.

  For example, Feeds of type officeholder should have an OfficeholderSubFeed,
  similarly pre-election and election-results feeds should have an
  ElectionEventCollection. In the case of an ElectionEventCollection, at least
  one ElectionEvent element should be present.
  """

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_type = element.find("FeedType")
    feed_id = element.find("FeedId").text

    if not rule_util.element_has_text(feed_type):
      return

    feed_type = feed_type.text
    if feed_type == "officeholder":
      if element.find("OfficeholderSubFeed") is None:
        raise loggers.ElectionError.from_message(
            "OfficeholderSubFeed should exist for %s feed %s."
            % (feed_type, feed_id)
        )
    elif feed_type == "pre-election" or feed_type == "election-results":
      if element.find("ElectionEventCollection") is None:
        raise loggers.ElectionError.from_message(
            "ElectionEventCollection should exist for %s feed %s."
            % (feed_type, feed_id)
        )
      if not element.find("ElectionEventCollection").findall("ElectionEvent"):
        raise loggers.ElectionError.from_message(
            "ElectionEventCollection should have at least one ElectionEvent"
            " for %s feed %s." % (feed_type, feed_id)
        )


class RuleSet(enum.Enum):
  """Names for sets of rules used to validate a particular feed type."""

  ELECTION = 1
  OFFICEHOLDER = 2
  COMMITTEE = 3
  ELECTION_DATES = 4
  ELECTION_RESULTS = 5
  METADATA = 6
  VOTER_INFORMATION = 7


# To add new rules, create a new class, inherit the base rule,
# and add it to the correct rule list.
COMMON_RULES = common_rules.COMMON_RULES
OFFICEHOLDER_RULES = officeholder_rules.OFFICEHOLDER_RULES
ELECTION_RULES = election_rules.ELECTION_RULES
ELECTION_DATES_RULES = election_dates_rules.ELECTION_DATES_RULES
COMMITTEE_RULES = committee_rules.COMMITTEE_RULES
VOTER_INFORMATION_RULES = voter_information_rules.VOTER_INFORMATION_RULES


METADATA_RULES = (
    # go/keep-sorted start
    ElectionEventDatesAreSequential,
    FeedElementsShouldHaveSubElementsBasedOnType,
    FeedHasValidCountryCode,
    FeedIdsAreUnique,
    FeedInactiveDateIsLatestDate,
    FeedInactiveDateNotOlderThanOneYear,
    FeedInactiveDateSetForNonEvergreenFeed,
    FeedTypeHasValidFeedLongevity,
    OfficeholderSubFeedDatesAreSequential,
    SourceDirPathMustBeSetAfterInitialDeliveryDate,
    SourceDirPathsAreUnique,
    # TODO(b/555757644): Reenable this rule once we are ready to enforce it.
    # SqsQueueNameIsFullyQualifiedArn,
    SqsQueueNameRequiresS3SourceDirPath,
    common_rules.EmptyString,
    common_rules.EmptyText,
    common_rules.Encoding,
    common_rules.OptionalAndEmpty,
    common_rules.Schema,
    common_rules.UniqueLabel,
    # go/keep-sorted end
)


ALL_RULES = frozenset(
    COMMON_RULES
    + ELECTION_RULES
    + OFFICEHOLDER_RULES
    + COMMITTEE_RULES
    + ELECTION_DATES_RULES
    + VOTER_INFORMATION_RULES
    + METADATA_RULES
)

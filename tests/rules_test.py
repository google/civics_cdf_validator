# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import election_rules
from civics_cdf_validator.rulesets import metadata_rules
import freezegun
from lxml import etree


class FeedTypeHasValidFeedLongevityTest(absltest.TestCase):

  def setUp(self):
    super(FeedTypeHasValidFeedLongevityTest, self).setUp()
    self.validator = metadata_rules.FeedTypeHasValidFeedLongevity(None, None)

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
    self.validator = metadata_rules.FeedIdsAreUnique(None, None)

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
    self.validator = metadata_rules.SourceDirPathsAreUnique(None, None)

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


class SqsQueueNameIsFullyQualifiedArnTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = metadata_rules.SqsQueueNameIsFullyQualifiedArn(None, None)

  def test_no_sqs_queue_name_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SourceDirPath>https://example.com/feed</SourceDirPath>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_empty_sqs_queue_name_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName></SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_whitespace_sqs_queue_name_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>   </SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_valid_arn_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_valid_arn_with_whitespace_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>
          arn:aws:sqs:us-east-1:123456789012:my-queue
        </SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_non_arn_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'my-queue' is not a valid fully qualified ARN for feed"
        " test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")
    self.assertEqual(context.exception.log_entry[0].lines, [4])

  def test_arn_missing_parts_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs:us-east-1</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws:sqs:us-east-1' is not a valid fully qualified"
        " ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_non_sqs_service_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sns:us-east-1:123456789012:my-topic</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws:sns:us-east-1:123456789012:my-topic' is not a"
        " valid fully qualified ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_missing_region_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs::123456789012:my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws:sqs::123456789012:my-queue' is not a valid"
        " fully qualified ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_missing_account_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs:us-east-1::my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws:sqs:us-east-1::my-queue' is not a valid fully"
        " qualified ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_missing_resource_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs:us-east-1:123456789012:</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws:sqs:us-east-1:123456789012:' is not a valid"
        " fully qualified ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_invalid_prefix_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>not-arn:aws:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'not-arn:aws:sqs:us-east-1:123456789012:my-queue' is not"
        " a valid fully qualified ARN for feed test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_missing_feed_id_fails(self):
    feed_string = """
      <Feed>
        <SqsQueueName>my-queue</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'my-queue' is not a valid fully qualified ARN.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_non_aws_partition_fails(self):
    for partition in ["aws-cn", "aws-us-gov", "other"]:
      feed_string = f"""
        <Feed>
          <FeedId>test-feed</FeedId>
          <SqsQueueName>arn:{partition}:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
        </Feed>
        """

      with self.assertRaises(loggers.ElectionError) as context:
        self.validator.check(etree.fromstring(feed_string))
      self.assertEqual(
          f"SqsQueueName 'arn:{partition}:sqs:us-east-1:123456789012:my-queue'"
          " is not a valid fully qualified ARN for feed test-feed.",
          context.exception.log_entry[0].message,
      )
      self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")

  def test_arn_invalid_arn_exception_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws</SqsQueueName>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        "SqsQueueName 'arn:aws' is not a valid fully qualified ARN for feed"
        " test-feed.",
        context.exception.log_entry[0].message,
    )
    self.assertEqual(context.exception.log_entry[0].elements[0].tag, "Feed")


class SqsQueueNameRequiresS3SourceDirPathTest(absltest.TestCase):

  def setUp(self):
    super(SqsQueueNameRequiresS3SourceDirPathTest, self).setUp()
    self.validator = metadata_rules.SqsQueueNameRequiresS3SourceDirPath(
        None, None
    )

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
        <SqsQueueName>arn:aws:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  def test_sqs_queue_name_missing_source_dir_path_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <SqsQueueName>arn:aws:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
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
        <SqsQueueName>arn:aws:sqs:us-east-1:123456789012:my-queue</SqsQueueName>
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
    self.validator = metadata_rules.ElectionEventDatesAreSequential(None, None)

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
    self.validator = (
        metadata_rules.SourceDirPathMustBeSetAfterInitialDeliveryDate(
            None, None
        )
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
    self.validator = metadata_rules.OfficeholderSubFeedDatesAreSequential(
        None, None
    )

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
    self.validator = metadata_rules.FeedInactiveDateIsLatestDate(None, None)

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
    self.validator = metadata_rules.FeedHasValidCountryCode(None, None)

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
    self.validator = metadata_rules.FeedInactiveDateSetForNonEvergreenFeed(
        None, None
    )

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


class FeedInactiveDateNotOlderThanOneYearTest(absltest.TestCase):

  def setUp(self):
    super(FeedInactiveDateNotOlderThanOneYearTest, self).setUp()
    self.validator = metadata_rules.FeedInactiveDateNotOlderThanOneYear(
        None, None
    )

  @freezegun.freeze_time("2026-01-01")
  def test_feed_without_inactive_date_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2026-01-01")
  def test_feed_inactive_date_less_than_one_year_old_succeeds(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <FeedInactiveDate>2025-06-01</FeedInactiveDate>
      </Feed>
      """

    self.validator.check(etree.fromstring(feed_string))

  @freezegun.freeze_time("2026-01-01")
  def test_feed_inactive_date_older_than_one_year_fails(self):
    feed_string = """
      <Feed>
        <FeedId>test-feed</FeedId>
        <FeedInactiveDate>2024-12-31</FeedInactiveDate>
      </Feed>
      """

    with self.assertRaises(loggers.ElectionError) as context:
      self.validator.check(etree.fromstring(feed_string))
    self.assertEqual(
        context.exception.log_entry[0].message,
        "FeedInactiveDate '2024-12-31' is older than 1 year for feed"
        " 'test-feed'.",
    )


class FeedElementsShouldHaveSubElementsBasedOnTypeTest(parameterized.TestCase):
  """Feeds should have certain elements based on feed type."""

  def setUp(self):
    super(FeedElementsShouldHaveSubElementsBasedOnTypeTest, self).setUp()
    self.validator = (
        metadata_rules.FeedElementsShouldHaveSubElementsBasedOnType(None, None)
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


class RulesTest(absltest.TestCase):

  def test_all_rules_included_succeeds(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(election_rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    possible_rules.remove(base.MissingFieldRule)
    possible_rules.remove(common_rules.UnreferencedEntitiesBase)
    # TODO(b/555757644): Reenable this rule once we are ready to enforce it.
    possible_rules.remove(metadata_rules.SqsQueueNameIsFullyQualifiedArn)

    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()

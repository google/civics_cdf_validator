"""Tests for google3.third_party.py.civics_cdf_validator."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

from absl import flags
from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
import pytest


FLAGS = flags.FLAGS


@pytest.mark.skip(reason='skip samples test during local development')
class SamplesTest(absltest.TestCase):
  """Test that all sample files pass validation."""

  def setUp(self):
    super(SamplesTest, self).setUp()
    # OCD-ID rules don't work inside google3.
    ocd_id_rules = {rules.ElectoralDistrictOcdId, rules.GpUnitOcdId}
    # Election dates check for dates to not be in the past. Since our sample
    # files will always, at some point, end up being in the past we are
    # removing date rules from these tests.
    date_rules = {rules.ElectionStartDates, rules.ElectionEndDatesInThePast,
                  rules.ElectionEndDatesOccurAfterStartDates}
    self.election_rules = (
        set(rules.ELECTION_RULES) - ocd_id_rules - date_rules)
    self.officeholder_rules = (
        set(rules.OFFICEHOLDER_RULES) - ocd_id_rules)

  def testOfficeholderSampleFeed(self):
    self._TestFile('officeholder_sample_feed.xml', self.officeholder_rules)

  def testPostElectionSampleFeedPrecincts(self):
    self._TestFile(
        'post_election_sample_feed_precincts.xml',
        self.election_rules,
        expected_errors=19,
    )

  def testPostRetentionContestSampleFeedSummary(self):
    self._TestFile(
        'post_retention_contest_sample_feed_summary.xml',
        self.election_rules,
    )

  def testPreRetentionContestSampleFeed(self):
    self._TestFile(
        'pre_retention_contest_sample_feed.xml',
        self.election_rules,
        )

  def testPostRetentionContestSampleFeedPrecincts(self):
    self._TestFile(
        'post_retention_contest_sample_feed_precincts.xml',
        self.election_rules,
        expected_errors=19,
    )

  def testPostElectionSampleFeedSummary(self):
    self._TestFile(
        'post_election_sample_feed_summary.xml',
        self.election_rules,
    )

  def testPreElectionSampleFeed(self):
    self._TestFile(
        'pre_election_sample_feed.xml',
        self.election_rules)

  def testBallotMeasureContestSampleFeed(self):
    self._TestFile('ballot_measure_contest_sample_feed.xml',
                   self.election_rules)

  def testBallotMeasureContestWithResultsSampleFeed(self):
    self._TestFile('ballot_measure_contest_sample_feed_with_results.xml',
                   self.election_rules)

  def testMultiElectionSampleFeed(self):
    self._TestFile('multi_election_sample_feed.xml', self.election_rules)

  def _TestFile(self, filename, rules_to_check,
                expected_errors=0, expected_warnings=0):
    sample_file = os.path.join(
        FLAGS.test_srcdir,
        'google3/third_party/py/civics_cdf_validator/'
        'samples/' + filename)
    schema_file = os.path.join(
        FLAGS.test_srcdir,
        'google3/third_party/py/civics_cdf_validator/'
        'civics_cdf_spec.xsd')
    registry = base.RulesRegistry(
        election_file=sample_file,
        schema_file=schema_file,
        rule_options={},
        rule_classes_to_check=rules_to_check)

    registry.check_rules()
    registry.print_exceptions(0, True)
    self.assertEqual(
        expected_errors,
        registry.exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionError))
    self.assertEqual(
        expected_warnings,
        registry.exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionWarning))


if __name__ == '__main__':
  absltest.main()

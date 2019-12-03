"""Tests for google3.third_party.py.election_results_xml_validator."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

from absl import flags
from absl.testing import absltest
from election_results_xml_validator import base
from election_results_xml_validator import rules
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
    date_rules = {rules.ElectionStartDates, rules.ElectionEndDates}
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
        expected_errors=1,
    )

  def testPostElectionSampleFeedSummary(self):
    self._TestFile(
        'post_election_sample_feed_summary.xml',
        self.election_rules,
        expected_errors=1,
    )

  def testPreElectionSampleFeed(self):
    self._TestFile(
        'pre_election_sample_feed.xml',
        self.election_rules,
        expected_warnings=19,
        expected_errors=18)

  def _TestFile(self, filename, rules_to_check,
                expected_errors=0, expected_warnings=0):
    sample_file = os.path.join(
        FLAGS.test_srcdir,
        'google3/third_party/py/election_results_xml_validator/'
        'samples/' + filename)
    schema_file = os.path.join(
        FLAGS.test_srcdir,
        'google3/third_party/py/election_results_xml_validator/'
        'election_data_spec.xsd')
    registry = base.RulesRegistry(
        election_file=sample_file,
        schema_file=schema_file,
        rule_options={},
        rule_classes_to_check=rules_to_check)

    registry.check_rules()
    self.assertEqual(expected_errors,
                     registry.exception_counts[base.ElectionError])
    self.assertEqual(expected_warnings,
                     registry.exception_counts[base.ElectionWarning])


if __name__ == '__main__':
  absltest.main()

"""Unit test for rules.py."""

import xml.etree.ElementTree as ET

from absl.testing import absltest
from election_results_xml_validator import base
from election_results_xml_validator.rules import AllLanguages
from election_results_xml_validator.rules import OnlyOneElection
from election_results_xml_validator.rules import PercentSum


class RulesTest(absltest.TestCase):

  def setUp(self):
    super(RulesTest, self).setUp()
    self.percent_sum = PercentSum(None, None)
    self.only_one_election = OnlyOneElection(None, None)
    self.all_languages = AllLanguages(None, None)

  def testZeroPercents(self):
    root_string = """
    <Contest>
      <BallotSelection>
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """

    self.percent_sum.check(ET.fromstring(root_string))

  def testHundredPercents(self):
    root_string = """
    <Contest>
      <BallotSelection>
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>60.0</Count>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>40.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """

    self.percent_sum.check(ET.fromstring(root_string))

  def testInvalidPercents_fails(self):
    root_string = """
    <Contest>
      <BallotSelection>
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>60.0</Count>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>20.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """

    with self.assertRaises(base.ElectionError):
      self.percent_sum.check(ET.fromstring(root_string))

  def testExactlyOneElection(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
    </ElectionReport>
    """

    self.only_one_election.check(ET.fromstring(root_string))

  def testMoreThanOneElection_fails(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
      <Election></Election>
    </ElectionReport>
    """

    with self.assertRaises(base.ElectionError):
      self.only_one_election.check(ET.fromstring(root_string))

  def testExactLanguages(self):
    root_string = """
    <FullName>
      <Text language="en">Name</Text>
      <Text language="es">Nombre</Text>
      <Text language="nl">Naam</Text>
    </FullName>
    """
    self.all_languages.required_languages = ["en", "es", "nl"]
    self.all_languages.check(ET.fromstring(root_string))

  def testExtraLanguages(self):
    root_string = """
    <FullName>
      <Text language="en">Name</Text>
      <Text language="es">Nombre</Text>
      <Text language="nl">Naam</Text>
    </FullName>
    """
    self.all_languages.required_languages = ["en"]
    self.all_languages.check(ET.fromstring(root_string))

  def testMissingLanguage_fails(self):
    root_string = """
    <FullName>
      <Text language="en">Name</Text>
      <Text language="es">Nombre</Text>
    </FullName>
    """
    self.all_languages.required_languages = ["en", "es", "nl"]
    with self.assertRaises(base.ElectionError):
      self.all_languages.check(ET.fromstring(root_string))

if __name__ == '__main__':
  absltest.main()

# -*- coding: utf-8 -*-
"""Unit test for base.py."""

import io
import sys
from absl.testing import absltest
from election_results_xml_validator import base
from lxml import etree
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
    with self.assertRaises(base.ElectionError) as ee:
      base.ValidReferenceRule(None, None).check()
    self.assertIn("id-5", str(ee.exception))
    self.assertIn("id-6", str(ee.exception))


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

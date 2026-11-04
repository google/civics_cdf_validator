# -*- coding: utf-8 -*-
"""Unit test for election_dates_rules.py."""

from absl.testing import absltest
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import election_dates_rules
from lxml import etree


class UnreferencedEntitiesElectionDatesTest(absltest.TestCase):
  _base_schema = etree.fromstring(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    </xs:schema>
  """)

  def test_unreferenced_top_level_gp_unit_raises_info(self):
    test_string = """
    <GpUnit objectId="gpunit-id">
      <ComposingGpUnitIds>child-gpunit child-gpunit-2</ComposingGpUnitIds>
    </GpUnit>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="ComposingGpUnitIds" type="xs:IDREFS" />
    </xs:schema>
  """

    with self.assertRaises(loggers.ElectionInfo) as context:
      election_dates_rules.UnreferencedEntitiesElectionDates(
          etree.fromstring(test_string), etree.fromstring(schema_string)
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "GpUnit with object id gpunit-id is not referenced by anything"
        " else in the feed. This is ok for top-level GpUnits that"
        " contain others; please ensure this GpUnit is still required in"
        " the feed.",
    )

  def test_unreferenced_child_gp_unit_fails(self):
    test_string = """
    <GpUnit objectId="gpunit-id">
    </GpUnit>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      election_dates_rules.UnreferencedEntitiesElectionDates(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type GpUnit with object id gpunit-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_office_fails(self):
    test_string = """
    <Office objectId="office-id">
    </Office>
    """

    with self.assertRaises(loggers.ElectionError) as context:
      election_dates_rules.UnreferencedEntitiesElectionDates(
          etree.fromstring(test_string), self._base_schema
      ).check()
    self.assertEqual(
        context.exception.log_entry[0].message,
        "Element of type Office with object id office-id is not referenced by"
        " anything else in the feed.",
    )

  def test_unreferenced_top_level_election_and_contest_succeeds(self):
    test_string = """
    <Election objectId="election-id">
      <ContestCollection>
        <Contest objectId="ballot-measure-contest-id">
        </Contest>
      </ContestCollection>
    </Election>
    """

    election_dates_rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), self._base_schema
    ).check()

  def test_referenced_office_succeeds(self):
    test_string = """
    <ElectionReport xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election objectId="election-id">
        <ContestCollection>
          <Contest objectId="ballot-measure-contest-id" xsi:type="BallotMeasureContest">
            <OfficeIds>office-id</OfficeIds>
          </Contest>
        </ContestCollection>
      </Election>
      <OfficeCollection>
        <Office objectId="office-id">
        </Office>
      </OfficeCollection>
    </ElectionReport>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="OfficeIds" type="xs:IDREFS" />
    </xs:schema>
  """

    election_dates_rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()

  def test_external_id_referenced_gp_unit_succeeds(self):
    test_string = """
    <ElectionReport xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Election objectId="election-id">
        <ContestCollection>
          <Contest objectId="ballot-measure-contest-id" xsi:type="BallotMeasureContest">
            <OfficeIds>office-id</OfficeIds>
          </Contest>
        </ContestCollection>
      </Election>
      <GpUnitCollection>
        <GpUnit objectId="gpunit-1">
        </GpUnit>
      </GpUnitCollection>
      <OfficeCollection>
        <Office objectId="office-id">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>jurisdiction-id</OtherType>
              <Value>gpunit-1</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Office>
      </OfficeCollection>
    </ElectionReport>
    """
    schema_string = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element minOccurs="0" name="OfficeIds" type="xs:IDREFS" />
    </xs:schema>
  """

    election_dates_rules.UnreferencedEntitiesElectionDates(
        etree.fromstring(test_string), etree.fromstring(schema_string)
    ).check()


if __name__ == "__main__":
  absltest.main()

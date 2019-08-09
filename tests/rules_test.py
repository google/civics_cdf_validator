"""Unit test for rules.py."""

import xml.etree.ElementTree as ET

from absl.testing import absltest
from election_results_xml_validator import base
from election_results_xml_validator import rules


class RulesTest(absltest.TestCase):

  def setUp(self):
    super(RulesTest, self).setUp()
    self.percent_sum = rules.PercentSum(None, None)
    self.only_one_election = rules.OnlyOneElection(None, None)
    self.all_languages = rules.AllLanguages(None, None)
    self.persons_have_offices = rules.PersonsHaveOffices(None, None)
    self.prohibit_election_data = rules.ProhibitElectionData(None, None)
    self.validate_ocdid_lowercase = rules.ValidateOcdidLowerCase(None, None)
    self.persons_missing_party = rules.PersonsMissingPartyData(
        None, None
    )
    self.office_missing_person_ids = rules.OfficeMissingOfficeHolderPersonData(
        None, None
    )
    self.unaffiliated_parties = rules.MissingPartyAffiliation(None, None)

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

  def testPartiesMissingReference(self):
    root_string = """
    <xml>
      <PartyCollection>
        <Party objectId="par0001">
          <Abbreviation>REP</Abbreviation>
          <Color>e91d0e</Color>
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Abbreviation>DEM</Abbreviation>
          <Color>e91fff</Color>
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
          <PartyId>par0002</PartyId>
        </Candidate>
      </CandidateCollection>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """
    self.unaffiliated_parties.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.unaffiliated_parties.check()

  def testPartiesMissingPersonReference(self):
    root_string = """
    <xml>
      <PartyCollection>
        <Party objectId="par0001">
          <Abbreviation>REP</Abbreviation>
          <Color>e91d0e</Color>
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Abbreviation>DEM</Abbreviation>
          <Color>e91fff</Color>
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
        </Party>
      </PartyCollection>
      <CandidateCollection>
        <Candidate>
          <PartyId>par0002</PartyId>
        </Candidate>
      </CandidateCollection>
    </xml>
    """
    self.unaffiliated_parties.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.unaffiliated_parties.check()

  def testPartiesMissingCandidateReference(self):
    root_string = """
    <xml>
      <PartyCollection>
        <Party objectId="par0001">
          <Abbreviation>REP</Abbreviation>
          <Color>e91d0e</Color>
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Abbreviation>DEM</Abbreviation>
          <Color>e91fff</Color>
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
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """
    self.unaffiliated_parties.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.unaffiliated_parties.check()

  def testPartiesMissingPartyReference_fails(self):
    root_string = """
    <xml>
      <PartyCollection>
        <Party objectId="par0001">
          <Abbreviation>REP</Abbreviation>
          <Color>e91d0e</Color>
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Abbreviation>DEM</Abbreviation>
          <Color>e91fff</Color>
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
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """

    self.unaffiliated_parties.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    with self.assertRaises(base.ElectionError) as cm:
      self.unaffiliated_parties.check()
    self.assertIn("Party elements not found", str(cm.exception))

  def testPersonsHaveOffices(self):
    root_string = """
    <xml>
      <PersonCollection>
        <Person objectId="p1" />
        <Person objectId="p2" />
        <Person objectId="p3" />
      </PersonCollection>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """
    self.persons_have_offices.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.persons_have_offices.check()

  def testPersonsHaveOffices_fails(self):
    root_string = """
    <xml>
      <PersonCollection>
        <Person objectId="p1" />
        <Person objectId="p2" />
        <Person objectId="p3" />
      </PersonCollection>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """
    with self.assertRaises(base.ElectionError):
      self.persons_have_offices.election_tree = ET.ElementTree(
          ET.fromstring(root_string))
      self.persons_have_offices.check()

  def testProhibitElectionData(self):
    root_string = """<xml><PersonCollection></PersonCollection></xml>"""
    self.prohibit_election_data.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.prohibit_election_data.check()

  def testProhibitElectionData_fails(self):
    root_string = """<xml><Election></Election></xml>"""
    with self.assertRaises(base.ElectionError) as cm:
      self.prohibit_election_data.election_tree = ET.ElementTree(
          ET.fromstring(root_string))
      self.prohibit_election_data.check()
    self.assertIn("Election data is prohibited", str(cm.exception))

  def testValidateOcdIdLowercase(self):
    root_string = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value>ocd-division/country:us/state:va</Value>
    </ExternalIdentifier>
    """
    self.validate_ocdid_lowercase.check(ET.fromstring(root_string))

  def testValidateOcdIdLowercase_fails(self):
    root_string = """
    <ExternalIdentifier>
      <Type>ocd-id</Type>
      <Value>ocd-division/country:us/state:VA</Value>
    </ExternalIdentifier>
    """
    with self.assertRaises(base.ElectionWarning) as cm:
      self.validate_ocdid_lowercase.check(ET.fromstring(root_string))
    self.assertIn("Valid OCD-IDs should be all lowercase", str(cm.exception))

  def testAllRulesIncluded(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses

  def testOfficeMissingOfficeHolderPersonData(self):
    root_string = """
    <xml>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
      <PersonCollection>
        <Person objectId="p1"/>
        <Person objectId="p2">
          <PartyId>par1</PartyId>
        </Person>
        <Person objectId="p3"/>
      </PersonCollection>
    </xml>
    """
    self.office_missing_person_ids.election_tree = ET.ElementTree(
        ET.fromstring(root_string))
    self.office_missing_person_ids.check()

  def testOfficeHolderPersonIdsHaveAllPersons_fails(self):
    root_string = """
    <xml>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
      <PersonCollection>
        <Person objectId="p2">
          <PartyId>par1</PartyId>
        </Person>
        <Person objectId="p3"/>
      </PersonCollection>
    </xml>
    """
    self.office_missing_person_ids.election_tree = ET.ElementTree(
        ET.fromstring(root_string))

    with self.assertRaises(base.ElectionError) as cm:
      self.office_missing_person_ids.check()
    self.assertIn("missing Person data", str(cm.exception))

  def testOfficeHolderPersonIdsHavePersons_fails(self):
    root_string = """
    <xml>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
      <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    </xml>
    """
    self.office_missing_person_ids.election_tree = ET.ElementTree(
        ET.fromstring(root_string))

    with self.assertRaises(base.ElectionError) as cm:
      self.office_missing_person_ids.check()
    self.assertIn("No Person data present.", str(cm.exception))

  def testOfficeHolderPersonDataHasIds_fails(self):
    root_string = """
    <xml>
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>  </OfficeHolderPersonIds></Office>
      </OfficeCollection>
      <PersonCollection>
        <Person objectId="p1"/>
        <Person objectId="p2">
          <PartyId>par1</PartyId>
        </Person>
      </PersonCollection>
    </xml>
    """

    self.office_missing_person_ids.election_tree = ET.ElementTree(
        ET.fromstring(root_string))

    with self.assertRaises(base.ElectionError) as cm:
      self.office_missing_person_ids.check()
    self.assertIn("Office is missing IDs of Officeholders.",
                  str(cm.exception))

  def testPersonsMissingPartyData(self):
    root_string = """
      <Person objectId="p1">
        <PartyId>par1</PartyId>
      </Person>
    """
    self.persons_missing_party.check(ET.fromstring(root_string))

  def testPersonsMissingPartyData_fails(self):
    root_string = """
      <Person objectId="p1">
        <PartyId></PartyId>
      </Person>
    """

    with self.assertRaises(base.ElectionWarning):
      self.persons_missing_party.check(
          ET.fromstring(root_string)
      )


class GenderValidationTest(absltest.TestCase):

  def setUp(self):
    super(GenderValidationTest, self).setUp()
    self.gender_validator = rules.PersonsHaveValidGender(None, None)

  def testAllPersonsHaveValidGender(self):
    root_string = """
      <Gender>Female</Gender>
    """
    gender_element = ET.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIsCaseInsensitive(self):
    root_string = """
      <Gender>female</Gender>
    """
    gender_element = ET.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIgnoresEmptyValue(self):
    root_string = """
      <Gender></Gender>
    """
    gender_element = ET.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationFailsForInvalidValue(self):
    root_string = """
      <Gender>blamo</Gender>
    """
    gender_element = ET.fromstring(root_string)
    with self.assertRaises(base.ElectionError):
      self.gender_validator.check(gender_element)


class VoteCountTypesCoherencyTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountTypesCoherencyTest, self).setUp()
    self.vc_coherency = rules.VoteCountTypesCoherency(None, None)

  def testInvalidNotInPartyContest(self):
    root_string = """
    <Contest objectId="pc1" type="PartyContest">
      <BallotSelection objectId="ps1-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>seats-leading</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """
    self.vc_coherency.check(ET.fromstring(root_string))

  def testInvalidNotInPartyContest_fails(self):
    root_string = """
    <Contest objectId="pc1" type="PartyContest">
      <BallotSelection objectId="ps1-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>candidate-votes</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.vc_coherency.check(ET.fromstring(root_string))

    for vc_type in rules.VoteCountTypesCoherency.CAND_VC_TYPES:
      self.assertIn(vc_type, str(cm.exception))

  def testInvalidNotInCandidateContest(self):
    root_string = """
    <Contest objectId="pc1" type="CandidateContest">
      <BallotSelection objectId="ps1-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>candidate-votes</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """
    self.vc_coherency.check(ET.fromstring(root_string))

  def testNonInvalidVCTypesDoNotFail(self):
    # returns None if no VoteCount types
    root_string = """
    <Contest objectId="pc1" type="CandidateContest">
      <BallotSelection objectId="ps1-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>total-percent</OtherType>
            <Count>0.0</Count>
          </VoteCounts>
          <VoteCounts>
            <OtherType>some-future-vote-count-type</OtherType>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """
    self.assertIsNone(self.vc_coherency.check(ET.fromstring(root_string)))

  def testInvalidNotInCandidateContest_fails(self):
    # Checks Candidate parsing fails on all party types
    root_string = """
    <Contest objectId="pc1" type="CandidateContest">
      <BallotSelection objectId="ps1-0">
        <VoteCountsCollection>
          <VoteCounts>
            <OtherType>seats-won</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-leading</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>party-votes</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-no-election</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-total</OtherType>
          </VoteCounts>
          <VoteCounts>
            <OtherType>seats-delta</OtherType>
          </VoteCounts>
        </VoteCountsCollection>
      </BallotSelection>
    </Contest>
    """

    with self.assertRaises(base.ElectionError) as cm:
      self.vc_coherency.check(ET.fromstring(root_string))

    for vc_type in rules.VoteCountTypesCoherency.PARTY_VC_TYPES:
      self.assertIn(vc_type, str(cm.exception))

if __name__ == "__main__":
  absltest.main()

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
"""Validation rules for the NIST CDF XML validator."""

from __future__ import print_function

import collections
import hashlib
import re

from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import office_utils
import enum
import language_tags
from lxml import etree
from six.moves.urllib.parse import urlparse

_PARTY_LEADERSHIP_TYPES = ["party-leader-id", "party-chair-id"]
_IDENTIFIER_TYPES = frozenset(
    ["local-level", "national-level", "ocd-id", "state-level"])


def get_external_id_values(element, value_type, return_elements=False):
  """Helper to gather all Values of external ids for a given type."""
  external_ids = element.findall(".//ExternalIdentifier")
  values = []
  for extern_id in external_ids:
    id_type = extern_id.find("Type")
    if id_type is None or not id_type.text:
      continue
    matches_type = False
    id_text = id_type.text.strip()
    if id_text in _IDENTIFIER_TYPES and id_text == value_type:
      matches_type = True
    elif id_text == "other":
      other_type = extern_id.find("OtherType")
      if (other_type is not None and other_type.text
          and other_type.text.strip() == value_type
          and value_type not in _IDENTIFIER_TYPES):
        matches_type = True
    if matches_type:
      value = extern_id.find("Value")
      # Could include empty text; check in calling function.
      # Not checked here because errors should be raised in some cases.
      if value is not None and value.text:
        if return_elements:
          values.append(value)
        else:
          values.append(value.text)
  return values


def get_additional_type_values(element, value_type, return_elements=False):
  """Helper to gather all nested additional type values for a given type."""
  elements = element.findall(".//AdditionalData[@type='{}']".format(value_type))
  if not return_elements:
    return [
        val.text
        for val in elements
        if val is not None and val.text and val.text.strip()
    ]
  return elements


def get_entity_info_for_value_type(element, info_type, return_elements=False):
  info_collection = get_additional_type_values(
      element, info_type, return_elements)
  info_collection.extend(
      list(get_external_id_values(element, info_type, return_elements))
  )
  return info_collection


def get_language_to_text_map(element):
  """Return a map of languages to text in an InternationalizedText element."""
  language_map = {}
  if element is None:
    return language_map
  intl_strings = element.findall("Text")

  for intl_string in intl_strings:
    text = intl_string.text
    if text is None or not text:
      continue
    language = intl_string.get("language")
    if language is None or not language:
      continue
    language_map[language] = text
  return language_map


def element_has_text(element):
  return (element is not None and element.text is not None
          and not element.text.isspace())


class Schema(base.TreeRule):
  """Checks if election file validates against the provided schema."""

  def check(self):
    try:
      schema = etree.XMLSchema(etree=self.schema_tree)
    except etree.XMLSchemaParseError as e:
      raise loggers.ElectionError.from_message(
          "The schema file could not be parsed correctly %s" % str(e))
    valid_xml = True
    try:
      schema.assertValid(self.election_tree)
    except etree.DocumentInvalid as e:
      valid_xml = False
    if not valid_xml:
      errors = []
      for error in schema.error_log:
        errors.append(
            loggers.LogEntry(lines=[error.line],
                             message=("The election file didn't validate "
                                      "against schema : {0}".format(
                                          error.message.encode("utf-8")))))
      raise loggers.ElectionError(errors)


class OptionalAndEmpty(base.BaseRule):
  """Checks for optional and empty fields."""

  def __init__(self, election_tree, schema_tree):
    super(OptionalAndEmpty, self).__init__(election_tree, schema_tree)
    self.previous = None

  def elements(self):
    eligible_elements = []
    for _, element in etree.iterwalk(self.schema_tree):
      tag = self.strip_schema_ns(element)
      if tag and tag == "element" and element.get("minOccurs") == "0":
        eligible_elements.append(element.get("name"))
    return eligible_elements

  # pylint: disable=g-explicit-length-test
  def check(self, element):
    if element == self.previous:
      return
    self.previous = element
    if (element.text is None or not element.text.strip()) and not len(element):
      raise loggers.ElectionWarning.from_message(
          "This optional element included although it is empty.", [element])


class Encoding(base.TreeRule):
  """Checks that the file provided uses UTF-8 encoding."""

  def check(self):
    docinfo = self.election_tree.docinfo
    if docinfo.encoding != "UTF-8":
      raise loggers.ElectionError.from_message("Encoding on file is not UTF-8")


class HungarianStyleNotation(base.BaseRule):
  """Check that element identifiers use Hungarian style notation.

  Hungarian style notation is used to maintain uniqueness and provide context
  for the identifiers.
  """

  # Add a prefix when there is a specific entity in the xml.
  elements_prefix = {
      "BallotMeasureContest": "bmc",
      "BallotMeasureSelection": "bms",
      "BallotStyle": "bs",
      "Candidate": "can",
      "CandidateContest": "cc",
      "CandidateSelection": "cs",
      "Coalition": "coa",
      "ContactInformation": "ci",
      "Hours": "hours",
      "Office": "off",
      "OfficeGroup": "og",
      "Party": "par",
      "PartyContest": "pc",
      "PartySelection": "ps",
      "Person": "per",
      "ReportingDevice": "rd",
      "ReportingUnit": "ru",
      "RetentionContest": "rc",
      "Schedule": "sched",
  }

  def elements(self):
    return self.elements_prefix.keys()

  def check(self, element):
    object_id = element.get("objectId")
    tag = self.get_element_class(element)
    if object_id:
      if not object_id.startswith(self.elements_prefix[tag]):
        raise loggers.ElectionInfo.from_message(
            ("%s ID %s is not in Hungarian Style Notation. Should start with "
             " %s" % (tag, object_id, self.elements_prefix[tag])), [element])


class LanguageCode(base.BaseRule):
  """Check that Text elements have a valid language code."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if "language" not in element.attrib:
      return
    elem_lang = element.get("language")
    if (not elem_lang.strip() or not language_tags.tags.check(elem_lang)):
      raise loggers.ElectionError.from_message(
          "%s is not a valid language code" % elem_lang, [element])


class PercentSum(base.BaseRule):
  """Check that Contest elements have percents summing to 0 or 100."""

  def elements(self):
    return ["Contest"]

  @staticmethod
  def fuzzy_equals(a, b, epsilon=1e-6):
    return abs(a - b) < epsilon

  def check(self, element):
    sum_percents = 0.0
    for ballot_selection in element.findall("BallotSelection"):
      for vote_counts in (
          ballot_selection.find("VoteCountsCollection").findall("VoteCounts")):
        other_type = vote_counts.find("OtherType")
        if other_type is not None and other_type.text == "total-percent":
          sum_percents += float(vote_counts.find("Count").text)
    if (not PercentSum.fuzzy_equals(sum_percents, 0) and
        not PercentSum.fuzzy_equals(sum_percents, 100)):
      raise loggers.ElectionError.from_message(
          "Contest percents do not sum to 0 or 100: %f" % sum_percents,
          [element])


class EmptyText(base.BaseRule):
  """Check that Text elements are not strictly whitespace."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if element.text is not None and not element.text.strip():
      raise loggers.ElectionWarning.from_message("Text is empty", element)


class DuplicateID(base.TreeRule):
  """Check that the file does not contain duplicate object IDs."""

  def check(self):
    all_object_ids = set()
    error_log = []
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      if "objectId" not in element.attrib:
        continue
      else:
        obj_id = element.get("objectId")
        if not obj_id:
          continue
        if obj_id in all_object_ids:
          error_log.append(loggers.LogEntry("duplicate object ID", element))
        else:
          all_object_ids.add(obj_id)
    if error_log:
      raise loggers.ElectionError(error_log)


class ValidIDREF(base.BaseRule):
  """Check that IDREFs are valid.

  Every field of type IDREF should actually reference a value that exists in a
  field of type ID. Additionaly the referenced value should be an objectId
  of the proper reference type for the given field.
  """

  def __init__(self, election_tree, schema_tree):
    super(ValidIDREF, self).__init__(election_tree, schema_tree)
    self.object_id_mapping = {}
    self.element_reference_mapping = {}

  _REFERENCE_TYPE_OVERRIDES = {
      "ElectoralDistrictId": "GpUnit",
      "ElectionScopeId": "GpUnit",
      "AuthorityId": "Person",
      "AuthorityIds": "Person"
  }

  def setup(self):
    object_id_map = self._gather_object_ids_by_type()
    self.object_id_mapping = object_id_map

    element_reference_map = self._gather_reference_mapping()
    self.element_reference_mapping = element_reference_map

  def _gather_object_ids_by_type(self):
    """Create a mapping of element types to set of objectIds of same type."""

    type_obj_id_mapping = dict()
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      if "objectId" in element.attrib:
        obj_type = element.tag
        obj_id = element.get("objectId")
        if obj_id:
          type_obj_id_mapping.setdefault(obj_type, set([])).add(obj_id)
    return type_obj_id_mapping

  def _gather_reference_mapping(self):
    """Create a mapping of each IDREF(S) element to their reference type."""

    reference_mapping = dict()
    for _, element in etree.iterwalk(self.schema_tree):
      tag = self.strip_schema_ns(element)
      if (tag and tag == "element" and
          element.get("type") in ("xs:IDREF", "xs:IDREFS")):
        elem_name = element.get("name")
        reference_type = self._determine_reference_type(elem_name)
        reference_mapping[elem_name] = reference_type
    return reference_mapping

  def _determine_reference_type(self, name):
    """Determines the XML type being referenced by an IDREF(S) element."""

    for elem_type in self.object_id_mapping.keys():
      type_id = elem_type + "Id"
      if name.endswith(type_id) or name.endswith(type_id + "s"):
        return elem_type
    if name in self._REFERENCE_TYPE_OVERRIDES:
      return self._REFERENCE_TYPE_OVERRIDES[name]
    return None

  def elements(self):
    return list(self.element_reference_mapping.keys())

  def check(self, element):
    error_log = []

    element_name = element.tag
    element_reference_type = self.element_reference_mapping[element_name]
    reference_object_ids = self.object_id_mapping.get(element_reference_type,
                                                      [])
    if element.text:
      id_references = element.text.split()
      for id_ref in id_references:
        if id_ref not in reference_object_ids:
          error_log.append(
              loggers.LogEntry(("{} is not a valid IDREF. {} should contain an "
                                "objectId from a {} element.")
                               .format(id_ref, element_name,
                                       element_reference_type), element))
    if error_log:
      raise loggers.ElectionError(error_log)


class ValidStableID(base.BaseRule):
  """Ensure stable-ids are in the correct format."""

  def __init__(self, election_tree, schema_tree):
    super(ValidStableID, self).__init__(election_tree, schema_tree)
    regex = r"^[a-zA-Z0-9_-]+$"
    self.stable_id_matcher = re.compile(regex, flags=re.U)

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    stable_ids = get_external_id_values(element, "stable")
    error_log = []
    for s_id in stable_ids:
      if not self.stable_id_matcher.match(s_id):
        error_log.append(loggers.LogEntry(
            "Stable id '{}' is not in the correct format.".format(s_id),
            [element]))
    if error_log:
      raise loggers.ElectionError(error_log)


class ElectoralDistrictOcdId(base.BaseRule):
  """GpUnit referred to by ElectoralDistrictId MUST have a valid OCD-ID."""

  def elements(self):
    return ["ElectoralDistrictId"]

  def check(self, element):
    error_log = []
    gp_unit_path = ".//GpUnit[@objectId='{}']".format(element.text)
    referenced_gpunits = self.election_tree.findall(gp_unit_path)
    if not referenced_gpunits:
      msg = ("The ElectoralDistrictId element not refer to a GpUnit. Every "
             "ElectoralDistrictId MUST reference a GpUnit")
      error_log.append(loggers.LogEntry(msg, [element]))
    else:
      referenced_gpunit = referenced_gpunits[0]
      ocd_ids = get_external_id_values(referenced_gpunit, "ocd-id")
      if not ocd_ids:
        error_log.append(
            loggers.LogEntry("The referenced GpUnit %s does not have an ocd-id"
                             % element.text,
                             [element], [referenced_gpunit.sourceline]))
      else:
        for ocd_id in ocd_ids:
          if not gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd(ocd_id):
            error_log.append(
                loggers.LogEntry("The ElectoralDistrictId refers to GpUnit %s "
                                 "that does not have a valid OCD ID (%s)"
                                 % (element.text, ocd_id),
                                 [element], [referenced_gpunit.sourceline]))
    if error_log:
      raise loggers.ElectionError(error_log)


class GpUnitOcdId(base.BaseRule):
  """Any GpUnit that is a geographic district SHOULD have a valid OCD-ID."""

  districts = [
      "borough", "city", "county", "municipality", "state", "town", "township",
      "village"
  ]
  validate_ocd_file = True

  def elements(self):
    return ["ReportingUnit"]

  def check(self, element):
    gpunit_type = element.find("Type")
    if gpunit_type is not None and gpunit_type.text in self.districts:
      external_id_elements = get_external_id_values(
          element, "ocd-id", return_elements=True)
      for extern_id in external_id_elements:
        if not gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd(extern_id.text):
          msg = "The OCD ID %s is not valid" % extern_id.text
          raise loggers.ElectionWarning.from_message(
              msg, [element], [extern_id.sourceline])


class DuplicateGpUnits(base.BaseRule):
  """Detect GpUnits which are effectively duplicates of each other."""

  def elements(self):
    return ["GpUnitCollection"]

  def check(self, element):
    children = {}
    object_ids = set()
    error_log = []
    for gpunit in element.findall("GpUnit"):
      object_id = gpunit.get("objectId")
      if not object_id:
        continue
      elif object_id in object_ids:
        error_log.append(
            loggers.LogEntry("GpUnit is duplicated", [gpunit]))
        continue
      object_ids.add(object_id)
      composing_gpunits = gpunit.find("ComposingGpUnitIds")
      if composing_gpunits is None or not composing_gpunits.text:
        continue
      composing_ids = frozenset(composing_gpunits.text.split())
      if children.get(composing_ids):
        error_log.append(
            loggers.LogEntry("GpUnits {} are duplicates".format(
                str((children[composing_ids], object_id)))))
        continue
      children[composing_ids] = object_id
    if error_log:
      raise loggers.ElectionError(error_log)


class GpUnitsHaveSingleRoot(base.TreeRule):
  """Ensure that GpUnits form a single-rooted tree."""

  def __init__(self, election_tree, schema_tree):
    super(GpUnitsHaveSingleRoot, self).__init__(election_tree, schema_tree)
    self.error_log = []

  def check(self):
    # Make sure there's at most one GpUnit as a root.
    # The root is defined as having ComposingGpUnitIds but
    # is not in the ComposingGpUnitIds of any other GpUnit.

    gpunit_ids = set()
    composing_gpunits = set()
    for element in self.get_elements_by_class(self.election_tree, "GpUnit"):
      object_id = element.get("objectId")
      if object_id is not None:
        gpunit_ids.add(object_id)
      composing_gpunit = element.find("ComposingGpUnitIds")
      if composing_gpunit is not None and composing_gpunit.text is not None:
        composing_gpunits.update(composing_gpunit.text.split())

    roots = gpunit_ids - composing_gpunits

    if not roots:
      self.error_log.append(
          loggers.LogEntry("GpUnits have no geo district root. "
                           "There should be exactly one root geo district."))
    elif len(roots) > 1:
      self.error_log.append(
          loggers.LogEntry("GpUnits tree has more than one root: {0}".format(
              ", ".join(roots))))

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class GpUnitsCyclesRefsValidation(base.TreeRule):
  """Ensure that GpUnits form a valid tree and no cycles are present."""

  def __init__(self, election_tree, schema_tree):
    super(GpUnitsCyclesRefsValidation, self).__init__(election_tree,
                                                      schema_tree)
    self.edges = dict()  # Used to maintain the record of connected edges
    self.visited = {}  # Used to store status of the nodes as visited or not.
    self.error_log = []
    self.bad_nodes = []

  def build_tree(self, gpunit):
    # Check if the node is already visited
    if gpunit in self.visited:
      if gpunit not in self.bad_nodes:
        self.error_log.append(
            loggers.LogEntry("Cycle detected at node {0}".format(gpunit)))
        self.bad_nodes.append(gpunit)
      return
    self.visited[gpunit] = 1
    # Check each composing_gpunit and its edges if any.
    for child_unit in self.edges[gpunit]:
      if child_unit in self.edges:
        self.build_tree(child_unit)
      else:
        self.error_log.append(
            loggers.LogEntry(
                "Node {0} is not present in the file as a GpUnit element."
                .format(child_unit)))

  def check(self):
    for element in self.get_elements_by_class(self.election_tree, "GpUnit"):
      object_id = element.get("objectId")
      if object_id is None:
        continue
      self.edges[object_id] = []
      composing_gp_unit = element.find("ComposingGpUnitIds")
      if composing_gp_unit is None or composing_gp_unit.text is None:
        continue
      composing_gp_unit_ids = composing_gp_unit.text.split()
      self.edges[object_id] = composing_gp_unit_ids
    for gpunit in self.edges:
      self.build_tree(gpunit)
      self.visited.clear()

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class OtherType(base.BaseRule):
  """Elements with an "other" enum should set OtherType.

  Elements that have enumerations which include a value named other should
  -- when that enumeration value is other -- set the corresponding field
  OtherType within the containing element.
  """

  def elements(self):
    eligible_elements = []
    for element in self.schema_tree.iterfind("{%s}complexType" %
                                             self._XSCHEMA_NAMESPACE):
      for elem in element.iter():
        tag = self.strip_schema_ns(elem)
        if tag == "element":
          elem_name = elem.get("name")
          if elem_name and elem_name == "OtherType":
            eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    type_element = element.find("Type")
    if type_element is not None and type_element.text == "other":
      other_type_element = element.find("OtherType")
      if other_type_element is None:
        msg = ("Type on this element is set to 'other' but OtherType element "
               "is not defined")
        raise loggers.ElectionError.from_message(msg, [element])


class PartisanPrimary(base.BaseRule):
  """Partisan elections should link to the correct political party.

  For an Election element of Election type primary, partisan-primary-open,
  or partisan-primary-closed, the Contests in that ContestCollection should
  have a PrimartyPartyIds that is present and non-empty.
  """
  election_type = None

  def __init__(self, election_tree, schema_tree):
    super(PartisanPrimary, self).__init__(election_tree, schema_tree)
    # There can only be one election element in a file.
    election_elem = self.election_tree.find("Election")
    if election_elem is not None:
      election_type_elem = election_elem.find("Type")
      if election_type_elem is not None:
        self.election_type = election_type_elem.text.strip()

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_type_elem = election_elem.find("Type")
    election_type = None
    if element_has_text(election_type_elem):
      election_type = election_type_elem.text.strip()

    if not election_type or election_type not in ("partisan-primary-open",
                                                  "partisan-primary-closed"):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      primary_party_ids = contest_elem.find("PrimaryPartyIds")
      if not element_has_text(primary_party_ids):
        msg = (
            "Election is of ElectionType %s but PrimaryPartyIds is not present"
            " or is empty" % (self.election_type))
        raise loggers.ElectionWarning.from_message(msg, [election_elem])


class PartisanPrimaryHeuristic(base.BaseRule):
  """Attempts to identify partisan primaries not marked up as such."""

  # Add other strings that imply this is a primary contest.
  party_text = ["(dem)", "(rep)", "(lib)"]

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_type_elem = election_elem.find("Type")
    election_type = None
    if element_has_text(election_type_elem):
      election_type = election_type_elem.text.strip()

    if election_type is not None and election_type in (
        "primary", "partisan-primary-open", "partisan-primary-closed"):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      contest_name = contest_elem.find("Name")
      if element_has_text(contest_name):
        c_name = contest_name.text.replace(" ", "").lower()
        for p_text in self.party_text:
          if p_text in c_name:
            msg = ("Name of contest - %s, contains text that implies it is a "
                   "partisan primary but is not marked up as such." %
                   (contest_name.text))
            raise loggers.ElectionWarning.from_message(msg, [contest_elem])


class CoalitionParties(base.BaseRule):
  """Coalitions should always define the Party IDs."""

  def elements(self):
    return ["Coalition"]

  def check(self, element):
    party_id = element.find("PartyIds")
    if (party_id is None or not party_id.text or not party_id.text.strip()):
      raise loggers.ElectionError.from_message("Coalition must define PartyIDs",
                                               [element])


class UniqueLabel(base.BaseRule):
  """Labels should be unique within a file."""

  def __init__(self, election_tree, schema_tree):
    super(UniqueLabel, self).__init__(election_tree, schema_tree)
    self.labels = set()

  def elements(self):
    eligible_elements = []
    for _, element in etree.iterwalk(self.schema_tree):
      tag = self.strip_schema_ns(element)
      if tag == "element":
        elem_type = element.get("type")
        if elem_type == "InternationalizedText":
          if element.get("name") not in eligible_elements:
            eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    element_label = element.get("label")
    if element_label:
      if element_label in self.labels:
        msg = "Duplicate label '%s'. Label already defined" % element_label
        raise loggers.ElectionError.from_message(msg, [element])
      else:
        self.labels.add(element_label)


class CandidatesReferencedOnceOrInRelatedContests(base.BaseRule):
  """Candidate should not be referred to by multiple unrelated contests.

  A Candidate object should only be referenced from one contest, unless the
  contests are related (contests for the same office, and in the same party if
  applicable). If a Person is running in multiple unrelated Contests, then that
  Person is a Candidate several times over, but a Candida(te|cy) can't span
  unrelated contests.  Candidates across different Elections with the same
  stableId are treated as the same Candidate and should still only appear in
  related Contests.
  """

  def __init__(self, election_tree, schema_tree):
    super(CandidatesReferencedOnceOrInRelatedContests,
          self).__init__(election_tree, schema_tree)
    self.error_log = []

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    elections = self.get_elements_by_class(election_report_element, "Election")
    candidate_registry = self._register_candidates(election_report_element)
    [office_ids,
     party_ids] = self._get_contest_offices_and_parties(election_report_element)
    for cand_stable_id, contest_ids in candidate_registry.items():
      if len(contest_ids) > 1:
        if not self._is_contest_group_related(contest_ids, office_ids,
                                              party_ids):
          error_message = (
              "Candidate(s) with stableId {} is/are referenced by the following"
              " unrelated contests: {}.").format(cand_stable_id,
                                                 ", ".join(contest_ids))
          self.error_log.append(loggers.LogEntry(error_message))
      if not contest_ids:
        error_message = ("A Candidate should be referenced in a Contest. "
                         "Candidate with stableId {0} is not referenced."
                        ).format(cand_stable_id)
        self.error_log.append(loggers.LogEntry(error_message))
    if self.error_log:
      raise loggers.ElectionError(self.error_log)

  def _register_candidates(self, election_report):
    candidate_registry = {}
    candidate_object_id_to_stable_id = {}
    candidates = self.get_elements_by_class(election_report, "Candidate")
    for candidate in candidates:
      stable_ids = get_external_id_values(candidate, "stable")
      if len(stable_ids) != 1:
        # Skip candidate if not exactly one stable id.  Raise error if more than
        # one - missing stable id error raised in another test
        if len(stable_ids) > 1:
          raise loggers.ElectionError(
              "Candidate % has more than one stable id" %
              candidate.get("objectId"))
        continue
      stable_id = stable_ids[0]
      object_id = candidate.get("objectId", None)
      candidate_object_id_to_stable_id[object_id] = stable_id
      candidate_registry[stable_id] = []

    contests = self.get_elements_by_class(election_report, "Contest")
    for contest in contests:
      contest_id = contest.get("objectId", None)
      for child in contest.iter(tag=etree.Element):
        if "CandidateId" in child.tag and element_has_text(child):
          for cand_id in child.text.split():
            # bug in case the cand_id is an invalid one
            if cand_id not in candidate_object_id_to_stable_id:
              error_message = (
                  "Could not find Candidate {} in Contest {}.").format(
                      cand_id, contest_id)
              self.error_log.append(loggers.LogEntry(error_message))
              continue
            cand_stable_id = candidate_object_id_to_stable_id[cand_id]
            candidate_registry[cand_stable_id].append(contest_id)
    return candidate_registry

  def _get_contest_offices_and_parties(self, election_report):
    contests = self.get_elements_by_class(election_report, "Contest")
    office_ids = {}
    party_ids = {}
    for contest in contests:
      contest_id = contest.get("objectId")

      element = contest.find("OfficeIds")
      if element_has_text(element):
        office_ids[contest_id] = element.text

      element = contest.find("PrimaryPartyIds")
      if element_has_text(element):
        party_ids[contest_id] = set(element.text.split())
    return [office_ids, party_ids]

  def _is_contest_group_related(self, contest_ids, office_ids, party_ids):
    """Checks if the list of contest_ids are related.

    Args:
      contest_ids: a list of contest_ids to check
      office_ids: dict of contest_ids to OfficeId
      party_ids: dict of contest_ids to PrimaryPartyIds

    Returns:
      True iff the OfficeIds are the same for all contests and the
      PrimaryPartyIds are all the same or None.
    """

    office_id = None
    party_id_set = None
    for contest_id in contest_ids:
      current_office_id = office_ids.get(contest_id, None)
      if office_id is None:
        office_id = current_office_id
      elif office_id != current_office_id:
        return False

      current_party_id_set = party_ids.get(contest_id, None)
      if current_party_id_set:
        if party_id_set is None:
          party_id_set = current_party_id_set
        elif party_id_set != current_party_id_set:
          return False

    return True


class ProperBallotSelection(base.BaseRule):
  """BallotSelections should be correct for that type of contest.

  Ensure that the BallotSelection elements in a CandidateContest are
  CandidateSelections, PartyContests have PartySelections, etc, etc.
  """

  con_sel_mapping = {
      "BallotMeasureContest": "BallotMeasureSelection",
      "CandidateContest": "CandidateSelection",
      "PartyContest": "PartySelection",
      "RetentionContest": "BallotMeasureSelection"
  }

  def elements(self):
    return self.con_sel_mapping.keys()

  def check(self, element):
    tag = self.get_element_class(element)
    selections = []
    for c in self.con_sel_mapping:
      selections += self.get_elements_by_class(element, self.con_sel_mapping[c])
    for selection in selections:
      selection_tag = self.get_element_class(selection)
      if selection_tag != self.con_sel_mapping[tag]:
        contest_id = element.get("objectId")
        selection_id = selection.get("objectId")
        msg = ("The Contest does not contain the right BallotSelection. %s "
               "must have a %s but contains a %s, %s" %
               (tag, self.con_sel_mapping[tag], selection_tag, selection_id))
        raise loggers.ElectionError.from_message(msg, [element])


class PartiesHaveValidColors(base.BaseRule):
  """Each Party should have a valid hex Color without a leading '#'.

  A Party object that has no Color or an invalid Color should be picked up
  within this class and returned to the user as a warning.
  """

  def elements(self):
    return ["Party"]

  def check(self, element):
    colors = element.findall("Color")
    if not colors:
      return
    if len(colors) > 1:
      raise loggers.ElectionWarning.from_message(
          "The Party has more than one color.", [element])
    color_val = colors[0].text
    if not color_val:
      raise loggers.ElectionWarning.from_message(
          "Color tag is missing a value.", [colors[0]])
    else:
      try:
        int(color_val, 16)
      except ValueError:
        raise loggers.ElectionWarning.from_message(
            "%s is not a valid hex color." % color_val, [colors[0]])


class PersonHasUniqueFullName(base.BaseRule):
  """A Person should be defined one time in <PersonCollection>.

  The main purpose of this check is to spot redundant person definition.
  If two people have the same full name and date of birhthday, a warning will
  be raised. So, we can check if the feed is coherent.
  """

  def elements(self):
    return ["PersonCollection"]

  def extract_person_fullname(self, person):
    """Extracts the person's fullname or builds it if needed."""
    full_name_elt = person.find("FullName")
    if full_name_elt is not None:
      names = full_name_elt.findall("Text")
      if names:
        full_name_list = set()
        for name in names:
          if name.text:
            full_name_list.add(name.text)
        return full_name_list

    full_name = ""
    first_name_elt = person.find("FirstName")
    if first_name_elt is not None and first_name_elt.text:
      full_name += (first_name_elt.text + " ")
    middle_name_elt = person.find("MiddleName")
    if middle_name_elt is not None and middle_name_elt.text:
      full_name += (middle_name_elt.text + " ")
    last_name_elt = person.find("LastName")
    if last_name_elt is not None and last_name_elt.text:
      full_name += last_name_elt.text

    return {full_name}

  def check_specific(self, people):
    person_def = collections.namedtuple("PersonDefinition",
                                        ["fullname", "birthday"])
    person_id_to_object_id = {}

    info_log = []
    for person in people:
      person_object_id = person.get("objectId")
      full_name_list = self.extract_person_fullname(person)
      date_of_birthday = person.find("DateOfBirth")
      birthday_val = "Undefined"
      if date_of_birthday is not None and date_of_birthday.text:
        birthday_val = date_of_birthday.text

      for full_name_val in full_name_list:
        person_id = person_def(full_name_val, birthday_val)
        if person_id in person_id_to_object_id and person_id_to_object_id[
            person_id] != person_object_id:
          info_message = (
              "Person has same full name '%s' and birthday %s as Person %s." %
              (full_name_val, birthday_val, person_id_to_object_id[person_id]))
          info_log.append(loggers.LogEntry(info_message, [person]))
        else:
          person_id_to_object_id[person_id] = person_object_id
    return info_log

  def check(self, element):
    info_log = []
    people = element.findall("Person")
    if len(people) < 1:
      info_log.append(
          loggers.LogEntry("<PersonCollection> does not have <Person> objects",
                           [element]))
    info_log.extend(self.check_specific(people))
    if info_log:
      raise loggers.ElectionInfo(info_log)


class ValidatePartyCollection(base.BaseRule):
  """Generic party collection validation rule.

  All partyCollection validation rules can inherit from this class since it
  contains basic checks.
  """

  def elements(self):
    return ["PartyCollection"]

  def check_specific(self, parties):
    """Return a list of info log to be raised."""
    raise NotImplementedError

  def check(self, element):
    info_log = []
    parties = element.findall("Party")
    if len(parties) < 1:
      info_message = "<PartyCollection> does not have <Party> objects"
      info_log.append(loggers.LogEntry(info_message, element))
    info_log.extend(self.check_specific(parties))
    if info_log:
      raise loggers.ElectionInfo(info_log)


class ValidateDuplicateColors(ValidatePartyCollection):
  """Each Party should have unique hex color.

  A Party object that has duplicate color should be picked up
  within this class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    party_colors = {}
    info_log = []
    for party in parties:
      color_element = party.find("Color")
      if color_element is None:
        continue
      color = color_element.text
      if color is None:
        continue
      if color in party_colors:
        party_colors[color].append(party)
      else:
        party_colors[color] = [party]

    for color, parties in party_colors.items():
      if len(parties) > 1:
        info_log.append(loggers.LogEntry(
            "Parties has the same color %s." % color, parties))
    return info_log


class DuplicatedPartyAbbreviation(ValidatePartyCollection):
  """Party abbreviation should be used once in a given language.

  If an abbreviation is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    party_abbrs_by_language = {}
    for party in parties:
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = ("<Party> does not have <InternationalizedAbbreviation> "
                        "objects")
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_abbrs = abbr_element.findall("Text")
      for party_abbr in party_abbrs:
        language = party_abbr.get("language")
        abbr = party_abbr.text
        if language not in party_abbrs_by_language:
          party_abbrs_by_language[language] = {}
        if abbr in party_abbrs_by_language[language]:
          party_abbrs_by_language[language][abbr].append(party)
        else:
          party_abbrs_by_language[language][abbr] = [party]

    for language, abbrs in party_abbrs_by_language.items():
      for abbr, parties in abbrs.items():
        if len(parties) > 1:
          info_message = "Parties have the same abbreviation in %s." % language
          info_log.append(loggers.LogEntry(info_message, parties))
    return info_log


class DuplicatedPartyName(ValidatePartyCollection):
  """Party name should be used once in a given language.

  If a party name is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    party_names_by_language = {}
    for party in parties:
      name_element = party.find("Name")
      if name_element is None:
        info_message = "<Party> does not have <Name> objects"
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_names = name_element.findall("Text")
      for party_name in party_names:
        language = party_name.get("language")
        name = party_name.text
        if language not in party_names_by_language:
          party_names_by_language[language] = {}
        if name in party_names_by_language[language]:
          party_names_by_language[language][name].append(party)
        else:
          party_names_by_language[language][name] = [party]

    for language, names in party_names_by_language.items():
      for name, parties in names.items():
        if len(parties) > 1:
          info_message = "Parties have the same name in %s." % language
          info_log.append(loggers.LogEntry(info_message, parties))
    return info_log


class MissingPartyNameTranslation(ValidatePartyCollection):
  """All Parties should have their name translated to the same languages.

  If there is a party name that is not translated to all the feed languages,
  the party should be picked up within this class and returned to the user as
  an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      name_element = party.find("Name")
      if name_element is None:
        info_message = "<Party> does not have <Name> objects"
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_names = name_element.findall("Text")
      party_languages = set()
      for party_name in party_names:
        language = party_name.get("language")
        if language not in feed_languages:
          feed_languages.add(language)
          if feed_party_ids:
            info_message = (
                "The feed is missing names translation to %s for parties : %s."
                % (language, feed_party_ids))
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party name is not translated to all feed languages %s. You "
            "did it only for the following languages : %s." %
            (feed_languages, party_languages))
        info_log.append(loggers.LogEntry(info_message, [party]))
    return info_log


class MissingPartyAbbreviationTranslation(ValidatePartyCollection):
  """Every party's abbreviation should be translated to the same languages.

  If a party is missing a name translation, it should be picked up within this
  class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = ("<Party> does not have <InternationalizedAbbreviation>"
                        " objects")
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_abbrs = abbr_element.findall("Text")
      party_languages = set()
      for party_abbr in party_abbrs:
        language = party_abbr.get("language")
        if language not in feed_languages:
          feed_languages.add(language)
          if feed_party_ids:
            info_message = (
                "The feed is missing abbreviation translation to %s for parties"
                " : %s." % (language, feed_party_ids))
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party abbreviation is not translated to all feed languages %s."
            " You only did it for the following languages : %s." %
            (feed_languages, party_languages))
        info_log.append(loggers.LogEntry(info_message, [party]))
    return info_log


class DuplicateContestNames(base.BaseRule):
  """Check that an election contains unique ContestNames.

  Add Warning if duplicate ContestName found.
  """

  def elements(self):
    return ["ContestCollection"]

  def check(self, election_elt):
    # Mapping for <Name> and its Contest ObjectId.
    error_log = []
    name_contest_id = {}
    contest_elts = election_elt.findall("Contest")
    if contest_elts is None:
      error_message = "ContestCollection is Empty."
      error_log.append(loggers.LogEntry(error_message, [election_elt]))
    for element in contest_elts:
      name = element.find("Name")
      if name is None or not name.text:
        error_message = "The contest is missing a <Name> "
        error_log.append(
            loggers.LogEntry(error_message, [element]))
        continue
      name_contest_id.setdefault(name.text, []).append(element)

    for name, contests in name_contest_id.items():
      if len(contests) > 1:
        error_log.append(loggers.LogEntry(
            "Contests have the same name %s." % name, contests))
    if error_log:
      raise loggers.ElectionError(error_log)


class MissingStableIds(base.BaseRule):
  """Check that each NIST object in the feed have a stable Id.

  Add an error message if stable id is missing from the object.
  """

  def elements(self):
    return [
        "Candidate", "Contest", "Party", "Person", "Coalition",
        "BallotMeasureSelection", "Office", "ReportingUnit"
    ]

  def check(self, element):
    element_name = self.strip_schema_ns(element)
    object_id = element.get("objectId")
    stable_ids = get_external_id_values(element, "stable")
    if not stable_ids:
      raise loggers.ElectionError.from_message(
          "The element is missing a stable id", [element])


class PersonsMissingPartyData(base.BaseRule):
  """Each Officeholder Person should have a Party associated with it.

  A Person object must contain a PartyId, and if not, it should be picked
  up within this class and returned to the user as a warning.
  """

  def elements(self):
    return ["Person"]

  def check(self, element):
    party_id = element.find("PartyId")
    if party_id is None or not party_id.text or party_id.text.isspace():
      raise loggers.ElectionWarning.from_message(
          "The person is missing party data", [element])


class AllCaps(base.BaseRule):
  """Name elements should not be in all uppercase.

  If the name elements in Candidates, Contests and Person elements are in
  uppercase, the list of objectIds of those elements will be returned to
  the user as a warning.
  """

  _element_field_mapping = {
      "Candidate": ["BallotName//Text"],
      "CandidateContest": ["Name"],
      "PartyContest": ["Name"],
      "Person": ["FullName//Text"]
  }

  def elements(self):
    return list(self._element_field_mapping.keys())

  def check(self, element):
    error_log = []

    element_tag = self.get_element_class(element)
    to_check_field_tags = self._element_field_mapping[element_tag]
    for field_tag in to_check_field_tags:
      to_check_field = element.find(field_tag)
      if to_check_field is not None:
        text_value = to_check_field.text
        if text_value and text_value.isupper():
          raise loggers.ElectionWarning.from_message(
              "{0} has {1} in all upper case letters.".format(
                  element_tag, field_tag), [element])


class AllLanguages(base.BaseRule):
  """Verify that required languages are present in Text fields.

    The Text elements in all entities with those fields should cover all
    required languages for this schema.
  """
  required_languages = []

  def elements(self):
    return ["BallotName", "BallotTitle", "FullName", "Name"]

  def check(self, element):
    text_elements = element.findall("Text")
    if not text_elements:
      return
    languages = set()
    for text in text_elements:
      languages.add(text.attrib["language"])
    required_language_set = frozenset(self.required_languages)
    if not required_language_set.issubset(languages):
      msg = ("Element does not contain text in all required languages, missing"
             + " : %s" % str(required_language_set - languages))
      raise loggers.ElectionError.from_message(msg, [element])


class ValidEnumerations(base.BaseRule):
  """Valid enumerations should not be encoded as 'OtherType'.

  Elements that have valid enumerations should not be included
  as 'OtherType'. Instead, the corresponding <Type> field
  should include the actual valid enumeration value.
  """

  valid_enumerations = []

  def elements(self):
    eligible_elements = []
    for element in self.schema_tree.iter():
      tag = self.strip_schema_ns(element)
      if tag == "enumeration":
        elem_val = element.get("value")
        if elem_val and elem_val != "other":
          self.valid_enumerations.append(elem_val)
      elif tag == "complexType":
        for elem in element.iter():
          tag = self.strip_schema_ns(elem)
          if tag == "element":
            elem_name = elem.get("name")
            if elem_name and element.get("name") and elem_name == "OtherType":
              if element.get("name") == "ExternalIdentifiers":
                eligible_elements.append("ExternalIdentifier")
                continue
              eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    type_element = element.find("Type")
    if type_element is not None and type_element.text == "other":
      other_type_element = element.find("OtherType")
      if (other_type_element is not None and
          other_type_element.text in self.valid_enumerations):
        raise loggers.ElectionError.from_message(
            ("Type is set to 'other' even though '%s' is a valid "
             "enumeration"% other_type_element.text), [element])


class ValidateOcdidLowerCase(base.BaseRule):
  """Validate that the ocd-ids are all lower case.

  Throw a warning if the ocd-ids are not all in lowercase.
  """

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    for ocd_id in get_external_id_values(element, "ocd-id"):
      if not ocd_id.islower():
        msg = ("OCD-ID %s is not in all lower case letters. "
               "Valid OCD-IDs should be all lowercase." % (ocd_id))
        raise loggers.ElectionWarning.from_message(msg, [element])


class ContestHasMultipleOffices(base.BaseRule):
  """Ensure that each contest has exactly one Office."""

  def elements(self):
    return ["Contest"]

  def check(self, element):
    # for each contest, get the <officeids> entity
    office_ids = element.find("OfficeIds")
    if office_ids is not None and office_ids.text:
      ids = office_ids.text.split()
      if len(ids) > 1:
        raise loggers.ElectionWarning.from_message(
            "Contest has more than one associated office.", [element])
    else:
      raise loggers.ElectionWarning.from_message(
          "Contest has no associated offices.", [element])


class PersonHasOffice(base.ValidReferenceRule):
  """Ensure that each non-party-leader Person object linked to one Office."""

  def _gather_reference_values(self):
    root = self.election_tree.getroot()

    person_ids = set()
    person_collection = root.find("PersonCollection")
    if person_collection is not None:
      person_ids = {p.attrib["objectId"] for p in person_collection}
    return person_ids

  def _gather_defined_values(self):
    root = self.election_tree.getroot()

    person_reference_ids = set()
    for external_id in root.findall(".//Party//ExternalIdentifier"):
      other_type = external_id.find("OtherType")
      if other_type is not None and other_type.text in _PARTY_LEADERSHIP_TYPES:
        person_reference_ids.add(external_id.find("Value").text)

    office_collection = root.find("OfficeCollection")
    if office_collection is not None:
      for office in office_collection.findall("Office"):
        id_obj = office.find("OfficeHolderPersonIds")
        if id_obj is not None and id_obj.text:
          ids = id_obj.text.strip().split()
          if len(ids) > 1:
            msg = "Office has {} OfficeHolders. Must have exactly one.".format(
                str(len(ids)))
            raise loggers.ElectionError.from_message(msg, [office])
          person_reference_ids.update(ids)

    return person_reference_ids


class PartyLeadershipMustExist(base.ValidReferenceRule):
  """Each party leader or party chair should refer to a person in the feed."""

  def __init__(self, election_tree, schema_tree):
    super(PartyLeadershipMustExist, self).__init__(election_tree, schema_tree,
                                                   "Person")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    if root is None:
      return

    party_leader_ids = set()
    for external_id in root.findall(".//Party//ExternalIdentifier"):
      other_type = external_id.find("OtherType")
      if other_type is not None and other_type.text in _PARTY_LEADERSHIP_TYPES:
        party_leader_ids.add(external_id.find("Value").text)
    return party_leader_ids

  def _gather_defined_values(self):
    root = self.election_tree.getroot()
    if root is None:
      return

    persons = root.find("PersonCollection")
    all_person_ids = set()
    if persons is not None:
      all_person_ids = {person.attrib["objectId"] for person in persons}
    return all_person_ids


class ProhibitElectionData(base.TreeRule):
  """Ensure that election data is not provided for officeholder feeds."""

  def check(self):
    root = self.election_tree.getroot()
    if root is not None and root.find("Election") is not None:
      raise loggers.ElectionError.from_message(
          "Election data is prohibited in officeholder feeds.")


class PersonsHaveValidGender(base.BaseRule):
  """Ensure that all Person objects have a valid gender identification."""

  _VALID_GENDERS = {
      "male", "m", "man", "female", "f", "woman", "o", "x", "other", "nonbinary"
  }

  def elements(self):
    return ["Gender"]

  def check(self, element):
    if (element.text is not None and
        element.text.lower() not in self._VALID_GENDERS):
      raise loggers.ElectionError("Person object has invalid gender value: %s" %
                                  element.text)


class VoteCountTypesCoherency(base.BaseRule):
  """Ensure VoteCount types describe the appropriate votable."""

  PARTY_VC_TYPES = {
      "seats-won", "seats-leading", "party-votes", "seats-no-election",
      "seats-total", "seats-delta"
  }
  # Ibid.
  CAND_VC_TYPES = {"candidate-votes"}

  def elements(self):
    return ["Contest"]

  def check(self, element):
    invalid_vc_types = None
    contest_type = ""
    if element.get("type", "") == "CandidateContest":
      invalid_vc_types = self.PARTY_VC_TYPES
      contest_type = "Candidate"
    elif element.get("type", "") == "PartyContest":
      invalid_vc_types = self.CAND_VC_TYPES
      contest_type = "Party"
    if invalid_vc_types:
      errors = []
      for ballot_selection in element.findall("BallotSelection"):
        for vote_counts in (ballot_selection.find(
            "VoteCountsCollection").findall("VoteCounts")):
          vc_type = vote_counts.find("OtherType").text
          if vc_type in invalid_vc_types:
            errors.append(vc_type)
      if errors:
        msg = "VoteCount types {0} should not be nested in {1} Contest".format(
            ", ".join(errors), contest_type)
        raise loggers.ElectionError.from_message(msg, [element])


class URIValidator(base.BaseRule):
  """Basic URL validations.

  Ensure each URL has valid protocol, domain, and query.
  """

  def elements(self):
    return ["Uri"]

  def check(self, element):
    url = element.text
    if url is None:
      raise loggers.ElectionError.from_message("Missing URI value.", [element])

    parsed_url = urlparse(url)
    discrepencies = []

    try:
      url.encode("ascii")
    except UnicodeEncodeError:
      discrepencies.append("not ascii encoded")

    if parsed_url.scheme not in {"http", "https"}:
      discrepencies.append("protocol - invalid")
    if not parsed_url.netloc:
      discrepencies.append("domain - missing")

    if discrepencies:
      msg = "The provided URI, {}, is invalid for the following reasons: {}.".format(
          url.encode("ascii", "ignore"), ", ".join(discrepencies))
      raise loggers.ElectionError.from_message(msg, [element])


class UniqueURIPerAnnotationCategory(base.TreeRule):
  """Check that annotated URIs for each category are unique.

  Ex: No ballotpedia URIs can be the same.
  """

  def _extract_uris_by_category(self, uri_elements):
    """For given list of Uri elements return nested paths of Uri values.

    Args:
      uri_elements: List of Uri elements
    Returns:
      Top level dict contains Annotation values as keys with uri/paths mapping
      as value.
    """
    uri_mapping = {}
    for uri in uri_elements:
      annotation = uri.get("Annotation", "").strip()
      annotation_elements = annotation.split("-")
      annotation_platform = ""
      if annotation_elements:
        annotation_platform = annotation_elements[-1]

      uri_value = uri.text

      if annotation_platform not in uri_mapping.keys():
        uri_mapping[annotation_platform] = {}

      if uri_mapping[annotation_platform].get(uri_value):
        uri_mapping[annotation_platform][uri_value].append(uri)
      else:
        uri_mapping[annotation_platform][uri_value] = [uri]
    return uri_mapping

  def check(self):
    all_uri_elements = self.get_elements_by_class(self.election_tree, "Uri")
    office_uri_elements = self.get_elements_by_class(
        self.election_tree, "Office//ContactInformation//Uri")
    uri_elements = set(all_uri_elements) - set(office_uri_elements)
    annotation_mapper = self._extract_uris_by_category(uri_elements)

    error_log = []
    for annotation, value_counter in annotation_mapper.items():
      for uri, uri_elements in value_counter.items():
        if len(uri_elements) > 1:
          error_message = ("The Uris contain the annotation type '{}' with the "
                           "same value '{}'.").format(annotation, uri)
          error_log.append(loggers.LogEntry(error_message, uri_elements))

    if error_log:
      raise loggers.ElectionWarning(error_log)


class ValidURIAnnotation(base.BaseRule):
  """Validate annotations on candidate/officeholder URLs.

  Ensure they describe the type of URL presented.
  Throws Warnings and Errors depending on type of invalidity.
  """

  TYPE_PLATFORMS = frozenset([
      "facebook", "twitter", "instagram", "youtube", "website", "line",
      "linkedin"
  ])
  USAGE_TYPES = frozenset(["personal", "official", "campaign"])
  PLATFORM_ONLY_ANNOTATIONS = frozenset(["wikipedia", "ballotpedia"])

  def elements(self):
    return ["ContactInformation"]

  def check_url(self, uri, annotation, platform):
    url = uri.text.strip()
    parsed_url = urlparse(url)
    # Ensure media platform name is in URL.
    if (platform != "website" and platform not in parsed_url.netloc and
        not (platform == "facebook" and "fb.com" in parsed_url.netloc)):
      # Note that the URL is encoded for printing purposes
      raise loggers.ElectionError.from_message(
          "Annotation '{}' is incorrect for URI {}.".format(
              annotation, url.encode("ascii", "ignore")), [uri])

  def check(self, element):
    uris = element.findall("Uri")

    for uri in uris:
      annotation = uri.get("Annotation", "").strip()
      url = uri.text.strip()
      ascii_url = url.encode("ascii", "ignore")

      if not annotation:
        raise loggers.ElectionWarning.from_message(
            "URI {} is missing annotation.".format(ascii_url), [uri])

      # Only do platform checks if the annotation is not an image.
      if not re.search(r"candidate-image", annotation):
        ann_elements = annotation.split("-")
        if len(ann_elements) == 1:
          platform = ann_elements[0]
          # One element would imply the annotation could be a platform
          # without a usage type, which is checked here.
          if platform in self.TYPE_PLATFORMS:
            raise loggers.ElectionWarning.from_message(
                "Annotation '{}' missing usage type.".format(annotation), [uri])
          elif platform in self.USAGE_TYPES:
            raise loggers.ElectionError.from_message(
                "Annotation '{}' has usage type, missing platform.".format(
                    annotation), [uri])
          elif platform not in self.PLATFORM_ONLY_ANNOTATIONS:
            raise loggers.ElectionError.from_message(
                "Annotation '{}' is not a valid annotation for URI {}.".format(
                    annotation, ascii_url), [uri])
        elif len(ann_elements) == 2:
          # Two elements at this stage would mean the annotation
          # must be a platform with a usage type.
          usage_type, platform = ann_elements
          if (usage_type not in self.USAGE_TYPES or
              platform not in self.TYPE_PLATFORMS):
            raise loggers.ElectionWarning.from_message(
                "'{}' is not a valid annotation.".format(annotation), [uri])
        else:
          # More than two implies an invalid annotation.
          raise loggers.ElectionError.from_message(
              "Annotation '{}' is invalid for URI {}.".format(
                  annotation, ascii_url), [uri])
        # Finally, check platform is in the URL.
        self.check_url(uri, annotation, platform)


class OfficesHaveJurisdictionID(base.BaseRule):
  """Each office must have a jurisdiction-id."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    jurisdiction_values = get_entity_info_for_value_type(
        element, "jurisdiction-id")
    jurisdiction_values = [
        j_id for j_id in jurisdiction_values if j_id.strip()
    ]
    if not jurisdiction_values:
      raise loggers.ElectionError.from_message(
          "Office is missing a jurisdiction-id.", [element])
    if len(jurisdiction_values) > 1:
      raise loggers.ElectionError.from_message(
          "Office has more than one jurisdiction-id.", [element])


class ValidJurisdictionID(base.ValidReferenceRule):
  """Each jurisdiction id should refer to a valid GpUnit."""

  def __init__(self, election_tree, schema_tree):
    super(ValidJurisdictionID, self).__init__(election_tree, schema_tree,
                                              "GpUnit")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    jurisdiction_values = get_entity_info_for_value_type(
        root, "jurisdiction-id")
    return set(jurisdiction_values)

  def _gather_defined_values(self):
    gp_unit_elements = self.election_tree.getroot().findall(".//GpUnit")
    return {elem.get("objectId") for elem in gp_unit_elements}


class OfficesHaveValidOfficeLevel(base.BaseRule):
  """Each office must have a valid office-level."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_level_values = [
        ol_id.strip()
        for ol_id in get_external_id_values(element, "office-level")
        if ol_id.strip()
    ]
    if not office_level_values:
      raise loggers.ElectionError.from_message(
          "Office is missing an office-level.", [element])
    if len(office_level_values) > 1:
      raise loggers.ElectionError.from_message(
          "Office has more than one office-level.", [element])
    office_level_value = office_level_values[0]
    if office_level_value not in office_utils.valid_office_level_values:
      raise loggers.ElectionError.from_message(
          "Office has invalid office-level {}.".format(office_level_value),
          [element])


class OfficesHaveValidOfficeRole(base.BaseRule):
  """Each office must have a valid office-role."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_role_values = [
        office_role_value.strip()
        for office_role_value in get_external_id_values(element, "office-role")
    ]
    if not office_role_values:
      raise loggers.ElectionError.from_message(
          "The office is missing an office-role.", [element])
    if len(office_role_values) > 1:
      raise loggers.ElectionError.from_message(
          "The office has more than one office-role.", [element])
    office_role_value = office_role_values[0]
    if office_role_value not in office_utils.valid_office_role_values:
      raise loggers.ElectionError.from_message(
          "The office has invalid office-role '{}'.".format(office_role_value),
          [element])


class ElectionStartDates(base.DateRule):
  """Election elements should contain valid start dates.

  Start dates in the past should raise a warning. This is not an error
  as validator could conceivably be run during an ongoing election.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_date:
      self.check_for_date_not_in_past(self.start_date, self.start_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ElectionEndDates(base.DateRule):
  """Election elements should contain valid end dates.

  End dates should be a present or future date and should not occur
  before the start date.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date:
      self.check_for_date_not_in_past(self.end_date, self.end_elem)
      if self.start_date:
        self.check_end_after_start()

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class OfficeTermDates(base.DateRule):
  """Office elements should contain valid term dates.

  Offices with OfficeHolderPersonIds should have a Term declared. Given
  term should have a start date. If term also has an end date then end date
  should come after start date.
  """

  def elements(self):
    return ["Office"]

  def check(self, element):
    self.reset_instance_vars()
    off_per_id = element.find("OfficeHolderPersonIds")
    if element_has_text(off_per_id):
      term = element.find("Term")
      if term is None:
        raise loggers.ElectionWarning.from_message(
            "The Office is missing a Term.", [element])

      self.gather_dates(term)
      if self.start_date is None:
        raise loggers.ElectionWarning.from_message(
            "The Office is missing a Term > StartDate.", [element])
      elif self.end_date is not None:
        self.check_end_after_start()

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class UniqueStartDatesForOfficeRoleAndJurisdiction(base.BaseRule):
  """Office StartDates should be unique within a certain group.

  Office StartDates should be unique amongst a group of Office entries
  with the same jurisdiction-id and office-role.
  """

  def elements(self):
    return ["OfficeCollection"]

  def _filter_out_past_end_dates(self, offices):
    valid_offices = []
    for office in offices:
      term = office.find(".//Term")
      if term is not None:
        date_validator = base.DateRule(None, None)
        try:
          date_validator.gather_dates(term)
          if date_validator.end_date is not None:
            date_validator.check_for_date_not_in_past(
                date_validator.end_date, date_validator.end_elem)
          if not date_validator.error_log:
            valid_offices.append(office)
        except loggers.ElectionError:
          continue
    return valid_offices

  def _count_start_dates_by_jurisdiction_role(self, element):
    offices = element.findall("Office")
    offices = self._filter_out_past_end_dates(offices)
    jurisdiction_role_mapping = {}
    for office in offices:
      office_role = ""
      jurisdiction_id = ""
      start_date = ""

      start_date_elem = office.find(
          ".//Term//StartDate"
      )
      if not element_has_text(start_date_elem):
        continue
      start_date = start_date_elem.text

      office_roles = get_entity_info_for_value_type(office, "office-role")
      if office_roles:
        office_role = office_roles[0]

      jurisdiction_ids = get_entity_info_for_value_type(
          office, "jurisdiction-id")
      if jurisdiction_ids:
        jurisdiction_id = jurisdiction_ids[0]

      office_hash = hashlib.sha256((
          office_role + jurisdiction_id
      ).encode("utf-8")).hexdigest()
      if office_hash not in jurisdiction_role_mapping.keys():
        jurisdiction_role_mapping[office_hash] = dict({
            "jurisdiction_id": jurisdiction_id,
            "office_role": office_role,
            "start_dates": dict({}),
        })

      office_date_info = jurisdiction_role_mapping[office_hash]
      if start_date not in office_date_info["start_dates"].keys():
        office_date_info["start_dates"][start_date] = set()

      office_date_info["start_dates"][start_date].add(office)

    return jurisdiction_role_mapping

  def check(self, element):
    warning_log = []

    start_counts = self._count_start_dates_by_jurisdiction_role(element)
    for start_info in start_counts.values():
      start_date_map = start_info["start_dates"]
      if len(start_date_map.keys()) == 1:
        start_date = list(start_date_map.keys())[0]
        # this accounts for offices with only one entry (i.e. US Pres)
        if len(start_date_map[start_date]) > 1:
          warning_log.append(loggers.LogEntry(
              ("Only one unique StartDate found for each jurisdiction-id: {} "
               "and office-role: {}. {} appears {} times.").format(
                   start_info["jurisdiction_id"], start_info["office_role"],
                   start_date, len(start_date_map[start_date])),
              start_date_map[start_date]))

    if warning_log:
      raise loggers.ElectionWarning(warning_log)


class GpUnitsHaveInternationalizedName(base.BaseRule):
  """GpUnits must have at least one non-empty InternationlizedName element."""

  def elements(self):
    return ["GpUnit"]

  def check(self, element):
    intl_names = element.findall("InternationalizedName")
    object_id = element.get("objectId", "")
    if intl_names is None or not intl_names or len(intl_names) > 1:
      raise loggers.ElectionError.from_message(
          "GpUnit is required to have exactly one InterationalizedName element."
          , [element])
    intl_name = intl_names[0]
    name_texts = intl_name.findall("Text")
    if name_texts is None or not name_texts:
      raise loggers.ElectionError.from_message(
          ("GpUnit InternationalizedName is required to have one or more Text "
           "elements."), [intl_name])
    error_log = []
    for name_text in name_texts:
      if name_text is None or not (name_text.text and name_text.text.strip()):
        error_log.append(loggers.LogEntry(
            "GpUnit InternationalizedName does not have a text value.",
            [name_text]))

    if error_log:
      raise loggers.ElectionError(error_log)


class FullTextMaxLength(base.BaseRule):
  """FullText field should not be longer than MAX_LENGTH."""

  MAX_LENGTH = 30000  # about 8-10 pages of text, 4500-5000 words

  def elements(self):
    return ["FullText"]

  def check(self, element):
    intl_text_list = element.findall("Text")
    for intl_text in intl_text_list:
      if len(intl_text.text) > self.MAX_LENGTH:
        msg = ("FullText is longer than %s characters. Please remove and "
               "include a link to the full text via InfoUri with Annotation "
               "'fulltext'." % (self.MAX_LENGTH))
        raise loggers.ElectionWarning.from_message(msg, [element])


class FullTextOrBallotText(base.BaseRule):
  """Warn if BallotText is missing and FullText is short."""

  SUGGESTION_CUTOFF_LENGTH = 2500  # about 3 paragraphs, 250-300 words

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    full_text_map = get_language_to_text_map(element.find("FullText"))
    if not full_text_map:
      return

    ballot_text_map = get_language_to_text_map(element.find("BallotText"))
    for language, full_text_string in full_text_map.items():
      if language not in ballot_text_map.keys(
      ) and len(full_text_string) < self.SUGGESTION_CUTOFF_LENGTH:
        msg = ("Language: %s.  BallotText is missing but FullText is present "
               "for the same language. Please confirm that FullText contains "
               "only supplementary text and not text on the ballot itself." %
               (language))
        raise loggers.ElectionWarning.from_message(msg, [element])


class BallotTitle(base.BaseRule):
  """BallotTitle must exist and should usually be shorter than BallotText."""

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    ballot_title_map = get_language_to_text_map(element.find("BallotTitle"))
    if not ballot_title_map:
      raise loggers.ElectionError.from_message(
          "BallotMeasureContest is missing BallotTitle.", [element])

    ballot_text_map = get_language_to_text_map(element.find("BallotText"))
    if not ballot_text_map:
      msg = ("BallotText is missing. Please confirm that the ballot "
             "text/question is not in BallotTitle.")
      raise loggers.ElectionWarning.from_message(msg, [element])

    for language, ballot_title_string in ballot_title_map.items():
      if language not in ballot_text_map.keys() or len(
          ballot_text_map[language]) < len(ballot_title_string):
        msg = ("Language: %s. BallotText is missing or shorter than "
               " Please confirm that the ballot text/question is not "
               "in BallotTitle." % (language))
        raise loggers.ElectionWarning.from_message(msg, [element])


class ImproperCandidateContest(base.TreeRule):
  """Detect CandidateContest elements that should be a BallotMeasureContest."""

  _BALLOT_SELECTION_OPTIONS = frozenset({"yes", "no", "for", "against"})

  def _gather_contest_candidates(self, contest):
    """Return candidate ids for given contest element."""
    candidate_ids = []
    cand_id_elems = contest.findall("BallotSelection//CandidateIds")
    for cand_id_elem in cand_id_elems:
      for cand_id in cand_id_elem.text.split():
        candidate_ids.append(cand_id)
    return candidate_ids

  def _gather_invalid_candidates(self):
    """Return candidate ids that appear to be BallotMeasureSelections."""
    invalid_candidates = []
    candidates = self.get_elements_by_class(self.election_tree,
                                            "CandidateCollection//Candidate")
    for candidate in candidates:
      ballot_name = candidate.find(".//BallotName/Text[@language='en']")
      if ballot_name is not None:
        if ballot_name.text.lower() in self._BALLOT_SELECTION_OPTIONS:
          invalid_candidates.append(candidate.get("objectId"))
    return invalid_candidates

  def check(self):
    candidate_contest_mapping = {}
    candidate_contests = self.get_elements_by_class(self.election_tree,
                                                    "CandidateContest")
    for cc in candidate_contests:
      cand_ids = self._gather_contest_candidates(cc)
      contest_id = cc.get("objectId")
      candidate_contest_mapping[contest_id] = cand_ids

    invalid_candidates = self._gather_invalid_candidates()

    warning_log = []
    for contest_id, cand_ids in candidate_contest_mapping.items():
      flagged_candidates = []
      for cand_id in cand_ids:
        if cand_id in invalid_candidates:
          flagged_candidates.append(cand_id)
      if flagged_candidates:
        warning_message = ("Candidates {} should be BallotMeasureSelection "
                           "elements. Similarly, Contest {} should be changed "
                           "to a BallotMeasureContest instead of a "
                           "CandidateContest.").format(
                               ", ".join(flagged_candidates), contest_id)
        warning_log.append(loggers.LogEntry(warning_message))
    if invalid_candidates:
      warning_message = ("There are CandidateContests that appear to be "
                         "BallotMeasureContests based on the "
                         "BallotName values.")
      raise loggers.ElectionWarning(warning_log)


class MissingFieldsError(base.MissingFieldRule):
  """Check for missing fields for given entity types and field names.

  Raise error for missing fields. To add a field, include the entity
  and field in element_field_mapping.
  """

  def get_severity(self):
    return 2

  def element_field_mapping(self):
    return {
        "Person": [
            "FullName//Text",
        ],
        "Candidate": [
            "PersonId",
        ],
        "Election": [
            "StartDate",
            "EndDate",
        ],
    }


class MissingFieldsWarning(base.MissingFieldRule):
  """Check for missing fields for given entity types and field names.

  Raise warning for missing fields. To add a field, include the entity
  and field in element_field_mapping.
  """

  def get_severity(self):
    return 1

  def element_field_mapping(self):
    return {
        "Candidate": [
            "PartyId",
        ],
    }


class MissingFieldsInfo(base.MissingFieldRule):
  """Check for missing fields for given entity types and field names.

  Raise info for missing fields. To add a field, include the entity
  and field in element_field_mapping.
  """

  def get_severity(self):
    return 0

  def element_field_mapping(self):
    return {
        "Office": [
            "ElectoralDistrictId",
        ],
    }


class PartySpanMultipleCountries(base.BaseRule):
  """Check if a party operate on multiple countries.

  Parties can have PartyScopeGpUnitIds which span multiple countries. This is
  sometimes correct, but we should flag it to double check.
  """

  def __init__(self, election_tree, schema_tree):
    super(PartySpanMultipleCountries, self).__init__(election_tree, schema_tree)
    self.existing_gpunits = dict()
    country_pattern = re.compile(r"^ocd-division\/country:[a-z]{2}")
    for gpunit in self.get_elements_by_class(election_tree, "GpUnit"):
      ocd_ids = get_external_id_values(gpunit, "ocd-id")
      if ocd_ids:
        country_match = country_pattern.search(ocd_ids[0])
        if country_match:
          country = country_match[0].split("/")[1]
          self.existing_gpunits[gpunit.get("objectId")] = country

  def elements(self):
    return ["PartyScopeGpUnitIds"]

  def check(self, element):
    if element.text is None:
      return
    referenced_country = dict()
    for gpunit_id in element.text.split():
      country = self.existing_gpunits.get(gpunit_id)
      if country is not None:
        if referenced_country.get(country) is None:
          referenced_country[country] = []
        referenced_country[country].append(gpunit_id)

    if len(referenced_country) > 1:
      gpunit_country_mapping = " / ".join(
          ["%s -> %s" % (key, str(value)) for (key, value)
           in referenced_country.items()])

      raise loggers.ElectionWarning.from_message(
          ("PartyScopeGpUnitIds refer to GpUnit from different countries: {}. "
           "Please double check."
           .format(gpunit_country_mapping)), [element])


class OfficeMissingGovernmentBody(base.BaseRule):
  """Ensure non-executive Office elements have a government body defined."""

  _EXEMPT_OFFICES = [
      "head of state", "head of government", "president", "vice president",
      "state executive", "deputy state executive",
  ]

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_roles = get_entity_info_for_value_type(element, "office-role")
    if office_roles:
      office_role = office_roles[0]
      if office_role in self._EXEMPT_OFFICES:
        return

    governmental_body = get_entity_info_for_value_type(
        element, "governmental-body")
    government_body = get_entity_info_for_value_type(
        element, "government-body")

    if not governmental_body and not government_body:
      raise loggers.ElectionInfo.from_message(
          ("Office element is missing an external identifier of other-type "
           "government-body."), [element])


class SubsequentContestIdIsValidRelatedContest(base.DateRule):
  """Check that SubsequentContests are valid.

  Conditions for a valid SubsequentContest:
  - OfficeId, if present, must match the original contest.
  - PrimaryPartyIds, if present, must match the original contest.
  - EndDate, if present, must not be after EndDate of the original contest.
  - ComposingContestIds must not contain the original contest.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    error_log = []
    contest_ids = {}
    contest_end_dates = {}

    for election in self.get_elements_by_class(election_report_element,
                                               "Election"):
      self.gather_dates(election)
      for contest in self.get_elements_by_class(election, "Contest"):
        contest_ids[contest.get("objectId")] = contest
        contest_end_dates[contest.get("objectId")] = self.end_date

    for contest_id, contest in contest_ids.items():
      element = contest.find("SubsequentContestId")
      if not element_has_text(element):
        continue
      subsequent_contest_id = element.text.strip()

      # Check that subsequent contest exists
      if subsequent_contest_id not in contest_ids:
        error_log.append(
            loggers.LogEntry(
                "Could not find SubsequentContest %s referenced by Contest %s."
                % (subsequent_contest_id, contest_id)))
        continue

      subsequent_contest = contest_ids[subsequent_contest_id]

      # Check that the subsequent contest has a later end date
      if (contest_end_dates[subsequent_contest_id] is not None and
          contest_end_dates[contest_id] is not None):
        end_delta = (contest_end_dates[subsequent_contest_id] -
                     contest_end_dates[contest_id]).days
        if end_delta < 0:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s references a subsequent contest with an earlier "
                  "end date." % contest_id, [contest], [contest.sourceline]))

      # Check that office ids match
      c_office_id = None
      sc_office_id = None
      element = contest.find("OfficeIds")
      if element_has_text(element):
        c_office_id = element.text
      element = subsequent_contest.find("OfficeIds")
      if element_has_text(element):
        sc_office_id = element.text

      if c_office_id != sc_office_id:
        error_log.append(
            loggers.LogEntry(
                "Contest %s references a subsequent contest with a different "
                "office id." % contest_id, [contest], [contest.sourceline]))

      # Check that primary party ids match or that the subsequent contest does
      # not have a primary party (e.g. primary -> general election)
      c_primary_party_ids = None
      sc_primary_party_ids = None
      element = contest.find("PrimaryPartyIds")
      if element_has_text(element):
        c_primary_party_ids = set(element.text.split())
      element = subsequent_contest.find("PrimaryPartyIds")
      if element_has_text(element):
        sc_primary_party_ids = set(element.text.split())

      if (sc_primary_party_ids is not None and
          c_primary_party_ids != sc_primary_party_ids):
        error_log.append(
            loggers.LogEntry(
                "Contest %s references a subsequent contest with different "
                "primary party ids." % contest_id, [contest],
                [contest.sourceline]))

      # Check that there is not a subsequent contest <-> composing contest loop
      element = subsequent_contest.find("ComposingContestIds")
      if element_has_text(element):
        subsequent_composing_ids = element.text.split()
        if contest_id in subsequent_composing_ids:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s is listed as a composing contest for its "
                  "subsequent contest.  Two contests can be linked by "
                  "SubsequentContestId or ComposingContestId, but not both." %
                  contest_id, [contest], [contest.sourceline]))

    if error_log:
      raise loggers.ElectionError(error_log)


class ComposingContestIdsAreValidRelatedContests(base.BaseRule):
  """Check that ComposingContestIds are valid.

  Conditions for a valid ComposingContest:
  - OfficeId, if present, must match the parent contest.
  - PrimaryPartyIds, if present, must match the parent contest.
  - ComposingContests must not be referenced by more than one parent contest.
  - ComposingContests must not reference each other.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    error_log = []

    contests = self.get_elements_by_class(election_report_element, "Contest")
    contest_ids = {cc.get("objectId"): cc for cc in contests}
    composing_contests = {}
    for contest_id, contest in contest_ids.items():
      element = contest.find("ComposingContestIds")
      if not element_has_text(element):
        continue
      composing_contests[contest_id] = element.text.split()

    # Check for composing contests that appear more than once
    unique_contests = set()
    for contest_list in composing_contests.values():
      for contest_id in contest_list:
        if contest_id not in unique_contests:
          unique_contests.add(contest_id)
        else:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s is listed as a ComposingContest for more "
                  "than one parent contest.  ComposingContests should be a "
                  "strict hierarchy." % contest_id))

    for contest_id, composing_contest_ids in composing_contests.items():
      contest = contest_ids[contest_id]
      for cc_id in composing_contest_ids:
        # Check that the composing contests exist
        if cc_id not in contest_ids.keys():
          error_log.append(
              loggers.LogEntry(
                  "Could not find ComposingContest % referenced by Contest %s."
                  % (contest_id, cc_id)))
          continue

        composing_contest = contest_ids[cc_id]
        # Check that the office ids match
        c_office_id = None
        cc_office_id = None
        element = contest.find("OfficeIds")
        if element_has_text(element):
          c_office_id = element.text
        element = composing_contest.find("OfficeIds")
        if element_has_text(element):
          cc_office_id = element.text

        if c_office_id != cc_office_id:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and composing contest %s have different office "
                  "ids." % (contest_id, cc_id)))

        # Check that primary party ids match
        c_primary_party_ids = None
        cc_primary_party_ids = None
        element = contest.find("PrimaryPartyIds")
        if element_has_text(element):
          c_primary_party_ids = set(element.text.split())
        element = composing_contest.find("PrimaryPartyIds")
        if element_has_text(element):
          cc_primary_party_ids = set(element.text.split())

        if c_primary_party_ids != cc_primary_party_ids:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and composing contest %s have different primary "
                  "party ids." % (contest_id, cc_id)))

        # Check that composing contests don't reference each other
        if (cc_id in composing_contests and
            contest_id in composing_contests[cc_id]):
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and contest %s reference each other as composing "
                  "contests." % (contest_id, cc_id)))

    if error_log:
      raise loggers.ElectionError(error_log)


class RuleSet(enum.Enum):
  """Names for sets of rules used to validate a particular feed type."""
  ELECTION = 1
  OFFICEHOLDER = 2


# To add new rules, create a new class, inherit the base rule,
# and add it to the correct rule list.
COMMON_RULES = (
    AllCaps,
    AllLanguages,
    DuplicateGpUnits,
    DuplicateID,
    EmptyText,
    Encoding,
    GpUnitOcdId,
    HungarianStyleNotation,
    LanguageCode,
    MissingStableIds,
    OtherType,
    OptionalAndEmpty,
    Schema,
    UniqueLabel,
    ValidEnumerations,
    ValidIDREF,
    ValidateOcdidLowerCase,
    PersonsHaveValidGender,
    PartyLeadershipMustExist,
    URIValidator,
    UniqueURIPerAnnotationCategory,
    ValidURIAnnotation,
    GpUnitsCyclesRefsValidation,
    ValidJurisdictionID,
    OfficesHaveJurisdictionID,
    OfficesHaveValidOfficeLevel,
    OfficesHaveValidOfficeRole,
    ValidStableID,
    PartySpanMultipleCountries,
    PersonHasUniqueFullName,
    PersonsMissingPartyData,
    GpUnitsHaveInternationalizedName,
    MissingFieldsError,
    MissingFieldsWarning,
    MissingFieldsInfo,
)

ELECTION_RULES = COMMON_RULES + (
    CoalitionParties,
    DuplicateContestNames,
    ElectoralDistrictOcdId,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    PercentSum,
    ProperBallotSelection,
    CandidatesReferencedOnceOrInRelatedContests,
    VoteCountTypesCoherency,
    PartiesHaveValidColors,
    ValidateDuplicateColors,
    ElectionStartDates,
    ElectionEndDates,
    ContestHasMultipleOffices,
    GpUnitsHaveSingleRoot,
    MissingPartyAbbreviationTranslation,
    DuplicatedPartyName,
    DuplicatedPartyAbbreviation,
    MissingPartyNameTranslation,
    FullTextMaxLength,
    FullTextOrBallotText,
    BallotTitle,
    ImproperCandidateContest,
    SubsequentContestIdIsValidRelatedContest,
    ComposingContestIdsAreValidRelatedContests,
)

OFFICEHOLDER_RULES = COMMON_RULES + (
    PersonHasOffice,
    ProhibitElectionData,
    OfficeTermDates,
    UniqueStartDatesForOfficeRoleAndJurisdiction,
    OfficeMissingGovernmentBody,
)

ALL_RULES = frozenset(COMMON_RULES + ELECTION_RULES + OFFICEHOLDER_RULES)

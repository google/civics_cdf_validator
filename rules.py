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
import datetime
import enum
import hashlib
import re

from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import office_utils
from frozendict import frozendict
import language_tags
from lxml import etree
import networkx
import pycountry
from six.moves.urllib.parse import urlparse

_PARTY_LEADERSHIP_TYPES = ["party-leader-id", "party-chair-id"]
_INDEPENDENT_PARTY_NAMES = frozenset(["independent", "nonpartisan"])
# The set of external identifiers that contain references to other entities.
_IDREF_EXTERNAL_IDENTIFIERS = frozenset(
    ["jurisdiction-id"] + _PARTY_LEADERSHIP_TYPES
)
_IDENTIFIER_TYPES = frozenset(
    ["local-level", "national-level", "ocd-id", "state-level"]
)
_CONTEST_STAGE_TYPES = frozenset([
    "exit-polls",
    "estimates",
    "projections",
    "preliminary",
    "official",
    "unnamed",
])
_INTERNATIONALIZED_TEXT_ELEMENTS = [
    # go/keep-sorted start
    "BallotName",
    "BallotSubTitle",
    "BallotText",
    "BallotTitle",
    "ConStatement",
    "Directions",
    "EffectOfAbstain",
    "FullName",
    "FullText",
    "InternationalizedAbbreviation",
    "InternationalizedName",
    "Name",
    "PassageThreshold",
    "ProStatement",
    "Profession",
    "Selection",
    "SummaryText",
    "Title",
    # go/keep-sorted end
]

_EXECUTIVE_OFFICE_ROLES = frozenset([
    "head of state",
    "head of government",
    "president",
    "vice president",
    "state executive",
    "deputy state executive",
    "deputy head of government",
])

_VALID_FEED_LONGEVITY_BY_FEED_TYPE = frozendict({
    "committee": ["evergreen"],
    "election-dates": ["evergreen"],
    "election-results": ["limited", "yearly"],
    "officeholder": ["evergreen"],
    "pre-election": ["limited", "yearly"],
})

_VALID_OFFICE_ROLE_COMBINATIONS = frozenset([
    frozenset(["head of government", "head of state"]),
    frozenset(["cabinet member", "general purpose officer"]),
])


def _get_office_roles(element, is_post_office_split_feed=False):
  if is_post_office_split_feed:
    return [element.text for element in element.findall("OfficeRole")]
  return get_entity_info_for_value_type(element, "office-role")


def _is_executive_office(element, is_post_office_split_feed=False):
  office_roles = _get_office_roles(element, is_post_office_split_feed)
  return not _EXECUTIVE_OFFICE_ROLES.isdisjoint(office_roles)


def _has_government_body(element):
  if element_has_text(element.find("GovernmentBodyIds")):
    return True
  governmental_body = get_entity_info_for_value_type(
      element,
      "governmental-body",
  )
  government_body = get_entity_info_for_value_type(element, "government-body")
  return bool(governmental_body or government_body)


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
      if (
          other_type is not None
          and other_type.text
          and other_type.text.strip() == value_type
          and value_type not in _IDENTIFIER_TYPES
      ):
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


def extract_person_fullname(person):
  """Extracts the person's fullname or builds it if needed."""
  full_name_elt = person.find("FullName")
  if full_name_elt is None:
    return []
  full_name_list = set()
  for name in full_name_elt.findall("Text"):
    if name.text:
      full_name_list.add(name.text)
      return full_name_list
  return []


def get_entity_info_for_value_type(element, info_type, return_elements=False):
  info_collection = get_additional_type_values(
      element, info_type, return_elements
  )
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
    if language not in language_map:
      language_map[language] = [text]
    else:
      language_map[language].append(text)
  return language_map


def element_has_text(element):
  return (
      element is not None
      and element.text is not None
      and not element.text.isspace()
  )


def country_code_is_valid(country_code):
  # EU is part of ISO 3166/MA
  return (
      country_code.lower() == "eu"
      or pycountry.countries.get(alpha_2=country_code.upper()) is not None
  )


class Schema(base.TreeRule):
  """Checks if election file validates against the provided schema."""

  def check(self):
    try:
      schema = etree.XMLSchema(etree=self.schema_tree)
    except etree.XMLSchemaParseError as e:
      raise loggers.ElectionError.from_message(
          "The schema file could not be parsed correctly %s" % str(e)
      )
    valid_xml = True
    try:
      schema.assertValid(self.election_tree)
    except etree.DocumentInvalid as e:
      valid_xml = False
    if not valid_xml:
      errors = []
      for error in schema.error_log:
        errors.append(
            loggers.LogEntry(
                lines=[error.line],
                message=(
                    "The election file didn't validate "
                    "against schema : {0}".format(error.message.encode("utf-8"))
                ),
            )
        )
      raise loggers.ElectionError(errors)


class OptionalAndEmpty(base.BaseRule):
  """Checks for optional and empty fields."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(OptionalAndEmpty, self).__init__(election_tree, schema_tree, **kwargs)
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
          "This optional element included although it is empty.", [element]
      )


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
            (
                "%s ID %s is not in Hungarian Style Notation. Should start"
                " with  %s" % (tag, object_id, self.elements_prefix[tag])
            ),
            [element],
        )


class LanguageCode(base.BaseRule):
  """Check that Text elements have a valid language code."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if "language" not in element.attrib:
      return
    elem_lang = element.get("language")
    if not elem_lang.strip() or not language_tags.tags.check(elem_lang):
      raise loggers.ElectionError.from_message(
          "%s is not a valid language code" % elem_lang, [element]
      )


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
      for vote_counts in ballot_selection.find("VoteCountsCollection").findall(
          "VoteCounts"
      ):
        other_type = vote_counts.find("OtherType")
        if other_type is not None and other_type.text == "total-percent":
          sum_percents += float(vote_counts.find("Count").text)
    if not PercentSum.fuzzy_equals(
        sum_percents, 0
    ) and not PercentSum.fuzzy_equals(sum_percents, 100):
      raise loggers.ElectionError.from_message(
          "Contest percents do not sum to 0 or 100: %f" % sum_percents,
          [element],
      )


class EmptyText(base.BaseRule):
  """Check that Text elements are not strictly whitespace."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if (element.text is None or not element.text.strip()) or (
        element.text is None and element.get("language") is not None
    ):
      raise loggers.ElectionError.from_message("Text is empty", element)


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

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(ValidIDREF, self).__init__(election_tree, schema_tree, **kwargs)
    self.object_id_mapping = {}
    self.element_reference_mapping = {}

  _REFERENCE_TYPE_OVERRIDES = {
      # ID refs to GpUnits
      "ElectoralDistrictId": "GpUnit",
      "ElectionScopeId": "GpUnit",
      "ScopeLevel": "GpUnit",
      "JurisdictionId": "GpUnit",
      # ID refs to Persons
      "AuthorityId": "Person",
      "AuthorityIds": "Person",
      "PartyLeaderId": "Person",
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
      if (
          tag
          and tag == "element"
          and element.get("type") in ("xs:IDREF", "xs:IDREFS")
      ):
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
    reference_object_ids = self.object_id_mapping.get(
        element_reference_type, []
    )
    if element.text:
      id_references = element.text.split()
      for id_ref in id_references:
        if id_ref not in reference_object_ids:
          error_log.append(
              loggers.LogEntry(
                  (
                      "{} is not a valid IDREF. {} should contain an "
                      "objectId from a {} element."
                  ).format(id_ref, element_name, element_reference_type),
                  element,
              )
          )
    if error_log:
      raise loggers.ElectionError(error_log)


class ValidStableID(base.BaseRule):
  """Ensure stable-ids are in the correct format."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(ValidStableID, self).__init__(election_tree, schema_tree, **kwargs)
    regex = r"^[a-zA-Z0-9_-]+$"
    self.stable_id_matcher = re.compile(regex, flags=re.U)

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    stable_ids = get_external_id_values(element, "stable")
    error_log = []
    for s_id in stable_ids:
      if not self.stable_id_matcher.match(s_id):
        error_log.append(
            loggers.LogEntry(
                "Stable id '{}' is not in the correct format.".format(s_id),
                [element],
            )
        )
    if error_log:
      raise loggers.ElectionError(error_log)


class ElectoralDistrictOcdId(base.BaseRule):
  """GpUnit referred to by ElectoralDistrictId MUST have a valid OCD-ID."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(ElectoralDistrictOcdId, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self._all_gpunits = {}

  def setup(self):
    gp_units = self.election_tree.findall(".//GpUnit")
    for gp_unit in gp_units:
      if "objectId" not in gp_unit.attrib:
        continue
      self._all_gpunits[gp_unit.attrib["objectId"]] = gp_unit

  def elements(self):
    return ["ElectoralDistrictId"]

  def check(self, element):
    error_log = []
    referenced_gpunit = self._all_gpunits.get(element.text)
    if referenced_gpunit is None:
      msg = (
          "The ElectoralDistrictId element not refer to a GpUnit. Every "
          "ElectoralDistrictId MUST reference a GpUnit"
      )
      error_log.append(loggers.LogEntry(msg, [element]))
    else:
      ocd_ids = get_external_id_values(referenced_gpunit, "ocd-id")
      if not ocd_ids:
        error_log.append(
            loggers.LogEntry(
                "The referenced GpUnit %s does not have an ocd-id"
                % element.text,
                [element],
                [referenced_gpunit.sourceline],
            )
        )
      else:
        for ocd_id in ocd_ids:
          if not self.ocd_id_validator.is_valid_ocd_id(ocd_id):
            error_log.append(
                loggers.LogEntry(
                    "The ElectoralDistrictId refers to GpUnit %s "
                    "that does not have a valid OCD ID (%s)"
                    % (element.text, ocd_id),
                    [element],
                    [referenced_gpunit.sourceline],
                )
            )
    if error_log:
      raise loggers.ElectionError(error_log)


class GpUnitOcdId(base.BaseRule):
  """Any GpUnit that is a geographic district SHOULD have a valid OCD-ID."""

  districts = [
      "borough",
      "city",
      "county",
      "municipality",
      "state",
      "town",
      "township",
      "village",
  ]
  validate_ocd_file = True

  def elements(self):
    return ["ReportingUnit"]

  def check(self, element):
    gpunit_type = element.find("Type")
    if gpunit_type is not None and gpunit_type.text in self.districts:
      external_id_elements = get_external_id_values(
          element, "ocd-id", return_elements=True
      )
      for extern_id in external_id_elements:
        if not self.ocd_id_validator.is_valid_ocd_id(extern_id.text):
          msg = "The OCD ID %s is not valid" % extern_id.text
          raise loggers.ElectionWarning.from_message(
              msg, [element], [extern_id.sourceline]
          )


class DuplicatedGpUnitOcdId(base.BaseRule):
  """2 GPUnits should not have same OCD-ID."""

  def elements(self):
    return ["GpUnitCollection"]

  def check(self, element):
    error_log = []
    gp_ocdid = dict()
    gpunits = element.findall("GpUnit")
    for gpunit in gpunits:
      ocd_ids = get_external_id_values(gpunit, "ocd-id")
      for ocd_id in ocd_ids:
        if ocd_id not in gp_ocdid.keys():
          gp_ocdid[ocd_id] = gpunit.get("objectId")
        else:
          msg = "GpUnits %s and %s have the same ocd-id %s" % (
              gp_ocdid[ocd_id],
              gpunit.get("objectId"),
              ocd_id,
          )
          error_log.append(loggers.LogEntry(msg, [gpunit]))
    if error_log:
      raise loggers.ElectionError(error_log)


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
        error_log.append(loggers.LogEntry("GpUnit is duplicated", [gpunit]))
        continue
      object_ids.add(object_id)
      composing_gpunits = gpunit.find("ComposingGpUnitIds")
      if composing_gpunits is None or not composing_gpunits.text:
        continue
      composing_ids = frozenset(composing_gpunits.text.split())
      if children.get(composing_ids):
        error_log.append(
            loggers.LogEntry(
                "GpUnits {} are duplicates".format(
                    str((children[composing_ids], object_id))
                )
            )
        )
        continue
      children[composing_ids] = object_id
    if error_log:
      raise loggers.ElectionError(error_log)


class GpUnitsHaveSingleRoot(base.TreeRule):
  """Ensure that GpUnits form a single-rooted tree."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(GpUnitsHaveSingleRoot, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.error_log = []

  def check(self):
    # Make sure there's at most one GpUnit as a root.
    # The root is defined as having ComposingGpUnitIds but
    # is not in the ComposingGpUnitIds of any other GpUnit.

    gpunit_ids = dict()
    composing_gpunits = set()
    for element in self.get_elements_by_class(self.election_tree, "GpUnit"):
      object_id = element.get("objectId")
      if object_id is not None:
        gpunit_ids[object_id] = element
      composing_gpunit = element.find("ComposingGpUnitIds")
      if composing_gpunit is not None and composing_gpunit.text is not None:
        composing_gpunits.update(composing_gpunit.text.split())

    roots = gpunit_ids.keys() - composing_gpunits

    if not roots:
      self.error_log.append(
          loggers.LogEntry(
              "GpUnits have no geo district root. "
              "There should be one or more root geo district."
          )
      )
    else:
      for object_id in roots:
        element = gpunit_ids.get(object_id)
        ocd_ids = get_external_id_values(element, "ocd-id")
        for ocd_id in ocd_ids:
          if not gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(
              ocd_id
          ):
            msg = (
                "GpUnits tree roots needs to be either a country or the EU"
                " region, please check the value %s." % (ocd_id)
            )
            self.error_log.append(loggers.LogEntry(msg, [element]))

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class GpUnitsCyclesRefsValidation(base.TreeRule):
  """Ensure that GpUnits form a valid tree and no cycles are present."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(GpUnitsCyclesRefsValidation, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.edges = dict()  # Used to maintain the record of connected edges
    self.visited = {}  # Used to store status of the nodes as visited or not.
    self.error_log = []
    self.bad_nodes = []

  def build_tree(self, gpunit):
    # Check if the node is already visited
    if gpunit in self.visited:
      if gpunit not in self.bad_nodes:
        self.error_log.append(
            loggers.LogEntry("Cycle detected at node {0}".format(gpunit))
        )
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
                .format(child_unit)
            )
        )

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
    for element in self.schema_tree.iterfind(
        "{%s}complexType" % self._XSCHEMA_NAMESPACE
    ):
      for elem in element.iter():
        tag = self.strip_schema_ns(elem)
        if tag == "element":
          elem_name = elem.get("name")
          if elem_name and elem_name == "OtherType":
            eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    type_element = element.find("Type")
    other_type_element = element.find("OtherType")
    if type_element is not None and type_element.text == "other":
      if other_type_element is None:
        msg = (
            "Type on this element is set to 'other' but OtherType element "
            "is not defined"
        )
        raise loggers.ElectionError.from_message(msg, [element])
    if type_element is not None and type_element.text != "other":
      if other_type_element is not None:
        msg = (
            "Type on this element is not set to 'other' but OtherType "
            "element is defined"
        )
        raise loggers.ElectionError.from_message(msg, [element])


class PartisanPrimary(base.BaseRule):
  """Partisan elections should link to the correct political party.

  For an Election element of Election type primary, partisan-primary-open,
  or partisan-primary-closed, the Contests in that ContestCollection should
  have a PrimartyPartyIds that is present and non-empty.
  """

  election_type = None

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(PartisanPrimary, self).__init__(election_tree, schema_tree, **kwargs)
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

    if not election_type or election_type not in (
        "partisan-primary-open",
        "partisan-primary-closed",
    ):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      primary_party_ids = contest_elem.find("PrimaryPartyIds")
      if not element_has_text(primary_party_ids):
        msg = (
            "Election is of ElectionType %s but PrimaryPartyIds is not present"
            " or is empty" % (self.election_type)
        )
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
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    ):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      contest_name = contest_elem.find("Name")
      if element_has_text(contest_name):
        c_name = contest_name.text.replace(" ", "").lower()
        for p_text in self.party_text:
          if p_text in c_name:
            msg = (
                "Name of contest - %s, contains text that implies it is a "
                "partisan primary but is not marked up as such."
                % (contest_name.text)
            )
            raise loggers.ElectionWarning.from_message(msg, [contest_elem])


class CoalitionParties(base.BaseRule):
  """Coalitions should always define the Party IDs."""

  def elements(self):
    return ["Coalition"]

  def check(self, element):
    party_id = element.find("PartyIds")
    if party_id is None or not party_id.text or not party_id.text.strip():
      raise loggers.ElectionError.from_message(
          "Coalition must define PartyIDs", [element]
      )


class UniqueLabel(base.BaseRule):
  """Labels should be unique within a file."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(UniqueLabel, self).__init__(election_tree, schema_tree, **kwargs)
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


class CandidatesReferencedInRelatedContests(base.BaseRule):
  """Candidate should not be referred to by multiple unrelated contests.

  A Candidate object should only be referenced from one contest, unless the
  contests are related (connected by SubsequentContestId). If a Person is
  running in multiple unrelated Contests, then that Person is a Candidate
  several times over, but a Candida(te|cy) can't span unrelated contests.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(CandidatesReferencedInRelatedContests, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.error_log = []
    self.contest_graph = networkx.Graph()

  def elements(self):
    return ["ElectionReport"]

  def _register_person_to_candidate_to_contests(self, election_report):
    person_candidate_contest_mapping = {}

    candidate_to_contest_mapping = {}
    contests = self.get_elements_by_class(election_report, "Contest")
    for contest in contests:
      contest_id = contest.get("objectId", None)
      candidate_ids_elements = self.get_elements_by_class(
          contest, "CandidateIds"
      )
      candidate_id_elements = self.get_elements_by_class(contest, "CandidateId")
      id_elements = candidate_ids_elements + candidate_id_elements
      for id_element in id_elements:
        if element_has_text(id_element):
          for candidate_id in id_element.text.split():
            candidate_to_contest_mapping.setdefault(candidate_id, []).append(
                contest_id
            )

    candidates = self.get_elements_by_class(election_report, "Candidate")
    for candidate in candidates:
      candidate_id = candidate.get("objectId", None)
      person_id = candidate.find("PersonId")
      if element_has_text(person_id):
        if candidate_id not in candidate_to_contest_mapping.keys():
          raise loggers.ElectionError.from_message(
              (
                  "A Candidate should be referenced in a Contest. Candidate {} "
                  "is not referenced."
              ).format(candidate_id)
          )
        contest_list = candidate_to_contest_mapping[candidate_id]
        person_candidate_contest_mapping.setdefault(person_id.text, {})[
            candidate_id
        ] = contest_list

    return person_candidate_contest_mapping

  def _construct_contest_graph(self, election_report):
    contests = self.get_elements_by_class(election_report, "Contest")
    # create a node for each contest
    for contest in contests:
      self.contest_graph.add_node(contest.get("objectId"))

    for contest in contests:
      subsequent_contest_id = None
      subsequent_contest = contest.find("SubsequentContestId")
      if element_has_text(subsequent_contest):
        subsequent_contest_id = subsequent_contest.text
        # subsequent contest id is not valid if it isn't in the graph
        if not self.contest_graph.has_node(subsequent_contest_id):
          raise loggers.ElectionError.from_message(
              (
                  "Contest {} contains a subsequent Contest Id ({}) that does "
                  "not exist."
              ).format(contest.get("objectId"), subsequent_contest_id),
              [subsequent_contest],
          )
        self.contest_graph.add_edge(
            contest.get("objectId"), subsequent_contest.text
        )
      # Add the composing contest if it exists
      composing_contests = contest.find("ComposingContestIds")
      if element_has_text(composing_contests):
        children = composing_contests.text.split()
        for child in children:
          # composing contest id is not valid if it isn't in the graph
          if not self.contest_graph.has_node(child):
            raise loggers.ElectionError.from_message(
                (
                    "Contest {} contains a composing Contest Id ({}) that does "
                    "not exist."
                ).format(contest.get("objectId"), child),
                [composing_contests],
            )
          if subsequent_contest_id:
            self.contest_graph.add_edge(child, subsequent_contest_id)

  def _check_candidate_contests_are_related(self, contest_id_list):
    for i in range(len(contest_id_list) - 1):
      contest_one = contest_id_list[i]
      contest_two = contest_id_list[i + 1]
      # every unique contest should be related, but since paths are transitive
      # checking each subsequent pair is enough to ensure this
      if not networkx.has_path(self.contest_graph, contest_one, contest_two):
        return False

    return True

  def _check_separate_candidates_not_related(self, candidate_contest_mapping):
    for contests in candidate_contest_mapping.values():
      for other_contests in [
          con for con in candidate_contest_mapping.values() if con != contests
      ]:
        for contest in contests:
          for other_contest in other_contests:
            if networkx.has_path(self.contest_graph, contest, other_contest):
              return False
    return True

  def check(self, election_report):
    self._construct_contest_graph(election_report)
    person_candidate_to_contest_map = (
        self._register_person_to_candidate_to_contests(election_report)
    )
    for person, cand_con_mapping in person_candidate_to_contest_map.items():
      for cand, contests in cand_con_mapping.items():
        related_contests = self._check_candidate_contests_are_related(contests)
        if not related_contests:
          error_message = (
              "Candidate {} appears in the following contests "
              "which are not all related: {}"
          ).format(cand, ", ".join(contests))
          self.error_log.append(
              loggers.LogEntry(error_message, [election_report])
          )

      sep_cand_not_related = self._check_separate_candidates_not_related(
          cand_con_mapping
      )
      if not sep_cand_not_related:
        error_message = (
            "Person {} has separate candidates in contests that "
            "are related.".format(person)
        )
        self.error_log.append(
            loggers.LogEntry(error_message, [election_report])
        )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ProperBallotSelection(base.BaseRule):
  """BallotSelections should be correct for that type of contest.

  Ensure that the BallotSelection elements in a CandidateContest are
  CandidateSelections, PartyContests have PartySelections, etc, etc.
  """

  con_sel_mapping = {
      "BallotMeasureContest": "BallotMeasureSelection",
      "CandidateContest": "CandidateSelection",
      "PartyContest": "PartySelection",
      "RetentionContest": "BallotMeasureSelection",
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
        msg = (
            "The Contest does not contain the right BallotSelection. %s "
            "must have a %s but contains a %s, %s"
            % (tag, self.con_sel_mapping[tag], selection_tag, selection_id)
        )
        raise loggers.ElectionError.from_message(msg, [element])


class CorrectCandidateSelectionCount(base.BaseRule):
  """CandidateSelections should only reference one candidate.

  This rule will throw a warning if a CandidateSelection references multiple
  candidates or does not reference any candidates at all. We currently do not
  support tickets (i.e. CandidateSelections with multiple candidates) except for
  party list elections.
  """

  def elements(self):
    return ["CandidateSelection"]

  def check(self, element):
    selection_id = element.get("objectId")
    candidate_ids = element.findall("CandidateIds")
    if not candidate_ids:
      msg = (
          f"The CandidateSelection {selection_id} does not reference any"
          " candidates."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])
    if len(candidate_ids) > 1:
      msg = (
          f"The CandidateSelection {selection_id} is expected to have one"
          f" CandidateIds but {len(candidate_ids)} were found."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])
    candidates = candidate_ids[0].text.split()
    if len(candidates) != 1:
      msg = (
          f"CandidateIds for CandidateSelection {selection_id} is expected to"
          f" reference one candidate but {len(candidates)} candidates were"
          " found. This warning can be ignored for party list elections."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])


class SingularPartySelection(base.BaseRule):
  """Each PartySelection should have exactly one Party in the PartyIds.

  While technically the schema allows multiple IDs, currently our pipeline does
  not support this. Having multiple parties can cause undefined behavior.
  """

  def elements(self):
    return ["PartySelection"]

  def check(self, element):
    party_ids = element.find("PartyIds")
    if party_ids is None or not party_ids.text or not party_ids.text.strip():
      raise loggers.ElectionError.from_message(
          "PartySelection has no associated parties.", [element]
      )
    elif len(party_ids.text.split()) != 1:
      raise loggers.ElectionError.from_message(
          "PartySelection has more than one associated party.", [element]
      )


class PartiesHaveValidColors(base.BaseRule):
  """Each Party should have a valid hex integer less than 16^6, without a leading '#'.

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
          "The Party has more than one color.", [element]
      )
    color_val = colors[0].text
    if not color_val:
      raise loggers.ElectionWarning.from_message(
          "Color tag is missing a value.", [colors[0]]
      )
    try:
      int(color_val, 16)
    except ValueError:
      raise loggers.ElectionWarning.from_message(
          "%s is not a valid hex color." % color_val,
          [colors[0]],
      )
    if not re.match("^([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$", color_val):
      raise loggers.ElectionWarning.from_message(
          "%s should be a hexadecimal less than 16^6." % color_val, [colors[0]]
      )


class PersonHasUniqueFullName(base.BaseRule):
  """A Person should be defined one time in <PersonCollection>.

  The main purpose of this check is to spot redundant person definition.
  If two people have the same full name and date of birhthday, a warning will
  be raised. So, we can check if the feed is coherent.
  """

  def elements(self):
    return ["PersonCollection"]

  def check_specific(self, people):
    person_def = collections.namedtuple(
        "PersonDefinition", ["fullname", "birthday"]
    )
    person_id_to_object_id = {}

    info_log = []
    for person in people:
      person_object_id = person.get("objectId")
      full_name_list = extract_person_fullname(person)
      date_of_birthday = person.find("DateOfBirth")
      birthday_val = "Undefined"
      if date_of_birthday is not None and date_of_birthday.text:
        birthday_val = date_of_birthday.text

      for full_name_val in full_name_list:
        person_id = person_def(full_name_val, birthday_val)
        if (
            person_id in person_id_to_object_id
            and person_id_to_object_id[person_id] != person_object_id
        ):
          info_message = (
              "Person has same full name '%s' and birthday %s as Person %s."
              % (full_name_val, birthday_val, person_id_to_object_id[person_id])
          )
          info_log.append(loggers.LogEntry(info_message, [person]))
        else:
          person_id_to_object_id[person_id] = person_object_id
    return info_log

  def check(self, element):
    info_log = []
    people = element.findall("Person")
    if len(people) < 1:
      info_log.append(
          loggers.LogEntry(
              "<PersonCollection> does not have <Person> objects", [element]
          )
      )
    info_log.extend(self.check_specific(people))
    if info_log:
      raise loggers.ElectionInfo(info_log)


class BadCharactersInPersonFullName(base.BaseRule):
  """A person Fullname should not include bad characters."""

  regex = r"([()@$%*/]|\balias\b)"

  def elements(self):
    return ["Person"]

  def check(self, element):
    warning_message = (
        "Person has known bad characters in FullName field."
        " Aliases should be included in Nickname field."
    )
    fullname = extract_person_fullname(element)
    person_fullname = re.compile(self.regex, flags=re.U)
    bad_characters_match = None
    for name in fullname:
      bad_characters_match = re.search(person_fullname, name.lower())
    if bad_characters_match:
      if "alias" in bad_characters_match.group():
        raise loggers.ElectionWarning.from_message(warning_message, [element])
      else:
        raise loggers.ElectionWarning.from_message(
            "Person has known bad characters in FullName field.", [element]
        )


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


class ValidateDuplicateColors(base.TreeRule):
  """Parties under the same contest should have unique color.

  A Party object that has duplicate color and referenced under the same contest
  should be picked up within this class and returned to the user as a warning
  message.
  """

  def check(self):
    party_color_mapping = {}
    for party in self.get_elements_by_class(self.election_tree, "Party"):
      color_element = party.find("Color")
      if color_element is None or not color_element.text:
        continue
      party_color_mapping[party.get("objectId")] = (color_element.text, party)

    warning_log = []
    for party_contest in self.get_elements_by_class(
        element=self.election_tree, element_name="PartyContest"
    ):
      contest_colors = {}
      for party_ids_element in self.get_elements_by_class(
          element=party_contest, element_name="PartyIds"
      ):
        for party_id in party_ids_element.text.split():
          party_color = party_color_mapping[party_id][0]
          if party_color in contest_colors:
            contest_colors[party_color].append(party_color_mapping[party_id][1])
          else:
            contest_colors[party_color] = [party_color_mapping[party_id][1]]
      for color, parties in contest_colors.items():
        if len(parties) > 1:
          warning_log.append(
              loggers.LogEntry(
                  "Parties have the same color %s." % color, parties
              )
          )
    if warning_log:
      raise loggers.ElectionWarning(warning_log)


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
        info_message = (
            "<Party> does not have <InternationalizedAbbreviation> objects"
        )
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
                % (language, feed_party_ids)
            )
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party name is not translated to all feed languages %s. You "
            "did it only for the following languages : %s."
            % (feed_languages, party_languages)
        )
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
        info_message = (
            "<Party> does not have <InternationalizedAbbreviation> objects"
        )
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
                " : %s." % (language, feed_party_ids)
            )
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party abbreviation is not translated to all feed languages %s."
            " You only did it for the following languages : %s."
            % (feed_languages, party_languages)
        )
        info_log.append(loggers.LogEntry(info_message, [party]))
    return info_log


class IndependentPartyName(base.BaseRule):
  """Warns on parties that contain common names indicating they are an independent party.

  These should instead supply the IsIndependent attribute.
  """

  def elements(self):
    return ["Party"]

  def check(self, party):
    is_independent_element = party.find("IsIndependent")
    if is_independent_element is not None:
      return
    name_element = party.find("Name")
    if name_element is None:
      return
    party_names = name_element.findall("Text")
    for party_name in party_names:
      if party_name.text.lower() in _INDEPENDENT_PARTY_NAMES:
        raise loggers.ElectionWarning.from_message(
            f"Party name '{party_name.text}' indicates an independent party."
            " Please use the IsIndependent attribute on the party element to"
            " specify this."
        )


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
        error_log.append(loggers.LogEntry(error_message, [element]))
        continue
      name_contest_id.setdefault(name.text, []).append(element)

    for name, contests in name_contest_id.items():
      if len(contests) > 1:
        error_log.append(
            loggers.LogEntry("Contests have the same name %s." % name, contests)
        )
    if error_log:
      raise loggers.ElectionError(error_log)


class UniqueStableID(base.TreeRule):
  """Check that every stableID is unique.

  Add an error message if stable id is not unique
  """

  _TOP_LEVEL_ENTITIES = frozenset(
      ["Party", "GpUnit", "Office", "Person", "Candidate", "Contest"]
  )

  def check(self):
    error_log = []
    stable_obj_dict = dict()
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      if "Election" not in element.tag:
        if element.tag in self._TOP_LEVEL_ENTITIES:
          if "objectId" in element.attrib:
            object_id = element.get("objectId")
            stable_ids = get_external_id_values(element, "stable")
            for stable_id in stable_ids:
              if stable_id in stable_obj_dict.keys():
                stable_obj_dict.get(stable_id).append(object_id)
              else:
                object_id_list = []
                object_id_list.append(object_id)
                stable_obj_dict[stable_id] = object_id_list
    for k, v in stable_obj_dict.items():
      if len(v) > 1:
        error_message = (
            "Stable ID {} is not unique as it is mapped in {}".format(k, v)
        )
        error_log.append(loggers.LogEntry(error_message))
    if error_log:
      raise loggers.ElectionError(error_log)


class MissingStableIds(base.BaseRule):
  """Check that each NIST object in the feed have a stable Id.

  Add an error message if stable id is missing from the object.
  """

  def elements(self):
    return [
        "BallotMeasureContest",
        "BallotMeasureSelection",
        "Candidate",
        "CandidateContest",
        "Coalition",
        "Committee",
        "Election",
        "Office",
        "Party",
        "PartyContest",
        "PartyLeadership",
        "Person",
        "ReportingUnit",
    ]

  def check(self, element):
    stable_ids = []
    external_identifiers = element.find("ExternalIdentifiers")
    if external_identifiers is not None:
      stable_ids = get_external_id_values(external_identifiers, "stable")
    if not stable_ids:
      raise loggers.ElectionError.from_message(
          "The element is missing a stable id", [element]
      )


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
          "The person is missing party data", [element]
      )


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
      "Person": ["FullName//Text"],
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
                  element_tag, field_tag
              ),
              [element],
          )


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
      msg = (
          "Element does not contain text in all required languages, missing"
          + " : %s" % str(required_language_set - languages)
      )
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
      if (
          other_type_element is not None
          and other_type_element.text in self.valid_enumerations
      ):
        raise loggers.ElectionError.from_message(
            (
                "Type is set to 'other' even though '%s' is a valid enumeration"
                % other_type_element.text
            ),
            [element],
        )


class MultipleCandidatesPointToTheSamePersonInTheSameContest(base.TreeRule):
  """Raise an error when multiple candidates point to the same person in the same contest."""

  def check(self):
    # Keep track of rule violations
    error_log = []
    rule_violations = []
    # Get all Candidate objects in the feed
    candidates = self.get_elements_by_class(self.election_tree, "Candidate")
    # Store link between candidate_id and person_id for each Candidate object
    person_id_by_candidate_id = {
        candidate.get("objectId"): candidate.find("PersonId").text
        for candidate in candidates
    }
    # Get all Contest objects in the feed
    contests = self.get_elements_by_class(self.election_tree, "Contest")
    for contest in contests:
      rule_violations.extend(
          self._check_for_bad_candidates(person_id_by_candidate_id, contest)
      )
    # Combine rule violations into one error message
    if rule_violations:
      for rule_violation in rule_violations:
        contest_id = rule_violation[0]
        person_id = rule_violation[1]
        candidate_list = rule_violation[2]
        error_message = (
            "Multiple candidates in Contest {} reference the same Person "
            "{}. Candidates: {}"
        ).format(contest_id, person_id, candidate_list)
        error_log.append(loggers.LogEntry((error_message), [contest_id]))
    if error_log:
      raise loggers.ElectionError(error_log)

  def _check_for_bad_candidates(self, person_id_by_candidate_id, contest):
    candidate_ids_by_person_id = dict()
    rule_violating_person_ids = []
    contest_id = contest.get("objectId")
    for candidate_id in self._get_candidate_ids_for_contest(contest):
      person_id = person_id_by_candidate_id[candidate_id]
      if person_id not in candidate_ids_by_person_id:
        candidate_ids_by_person_id[person_id] = [candidate_id]
      else:
        candidate_ids_by_person_id[person_id].append(candidate_id)
        rule_violating_person_ids.append(person_id)
    return [
        (contest_id, person_id, str(candidate_ids_by_person_id[person_id]))
        for person_id in rule_violating_person_ids
    ]

  def _get_candidate_ids_for_contest(self, contest):
    candidate_id_elements = self.get_elements_by_class(contest, "CandidateIds")
    candidate_ids = []
    for candidate_id_element in candidate_id_elements:
      candidate_ids.extend(candidate_id_element.text.split())
    return candidate_ids


class SelfDeclaredCandidateMethod(base.BaseRule):
  """A self declared candidate cannot have an "electoral-commission" id.

  Please update the candidate Pre election Status.
  """

  def elements(self):
    return ["Candidate"]

  def check(self, element):
    status = element.find("PreElectionStatus")
    if status is not None and status.text == "self-declared":
      externalidvalues = get_external_id_values(element, "electoral-commission")
      length = len(externalidvalues)
      if length > 0:
        msg = (
            "A self declared candidate cannot have an electoral-commission"
            " id. Please update the candidate Pre election Status."
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class ValidateOcdidLowerCase(base.BaseRule):
  """Validate that the ocd-ids are all lower case.

  Throw a warning if the ocd-ids are not all in lowercase.
  """

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    for ocd_id in get_external_id_values(element, "ocd-id"):
      if not ocd_id.islower():
        msg = (
            "OCD-ID %s is not in all lower case letters. "
            "Valid OCD-IDs should be all lowercase." % (ocd_id)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class ContestHasMultipleOffices(base.BaseRule):
  """Ensure that each contest has exactly one Office."""

  def elements(self):
    return ["CandidateContest", "PartyContest"]

  def check(self, element):
    # for each contest, get the <officeids> entity
    office_ids = element.find("OfficeIds")
    if office_ids is not None and office_ids.text:
      ids = office_ids.text.split()
      if len(ids) > 1:
        raise loggers.ElectionWarning.from_message(
            "Contest has more than one associated office.", [element]
        )
    else:
      raise loggers.ElectionWarning.from_message(
          "Contest has no associated offices.", [element]
      )


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
    # Add party leaders provided in the External Identifier
    for external_id in root.findall(".//Party//ExternalIdentifier"):
      other_type = external_id.find("OtherType")
      if other_type is not None and other_type.text in _PARTY_LEADERSHIP_TYPES:
        person_reference_ids.add(external_id.find("Value").text)
    # Add party leaders provided in the Leadership entity
    for leader_id in root.findall(".//Party//PartyLeaderId"):
      if leader_id.text:
        person_reference_ids.add(leader_id.text)

    office_holder_tenure_collection = root.find("OfficeHolderTenureCollection")
    if office_holder_tenure_collection is not None:
      for office_holder_tenure in office_holder_tenure_collection.findall(
          "OfficeHolderTenure"
      ):
        id_obj = office_holder_tenure.find("OfficeHolderPersonId")
        if id_obj is not None and id_obj.text:
          person_reference_ids.add(id_obj.text.strip())

    office_collection = root.find("OfficeCollection")
    if (
        office_holder_tenure_collection is None
        and office_collection is not None
    ):
      for office in office_collection.findall("Office"):
        id_obj = office.find("OfficeHolderPersonIds")
        if id_obj is not None and id_obj.text:
          ids = id_obj.text.strip().split()
          if len(ids) > 1:
            msg = "Office has {} OfficeHolders. Must have exactly one.".format(
                str(len(ids))
            )
            raise loggers.ElectionError.from_message(msg, [office])
          person_reference_ids.update(ids)

    return person_reference_ids


class PartyLeadershipMustExist(base.ValidReferenceRule):
  """Each party leader or party chair should refer to a person in the feed."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(PartyLeadershipMustExist, self).__init__(
        election_tree, schema_tree, "Person", **kwargs
    )

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
          "Election data is prohibited in officeholder feeds."
      )


class PersonsHaveValidGender(base.BaseRule):
  """Ensure that all Person objects have a valid gender identification."""

  _VALID_GENDERS = {
      "male",
      "m",
      "man",
      "female",
      "f",
      "woman",
      "o",
      "x",
      "other",
      "nonbinary",
  }

  def elements(self):
    return ["Gender"]

  def check(self, element):
    if (
        element.text is not None
        and element.text.lower() not in self._VALID_GENDERS
    ):
      raise loggers.ElectionError.from_message(
          "Person object has invalid gender value: {0}".format(element.text),
          [element],
      )


class VoteCountTypesCoherency(base.BaseRule):
  """Ensure VoteCount types describe the appropriate votable."""

  PARTY_VC_TYPES = {
      "seats-won",
      "seats-leading",
      "party-votes",
      "seats-no-election",
      "seats-total",
      "seats-delta",
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
        for vote_counts in ballot_selection.find(
            "VoteCountsCollection"
        ).findall("VoteCounts"):
          vc_type = vote_counts.find("OtherType").text
          if vc_type in invalid_vc_types:
            errors.append(vc_type)
      if errors:
        msg = "VoteCount types {0} should not be nested in {1} Contest".format(
            ", ".join(errors), contest_type
        )
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
    discrepancies = []
    social_media_platform = [
        "facebook",
        "twitter",
        "wikipedia",
        "instagram",
        "youtube",
        "website",
        "linkedin",
        "line",
        "ballotpedia",
        "tiktok",
    ]

    try:
      url.encode("ascii")
    except UnicodeEncodeError:
      discrepancies.append("not ascii encoded")

    if parsed_url.scheme not in {"http", "https"}:
      discrepancies.append("protocol - invalid")
    if not parsed_url.netloc:
      discrepancies.append("domain - missing")
    if discrepancies:
      msg = (
          "The provided URI, {}, is invalid for the following reasons: {}."
          .format(url.encode("ascii", "ignore"), ", ".join(discrepancies))
      )
      raise loggers.ElectionError.from_message(msg, [element])

    for platform in social_media_platform:
      if (
          re.search(platform, parsed_url.netloc)
          and parsed_url.scheme != "https"
      ):
        msg = (
            "It is recommended to use https instead of http. The provided "
            "URI, '{}'."
        ).format(url)
        raise loggers.ElectionInfo.from_message(msg, [element])


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
        self.election_tree, "Office//ContactInformation//Uri"
    )
    uri_elements = set(all_uri_elements) - set(office_uri_elements)
    annotation_mapper = self._extract_uris_by_category(uri_elements)

    error_log = []
    for annotation, value_counter in annotation_mapper.items():
      for uri, uri_elements in value_counter.items():
        if len(uri_elements) > 1:
          error_message = (
              "The Uris contain the annotation type '{}' with the "
              "same value '{}'."
          ).format(annotation, uri)
          error_log.append(loggers.LogEntry(error_message, uri_elements))

    if error_log:
      raise loggers.ElectionWarning(error_log)


class ValidYoutubeURL(base.BaseRule):
  """Validate Youtube URL.

  Ensure the provided URL is not a generic youtube url or direct link to a
  playlist as one of the invalid youtube URL types.
  """

  def elements(self):
    return ["Uri"]

  def check(self, element):
    url = element.text.strip()
    parsed_url = urlparse(url)
    if "youtube" in parsed_url.netloc and (
        parsed_url.path in ["", "/"]
        or "watch" in parsed_url.path
        or "playlist" in parsed_url.path
        or "hashtag" in parsed_url.path
    ):
      raise loggers.ElectionError.from_message(
          "'{}' is not an expected value for a youtube channel.".format(url),
          [element],
      )


class ValidTiktokURL(base.BaseRule):
  """Validate Tiktok URL.

  Ensure the provided URL is a valid Tiktok URL types.
  """

  def elements(self):
    return ["Uri"]

  def check(self, element):
    url = element.text.strip()
    parsed_url = urlparse(url)
    if "tiktok" in parsed_url.netloc and (
        not re.match(r"^\/@[^\/@]+$", parsed_url.path)
        or parsed_url.query
        or parsed_url.fragment
    ):
      raise loggers.ElectionError.from_message(
          "'{}' is not an expected value for a tiktok account.".format(url),
          [element],
      )


class ValidURIAnnotation(base.BaseRule):
  """Validate annotations on candidate/officeholder URLs.

  Ensure they describe the type of URL presented.
  Throws Warnings and Errors depending on type of invalidity.
  """

  TYPE_PLATFORMS = frozenset([
      "facebook",
      "twitter",
      "instagram",
      "youtube",
      "website",
      "line",
      "linkedin",
      "tiktok",
      "whatsapp",
  ])
  USAGE_TYPES = frozenset(["personal", "official", "campaign"])
  PLATFORM_ONLY_ANNOTATIONS = frozenset(
      ["wikipedia", "ballotpedia", "opensecrets", "fec", "followthemoney"]
  )

  def elements(self):
    return ["ContactInformation"]

  def check_url(self, uri, annotation, platform):
    url = uri.text.strip()
    parsed_url = urlparse(url)
    # Ensure media platform name is in URL.
    if (
        platform != "website"
        and platform not in parsed_url.netloc
        and not (platform == "facebook" and "fb.com" in parsed_url.netloc)
        and not (platform == "twitter" and "x.com" in parsed_url.netloc)
    ):
      # Note that the URL is encoded for printing purposes
      raise loggers.ElectionError.from_message(
          "Annotation '{}' is incorrect for URI {}.".format(
              annotation, url.encode("ascii", "ignore")
          ),
          [uri],
      )

  def check(self, element):
    uris = element.findall("Uri")

    for uri in uris:
      annotation = uri.get("Annotation", "").strip()
      url = uri.text.strip()
      ascii_url = url.encode("ascii", "ignore")

      if not annotation:
        raise loggers.ElectionWarning.from_message(
            "URI {} is missing annotation.".format(ascii_url), [uri]
        )

      # Only do platform checks if the annotation is not an image.
      if re.search(r"candidate-image", annotation):
        continue

      ann_elements = annotation.split("-")
      if len(ann_elements) == 1:
        platform = ann_elements[0]
        # One element would imply the annotation could be a platform
        # without a usage type, which is checked here.
        if platform in self.TYPE_PLATFORMS:
          raise loggers.ElectionWarning.from_message(
              "Annotation '{}' missing usage type.".format(annotation), [uri]
          )
        elif platform in self.USAGE_TYPES:
          raise loggers.ElectionError.from_message(
              "Annotation '{}' has usage type, missing platform.".format(
                  annotation
              ),
              [uri],
          )
        elif platform not in self.PLATFORM_ONLY_ANNOTATIONS:
          raise loggers.ElectionError.from_message(
              "Annotation '{}' is not a valid annotation for URI {}.".format(
                  annotation, ascii_url
              ),
              [uri],
          )
      elif len(ann_elements) == 2:
        # Two elements at this stage would mean the annotation
        # must be a platform with a usage type.
        usage_type, platform = ann_elements
        if (
            usage_type not in self.USAGE_TYPES
            or platform not in self.TYPE_PLATFORMS
        ):
          raise loggers.ElectionWarning.from_message(
              "'{}' is not a valid annotation.".format(annotation), [uri]
          )
      else:
        # More than two implies an invalid annotation.
        raise loggers.ElectionError.from_message(
            "Annotation '{}' is invalid for URI {}.".format(
                annotation, ascii_url
            ),
            [uri],
        )
      # Finally, check platform is in the URL.
      self.check_url(uri, annotation, platform)


class OfficesHaveJurisdictionID(base.BaseRule):
  """Each office must have a jurisdiction-id."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    jurisdiction_values = []
    post_office_split_jurisdiction_element = element.find("JurisdictionId")
    if element_has_text(post_office_split_jurisdiction_element):
      jurisdiction_values.append(post_office_split_jurisdiction_element.text)
    else:
      jurisdiction_values = get_entity_info_for_value_type(
          element, "jurisdiction-id"
      )

    jurisdiction_values = [j_id for j_id in jurisdiction_values if j_id.strip()]
    if not jurisdiction_values:
      raise loggers.ElectionError.from_message(
          "Office is missing a jurisdiction ID.", [element]
      )
    if len(jurisdiction_values) > 1:
      raise loggers.ElectionError.from_message(
          "Office has more than one jurisdiction ID.",
          [element],
      )


class ValidJurisdictionID(base.ValidReferenceRule):
  """Each jurisdiction id should refer to a valid GpUnit."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(ValidJurisdictionID, self).__init__(
        election_tree, schema_tree, "GpUnit", **kwargs
    )

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    jurisdiction_values = get_entity_info_for_value_type(
        root, "jurisdiction-id"
    )
    return set(jurisdiction_values)

  def _gather_defined_values(self):
    gp_unit_elements = self.election_tree.getroot().findall(".//GpUnit")
    return {elem.get("objectId") for elem in gp_unit_elements}


class OfficeHasjurisdictionSameAsElectoralDistrict(base.BaseRule):
  """In election feeds, office has the electoral district same as jurisdiction."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    jurisdiction_values = get_entity_info_for_value_type(
        element, "jurisdiction-id")
    jurisdiction_values = [
        j_id.strip() for j_id in jurisdiction_values if j_id.strip()
    ]
    if not jurisdiction_values or len(jurisdiction_values) > 1:
      return

    electoral_district = element.find(".//ElectoralDistrictId")
    if electoral_district is None:
      return
    if electoral_district.text.strip() != jurisdiction_values[0]:
      raise loggers.ElectionInfo.from_message(
          "Office has electoral district different from jurisdiction.",
          [element],
      )


class OfficesHaveValidOfficeLevel(base.BaseRule):
  """Each office must have a valid office-level."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_levels = []
    post_office_split_office_level_element = element.find("Level")
    if element_has_text(post_office_split_office_level_element):
      office_levels.append(post_office_split_office_level_element.text)
    else:
      office_levels = [
          ol_id.strip()
          for ol_id in get_external_id_values(element, "office-level")
          if ol_id.strip()
      ]

    if not office_levels:
      raise loggers.ElectionError.from_message(
          "Office is missing an office level.",
          [element],
      )
    if len(office_levels) > 1:
      raise loggers.ElectionError.from_message(
          "Office has more than one office level.",
          [element],
      )
    office_level = office_levels[0]
    if office_level not in office_utils.VALID_OFFICE_LEVELS:
      raise loggers.ElectionError.from_message(
          f"Office has an invalid office level: '{office_level}'.",
          [element],
      )


class OfficesHaveValidOfficeRole(base.BaseRule):
  """Each office must have valid office role(s)."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_roles = [role.text for role in element.findall("Role")]
    if not office_roles:
      office_roles = [
          office_role.strip()
          for office_role in get_external_id_values(element, "office-role")
      ]

    if not office_roles:
      raise loggers.ElectionError.from_message(
          "Office is missing an office role.",
          [element],
      )
    if len(office_roles) == 1:
      office_role = office_roles[0]
      if office_role not in office_utils.VALID_OFFICE_ROLES:
        raise loggers.ElectionError.from_message(
            f"Office has an invalid office role: '{office_role}'.",
            [element],
        )
    elif len(office_roles) == 2:
      if set(office_roles) not in _VALID_OFFICE_ROLE_COMBINATIONS:
        raise loggers.ElectionError.from_message(
            "Office has an invalid combination of office roles: "
            f"{office_roles}. Valid combinations are "
            f"{_VALID_OFFICE_ROLE_COMBINATIONS}.",
            [element],
        )
    else:
      raise loggers.ElectionError.from_message(
          "Office has more than two office roles.",
          [element],
      )


class ContestHasValidContestStage(base.BaseRule):
  """Each Contest must have a valid contest-stage."""

  def elements(self):
    return ["CandidateContest", "PartyContest", "BallotMeasureContest"]

  def check(self, element):
    contest_stage_values = [
        contest_stage_value.strip()
        for contest_stage_value in get_external_id_values(
            element, "contest-stage"
        )
    ]
    for contest_stage_value in contest_stage_values:
      if contest_stage_value not in _CONTEST_STAGE_TYPES:
        raise loggers.ElectionError.from_message(
            "The contest has invalid contest-stage '{}'.".format(
                contest_stage_value
            ),
            [element],
        )


class DateOfBirthIsInPast(base.DateRule):
  """Date of Birth should not be in the future."""

  def elements(self):
    return ["PersonCollection"]

  def check(self, element):
    for person_element in element:
      date_of_birthday = person_element.find("DateOfBirth")
      if date_of_birthday is not None and date_of_birthday.text:
        date_of_birthday = base.PartialDate.init_partial_date(
            date_of_birthday.text
        )
        self.check_for_date_in_past(date_of_birthday, person_element)
        if self.error_log:
          raise loggers.ElectionError(self.error_log)


class ElectionContainsStartAndEndDates(base.DateRule):
  """Election elements should have start and end dates populated."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_elem is None:
      self.error_log.append(
          loggers.LogEntry(
              "Election {} is missing a start date.".format(
                  element.get("objectId")
              )
          )
      )

    if self.end_elem is None:
      self.error_log.append(
          loggers.LogEntry(
              "Election {} is missing an end date.".format(
                  element.get("objectId")
              )
          )
      )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


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


class ElectionEndDatesInThePast(base.DateRule):
  """Election elements would be in the present or in the future.

  Using a past end date needs to be notified. The warning is useful to prevent
  using a wrong date.

  A bounded election with a past end date is an error since the date should be
  confirmed. The only exception to this is elections that are postponed or
  canceled.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)
    date_type = element.find("ElectionDateType")
    if date_type is not None and date_type.text.lower() == "bounded":
      if self.end_date:
        self.check_for_date_not_in_past(self.end_date, self.end_elem)
      if self.error_log:
        date_status = element.find("ElectionDateStatus")
        if date_status is None or date_status.text.lower() not in [
            "postponed",
            "canceled",
        ]:
          raise loggers.ElectionError.from_message(
              "A bounded election should not have an end date in the past."
          )
        self.reset_instance_vars()
    for contest in self.get_elements_by_class(element, "Contest"):
      subsequent_contest_id_element = contest.find("SubsequentContestId")
      if subsequent_contest_id_element is not None:
        continue
      else:
        if self.end_date:
          self.check_for_date_not_in_past(self.end_date, self.end_elem)
    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ElectionEndDatesOccurAfterStartDates(base.DateRule):
  """Election elements should contain a coherent start and end dates.

  End dates should not occur before the start date.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class ValidPartyLeadershipDates(base.DateRule):
  """Party Leadership start/end dates should be valid if specified.

  End dates should not occur before the start date.
  """

  def elements(self):
    return ["PartyLeadership"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)
    self.check_end_after_start()
    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ElectionDatesSpanContestDates(base.DateRule):
  """Election start/end dates should span the Contest start/end dates.

  The start date of the Election should be on or before the start date of every
  included Contest. The end date of the Election should be on or after the end
  date of every included Contest. Only Contests that have the dates populated
  will be considered.
  """

  def elements(self):
    return ["ElectionReport"]

  def _validate_contest_dates_within_election(self, election, contest):
    self.reset_instance_vars()
    self.gather_dates(election)
    election_start_date = self.start_date
    election_end_date = self.end_date
    election_id = election.get("objectId")
    self.reset_instance_vars()
    self.gather_dates(contest)
    contest_id = contest.get("objectId")
    contest_date_status = contest.find("ContestDateStatus")
    if (
        election_end_date is not None
        and self.end_date is not None
        and election_end_date < self.end_date
        # Only compare election end date to contests that are not canceled
        and (
            contest_date_status is None
            or contest_date_status.text.lower() != "canceled"
        )
    ):
      self.error_log.append(
          loggers.LogEntry(
              "Contest {} with end date {} occurs after Election {} with"
              " end date {}. Election end date should be on or after any"
              " Contest end date.".format(
                  contest_id,
                  self.end_date,
                  election_id,
                  election_end_date,
              )
          )
      )
    if (
        election_start_date is not None
        and self.start_date is not None
        and self.start_date < election_start_date
    ):
      self.error_log.append(
          loggers.LogEntry(
              "Contest {} with start date {} occurs before Election {} with"
              " start date {}. Election start date should be on or before"
              " any Contest start date.".format(
                  contest_id,
                  self.start_date,
                  election_id,
                  election_start_date,
              )
          )
      )

  def check(self, election_report_element):
    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      for contest in self.get_elements_by_class(election, "Contest"):
        self._validate_contest_dates_within_election(election, contest)

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ElectionTypesAreCompatible(base.BaseRule):
  """Election element Type values cannot be both a general and primary type."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    election_types = element.findall("Type")
    if election_types:
      for i in range(len(election_types)):
        election_types[i] = election_types[i].text
      if "general" in election_types and (
          "primary" in election_types
          or "partisan-primary-open" in election_types
          or "partisan-primary-closed" in election_types
      ):
        raise loggers.ElectionError.from_message(
            "Election element has incompatible election-type values.", [element]
        )


class ElectionTypesAndCandidateContestTypesAreCompatible(base.BaseRule):
  """Election elements should contain CandidateContests with compatible types.

  Elections with the general type should not have any CandidateContests with the
  primary types. Elections with the primary types should not have any
  CandidateContests with the general type.
  """

  def _extract_text_from_elements(self, elements):
    return {
        element.text.strip().lower()
        for element in elements
        if element_has_text(element)
    }

  def elements(self):
    return ["Election"]

  def check(self, element):
    errors = []
    contests = self.get_elements_by_class(element, "CandidateContest")
    election_types = self._extract_text_from_elements(element.findall("Type"))
    primary_types = {
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    }
    for contest in contests:
      contest_types = self._extract_text_from_elements(contest.findall("Type"))
      if "general" in election_types and primary_types.intersection(
          contest_types
      ):
        errors.append(
            loggers.LogEntry(
                "Election %s includes CandidateContest %s with incompatible"
                " type(s). General elections cannot include primary contests."
                % (element.get("objectId"), contest.get("objectId")),
                element,
            )
        )
      elif (
          primary_types.intersection(election_types)
          and "general" in contest_types
      ):
        errors.append(
            loggers.LogEntry(
                "Election %s includes CandidateContest %s with incompatible"
                " type(s). Primary elections cannot include general contests."
                % (element.get("objectId"), contest.get("objectId")),
                element,
            )
        )

    if errors:
      raise loggers.ElectionError(errors)


class DateStatusMatches(base.DateRule):
  """In most cases, ContestDateStatus should match ElectionDateStatus.

  If all contests contained in an election have the same status, and this status
  does not match the status on the election, it is probably incorrect - raise
  warning.  Differing values among ContestDateStatus in an election are possible
  but uncommon - raise Info level message.
  """

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_date_status = "confirmed"  # default value
    election_status_elem = election_elem.find("ElectionDateStatus")

    if element_has_text(election_status_elem):
      election_date_status = election_status_elem.text.strip()

    contest_statuses = set()
    for contest_elem in self.get_elements_by_class(election_elem, "Contest"):
      contest_status_elem = contest_elem.find("ContestDateStatus")
      if element_has_text(contest_status_elem):
        contest_statuses.add(contest_status_elem.text.strip())
      else:
        contest_statuses.add("confirmed")

    if len(contest_statuses) == 1:
      contest_status = contest_statuses.pop()
      if contest_status != election_date_status:
        msg = (
            "All contests on election {} have a date status of {}, but the "
            "election has a date status of {}.".format(
                election_elem.get("objectId"),
                contest_status,
                election_date_status,
            )
        )
        raise loggers.ElectionWarning.from_message(msg, [election_elem])
    elif len(contest_statuses) > 1:
      msg = (
          "There are multiple date statuses present for the contests on "
          "election {}.  This may be correct, but is an unusal case.  Please "
          "confirm.".format(election_elem.get("objectId"))
      )
      raise loggers.ElectionInfo.from_message(msg, [election_elem])


class OfficeSelectionMethodMatch(base.BaseRule):
  """Office and OfficeHolderTenure need to have matching selection methods.

  Ensure that the OfficeSelectionMethod of a given OfficeHolderTenure is
  also
  present in the list of SelectionMethods of the Office it points to.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.office_selection_methods = {}
    officeholder_tenure_elements = self.get_elements_by_class(
        election_tree, "OfficeHolderTenure"
    )
    office_elements = self.get_elements_by_class(election_tree, "Office")
    if officeholder_tenure_elements:
      for element in office_elements:
        office_id = element.get("objectId")
        selection_methods = {
            selection_method.text
            for selection_method in element.findall("SelectionMethod")
        }
        self.office_selection_methods[office_id] = selection_methods

  def elements(self):
    return ["OfficeHolderTenure"]

  def check(self, element):
    office_id = element.find("OfficeId").text
    office_selection_method = element.find("OfficeSelectionMethod").text
    if (
        office_id not in self.office_selection_methods
        or office_selection_method
        not in self.office_selection_methods[office_id]
    ):
      raise loggers.ElectionError.from_message(
          "OfficeSelectionMethod does not have a matching SelectionMethod"
          " in the corresponding Office element.",
          [element],
      )


class OfficeHolderTenureTermDates(base.DateRule):
  """OfficeHolderTenure elements should contain valid term dates."""

  def elements(self):
    return ["OfficeHolderTenure"]

  def check(self, element):
    start_date = element.find("StartDate")
    end_date = element.find("EndDate")
    if element_has_text(start_date) and element_has_text(end_date):
      start_date_obj = base.PartialDate.init_partial_date(start_date.text)
      end_date_obj = base.PartialDate.init_partial_date(end_date.text)
      if end_date_obj < start_date_obj:
        raise loggers.ElectionError.from_message(
            "OfficeHolderTenure element has an EndDate that is before the"
            " StartDate.",
            [element],
        )


class OfficeTermDates(base.DateRule):
  """Office elements should contain valid term dates.

  Offices with OfficeHolderPersonIds should have a Term declared. Given
  term should have a start date. If term also has an end date then end date
  should come after start date. Post Office split feed office objects should
  not have a Term element.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    if officeholder_tenure_collection_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    self.reset_instance_vars()
    if self.is_post_office_split_feed:
      term = element.find("Term")
      if term is not None:
        raise loggers.ElectionError.from_message(
            "Office should not contain Term data in post Office split feed.",
            [element],
        )
      if self.error_log:
        raise loggers.ElectionError(self.error_log)
    else:
      off_per_id = element.find("OfficeHolderPersonIds")
      if element_has_text(off_per_id):
        term = element.find("Term")
        if term is None:
          raise loggers.ElectionWarning.from_message(
              "The Office is missing a Term.", [element]
          )

        self.gather_dates(term)
        if self.start_date is None:
          raise loggers.ElectionWarning.from_message(
              "The Office is missing a Term > StartDate.", [element]
          )
        elif self.end_date is not None:
          self.check_end_after_start()

      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class RemovePersonAndOfficeHolderId60DaysAfterEndDate(base.TreeRule):
  """Office elements should contain valid term dates.

  Check if 60 days after the specified office term EndDate,
  the associated Person and OfficeholderId may be removed from the feed.
  However, if the Person is elected to another office,
  they will be kept in the feed with the same stable ID.
  """

  def check(self):
    info_log = []
    persons = self.get_elements_by_class(self.election_tree, "Person")
    offices = self.get_elements_by_class(self.election_tree, "Office")
    officeholder_tenure_collection = self.get_elements_by_class(
        self.election_tree, "OfficeHolderTenureCollection"
    )
    is_post_office_split_feed = bool(officeholder_tenure_collection)
    person_office_dict = dict()
    outdated_offices = []
    outdated_officeholder_tenures = []
    outdated_officetenure_persons = dict()
    if is_post_office_split_feed:
      officeholder_tenures = self.get_elements_by_class(
          self.election_tree, "OfficeHolderTenure"
      )
      for officeholder_tenure in officeholder_tenures:
        office_holder_person_elem = officeholder_tenure.find(
            "OfficeHolderPersonId"
        )
        person_id = office_holder_person_elem.text
        date_validator = base.DateRule(None, None)
        date_validator.gather_dates(officeholder_tenure)
        end_date = date_validator.end_date
        if end_date is not None:
          sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
              days=-60
          )
          partial_date_sixty_days = base.PartialDate(
              sixty_days_earlier.year,
              sixty_days_earlier.month,
              sixty_days_earlier.day,
          )
          if end_date < partial_date_sixty_days:
            outdated_officeholder_tenures.append(officeholder_tenure)
          if person_id in outdated_officetenure_persons.keys():
            outdated_officetenure_persons[person_id].append(
                (office_holder_person_elem, end_date)
            )
          else:
            outdated_officetenure_persons[person_id] = [
                (office_holder_person_elem, end_date)
            ]
      for outdated_officeholder_tenure in outdated_officeholder_tenures:
        info_message = (
            "The officeholder tenure end date is more than 60 days"
            " in the past; this OfficeHolderTenure element can be removed"
            " from the feed."
        )
        info_log.append(
            loggers.LogEntry(info_message, [outdated_officeholder_tenure])
        )
      for person_id, value_list in outdated_officetenure_persons.items():
        has_recent_tenure = False
        office_holder_person_elem = None
        for value in value_list:
          office_holder_person_elem = value[0]
          end_date = value[1]
          sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
              days=-60
          )
          partial_date_sixty_days = base.PartialDate(
              sixty_days_earlier.year,
              sixty_days_earlier.month,
              sixty_days_earlier.day,
          )
          if end_date > partial_date_sixty_days:
            has_recent_tenure = True
        if not has_recent_tenure and office_holder_person_elem is not None:
          info_message = (
              "All officeholder tenures ended more than 60 days ago. "
              "Therefore, you can remove the person and the "
              "related officeholder tenures from the feed."
          )
          info_log.append(
              loggers.LogEntry(info_message, [office_holder_person_elem])
          )
    else:
      for office in offices:
        person_id = office.find("OfficeHolderPersonIds").text
        if person_id in person_office_dict:
          person_office_dict[person_id].append(office.get("objectId"))
        else:
          person_office_dict[person_id] = [office.get("objectId")]
        term = office.find(".//Term")
        if term is not None:
          date_validator = base.DateRule(None, None)
          date_validator.gather_dates(term)
          end_date_person = date_validator.end_date
          if end_date_person is not None:
            sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
                days=-60
            )
            partial_date_sixty_days = base.PartialDate(
                sixty_days_earlier.year,
                sixty_days_earlier.month,
                sixty_days_earlier.day,
            )
            if end_date_person < partial_date_sixty_days:
              outdated_offices.append(office.get("objectId"))
      for person in persons:
        pid = person.get("objectId")
        if person_office_dict.get(pid) is not None:
          check_person_outdated = all(
              item in outdated_offices for item in person_office_dict.get(pid)
          )
          if check_person_outdated:
            info_message = (
                "The officeholder mandates ended more than 60 days ago. "
                "Therefore, you can remove the person and the related offices "
                "from the feed."
            )
            info_log.append(loggers.LogEntry(info_message, [person]))
    if info_log:
      raise loggers.ElectionInfo(info_log)


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
        date_validator = base.DateRule(None, None, ocd_id_validator=None)
        try:
          date_validator.gather_dates(term)
          if date_validator.end_date is not None:
            date_validator.check_for_date_not_in_past(
                date_validator.end_date, date_validator.end_elem
            )
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

      start_date_elem = office.find(".//Term//StartDate")
      if not element_has_text(start_date_elem):
        continue
      start_date = start_date_elem.text

      office_roles = get_entity_info_for_value_type(office, "office-role")
      if office_roles:
        office_role = office_roles[0]

      jurisdiction_ids = get_entity_info_for_value_type(
          office, "jurisdiction-id"
      )
      if jurisdiction_ids:
        jurisdiction_id = jurisdiction_ids[0]

      office_hash = hashlib.sha256(
          (office_role + jurisdiction_id).encode("utf-8")
      ).hexdigest()
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
          warning_log.append(
              loggers.LogEntry(
                  (
                      "Only one unique StartDate found for each"
                      " jurisdiction-id: {} and office-role: {}. {} appears {}"
                      " times."
                  ).format(
                      start_info["jurisdiction_id"],
                      start_info["office_role"],
                      start_date,
                      len(start_date_map[start_date]),
                  ),
                  start_date_map[start_date],
              )
          )

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
          "GpUnit is required to have exactly one InterationalizedName"
          " element.",
          [element],
      )
    intl_name = intl_names[0]
    name_texts = intl_name.findall("Text")
    if name_texts is None or not name_texts:
      raise loggers.ElectionError.from_message(
          (
              "GpUnit InternationalizedName is required to have one or more"
              " Text elements."
          ),
          [intl_name],
      )
    error_log = []
    for name_text in name_texts:
      if name_text is None or not (name_text.text and name_text.text.strip()):
        error_log.append(
            loggers.LogEntry(
                "GpUnit InternationalizedName does not have a text value.",
                [name_text],
            )
        )

    if error_log:
      raise loggers.ElectionError(error_log)


class ValidateInfoUriAnnotation(base.BaseRule):
  """InfoUri is an annotated Uri that accepts the following annotations.

  wikipedia, ballotpedia, official-website, fulltext.
  Adding a check for this.
  """

  info_array = [
      "wikipedia",
      "ballotpedia",
      "official-website",
      "fulltext",
      "logo-uri",
  ]

  def elements(self):
    return ["InfoUri"]

  def check(self, element):
    error_log = []
    annotation = element.attrib["Annotation"]
    if annotation not in self.info_array:
      error_log.append(
          loggers.LogEntry(annotation + " is an invalid annotation.", [element])
      )
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
        msg = (
            "FullText is longer than %s characters. Please remove and "
            "include a link to the full text via InfoUri with Annotation "
            "'fulltext'." % (self.MAX_LENGTH)
        )
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
    for language, full_text_strings in full_text_map.items():
      full_text_string = full_text_strings[0]
      if (
          language not in ballot_text_map.keys()
          and len(full_text_string) < self.SUGGESTION_CUTOFF_LENGTH
      ):
        msg = (
            "Language: %s.  BallotText is missing but FullText is present "
            "for the same language. Please confirm that FullText contains "
            "only supplementary text and not text on the ballot itself."
            % (language)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class BallotTitle(base.BaseRule):
  """BallotTitle must exist and should usually be shorter than BallotText."""

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    ballot_title_map = get_language_to_text_map(element.find("BallotTitle"))
    if not ballot_title_map:
      raise loggers.ElectionError.from_message(
          "BallotMeasureContest is missing BallotTitle.", [element]
      )

    ballot_text_map = get_language_to_text_map(element.find("BallotText"))
    if not ballot_text_map:
      msg = (
          "BallotText is missing. Please confirm that the ballot "
          "text/question is not in BallotTitle."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])

    for language, ballot_title_strings in ballot_title_map.items():
      ballot_title_string = ballot_title_strings[0]
      if language not in ballot_text_map.keys() or len(
          ballot_text_map[language][0]
      ) < len(ballot_title_string):
        msg = (
            "Language: %s. BallotText is missing or shorter than "
            " Please confirm that the ballot text/question is not "
            "in BallotTitle." % (language)
        )
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
    candidates = self.get_elements_by_class(
        self.election_tree, "CandidateCollection//Candidate"
    )
    for candidate in candidates:
      ballot_name = candidate.find(".//BallotName/Text[@language='en']")
      if ballot_name is not None:
        if ballot_name.text.lower() in self._BALLOT_SELECTION_OPTIONS:
          invalid_candidates.append(candidate.get("objectId"))
    return invalid_candidates

  def check(self):
    candidate_contest_mapping = {}
    candidate_contests = self.get_elements_by_class(
        self.election_tree, "CandidateContest"
    )
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
        warning_message = (
            "Candidates {} should be BallotMeasureSelection "
            "elements. Similarly, Contest {} should be changed "
            "to a BallotMeasureContest instead of a "
            "CandidateContest."
        ).format(", ".join(flagged_candidates), contest_id)
        warning_log.append(loggers.LogEntry(warning_message))
    if invalid_candidates:
      warning_message = (
          "There are CandidateContests that appear to be "
          "BallotMeasureContests based on the "
          "BallotName values."
      )
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
        "Party": [
            "PartyScopeGpUnitIds",
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
    }


class PartySpanMultipleCountries(base.BaseRule):
  """Check if a party operate on multiple countries.

  Parties can have PartyScopeGpUnitIds which span multiple countries. This is
  sometimes correct, but we should flag it to double check.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(PartySpanMultipleCountries, self).__init__(
        election_tree, schema_tree, **kwargs
    )
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
      gpunit_country_mapping = " / ".join([
          "%s -> %s" % (key, str(value))
          for (key, value) in referenced_country.items()
      ])

      raise loggers.ElectionWarning.from_message(
          (
              "PartyScopeGpUnitIds refer to GpUnit from different countries:"
              " {}. Please double check.".format(gpunit_country_mapping)
          ),
          [element],
      )


class NonExecutiveOfficeShouldHaveGovernmentBody(base.BaseRule):
  """Ensure non-executive Office elements have a government body defined."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    if officeholder_tenure_collection_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    if not _is_executive_office(
        element, self.is_post_office_split_feed
    ) and not _has_government_body(element):
      raise loggers.ElectionInfo.from_message(
          "Non-executive Office element is missing a government body.",
          [element],
      )


class ExecutiveOfficeShouldNotHaveGovernmentBody(base.BaseRule):
  """Ensure executive Office elements do not have a government body defined."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    if officeholder_tenure_collection_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    if _is_executive_office(
        element, self.is_post_office_split_feed
    ) and _has_government_body(element):
      office_roles = _get_office_roles(element, self.is_post_office_split_feed)
      raise loggers.ElectionError.from_message(
          f"Executive Office element (roles: {','.join(office_roles)}) has a "
          "government body. Executive offices should not have government "
          "bodies.",
          [element],
      )


class MissingOfficeSelectionMethod(base.BaseRule):
  """Checks that SelectionMethod is present and .

  Values supported for SelectionMethod:
  -appointed
  -directly-elected
  -hereditary
  -indirectly-elected
  -succession
  -ex-officio
  """

  def elements(self):
    return ["Office"]

  def check(self, element):
    selection = element.find("SelectionMethod")
    if selection is None:
      raise loggers.ElectionWarning.from_message(
          "Office element is missing its SelectionMethod.", [element]
      )


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
    contest_by_id = {}
    contest_end_date_by_id = {}

    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      self.gather_dates(election)
      election_end_date = self.end_date
      for contest in self.get_elements_by_class(election, "Contest"):
        self.reset_instance_vars()
        self.gather_dates(contest)
        contest_by_id[contest.get("objectId")] = contest
        contest_end_date_by_id[contest.get("objectId")] = (
            self.end_date or election_end_date
        )

    for contest_id, contest in contest_by_id.items():
      element = contest.find("SubsequentContestId")
      if not element_has_text(element):
        continue
      subsequent_contest_id = element.text.strip()

      # Check that subsequent contest exists
      if subsequent_contest_id not in contest_by_id:
        error_log.append(
            loggers.LogEntry(
                "Could not find SubsequentContest"
                f" {subsequent_contest_id} referenced by Contest {contest_id}."
            )
        )
        continue

      subsequent_contest = contest_by_id[subsequent_contest_id]
      # Check that the subsequent contest has a later end date
      if subsequent_contest is not None and contest is not None:
        contest_end_date = contest_end_date_by_id[contest_id]
        subsequent_contest_end_date = contest_end_date_by_id[
            subsequent_contest_id
        ]
        if subsequent_contest_end_date < contest_end_date:
          error_log.append(
              loggers.LogEntry(
                  f"Contest {contest_id} references a subsequent contest with"
                  " an earlier end date.",
                  [contest],
                  [contest.sourceline],
              )
          )

      # Check that office ids match
      contest_office_id = None
      subsequent_contest_office_id = None
      element = contest.find("OfficeIds")
      if element_has_text(element):
        contest_office_id = element.text
      element = subsequent_contest.find("OfficeIds")
      if element_has_text(element):
        subsequent_contest_office_id = element.text

      if contest_office_id != subsequent_contest_office_id:
        error_log.append(
            loggers.LogEntry(
                f"Contest {contest_id} references a subsequent contest with a"
                " different office id.",
                [contest],
                [contest.sourceline],
            )
        )

      # Check that primary party ids match or that the subsequent contest does
      # not have a primary party (e.g. primary -> general election)
      contest_primary_party_ids = None
      subsequent_contest_primary_party_ids = None
      element = contest.find("PrimaryPartyIds")
      if element_has_text(element):
        contest_primary_party_ids = set(element.text.split())
      element = subsequent_contest.find("PrimaryPartyIds")
      if element_has_text(element):
        subsequent_contest_primary_party_ids = set(element.text.split())

      if (
          subsequent_contest_primary_party_ids is not None
          and contest_primary_party_ids != subsequent_contest_primary_party_ids
      ):
        error_log.append(
            loggers.LogEntry(
                "Contest %s references a subsequent contest with different "
                "primary party ids." % contest_id,
                [contest],
                [contest.sourceline],
            )
        )

      # Check that there is not a subsequent contest <-> composing contest loop
      element = subsequent_contest.find("ComposingContestIds")
      if element_has_text(element):
        subsequent_composing_ids = element.text.split()
        if contest_id in subsequent_composing_ids:
          error_log.append(
              loggers.LogEntry(
                  f"Contest {contest_id} is listed as a composing contest for"
                  " its subsequent contest. Two contests can be linked by"
                  " SubsequentContestId or ComposingContestId, but not both.",
                  [contest],
                  [contest.sourceline],
              )
          )

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
                  "strict hierarchy." % contest_id
              )
          )

    for contest_id, composing_contest_ids in composing_contests.items():
      contest = contest_ids[contest_id]
      for cc_id in composing_contest_ids:
        # Check that the composing contests exist
        if cc_id not in contest_ids.keys():
          error_log.append(
              loggers.LogEntry(
                  "Could not find ComposingContest % referenced by Contest %s."
                  % (contest_id, cc_id)
              )
          )
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
                  "ids." % (contest_id, cc_id)
              )
          )

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
                  "party ids." % (contest_id, cc_id)
              )
          )

        # Check that composing contests don't reference each other
        if (
            cc_id in composing_contests
            and contest_id in composing_contests[cc_id]
        ):
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and contest %s reference each other as composing "
                  "contests." % (contest_id, cc_id)
              )
          )

    if error_log:
      raise loggers.ElectionError(error_log)


class MultipleInternationalizedTextWithSameLanguageCode(base.BaseRule):
  """Checks for multiple InternationalizedText with the same language code."""

  def elements(self):
    return _INTERNATIONALIZED_TEXT_ELEMENTS

  def check(self, element):
    language_map = get_language_to_text_map(element)

    for language, texts in language_map.items():
      if len(texts) > 1:
        raise loggers.ElectionError.from_message(
            'Multiple "%s" texts found for "%s"' % (language, texts[0].strip())
        )


class AllInternationalizedTextHaveEnVersion(base.BaseRule):
  """Checks for Internationalized Text Elements missing the english version."""

  def elements(self):
    return [
        "BallotName",
        "Directions",
        "BallotSubTitle",
        "BallotTitle",
        "Name",
        "InternationalizedName",
        "InternationalizedAbbreviation",
        "Alias",
        "FullName",
        "Profession",
        "Title",
    ]

  def check(self, element):
    language_map = get_language_to_text_map(element)
    if "en" not in language_map:
      raise loggers.ElectionInfo.from_message(
          message='No "english" version found for the InternationalizedText.',
          elements=[element],
      )


class ContestContainsValidStartDate(base.DateRule):
  """Contest elements should contain valid start dates.

  A warning will be raised for start dates in the past. These dates are still
  valid because the validator could be run during an ongoing election.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_date:
      self.check_for_date_not_in_past(self.start_date, self.start_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ContestContainsValidEndDate(base.DateRule):
  """Contest elements should contain valid end dates.

  A warning will be raised for end dates in the past. These dates are still
  valid because the validator could be run during an ongoing election.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date:
      self.check_for_date_not_in_past(self.end_date, self.end_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ContestEndDateOccursAfterStartDate(base.DateRule):
  """Contest elements should have end dates that occur after the start dates."""

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class ContestEndDateOccursBeforeSubsequentContestStartDate(base.DateRule):
  """Contest end dates should occur before subsequent contest start dates.

  This rule will trigger if a Contest has a valid Subsequent Contest and both
  Contests have dates.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    contest_by_contest_id = {}
    dates_by_contest_id = {}

    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      for contest in self.get_elements_by_class(election, "Contest"):
        contest_id = contest.get("objectId")
        self.reset_instance_vars()
        self.gather_dates(contest)
        contest_by_contest_id[contest_id] = contest
        dates_by_contest_id[contest_id] = (self.start_date, self.end_date)

    for contest_id, contest in contest_by_contest_id.items():
      # ignore contests that don't have a subsequent contest
      subsequent_element = contest.find("SubsequentContestId")
      if not element_has_text(subsequent_element):
        continue
      # ignore invalid subsequent contest ids
      subsequent_contest_id = subsequent_element.text.strip()
      if subsequent_contest_id not in contest_by_contest_id:
        continue
      # compare contest end date with subsequent contest start date
      _, contest_end = dates_by_contest_id[contest_id]
      subsequent_contest_start, _ = dates_by_contest_id[subsequent_contest_id]
      if contest_end is not None and subsequent_contest_start is not None:
        if subsequent_contest_start < contest_end:
          self.error_log.append(
              loggers.LogEntry(
                  "Contest {} with end date {} does not occur before"
                  " subsequent contest {} with start date {}".format(
                      contest_id,
                      contest_end,
                      subsequent_contest_id,
                      subsequent_contest_start,
                  )
              )
          )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ContestStartDateContainsCorrespondingEndDate(base.DateRule):
  """Contest start dates must always have corresponding end dates.

  A Contest can either have both StartDate and EndDate populated or neither at
  all.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_elem is None and self.end_elem is not None:
      raise loggers.ElectionError.from_message(
          "Contest has an EndDate but is missing a StartDate. Every EndDate"
          " must have a corresponding StartDate.",
          [element],
      )

    if self.start_elem is not None and self.end_elem is None:
      raise loggers.ElectionError.from_message(
          "Contest has a StartDate but is missing an EndDate. Every StartDate"
          " must have a corresponding EndDate.",
          [element],
      )


class CandidateContestTypesAreCompatible(base.BaseRule):
  """CandidateContest Type values cannot have both a general and primary type."""

  def elements(self):
    return ["CandidateContest"]

  def check(self, element):
    primary_types = {
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    }
    contest_type_elements = element.findall("Type")
    if contest_type_elements:
      contest_types = {
          type_element.text.strip().lower()
          for type_element in contest_type_elements
          if element_has_text(type_element)
      }
      if "general" in contest_types and primary_types.intersection(
          contest_types
      ):
        raise loggers.ElectionError.from_message(
            "CandidateContest {} has incompatible type values. A contest cannot"
            " have both a general and primary type.".format(
                element.get("objectId")
            ),
            [element],
        )


class CommitteeClassificationEndDateOccursAfterStartDate(base.DateRule):
  """CommitteeClassification elements should have end dates that occur after the start dates."""

  def elements(self):
    return ["CommitteeClassification"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class AffiliationEndDateOccursAfterStartDate(base.DateRule):
  """Affiliation elements should have end dates that occur after the start dates."""

  def elements(self):
    return ["Affiliation"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class EinMatchesFormat(base.BaseRule):
  """EIN id should be in the following format: XX-XXXXXXX."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(EinMatchesFormat, self).__init__(election_tree, schema_tree, **kwargs)
    regex = r"\d{2}(-\d{7})?"
    self.ein_id_matcher = re.compile(regex, flags=re.U)

  def elements(self):
    return ["Committee"]

  def check(self, element):
    external_identifiers = element.find("ExternalIdentifiers")
    if external_identifiers is not None:
      ein_ids = get_external_id_values(external_identifiers, "ein")
      if ein_ids:
        e_id = ein_ids.pop()
        if not self.ein_id_matcher.match(e_id):
          raise loggers.ElectionError.from_message(
              "EIN id '{}' is not in the correct format.".format(e_id),
              [element],
          )


class AffiliationHasEitherPartyOrPerson(base.BaseRule):
  """Affiliation should contain either a Party or a Person objectId."""

  def elements(self):
    return ["Affiliation"]

  def check(self, element):
    party_id = element.find("PartyId")
    person_id = element.find("PersonId")
    if not ((party_id is None) ^ (person_id is None)):
      raise loggers.ElectionError.from_message(
          "Affiliation must have one of: PartyId, PersonId. Cannot include"
          " both.",
          [element],
      )


class FeedTypeHasValidFeedLongevity(base.BaseRule):
  """Feeds types should have valid corresponding FeedLongevity."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_type_element = element.find("FeedType")
    feed_longevity_element = element.find("FeedLongevity")
    if element_has_text(feed_type_element) and element_has_text(
        feed_longevity_element
    ):
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
      if element_has_text(feed_element.find("FeedId")):
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
      if element_has_text(feed_element.find("SourceDirPath")):
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


class ElectionEventDatesAreSequential(base.DateRule):
  """Dates in an ElectionEvent element should be sequential."""

  def elements(self):
    return ["ElectionEvent"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)
    self.check_end_after_start()
    if element_has_text(element.find("FullDeliveryDate")) and self.start_date:
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
    if element_has_text(
        element.find("InitialDeliveryDate")
    ) and element_has_text(element.find("FullDeliveryDate")):
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
    if element_has_text(element.find("SourceDirPath")):
      return
    today = datetime.date.today()
    today_partial_date = base.PartialDate(
        year=today.year, month=today.month, day=today.day
    )
    initial_deliveries = element.findall(".//InitialDeliveryDate") or []
    for initial_delivery in initial_deliveries:
      initial_delivery_date = (
          base.PartialDate.init_partial_date(initial_delivery.text)
          if element_has_text(initial_delivery)
          else None
      )
      if initial_delivery_date and initial_delivery_date < today_partial_date:
        raise loggers.ElectionError.from_message(
            "SourceDirPath is not set but an InitialDeliveryDate is in the "
            f"past for feed {element.find('FeedId').text}.",
            [element],
        )


class OfficeHolderSubFeedDatesAreSequential(base.DateRule):
  """Dates in an OfficeHolderSubFeed element should be sequential."""

  def elements(self):
    return ["OfficeHolderSubFeed"]

  def check(self, element):
    if element_has_text(
        element.find("InitialDeliveryDate")
    ) and element_has_text(element.find("FullDeliveryDate")):
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
    if element_has_text(element.find("FeedInactiveDate")):
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
        if element_has_text(
            election_event_element.find("ElectionDateStatus")
        ) and (
            election_event_element.find("ElectionDateStatus").text
            in self.ignorable_election_date_statuses
        ):
          continue
        if element_has_text(election_event_element.find("EndDate")):
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
    if element_has_text(country_code_element):
      country_code = country_code_element.text.upper()
      if not country_code_is_valid(country_code):
        raise loggers.ElectionError.from_message(
            "Invalid country code {}.".format(country_code),
            [element],
        )
    else:
      feed_type = element.find("FeedType")
      if (
          element_has_text(feed_type)
          and feed_type.text.lower().replace("_", "-") == "election-dates"
      ):
        return
      raise loggers.ElectionError.from_message(
          "Feed {} is missing CountryCode.".format(element.find("FeedId").text),
          [element],
      )


class FeedInactiveDateSetForNonEvergreenFeed(base.BaseRule):
  """All non-evergreen feeds should have a FeedInactiveDate set."""

  def elements(self):
    return ["Feed"]

  def check(self, element):
    feed_longevity = element.find("FeedLongevity")
    if (
        element_has_text(feed_longevity)
        and feed_longevity.text.lower() != "evergreen"
        and not element_has_text(element.find("FeedInactiveDate"))
    ):
      raise loggers.ElectionError.from_message(
          "FeedInactiveDate is not set for non-evergreen feed with FeedId {}."
          .format(element.find("FeedId").text),
          [element],
      )


class UnreferencedEntitiesBase(base.TreeRule):
  """All non-top-level entities in a feed should be referenced by at least one other entity.

  In the context of this rule, top-level means that an entity is not expected to
  be referenced by anything else in the feed. This base class allows derived
  rules to specify the set of top-level and warning-level entities since these
  differ by feed type. The rule is an info for gpunits (as long as they have
  ComposingGpunitIds) since top-level gpunits may exist solely to contain
  others.
  """

  def __init__(
      self,
      election_tree,
      schema_tree,
      top_level_entity_types,
      warned_entity_types,
      **kwargs,
  ):
    super(UnreferencedEntitiesBase, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.referenced_entities = self._gather_referenced_entities()
    self.top_level_entity_types = top_level_entity_types
    self.warned_entity_types = warned_entity_types

  def _get_idref_elements(self):
    """Returns the names of all XML elements in the schema of type IDREF or IDREFS."""

    idref_elements = set()
    for _, element in etree.iterwalk(self.schema_tree):
      tag = self.strip_schema_ns(element)
      if (
          tag
          and tag == "element"
          and element.get("type") in ("xs:IDREF", "xs:IDREFS")
      ):
        idref_elements.add(element.get("name"))
    return idref_elements

  def _gather_referenced_entities(self):
    """Create a set of all entities referenced by either IDREF(S) elements or external identifiers."""

    idref_elements = self._get_idref_elements()
    referenced_entities = set()
    for external_id_type in _IDREF_EXTERNAL_IDENTIFIERS:
      referenced_entities.update(
          get_external_id_values(self.election_tree, external_id_type)
      )
    for _, element in etree.iterwalk(self.election_tree):
      tag = self.strip_schema_ns(element)
      if tag and tag in idref_elements:
        referenced_entities.update(element.text.split())
    return referenced_entities

  def check(self):
    for _, element in etree.iterwalk(self.election_tree):
      element_name = element.tag
      # Skip anything without an object id.
      if "objectId" not in element.attrib:
        continue
      obj_id = element.get("objectId")
      if (
          obj_id not in self.referenced_entities
          and element_name not in self.top_level_entity_types
      ):
        if element_name in self.warned_entity_types:
          raise loggers.ElectionWarning.from_message(
              f"Element of type {element_name} with object id {obj_id} is not"
              " referenced by anything else in the feed. This is only ok if"
              " there are explicit instructions to include this entity anyways."
          )
        elif (
            element_name == "GpUnit"
            and element.find("ComposingGpUnitIds") is not None
        ):
          raise loggers.ElectionInfo.from_message(
              f"GpUnit with object id {obj_id} is not referenced by anything"
              " else in the feed. This is ok for top-level GpUnits that"
              " contain others; please ensure this GpUnit is still required in"
              " the feed."
          )
        else:
          raise loggers.ElectionError.from_message(
              f"Element of type {element_name} with object id {obj_id} is not"
              " referenced by anything else in the feed."
          )


class UnreferencedEntitiesElectionDates(UnreferencedEntitiesBase):
  """CDF elections and contests are top-level in election dates feeds.

  All other entity types must be referenced.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(UnreferencedEntitiesElectionDates, self).__init__(
        election_tree,
        schema_tree,
        frozenset(["Election", "Contest"]),
        frozenset([]),
        **kwargs,
    )


class UnreferencedEntitiesOfficeholders(UnreferencedEntitiesBase):
  """CDF offices and party leadership entities are top-level in officeholders feeds.

  This rule is a warning for CDF parties since we ask for all parties for some
  LatAm feeds.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    office_holder_tenure_collection = self.get_elements_by_class(
        election_tree, "OfficeHolderTenure"
    )
    is_post_office_split = False
    if office_holder_tenure_collection:
      is_post_office_split = True
    super(UnreferencedEntitiesOfficeholders, self).__init__(
        election_tree,
        schema_tree,
        (
            frozenset(["OfficeHolderTenure", "Leadership"])
            if is_post_office_split
            else frozenset(["Office", "Leadership"])
        ),
        frozenset(["Party"]),
        **kwargs,
    )


class DeprecatedPartyLeadershipSchema(base.BaseRule):
  """Errors if the deprecated party leadership schema is used."""

  def elements(self):
    return ["Party"]

  def check(self, element):
    if len(get_external_id_values(element, "party-leader-id")) or len(
        get_external_id_values(element, "party-chair-id")
    ):
      raise loggers.ElectionError.from_message(
          "Specifying party leadership via external identifiers is deprecated."
          " Please use the PartyLeadership element instead."
      )


class GovernmentBodyExternalId(base.BaseRule):
  """Warns if the government body is set using an external identifier instead of the GovernmentBody element.

  This rule will be upgraded to an error once all feeds are migrated to the new
  schema.
  """

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    if get_external_id_values(
        element, "government-body"
    ) or get_external_id_values(element, "governmental-body"):
      raise loggers.ElectionWarning.from_message(
          "Specifying government body via external identifiers is deprecated."
          " Please use the top level GovernmentBody element instead."
      )


class UnsupportedOfficeSchema(base.BaseRule):
  """Fails if new unsupported office schema is used in the feed.

  This rule will eventually be removed once the new schema is supported.
  """

  def elements(self):
    return ["Office"]

  def check(self, element):
    if element.find("JurisdictionId") is not None:
      raise loggers.ElectionError.from_message(
          "Specifying JurisdictionId on Office is not yet supported."
      )
    if element.find("Level") is not None:
      raise loggers.ElectionError.from_message(
          "Specifying Level on Office is not yet supported."
      )
    if element.find("Role") is not None:
      raise loggers.ElectionError.from_message(
          "Specifying Role on Office is not yet supported."
      )
    if len(element.findall("SelectionMethod")) > 1:
      raise loggers.ElectionError.from_message(
          "Specifying multiple SelectionMethod elements on Office is not yet "
          "supported."
      )


class UnsupportedOfficeHolderTenureSchema(base.BaseRule):
  """Fails if new unsupported officeholder tenure schema is used in the feed.

  This rule will eventually be removed once the new schema is supported.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("OfficeHolderTenureCollection") is not None:
      raise loggers.ElectionError.from_message(
          "Specifying OfficeHolderTenureCollection on ElectionReport is not "
          "yet supported."
      )


class ElectoralCommissionCollectionExists(base.BaseRule):
  """ElectoralCommissionCollection should exist."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("ElectoralCommissionCollection") is None:
      raise loggers.ElectionError.from_message(
          "ElectoralCommissionCollection should exist."
      )


class VoterInformationCollectionExists(base.BaseRule):
  """Warn if there is no VoterInformationCollection."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("VoterInformationCollection") is None:
      raise loggers.ElectionWarning.from_message(
          "VoterInformationCollection should exist."
      )


class NoExtraElectionElements(base.BaseRule):
  """Elections for voter information feeds should not have certain elements.

  BallotStyleCollection, CandidateCollection, ContestCollection, CountStatus
  should all be excluded.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    if element.find("BallotStyleCollection") is not None:
      raise loggers.ElectionError.from_message(
          "BallotStyleCollection should not exist."
      )

    if element.find("CandidateCollection") is not None:
      raise loggers.ElectionError.from_message(
          "CandidateCollection should not exist."
      )
    if element.find("ContestCollection") is not None:
      raise loggers.ElectionError.from_message(
          "ContestCollection should not exist."
      )

    if element.find("CountStatus") is not None:
      raise loggers.ElectionError.from_message("CountStatus should not exist.")


class WarnOnElementsNotRecommendedForElection(base.BaseRule):
  """Warn on ContactInformation on an Election for voter information feeds."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    if element.find("ContactInformation") is not None:
      raise loggers.ElectionWarning.from_message(
          "ContactInformation is not recommended for Election, prefer using an"
          " ElectionAdministration."
      )


class NoExtraElectionReportCollections(base.BaseRule):
  """ElectionReports for voter information feeds should not have certain elements.

  CommitteeCollection, GovernmentBodyCollection, OfficeCollection,
  OfficeHolderTenureCollection, PartyCollection, PersonCollection should all be
  excluded.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("CommitteeCollection") is not None:
      raise loggers.ElectionError.from_message(
          "CommitteeCollection should not exist."
      )

    if element.find("GovernmentBodyCollection") is not None:
      raise loggers.ElectionError.from_message(
          "GovernmentBodyCollection should not exist."
      )

    if element.find("OfficeCollection") is not None:
      raise loggers.ElectionError.from_message(
          "OfficeCollection should not exist."
      )

    if element.find("OfficeHolderTenureCollection") is not None:
      raise loggers.ElectionError.from_message(
          "OfficeHolderTenureCollection should not exist."
      )

    if element.find("PartyCollection") is not None:
      raise loggers.ElectionError.from_message(
          "PartyCollection should not exist."
      )

    if element.find("PersonCollection") is not None:
      raise loggers.ElectionError.from_message(
          "PersonCollection should not exist."
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
COMMON_RULES = (
    # go/keep-sorted start
    AllCaps,
    AllInternationalizedTextHaveEnVersion,
    AllLanguages,
    BadCharactersInPersonFullName,
    DeprecatedPartyLeadershipSchema,
    DuplicateGpUnits,
    DuplicateID,
    DuplicatedGpUnitOcdId,
    EmptyText,
    Encoding,
    ExecutiveOfficeShouldNotHaveGovernmentBody,
    GovernmentBodyExternalId,
    GpUnitOcdId,
    GpUnitsCyclesRefsValidation,
    GpUnitsHaveInternationalizedName,
    HungarianStyleNotation,
    IndependentPartyName,
    LanguageCode,
    MissingFieldsError,
    MissingFieldsInfo,
    MissingFieldsWarning,
    MissingOfficeSelectionMethod,
    MissingStableIds,
    NonExecutiveOfficeShouldHaveGovernmentBody,
    OfficesHaveJurisdictionID,
    OfficesHaveValidOfficeLevel,
    OfficesHaveValidOfficeRole,
    OptionalAndEmpty,
    OtherType,
    PartyLeadershipMustExist,
    PartySpanMultipleCountries,
    PersonHasUniqueFullName,
    PersonsHaveValidGender,
    PersonsMissingPartyData,
    Schema,
    URIValidator,
    UniqueLabel,
    UniqueStableID,
    UniqueURIPerAnnotationCategory,
    UnsupportedOfficeHolderTenureSchema,
    UnsupportedOfficeSchema,
    ValidEnumerations,
    ValidIDREF,
    ValidJurisdictionID,
    ValidPartyLeadershipDates,
    ValidStableID,
    ValidTiktokURL,
    ValidURIAnnotation,
    ValidYoutubeURL,
    ValidateOcdidLowerCase,
    # go/keep-sorted end
)

ELECTION_RULES = COMMON_RULES + (
    # go/keep-sorted start
    BallotTitle,
    CandidateContestTypesAreCompatible,
    CandidatesReferencedInRelatedContests,
    CoalitionParties,
    ComposingContestIdsAreValidRelatedContests,
    ContestContainsValidEndDate,
    ContestContainsValidStartDate,
    ContestEndDateOccursAfterStartDate,
    ContestEndDateOccursBeforeSubsequentContestStartDate,
    ContestHasMultipleOffices,
    ContestHasValidContestStage,
    ContestStartDateContainsCorrespondingEndDate,
    CorrectCandidateSelectionCount,
    DateStatusMatches,
    DuplicateContestNames,
    DuplicatedPartyAbbreviation,
    DuplicatedPartyName,
    ElectionContainsStartAndEndDates,
    ElectionDatesSpanContestDates,
    ElectionEndDatesInThePast,
    ElectionEndDatesOccurAfterStartDates,
    ElectionStartDates,
    ElectionTypesAndCandidateContestTypesAreCompatible,
    ElectionTypesAreCompatible,
    ElectoralDistrictOcdId,
    FullTextMaxLength,
    FullTextOrBallotText,
    GpUnitsHaveSingleRoot,
    ImproperCandidateContest,
    MissingPartyAbbreviationTranslation,
    MissingPartyNameTranslation,
    MultipleCandidatesPointToTheSamePersonInTheSameContest,
    MultipleInternationalizedTextWithSameLanguageCode,
    OfficeHasjurisdictionSameAsElectoralDistrict,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    ProperBallotSelection,
    SelfDeclaredCandidateMethod,
    SingularPartySelection,
    SubsequentContestIdIsValidRelatedContest,
    ValidateInfoUriAnnotation,
    # go/keep-sorted end
)

ELECTION_RESULTS_RULES = ELECTION_RULES + (
    # go/keep-sorted start
    PartiesHaveValidColors,
    PercentSum,
    ValidateDuplicateColors,
    VoteCountTypesCoherency,
    # go/keep-sorted end
)


OFFICEHOLDER_RULES = COMMON_RULES + (
    # go/keep-sorted start
    DateOfBirthIsInPast,
    OfficeHolderTenureTermDates,
    OfficeSelectionMethodMatch,
    OfficeTermDates,
    PersonHasOffice,
    ProhibitElectionData,
    RemovePersonAndOfficeHolderId60DaysAfterEndDate,
    UniqueStartDatesForOfficeRoleAndJurisdiction,
    UnreferencedEntitiesOfficeholders,
    # go/keep-sorted end
)

COMMITTEE_RULES = COMMON_RULES + (
    # go/keep-sorted start
    AffiliationEndDateOccursAfterStartDate,
    AffiliationHasEitherPartyOrPerson,
    CommitteeClassificationEndDateOccursAfterStartDate,
    EinMatchesFormat,
    ProhibitElectionData,
    # go/keep-sorted end
)

ELECTION_DATES_RULES = (
    COMMON_RULES + ELECTION_RULES + (UnreferencedEntitiesElectionDates,)
)

METADATA_RULES = (
    # go/keep-sorted start
    ElectionEventDatesAreSequential,
    Encoding,
    FeedHasValidCountryCode,
    FeedIdsAreUnique,
    FeedInactiveDateIsLatestDate,
    FeedInactiveDateSetForNonEvergreenFeed,
    FeedTypeHasValidFeedLongevity,
    OfficeHolderSubFeedDatesAreSequential,
    OptionalAndEmpty,
    Schema,
    SourceDirPathMustBeSetAfterInitialDeliveryDate,
    SourceDirPathsAreUnique,
    UniqueLabel,
    # go/keep-sorted end
)

VOTER_INFORMATION_RULES = COMMON_RULES + (
    # go/keep-sorted start
    ElectoralCommissionCollectionExists,
    NoExtraElectionElements,
    NoExtraElectionReportCollections,
    VoterInformationCollectionExists,
    WarnOnElementsNotRecommendedForElection,
    # go/keep-sorted end
)

ALL_RULES = frozenset(
    COMMON_RULES
    + ELECTION_RULES
    + ELECTION_RESULTS_RULES
    + OFFICEHOLDER_RULES
    + COMMITTEE_RULES
    + ELECTION_DATES_RULES
    + VOTER_INFORMATION_RULES
    + METADATA_RULES
)

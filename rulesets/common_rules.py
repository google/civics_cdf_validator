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
"""Validation rules shared by all rulesets of the CDF XML validator."""

from __future__ import print_function

import collections
import re

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import office_utils
from civics_cdf_validator.rulesets import rule_util
import language_tags
from lxml import etree
from six.moves.urllib.parse import urlparse


_INDEPENDENT_PARTY_NAMES = frozenset(["independent", "nonpartisan"])

_GPUNIT_TYPES_WITHOUT_OCD_IDS = frozenset([
    "ballot-batch",
    "ballot-style-area",
    "combined-precinct",
    "drop-box",
    "polling-place",
    "split-precinct",
    "vote-center",
])

_EXECUTIVE_OFFICE_ROLES = frozenset([
    "head of state",
    "head of government",
    "president",
    "vice president",
    "state executive",
    "deputy state executive",
    "deputy head of government",
    "mayor",
])

_VALID_OFFICE_ROLE_COMBINATIONS = frozenset([
    frozenset(["head of government", "head of state"]),
    frozenset(["cabinet member", "general purpose officer"]),
])

_URI_USAGE_TYPES = frozenset([
    "campaign",
    "official",
    "personal",
])

_TYPED_URI_PLATFORMS = frozenset([
    "facebook",
    "instagram",
    "line",
    "linkedin",
    "tiktok",
    "twitter",
    "website",
    "whatsapp",
    "youtube",
])

_UNTYPED_URI_PLATFORMS = frozenset([
    "ballotpedia",
    "fec",
    "followthemoney",
    "opensecrets",
    "wikipedia",
])

_ALL_URI_PLATFORMS = _TYPED_URI_PLATFORMS | _UNTYPED_URI_PLATFORMS


def _get_office_roles(element, is_post_office_split_feed=False):
  if is_post_office_split_feed:
    return [element.text for element in element.findall("Role")]
  return rule_util.get_entity_info_for_value_type(element, "office-role")


def _is_executive_office(element, is_post_office_split_feed=False):
  office_roles = _get_office_roles(element, is_post_office_split_feed)
  return not _EXECUTIVE_OFFICE_ROLES.isdisjoint(office_roles)


def _has_government_body(element):
  return rule_util.element_has_text(element.find("GovernmentBodyIds"))


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
    except etree.DocumentInvalid:
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


class LanguageCode(base.BaseRule):
  """Check that Text and Uri elements have a valid language code."""

  def elements(self):
    return ["Text", "Uri"]

  def check(self, element):
    if "language" not in element.attrib:
      return
    elem_lang = element.get("language")
    if not elem_lang.strip() or not language_tags.tags.check(elem_lang):
      raise loggers.ElectionError.from_message(
          "%s is not a valid language code" % elem_lang, [element]
      )


class EmptyText(base.BaseRule):
  """Check that Text elements are not empty or strictly whitespace."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if element.text is None or not element.text.strip():
      raise loggers.ElectionError.from_message("Text is empty", element)


class EmptyString(base.BaseRule):
  """Check that string fields are not empty or strictly whitespace."""

  def elements(self):
    return list(self.get_element_names_for_type("xs:string"))

  # pylint: disable=g-explicit-length-test
  def check(self, element):
    if (element.text is None or not element.text.strip()) and not len(element):
      raise loggers.ElectionError.from_message(
          "String field is empty", [element]
      )


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
      "DiplomatReceivingStateId": "GpUnit",
      "DiplomatSendingStateId": "GpUnit",
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

    for elem_type in self.object_id_mapping:
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
    stable_ids = rule_util.get_external_id_values(element, "stable")
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


class GpUnitOcdId(base.BaseRule):
  """All GpUnits MUST have a valid OCD ID."""

  def elements(self):
    return ["GpUnit", "ReportingUnit"]

  def check(self, element):
    # ReportingDevices are not expected to have OCD IDs.
    if self.get_element_class(element) == "ReportingDevice":
      return
    type_element = element.find("Type")
    if (
        rule_util.element_has_text(type_element)
        and type_element.text in _GPUNIT_TYPES_WITHOUT_OCD_IDS
    ):
      return
    ocd_ids = rule_util.get_external_id_values(element, "ocd-id")
    if not ocd_ids:
      raise loggers.ElectionError.from_message(
          f"The GpUnit {element.get('objectId')} does not have an ocd-id.",
          [element],
          [element.sourceline],
      )
    for ocd_id in ocd_ids:
      if not self.ocd_id_validator.is_valid_ocd_id(ocd_id):
        raise loggers.ElectionError.from_message(
            f"The GpUnit {element.get('objectId')} does not have a valid "
            f"ocd-id: '{ocd_id}'.",
            [element],
            [element.sourceline],
        )


class DuplicatedGpUnitOcdId(base.BaseRule):
  """2 GpUnits should not have same OCD ID."""

  def elements(self):
    return ["GpUnitCollection"]

  def check(self, element):
    error_log = []
    gp_ocdid = dict()
    gpunits = element.findall("GpUnit")
    for gpunit in gpunits:
      ocd_ids = rule_util.get_external_id_values(gpunit, "ocd-id")
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


class UniqueLabel(base.BaseRule):
  """Labels should be unique within a file."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(UniqueLabel, self).__init__(election_tree, schema_tree, **kwargs)
    self.labels = set()

  def elements(self):
    return list(self.get_element_names_for_type("InternationalizedText"))

  def check(self, element):
    element_label = element.get("label")
    if element_label:
      if element_label in self.labels:
        msg = "Duplicate label '%s'. Label already defined" % element_label
        raise loggers.ElectionError.from_message(msg, [element])
      else:
        self.labels.add(element_label)


class PersonHasUniqueFullName(base.BaseRule):
  """A Person should be defined one time in <PersonCollection>.

  The main purpose of this check is to spot redundant person definition.
  If two people have the same full name and date of birthday, a warning will
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


class UniqueStableID(base.TreeRule):
  """Check that every stableID is unique.

  Add an error message if stable id is not unique
  """

  def check(self):
    error_log = []
    stable_obj_dict = dict()
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      stable_ids = rule_util.get_external_id_values(
          element, "stable", search_subelements=False
      )
      if not stable_ids:
        continue
      elem_id = self._get_object_id_or_name(element)
      for stable_id in stable_ids:
        if stable_id in stable_obj_dict.keys():
          stable_obj_dict.get(stable_id).append(elem_id)
        else:
          elem_id_list = []
          elem_id_list.append(elem_id)
          stable_obj_dict[stable_id] = elem_id_list
    for k, v in stable_obj_dict.items():
      if len(v) > 1:
        error_message = (
            "Stable ID {} is not unique as it is mapped in {}".format(k, v)
        )
        error_log.append(loggers.LogEntry(error_message))
    if error_log:
      raise loggers.ElectionError(error_log)

  def _get_object_id_or_name(self, element):
    if "objectId" in element.attrib:
      return element.get("objectId")
    names_by_language = rule_util.get_language_to_text_map(element.find("Name"))
    if "en" in names_by_language:
      return names_by_language["en"][0]
    for names in names_by_language.values():
      return names[0]


class MissingStableIds(base.BaseRule):
  """Check that each NIST object in the feed have a stable Id.

  Add an error message if stable id is missing from the object.
  """

  _ELEMENTS_WITH_STABLE_IDS = [
      "BallotMeasureContest",
      "BallotMeasureSelection",
      "Candidate",
      "CandidateContest",
      "Coalition",
      "Committee",
      "Election",
      "Leadership",
      "Office",
      "OfficeHolderTenure",
      "Party",
      "PartyContest",
      "Person",
      "ReportingUnit",
  ]

  def elements(self):
    return self._ELEMENTS_WITH_STABLE_IDS

  def check(self, element):
    stable_ids = []
    external_identifiers = element.find("ExternalIdentifiers")
    if external_identifiers is not None:
      stable_ids = rule_util.get_external_id_values(
          external_identifiers, "stable"
      )
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


class CandidateImageInContactInformation(base.BaseRule):
  """Warn if candidate-image is set in ContactInformation.Uri."""

  def elements(self):
    return ["ContactInformation"]

  def check(self, element):
    candidate_image_uris = []
    for uri in element.findall("Uri"):
      annotation = uri.get("Annotation", "").strip()
      if annotation == "candidate-image":
        candidate_image_uris.append(uri)

    if candidate_image_uris:
      raise loggers.ElectionWarning.from_message(
          "Annotation 'candidate-image' in ContactInformation.Uri is"
          " deprecated. Please use Person.ImageUri instead.",
          candidate_image_uris,
      )


class OnlyOneCandidateImagePerPerson(base.BaseRule):
  """Ensure only one candidate-image is provided per Person."""

  def elements(self):
    return ["Person"]

  def check(self, element):
    image_uris = element.findall("ImageUri")
    candidate_images = []
    for image_uri in image_uris:
      annotation = image_uri.get("Annotation", "").strip()
      if annotation == "candidate-image":
        candidate_images.append(image_uri)

    if len(candidate_images) > 1:
      raise loggers.ElectionError.from_message(
          "Person has {} ImageUri fields annotated as 'candidate-image'."
          " Must have at most one.".format(len(candidate_images)),
          candidate_images,
      )


class UniqueCandidateImageUris(base.TreeRule):
  """Check that candidate-image URIs are unique to a person."""

  def check(self):
    root = self.election_tree.getroot()
    if root is None:
      return

    persons_by_candidate_image_uri = collections.defaultdict(list)
    person_collection = root.find("PersonCollection")
    if person_collection is None:
      return
    for person in person_collection.findall("Person"):
      for image_uri_element in person.findall("ImageUri"):
        if not rule_util.element_has_text(image_uri_element):
          continue
        annotation = image_uri_element.get("Annotation", "").strip()
        if annotation == "candidate-image":
          image_uri = image_uri_element.text.strip()
          if image_uri:
            persons_by_candidate_image_uri[image_uri].append(person)

    error_log = []
    for image_uri, persons in persons_by_candidate_image_uri.items():
      if len(persons) > 1:
        person_ids = sorted(person.get("objectId") for person in persons)
        error_log.append(
            loggers.LogEntry(
                f"Candidate image URI '{image_uri}' is shared by multiple"
                f" people: [{', '.join(person_ids)}].",
                persons,
            )
        )
    if error_log:
      raise loggers.ElectionError(error_log)


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


class ValidateOcdidLowerCase(base.BaseRule):
  """Validate that the ocd-ids are all lower case.

  Throw a warning if the ocd-ids are not all in lowercase.
  """

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    for ocd_id in rule_util.get_external_id_values(element, "ocd-id"):
      if not ocd_id.islower():
        msg = (
            "OCD-ID %s is not in all lower case letters. "
            "Valid OCD-IDs should be all lowercase." % (ocd_id)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


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
      if (
          other_type is not None
          and other_type.text in rule_util.PARTY_LEADERSHIP_TYPES
      ):
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

    for platform in _ALL_URI_PLATFORMS:
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

      # Skip platform checks for office contact form and candidate-image
      # annotations.
      if annotation in ("office-contact_form", "candidate-image"):
        continue

      ann_elements = annotation.split("-")
      if len(ann_elements) == 1:
        platform = ann_elements[0]
        # One element would imply the annotation could be a platform
        # without a usage type, which is checked here.
        if platform in _TYPED_URI_PLATFORMS:
          raise loggers.ElectionWarning.from_message(
              "Annotation '{}' missing usage type.".format(annotation), [uri]
          )
        elif platform in _URI_USAGE_TYPES:
          raise loggers.ElectionError.from_message(
              "Annotation '{}' has usage type, missing platform.".format(
                  annotation
              ),
              [uri],
          )
        elif platform not in _UNTYPED_URI_PLATFORMS:
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
            usage_type not in _URI_USAGE_TYPES
            or platform not in _TYPED_URI_PLATFORMS
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
    if rule_util.element_has_text(post_office_split_jurisdiction_element):
      jurisdiction_values.append(post_office_split_jurisdiction_element.text)
    else:
      jurisdiction_values = rule_util.get_entity_info_for_value_type(
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
    jurisdiction_values = rule_util.get_entity_info_for_value_type(
        root, "jurisdiction-id"
    )
    return set(jurisdiction_values)

  def _gather_defined_values(self):
    gp_unit_elements = self.election_tree.getroot().findall(".//GpUnit")
    return {elem.get("objectId") for elem in gp_unit_elements}


class OfficesHaveValidOfficeLevel(base.BaseRule):
  """Each office must have a valid office-level."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_levels = []
    post_office_split_office_level_element = element.find("Level")
    if rule_util.element_has_text(post_office_split_office_level_element):
      office_levels.append(post_office_split_office_level_element.text)
    else:
      office_levels = [
          ol_id.strip()
          for ol_id in rule_util.get_external_id_values(element, "office-level")
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
          for office_role in rule_util.get_external_id_values(
              element, "office-role"
          )
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


class DiplomaticOfficesHaveCorrespondingGpUnitsSet(base.BaseRule):
  """Offices with the 'diplomat' role must have a sending or receiving state."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    office_roles = (
        role.text.strip()
        for role in element.findall("Role")
        if rule_util.element_has_text(role)
    )
    if "diplomat" not in office_roles:
      return

    if not rule_util.element_has_text(
        element.find("DiplomatSendingStateId")
    ) and not rule_util.element_has_text(
        element.find("DiplomatReceivingStateId")
    ):
      raise loggers.ElectionError.from_message(
          "Office with role 'diplomat' must have at least one of"
          " DiplomatSendingStateId or DiplomatReceivingStateId set.",
          [element],
      )


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


class GpUnitsHaveInternationalizedName(base.BaseRule):
  """GpUnits must have at least one non-empty InternationlizedName element."""

  def elements(self):
    return ["GpUnit"]

  def check(self, element):
    intl_names = element.findall("InternationalizedName")
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
    return {}


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
      ocd_ids = rule_util.get_external_id_values(gpunit, "ocd-id")
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
  """Ensure non-Head of Government/State Office elements have a government body defined."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    role_element = self.get_elements_by_class(election_tree, "Role")
    if officeholder_tenure_collection_element or role_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    if not _is_executive_office(
        element, self.is_post_office_split_feed
    ) and not _has_government_body(element):
      raise loggers.ElectionInfo.from_message(
          "Non-Head of Government/State Office element is missing a government"
          " body.",
          [element],
      )


class ExecutiveOfficeShouldNotHaveGovernmentBody(base.BaseRule):
  """Ensure Head of Government/State Office elements do not have a government body defined."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    role_element = self.get_elements_by_class(election_tree, "Role")
    if officeholder_tenure_collection_element or role_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    if _is_executive_office(
        element, self.is_post_office_split_feed
    ) and _has_government_body(element):
      office_roles = _get_office_roles(element, self.is_post_office_split_feed)
      raise loggers.ElectionError.from_message(
          "Head of Government/State Office element (roles:"
          f" {','.join(office_roles)}) has a government body. Head of"
          " Government/State offices should not have government bodies.",
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


class AllInternationalizedTextHaveEnVersion(base.BaseRule):
  """Checks for InternationalizedText elements missing an English version."""

  def elements(self):
    return list(self.get_element_names_for_type("InternationalizedText"))

  def check(self, element):
    language_map = rule_util.get_language_to_text_map(element)
    if "en" not in language_map:
      raise loggers.ElectionInfo.from_message(
          message='No "english" version found for the InternationalizedText.',
          elements=[element],
      )


class DeprecatedPartyLeadershipSchema(base.BaseRule):
  """Errors if the deprecated party leadership schema is used."""

  def elements(self):
    return ["Party"]

  def check(self, element):
    if len(rule_util.get_external_id_values(element, "party-leader-id")) or len(
        rule_util.get_external_id_values(element, "party-chair-id")
    ):
      raise loggers.ElectionError.from_message(
          "Specifying party leadership via external identifiers is deprecated."
          " Please use the PartyLeadership element instead."
      )


_IDREF_TYPES = frozenset(["xs:IDREF", "xs:IDREFS"])

# The set of external identifiers that contain references to other entities.
_IDREF_EXTERNAL_IDENTIFIERS = frozenset(
    ["jurisdiction-id"] + rule_util.PARTY_LEADERSHIP_TYPES
)


class ProhibitElectionData(base.TreeRule):
  """Ensure that election data is not provided for officeholder feeds."""

  def check(self):
    root = self.election_tree.getroot()
    if root is not None and root.find("Election") is not None:
      raise loggers.ElectionError.from_message(
          "Election data is prohibited in officeholder feeds."
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

  def _gather_referenced_entities(self):
    """Create a set of all entities referenced by either IDREF(S) elements or external identifiers."""
    referenced_entities = set()
    for external_id_type in _IDREF_EXTERNAL_IDENTIFIERS:
      referenced_entities.update(
          rule_util.get_external_id_values(self.election_tree, external_id_type)
      )
    idref_elements = self.get_element_names_for_types(_IDREF_TYPES)
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


COMMON_RULES = (
    # go/keep-sorted start
    AllCaps,
    AllInternationalizedTextHaveEnVersion,
    AllLanguages,
    BadCharactersInPersonFullName,
    CandidateImageInContactInformation,
    DeprecatedPartyLeadershipSchema,
    DiplomaticOfficesHaveCorrespondingGpUnitsSet,
    DuplicateGpUnits,
    DuplicateID,
    DuplicatedGpUnitOcdId,
    EmptyString,
    EmptyText,
    Encoding,
    ExecutiveOfficeShouldNotHaveGovernmentBody,
    GpUnitOcdId,
    GpUnitsCyclesRefsValidation,
    GpUnitsHaveInternationalizedName,
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
    OnlyOneCandidateImagePerPerson,
    OptionalAndEmpty,
    OtherType,
    PartyLeadershipMustExist,
    PartySpanMultipleCountries,
    PersonHasUniqueFullName,
    PersonsHaveValidGender,
    PersonsMissingPartyData,
    Schema,
    URIValidator,
    UniqueCandidateImageUris,
    UniqueLabel,
    UniqueStableID,
    UniqueURIPerAnnotationCategory,
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

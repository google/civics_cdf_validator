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
import csv
import datetime
import hashlib
import io
import os
import re
import shutil
import sys

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import office_utils
import enum
import github
import language_tags
from lxml import etree
import requests
from six.moves.urllib.parse import urlparse

_PARTY_LEADERSHIP_TYPES = ["party-leader-id", "party-chair-id"]
_IDENTIFIER_TYPES = frozenset(
    ["local-level", "national-level", "ocd-id", "state-level"])


def sourceline_prefix(element):
  if hasattr(element, "sourceline") and element.sourceline is not None:
    return "Line %d. " % element.sourceline
  else:
    return ""


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


def get_parent_hierarchy_object_id_str(elt):
  """Get the elt path from the 1st parent with an objectId / ElectionReport."""

  elt_hierarchy = []
  current_elt = elt
  while current_elt is not None:
    if current_elt.get("objectId"):
      elt_hierarchy.append(current_elt.tag + ":" + current_elt.get("objectId"))
      break
    else:
      elt_hierarchy.append(current_elt.tag)
    current_elt = current_elt.getparent()
  return " > ".join(elt_hierarchy[::-1])


def element_has_text(element):
  return (element is not None and element.text is not None
          and not element.text.isspace())


class Schema(base.TreeRule):
  """Checks if election file validates against the provided schema."""

  def check(self):
    try:
      schema = etree.XMLSchema(etree=self.schema_tree)
    except etree.XMLSchemaParseError as e:
      raise loggers.ElectionError(
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
            loggers.ErrorLogEntry(error.line, error.message.encode("utf-8")))
      raise loggers.ElectionTreeError(
          "The election file didn't validate against schema.", errors)


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
    if ((element.text is None or not element.text.strip()) and
        not len(element)):
      raise loggers.ElectionWarning(
          "Line %d. %s optional element included although it "
          "is empty." % (element.sourceline, element.tag))


class Encoding(base.TreeRule):
  """Checks that the file provided uses UTF-8 encoding."""

  def check(self):
    docinfo = self.election_tree.docinfo
    if docinfo.encoding != "UTF-8":
      raise loggers.ElectionError("Encoding on file is not UTF-8")


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
        raise loggers.ElectionInfo(
            "Line %d. %s ID %s is not in Hungarian Style Notation. "
            "Should start with %s" %
            (element.sourceline, tag, object_id, self.elements_prefix[tag]))


class LanguageCode(base.BaseRule):
  """Check that Text elements have a valid language code."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if "language" not in element.attrib:
      return
    elem_lang = element.get("language")
    if (not elem_lang.strip() or not language_tags.tags.check(elem_lang)):
      raise loggers.ElectionError("Line %d. %s is not a valid language code" %
                                  (element.sourceline, elem_lang))


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
      raise loggers.ElectionError(
          sourceline_prefix(element) +
          "Contest percents do not sum to 0 or 100: %f" % sum_percents)


class OnlyOneElection(base.BaseRule):
  """Check that there is only one Election in the ElectionReport."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if len(element.findall("Election")) > 1:
      raise loggers.ElectionError(
          sourceline_prefix(element) +
          "ElectionReport has more than one Election.")


class EmptyText(base.BaseRule):
  """Check that Text elements are not strictly whitespace."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if element.text is not None and not element.text.strip():
      raise loggers.ElectionWarning("Line %d. %s is empty" %
                                    (element.sourceline, element.tag))


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
          error_line = element.sourceline
          error_message = "{0} is a duplicate object ID".format(obj_id)
          error_log.append(loggers.ErrorLogEntry(error_line, error_message))
        else:
          all_object_ids.add(obj_id)
    if error_log:
      raise loggers.ElectionTreeError(
          "The Election File contains duplicate object IDs", error_log)


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
    reference_object_ids = self.object_id_mapping.get(
        element_reference_type, [])
    if element.text:
      id_references = element.text.split()
      for id_ref in id_references:
        if id_ref not in reference_object_ids:
          err_message = ("Line {}. {}. {} is not a valid IDREF. {} should"
                         " contain an objectId from a {} element.").format(
                             element.sourceline,
                             get_parent_hierarchy_object_id_str(element),
                             id_ref, element_name, element_reference_type)
          error_log.append(loggers.ErrorLogEntry(None, err_message))
    if error_log:
      raise loggers.ElectionError(("There are {} invalid IDREF elements "
                                   "present.").format(
                                       len(error_log)), error_log)


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
        error_log.append(
            loggers.ErrorLogEntry(
                None,
                "Stable id {} is not in the correct format.".format(s_id)))
    if error_log:
      raise loggers.ElectionError(
          "The file contains the following Stable ID "
          "error(s) \n{}".format("\n".join([e.message for e in error_log])),
          error_log=error_log)


class ElectoralDistrictOcdId(base.BaseRule):
  """GpUnit referred to by Contest.ElectoralDistrictId MUST have a valid OCD-ID."""

  CACHE_DIR = "~/.cache"
  GITHUB_REPO = "opencivicdata/ocd-division-ids"
  GITHUB_DIR = "identifiers"
  # Reference http://docs.opencivicdata.org/en/latest/proposals/0002.html
  OCD_PATTERN = r"^ocd-division\/country:[a-z]{2}(\/(\w|-)+:(\w|-|\.|~)+)*$"

  def __init__(self, election_tree, schema_tree):
    super(ElectoralDistrictOcdId, self).__init__(election_tree, schema_tree)
    self.gpunits = []
    self.check_github = True
    self.country_code = None
    self.github_file = None
    self.github_repo = None
    self.local_file = None
    self.ocd_matcher = re.compile(self.OCD_PATTERN, flags=re.U)
    for gpunit in self.get_elements_by_class(self.election_tree, "GpUnit"):
      self.gpunits.append(gpunit)

  def setup(self):
    if self.local_file is None:
      self.github_file = "country-%s.csv" % self.country_code
    self.ocds = self._get_ocd_data()

  def _read_csv(self, reader, ocd_id_codes):
    """Reads in OCD IDs from CSV file."""
    for row in reader:
      if "id" in row and row["id"]:
        ocd_id_codes.add(row["id"])

  def _get_ocd_data(self):
    """Returns a list of OCD-ID codes.

    This list is populated using either a local file or a downloaded file
    from GitHub.
    """
    # Value `local_file` is not provided by default, only by cmd line arg.
    if self.local_file:
      countries_file = self.local_file
    else:
      cache_directory = os.path.expanduser(self.CACHE_DIR)
      countries_filename = "{0}/{1}".format(cache_directory, self.github_file)

      if not os.path.exists(countries_filename):
        # Only initialize `github_repo` if there's no cached file.
        github_api = github.Github()
        self.github_repo = github_api.get_repo(self.GITHUB_REPO)
        if not os.path.exists(cache_directory):
          os.makedirs(cache_directory)
        self._download_data(countries_filename)
      else:
        if self.check_github:
          last_mod_date = datetime.datetime.fromtimestamp(
              os.path.getmtime(countries_filename))

          seconds_since_mod = (datetime.datetime.now() -
                               last_mod_date).total_seconds()

          # If 1 hour has elapsed, check GitHub for the last file update.
          if (seconds_since_mod / 3600) > 1:
            github_api = github.Github()
            self.github_repo = github_api.get_repo(self.GITHUB_REPO)
            # Re-download the file if the file on GitHub was updated.
            if last_mod_date < self._get_latest_commit_date():
              self._download_data(countries_filename)
            # Update the timestamp to reflect last GitHub check.
            os.utime(countries_filename, None)
      countries_file = open(countries_filename, encoding="utf-8")
    ocd_id_codes = set()
    csv_reader = csv.DictReader(countries_file)
    self._read_csv(csv_reader, ocd_id_codes)

    return ocd_id_codes

  def _get_latest_commit_date(self):
    """Returns the latest commit date to country-*.csv."""
    latest_commit_date = None
    latest_commit = self.github_repo.get_commits(
        path="{0}/{1}".format(self.GITHUB_DIR, self.github_file))[0]
    latest_commit_date = latest_commit.commit.committer.date
    return latest_commit_date

  def _download_data(self, file_path):
    """Makes a request to Github to download the file."""
    ocdid_url = "https://raw.github.com/{0}/master/{1}/{2}".format(
        self.GITHUB_REPO, self.GITHUB_DIR, self.github_file)
    r = requests.get(ocdid_url)
    with io.open("{0}.tmp".format(file_path), "wb") as fd:
      for chunk in r.iter_content():
        fd.write(chunk)
    valid = self._verify_data("{0}.tmp".format(file_path))
    if not valid:
      raise loggers.ElectionError(
          "Could not successfully download OCD ID data files. "
          "Please try downloading the file manually and "
          "place it in ~/.cache")
    else:
      shutil.copy("{0}.tmp".format(file_path), file_path)

  def _verify_data(self, file_path):
    """Validates a file's SHA."""
    file_sha1 = hashlib.sha1()
    file_info = os.stat(file_path)
    # GitHub calculates the blob SHA like this:
    # sha1("blob "+filesize+"\0"+data)
    file_sha1.update(b"blob %d\0" % file_info.st_size)
    with io.open(file_path, mode="rb") as fd:
      for line in fd:
        file_sha1.update(line)
    latest_file_sha = self._get_latest_file_blob_sha()
    return latest_file_sha == file_sha1.hexdigest()

  def _get_latest_file_blob_sha(self):
    """Returns the GitHub blob SHA of country-*.csv."""
    blob_sha = None
    dir_contents = self.github_repo.get_contents(self.GITHUB_DIR)
    for content_file in dir_contents:
      if content_file.name == self.github_file:
        blob_sha = content_file.sha
        break
    return blob_sha

  def _encode_ocdid_value(self, ocdid):
    if sys.version_info.major < 3:
      if isinstance(ocdid, unicode):
        return ocdid.encode("utf-8")
    if isinstance(ocdid, str):
      return ocdid
    else:
      return ""

  def elements(self):
    return ["ElectoralDistrictId"]

  def check(self, element):
    if element.getparent().tag != "Contest":
      return
    contest_id = element.getparent().get("objectId")
    if not contest_id:
      return
    error_log = []
    referenced_gpunits = [
        g for g in self.gpunits if g.get("objectId", "") == element.text
    ]
    if not referenced_gpunits:
      error_log.append(
          loggers.ErrorLogEntry(
              None, "Line %d. The ElectoralDistrictId element"
              " for contest %s does not refer to a GpUnit. "
              "Every ElectoralDistrictId MUST reference a GpUnit" %
              (element.sourceline, contest_id)))
    else:
      referenced_gpunit = referenced_gpunits[0]
      external_ids = get_external_id_values(referenced_gpunit, "ocd-id")
      if not external_ids:
        error_log.append(
            loggers.ErrorLogEntry(
                None, "Line %d. The GpUnit %s on line %d referenced by "
                "contest %s does not have an ocd-id" %
                (element.sourceline, element.text, referenced_gpunit.sourceline,
                 contest_id)))
      else:
        for external_id in external_ids:
          ocd_id = self._encode_ocdid_value(external_id)
          valid_ocd_id = (
              ocd_id in self.ocds and self.ocd_matcher.match(ocd_id))
          if not valid_ocd_id:
            error_log.append(
                loggers.ErrorLogEntry(
                    None, "Line %d. The ElectoralDistrictId element for "
                    "contest %s refers to GpUnit %s on line %d that "
                    "does not have a valid OCD ID (%s)" %
                    (element.sourceline, contest_id, element.text,
                     referenced_gpunit.sourceline, ocd_id)))
    if error_log:
      raise loggers.ElectionError(
          ("The file contains the following ElectoralDistrictId error(s) \n{}"
           .format("\n".join([e.message for e in error_log]))),
          error_log=error_log)


class GpUnitOcdId(ElectoralDistrictOcdId):
  """Any GpUnit that is a geographic district SHOULD have a valid OCD-ID."""

  districts = [
      "borough", "city", "county", "municipality", "state", "town", "township",
      "village"
  ]
  validate_ocd_file = True

  def elements(self):
    return ["ReportingUnit"]

  def check(self, element):
    gpunit_id = element.get("objectId")
    if not gpunit_id:
      return
    gpunit_type = element.find("Type")
    if gpunit_type is not None and gpunit_type.text in self.districts:
      external_id_elements = get_external_id_values(
          element, "ocd-id", return_elements=True)
      for extern_id in external_id_elements:
        ocd_id = self._encode_ocdid_value(extern_id.text)
        if ocd_id not in self.ocds:
          raise loggers.ElectionWarning(
              "The OCD ID %s in GpUnit %s defined on line %d is "
              "not valid" % (ocd_id, gpunit_id, extern_id.sourceline))


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
            loggers.ErrorLogEntry(
                None, "GpUnit with object_id {} is "
                "duplicated at line {}".format(object_id, gpunit.sourceline)))
        continue
      object_ids.add(object_id)
      composing_gpunits = gpunit.find("ComposingGpUnitIds")
      if composing_gpunits is None or not composing_gpunits.text:
        continue
      composing_ids = frozenset(composing_gpunits.text.split())
      if children.get(composing_ids):
        error_log.append(
            loggers.ErrorLogEntry(
                None, "GpUnits {} are duplicates".format(
                    str((children[composing_ids], object_id)))))
        continue
      children[composing_ids] = object_id
    if error_log:
      raise loggers.ElectionError(
          "The following errors are due to duplicate GpUnits: \n{}".format(
              "\n".join([e.message for e in error_log])),
          error_log=error_log)


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
          loggers.ErrorLogEntry(
              None, "GpUnits have no geo district root. "
              "There should be exactly one root geo district."))
    elif len(roots) > 1:
      self.error_log.append(
          loggers.ErrorLogEntry(
              None, "GpUnits tree has more than one root: {0}".format(
                  ", ".join(roots))))

    if self.error_log:
      raise loggers.ElectionError(
          "GpUnits tree has the following errors regarding the root: \n{}"
          .format("\n".join([entry.message for entry in self.error_log])),
          error_log=self.error_log)


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
            loggers.ErrorLogEntry(None,
                                  "Cycle detected at node {0}".format(gpunit)))
        self.bad_nodes.append(gpunit)
      return
    self.visited[gpunit] = 1
    # Check each composing_gpunit and its edges if any.
    for child_unit in self.edges[gpunit]:
      if child_unit in self.edges:
        self.build_tree(child_unit)
      else:
        self.error_log.append(
            loggers.ErrorLogEntry(
                None, "Node {0} is not present in the file as a GpUnit element."
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
      raise loggers.ElectionError(
          "GpUnits tree has the following errors: \n{}".format("\n".join(
              [entry.message for entry in self.error_log])),
          error_log=self.error_log)


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
        raise loggers.ElectionError(
            "Line %d. Type on element %s is set to 'other' but "
            "OtherType element is not defined" %
            (element.sourceline, element.tag))


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
    # Only check contest elements if this is a partisan election.
    if self.election_type and self.election_type in ("primary",
                                                     "partisan-primary-open",
                                                     "partisan-primary-closed"):
      return ["CandidateContest"]
    else:
      return []

  def check(self, element):
    primary_party_ids = element.find("PrimaryPartyIds")
    if (primary_party_ids is None or not primary_party_ids.text or
        not primary_party_ids.text.strip()):
      election_elem = self.election_tree.find("Election")
      raise loggers.ElectionWarning(
          "Line %d. Election is of ElectionType %s but PrimaryPartyIds "
          "is not present or is empty" %
          (election_elem.sourceline, self.election_type))


class PartisanPrimaryHeuristic(PartisanPrimary):
  """Attempts to identify partisan primaries not marked up as such."""

  # Add other strings that imply this is a primary contest.
  party_text = ["(dem)", "(rep)", "(lib)"]

  def elements(self):
    if not self.election_type or self.election_type not in (
        "primary", "partisan-primary-open", "partisan-primary-closed"):
      return ["CandidateContest"]
    else:
      return []

  def check(self, element):
    contest_name = element.find("Name")
    if contest_name is not None and contest_name.text is not None:
      c_name = contest_name.text.replace(" ", "").lower()
      for p_text in self.party_text:
        if p_text in c_name:
          raise loggers.ElectionWarning(
              "Line %d. Name of contest - %s, "
              "contains text that implies it is a partisan primary "
              "but is not marked up as such." %
              (element.sourceline, contest_name.text))


class CoalitionParties(base.TreeRule):
  """Coalitions should always define the Party IDs."""

  def check(self):
    coalitions = self.get_elements_by_class(self.election_tree, "Coalition")
    for coalition in coalitions:
      party_id = coalition.find("PartyIds")
      if (party_id is None or not party_id.text or not party_id.text.strip()):
        raise loggers.ElectionError(
            "Line %d. Coalition %s must define PartyIDs" %
            (coalition.sourceline, coalition.get("objectId")))


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
        raise loggers.ElectionError(
            "Line %d. Duplicate label '%s'. Label already defined" %
            (element.sourceline, element_label))
      else:
        self.labels.add(element_label)


class CandidatesReferencedOnce(base.BaseRule):
  """Candidate should be referred to by only one contest for an election.

  A Candidate object should only ever be referenced from one contest. If a
  Person is running in multiple Contests, then that Person is a Candidate
  several times over, but a Candida(te|cy) can't span contests.
  """

  def __init__(self, election_tree, schema_tree):
    super(CandidatesReferencedOnce, self).__init__(election_tree, schema_tree)
    self.error_log = []

  def elements(self):
    return ["Election"]

  def _register_candidates(self, election):
    candidate_registry = {}
    candidates = self.get_elements_by_class(election, "Candidate")
    for candidate in candidates:
      cand_id = candidate.get("objectId", None)
      candidate_registry[cand_id] = []

    contests = self.get_elements_by_class(election, "Contest")
    for contest in contests:
      contest_id = contest.get("objectId")
      for child in contest.iter(tag=etree.Element):
        if "CandidateId" in child.tag:
          for cand_id in child.text.split():
            # bug in case the cand_id is an invalid one
            if cand_id not in candidate_registry:
              error_message = (
                  "Contest {} refer to a non existing candidate {}.").format(
                      contest_id, cand_id)
              self.error_log.append(loggers.ErrorLogEntry(None, error_message))
              continue
            candidate_registry[cand_id].append(contest_id)
    return candidate_registry

  def check(self, element):
    candidate_registry = self._register_candidates(element)
    for cand_id, contest_ids in candidate_registry.items():
      if len(contest_ids) > 1:
        error_message = ("A Candidate object should only ever be referenced"
                         " in one Contest. Candidate {} is"
                         " referenced by the following Contests"
                         ": {}").format(cand_id, ", ".join(contest_ids))
        self.error_log.append(loggers.ErrorLogEntry(None, error_message))
      if not contest_ids:
        error_message = ("A Candidate should be referenced in a Contest. "
                         "Candidate {0} is not referenced.").format(cand_id)
        self.error_log.append(loggers.ErrorLogEntry(None, error_message))
    if self.error_log:
      raise loggers.ElectionTreeError(
          "The Election File contains invalid Candidate references",
          self.error_log)


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
        raise loggers.ElectionError(
            "Line %d. The Contest %s does not contain the right "
            "BallotSelection. %s must have a %s but contains a "
            "%s, %s" % (element.sourceline, contest_id, tag,
                        self.con_sel_mapping[tag], selection_tag, selection_id))


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
    party_object_id = element.get("objectId")
    if len(colors) > 1:
      raise loggers.ElectionWarning(
          "Line %d: Party %s has more than one color." %
          (element.sourceline, party_object_id))
    color_val = colors[0].text
    if not color_val:
      raise loggers.ElectionWarning(
          "Line %d: Color tag in Party %s is missing a value." %
          (element.sourceline, party_object_id))
    else:
      try:
        int(color_val, 16)
      except ValueError:
        raise loggers.ElectionWarning(
            "Line %d: %s in Party %s is not a valid hex color." %
            (element.sourceline, color_val, party_object_id))


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
              "Line %d: Person %s has same full name '%s' and birthday %s as "
              "Person %s." %
              (person.sourceline, person_object_id, full_name_val, birthday_val,
               person_id_to_object_id[person_id]))
          info_log.append(loggers.ErrorLogEntry(None, info_message))
        else:
          person_id_to_object_id[person_id] = person_object_id
    return info_log

  def check(self, element):
    info_log = []
    people = element.findall("Person")
    if len(people) < 1:
      info_message = (
          "Line %d: <PersonCollection> does not have <Person> objects" %
          (element.sourceline))
      info_log.append(loggers.ErrorLogEntry(None, info_message))
    info_log.extend(self.check_specific(people))
    if info_log:
      raise loggers.ElectionTreeInfo(
          "The feed contains people with duplicated name", info_log)


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

  def get_specific_info_message(self):
    """Return an ElectionTreeInfo specific message."""
    raise NotImplementedError

  def check(self, element):
    info_log = []
    parties = element.findall("Party")
    if len(parties) < 1:
      info_message = (
          "Line %d: <PartyCollection> does not have <Party> objects" %
          (element.sourceline))
      info_log.append(loggers.ErrorLogEntry(None, info_message))
    info_log.extend(self.check_specific(parties))
    if info_log:
      raise loggers.ElectionTreeInfo(self.get_specific_info_message(), info_log)


class ValidateDuplicateColors(ValidatePartyCollection):
  """Each Party should have unique hex color.

  A Party object that has duplicate color should be picked up
  within this class and returned to the user as an Info message.
  """

  def get_specific_info_message(self):
    return "The feed contains parties with duplicate colors"

  def check_specific(self, parties):
    party_colors = {}
    info_log = []
    for party in parties:
      color_element = party.find("Color")
      if color_element is None:
        continue
      party_object_id = party.get("objectId")
      color = color_element.text
      if color is None:
        continue
      if color in party_colors:
        info_message = (
            "Line %d: Party %s has same color as Party %s." %
            (color_element.sourceline, party_object_id, party_colors[color]))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
      else:
        party_colors[color] = party_object_id
    return info_log


class DuplicatedPartyAbbreviation(ValidatePartyCollection):
  """Party abbreviation should be used once in a given language.

  If an abbreviation is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def get_specific_info_message(self):
    return "The feed contains duplicated party abbreviations"

  def check_specific(self, parties):
    info_log = []
    party_abbrs_by_language = {}
    for party in parties:
      party_object_id = party.get("objectId")
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = (
            "Line %d: <Party> %s does not have <InternationalizedAbbreviation>"
            " objects" % (party.sourceline, party_object_id))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
        continue
      party_abbrs = abbr_element.findall("Text")
      for party_abbr in party_abbrs:
        language = party_abbr.get("language")
        abbr = party_abbr.text
        if language not in party_abbrs_by_language:
          party_abbrs_by_language[language] = {}
        if abbr in party_abbrs_by_language[language]:
          info_message = (
              "Line %d: Party %s has same abbreviation in %s as Party %s." %
              (party.sourceline, party_object_id, language,
               party_abbrs_by_language[language][abbr]))
          info_log.append(loggers.ErrorLogEntry(None, info_message))
        else:
          party_abbrs_by_language[language][abbr] = party_object_id
    return info_log


class DuplicatedPartyName(ValidatePartyCollection):
  """Party name should be used once in a given language.

  If a party name is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def get_specific_info_message(self):
    return "The feed contains duplicated party names"

  def check_specific(self, parties):
    info_log = []
    party_names_by_language = {}
    for party in parties:
      party_object_id = party.get("objectId")
      name_element = party.find("Name")
      if name_element is None:
        info_message = ("Line %d: <Party> %s does not have <Name> objects" %
                        (party.sourceline, party_object_id))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
        continue
      party_names = name_element.findall("Text")
      for party_name in party_names:
        language = party_name.get("language")
        name = party_name.text
        if language not in party_names_by_language:
          party_names_by_language[language] = {}
        if name in party_names_by_language[language]:
          info_message = ("Line %d: Party %s has same name in %s as Party %s." %
                          (party_name.sourceline, party_object_id, language,
                           party_names_by_language[language][name]))
          info_log.append(loggers.ErrorLogEntry(None, info_message))
        else:
          party_names_by_language[language][name] = party_object_id
    return info_log


class MissingPartyNameTranslation(ValidatePartyCollection):
  """All Parties should have their name translated to the same languages.

  If there is a party name that is not translated to all the feed languages,
  the party should be picked up within this class and returned to the user as
  an Info message.
  """

  def get_specific_info_message(self):
    return "The feed is missing several parties name translation"

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      name_element = party.find("Name")
      if name_element is None:
        info_message = ("Line %d: <Party> %s does not have <Name> objects" %
                        (party.sourceline, party_object_id))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
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
            info_log.append(loggers.ErrorLogEntry(None, info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party %s name is not translated to all feed languages %s. You"
            " only did it for the following languages : %s." %
            (party_object_id, feed_languages, party_languages))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
    return info_log


class MissingPartyAbbreviationTranslation(ValidatePartyCollection):
  """Every party's abbreviation should be translated to the same languages.

  If a party is missing a name translation, it should be picked up within this
  class and returned to the user as an Info message.
  """

  def get_specific_info_message(self):
    return "The feed is missing several parties abbreviation translation"

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = ("Line %d: <Party> %s does not have "
                        "<InternationalizedAbbreviation> objects" %
                        (party.sourceline, party_object_id))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
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
            info_log.append(loggers.ErrorLogEntry(None, info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party %s abbreviation is not translated to all feed languages "
            "%s. You only did it for the following languages : %s." %
            (party_object_id, feed_languages, party_languages))
        info_log.append(loggers.ErrorLogEntry(None, info_message))
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
      error_log.append(
          loggers.ErrorLogEntry(election_elt.sourceline, error_message))
    for element in contest_elts:
      object_id = element.get("objectId")
      name = element.find("Name")
      if name is None or not name.text:
        error_message = "Contest {0} is missing a <Name> ".format(object_id)
        error_log.append(
            loggers.ErrorLogEntry(element.sourceline, error_message))
        continue
      name_contest_id.setdefault(name.text, []).append(object_id)

    for name, contests in name_contest_id.items():
      if len(contests) > 1:
        error_message = (
            "Contest name '{0}' appears in following {1} contests: {2}".format(
                name, len(contests), ", ".join(contests)))
        error_log.append(loggers.ErrorLogEntry(None, error_message))
    if error_log:
      raise loggers.ElectionTreeError(
          "The Election File contains duplicate contest names.", error_log)


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
      raise loggers.ElectionError(
          "Line: %d. %s element with object id %s is missing a stable id" %
          (element.sourceline, element_name, object_id))


class CandidatesMissingPartyData(base.BaseRule):
  """Each Candidate should have party data associated with it.

  A Candidate object that has no PartyId attached to it should be picked up
  within this class and returned to the user as a warning.
  """

  def elements(self):
    return ["Candidate"]

  def check(self, element):
    party_id = element.find("PartyId")
    if party_id is None or not party_id.text:
      raise loggers.ElectionWarning(
          "Line %d: Candidate %s is missing party data" %
          (element.sourceline, element.get("objectId")))


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
      raise loggers.ElectionWarning("Person {} is missing party data".format(
          element.get("objectId")))


class AllCaps(base.BaseRule):
  """Name elements should not be in all uppercase.

  If the name elements in Candidates, Contests and Person elements are in
  uppercase, the list of objectIds of those elements will be returned to
  the user as a warning.
  """

  def elements(self):
    return ["Candidate", "CandidateContest", "PartyContest", "Person"]

  def check(self, element):
    object_id = element.get("objectId")
    if element.tag == "Candidate":
      ballot_name_element = element.find("BallotName")
      if ballot_name_element is None:
        return
      ballot_name = ballot_name_element.find("Text")
      if ballot_name is None:
        return
      name = ballot_name.text
      if name and name.isupper():
        raise loggers.ElectionWarning(
            "Line %d. Candidate %s has name in all upper case letters." %
            (element.sourceline, object_id))
    elif element.tag == "Contest":
      name_element = element.find("Name")
      if name_element is None:
        return
      name = name_element.text
      if name and name.isupper():
        raise loggers.ElectionWarning(
            "Line %d. Contest %s has name in all upper case letters." %
            (element.sourceline, object_id))
    else:
      full_name_element = element.find("FullName")
      if full_name_element is None:
        return
      full_name = full_name_element.find("Text")
      if full_name is None:
        return
      name = full_name.text
      if name and name.isupper():
        raise loggers.ElectionWarning(
            "Line %d. Person %s has name in all upper case letters." %
            (element.sourceline, object_id))


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
      raise loggers.ElectionError(
          sourceline_prefix(element) +
          "Element does not contain text in all required languages, missing: " +
          str(required_language_set - languages))


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
        raise loggers.ElectionError(
            "%sType of element %s is set to 'other' even though "
            "'%s' is a valid enumeration" %
            (sourceline_prefix(element), element.tag, other_type_element.text))


class ValidateOcdidLowerCase(base.BaseRule):
  """Validate that the ocd-ids are all lower case.

  Throw a warning if the ocd-ids are not all in lowercase.
  """

  def elements(self):
    return ["ExternalIdentifiers"]

  def check(self, element):
    for ocd_id in get_external_id_values(element, "ocd-id"):
      if not ocd_id.islower():
        raise loggers.ElectionWarning(
            "%sOCD-ID %s is not in all lower case letters. "
            "Valid OCD-IDs should be all lowercase." %
            (sourceline_prefix(element), ocd_id))


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
        raise loggers.ElectionWarning(
            "Contest {} has more than one associated office.".format(
                element.get("objectId", "")))
    else:
      raise loggers.ElectionWarning(
          "Contest {} has no associated offices.".format(
              element.get("objectId", "")))


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
            raise loggers.ElectionError(
                "Office object {} has {} OfficeHolders. Must have exactly one."
                .format(office.get("objectId", ""), str(len(ids))))
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
      raise loggers.ElectionError(
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
        raise loggers.ElectionError("VoteCount types {0} should not be nested "
                                    " in {1} Contest ({2})".format(
                                        ", ".join(errors), contest_type,
                                        element.attrib["objectId"]))


class URIValidator(base.BaseRule):
  """Basic URL validations.

  Ensure each URL has valid protocol, domain, and query.
  """

  def elements(self):
    return ["Uri"]

  def check(self, element):
    url = element.text
    if url is None:
      raise loggers.ElectionError("Missing URI value.")

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
      raise loggers.ElectionError(
          "The provided URI, {}, is invalid for the following reasons: {}."
          .format(url.encode("ascii", "ignore"), ", ".join(discrepencies)))


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

      elt_hierarchy = get_parent_hierarchy_object_id_str(uri)
      if uri_mapping[annotation_platform].get(uri_value):
        uri_mapping[annotation_platform][uri_value].append(elt_hierarchy)
      else:
        uri_mapping[annotation_platform][uri_value] = [elt_hierarchy]
    return uri_mapping

  def check(self):
    all_uri_elements = self.get_elements_by_class(self.election_tree, "Uri")
    office_uri_elements = self.get_elements_by_class(
        self.election_tree, "Office//ContactInformation//Uri")
    uri_elements = set(all_uri_elements) - set(office_uri_elements)
    annotation_mapper = self._extract_uris_by_category(uri_elements)

    error_log = []
    for annotation, value_counter in annotation_mapper.items():
      for uri, hierarchy_list in value_counter.items():
        if len(hierarchy_list) > 1:
          error_message = ("The annotation type {} contains duplicate value:"
                           " {}. It appears {} times in the following elements:"
                           " {}").format(annotation, uri, len(hierarchy_list),
                                         hierarchy_list)
          error_log.append(loggers.ErrorLogEntry(None, error_message))

    if error_log:
      raise loggers.ElectionError(("There are duplicate URIs in the feed. "
                                   "URIs should be unique for each category."),
                                  error_log)


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

  def check_url(self, url, annotation, platform):
    parsed_url = urlparse(url)
    # Ensure media platform name is in URL.
    if (platform != "website" and platform not in parsed_url.netloc and
        not (platform == "facebook" and "fb.com" in parsed_url.netloc)):
      # Note that the URL is encoded for printing purposes
      raise loggers.ElectionError(
          "Annotation {} is incorrect for URI {}.".format(
              annotation, url.encode("ascii", "ignore")))

  def check(self, element):
    uris = element.findall("Uri")

    for uri in uris:
      annotation = uri.get("Annotation", "").strip()
      url = uri.text.strip()
      ascii_url = url.encode("ascii", "ignore")

      if not annotation:
        raise loggers.ElectionWarning(
            "URI {} is missing annotation.".format(ascii_url))

      # Only do platform checks if the annotation is not an image.
      if not re.search(r"candidate-image", annotation):
        ann_elements = annotation.split("-")
        if len(ann_elements) == 1:
          platform = ann_elements[0]
          # One element would imply the annotation could be a platform
          # without a usage type, which is checked here.
          if platform in self.TYPE_PLATFORMS:
            raise loggers.ElectionWarning(
                "Annotation {} missing usage type.".format(annotation))
          elif platform in self.USAGE_TYPES:
            raise loggers.ElectionError("Annotation {} has usage type, "
                                        "missing platform.".format(annotation))
          elif platform not in self.PLATFORM_ONLY_ANNOTATIONS:
            raise loggers.ElectionError(
                "Annotation {} is not a valid annotation for URI {}.".format(
                    annotation, ascii_url))
        elif len(ann_elements) == 2:
          # Two elements at this stage would mean the annotation
          # must be a platform with a usage type.
          usage_type, platform = ann_elements
          if (usage_type not in self.USAGE_TYPES or
              platform not in self.TYPE_PLATFORMS):
            raise loggers.ElectionWarning(
                "{} is not a valid annotation.".format(annotation))
        else:
          # More than two implies an invalid annotation.
          raise loggers.ElectionError(
              "Annotation {} is invalid for URI {}.".format(
                  annotation, ascii_url))
        # Finally, check platform is in the URL.
        self.check_url(url, annotation, platform)


class OfficesHaveJurisdictionID(base.BaseRule):
  """Each office must have a jurisdiction-id."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    jurisdiction_values = get_additional_type_values(element, "jurisdiction-id")
    jurisdiction_values.extend([
        j_id.strip()
        for j_id in get_external_id_values(element, "jurisdiction-id")
        if j_id.strip()
    ])
    object_id = element.get("objectId")
    if not jurisdiction_values:
      raise loggers.ElectionError(
          "Office {} is missing a jurisdiction-id.".format(object_id))
    if len(jurisdiction_values) > 1:
      raise loggers.ElectionError(
          "Office {} has more than one jurisdiction-id.".format(object_id))


class ValidJurisdictionID(base.ValidReferenceRule):
  """Each jurisdiction id should refer to a valid GpUnit."""

  def __init__(self, election_tree, schema_tree):
    super(ValidJurisdictionID, self).__init__(election_tree, schema_tree,
                                              "GpUnit")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    jurisdiction_values = get_additional_type_values(root, "jurisdiction-id")
    jurisdiction_values.extend(get_external_id_values(root, "jurisdiction-id"))
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
      raise loggers.ElectionError(
          ("Office {} is missing an office-level.".format(
              element.get("objectId", ""))))
    if len(office_level_values) > 1:
      raise loggers.ElectionError(
          ("Office {} has more than one office-level.".format(
              element.get("objectId", ""))))
    office_level_value = office_level_values[0]
    if office_level_value not in office_utils.valid_office_level_values:
      raise loggers.ElectionError(
          ("Office {} has invalid office-level {}.".format(
              element.get("objectId", ""), office_level_value)))


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
      raise loggers.ElectionError(
          ("Office {} is missing an office-role.".format(
              element.get("objectId", ""))))
    if len(office_role_values) > 1:
      raise loggers.ElectionError(
          ("Office {} has more than one office-role.".format(
              element.get("objectId", ""))))
    office_role_value = office_role_values[0]
    if office_role_value not in office_utils.valid_office_role_values:
      raise loggers.ElectionError(
          ("Office {} has invalid office-role {}.".format(
              element.get("objectId", ""), office_role_value)))


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
      error_message = """The start date {} is in the past. Please double
      check that this is expected.""".format(self.start_date)
      raise loggers.ElectionWarning(error_message, self.error_log)


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
      raise loggers.ElectionError("The election dates are invalid: ",
                                  self.error_log)


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
        raise loggers.ElectionWarning(("Office (objectId: {}) is missing a "
                                       "Term").format(element.get("objectId")))

      self.gather_dates(term)
      if self.start_date is None:
        raise loggers.ElectionWarning(
            ("Office (objectId: {}) is missing a Term > StartDate.").format(
                element.get("objectId")))
      elif self.end_date is not None:
        self.check_end_after_start()

    if self.error_log:
      raise loggers.ElectionError("The Office term dates are invalid.",
                                  self.error_log)


class GpUnitsHaveInternationalizedName(base.BaseRule):
  """GpUnits must have at least one non-empty InternationlizedName element."""

  def elements(self):
    return ["GpUnit"]

  def check(self, element):
    intl_names = element.findall("InternationalizedName")
    missing_names = []
    object_id = element.get("objectId", "")
    if intl_names is None or not intl_names or len(intl_names) > 1:
      raise loggers.ElectionError(
          "GpUnit {} is required to have exactly one InterationalizedName element."
          .format(object_id))
    intl_name = intl_names[0]
    name_texts = intl_name.findall("Text")
    if name_texts is None or not name_texts:
      raise loggers.ElectionError(
          ("GpUnit {} InternationalizedName on line {} is required to have one "
           "or more Text elements.".format(object_id, intl_name.sourceline)))
    for name_text in name_texts:
      if name_text is None or not (name_text.text and name_text.text.strip()):
        missing_names.append(
            "GpUnit {} InternationalizedName on line {} does not have a text value."
            .format(object_id, intl_name.sourceline))
    if missing_names:
      raise loggers.ElectionError(
          ("GpUnit {} must not have empty InternationalizedName Text elements. "
           "{}".format(object_id, "\n".join(missing_names))))


class FullTextMaxLength(base.BaseRule):
  """FullText field should not be longer than MAX_LENGTH."""

  MAX_LENGTH = 30000  # about 8-10 pages of text, 4500-5000 words

  def elements(self):
    return ["FullText"]

  def check(self, element):
    intl_text_list = element.findall("Text")
    for intl_text in intl_text_list:
      if len(intl_text.text) > self.MAX_LENGTH:
        raise loggers.ElectionWarning(
            "FullText is longer than %s characters.  Please remove and "
            "include a link to the full text via InfoUri with Annotation "
            "'fulltext'." % (self.MAX_LENGTH))


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
        raise loggers.ElectionWarning(
            "Line: %d. Language: %s.  BallotText is missing but FullText is "
            "present for the same language. Please confirm that FullText "
            "contains only supplementary text and not text on the ballot "
            "itself." % (element.sourceline, language))


class BallotTitle(base.BaseRule):
  """BallotTitle must exist and should usually be shorter than BallotText."""

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    ballot_title_map = get_language_to_text_map(element.find("BallotTitle"))
    if not ballot_title_map:
      raise loggers.ElectionError(
          "Line %d. BallotMeasureContest is missing BallotTitle." %
          (element.sourceline))

    ballot_text_map = get_language_to_text_map(element.find("BallotText"))
    if not ballot_text_map:
      raise loggers.ElectionWarning(
          "Line %d. BallotText is missing. Please confirm that the ballot "
          " text/question is not in BallotTitle." % (element.sourceline))

    for language, ballot_title_string in ballot_title_map.items():
      if language not in ballot_text_map.keys() or len(
          ballot_text_map[language]) < len(ballot_title_string):
        raise loggers.ElectionWarning(
            "Line: %d. Language: %s. BallotText is missing or shorter than "
            "BallotTitle. Please confirm that the ballot text/question is not "
            "in BallotTitle." % (element.sourceline, language))


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
        self.election_tree, "CandidateCollection//Candidate")
    for candidate in candidates:
      ballot_name = candidate.find(".//BallotName/Text[@language='en']")
      if ballot_name is not None:
        if ballot_name.text.lower() in self._BALLOT_SELECTION_OPTIONS:
          invalid_candidates.append(candidate.get("objectId"))
    return invalid_candidates

  def check(self):
    candidate_contest_mapping = {}
    candidate_contests = self.get_elements_by_class(
        self.election_tree, "CandidateContest")
    for cc in candidate_contests:
      cand_ids = self._gather_contest_candidates(cc)
      contest_id = cc.get("objectId")
      candidate_contest_mapping[contest_id] = cand_ids

    invalid_candidates = self._gather_invalid_candidates()

    error_log = []
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
        error_log.append(loggers.ErrorLogEntry(None, warning_message))

    if invalid_candidates:
      warning_message = ("There are CandidateContests that appear to be "
                         "BallotMeasureContests based on the "
                         "BallotName values.")
      raise loggers.ElectionWarning("There are misformatted contests.",
                                    error_log)


class RequiredFields(base.BaseRule):
  """Check for required fields for given entity types and field names.

  To add a field, include the entity and field in the _element_field_mapping
  and add the entity to the elements list.
  """

  _element_field_mapping = {
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

  def elements(self):
    return list(self._element_field_mapping.keys())

  def check(self, element):
    error_log = []

    required_field_tags = self._element_field_mapping[element.tag]
    for field_tag in required_field_tags:
      required_field = element.find(field_tag)
      if (required_field is None or required_field.text is None
          or not required_field.text.strip()):
        error_log.append(
            loggers.ErrorLogEntry(None, (
                "Line {}. Element {} (objectId: {}) is missing required "
                "field {}.").format(element.sourceline, element.tag,
                                    element.get("objectId"), field_tag)))

    if error_log:
      raise loggers.ElectionError("{} is missing required fields.".format(
          element.tag), error_log)


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
    PersonHasUniqueFullName,
    PersonsMissingPartyData,
    GpUnitsHaveInternationalizedName,
    RequiredFields,
)

ELECTION_RULES = COMMON_RULES + (
    CandidatesMissingPartyData,
    CoalitionParties,
    DuplicateContestNames,
    ElectoralDistrictOcdId,
    OnlyOneElection,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    PercentSum,
    ProperBallotSelection,
    CandidatesReferencedOnce,
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
)

OFFICEHOLDER_RULES = COMMON_RULES + (
    PersonHasOffice,
    ProhibitElectionData,
    OfficeTermDates,
)

ALL_RULES = frozenset(COMMON_RULES + ELECTION_RULES + OFFICEHOLDER_RULES)

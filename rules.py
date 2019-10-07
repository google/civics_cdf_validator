# Copyright 2019 Google LLC
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

import csv
import datetime
import hashlib
import io
import os
import re
import shutil
import sys

from election_results_xml_validator import base
import enum
import github
import language_tags
from lxml import etree
import requests
from six.moves.urllib.parse import urlparse

_PARTY_LEADERSHIP_TYPES = ["party-leader-id", "party-chair-id"]


def sourceline_prefix(element):
  if hasattr(element, "sourceline") and element.sourceline is not None:
    return "Line %d. " % element.sourceline
  else:
    return ""


class Schema(base.TreeRule):
  """Checks if election file validates against the provided schema."""

  def check(self):
    schema_tree = etree.parse(self.schema_file)
    try:
      schema = etree.XMLSchema(etree=schema_tree)
    except etree.XMLSchemaParseError as e:
      raise base.ElectionError(
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
            base.ErrorLogEntry(error.line, error.message.encode("utf-8")))
      raise base.ElectionTreeError(
          "The election file didn't validate against schema.", errors)


class OptionalAndEmpty(base.BaseRule):
  """Checks for optional and empty fields."""

  def __init__(self, election_tree, schema_file):
    super(OptionalAndEmpty, self).__init__(election_tree, schema_file)
    self.previous = None

  def elements(self):
    schema_tree = etree.parse(self.schema_file)
    eligible_elements = []
    for _, element in etree.iterwalk(schema_tree):
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
      raise base.ElectionWarning(
          "Line %d. %s optional element included although it "
          "is empty." % (element.sourceline, element.tag))


class Encoding(base.TreeRule):
  """Checks that the file provided uses UTF-8 encoding."""

  def check(self):
    docinfo = self.election_tree.docinfo
    if docinfo.encoding != "UTF-8":
      raise base.ElectionError("Encoding on file is not UTF-8")


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
    object_id = element.get("objectId", None)
    tag = self.get_element_class(element)
    if object_id:
      if not object_id.startswith(self.elements_prefix[tag]):
        raise base.ElectionInfo(
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
      raise base.ElectionError("Line %d. %s is not a valid language code" %
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
      raise base.ElectionError(
          sourceline_prefix(element) +
          "Contest percents do not sum to 0 or 100: %f" % sum_percents)


class OnlyOneElection(base.BaseRule):
  """Check that there is only one Election in the ElectionReport."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if len(element.findall("Election")) > 1:
      raise base.ElectionError(
          sourceline_prefix(element) +
          "ElectionReport has more than one Election.")


class EmptyText(base.BaseRule):
  """Check that Text elements are not strictly whitespace."""

  def elements(self):
    return ["Text"]

  def check(self, element):
    if element.text is not None and not element.text.strip():
      raise base.ElectionWarning("Line %d. %s is empty" %
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
          error_log.append(base.ErrorLogEntry(error_line, error_message))
        else:
          all_object_ids.add(obj_id)
    if error_log:
      raise base.ElectionTreeError(
          "The Election File contains duplicate object IDs", error_log)


class ValidIDREF(base.BaseRule):
  """Check that IDREFs are valid.

  Every field of type IDREF should actually reference a value that exists in a
  field of type ID.
  """

  def __init__(self, election_tree, schema_file):
    super(ValidIDREF, self).__init__(election_tree, schema_file)
    self.all_object_ids = set()
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      if "objectId" not in element.attrib:
        continue
      else:
        obj_id = element.get("objectId")
        if not obj_id:
          continue
        else:
          self.all_object_ids.add(obj_id)

  def elements(self):
    schema_tree = etree.parse(self.schema_file)
    eligible_elements = []
    for _, element in etree.iterwalk(schema_tree):
      tag = self.strip_schema_ns(element)
      if (tag and tag == "element" and
          element.get("type") in ("xs:IDREF", "xs:IDREFS")):
        eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    if element.text:
      id_references = element.text.split()
      for id_ref in id_references:
        if id_ref not in self.all_object_ids:
          raise base.ElectionError("Line %d. %s is not a valid IDREF." %
                                   (element.sourceline, id_ref))


class ElectoralDistrictOcdId(base.BaseRule):
  """GpUnit referred to by Contest.ElectoralDistrictId MUST have a valid OCD-ID."""

  CACHE_DIR = "~/.cache"
  GITHUB_REPO = "opencivicdata/ocd-division-ids"
  GITHUB_DIR = "identifiers"
  # Reference http://docs.opencivicdata.org/en/latest/proposals/0002.html
  OCD_PATTERN = r"^ocd-division\/country:[a-z]{2}(\/(\w|-)+:(\w|-|\.|~)+)*$"

  def __init__(self, election_tree, schema_file):
    super(ElectoralDistrictOcdId, self).__init__(election_tree, schema_file)
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
      countries_file = "{0}/{1}".format(cache_directory, self.github_file)

      if not os.path.exists(countries_file):
        # Only initialize `github_repo` if there's no cached file.
        github_api = github.Github()
        self.github_repo = github_api.get_repo(self.GITHUB_REPO)
        if not os.path.exists(cache_directory):
          os.makedirs(cache_directory)
        self._download_data(countries_file)
      else:
        if self.check_github:
          last_mod_date = datetime.datetime.fromtimestamp(
              os.path.getmtime(countries_file))

          seconds_since_mod = (
              datetime.datetime.now() - last_mod_date
          ).total_seconds()

          # If 1 hour has elapsed, check GitHub for the last file update.
          if (seconds_since_mod/3600) > 1:
            github_api = github.Github()
            self.github_repo = github_api.get_repo(self.GITHUB_REPO)
            # Re-download the file if the file on GitHub was updated.
            if last_mod_date < self._get_latest_commit_date():
              self._download_data(countries_file)
            # Update the timestamp to reflect last GitHub check.
            os.utime(countries_file, None)
    ocd_id_codes = set()

    # CSVs read in Python3 must be specified as UTF-8.
    if sys.version_info.major < 3:
      with open(countries_file) as csvfile:
        csv_reader = csv.DictReader(csvfile)
        self._read_csv(csv_reader, ocd_id_codes)
    else:
      with open(countries_file, encoding="utf-8") as csvfile:
        csv_reader = csv.DictReader(csvfile)
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
      raise base.ElectionError(
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
    dir_contents = self.github_repo.get_dir_contents(self.GITHUB_DIR)
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
    valid_ocd_id = False
    referenced_gpunit = None
    external_ids = []
    for gpunit in self.gpunits:
      if gpunit.get("objectId", None) == element.text:
        referenced_gpunit = gpunit
        external_ids = gpunit.findall(".//ExternalIdentifier")
        for extern_id in external_ids:
          id_type = extern_id.find("Type")
          if id_type is not None and id_type.text == "ocd-id":
            value = extern_id.find("Value")
            if value is None or not hasattr(value, "text"):
              continue
            ocd_id = self._encode_ocdid_value(value.text)
            valid_ocd_id = (ocd_id in self.ocds and
                            self.ocd_matcher.match(ocd_id))
          if (id_type is not None and id_type.text != "ocd-id" and
              id_type.text.lower() == "ocd-id"):
            raise base.ElectionError(
                "Line %d. The External Identifier case is incorrect"
                ". Should be ocd-id and not %s" %
                (id_type.sourceline, id_type.text))
    if referenced_gpunit is None:
      raise base.ElectionError(
          "Line %d. The ElectoralDistrictId element for contest %s does "
          "not refer to a GpUnit. Every ElectoralDistrictId MUST "
          "reference a GpUnit" % (element.sourceline, contest_id))
    if referenced_gpunit is not None and not external_ids:
      raise base.ElectionError(
          "Line %d. The GpUnit %s on line %d referenced by contest %s "
          "does not have any external identifiers" %
          (element.sourceline, element.text, referenced_gpunit.sourceline,
           contest_id))
    if referenced_gpunit is not None and not valid_ocd_id:
      raise base.ElectionError(
          "Line %d. The ElectoralDistrictId element for contest %s "
          "refers to GpUnit %s on line %d that does not have a valid OCD "
          "ID" % (element.sourceline, contest_id, element.text,
                  referenced_gpunit.sourceline))


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
      for extern_id in element.iter("ExternalIdentifier"):
        id_type = extern_id.find("Type")
        if id_type is not None and id_type.text == "ocd-id":
          value = extern_id.find("Value")
          if value is None or not hasattr(value, "text"):
            continue
          ocd_id = self._encode_ocdid_value(value.text)
          if ocd_id not in self.ocds:
            raise base.ElectionWarning(
                "The OCD ID %s in GpUnit %s defined on line %d is "
                "not valid" % (ocd_id, gpunit_id, value.sourceline))


class DuplicateGpUnits(base.TreeRule):
  """Detect GpUnits which are effectively duplicates of each other."""

  def __init__(self, election_tree, schema_file):
    super(DuplicateGpUnits, self).__init__(election_tree, schema_file)
    self.leaf_nodes = set()
    self.children = dict()
    self.defined_gpunits = set()

  def check(self):
    root = self.election_tree.getroot()
    if root is None:
      return
    collection = root.find("GpUnitCollection")
    if collection is None:
      return
    self.process_gpunit_collection(collection)
    self.find_duplicates()

  def process_gpunit_collection(self, collection):
    for gpunit in collection:
      if "objectId" not in gpunit.attrib:
        continue
      object_id = gpunit.attrib["objectId"]
      self.defined_gpunits.add(object_id)
      composing_ids = self.get_composing_gpunits(gpunit)
      if composing_ids is None:
        self.leaf_nodes.add(object_id)
      else:
        self.children[object_id] = composing_ids
    for gpunit in collection:
      self.process_one_gpunit(gpunit)

  def find_duplicates(self):
    tags = dict()
    for object_id in self.children:
      if not self.children[object_id]:
        continue
      sorted_children = " ".join(sorted(self.children[object_id]))
      if sorted_children in tags:
        tags[sorted_children].append(object_id)
      else:
        tags[sorted_children] = [object_id]
    for tag in tags:
      if len(tags[tag]) == 1:
        continue
      raise base.ElectionError("GpUnits [%s] are duplicates" %
                               (", ".join(tags[tag])))

  def process_one_gpunit(self, gpunit):
    """Define each GpUnit in terms of only nodes with no children."""
    if "objectId" not in gpunit.attrib:
      return
    object_id = gpunit.attrib["objectId"]
    if object_id in self.leaf_nodes:
      return
    composing_ids = self.get_composing_gpunits(gpunit)
    visited = set()
    while True:
      # Iterate over the set of GpUnits which compose this particular
      # GpUnit. If any of the children of this node have children
      # themselves, replace the child of this node with the set of
      # grandchildren. Repeat until the only children of this GpUnit are
      # leaf nodes.
      non_leaf_nodes = set()
      are_leaf_nodes = set()
      for composing_id in composing_ids:
        if (composing_id in self.leaf_nodes or
            composing_id not in self.defined_gpunits):
          are_leaf_nodes.add(composing_id)
        elif composing_id in self.children:
          non_leaf_nodes.add(composing_id)
        # If we get here then it means that the composing ID (i.e., the
        # GpUnit referenced by the current GpUnit) is not actually
        # present in the doc. Since everything is handled by IDREFS this
        # means that the schema validation should catch this, and we can
        # skip this error.
      if not non_leaf_nodes:
        self.children[object_id] = are_leaf_nodes
        return
      for middle_node in non_leaf_nodes:
        if middle_node not in self.children:
          # TODO(kaminer): Confirm whether or not it's possible to remove
          # this block. non_leafe_nodes consist exclusively of nodes in
          # self.children (see line 565). Checking for them not to be there
          # seems like something that will never happen.
          print("Non-leaf node {} has no children".format(middle_node))
          continue
        visited.add(middle_node)
        for node in self.children[middle_node]:
          if node in visited:
            continue
          composing_ids.add(node)
        composing_ids.remove(middle_node)

  def get_composing_gpunits(self, gpunit):
    composing = gpunit.find("ComposingGpUnitIds")
    if composing is None or composing.text is None:
      return None
    composing_ids = composing.text.split()
    if not composing_ids:
      return None
    return set(composing_ids)


class GpUnitsTree(base.TreeRule):
  """Ensure that GpUnits form a tree and no cycles are present."""

  def __init__(self, election_tree, schema_file):
    super(GpUnitsTree, self).__init__(election_tree, schema_file)
    self.edges = dict()  # Used to maintain the record of connected edges
    self.visited = {}  # Used to store status of the nodes as - visited ot not.
    self.error_log = []
    self.bad_nodes = []

  def build_tree(self, gpunit):
    # Check if the node is already visited
    if gpunit in self.visited:
      if gpunit not in self.bad_nodes:
        error_message = ("Cycle detected at node {0}".format(gpunit))
        self.error_log.append(base.ErrorLogEntry(None, error_message))
        self.bad_nodes.append(gpunit)
      return
    self.visited[gpunit] = 1
    # Check each composing_gpunit and its edges if any.
    for child_unit in self.edges[gpunit]:
      if child_unit in self.edges:
        self.build_tree(child_unit)
      else:
        error_message = ("Node {0} is not present in the"
                         " file as a GpUnit element.".format(child_unit))
        self.error_log.append(base.ErrorLogEntry(None, error_message))

  def check(self):
    for element in self.get_elements_by_class(self.election_tree, "GpUnit"):
      object_id = element.get("objectId", None)
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
      raise base.ElectionTreeError("The GpUnits have a cycle.", self.error_log)


class OtherType(base.BaseRule):
  """Elements with an "other" enum should set OtherType.

  Elements that have enumerations which include a value named other should
  -- when that enumeration value is other -- set the corresponding field
  OtherType within the containing element.
  """

  def elements(self):
    schema_tree = etree.parse(self.schema_file)
    eligible_elements = []
    for element in schema_tree.iterfind("{%s}complexType" %
                                        self._XSCHEMA_NAMESPACE):
      for elem in element.iter():
        tag = self.strip_schema_ns(elem)
        if tag == "element":
          elem_name = elem.get("name", None)
          if elem_name and elem_name == "OtherType":
            eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    type_element = element.find("Type")
    if type_element is not None and type_element.text == "other":
      other_type_element = element.find("OtherType")
      if other_type_element is None:
        raise base.ElectionError(
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

  def __init__(self, election_tree, schema_file):
    super(PartisanPrimary, self).__init__(election_tree, schema_file)
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
      raise base.ElectionError(
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
          raise base.ElectionWarning(
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
        raise base.ElectionError(
            "Line %d. Coalition %s must define PartyIDs" %
            (coalition.sourceline, coalition.get("objectId", None)))


class UniqueLabel(base.BaseRule):
  """Labels should be unique within a file."""

  def __init__(self, election_tree, schema_file):
    super(UniqueLabel, self).__init__(election_tree, schema_file)
    self.labels = set()

  def elements(self):
    schema_tree = etree.parse(self.schema_file)
    eligible_elements = []
    for _, element in etree.iterwalk(schema_tree):
      tag = self.strip_schema_ns(element)
      if tag == "element":
        elem_type = element.get("type", None)
        if elem_type == "InternationalizedText":
          if element.get("name") not in eligible_elements:
            eligible_elements.append(element.get("name"))
    return eligible_elements

  def check(self, element):
    element_label = element.get("label", None)
    if element_label:
      if element_label in self.labels:
        raise base.ElectionError(
            "Line %d. Duplicate label '%s'. Label already defined" %
            (element.sourceline, element_label))
      else:
        self.labels.add(element_label)


class ReusedCandidate(base.TreeRule):
  """Candidate should be referred to by only one contest.

  A Candidate object should only ever be referenced from one contest. If a
  Person is running in multiple Contests, then that Person is a Candidate
  several times over, but a Candida(te|cy) can't span contests.
  """

  def __init__(self, election_tree, schema_file):
    super(ReusedCandidate, self).__init__(election_tree, schema_file)

    # Mapping of candidates and candidate selections.
    self.seen_candidates = {}

  def _register_candidates(self):
    candidate_selections = self.get_elements_by_class(self.election_tree,
                                                      "CandidateSelection")
    for candidate_selection in candidate_selections:
      candidate_selection_id = candidate_selection.get("objectId", None)
      candidate_ids = candidate_selection.find("CandidateIds")
      if candidate_ids is None:
        continue
      for candidate_id in candidate_ids.text.split():
        if candidate_selection_id:
          self.seen_candidates.setdefault(candidate_id,
                                          []).append(candidate_selection_id)

  def check(self):
    self._register_candidates()
    error_log = []
    for cand_id, cand_select_ids in self.seen_candidates.items():
      if len(cand_select_ids) > 1:
        error_message = ("A Candidate object should only ever be referenced"
                         " from one CandidateSelection. Candidate %s is"
                         " referenced by the following CandidateSelections "
                         ":- %s") % (cand_id, ", ".join(cand_select_ids))
        error_log.append(base.ErrorLogEntry(None, error_message))
    if error_log:
      raise base.ElectionTreeError(
          "The Election File contains reused Candidates", error_log)


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
        contest_id = element.get("objectId", None)
        selection_id = selection.get("objectId", None)
        raise base.ElectionError(
            "Line %d. The Contest %s does not contain the right "
            "BallotSelection. %s must have a %s but contains a "
            "%s, %s" % (element.sourceline, contest_id, tag,
                        self.con_sel_mapping[tag], selection_tag, selection_id))


class PartiesHaveDifferentColors(base.BaseRule):
  """Each Party should have a single, unique hex Color without a leading '#'.

  A Party object that has no Color or an invalid Color should be picked up
  within this class and returned to the user as a warning.
  """

  def elements(self):
    return ["PartyCollection"]

  def check(self, element):
    party_colors = {}
    warnings = []
    for party in element.findall("Party"):
      colors = party.findall("Color")
      if not colors:
        continue
      party_object_id = party.get("objectId")
      if len(colors) > 1:
        warnings.append(
            "Line %d: Party %s has more than one color." %
            (element.sourceline, party.get("objectId"))
        )
      for color in colors:
        color_val = color.text
        if not color_val:
          warnings.append(
              "Line %d: Color tag in Party %s is missing a value." %
              (element.sourceline, party_object_id)
          )
        else:
          try:
            int(color_val, 16)
          except ValueError:
            warnings.append(
                "Line %d: %s in Party %s is not a valid hex color." %
                (element.sourceline, color_val, party_object_id)
            )
          if color_val in party_colors:
            warnings.append(
                "Line %d: Party %s has same color as Party %s." %
                (element.sourceline, party_object_id, party_colors[color_val])
            )
          else:
            party_colors[color_val] = party_object_id
    if warnings:
      raise base.ElectionWarning(
          "The Election File contains the following "
          "party color warning(s) \n{}".format("\n".join(warnings)),
          warning_log=warnings
      )


class MissingPartyAffiliation(base.ValidReferenceRule):
  """Each Person/Candidate PartyId must have an associated Party.

  A PartyId that has no Party that references them should be picked up
  within this class and returned to the user as an error.
  """

  def __init__(self, election_tree, schema_file):
    super(MissingPartyAffiliation, self).__init__(
        election_tree, schema_file, "Party")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    check_party_ids = set()

    party_ids = root.findall(".//CandidateCollection//Candidate//PartyId")
    party_ids += root.findall(".//PersonCollection//Person//PartyId")

    for elem in party_ids:
      if elem.text and elem.text.strip():
        check_party_ids.add(elem.text.strip())
    return check_party_ids

  def _gather_defined_values(self):
    all_parties = set()
    party_collection = self.election_tree.getroot().find("PartyCollection")
    if party_collection is not None:
      all_parties = set(party.attrib["objectId"] for party
                        in party_collection if party is not None
                        and party.get("objectId", None))
    return all_parties


class CandidateNotReferenced(base.TreeRule):
  """Candidate should have AT LEAST one contest they are referred to.

  A Candidate object that has no contests attached to them should be picked up
  within this class and returned to the user as an error.
  """

  def __init__(self, election_tree, schema_file):
    super(CandidateNotReferenced, self).__init__(election_tree, schema_file)
    self.cand_to_cand_selection = {}

  def check(self):
    error_log = []
    candidates = self.get_elements_by_class(self.election_tree, "Candidate")
    for candidate in candidates:
      cand_id = candidate.get("objectId", None)
      self.cand_to_cand_selection[cand_id] = []

    candidate_selections = self.get_elements_by_class(self.election_tree,
                                                      "CandidateSelection")
    for candidate_selection in candidate_selections:
      candidate_selection_id = candidate_selection.get("objectId", None)
      candidate_ids = candidate_selection.find("CandidateIds")
      # if no candidate ids, skip to the next one
      if candidate_ids is None or candidate_selection_id is None:
        continue
      for candidate_id in candidate_ids.text.split():
        self.cand_to_cand_selection.setdefault(
            candidate_id, []).append(candidate_selection_id)

    for cand_id, cand_select_ids in self.cand_to_cand_selection.items():
      if not cand_select_ids:
        error_message = ("A Candidate object should be referenced from one"
                         " CandidateSelection. Candidate {0} is not referenced"
                         " by any CandidateSelections").format(cand_id)
        error_log.append(base.ErrorLogEntry(None, error_message))
    if error_log:
      raise base.ElectionTreeError(
          "The Election File contains unreferenced Candidates", error_log)


class DuplicateContestNames(base.TreeRule):
  """Check that the file contains unique ContestNames.

  Add Warning if duplicate ContestName found.
  """

  def check(self):
    # Mapping for <Name> and its Contest ObjectId.
    name_contest_id = {}
    error_log = []

    # TODO(kaminer) Avoid the iterwalk by extending BaseRule
    # and only checking ContestCollection. Verify with Justin
    # Get the object ids associated with each contest name.
    for _, element in etree.iterwalk(self.election_tree):
      tag = self.strip_schema_ns(element)
      if tag != "Contest":
        continue
      object_id = element.get("objectId", None)
      name = element.find("Name")
      if name is None or not name.text:
        error_message = "Contest {0} is missing a <Name> ".format(object_id)
        error_log.append(base.ErrorLogEntry(element.sourceline, error_message))
        continue
      name_contest_id.setdefault(name.text, []).append(object_id)

    for name, contests in name_contest_id.items():
      if len(contests) > 1:
        error_message = (
            "Contest name '{0}' appears in following {1} contests: {2}".format(
                name, len(contests), ", ".join(contests)))
        error_log.append(base.ErrorLogEntry(None, error_message))
    if error_log:
      raise base.ElectionTreeError(
          "The Election File contains duplicate contest names.", error_log)


class CheckIdentifiers(base.TreeRule):
  """Check that the NIST objects in the feed have an <ExternalIdentifier> block.

  Add an error message if the block is missing.
  """

  _SKIPPABLE_TYPES = ["contest-stage"]

  def check(self):
    identifier_values = {}
    error_log = []
    # TODO(kaminer) Turn this rule into a BaseRule by returning
    # this list from elements function.
    nist_objects = ("Candidate", "Contest", "Party")
    for _, element in etree.iterwalk(self.election_tree):
      nist_obj = self.strip_schema_ns(element)
      if nist_obj not in nist_objects:
        continue
      object_id = element.get("objectId")
      external_identifiers = element.find("ExternalIdentifiers")
      if external_identifiers is None:
        err_message = "{0} {1} is missing a stable ExternalIdentifier".format(
            nist_obj, object_id)
        error_log.append(base.ErrorLogEntry(element.sourceline, err_message))
        continue
      identifier = external_identifiers.find("ExternalIdentifier")
      if identifier is None:
        err_message = "{0} {1} is missing a stable ExternalIdentifier.".format(
            nist_obj, object_id)
        error_log.append(base.ErrorLogEntry(element.sourceline, err_message))
        continue
      value = identifier.find("Value")
      if value is None or not value.text:
        err_message = "{0} {1} is missing a stable ExternalIdentifier.".format(
            nist_obj, object_id)
        error_log.append(base.ErrorLogEntry(element.sourceline, err_message))
        continue
      id_type = identifier.find("Type")
      if id_type is not None and id_type.text == "other":
        other_type = identifier.find("OtherType")
        if other_type is not None and other_type.text in self._SKIPPABLE_TYPES:
          continue
      identifier_values.setdefault(value.text, []).append(object_id)
    for value_text, obj_ids in identifier_values.items():
      if len(obj_ids) > 1:
        err_message = ("Stable ExternalIdentifier '{0}' is used for the "
                       "following {1} objectIds: {2}").format(
                           value_text, len(obj_ids), ", ".join(obj_ids))
        error_log.append(base.ErrorLogEntry(None, err_message))
    if error_log:
      raise base.ElectionTreeError(
          "The Election File has following issues with the identifiers:",
          error_log)


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
      raise base.ElectionWarning("Line %d: Candidate %s is missing party data" %
                                 (element.sourceline, element.get("objectId")))


class OfficeMissingOfficeHolderPersonData(base.ValidReferenceRule):
  """Each Office must have Persons occupying it.

  An Office object that has no OfficeHolderPersonIds in it should be
  picked up within this class and returned as an error to the user.
  """

  def __init__(self, election_tree, schema_file):
    super(OfficeMissingOfficeHolderPersonData, self).__init__(
        election_tree, schema_file, "Person")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    reference_values = set()

    officeholder_ids = root.findall(
        ".//OfficeCollection//Office//OfficeHolderPersonIds")

    for elem in officeholder_ids:
      if elem.text and elem.text.strip():
        reference_values.update(elem.text.strip().split())
      else:
        raise base.ElectionError("Office is missing IDs of Officeholders.")
    return reference_values

  def _gather_defined_values(self):
    all_people = set()
    person_collection = self.election_tree.getroot().find("PersonCollection")
    if person_collection is not None:
      all_people = set(person.attrib["objectId"]
                       for person in person_collection)
    return all_people


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
      raise base.ElectionWarning("Person {} is missing party data".format(
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
        raise base.ElectionWarning(
            "Line %d. Candidate %s has name in all upper case letters." %
            (element.sourceline, object_id))
    elif element.tag == "Contest":
      name_element = element.find("Name")
      if name_element is None:
        return
      name = name_element.text
      if name and name.isupper():
        raise base.ElectionWarning(
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
        raise base.ElectionWarning(
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
      raise base.ElectionError(
          sourceline_prefix(element)
          + "Element does not contain text in all required languages, missing: "
          + str(required_language_set - languages))


class ValidEnumerations(base.BaseRule):
  """Valid enumerations should not be encoded as 'OtherType'.

  Elements that have valid enumerations should not be included
  as 'OtherType'. Instead, the corresponding <Type> field
  should include the actual valid enumeration value.
  """

  valid_enumerations = []

  def elements(self):
    schema_tree = etree.parse(self.schema_file)
    eligible_elements = []
    for element in schema_tree.iter():
      tag = self.strip_schema_ns(element)
      if tag == "enumeration":
        elem_val = element.get("value", None)
        if elem_val and elem_val != "other":
          self.valid_enumerations.append(elem_val)
      elif tag == "complexType":
        for elem in element.iter():
          tag = self.strip_schema_ns(elem)
          if tag == "element":
            elem_name = elem.get("name", None)
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
      if other_type_element is not None:
        if other_type_element.text in self.valid_enumerations:
          raise base.ElectionError(
              "%sType of element %s is set to 'other' even though "
              "'%s' is a valid enumeration"
              % (sourceline_prefix(element), element.tag,
                 other_type_element.text))


class ValidateOcdidLowerCase(base.BaseRule):
  """Validate that the ocd-ids are all lower case.

  Throw a warning if the ocd-ids are not all in lowercase.
  """

  def elements(self):
    return ["ExternalIdentifier"]

  def check(self, element):
    id_type = element.find("Type")
    if id_type is None:
      return
    id_type_text = id_type.text
    if id_type_text != "ocd-id":
      return
    id_value = element.find("Value")
    if id_value is None:
      return
    ocdid = id_value.text
    if ocdid is None or not ocdid.strip():
      return
    if not ocdid.islower():
      raise base.ElectionWarning(
          "%sOCD-ID %s is not in all lower case letters. "
          "Valid OCD-IDs should be all lowercase." %
          (sourceline_prefix(element), ocdid))


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
          # TODO(kaminer): OfficeMissingOfficeHolderPersonData allows more
          # than one id. Evaluate contradiction.
          if len(ids) > 1:
            raise base.ElectionError(
                "Office object {} has {} OfficeHolders. Must have exactly one."
                .format(office.get("objectId", ""), str(len(ids)))
            )
          person_reference_ids.update(ids)

    return person_reference_ids


class PartyLeadershipMustExist(base.ValidReferenceRule):
  """Each party leader or party chair should refer to a person in the feed."""

  def __init__(self, election_tree, schema_file):
    super(PartyLeadershipMustExist, self).__init__(
        election_tree, schema_file, "Person")

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
      all_person_ids = set(person.attrib["objectId"] for person in persons)
    return all_person_ids


class ProhibitElectionData(base.TreeRule):
  """Ensure that election data is not provided for officeholder feeds."""

  def check(self):
    root = self.election_tree.getroot()
    if root is not None and root.find("Election") is not None:
      raise base.ElectionError(
          "Election data is prohibited in officeholder feeds.")


class PersonsHaveValidGender(base.BaseRule):
  """Ensure that all Person objects have a valid gender identification."""

  _VALID_GENDERS = {"male", "m", "man", "female", "f", "woman",
                    "o", "x", "other", "nonbinary"}

  def elements(self):
    return ["Gender"]

  def check(self, element):
    if (element.text is not None
        and element.text.lower() not in self._VALID_GENDERS):
      raise base.ElectionError(
          "Person object has invalid gender value: %s" % element.text)


class VoteCountTypesCoherency(base.BaseRule):
  """Ensure VoteCount types describe the appropriate votable."""

  PARTY_VC_TYPES = {"seats-won", "seats-leading", "party-votes",
                    "seats-no-election", "seats-total", "seats-delta"}
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
        raise base.ElectionError("VoteCount types {0} should not be nested "
                                 " in {1} Contest ({2})"
                                 .format(", ".join(errors), contest_type,
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
      raise base.ElectionError("Missing URI value.")
    parsed_url = urlparse(url)
    discrepencies = []
    if parsed_url.scheme not in set(["http", "https"]):
      discrepencies.append("protocol - invalid")
    if not parsed_url.netloc:
      discrepencies.append("domain - missing")

    if discrepencies:
      raise base.ElectionError(
          "The provided URI, {}, is invalid for the following reasons: {}."
          .format(url, ", ".join(discrepencies))
      )


class ValidURIAnnotation(base.BaseRule):
  """Validate annotations on candidate/officeholder URLs.

  Ensure they describe the type of URL presented.
  Throws Warnings and Errors depending on type of invalidity.
  """

  TYPE_PLATFORMS = set(["facebook", "twitter", "instagram",
                        "youtube", "website", "fb"])
  USAGE_TYPES = set(["personal", "official", "campaign"])

  def elements(self):
    return ["ContactInformation"]

  def check_url(self, url, annotation, platform=None):
    parsed_url = urlparse(url)
    # Ensure media platform name is in URL.
    if platform and platform != "website" and platform not in parsed_url.netloc:
       # Note that the URL is encoded for printing purposes
      raise base.ElectionError("Annotation {} is incorrect for URI {}.".format(
          annotation, url.encode("ascii", "ignore")
      ))

  def check(self, element):
    uris = element.findall("Uri")

    for uri in uris:
      annotation = uri.get("Annotation", "").strip()
      url = uri.text.strip()

      if not annotation:
        raise base.ElectionWarning("URI {} is missing annotation."
                                   .format(url))

      if re.search(r"candidate-image", annotation):
        self.check_url(url, annotation)
      else:
        # If the annotation is not an image, do platform checks.
        ann_elements = annotation.split("-")
        if len(ann_elements) == 1:
          platform = ann_elements[0]
          # One element would imply the annotation could be a platform
          # without a usage type, which is checked here.
          if platform in self.TYPE_PLATFORMS:
            raise base.ElectionWarning("Annotation {} missing usage type."
                                       .format(annotation))
          elif platform in self.USAGE_TYPES:
            raise base.ElectionError("Annotation {} has usage type, "
                                     "missing platform.".format(annotation))
          elif platform != "wikipedia":
            raise base.ElectionError(
                "Annotation {} is not a valid annotation for URI {}."
                .format(annotation, url))
        elif len(ann_elements) == 2:
          # Two elements at this stage would mean the annotation
          # must be a platform with a usage type.
          usage_type, platform = ann_elements
          if (usage_type not in self.USAGE_TYPES or
              platform not in self.TYPE_PLATFORMS):
            raise base.ElectionError("{} is not a valid annotation."
                                     .format(annotation))
        else:
          # More than two implies an invalid annotation.
          raise base.ElectionError("Annotation {} is invalid for URI {}."
                                   .format(annotation, url))
        # Finally, check platform is in the URL.
        self.check_url(url, annotation, platform=platform)


class ValidJurisdictionID(base.ValidReferenceRule):
  """Each jurisdiction id should refer to a valid GpUnit."""

  def __init__(self, election_tree, schema_file):
    super(ValidJurisdictionID, self).__init__(
        election_tree, schema_file, "GpUnit")

  def _gather_reference_values(self):
    root = self.election_tree.getroot()
    jurisdiction_elements = root.findall(
        ".//AdditionalData[@type='jurisdiction-id']")

    external_ids = root.findall(".//ExternalIdentifier")
    for extern_id in external_ids:
      id_type = extern_id.find("Type")
      if (id_type is not None and id_type.text == "other"):
        other_type = extern_id.find("OtherType")
        if (other_type is not None and other_type.text == "jurisdiction-id"):
          if extern_id.find("Value") is not None:
            jurisdiction_elements.append(extern_id.find("Value"))

    return set([elem.text for elem in jurisdiction_elements])

  def _gather_defined_values(self):
    gp_unit_elements = self.election_tree.getroot().findall(".//GpUnit")
    return set([elem.get("objectId", None) for elem in gp_unit_elements])


class RuleSet(enum.Enum):
  """Names for sets of rules used to validate a particular feed type."""
  ELECTION = 1
  OFFICEHOLDER = 2

# To add new rules, create a new class, inherit the base rule,
# and add it to the correct rule list.
COMMON_RULES = (
    AllCaps,
    AllLanguages,
    CheckIdentifiers,
    DuplicateGpUnits,
    DuplicateID,
    EmptyText,
    Encoding,
    GpUnitOcdId,
    HungarianStyleNotation,
    LanguageCode,
    OtherType,
    OptionalAndEmpty,
    Schema,
    UniqueLabel,
    ValidEnumerations,
    ValidIDREF,
    ValidateOcdidLowerCase,
    PersonsHaveValidGender,
    MissingPartyAffiliation,
    PartyLeadershipMustExist,
    URIValidator,
    ValidURIAnnotation,
    GpUnitsTree,
    ValidJurisdictionID,
)

ELECTION_RULES = COMMON_RULES + (
    CandidateNotReferenced,
    CandidatesMissingPartyData,
    CoalitionParties,
    DuplicateContestNames,
    ElectoralDistrictOcdId,
    OnlyOneElection,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    PercentSum,
    ProperBallotSelection,
    ReusedCandidate,
    VoteCountTypesCoherency,
    PartiesHaveDifferentColors,
)

OFFICEHOLDER_RULES = COMMON_RULES + (
    PersonHasOffice,
    ProhibitElectionData,
    PersonsMissingPartyData,
    OfficeMissingOfficeHolderPersonData,
)

ALL_RULES = frozenset(COMMON_RULES + ELECTION_RULES + OFFICEHOLDER_RULES)

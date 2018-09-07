"""
Copyright 2016 Google Inc. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from __future__ import print_function

import argparse
import io
import os.path
import hashlib
from shutil import copyfile
from datetime import datetime
import language_tags
import requests
from lxml import etree
from github import Github
from election_results_xml_validator import base


def validate_file(parser, arg):
    """Check that the files provided exist."""
    if not os.path.exists(arg):
        parser.error("The file %s doesn't exist" % arg)
    else:
        return arg


def validate_rules(parser, arg):
    """Check that the listed rules exist"""
    invalid_rules = []
    rule_names = [x.__name__ for x in _RULES]
    input_rules = arg.strip().split(",")
    for rule in input_rules:
        if rule and rule not in rule_names:
            invalid_rules.append(rule)
    if invalid_rules:
        parser.error("The rule(s) %s do not exist" % ", ".join(invalid_rules))
    else:
        return input_rules


def validate_severity(parser, arg):
    """Check that the severity level provided is correct."""

    _VALID_SEVERITIES = {'info': 0, 'warning': 1, 'error': 2}
    if arg.strip().lower() not in _VALID_SEVERITIES:
        parser.error("Invalid severity. Options are error, warning, or info")
    else:
        return _VALID_SEVERITIES[arg.strip().lower()]


def validate_country_codes(parser, arg):
    """Check that the supplied 2 country code is correct.

    The repo is at https://github.com/opencivicdata/ocd-division-ids
    """
    country_codes = ["au", "ca", "cl", "de", "fi", "in", "nz", "mx", "ua", "us", "br"]
    if arg.strip().lower() not in country_codes:
        parser.error("Invalid country code. Available codes are: %s" %
                     ", ".join(country_codes))
    else:
        return arg.strip().lower()


def arg_parser():
    """Parser for command line arguments."""

    description = ("Script to validate that an elections results XML file "
                   "follows best practices")
    parser = argparse.ArgumentParser(description=description)
    subparsers = parser.add_subparsers(dest="cmd")
    parser_validate = subparsers.add_parser("validate")
    parser_validate.add_argument(
        "-x", "--xsd", help="Common Data Format XSD file path", required=True,
        metavar="xsd_file", type=lambda x: validate_file(parser, x))
    parser_validate.add_argument(
        "election_file", help="XML election file to be validated",
        metavar="election_file", type=lambda x: validate_file(parser, x))
    parser_validate.add_argument(
        "--ocdid_file", help="Local ocd-id csv file path", required=False,
        metavar="csv_file", type=lambda x: validate_file(parser, x))
    group = parser_validate.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "-i", help="Comma separated list of rules to be validated.",
        required=False, type=lambda x: validate_rules(parser, x))
    group.add_argument(
        "-e", help="Comma separated list of rules to be excluded.",
        required=False, type=lambda x: validate_rules(parser, x))
    parser_validate.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print out detailed log messages. Defaults to False",
        required=False)
    parser_validate.add_argument(
        "--severity", "-s",
        type=lambda x: validate_severity(parser, x),
        help="Minimum issue severity level - error, warning or info",
        required=False)
    parser_validate.add_argument(
        "-g", help="Skip check to see if there is a new OCD ID file on Github."
        "Defaults to True",
        action="store_true", required=False)
    parser_validate.add_argument(
        "-c", help="Two letter country code for OCD IDs.", metavar="country",
        type=lambda x: validate_country_codes(parser, x), required=False,
        default="us")
    subparsers.add_parser("list")
    return parser


class Schema(base.TreeRule):
    """Checks if election file validates against the provided schema."""

    def check(self):
        schema_tree = etree.parse(self.schema_file)
        try:
            schema = etree.XMLSchema(etree=schema_tree)
        except etree.XMLSchemaParseError as e:
            raise base.ElectionError(
                "The schema file could not be parsed correctly %s" %
                str(e))
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

    previous = None

    def elements(self):
        schema_tree = etree.parse(self.schema_file)
        eligible_elements = []
        for event, element in etree.iterwalk(schema_tree):
            tag = self.strip_schema_ns(element)
            if tag and tag == "element" and element.get("minOccurs") == "0":
                eligible_elements.append(element.get("name"))
        return eligible_elements

    def check(self, element):
        if element == self.previous:
            return
        self.previous = element
        if ((element.text is None or element.text.strip() == "") and
                not len(element)):
            raise base.ElectionWarning(
                "Line %d. %s optional element included although it "
                "is empty" % (element.sourceline, element.tag))


class Encoding(base.TreeRule):
    """Checks that the file provided uses UTF-8 encoding."""

    def check(self):
        docinfo = self.election_tree.docinfo
        if docinfo.encoding != "UTF-8":
            raise base.ElectionError("Encoding on file is not UTF-8")


class HungarianStyleNotation(base.BaseRule):
    """Check that element identifiers use Hungarian style notation.

    Hungarian sytle notation is used to maintain uniqueness and provide context
    for the identifiers
    """

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
                    "Should start with %s" % (element.sourceline, tag,
                                              object_id,
                                              self.elements_prefix[tag]))


class LanguageCode(base.BaseRule):
    """Check that Text elements have a valid language code."""

    def elements(self):
        return ["Text"]

    def check(self, element):
        if "language" not in element.attrib:
            return
        elem_lang = element.get("language")
        if (not elem_lang or elem_lang.strip() == "" or not language_tags.tags.check(elem_lang)):
            raise base.ElectionError(
                "Line %d. %s is not a valid language code" % (element.sourceline, elem_lang))


class EmptyText(base.BaseRule):
    """Check that Text elements are not empty."""

    def elements(self):
        return ["Text"]

    def check(self, element):
        if element.text is not None and element.text.strip() == "":
            raise base.ElectionWarning(
                "Line %d. %s is empty" % (
                    element.sourceline, element.tag))


class DuplicateID(base.TreeRule):
    """Check that the file does not contain duplicate object IDs
    """

    def check(self):
        all_object_ids = set()
        error_log = []
        for event, element in etree.iterwalk(
                self.election_tree, events=("end",)):
            if "objectId" not in element.attrib:
                continue
            else:
                obj_id = element.get("objectId")
                if not obj_id:
                    continue
                if obj_id in all_object_ids:
                    error_line = element.sourceline
                    error_message = "{0} is a duplicate object ID".format(
                        obj_id)
                    error_log.append(base.ErrorLogEntry(
                        error_line, error_message))
                else:
                    all_object_ids.add(obj_id)
        if error_log:
            raise base.ElectionTreeError(
                "The Election File contains duplicate object IDs", error_log)


class ValidIDREF(base.BaseRule):
    """Check that every field of type IDREF actually references a value that
    exists in a field of type ID.
    """

    all_object_ids = set()

    def __init__(self, election_tree, schema_file):
        super(ValidIDREF, self).__init__(election_tree, schema_file)
        for event, element in etree.iterwalk(
                self.election_tree, events=("end",)):
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
        for event, element in etree.iterwalk(schema_tree):
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
                    raise base.ElectionError(
                        "Line %d. %s is not a valid IDREF." % (
                            element.sourceline, id_ref))


class ElectoralDistrictOcdId(base.BaseRule):
    """GpUnit refered to by Contest.ElectoralDistrictId MUST have a valid OCD-ID.
    """
    ocds = []
    gpunits = []
    CACHE_DIR = "~/.cache"
    GITHUB_REPO = "opencivicdata/ocd-division-ids"
    GITHUB_DIR = "identifiers"
    check_github = True
    github_repo = None
    github_file = None
    local_file = None
    country_code = None

    def __init__(self, election_tree, schema_file):
        super(ElectoralDistrictOcdId, self).__init__(election_tree, schema_file)
        self.gpunits = []
        for gpunit in self.get_elements_by_class(self.election_tree, "GpUnit"):
            self.gpunits.append(gpunit)

    def setup(self):
        if not self.local_file:
            g = Github()
            self.github_file = "country-%s.csv" % self.country_code
            self.github_repo = g.get_repo(self.GITHUB_REPO)
        self.ocds = self._get_ocd_data()

    def _get_latest_commit_date(self):
        """Returns the latest commit date to country-us.csv."""
        latest_commit_date = None
        latest_commit = self.github_repo.get_commits(
            path="{0}/{1}".format(self.GITHUB_DIR, self.github_file))[0]
        latest_commit_date = latest_commit.commit.committer.date
        return latest_commit_date

    def _get_latest_file_blob_sha(self):
        """Returns the gihub blob sha of country-us.csv."""
        blob_sha = None
        dir_contents = self.github_repo.get_dir_contents(self.GITHUB_DIR)
        for content_file in dir_contents:
            if content_file.name == self.github_file:
                blob_sha = content_file.sha
                break
        return blob_sha

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
            copyfile("{0}.tmp".format(file_path), file_path)

    def _verify_data(self, file_path):
        """Compares blob sha to gihub sha and returns set of ocd id codes
        if the file is valid
        """
        file_sha1 = hashlib.sha1()
        ocd_id_codes = set()
        file_info = os.stat(file_path)
        # github calculates the blob sha like this
        #sha1("blob "+filesize+"\0"+data)
        file_sha1.update(b"blob %d\0" % file_info.st_size)
        with io.open(file_path, mode="rb") as fd:
            for line in fd:
                file_sha1.update(line)
                if line is not "":
                    ocd_id_codes.add(line.split(b",")[0])
        latest_file_sha = self._get_latest_file_blob_sha()
        if latest_file_sha != file_sha1.hexdigest():
            return False
        else:
            return True

    def _get_ocd_data(self):
        """Returns a list of OCD-ID codes. This list is populated using
        either a local file or a downloaded file from GitHub
    """
        if self.local_file:
            countries_file = self.local_file
        else:
            """Checks if OCD file is in ~/cache, downloads it if not."""
            cache_directory = os.path.expanduser(self.CACHE_DIR)
            countries_file = "{0}/{1}".format(cache_directory, self.github_file)
            if not os.path.exists(countries_file):
                if not os.path.exists(cache_directory):
                    os.makedirs(cache_directory)
                self._download_data(countries_file)
            else:
                if self.check_github:
                    last_mod_date = datetime.fromtimestamp(
                        os.path.getmtime(countries_file))
                    latest_github_commit_date = self._get_latest_commit_date()
                    if last_mod_date < latest_github_commit_date:
                        self._download_data(countries_file)
        ocd_id_codes = set()
        with io.open(countries_file, mode="rb") as fd:
            for line in fd:
                if line is not "":
                    ocd_id_codes.add(line.split(b",")[0])
        return ocd_id_codes

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
                        if value is None or not hasattr(value, 'text'):
                            continue
                        if value.text in self.ocds:
                            valid_ocd_id = True
                    if (id_type is not None and id_type.text != "ocd-id" and
                            id_type.text.lower() == "ocd-id"):
                        raise base.ElectionError(
                            "Line %d. The External Identifier case is incorrect"
                            ". Should be ocd-id and not %s" % (
                                id_type.sourceline, id_type.text)
                        )
        if referenced_gpunit is None:
            raise base.ElectionError(
                "Line %d. The ElectoralDistrictId element for contest %s does "
                "not refer to a GpUnit. Every ElectoralDistrictId MUST "
                "reference a GpUnit" % (element.sourceline, contest_id))
        if referenced_gpunit is not None and not external_ids:
            raise base.ElectionError(
                "Line %d. The GpUnit %s on line %d referenced by contest %s "
                "does not have any external identifiers" %
                (element.sourceline, element.text,
                 referenced_gpunit.sourceline, contest_id))
        if not valid_ocd_id and referenced_gpunit is not None:
            raise base.ElectionError(
                "Line %d. The ElectoralDistrictId element for contest %s "
                "refers to GpUnit %s on line %d that does not have a valid OCD "
                "ID" % (element.sourceline, contest_id, element.text,
                        referenced_gpunit.sourceline))


class GpUnitOcdId(ElectoralDistrictOcdId):
    """Any GpUnit that is a geographic district SHOULD have a valid OCD-ID."""

    districts = [
        "borough", "city", "county", "municipality", "state", "town",
        "township", "village"
    ]
    validate_ocd_file = True

    def __init__(self, election_tree, schema_file):
        super(GpUnitOcdId, self).__init__(election_tree, schema_file)

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
                    if value.text not in self.ocds:
                        raise base.ElectionWarning(
                            "The OCD ID %s in GpUnit %s defined on line %d is "
                            "not valid" % (
                                value.text, gpunit_id, value.sourceline))


class DuplicateGpUnits(base.TreeRule):
    """Detect GpUnits which are effectively duplicates of each other."""

    leaf_nodes = set()
    children = dict()
    defined_gpunits = set()

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
            sorted_children = " ".join(sorted(self.children[object_id]))
            if sorted_children in tags:
                tags[sorted_children].append(object_id)
            else:
                tags[sorted_children] = [object_id]
        for tag in tags:
            if len(tags[tag]) == 1:
                continue
            raise base.ElectionError(
                "GpUnits [%s] are duplicates" % (", ".join(tags[tag])))

    def process_one_gpunit(self, gpunit):
        """Define each GpUnit in terms of only nodes with no children."""
        if "objectId" not in gpunit.attrib:
            return
        object_id = gpunit.attrib["objectId"]
        if object_id in self.leaf_nodes:
            return
        composing_ids = self.get_composing_gpunits(gpunit)
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
                    # TODO: Figure out error
                    print("Non-leaf node {} has no children".format(middle_node))
                    continue
                for node in self.children[middle_node]:
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


class OtherType(base.BaseRule):
    """Elements with an "other" enum should set OtherType.

    Elements that have enumerations which include a value named other should
    -- when that enumeration value is other -- set the corresponding field
    OtherType within the containing element."""

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
                    "OtherType element is not defined" % (
                        element.sourceline, element.tag))


class PartisanPrimary(base.BaseRule):
    """Partisan elections should link to the correct political party.

    For an Election element of Election type primary, partisan-primary-open,
    or partisan-primary-closed, the Contests in that ContestCollection should
    have a PrimartyPartyIds that is present and non-empty.
    """
    election_type = None

    def __init__(self, election_tree, schema_file):
        super(PartisanPrimary, self).__init__(election_tree, schema_file)
        # There can only be one election element in a file
        election_elem = self.election_tree.find("Election")
        election_type_elem = election_elem.find("Type")
        if election_type_elem is not None:
            self.election_type = election_type_elem.text.strip()

    def elements(self):
        # only check contest elements if this is a partisan election
        if self.election_type and self.election_type in (
                "primary", "partisan-primary-open", "partisan-primary-closed"):
            return ["CandidateContest"]
        else:
            return []

    def check(self, element):
        primary_party_ids = element.find("PrimaryPartyIds")
        if (primary_party_ids is None or not primary_party_ids.text
                or not primary_party_ids.text.strip()):
            raise base.ElectionError(
                "Line %d. Election is of ElectionType %s but PrimaryPartyIds "
                "is not present or is empty" % (
                    primary_party_ids.sourceline, self.election_type))


class PartisanPrimaryHeuristic(PartisanPrimary):
    """Attempts to identify partisan primaries not marked up as such.
    """
    # add other strings that imply this is a primary contest
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
                        "but is not marked up as such." % (
                            element.sourceline, contest_name.text))


class CoalitionParties(base.TreeRule):
    """Coaltions should always define the Party IDs."""

    def check(self):
        coalitions = self.get_elements_by_class(self.election_tree, "Coalition")
        for coalition in coalitions:
            party_id = coalition.find("PartyIds")
            if (party_id is None or not party_id.text or
                    not party_id.text.strip()):
                raise base.ElectionError(
                    "Line %d. Coalition %s must define PartyIDs" %
                    (coalition.sourceline, coalition.get("objectId", None)))


class UniqueLabel(base.BaseRule):
    """Labels should be unique within a file.
    """
    labels = set()

    def elements(self):
        schema_tree = etree.parse(self.schema_file)
        eligible_elements = []
        for event, element in etree.iterwalk(schema_tree):
            tag = self.strip_schema_ns(element)
            if tag == "element":
                elem_type = element.get("type", None)
                if elem_type and elem_type == "InternationalizedText":
                    if element.get("name") not in eligible_elements:
                        eligible_elements.append(element.get("name"))
        return eligible_elements

    def check(self, element):
        element_label = element.get("label", None)
        if element_label:
            if element_label in self.labels:
                raise base.ElectionError(
                    "Line %d. Duplicate label '%s'. Label already defined"
                    % (element.sourceline, element_label))
            else:
                self.labels.add(element_label)


class ReusedCandidate(base.TreeRule):
    """Candidate should be referred to by only one contest.

    A Candidate object should only ever be referenced from one contest. If a
    Person is running in multiple Contests, then that Person is a Candidate
    several times over, but a Candida(te|cy) can't span contests.
    """
    seen_candidates = {}  # mapping of candidates and candidate selections

    def check(self):
        error_log = []
        candidate_selections = self.get_elements_by_class(
            self.election_tree, "CandidateSelection")
        for candidate_selection in candidate_selections:
            candidate_selection_id = candidate_selection.get("objectId", None)
            candidate_ids = candidate_selection.find("CandidateIds")
            if candidate_ids is None:
                break
            for candidate_id in candidate_ids.text.split():
                if candidate_selection_id:
                    self.seen_candidates.setdefault(
                        candidate_id, []).append(candidate_selection_id)
        for cand_id, cand_select_ids in self.seen_candidates.items():
            if len(cand_select_ids) > 1:
                error_message = "A Candidate object should only ever be " \
                    "referenced from one CandidateSelection. Candidate %s is " \
                    "referenced by the following CandidateSelections :- %s" % (
                        cand_id, ", ".join(cand_select_ids))
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
        for c in self.con_sel_mapping.keys():
            selections += self.get_elements_by_class(element,
                                                     self.con_sel_mapping[c])
        for selection in selections:
            selection_tag = self.get_element_class(selection)
            contest_id = element.get("objectId", None)
            selection_id = selection.get("objectId", None)
            if (selection_tag != self.con_sel_mapping[tag]):
                raise base.ElectionError(
                    "Line %d. The Contest %s does not contain the right "
                    "BallotSelection. %s must have a %s but contains a "
                    "%s, %s" % (
                        element.sourceline, contest_id, tag,
                        self.con_sel_mapping[tag], selection_tag, selection_id))


class CandidateNotReferenced(base.TreeRule):
    """Candidate should have AT LEAST one contest they are referred to.

    A Candidate object that has no contests attached to them should be picked up
    within this class and returned to the user as an error."""

    cand_to_cand_selection = {}  # mapping of candidates to cand_selection

    def check(self):
        error_log = []
        candidates = self.get_elements_by_class(self.election_tree, "Candidate")
        for candidate in candidates:
            cand_id = candidate.get("objectId", None)
            self.cand_to_cand_selection[cand_id] = []

        candidate_selections = self.get_elements_by_class(
            self.election_tree, "CandidateSelection")
        for candidate_selection in candidate_selections:
            candidate_selection_id = candidate_selection.get("objectId", None)
            candidate_ids = candidate_selection.find("CandidateIds")
            if candidate_ids is None or candidate_selection_id is None:
                break
            for candidate_id in candidate_ids.text.split():
                self.cand_to_cand_selection.setdefault(
                    candidate_id, []).append(candidate_selection_id)

        for cand_id, cand_select_ids in self.cand_to_cand_selection.items():
            if len(cand_select_ids) == 0:
                error_message = "A Candidate object should be referenced from one" \
                    " CandidateSelection. Candidate {0} is not referenced by any" \
                    " CandidateSelections".format(cand_id)
                error_log.append(base.ErrorLogEntry(
                    None, error_message))
        if error_log:
            raise base.ElectionTreeError(
                "The Election File contains unreferenced Candidates", error_log)

class DuplicateContestNames(base.TreeRule):
    """Check that the file contains unique ContestNames.
        Add Warning if duplicate ContestName found."""

    def check(self):
        name_contest_id = {}  # Mapping for <Name> and its Contest ObjectId.
        error_log = []
        for event, element in etree.iterwalk(self.election_tree):
            tag = self.strip_schema_ns(element)
            if tag != "Contest":
                continue
            object_id = element.get("objectId", None)
            name = element.find("Name")
            if name is None or not name.text:
                error_message = "Contest {0} is missing a <Name> ".format(
                    object_id)
                error_log.append(base.ErrorLogEntry(
                    element.sourceline, error_message))
                continue
            name_contest_id.setdefault(name.text, []).append(object_id)
            """Add names and its objectId as key and list of values.
        Ideally 1 objectId. If duplicates are found, then list of multiple objectIds."""
        for name, contests in name_contest_id.items():
            if len(contests) > 1:
                error_message = ("Contest name '{0}' appears in following {1} contests: {2}".format(
                    name, len(contests), ", ".join(contests)))
                error_log.append(base.ErrorLogEntry(None, error_message))
        if error_log:
            raise base.ElectionTreeError(
                "The Election File contains duplicate contest names.", error_log)


class CheckIdentifiers(base.TreeRule):
    """Check that the NIST objects in the feed has an '<ExternalIdentifier>' block.
        Add error message if the block is missing."""

    def check(self):
        identifier_values = {}
        error_log = []
        nist_objects = ("Candidate", "Contest", "Party")
        for event, element in etree.iterwalk(self.election_tree):
            nist_obj = self.strip_schema_ns(element)
            if nist_obj not in nist_objects:
                continue
            object_id = element.get("objectId")
            external_identifiers = element.find("ExternalIdentifiers")
            if external_identifiers is None:
                error_message = "{0} {1} is missing a stable ExternalIdentifier".format(
                    nist_obj, object_id)
                error_log.append(base.ErrorLogEntry(
                    element.sourceline, error_message))
                continue
            identifier = external_identifiers.find("ExternalIdentifier")
            if identifier is None:
                error_message = "{0} {1} is missing a stable ExternalIdentifier".format(
                    nist_obj, object_id)
                error_log.append(base.ErrorLogEntry(
                    element.sourceline, error_message))
                continue
            value = identifier.find("Value")
            if value is None or not value.text:
                error_message = "{0} {1} is missing a stable ExternalIdentifier".format(
                    nist_obj, object_id)
                error_log.append(base.ErrorLogEntry(
                    element.sourceline, error_message))
                continue
            identifier_values.setdefault(value.text, []).append(object_id)
        for value_text, obj_ids in identifier_values.items():
            if len(obj_ids) > 1:
                error_message = "Stable ExternalIdentifier '{0}' is a used for following {1} objectIds: {2}".format(
                                value_text, len(obj_ids), ", ".join(obj_ids))
                error_log.append(base.ErrorLogEntry(None, error_message))
        if error_log:
            raise base.ElectionTreeError(
                "The Election File has following issues with the identifiers.", error_log)

class CandidatesMissingPartyData(base.BaseRule):
    """Each Candidate should have party data associated with them.

    A Candidate object that has no PartyId attached to them should be picked up
    within this class and returned to the user as a warning."""

    def elements(self):
        return ["Candidate"]

    def check(self, element):
        party_id = element.find("PartyId")
        if party_id is None or not party_id.text:
            raise base.ElectionWarning("Line %d: Candidate %s is missing party data" % (
                element.sourceline, element.get("objectId")))

class AllCaps(base.BaseRule):
    """The Name elements in Candidates, Contests and Person elements should not be in all uppercase.

    If the name elements in Candidates, Contests and Person elements are in uppercase, 
    the list of objectIds of those elements will be returned to the user as a warning."""

    def elements(self):
        return ["Candidate", "CandidateContest", "Person"]

    def check(self, element):
        object_id = element.get("objectId")
        if element.tag == "Candidate":
            ballot_name = element.find("BallotName")
            if ballot_name.find("Text") is not None:
                name = ballot_name.find("Text").text
                if name is not None and name == name.upper():
                    raise base.ElectionWarning("Line %d. Candidate %s has name in all upper case letters." % (
                        element.sourceline, object_id))
        elif element.tag == "Contest":
            name_element = element.find("Name")
            if name_element is not None:
                name = name_element.text
                if name is not None and name == name.upper():
                    raise base.ElectionWarning("Line %d. Contest %s has name in all upper case letters." % (
                        element.sourceline, object_id))
        else:
            full_name = element.find("FullName")
            if full_name.find("Text") is not None:
                name = full_name.find("Text").text
                if name is not None and name == name.upper():
                    raise base.ElectionWarning("Line %d. Person %s has name in all upper case letters." % (
                        element.sourceline, object_id))


class ValidEnumerations(base.BaseRule):
    """Valid enumerations should not be encoded as 'OtherType'. 

    Elements that have valid enumerations should not be included 
    as 'OtherType'. Instead, the corresponding <Type> field 
    should include the actual valid enumeration value."""

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
                            eligible_elements.append(element.get("name"))
        return eligible_elements

    def check(self, element):
        type_element = element.find("Type")
        if type_element is not None and type_element.text == "other":
            other_type_element = element.find("OtherType")
            if other_type_element is not None:
                if other_type_element.text in self.valid_enumerations:
                    raise base.ElectionError(
                        "Line %d. Type of element %s is set to 'other' even though "
                        "'%s' is a valid enumeration" % (
                            element.sourceline, element.tag, other_type_element.text))


# To add new rules, create a new class, inherit the base rule
# then add it to this list
_RULES = [
    Schema,
    Encoding,
    HungarianStyleNotation,
    OptionalAndEmpty,
    LanguageCode,
    EmptyText,
    ElectoralDistrictOcdId,
    GpUnitOcdId,
    DuplicateGpUnits,
    OtherType,
    DuplicateID,
    ValidIDREF,
    UniqueLabel,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    ReusedCandidate,
    CoalitionParties,
    ProperBallotSelection,
    CandidateNotReferenced,
    CheckIdentifiers,
    DuplicateContestNames,
    CandidatesMissingPartyData,
    AllCaps,
    ValidEnumerations
]


def main():
    p = arg_parser()
    options = p.parse_args()
    if options.cmd == "list":
        print("Available rules are :")
        for rule in _RULES:
            print("\t" + rule.__name__ + " - " + rule.__doc__.split("\n")[0])
        return
    elif options.cmd == "validate":
        rules_to_check = []
        if options.i:
            rules_to_check = options.i
        elif options.e:
            rules_to_check = [x.__name__ for x in _RULES
                              if x.__name__ not in options.e]
        else:
            rules_to_check = [x.__name__ for x in _RULES]
        rule_options = {}
        if options.g:
            rule_options.setdefault("ElectoralDistrictOcdId", []).append(
                base.RuleOption("check_github", False))
            rule_options.setdefault("GpUnitOcdId", []).append(
                base.RuleOption("check_github", False))
        if options.c:
            rule_options.setdefault("ElectoralDistrictOcdId", []).append(
                base.RuleOption("country_code", options.c))
            rule_options.setdefault("GpUnitOcdId", []).append(
                base.RuleOption("country_code", options.c))
        if options.ocdid_file:
            rule_options.setdefault("ElectoralDistrictOcdId", []).append(
                base.RuleOption("local_file", options.ocdid_file))
            rule_options.setdefault("GpUnitOcdId", []).append(
                base.RuleOption("local_file", options.ocdid_file))
        rule_classes_to_check = [x for x in _RULES
                                 if x.__name__ in rules_to_check]
        registry = base.RulesRegistry(
            election_file=options.election_file, schema_file=options.xsd,
            rule_classes_to_check=rule_classes_to_check,
            rule_options=rule_options)
        found_errors = registry.check_rules()
        registry.print_exceptions(options.severity, options.verbose)
        # TODO other error codes?
        return found_errors


if __name__ == "__main__":
    main()

# pylint: disable=bad-indentation
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

import argparse
import io
import os.path
import pycountry
import requests
from lxml import etree
from election_results_xml_validator import base



def valid_file(parser, arg):
    """Check that the files provided exist."""
    if not os.path.exists(arg):
        parser.error("The file %s doesn't exist" % arg)
    else:
        return arg


def valid_rules(parser, arg):
    """Check that the listed rules exist"""
    invalid_rules = []
    rule_names = [x.__name__ for x in _RULES]
    for rule in arg.strip().split(","):
        if rule and rule not in rule_names:
            invalid_rules.append(rule)
    if invalid_rules:
        parser.error("The rule(s) %s do not exist" % ", ".join(invalid_rules))
    else:
        # TODO: Split this into something more readable
        return [x for x in arg.strip().split(",") if x]


def arg_parser():
    """Parser for command line arguments."""

    description = ("Script to validate that an elections results XML file "
                   "follows best practices")
    parser = argparse.ArgumentParser(description=description)
    subparsers = parser.add_subparsers(dest="cmd")
    parser_validate = subparsers.add_parser("validate")
    parser_validate.add_argument(
        "-x", "--xsd", help="NIST Voting Program XSD file path", required=True,
        metavar="xsd_file", type=lambda x: valid_file(parser, x))
    parser_validate.add_argument(
        "election_file", help="XML election file to be validated",
        metavar="election_file", type=lambda x: valid_file(parser, x))
    group = parser_validate.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "-i", help="Comma separated list of rules to be validated.",
        required=False, type=lambda x: valid_rules(parser, x))
    group.add_argument(
        "-e", help="Comma separated list of rules to be excluded.",
        required=False, type=lambda x: valid_rules(parser, x))
    parser_validate.add_argument(
        "-d", help="Display detailed error log. Defaults to aggregated",
        action="store_true", required=False)
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
            error_log = schema.error_log
            raise base.ElectionSchemaError(
                "The election file didn't validate against schema.", error_log)


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

    languages = []

    def __init__(self, election_tree, schema_file):
        super(LanguageCode, self).__init__(election_tree, schema_file)
        self.languages = [getattr(language, 'iso639_1_code', None)
                          for language in pycountry.languages]

    def elements(self):
        return ["Text"]

    def check(self, element):
        if "language" not in element.attrib:
            return
        elem_lang = element.get("language")
        if (not elem_lang or elem_lang not in self.languages or
            elem_lang.strip() == ""):
            raise base.ElectionError(
                "Line %d. %s is not a valid ISO 639 language code "% (
                    element.sourceline, elem_lang))

class EmptyText(base.BaseRule):
    """Check that Text elements are not empty."""

    def elements(self):
        return ["Text"]

    def check(self, element):
        if element.text is not None and element.text.strip() == "":
            raise base.ElectionWarning(
                "Line %d. %s is empty"% (
                    element.sourceline, element.tag))

class ElectoralDistrictOcdId(base.BaseRule):
    """GpUnit refered to by Contest.ElectoralDistrictId MUST have a valid OCD-ID.
    """
    ocds = []
    gpunits = []
    _OCDID_URL = (
        "https://raw.github.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
    )

    def __init__(self, election_tree, schema_file):
        super(ElectoralDistrictOcdId, self).__init__(election_tree, schema_file)
        self.ocds = self._get_ocd_data()
        self.gpunits = []
        for gpunit in self.election_tree.iterfind("//GpUnit"):
            self.gpunits.append(gpunit)

    def _get_ocd_data(self):
        """Checks if OCD file is in the curent directory, dowloads it if not."""
        cache_directory = os.path.expanduser("~/.cache")
        countries_file = cache_directory + "/country-us.csv"
        if not os.path.exists(countries_file):
            if not os.path.exists(cache_directory):
                os.makedirs(cache_directory)
            ocd_file = io.open(countries_file, "w")
            data = requests.get(self._OCDID_URL).text
            ocd_file.write(data)
            ocd_file.close()
        else:
            ocd_file = io.open(countries_file, "r")
            data = ocd_file.read()
            ocd_file.close()
        # TODO: Break this statement up into something more readable
        return [l.split(",")[0] for l in data.split("\n") if l is not ""]

    def elements(self):
        return ["ElectoralDistrictId"]

    def check(self, element):
        if element.getparent().tag != "Contest":
            return
        valid_ocd_id = False
        referenced_gpunit = None
        for gpunit in self.gpunits:
            if gpunit.get("objectId", None) == element.text:
                referenced_gpunit = gpunit
                for extern_id in gpunit.iter("ExternalIdentifier"):
                    id_type = extern_id.find("Type")
                    if id_type is not None and id_type.text == "ocd-id":
                        value = extern_id.find("Value")
                        if value.text in self.ocds:
                            valid_ocd_id = True
        if referenced_gpunit is None:
            raise base.ElectionError(
                "Line %d. The ElectoralDistrictId Element does not refer to a "
                "GpUnit. Every ElectoralDistrictId MUST reference a GpUnit" % (
                    element.sourceline))
        if not valid_ocd_id and referenced_gpunit is not None:
            raise base.ElectionError(
                "Line %d. The ElectoralDistrictId element refers to GpUnit on "
                "line %d that does not have a valid OCD ID" % (
                    element.sourceline, referenced_gpunit.sourceline))


class GpUnitOcdId(ElectoralDistrictOcdId):
    """Any GpUnit that is a geographic district SHOULD have a valid OCD-ID."""

    districts = ["borough", "city", "county", "municipality","state", "town",
                "township", "village"]

    def __init__(self, election_tree, schema_file):
        super(GpUnitOcdId, self).__init__(election_tree, schema_file)
        self.ocds = self._get_ocd_data()

    def elements(self):
        return ["GpUnit"]

    def check(self, element):
        if self.get_element_class(element) == "ReportingUnit":
            gpunit_type = element.find("Type")
            if gpunit_type.text in self.districts:
                for extern_id in element.iter("ExternalIdentifier"):
                    id_type = extern_id.find("Type")
                    if id_type is not None and id_type.text == "ocd-id":
                        value = extern_id.find("Value")
                        if value.text not in self.ocds:
                            raise base.ElectionWarning(
                                "The OCD ID %s defined on line %d is not "
                                "valid" % (value.text, value.sourceline))


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
        self.find_duplicates(collection)

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

    def find_duplicates(self, collection):
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
                if composing_id in self.leaf_nodes or composing_id not in self.defined_gpunits:
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
                    print "Non-leaf node %s has no children" % (middle_node)
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
    OtherType
]


def main():
    p = arg_parser()
    options = p.parse_args()
    if options.cmd == "list":
        print "Available rules are :"
        for rule in _RULES:
            print "\t", rule.__name__, " - ", rule.__doc__.split("\n")[0]
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
        rule_classes_to_check = [x for x in _RULES
                                     if x.__name__ in rules_to_check]
        registry = base.RulesRegistry(
            election_file = options.election_file, schema_file = options.xsd,
            rule_classes_to_check = rule_classes_to_check)
        found_errors = registry.check_rules()
        registry.print_exceptions(options.d)
        # TODO other error codes?
        return found_errors

if __name__ == "__main__":
    main()

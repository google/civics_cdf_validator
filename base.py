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

from lxml import etree

class ElectionException(Exception):
    """Base class for all the errors in this script."""

    def __init__(self, message):
        super(ElectionException, self).__init__()
        self.error_message = message

    def __str__(self):
        return repr(self.error_message)


class ElectionError(ElectionException):
    """An error that must be fixed, otherwise the feed will not be successfully
    processed."""

    description = "Error"


class ElectionSchemaError(ElectionError):
    """Special exception for schema errors."""

    description = "Schema Error"

    def __init__(self, message, error_log):
        super(ElectionSchemaError, self).__init__(message)
        self.error_log = error_log


class ElectionWarning(ElectionException):
    """An issue that should be fixed. It will not stop the feed from being
    successfully processed but may lead to undefined errors."""

    description = "Warning"


class ElectionInfo(ElectionException):
    """Information that user needs to know about following NIST best
    practices."""

    description = "Info"


class SchemaHandler(object):
    """Base class for anything that parses an XML schema document."""
    _XSCHEMA_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
    _XSCHEMA_INSTANCE_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
    _TYPE_ATTRIB = "{%s}type" % (_XSCHEMA_INSTANCE_NAMESPACE)

    def get_element_class(self, element):
        """Return the class of the element"""
        if element is None:
            return None
        if self._TYPE_ATTRIB not in element.attrib:
            return element.tag
        return element.attrib[self._TYPE_ATTRIB]

    def strip_schema_ns(self, element):
        """Remove namespace from lxml element tag."""
        tag = element.tag
        if not hasattr(tag, "startswith"):
            # Comment tags return a function
            return None
        if tag.startswith("{%s}" % self._XSCHEMA_NAMESPACE):
            return tag[len("{%s}" % self._XSCHEMA_NAMESPACE):]
        return tag


class BaseRule(SchemaHandler):
    """Base class for rules."""

    def __init__(self, election_tree, schema_file):
        super(BaseRule, self).__init__()
        self.election_tree = election_tree
        self.schema_file = schema_file

    def elements(self):
        """Return a list of all the elements this rule checks."""
        raise NotImplementedError

    def check(self, element):
        """Given an element, check whether it implements best practices."""
        raise NotImplementedError


class TreeRule(BaseRule):
    """Rule that checks entire tree."""

    def elements(self):
        return ["tree"]


class RulesRegistry(SchemaHandler):
    """Registry of rules and the elements they check"""

    election_file = None
    schema_file = None
    rule_classes_to_check = None
    registry = {}
    exceptions = {}
    exception_counts = {}
    exception_rule_counts = {}
    total_count = 0

    def __init__(self, election_file, schema_file, rule_classes_to_check):
        self.election_file = election_file
        self.schema_file = schema_file
        self.rule_classes_to_check = rule_classes_to_check
        for e_type in [ElectionError, ElectionWarning, ElectionInfo]:
            self.exceptions[e_type] = dict()
            self.exception_counts[e_type] = 0
            self.exception_rule_counts[e_type] = dict()

    def register_rules(self, election_tree):
        """Register all the rules to be checked.

        Returns:
            A dictionary of elements and rules that check each element

        Args:
            election_tree: election tree to be checked
        """
        for rule in self.rule_classes_to_check:
            rule_instance = rule(election_tree, self.schema_file)
            for element in rule_instance.elements():
                if element in self.registry:
                    self.registry[element].append(rule_instance)
                else:
                    self.registry[element] = [rule_instance]

    def exception_handler(self, rule, exception):
        for e_type in self.exceptions.keys():
            if issubclass(exception.__class__, e_type):
                if rule.__class__ not in self.exceptions[e_type]:
                    self.exceptions[e_type][rule.__class__] = []
                    self.exception_rule_counts[e_type][rule.__class__] = 0
                self.exceptions[e_type][rule.__class__].append(exception)
                error_count = 1
                if hasattr(exception, "error_log"):
                    error_count = len(exception.error_log)
                self.exception_counts[e_type] += error_count
                self.exception_rule_counts[e_type][rule.__class__] += error_count
                self.total_count += error_count

    def print_exceptions(self, detailed):
        if self.total_count == 0:
            print "Validation completed with no warnings/errors."
            return
        # Descend from most severe to least severe issues.
        for e_type in [ElectionError, ElectionWarning, ElectionInfo]:
            suffix = ""
            if self.exception_counts[e_type] == 0:
                continue
            elif self.exception_counts[e_type] > 1:
                suffix = "s"
            e_type_name = e_type.description
            print "{0:6d} {1} message{2} found".format(
                self.exception_counts[e_type], e_type_name, suffix)
            # Within the error severity, sort from most common to least common.
            for rule_class in sorted(
                self.exceptions[e_type].keys(),
                key=lambda rclass: self.exception_rule_counts[e_type][rclass],
                reverse=True):
                rule_class_name = rule_class.__name__
                rule_count = self.exception_rule_counts[e_type][rule_class]
                rule_suffix = ""
                if rule_count > 1:
                    rule_suffix = "s"
                print "{0:10d} {1} {2} message{3}".format(
                    rule_count, rule_class_name, e_type_name, rule_suffix)
                if detailed:
                    for exception in self.exceptions[e_type][rule_class]:
                        if hasattr(exception, "error_log"):
                             for error in exception.error_log:
                                    print "        %d: %s" % (
                                        error.line, error.message.encode("utf-8"))
                        else:
                            print "        %s" % exception

    def check_rules(self):
        """Checks all rules.

        Returns:
            0 if no warnings or errors are generated. 1 otherwise.

        Args:
            detailed:if True prints detailed error messages
        """

        try:
            election_tree = etree.parse(self.election_file)
        except etree.LxmlError as e:
            print "Fatal Error. XML file could not be parsed. %s" % e
            return 1
        self.register_rules(election_tree)
        for rule in self.registry.get("tree", []):
            try:
                rule.check()
            except ElectionException as e:
                self.exception_handler(rule, e)
        for event, element in etree.iterwalk(election_tree, events=("end",)):
            tag = self.get_element_class(element)
            if not tag or tag not in self.registry.keys():
                continue
            for element_rule in self.registry[tag]:
                try:
                    element_rule.check(element)
                except ElectionException as e:
                    self.exception_handler(element_rule, e)
        if self.total_count == 0:
            return 0
        else:
            return 1


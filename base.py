"""Copyright 2016 Google Inc.

All Rights Reserved.
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
from lxml import etree


class ElectionException(Exception):
  """Base class for all the errors in this script."""
  error_message = None
  description = None
  error_log = []

  def __init__(self, message):
    super(ElectionException, self).__init__()
    self.error_message = message

  def __str__(self):
    return repr(self.error_message)


class ElectionError(ElectionException):
  """An error that prevents the feed from being processed successfully."""

  description = "Error"


class ElectionTreeError(ElectionError):
  """Special exception for Tree Rules."""

  def __init__(self, message, error_log):
    super(ElectionTreeError, self).__init__(message)
    self.error_log = error_log


class ElectionWarning(ElectionException):
  """An issue that should be fixed.

  It will not stop the feed from being successfully processed but may lead to
  undefined errors.
  """

  description = "Warning"


class ElectionInfo(ElectionException):
  """Information that user needs to know about following XML best practices."""

  description = "Info"


class ErrorLogEntry(object):
  line = None
  message = None

  def __init__(self, line, message):
    self.line = line
    self.message = message


class SchemaHandler(object):
  """Base class for anything that parses an XML schema document."""
  _XSCHEMA_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
  _XSCHEMA_INSTANCE_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
  _TYPE_ATTRIB = "{%s}type" % (_XSCHEMA_INSTANCE_NAMESPACE)

  def get_element_class(self, element):
    """Return the class of the element."""
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

  def get_elements_by_class(self, element, element_name):
    """Searches for all tags under element of type element_name."""
    # find all the tags that match element_name
    elements = element.findall(".//" + element_name)
    # next find all elements where the type is element_name
    elements += element.xpath(
        ".//*[@xsi:type ='%s']" % (element_name),
        namespaces={"xsi": self._XSCHEMA_INSTANCE_NAMESPACE})
    return elements


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

  def set_option(self, option):
    """Used to set commandline options for the rule.

    The rule must have the option_name attribute, otherwise raise an
    exception.
    """
    if not hasattr(self, option.option_name):
      raise ElectionException("Invalid attribute set")
    setattr(self, option.option_name, option.option_value)

  def setup(self):
    """Perform any rule specific setup before checking."""


class TreeRule(BaseRule):
  """Rule that checks entire tree."""

  def elements(self):
    return ["tree"]

  def check(self):
    """Checks entire tree."""


class RuleOption(object):
  class_name = None
  option_name = None
  option_value = None

  def __init__(self, option_name, option_value):
    self.option_name = option_name
    self.option_value = option_value


class RulesRegistry(SchemaHandler):
  """Registry of rules and the elements they check."""

  _SEVERITIES = (ElectionInfo, ElectionWarning, ElectionError)

  def __init__(self, election_file, schema_file, rule_classes_to_check,
               rule_options):
    self.election_file = election_file
    self.schema_file = schema_file
    self.rule_classes_to_check = rule_classes_to_check
    self.rule_options = rule_options
    self.registry = {}
    self.exceptions = {}
    self.exception_counts = {}
    self.exception_rule_counts = {}
    self.total_count = 0

    for e_type in self._SEVERITIES:
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
      if rule.__name__ in self.rule_options.keys():
        for option in self.rule_options[rule.__name__]:
          rule_instance.set_option(option)
      rule_instance.setup()
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
        if exception.error_log:
          error_count = len(exception.error_log)
        self.exception_counts[e_type] += error_count
        self.exception_rule_counts[e_type][rule.__class__] += error_count
        self.total_count += error_count

  def print_exceptions(self, severity, verbose):
    """Print exceptions in decreasing order of severity."""
    if not severity:
      severity = 0
    elif severity > len(self._SEVERITIES):
      severity = len(self._SEVERITIES) - 1
    exception_types = self._SEVERITIES[severity:]
    if self.total_count == 0:
      print("Validation completed with no warnings/errors.")
      return
    for e_type in reversed(exception_types):
      suffix = ""
      if self.exception_counts[e_type] == 0:
        continue
      elif self.exception_counts[e_type] > 1:
        suffix = "s"
      e_type_name = e_type.description
      print("{0:6d} {1} message{2} found".format(self.exception_counts[e_type],
                                                 e_type_name, suffix))
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
        print("{0:10d} {1} {2} message{3}".format(rule_count, rule_class_name,
                                                  e_type_name, rule_suffix))
        if verbose:
          for exception in self.exceptions[e_type][rule_class]:
            if exception.error_log:
              for error in exception.error_log:
                if error.line is not None:
                  print(" " * 14 +
                        "Line {0}: {1}".format(error.line, error.message))
                else:
                  print(" " * 14 + "{0}".format(error.message))
            else:
              print(" " * 14 + "{0}".format(exception))

  def check_rules(self):
    """Checks all rules."""
    try:
      election_tree = etree.parse(self.election_file)
    except etree.LxmlError as e:
      print("Fatal Error. XML file could not be parsed. {}".format(e))
      self.exception_counts[ElectionError] += 1
      self.total_count += 1
      return
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

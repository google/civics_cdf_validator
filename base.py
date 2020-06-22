"""Copyright 2020 Google Inc.

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

import datetime

from civics_cdf_validator import loggers
from civics_cdf_validator import stats
from lxml import etree


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

  def __init__(self, election_tree, schema_tree):
    super(BaseRule, self).__init__()
    self.election_tree = election_tree
    self.schema_tree = schema_tree

  def elements(self):
    """Return a list of all the elements this rule checks."""
    raise NotImplementedError

  def check(self, element):
    """Given an element, check whether it implements best practices."""
    raise NotImplementedError

  def set_option(self, option):
    """Used to set commandline options for the rule.

    Args:
      option: commandline option object.

    Raises:
      ElectionException: the rule must have the option_name attribute.
    """
    if not hasattr(self, option.option_name):
      raise loggers.ElectionException("Invalid attribute set")
    setattr(self, option.option_name, option.option_value)

  def setup(self):
    """Perform any rule specific setup before checking."""


class TreeRule(BaseRule):
  """Rule that checks entire tree."""

  def elements(self):
    return ["tree"]

  def check(self):
    """Checks entire tree."""


class ValidReferenceRule(TreeRule):
  """Rule that makes sure reference values are properly defined."""

  def __init__(self, election_tree, schema_tree, missing_element="data"):
    super(ValidReferenceRule, self).__init__(election_tree, schema_tree)
    self.missing_element = missing_element

  def _gather_reference_values(self):
    """Collect a set of all values that are referencing a pre-defined value.

    Ex: A party leader ID should reference an ID from a PersonCollection.
    This method should return a set of all party leader IDs.
    """
    raise NotImplementedError

  def _gather_defined_values(self):
    """Collect a set of the pre-defined values that are being referenced.

    Ex: A party leader ID should reference an ID from a PersonCollection.
    This method should return a set of all PersonIDs from the PersonCollection.
    """
    raise NotImplementedError

  def check(self):
    reference_ids = self._gather_reference_values()
    defined_ids = self._gather_defined_values()
    invalid_references = reference_ids - defined_ids

    if invalid_references:
      raise loggers.ElectionError.from_message(
          ("No defined {} for {} found in the feed.".format(
              self.missing_element, ", ".join(invalid_references))))


class DateRule(BaseRule):
  """Base rule used for date validations.

  When validating dates, this rule can be used to gather start and
  end date values.
  """

  def __init__(self, election_tree, schema_file):
    super(DateRule, self).__init__(election_tree, schema_file)
    self.today = datetime.datetime.now().date()
    self.start_elem = None
    self.start_date = None
    self.end_elem = None
    self.end_date = None
    self.error_log = []

  def reset_instance_vars(self):
    """Reset instance variables to initial state.

    Due to ordered procedure of validator, instance vars created in init
    are not getting reset when same rule is run on different elements.
    """
    self.start_elem = None
    self.start_date = None
    self.end_elem = None
    self.end_date = None
    self.error_log = []

  def gather_dates(self, element):
    """Gather StartDate and EndDate values for the provided element.

    An election element should have a start and end date in the desired format.
    These dates should be extracted and set as instance variables to be used
    in validation checks.

    Args:
      element: A parent element that contains StartDate and EndDate children.

    Raises:
      ElectionError: dates need to be properly formatted.
    """
    error_log = []

    self.start_elem = element.find("StartDate")
    if self.start_elem is not None and self.start_elem.text is not None:
      try:
        self.start_date = datetime.datetime.strptime(
            self.start_elem.text, "%Y-%m-%d").date()
      except ValueError:
        error_message = "The StartDate text should be of the format yyyy-mm-dd"
        error_log.append(loggers.LogEntry(error_message, [self.start_elem]))

    self.end_elem = element.find("EndDate")
    if self.end_elem is not None and self.end_elem.text is not None:
      try:
        self.end_date = datetime.datetime.strptime(
            self.end_elem.text, "%Y-%m-%d").date()
      except ValueError:
        error_message = "The EndDate text should be of the format yyyy-mm-dd"
        error_log.append(loggers.LogEntry(error_message, [self.end_elem]))

    if error_log:
      raise loggers.ElectionError(error_log)

  def check_for_date_not_in_past(self, date, date_elem):
    delta = (date - self.today).days
    if delta < 0:
      error_message = """The date {} is in the past.""".format(date)
      self.error_log.append(loggers.LogEntry(error_message, [date_elem]))

  def check_end_after_start(self):
    start_end_delta = (self.end_date - self.start_date).days
    if start_end_delta < 0:
      error_message = """The dates (start: {}, end: {}) are invalid.
      The end date must be the same or after the start date.""".format(
          self.start_date, self.end_date)
      self.error_log.append(loggers.LogEntry(error_message, [self.end_elem]))


class MissingFieldRule(BaseRule):
  """Check for required fields for given entity types and field names."""

  def get_severity(self):
    """Return 0 for Info, 1 for Warning, or 2 for Error."""
    raise NotImplementedError

  def element_field_mapping(self):
    """Return a map of element tag to list of required fields."""
    raise NotImplementedError

  def setup(self):
    severity = self.get_severity()
    handled_severities = loggers.handled_severities()
    if (severity > len(handled_severities)
        or severity < 0):
      raise Exception(("Invalid severity. Must be either 0 (Info), "
                       "1 (Warning), or 2 (Error)"))
    self.exception = handled_severities[severity]

  def elements(self):
    return list(self.element_field_mapping().keys())

  def check(self, element):
    error_log = []

    required_field_tags = self.element_field_mapping()[element.tag]
    for field_tag in required_field_tags:
      required_field = element.find(field_tag)
      if (required_field is None or required_field.text is None
          or not required_field.text.strip()):
        error_log.append(loggers.LogEntry(
            "The element {} is missing field {}.".format(element.tag,
                                                         field_tag), [element]))

    if error_log:
      raise self.exception(error_log)


class RuleOption(object):
  class_name = None
  option_name = None
  option_value = None

  def __init__(self, option_name, option_value):
    self.option_name = option_name
    self.option_value = option_value


class RulesRegistry(SchemaHandler):
  """Registry of rules and the elements they check."""

  _TOP_LEVEL_ENTITIES = set(
      ["Party", "GpUnit", "Office", "Person", "Candidate", "Contest"])

  def __init__(self, election_file, schema_file, rule_classes_to_check,
               rule_options):
    self.election_file = election_file
    self.schema_file = schema_file
    self.rule_classes_to_check = rule_classes_to_check
    self.rule_options = rule_options
    self.registry = {}
    self.exceptions_wrapper = loggers.ExceptionListWrapper()
    self.election_tree = None

  def register_rules(self):
    """Register all the rules to be checked.

    Returns:
      A dictionary of elements and rules that check each element
    """
    for rule in self.rule_classes_to_check:
      rule_instance = rule(self.election_tree, self.schema_tree)
      if rule.__name__ in self.rule_options.keys():
        for option in self.rule_options[rule.__name__]:
          rule_instance.set_option(option)
      rule_instance.setup()
      for element in set(rule_instance.elements()):
        if element in self.registry:
          self.registry[element].append(rule_instance)
        else:
          self.registry[element] = [rule_instance]

  def print_exceptions(self, severity, verbose):
    self.exceptions_wrapper.print_exceptions(severity, verbose)

  def count_stats(self):
    """Aggregates the counts for each top level entity."""
    if self.election_tree:
      # Find the top-level entities.
      entity_path_str = ".//{0}Collection//{1}"
      print("\n" + " " * 5 + "Entity and Attribute Counts:")
      for entity_name in stats.ENTITY_STATS:
        entity_instances = self.election_tree.findall(
            entity_path_str.format(entity_name, entity_name))
        if entity_instances:
          # If top-level entity exists, instantiate a stat counter with total.
          entity_stats = stats.ENTITY_STATS[entity_name](len(entity_instances))
          # Then for each possible nested attribute, add count for those.
          for attr in entity_stats.attribute_counts:
            for instance in entity_instances:
              entity_stats.increment_attribute(
                  attr, len(instance.findall(".//{}".format(attr))))
          print(entity_stats)

  def check_rules(self):
    """Checks all rules."""
    try:
      self.schema_tree = etree.parse(self.schema_file)
      self.election_tree = etree.parse(self.election_file)
    except etree.LxmlError as e:
      exp = loggers.ElectionFatal.from_message(
          "Fatal Error. XML file could not be parsed. {}".format(e))
      self.exceptions_wrapper.exception_handler(exp)
      return
    self.register_rules()
    for rule in self.registry.get("tree", []):
      try:
        rule.check()
      except loggers.ElectionException as e:
        rule_name = rule.__class__.__name__
        self.exceptions_wrapper.exception_handler(e, rule_name)
    for _, element in etree.iterwalk(self.election_tree, events=("end",)):
      tag = self.get_element_class(element)

      if not tag or tag not in self.registry:
        continue

      for element_rule in self.registry[tag]:
        try:
          element_rule.check(element)
        except loggers.ElectionException as e:
          rule_name = element_rule.__class__.__name__
          self.exceptions_wrapper.exception_handler(e, rule_name)

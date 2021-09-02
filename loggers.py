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

import copy


class LogEntry(object):
  """This class contains needed information for user output."""

  def __init__(self, message, elements=None, lines=None):
    self.message = message
    self.elements = elements
    if lines is not None:
      self.lines = lines
    elif elements is not None:
      self.lines = []
      for element in elements:
        if(element is not None and hasattr(element, "sourceline")
           and element.sourceline is not None):
          self.lines.append(element.sourceline)
    else:
      self.lines = None


# pylint: disable=g-bad-exception-name
class ElectionException(Exception):
  """Base class for all the exceptions in this script."""
  description = None

  def __init__(self, log_entry):
    super(ElectionException, self).__init__()
    if isinstance(log_entry, list):
      self.log_entry = log_entry
    else:
      self.log_entry = [log_entry]

  @classmethod
  def from_message(cls, message, elements=None, lines=None):
    return cls(LogEntry(message, elements, lines))


class ElectionFatal(ElectionException):
  """An Fatal that prevents the feed from being processed successfully."""

  description = "Fatal"


class ElectionError(ElectionException):
  """An error that prevents the feed from being processed successfully."""

  description = "Error"


# pylint: disable=g-bad-exception-name
class ElectionWarning(ElectionException):
  """An issue that should be fixed.

  It will not stop the feed from being successfully processed but may lead to
  undefined errors.
  """

  description = "Warning"


# pylint: disable=g-bad-exception-name
class ElectionInfo(ElectionException):
  """Information that user needs to know about following XML best practices."""

  description = "Info"


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


class ExceptionListWrapper:
  """This provide helpers to manage a list of ElectionException.

  This class contains a list of ElectionExceptions. It provides a handler to
  enrich the list and manage the validator output depending on the user choice
  for severity. So, as an example if the user selects a severity warning,
  ElectionWarning, ElectionError log_entry will be displayed and ElectionInfo
  will be skipped. We print the selected severity + other Exception types with
  higher severity.
  """

  SUPPORTED_SEVERITIES = (ElectionInfo,
                          ElectionWarning,
                          ElectionError,
                          ElectionFatal)

  def __init__(self):
    self._rules_exc_logs = dict()
    for e_type in self.SUPPORTED_SEVERITIES:
      self._rules_exc_logs[e_type] = dict()

  def exception_handler(self, exception, rule_name="No rule"):
    """Gather log entry counts by type, class, and total."""
    for e_type in self._rules_exc_logs:
      if issubclass(exception.__class__, e_type):
        if rule_name not in self._rules_exc_logs[e_type]:
          self._rules_exc_logs[e_type][rule_name] = []
        self._rules_exc_logs[e_type][rule_name].extend(exception.log_entry)

  def _select_exception_types(self, severity):
    if not severity:
      severity = 0
    elif severity > len(self.SUPPORTED_SEVERITIES):
      severity = len(self.SUPPORTED_SEVERITIES) - 1
    return self.SUPPORTED_SEVERITIES[severity:]

  def count_logs_with_exception_type(self, e_type):
    exception_count = 0
    for log_list in list(self._rules_exc_logs[e_type].values()):
      exception_count += len(log_list)
    return exception_count

  def _print_exception_type_summary(self, e_type, count_exception):
    suffix = ""
    if count_exception > 1:
      suffix = "s"
    print("{0:6d} {1} message{2} found".format(count_exception,
                                               e_type.description, suffix))

  def _print_rule_exception_summary(self, e_type, rule_name):
    rule_count = len(self._rules_exc_logs[e_type][rule_name])
    rule_suffix = ""
    if rule_count > 1:
      rule_suffix = "s"
    print("{0:10d} {1} {2} message{3}".format(rule_count, rule_name,
                                              e_type.description, rule_suffix))

  def _print_exception_log(self, log_entry):
    if log_entry.lines is not None:
      print(" " * 14 + "Lines %s :" % log_entry.lines)
    if log_entry.elements is not None:
      print(" " * 15 + "Affected elements :")
      for element in log_entry.elements:
        print(" " * 16 + get_parent_hierarchy_object_id_str(element))
    print(" " * 18 + "* {0}".format(log_entry.message))

  def get_all_exceptions(self):
    return copy.deepcopy(self._rules_exc_logs)

  def print_exceptions(self, severity, verbose):
    """Print exceptions in decreasing order of severity."""
    exception_types = self._select_exception_types(severity)
    for e_type in reversed(exception_types):
      exception_count = self.count_logs_with_exception_type(e_type)
      self._print_exception_type_summary(e_type, exception_count)
      if exception_count == 0:
        continue
      # pylint: disable=cell-var-from-loop
      # Within the error severity, sort from most common to least common.
      for rule_name in sorted(
          self._rules_exc_logs[e_type].keys(),
          key=lambda rclass: len(self._rules_exc_logs[e_type][rclass]),
          reverse=True):
        self._print_rule_exception_summary(e_type, rule_name)
        if verbose:
          for log_entry in self._rules_exc_logs[e_type][rule_name]:
            self._print_exception_log(log_entry)


def handled_severities():
  return ExceptionListWrapper.SUPPORTED_SEVERITIES


def supported_severities_mapping():
  exp_severity_map = {}
  for n in range(len(ExceptionListWrapper.SUPPORTED_SEVERITIES)):
    exp_severity_map[
        ExceptionListWrapper.SUPPORTED_SEVERITIES[n].description.lower()] = n
  return exp_severity_map


def severities_names():
  names = []
  for exp in ExceptionListWrapper.SUPPORTED_SEVERITIES:
    names.append(exp.description.lower())
  return names


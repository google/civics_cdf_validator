# -*- coding: utf-8 -*-
"""Unit test for loggers.py."""

import contextlib
import io

from absl.testing import absltest
from civics_cdf_validator import loggers
from lxml import etree


class ParentHierarchyObjectIdStrTest(absltest.TestCase):

  def test_no_parent_hierarchy_returns_tag(self):
    uri = "<Uri>www.facebook.com/michael_scott</Uri>"
    uri_element = etree.fromstring(uri)
    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Uri", actual_value)

  def test_hierarchy_stops_at_object_id(self):
    election_feed = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per-1">
            <ContactInformation>
              <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
              </Uri>
            </ContactInformation>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find(
        "PersonCollection/Person/ContactInformation/Uri"
    )

    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Person:per-1 > ContactInformation > Uri", actual_value)

  def test_hierarchy_goes_to_root_when_no_object_id(self):
    election_feed = """
      <ElectionReport>
        <Election>
          <ContactInformation>
            <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
            </Uri>
          </ContactInformation>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find("Election/ContactInformation/Uri")

    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual(
        "ElectionReport > Election > ContactInformation > Uri", actual_value
    )


class LogEntryTest(absltest.TestCase):

  def test_lines_given_uses_given_lines(self):
    party = etree.fromstring('<Party objectId="par-fake"/>')

    log_entry = loggers.LogEntry("Fake message.", [party], [42])

    self.assertEqual([42], log_entry.lines)

  def test_elements_given_collects_source_lines(self):
    election_feed = """<ElectionReport>
  <Party objectId="par-fake-1"/>
  <Party objectId="par-fake-2"/>
</ElectionReport>"""
    election_tree = etree.fromstring(election_feed)
    parties = election_tree.findall("Party")

    log_entry = loggers.LogEntry("Fake message.", parties)

    self.assertEqual([2, 3], log_entry.lines)
    self.assertEqual(parties, log_entry.elements)

  def test_elements_without_source_lines_are_skipped(self):
    party = etree.Element("Party")

    log_entry = loggers.LogEntry("Fake message.", [None, party])

    self.assertEqual([], log_entry.lines)

  def test_no_elements_or_lines_sets_lines_to_none(self):
    log_entry = loggers.LogEntry("Fake message.")

    self.assertIsNone(log_entry.lines)
    self.assertIsNone(log_entry.elements)


class ExceptionListWrapperTest(absltest.TestCase):

  def _print_exceptions(self, exceptions_wrapper, severity, verbose):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      exceptions_wrapper.print_exceptions(severity, verbose)
    return output.getvalue()

  def test_exception_handler_groups_entries_by_severity_and_rule(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    first_error = loggers.ElectionError.from_message("First error.")
    second_error = loggers.ElectionError.from_message("Second error.")
    warning = loggers.ElectionWarning.from_message("Fake warning.")

    exceptions_wrapper.exception_handler(first_error, "FakeRule")
    exceptions_wrapper.exception_handler(second_error, "FakeRule")
    exceptions_wrapper.exception_handler(warning, "OtherFakeRule")
    all_exceptions = exceptions_wrapper.get_all_exceptions()

    error_messages = [
        log_entry.message
        for log_entry in all_exceptions[loggers.ElectionError]["FakeRule"]
    ]
    warning_messages = [
        log_entry.message
        for log_entry in all_exceptions[loggers.ElectionWarning][
            "OtherFakeRule"
        ]
    ]
    self.assertEqual(["First error.", "Second error."], error_messages)
    self.assertEqual(["Fake warning."], warning_messages)
    self.assertEqual({}, all_exceptions[loggers.ElectionInfo])
    self.assertEqual({}, all_exceptions[loggers.ElectionFatal])

  def test_exception_handler_without_rule_name_uses_default_name(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    fatal = loggers.ElectionFatal.from_message("Fake fatal.")

    exceptions_wrapper.exception_handler(fatal)
    all_exceptions = exceptions_wrapper.get_all_exceptions()

    self.assertEqual(["No rule"], list(all_exceptions[loggers.ElectionFatal]))

  def test_get_all_exceptions_returns_independent_copy(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    error = loggers.ElectionError.from_message("Fake error.")
    exceptions_wrapper.exception_handler(error, "FakeRule")

    all_exceptions = exceptions_wrapper.get_all_exceptions()
    all_exceptions[loggers.ElectionError]["FakeRule"].clear()

    self.assertEqual(
        1,
        exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionError
        ),
    )

  def test_count_logs_with_exception_type_counts_entries_across_rules(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    multiple_errors = loggers.ElectionError([
        loggers.LogEntry("First error."),
        loggers.LogEntry("Second error."),
    ])
    other_error = loggers.ElectionError.from_message("Third error.")
    exceptions_wrapper.exception_handler(multiple_errors, "FakeRule")
    exceptions_wrapper.exception_handler(other_error, "OtherFakeRule")

    error_count = exceptions_wrapper.count_logs_with_exception_type(
        loggers.ElectionError
    )

    self.assertEqual(3, error_count)

  def test_print_exceptions_without_severity_prints_all_types(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()

    output = self._print_exceptions(exceptions_wrapper, None, False)

    self.assertEqual(
        "     0 Fatal message found\n"
        "     0 Error message found\n"
        "     0 Warning message found\n"
        "     0 Info message found\n",
        output,
    )

  def test_print_exceptions_with_error_severity_prints_error_and_fatal(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()

    output = self._print_exceptions(exceptions_wrapper, 2, False)

    self.assertEqual(
        "     0 Fatal message found\n     0 Error message found\n", output
    )

  def test_print_exceptions_with_too_high_severity_prints_only_fatal(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()

    output = self._print_exceptions(exceptions_wrapper, 10, False)

    self.assertEqual("     0 Fatal message found\n", output)

  def test_print_exceptions_with_severity_just_past_fatal_prints_only_fatal(
      self,
  ):
    exceptions_wrapper = loggers.ExceptionListWrapper()

    output = self._print_exceptions(exceptions_wrapper, 4, False)

    self.assertEqual("     0 Fatal message found\n", output)

  def test_print_exceptions_single_entry_uses_singular_message(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    fatal = loggers.ElectionFatal.from_message("Fake fatal.")
    exceptions_wrapper.exception_handler(fatal, "FakeRule")

    output = self._print_exceptions(exceptions_wrapper, 3, False)

    self.assertEqual(
        "     1 Fatal message found\n         1 FakeRule Fatal message\n",
        output,
    )

  def test_print_exceptions_multiple_entries_uses_plural_messages(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    first_fatal = loggers.ElectionFatal.from_message("First fatal.")
    second_fatal = loggers.ElectionFatal.from_message("Second fatal.")
    exceptions_wrapper.exception_handler(first_fatal, "FakeRule")
    exceptions_wrapper.exception_handler(second_fatal, "FakeRule")

    output = self._print_exceptions(exceptions_wrapper, 3, False)

    self.assertEqual(
        "     2 Fatal messages found\n         2 FakeRule Fatal messages\n",
        output,
    )

  def test_print_exceptions_sorts_rules_by_descending_count(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    exceptions_wrapper.exception_handler(
        loggers.ElectionFatal.from_message("First fatal."), "FakeRule"
    )
    exceptions_wrapper.exception_handler(
        loggers.ElectionFatal.from_message("Second fatal."), "OtherFakeRule"
    )
    exceptions_wrapper.exception_handler(
        loggers.ElectionFatal.from_message("Third fatal."), "OtherFakeRule"
    )

    output = self._print_exceptions(exceptions_wrapper, 3, False)

    self.assertEqual(
        "     3 Fatal messages found\n"
        "         2 OtherFakeRule Fatal messages\n"
        "         1 FakeRule Fatal message\n",
        output,
    )

  def test_print_exceptions_with_empty_entry_list_skips_rule_summary(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    exceptions_wrapper.exception_handler(loggers.ElectionFatal([]), "FakeRule")

    output = self._print_exceptions(exceptions_wrapper, 3, True)

    self.assertEqual("     0 Fatal message found\n", output)

  def test_print_exceptions_verbose_prints_lines_elements_and_message(self):
    election_feed = """<ElectionReport>
  <Party objectId="par-fake"/>
</ElectionReport>"""
    party = etree.fromstring(election_feed).find("Party")
    exceptions_wrapper = loggers.ExceptionListWrapper()
    fatal = loggers.ElectionFatal.from_message("Fake fatal.", [party])
    exceptions_wrapper.exception_handler(fatal, "FakeRule")

    output = self._print_exceptions(exceptions_wrapper, 3, True)

    self.assertEqual(
        "     1 Fatal message found\n"
        "         1 FakeRule Fatal message\n"
        "              Lines [2] :\n"
        "               Affected elements :\n"
        "                Party:par-fake\n"
        "                  * Fake fatal.\n",
        output,
    )

  def test_print_exceptions_verbose_message_only_prints_message(self):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    fatal = loggers.ElectionFatal.from_message("Fake fatal.")
    exceptions_wrapper.exception_handler(fatal, "FakeRule")

    output = self._print_exceptions(exceptions_wrapper, 3, True)

    self.assertEqual(
        "     1 Fatal message found\n"
        "         1 FakeRule Fatal message\n"
        "                  * Fake fatal.\n",
        output,
    )


class SeveritiesTest(absltest.TestCase):

  def test_handled_severities_returns_increasing_severities(self):
    severities = loggers.handled_severities()

    self.assertEqual(
        (
            loggers.ElectionInfo,
            loggers.ElectionWarning,
            loggers.ElectionError,
            loggers.ElectionFatal,
        ),
        severities,
    )

  def test_supported_severities_mapping_maps_names_to_levels(self):
    mapping = loggers.supported_severities_mapping()

    self.assertEqual({"info": 0, "warning": 1, "error": 2, "fatal": 3}, mapping)

  def test_severities_names_returns_lowercase_names(self):
    names = loggers.severities_names()

    self.assertEqual(["info", "warning", "error", "fatal"], names)


if __name__ == "__main__":
  absltest.main()

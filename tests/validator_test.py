# -*- coding: utf-8 -*-
"""Unit test for validator.py."""

import argparse
from collections.abc import Sequence
import contextlib
import hashlib
import io
import sys
from typing import Any, BinaryIO
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
from civics_cdf_validator import validator
from civics_cdf_validator import version
from civics_cdf_validator.rulesets import common_rules
from lxml import etree

_FAKE_XSD = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
_FAKE_OCD_ID_CSV = "id,name\nocd-division/country:us,United States\n"
_FEED_WITH_ENGLISH_NAME = """
  <ElectionReport>
    <PartyCollection>
      <Party objectId="par-fake">
        <Name>
          <Text language="en">Fake Party</Text>
        </Name>
      </Party>
    </PartyCollection>
  </ElectionReport>
"""
_ALL_LANGUAGES_DOC_FIRST_LINE = (
    "Verify that required languages are present in Text fields."
)
_FAKE_OCD_ID_LIST = ["ocd-division/country:us"]


def _fake_rules_work(options: argparse.Namespace | None) -> str:
  """Stands in for profiled validation work and returns a fixed result."""
  del options
  return "fake-result"


class ValidatePathTest(absltest.TestCase):

  def test_existing_path_returns_path(self):
    parser = argparse.ArgumentParser(prog="fake_validator")
    existing_file = self.create_tempfile(content="fake")

    result = validator._validate_path(parser, existing_file.full_path)

    self.assertEqual(result, existing_file.full_path)

  def test_missing_path_exits_with_error_message(self):
    parser = argparse.ArgumentParser(prog="fake_validator")
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        validator._validate_path(parser, "/fake/missing-file.xml")

    self.assertIn(
        "The file path for /fake/missing-file.xml doesn't exist",
        stderr.getvalue(),
    )


class ValidateRulesTest(absltest.TestCase):

  def test_existing_rules_returns_stripped_rule_names(self):
    parser = argparse.ArgumentParser(prog="fake_validator")

    result = validator._validate_rules(
        parser, " AllLanguages,ValidEnumerations "
    )

    self.assertEqual(result, ["AllLanguages", "ValidEnumerations"])

  def test_trailing_comma_keeps_empty_rule_name(self):
    parser = argparse.ArgumentParser(prog="fake_validator")

    result = validator._validate_rules(parser, "AllLanguages,")

    self.assertEqual(result, ["AllLanguages", ""])

  def test_unknown_rules_exits_listing_unknown_rules(self):
    parser = argparse.ArgumentParser(prog="fake_validator")
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        validator._validate_rules(
            parser, "FakeRuleOne,AllLanguages,FakeRuleTwo"
        )

    self.assertIn(
        "The rule(s) FakeRuleOne, FakeRuleTwo do not exist", stderr.getvalue()
    )


class ValidateSeverityTest(absltest.TestCase):

  def test_known_severity_returns_severity_index(self):
    parser = argparse.ArgumentParser(prog="fake_validator")

    result = validator._validate_severity(parser, " Error ")

    self.assertEqual(result, 2)

  def test_unknown_severity_exits_listing_options(self):
    parser = argparse.ArgumentParser(prog="fake_validator")
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        validator._validate_severity(parser, "fake-severity")

    self.assertIn(
        "Invalid severity. Options are dict_keys(['info', 'warning', 'error',"
        " 'fatal'])",
        stderr.getvalue(),
    )


class ValidateCountryCodesTest(absltest.TestCase):

  def test_valid_country_code_returns_lowercase_code(self):
    parser = argparse.ArgumentParser(prog="fake_validator")

    result = validator._validate_country_codes(parser, " US ")

    self.assertEqual(result, "us")

  def test_invalid_country_code_exits_with_error_message(self):
    parser = argparse.ArgumentParser(prog="fake_validator")
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        validator._validate_country_codes(parser, "zz")

    self.assertIn("Invalid country code.", stderr.getvalue())


class ArgParserTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.xsd_file = self.create_tempfile(content=_FAKE_XSD)
    self.election_file = self.create_tempfile(content=_FEED_WITH_ENGLISH_NAME)

  def test_validate_without_optional_args_uses_defaults(self):
    parser = validator.arg_parser()

    options = parser.parse_args([
        "validate",
        "-x",
        self.xsd_file.full_path,
        self.election_file.full_path,
    ])

    self.assertEqual(options.cmd, "validate")
    self.assertEqual(options.xsd, self.xsd_file.full_path)
    self.assertEqual(options.election_files, [self.election_file.full_path])
    self.assertFalse(options.verbose)
    self.assertIsNone(options.severity)
    self.assertIsNone(options.ocdid_file)
    self.assertEqual(options.c, "us")
    self.assertFalse(options.g)
    self.assertIsNone(options.exclude)
    self.assertIsNone(options.include)
    self.assertEqual(options.rule_set, rules.RuleSet.ELECTION)
    self.assertIsNone(options.required_languages)
    self.assertIsNone(options.profile_report)

  def test_validate_with_all_args_parses_values(self):
    parser = validator.arg_parser()
    ocd_id_file = self.create_tempfile(content=_FAKE_OCD_ID_CSV)

    options = parser.parse_args([
        "validate",
        "-x",
        self.xsd_file.full_path,
        "--verbose",
        "-s",
        "warning",
        "--ocdid_file",
        ocd_id_file.full_path,
        "-c",
        "CA",
        "-g",
        "-e",
        "ValidEnumerations",
        "-r",
        "officeholder",
        "--required_languages",
        "en,es",
        "--profile_report",
        "true",
        self.election_file.full_path,
    ])

    self.assertTrue(options.verbose)
    self.assertEqual(options.severity, 1)
    self.assertEqual(options.ocdid_file, ocd_id_file.full_path)
    self.assertEqual(options.c, "ca")
    self.assertTrue(options.g)
    self.assertEqual(options.exclude, ["ValidEnumerations"])
    self.assertEqual(options.rule_set, rules.RuleSet.OFFICEHOLDER)
    self.assertEqual(options.required_languages, "en,es")
    self.assertEqual(options.profile_report, "true")

  def test_validate_with_include_parses_rule_names(self):
    parser = validator.arg_parser()

    options = parser.parse_args([
        "validate",
        "-x",
        self.xsd_file.full_path,
        "-i",
        "AllLanguages",
        self.election_file.full_path,
    ])

    self.assertEqual(options.include, ["AllLanguages"])

  def test_validate_without_xsd_exits(self):
    parser = validator.arg_parser()

    with contextlib.redirect_stderr(io.StringIO()):
      with self.assertRaises(SystemExit):
        parser.parse_args(["validate", self.election_file.full_path])

  def test_validate_with_missing_election_file_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args(
            ["validate", "-x", self.xsd_file.full_path, "/fake/feed.xml"]
        )

    self.assertIn(
        "The file path for /fake/feed.xml doesn't exist", stderr.getvalue()
    )

  def test_validate_with_missing_xsd_file_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args(
            ["validate", "-x", "/fake/spec.xsd", self.election_file.full_path]
        )

    self.assertIn(
        "The file path for /fake/spec.xsd doesn't exist", stderr.getvalue()
    )

  def test_validate_with_missing_ocdid_file_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args([
            "validate",
            "-x",
            self.xsd_file.full_path,
            "--ocdid_file",
            "/fake/ocd-ids.csv",
            self.election_file.full_path,
        ])

    self.assertIn(
        "The file path for /fake/ocd-ids.csv doesn't exist", stderr.getvalue()
    )

  def test_validate_with_invalid_severity_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args([
            "validate",
            "-x",
            self.xsd_file.full_path,
            "-s",
            "fake-severity",
            self.election_file.full_path,
        ])

    self.assertIn("Invalid severity.", stderr.getvalue())

  def test_validate_with_invalid_country_code_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args([
            "validate",
            "-x",
            self.xsd_file.full_path,
            "-c",
            "zz",
            self.election_file.full_path,
        ])

    self.assertIn("Invalid country code.", stderr.getvalue())

  def test_validate_with_unknown_rule_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args([
            "validate",
            "-x",
            self.xsd_file.full_path,
            "-i",
            "FakeRule",
            self.election_file.full_path,
        ])

    self.assertIn("The rule(s) FakeRule do not exist", stderr.getvalue())

  def test_validate_with_include_and_rule_set_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args([
            "validate",
            "-x",
            self.xsd_file.full_path,
            "-i",
            "AllLanguages",
            "-r",
            "officeholder",
            self.election_file.full_path,
        ])

    self.assertIn("not allowed with argument", stderr.getvalue())

  def test_list_without_args_uses_defaults(self):
    parser = validator.arg_parser()

    options = parser.parse_args(["list"])

    self.assertEqual(options.cmd, "list")
    self.assertIsNone(options.include)
    self.assertIsNone(options.exclude)
    self.assertEqual(options.rule_set, rules.RuleSet.ELECTION)

  def test_list_with_rule_set_parses_rule_set(self):
    parser = validator.arg_parser()

    options = parser.parse_args(
        ["list", "-r", "committee", "-e", "AllLanguages"]
    )

    self.assertEqual(options.rule_set, rules.RuleSet.COMMITTEE)
    self.assertEqual(options.exclude, ["AllLanguages"])

  def test_list_with_unknown_rule_exits(self):
    parser = validator.arg_parser()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
      with self.assertRaises(SystemExit):
        parser.parse_args(["list", "-e", "FakeRule"])

    self.assertIn("The rule(s) FakeRule do not exist", stderr.getvalue())


class RulesetTypeTest(absltest.TestCase):

  def test_lowercase_name_returns_rule_set(self):
    result = validator.ruleset_type("voter_information")

    self.assertEqual(result, rules.RuleSet.VOTER_INFORMATION)

  def test_unknown_name_raises_argument_type_error(self):
    with self.assertRaises(argparse.ArgumentTypeError) as context:
      validator.ruleset_type("fake_rule_set")

    self.assertEqual(
        str(context.exception),
        "Rule set must be one of [election, officeholder, committee,"
        " election_dates, election_results, metadata, voter_information]",
    )


class GetMetadataTest(absltest.TestCase):

  def test_returns_version_and_checksum_and_rewinds_file(self):
    content = b"fake feed content"
    feed_file = io.BytesIO(content)

    metadata = validator.get_metadata(feed_file)

    self.assertEqual(
        metadata,
        [
            f"Validator version: {version.__version__}",
            f"SHA3-256 checksum: 0x{hashlib.sha3_256(content).hexdigest()}",
        ],
    )
    self.assertEqual(feed_file.read(), content)


class DisplayRulesDetailsTest(absltest.TestCase):

  def test_prints_sorted_rule_names_with_first_doc_line(self):
    options = argparse.Namespace(
        include=["ValidEnumerations", "AllLanguages"],
        rule_set=rules.RuleSet.ELECTION,
        exclude=None,
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      validator.display_rules_details(options)

    self.assertEqual(
        stdout.getvalue(),
        "Selected rules details:\n"
        f"\tAllLanguages - {_ALL_LANGUAGES_DOC_FIRST_LINE}\n"
        "\tValidEnumerations - Valid enumerations should not be encoded as"
        " 'OtherType'.\n",
    )


class FilterAllRulesUsingUserArgTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ("election", rules.RuleSet.ELECTION, rules.ELECTION_RULES),
      (
          "election_results",
          rules.RuleSet.ELECTION_RESULTS,
          rules.ELECTION_RULES,
      ),
      ("officeholder", rules.RuleSet.OFFICEHOLDER, rules.OFFICEHOLDER_RULES),
      ("committee", rules.RuleSet.COMMITTEE, rules.COMMITTEE_RULES),
      (
          "election_dates",
          rules.RuleSet.ELECTION_DATES,
          rules.ELECTION_DATES_RULES,
      ),
      ("metadata", rules.RuleSet.METADATA, rules.METADATA_RULES),
      (
          "voter_information",
          rules.RuleSet.VOTER_INFORMATION,
          rules.VOTER_INFORMATION_RULES,
      ),
  )
  def test_rule_set_returns_rule_set_rules(self, rule_set, expected_rules):
    result = validator.filter_all_rules_using_user_arg(None, rule_set, None)

    self.assertCountEqual(result, expected_rules)

  def test_rule_sets_select_distinct_rules(self):
    rule_lists = [
        rules.OFFICEHOLDER_RULES,
        rules.COMMITTEE_RULES,
        rules.ELECTION_DATES_RULES,
        rules.METADATA_RULES,
        rules.VOTER_INFORMATION_RULES,
        rules.ELECTION_RULES,
    ]

    rule_sets = [frozenset(rule_list) for rule_list in rule_lists]

    self.assertLen(set(rule_sets), len(rule_lists))

  def test_blocklist_removes_rules_from_rule_set(self):
    result = validator.filter_all_rules_using_user_arg(
        None, rules.RuleSet.ELECTION, ["AllLanguages"]
    )

    self.assertNotIn(common_rules.AllLanguages, result)
    self.assertCountEqual(
        result,
        [
            rule
            for rule in rules.ELECTION_RULES
            if rule != common_rules.AllLanguages
        ],
    )

  def test_allowlist_returns_only_allowed_rules_in_all_rules_order(self):
    result = validator.filter_all_rules_using_user_arg(
        ["ValidEnumerations", "AllLanguages"],
        rules.RuleSet.METADATA,
        None,
    )

    self.assertEqual(
        result,
        [
            rule
            for rule in rules.ALL_RULES
            if rule in (
                common_rules.AllLanguages,
                common_rules.ValidEnumerations,
            )
        ],
    )

  def test_invalid_rule_set_raises_assertion_error(self):
    with self.assertRaises(AssertionError) as context:
      validator.filter_all_rules_using_user_arg(None, "fake_rule_set", None)

    self.assertEqual(str(context.exception), "Invalid rule_set: fake_rule_set")


class ComputeMaxFoundSeverityTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ("none", [], 0),
      ("info", [loggers.ElectionInfo], 1),
      ("warning", [loggers.ElectionInfo, loggers.ElectionWarning], 2),
      ("error", [loggers.ElectionWarning, loggers.ElectionError], 3),
      ("fatal_only", [loggers.ElectionFatal], 4),
      ("fatal_and_error", [loggers.ElectionError, loggers.ElectionFatal], 4),
  )
  def test_exceptions_return_highest_severity(
      self, exception_types, expected_severity
  ):
    exceptions_wrapper = loggers.ExceptionListWrapper()
    for exception_type in exception_types:
      exceptions_wrapper.exception_handler(
          exception_type.from_message("fake message"), "FakeRule"
      )

    result = validator.compute_max_found_severity(exceptions_wrapper)

    self.assertEqual(result, expected_severity)


class ExecProfilingTest(absltest.TestCase):

  def test_none_options_runs_without_profiling(self):
    profiled_function = validator.exec_profiling(_fake_rules_work)
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      result = profiled_function(None)

    self.assertEqual(result, "fake-result")
    self.assertEqual(stdout.getvalue(), "")

  def test_no_profile_report_runs_without_profiling(self):
    profiled_function = validator.exec_profiling(_fake_rules_work)
    options = argparse.Namespace(profile_report=None)
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      result = profiled_function(options)

    self.assertEqual(result, "fake-result")
    self.assertEqual(stdout.getvalue(), "")

  def test_profile_report_prints_profiling_stats(self):
    profiled_function = validator.exec_profiling(_fake_rules_work)
    options = argparse.Namespace(profile_report="true")
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      result = profiled_function(options)

    self.assertEqual(result, "fake-result")
    self.assertIn("(_fake_rules_work)", stdout.getvalue())


class FeedValidationTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.feed_path = self.create_tempfile(
        content=_FEED_WITH_ENGLISH_NAME
    ).full_path

  def _options(
      self, election_file: BinaryIO, required_languages: str | None
  ) -> argparse.Namespace:
    """Returns validate options that run only AllLanguages on one feed."""
    return argparse.Namespace(
        c="us",
        ocdid_file=None,
        required_languages=required_languages,
        include=["AllLanguages"],
        rule_set=rules.RuleSet.ELECTION,
        exclude=None,
        election_files=[election_file],
        xsd=io.StringIO(_FAKE_XSD),
        profile_report=None,
    )

  def test_missing_required_language_returns_error_in_registry(self):
    with open(self.feed_path, "rb") as election_file:
      options = self._options(election_file, "en,es")

      results = validator.feed_validation(options, _FAKE_OCD_ID_LIST)

    self.assertLen(results, 1)
    self.assertCountEqual(
        results[0].keys(), ["registry", "metadata", "file_name"]
    )
    self.assertEqual(results[0]["file_name"], self.feed_path)
    self.assertEqual(
        results[0]["metadata"][0], f"Validator version: {version.__version__}"
    )
    registry = results[0]["registry"]
    self.assertIsInstance(registry, base.RulesRegistry)
    self.assertEqual(
        registry.exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionError
        ),
        1,
    )
    self.assertEqual(
        registry.rule_classes_to_check, [common_rules.AllLanguages]
    )

  def test_no_required_languages_returns_no_errors(self):
    with open(self.feed_path, "rb") as election_file:
      options = self._options(election_file, None)

      results = validator.feed_validation(options, _FAKE_OCD_ID_LIST)

    registry = results[0]["registry"]
    self.assertEqual(
        registry.exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionError
        ),
        0,
    )
    self.assertIsNotNone(registry.election_tree)

  def test_present_required_languages_returns_no_errors(self):
    with open(self.feed_path, "rb") as election_file:
      options = self._options(election_file, "en")

      results = validator.feed_validation(options, _FAKE_OCD_ID_LIST)

    registry = results[0]["registry"]
    self.assertEqual(
        registry.exceptions_wrapper.count_logs_with_exception_type(
            loggers.ElectionError
        ),
        0,
    )

  def test_ocd_id_list_is_passed_to_rules(self):
    with open(self.feed_path, "rb") as election_file:
      options = self._options(election_file, None)

      results = validator.feed_validation(options, _FAKE_OCD_ID_LIST)

    registry = results[0]["registry"]
    self.assertEqual(
        registry.ocd_id_validator.ocd_ids, frozenset(_FAKE_OCD_ID_LIST)
    )


class PrintExceptionsFromValidationsTest(absltest.TestCase):

  def _registry_with_exceptions(
      self, exception_types: Sequence[type[loggers.ElectionException]]
  ) -> base.RulesRegistry:
    """Returns a registry with one logged exception per given type."""
    registry = base.RulesRegistry(
        election_file=None,
        schema_file=None,
        rule_classes_to_check=[],
        rule_options={},
        ocd_id_validator=None,
    )
    for exception_type in exception_types:
      registry.exceptions_wrapper.exception_handler(
          exception_type.from_message("fake message"), "FakeRule"
      )
    return registry

  def _validation_result(
      self,
      file_name: str,
      exception_types: Sequence[type[loggers.ElectionException]],
  ) -> dict[str, Any]:
    """Returns a feed validation result dict like feed_validation builds."""
    return {
        "registry": self._registry_with_exceptions(exception_types),
        "metadata": ["fake metadata one", "fake metadata two"],
        "file_name": file_name,
    }

  def test_returns_max_severity_across_files_and_prints_results(self):
    options = argparse.Namespace(severity=None, verbose=False)
    results = [
        self._validation_result("fake_error_feed.xml", [loggers.ElectionError]),
        self._validation_result("fake_clean_feed.xml", []),
    ]
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      max_severity = validator.print_exceptions_from_validations(
          options, results
      )

    self.assertEqual(max_severity, 3)
    output = stdout.getvalue()
    self.assertIn(
        "\n--------- Results after validating file: fake_error_feed.xml ",
        output,
    )
    self.assertIn(
        "\n--------- Results after validating file: fake_clean_feed.xml ",
        output,
    )
    self.assertIn("fake metadata one\nfake metadata two\n", output)
    self.assertIn("Error", output)
    self.assertNotIn("Entity and Attribute Counts", output)

  def test_clean_files_return_zero(self):
    options = argparse.Namespace(severity=None, verbose=False)
    results = [self._validation_result("fake_clean_feed.xml", [])]

    with contextlib.redirect_stdout(io.StringIO()):
      max_severity = validator.print_exceptions_from_validations(
          options, results
      )

    self.assertEqual(max_severity, 0)

  def test_no_results_return_zero(self):
    options = argparse.Namespace(severity=None, verbose=False)

    max_severity = validator.print_exceptions_from_validations(options, [])

    self.assertEqual(max_severity, 0)

  def test_non_verbose_does_not_print_entity_counts(self):
    options = argparse.Namespace(severity=None, verbose=False)
    result = self._validation_result("fake_feed.xml", [])
    result["registry"].election_tree = etree.ElementTree(
        etree.fromstring(_FEED_WITH_ENGLISH_NAME)
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      validator.print_exceptions_from_validations(options, [result])

    self.assertNotIn("Entity and Attribute Counts", stdout.getvalue())

  def test_verbose_prints_entity_counts(self):
    options = argparse.Namespace(severity=None, verbose=True)
    result = self._validation_result("fake_feed.xml", [loggers.ElectionInfo])
    result["registry"].election_tree = etree.ElementTree(
        etree.fromstring(_FEED_WITH_ENGLISH_NAME)
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
      max_severity = validator.print_exceptions_from_validations(
          options, [result]
      )

    self.assertEqual(max_severity, 1)
    self.assertIn("Entity and Attribute Counts", stdout.getvalue())


class MainTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.xsd_path = self.create_tempfile(content=_FAKE_XSD).full_path
    self.feed_path = self.create_tempfile(
        content=_FEED_WITH_ENGLISH_NAME
    ).full_path
    self.ocd_id_path = self.create_tempfile(content=_FAKE_OCD_ID_CSV).full_path

  def _validate_argv(self, required_languages: str) -> list[str]:
    """Returns validator argv that checks AllLanguages on the fake feed."""
    return [
        "validator",
        "validate",
        "-x",
        self.xsd_path,
        "--ocdid_file",
        self.ocd_id_path,
        "-i",
        "AllLanguages",
        "--required_languages",
        required_languages,
        self.feed_path,
    ]

  def test_validate_with_errors_returns_error_severity(self):
    stdout = io.StringIO()

    with mock.patch.object(sys, "argv", self._validate_argv("en,es")):
      with contextlib.redirect_stdout(stdout):
        result = validator.main()

    self.assertEqual(result, 3)
    self.assertIn(
        f"--------- Results after validating file: {self.feed_path} ",
        stdout.getvalue(),
    )

  def test_validate_without_errors_returns_zero(self):
    with mock.patch.object(sys, "argv", self._validate_argv("en")):
      with contextlib.redirect_stdout(io.StringIO()):
        result = validator.main()

    self.assertEqual(result, 0)

  def test_list_prints_rules_and_returns_none(self):
    stdout = io.StringIO()

    with mock.patch.object(
        sys, "argv", ["validator", "list", "-i", "AllLanguages"]
    ):
      with contextlib.redirect_stdout(stdout):
        result = validator.main()

    self.assertIsNone(result)
    self.assertEqual(
        stdout.getvalue(),
        "Selected rules details:\n"
        f"\tAllLanguages - {_ALL_LANGUAGES_DOC_FIRST_LINE}\n",
    )

  def test_no_command_prints_nothing_and_returns_none(self):
    stdout = io.StringIO()

    with mock.patch.object(sys, "argv", ["validator"]):
      with contextlib.redirect_stdout(stdout):
        result = validator.main()

    self.assertIsNone(result)
    self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
  absltest.main()

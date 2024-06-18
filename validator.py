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
"""NIST CDF validation library.

A set of rules that can be used to validate a NIST 1500-100 file containing
election candidate or sitting officeholder data according to the included
XSD and additional higher-level requirements.

See https://developers.google.com/elections-data/reference/
"""
from __future__ import print_function

import argparse
import cProfile
import hashlib
import io
import os
import pstats

from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator import rules
from civics_cdf_validator import version

_REGISTRY_KEY = "registry"
_METADATA_KEY = "metadata"
_FILE_NAME_KEY = "file_name"


def _validate_path(parser, arg):
  """Check that the files provided exist."""
  if not os.path.exists(arg):
    parser.error("The file path for %s doesn't exist" % arg)
  else:
    return arg


def _validate_rules(parser, arg):
  """Check that the listed rules exist."""
  invalid_rules = []
  rule_names = [x.__name__ for x in rules.ALL_RULES]
  input_rules = arg.strip().split(",")
  for rule in input_rules:
    if rule and rule not in rule_names:
      invalid_rules.append(rule)
  if invalid_rules:
    parser.error("The rule(s) %s do not exist" % ", ".join(invalid_rules))
  else:
    return input_rules


def _validate_severity(parser, arg):
  """Check that the severity level provided is correct."""
  valid_severities = loggers.supported_severities_mapping()

  if arg.strip().lower() not in valid_severities:
    parser.error("Invalid severity. Options are {0}".format(
        valid_severities.keys()))
  else:
    return valid_severities[arg.strip().lower()]


# pylint: disable=g-doc-args
# pylint: disable=g-doc-return-or-yield
def _validate_country_codes(parser, arg):
  """Check that the supplied 2 country code is correct.

  Check if the provided country code is listed in ISO 3166-1 alpha-2 codes
  """
  country_code = arg.strip().lower()

  if rules.country_code_is_valid(country_code):
    return country_code

  parser.error(
      "Invalid country code. Please make sure it is listed under the officially"
      " assigned ISO 3166-1 alpha-2 codes."
  )


def arg_parser():
  """Parser for command line arguments."""

  description = ("Script to validate that "
                 "election results XML file(s) "
                 "follow best practices")
  parser = argparse.ArgumentParser(description=description)
  subparsers = parser.add_subparsers(dest="cmd")
  parser_validate = subparsers.add_parser("validate")
  add_validate_parser_args(parser, parser_validate)
  parser_list = subparsers.add_parser("list")
  add_parser_rules_filter_args(parser, parser_list)
  return parser


def add_validate_parser_args(parser, parser_validate):
  add_validate_parser_input_file_args(parser, parser_validate)
  add_validate_parser_output_args(parser, parser_validate)
  add_validate_parser_ocd_id_args(parser, parser_validate)
  add_parser_rules_filter_args(parser, parser_validate)
  parser_validate.add_argument(
      "--required_languages",
      help="Languages required by the AllLanguages check.",
      required=False)
  parser_validate.add_argument(
      "--profile_report",
      help="Run profiling and print the execution report.",
      required=False)


def add_validate_parser_input_file_args(parser, parser_validate):
  parser_validate.add_argument(
      "-x",
      "--xsd",
      help="Common Data Format XSD file path",
      required=True,
      metavar="xsd_file",
      type=lambda x: _validate_path(parser, x))
  parser_validate.add_argument(
      "election_files",
      help="XML election files to be validated",
      nargs="+",
      metavar="election_files",
      type=lambda x: _validate_path(parser, x))


def add_validate_parser_output_args(parser, parser_validate):
  """Enriches cmd "validate" parser with output display config."""
  parser_validate.add_argument(
      "--verbose",
      "-v",
      action="store_true",
      help="Print out detailed log messages. Defaults to False",
      required=False)
  parser_validate.add_argument(
      "--severity",
      "-s",
      type=lambda x: _validate_severity(parser, x),
      help="Minimum issue severity level - {0}".format(
          loggers.severities_names()),
      required=False)


def add_validate_parser_ocd_id_args(parser, parser_validate):
  """Enriches cmd "validate" parser with ocdId related arguments."""
  parser_validate.add_argument(
      "--ocdid_file",
      help="Local ocd-id csv file path",
      required=False,
      metavar="csv_file",
      type=lambda x: _validate_path(parser, x))
  parser_validate.add_argument(
      "-c",
      help="Two letter country code for OCD IDs.",
      metavar="country",
      type=lambda x: _validate_country_codes(parser, x),
      required=False,
      default="us")
  parser_validate.add_argument(
      "-g",
      help="Skip check to see if there is a new OCD ID file on Github."
      "Defaults to True",
      action="store_true",
      required=False)


def add_parser_rules_filter_args(parser, cmd_parser):
  """Enriches cmd parser with rules related arguments."""
  cmd_parser.add_argument(
      "-e",
      "--exclude",
      help="Comma separated list of rules to be excluded.",
      required=False,
      type=lambda x: _validate_rules(parser, x))

  group = cmd_parser.add_mutually_exclusive_group(required=False)
  group.add_argument(
      "-i",
      "--include",
      help="Comma separated list of rules to be validated.",
      required=False,
      type=lambda x: _validate_rules(parser, x))
  group.add_argument(
      "--rule_set",
      "-r",
      help="Pre-defined rule set: [{}].".format(", ".join(
          s.name.lower() for s in rules.RuleSet)),
      required=False,
      default="election",
      type=ruleset_type)


def ruleset_type(enum_string):
  try:
    return rules.RuleSet[enum_string.upper()]
  except KeyError:
    msg = "Rule set must be one of [{}]".format(", ".join(
        s.name.lower() for s in rules.RuleSet))
    raise argparse.ArgumentTypeError(msg)


def get_metadata(file):
  """Gets metadata associated with this run of the validator."""
  metadata = ["Validator version: {}".format(version.__version__)]

  blocksize = 65536
  digest = hashlib.new("sha3_256")
  for block in iter(lambda: file.read(blocksize), b""):
    digest.update(block)
  metadata.append("SHA3-256 checksum: 0x{}".format(digest.hexdigest()))
  file.seek(0)
  return metadata


def display_rules_details(options):
  """Display rules set details based on user input."""
  print("Selected rules details:")
  rules_to_display = filter_all_rules_using_user_arg(options.include,
                                                     options.rule_set,
                                                     options.exclude)
  for rule in sorted(rules_to_display, key=lambda x: x.__name__):
    print("\t{} - {}".format(rule.__name__, rule.__doc__.split("\n")[0]))


def filter_all_rules_using_user_arg(rules_allowlist, rule_set, rules_blocklist):
  """Extract a sublist from ALL_RULES list using the user input."""
  if rules_allowlist:
    rule_names = rules_allowlist
  else:
    if rule_set == rules.RuleSet.ELECTION:
      rule_names = [x.__name__ for x in rules.ELECTION_RULES]
    elif rule_set == rules.RuleSet.OFFICEHOLDER:
      rule_names = [x.__name__ for x in rules.OFFICEHOLDER_RULES]
    elif rule_set == rules.RuleSet.COMMITTEE:
      rule_names = [x.__name__ for x in rules.COMMITTEE_RULES]
    elif rule_set == rules.RuleSet.ELECTION_DATES:
      rule_names = [x.__name__ for x in rules.ELECTION_DATES_RULES]
    elif rule_set == rules.RuleSet.ELECTION_RESULTS:
      rule_names = [x.__name__ for x in rules.ELECTION_RESULTS_RULES]
    elif rule_set == rules.RuleSet.METADATA:
      rule_names = [x.__name__ for x in rules.METADATA_RULES]
    else:
      raise AssertionError("Invalid rule_set: " + rule_set)
    if rules_blocklist:
      rule_names = set(rule_names) - set(rules_blocklist)

  rule_classes_to_check = [
      x for x in rules.ALL_RULES if x.__name__ in rule_names
  ]
  return rule_classes_to_check


def compute_max_found_severity(exceptions_wrapper):
  if exceptions_wrapper.count_logs_with_exception_type(loggers.ElectionError):
    return 3
  elif exceptions_wrapper.count_logs_with_exception_type(loggers.
                                                         ElectionWarning):
    return 2
  elif exceptions_wrapper.count_logs_with_exception_type(loggers.ElectionInfo):
    return 1
  else:
    return 0


def exec_profiling(func):
  """This is a decorator to add profiling to the feed validation."""
  def add_profiling_if_needed(options, *args, **kwargs):
    if options is None or not options.profile_report:
      return func(options, *args, **kwargs)
    pr = cProfile.Profile(builtins=False)
    pr.enable()
    result = func(options, *args, **kwargs)
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumulative")
    ps.print_stats("rules")
    print(s.getvalue())
    return result

  return add_profiling_if_needed


@exec_profiling
def feed_validation(options, ocd_id_list=None):
  """Validate the input feed depending on the user parameters."""
  ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
      options.c, options.ocdid_file, not options.g, ocd_id_list
  )
  rule_options = {}
  if options.required_languages:
    rule_options.setdefault("AllLanguages", []).append(
        base.RuleOption("required_languages",
                        str.split(options.required_languages, ",")))
  rule_classes_to_check = filter_all_rules_using_user_arg(
      options.include, options.rule_set, options.exclude)

  validation_results = []
  for election_file in options.election_files:
    validation_context = dict()
    metadata = get_metadata(election_file)
    registry = base.RulesRegistry(
        election_file=election_file,
        schema_file=options.xsd,
        rule_classes_to_check=rule_classes_to_check,
        rule_options=rule_options,
        ocd_id_validator=ocd_id_validator,
    )
    registry.check_rules()
    validation_context[_REGISTRY_KEY] = registry
    validation_context[_METADATA_KEY] = metadata
    validation_context[_FILE_NAME_KEY] = election_file.name
    validation_results.append(validation_context)
  return validation_results


def print_exceptions_from_validations(options, results_validations):
  """Print errors to stdout."""
  max_error_severity = 0
  for result_validation in results_validations:
    election_filename = result_validation[_FILE_NAME_KEY]
    metadata = result_validation[_METADATA_KEY]
    rule_registry = result_validation[_REGISTRY_KEY]
    print(
        "\n--------- Results after validating file: {} ".format(
            election_filename
        )
    )
    for metadatum in metadata:
      print(metadatum)
    rule_registry.print_exceptions(options.severity, options.verbose)
    if options.verbose:
      rule_registry.count_stats()
    max_error_severity = max(
        max_error_severity,
        compute_max_found_severity(rule_registry.exceptions_wrapper),
    )
  return max_error_severity


def main():
  p = arg_parser()
  options = p.parse_args()
  if options.cmd == "list":
    display_rules_details(options)
    return None
  elif options.cmd == "validate":
    options.election_files = [
        open(file, "rb") for file in options.election_files
    ]
    options.xsd = open(options.xsd, "r")
    if options.ocdid_file:
      options.ocdid_file = open(options.ocdid_file, encoding="utf-8")
    validation_results = feed_validation(options)
    return_value = print_exceptions_from_validations(
        options, validation_results
    )
    for file in options.election_files:
      file.close()
    options.xsd.close()
    if options.ocdid_file:
      options.ocdid_file.close()
    return return_value


if __name__ == "__main__":
  main()

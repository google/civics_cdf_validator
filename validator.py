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

"""NIST CDF validation library.

A set of rules that can be used to validate a NIST 1500-100 file containing
election candidate or sitting officeholder data according to the included
XSD and additional higher-level requirements.

See https://developers.google.com/elections-data/reference/
"""
from __future__ import print_function

import argparse
import codecs
import os
import re

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from election_results_xml_validator import base
from election_results_xml_validator import rules
from election_results_xml_validator import version
import github


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

  valid_severities = {"info": 0, "warning": 1, "error": 2}
  if arg.strip().lower() not in valid_severities:
    parser.error("Invalid severity. Options are error, warning, or info")
  else:
    return valid_severities[arg.strip().lower()]


# pylint: disable=g-doc-args
# pylint: disable=g-doc-return-or-yield
def _validate_country_codes(parser, arg):
  """Check that the supplied 2 country code is correct.

  The repo is at https://github.com/opencivicdata/ocd-division-ids
  """
  country_code = arg.strip().lower()

  # 'us' is the default country code and will always be valid.
  # This is so we bypass the call to the GitHub API when no -c flag
  if country_code == "us":
    return country_code

  github_api = github.Github()
  country_ids = github_api.get_repo(
      "opencivicdata/ocd-division-ids"
  ).get_contents("identifiers")
  valid_codes = []

  for content_file in country_ids:
    if content_file.type == "file":
      result = re.search(r"country-([a-z]{2})\.csv", content_file.name)
      if result:
        ocd_id = result.group(1)
        if country_code == ocd_id:
          return country_code
        else:
          valid_codes.append(ocd_id)

  parser.error("Invalid country code. Available codes are: %s" %
               ", ".join(valid_codes))


def arg_parser():
  """Parser for command line arguments."""

  description = ("Script to validate that "
                 "election results XML file(s) "
                 "follow best practices")
  parser = argparse.ArgumentParser(description=description)
  subparsers = parser.add_subparsers(dest="cmd")
  parser_validate = subparsers.add_parser("validate")
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
  parser_validate.add_argument(
      "--ocdid_file",
      help="Local ocd-id csv file path",
      required=False,
      metavar="csv_file",
      type=lambda x: _validate_path(parser, x))

  group = parser_validate.add_mutually_exclusive_group(required=False)
  group.add_argument(
      "-i",
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

  parser_validate.add_argument(
      "-e",
      help="Comma separated list of rules to be excluded.",
      required=False,
      type=lambda x: _validate_rules(parser, x))
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
      help="Minimum issue severity level - error, warning or info",
      required=False)
  parser_validate.add_argument(
      "-g",
      help="Skip check to see if there is a new OCD ID file on Github."
      "Defaults to True",
      action="store_true",
      required=False)
  parser_validate.add_argument(
      "-c",
      help="Two letter country code for OCD IDs.",
      metavar="country",
      type=lambda x: _validate_country_codes(parser, x),
      required=False,
      default="us")
  parser_validate.add_argument(
      "--required_languages",
      help="Languages required by the AllLanguages check.",
      required=False)
  subparsers.add_parser("list")
  return parser


def ruleset_type(enum_string):
  try:
    return rules.RuleSet[enum_string.upper()]
  except KeyError:
    msg = "Rule set must be one of [{}]".format(", ".join(
        s.name.lower() for s in rules.RuleSet))
    raise argparse.ArgumentTypeError(msg)


def print_metadata(filename):
  """Prints metadata associated with this run of the validator."""
  print("Validator version: {}".format(version.__version__))

  blocksize = 65536
  digest = hashes.Hash(hashes.SHA512_256(), backend=default_backend())
  with open(filename, "rb") as f:
    for block in iter(lambda: f.read(blocksize), b""):
      digest.update(block)
  print("SHA-512/256 checksum: 0x{:x}".format(
      int(codecs.encode(digest.finalize(), "hex"), 16)))


def main():
  p = arg_parser()
  options = p.parse_args()
  if options.cmd == "list":
    print("Available rules are :")
    for rule in sorted(rules.ALL_RULES, key=lambda x: x.__name__):
      print("\t" + rule.__name__ + " - " + rule.__doc__.split("\n")[0])
    return
  elif options.cmd == "validate":
    if options.rule_set == rules.RuleSet.ELECTION:
      rule_names = [x.__name__ for x in rules.ELECTION_RULES]
    elif options.rule_set == rules.RuleSet.OFFICEHOLDER:
      rule_names = [x.__name__ for x in rules.OFFICEHOLDER_RULES]
    else:
      raise AssertionError("Invalid rule_set: " + options.rule_set)

    if options.i:
      rule_names = options.i
    elif options.e:
      rule_names = set(rule_names) - set(options.e)

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
    if options.required_languages:
      rule_options.setdefault("AllLanguages", []).append(
          base.RuleOption("required_languages",
                          str.split(options.required_languages, ",")))
    rule_classes_to_check = [
        x for x in rules.ALL_RULES if x.__name__ in rule_names
    ]

    if isinstance(options.election_files, list):
      xml_files = options.election_files
    else:
      xml_files = [options.election_files]

    errors = []

    for election_file in xml_files:
      print("\n--------- Results after validating file: {0} "
            .format(election_file))

      if (not election_file.endswith(".xml")
          or not os.stat(election_file).st_size):
        print("{0} is not a valid XML file.".format(election_file))
        errors.append(3)
        continue

      print_metadata(election_file)
      registry = base.RulesRegistry(
          election_file=election_file,
          schema_file=options.xsd,
          rule_classes_to_check=rule_classes_to_check,
          rule_options=rule_options)
      registry.check_rules()
      registry.count_stats()
      registry.print_exceptions(options.severity, options.verbose)
      if registry.exception_counts[base.ElectionError]:
        errors.append(3)
      elif registry.exception_counts[base.ElectionWarning]:
        errors.append(2)
      elif registry.exception_counts[base.ElectionInfo]:
        errors.append(1)
      else:
        errors.append(0)
    return max(errors)

if __name__ == "__main__":
  main()

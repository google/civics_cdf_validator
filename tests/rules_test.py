# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import rules
from civics_cdf_validator.rulesets import common_rules

_EXCLUDED_BASE_OR_DISABLED_RULES = frozenset({
    base.TreeRule,
    base.ValidReferenceRule,
    base.DateRule,
    base.MissingFieldRule,
    base.SchemaRule,
    common_rules.ValidatePartyCollection,
    common_rules.UnreferencedEntitiesBase,
})


class _FakeTestReferenceRule(base.ValidReferenceRule):
  """Fake deep rule subclass defined in tests to verify test-rule exclusion."""


def _subclasses(cls: type[object]) -> set[type[object]]:
  subclasses = set()
  worklist = list(cls.__subclasses__())
  while worklist:
    subclass = worklist.pop()
    if subclass not in subclasses:
      subclasses.add(subclass)
      worklist.extend(subclass.__subclasses__())
  return subclasses


def _is_production_rule(rule_cls: type[base.BaseRule]) -> bool:
  package = base.__package__ or "civics_cdf_validator"
  module = rule_cls.__module__
  return module.startswith(f"{package}.") and not f"{module}.".startswith(
      f"{package}.tests."
  )


class RulesTest(absltest.TestCase):

  def test_all_rules_included_succeeds(self):
    all_rules = rules.ALL_RULES
    possible_rules = {
        rule for rule in _subclasses(base.BaseRule) if _is_production_rule(rule)
    } - _EXCLUDED_BASE_OR_DISABLED_RULES

    self.assertSetEqual(all_rules, possible_rules)

  def test_subclasses_returns_all_descendants_across_levels(self):
    class _Root:
      pass

    class _BranchA(_Root):
      pass

    class _BranchB(_Root):
      pass

    class _DiamondChild(_BranchA, _BranchB):
      pass

    class _Leaf(_DiamondChild):
      pass

    self.assertSetEqual(
        _subclasses(_Root),
        {_BranchA, _BranchB, _DiamondChild, _Leaf},
    )
    self.assertIn(_FakeTestReferenceRule, _subclasses(base.BaseRule))

  def test_rule_set_names_match_supported_feed_types(self):
    rule_set_names = [rule_set.name for rule_set in rules.RuleSet]

    self.assertEqual(
        rule_set_names,
        [
            "ELECTION",
            "OFFICEHOLDER",
            "COMMITTEE",
            "ELECTION_DATES",
            "ELECTION_RESULTS",
            "METADATA",
            "VOTER_INFORMATION",
        ],
    )


if __name__ == "__main__":
  absltest.main()

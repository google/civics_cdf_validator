# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

from absl.testing import absltest
from civics_cdf_validator import base
from civics_cdf_validator import rules
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import election_rules
from civics_cdf_validator.rulesets import metadata_rules


class RulesTest(absltest.TestCase):

  def test_all_rules_included_succeeds(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(election_rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    possible_rules.remove(base.MissingFieldRule)
    possible_rules.remove(common_rules.UnreferencedEntitiesBase)
    # TODO(b/555757644): Reenable this rule once we are ready to enforce it.
    possible_rules.remove(metadata_rules.SqsQueueNameIsFullyQualifiedArn)

    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()

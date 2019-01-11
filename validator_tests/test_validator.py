import unittest

import base

class TestValidator(unittest.TestCase):
    """Unit tests to test the validar package."""
    def setUp(self):
       self.test_rule_option = base.RuleOption('name', 'value')

    def testRuleOption(self):
    	self.assertEqual('name', self.test_rule_option.option_name)
    	self.assertEqual('value', self.test_rule_option.option_value)

    def testFail(self):
    	self.assertEqual('YES', 'NO')
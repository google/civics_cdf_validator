# -*- coding: utf-8 -*-
"""Unit test for validator.py."""

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import loggers
from civics_cdf_validator import validator


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


if __name__ == "__main__":
  absltest.main()

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


# pylint: disable=g-bad-exception-name
class ElectionException(Exception):
  """Base class for all the errors in this script."""
  error_message = None
  description = None
  error_log = []

  def __init__(self, message):
    super(ElectionException, self).__init__()
    self.error_message = message

  def __str__(self):
    return repr(self.error_message)


class ElectionError(ElectionException):
  """An error that prevents the feed from being processed successfully."""

  description = "Error"

  def __init__(self, message, error_log=None):
    super(ElectionError, self).__init__(message)
    if error_log:
      self.error_log = error_log


class ElectionTreeError(ElectionError):
  """Special exception for Tree Rules."""

  def __init__(self, message, error_log):
    super(ElectionTreeError, self).__init__(message)
    self.error_log = error_log


# pylint: disable=g-bad-exception-name
class ElectionWarning(ElectionException):
  """An issue that should be fixed.

  It will not stop the feed from being successfully processed but may lead to
  undefined errors.
  """

  description = "Warning"

  def __init__(self, message, warning_log=None):
    super(ElectionWarning, self).__init__(message)
    if warning_log:
      self.error_log = warning_log


# pylint: disable=g-bad-exception-name
class ElectionInfo(ElectionException):
  """Information that user needs to know about following XML best practices."""

  description = "Info"

  def __init__(self, message, error_log=None):
    super(ElectionInfo, self).__init__(message)
    if error_log:
      self.error_log = error_log


class ElectionTreeInfo(ElectionInfo):
  """Special exception for Tree Rules."""

  def __init__(self, message, error_log):
    super(ElectionTreeInfo, self).__init__(message)
    self.error_log = error_log


class ErrorLogEntry(object):
  line = None
  message = None

  def __init__(self, line, message):
    self.line = line
    self.message = message

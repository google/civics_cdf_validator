# Copyright 2026 Google LLC
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
"""Tests that dependencies in setup.py match third-party deps in BUILD."""

import os
import re
import sys

from absl.testing import absltest

_VALIDATOR_RELATIVE_PATH = os.path.join(
    "third_party", "py", "civics_cdf_validator"
)

_INSTALL_REQUIRES_REGEX = re.compile(
    r"install_requires\s*=\s*\[(.*?)\]", re.DOTALL
)
_SETUP_PKG_SPEC_REGEX = re.compile(r"['\"]([^'\"]+)['\"]")
_PKG_SPEC_SPLIT_REGEX = re.compile(r"[><=~\[]")

_VALIDATOR_LIB_DEPS_REGEX = re.compile(
    r'py_library\s*\(\s*name\s*=\s*"validator_lib".*?deps\s*=\s*\[(.*?)\]',
    re.DOTALL,
)
_THIRD_PARTY_PY_DEP_REGEX = re.compile(r'["\'](//third_party/py/[^"\']+)["\']')


def _get_file_path(filename):
  """Finds a file relative to __file__ or in TEST_SRCDIR."""
  dir_path = os.path.dirname(__file__)
  candidate = os.path.abspath(os.path.join(dir_path, "..", filename))
  if os.path.exists(candidate):
    return candidate

  srcdir = os.environ.get("TEST_SRCDIR", "")
  if srcdir:
    candidate = os.path.join(
        srcdir, "google3", _VALIDATOR_RELATIVE_PATH, filename
    )
    if os.path.exists(candidate):
      return candidate
    candidate = os.path.join(srcdir, _VALIDATOR_RELATIVE_PATH, filename)
    if os.path.exists(candidate):
      return candidate
  raise FileNotFoundError(f"Could not locate {filename}")


def _get_requests_version():
  """Returns requests dependency name based on Python version as in setup.py."""
  if sys.version_info[0] == 2 and sys.version_info[1] <= 7:
    requests_version = "requests[security]"
    if sys.version_info[1] == 7 and sys.version_info[2] >= 9:
      requests_version = "requests"
  else:
    requests_version = "requests"
  return requests_version


def _extract_setup_deps(setup_py_path):
  """Extracts raw package names from install_requires in setup.py."""
  with open(setup_py_path, "r", encoding="utf-8") as f:
    content = f.read()

  match = _INSTALL_REQUIRES_REGEX.search(content)
  if not match:
    raise ValueError("Could not find install_requires in setup.py")

  requests_version = _get_requests_version()
  block = match.group(1)
  raw_items = _SETUP_PKG_SPEC_REGEX.findall(block)
  packages = []
  for item in raw_items:
    if "%s" in item:
      item = item % requests_version
    pkg = _PKG_SPEC_SPLIT_REGEX.split(item)[0].strip()
    if pkg:
      packages.append(pkg)
  return packages


def _extract_build_deps(build_path):
  """Extracts third-party py deps from validator_lib in BUILD."""
  with open(build_path, "r", encoding="utf-8") as f:
    content = f.read()

  match = _VALIDATOR_LIB_DEPS_REGEX.search(content)
  if not match:
    raise ValueError("Could not find validator_lib deps in BUILD")

  deps_block = match.group(1)
  raw_deps = _THIRD_PARTY_PY_DEP_REGEX.findall(deps_block)
  return raw_deps


def _normalize_name(pkg_name):
  """Normalizes package names for cross-validation."""
  pkg_name = pkg_name.replace("//third_party/py/", "")
  if ":" in pkg_name:
    pkg_name = pkg_name.split(":")[0]

  pkg_name = pkg_name.lower().strip()
  if pkg_name in ("python-dateutil", "dateutil", "dateutil_core"):
    return "dateutil"
  if pkg_name in ("language-tags", "language_tags"):
    return "language_tags"
  return pkg_name.replace("-", "_")


class SetupDepsTest(absltest.TestCase):

  def test_setup_deps_match_build_deps(self):
    setup_path = _get_file_path("setup.py")
    build_path = _get_file_path("BUILD")

    setup_pkgs = _extract_setup_deps(setup_path)
    build_deps = _extract_build_deps(build_path)

    setup_normalized = {_normalize_name(pkg) for pkg in setup_pkgs}
    build_normalized = {_normalize_name(dep) for dep in build_deps}

    self.assertEqual(
        setup_normalized,
        build_normalized,
        f"Mismatch between setup.py install_requires ({setup_pkgs}) and "
        f"BUILD validator_lib deps ({build_deps}).",
    )


if __name__ == "__main__":
  absltest.main()

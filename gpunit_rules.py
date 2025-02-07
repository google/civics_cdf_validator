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
"""Classes used to validate GpUnit OCD IDs in CDF feeds."""

from __future__ import print_function

import csv
import datetime
import io
import os
import re
import shutil

import attrs
import pycountry
import requests


def generate_github_raw_url(repo_name, subdir, file_name, branch="master"):
  return "https://raw.github.com/{0}/{1}/{2}/{3}".format(
      repo_name, branch, subdir, file_name
  )


def generate_country_filename(country_code):
  return "country-{0}.csv".format(country_code)


def generate_absolute_path(path_to_directory, country_code):
  return "{0}/{1}".format(
      path_to_directory, generate_country_filename(country_code)
  )


class GpUnitOcdIdValidator(object):
  """Validates GpUnit OCD-IDs.

  This class fetches and stores existing OCD IDs to be used for validity checks.
  It should be initialized with the user input.
  """

  OCD_PATTERN = r"^ocd-division\/(?P<country_code>(country|region):[a-z]{2})(\/(\w|-)+:(\w|-|\.|~)+)*$"
  OCD_MATCHER = re.compile(OCD_PATTERN, flags=re.U)
  OCD_PATTERN_ROOT = r"^ocd-division\/(country:[a-z]{2}|region:eu)$"
  OCD_MATCHER_ROOT = re.compile(OCD_PATTERN_ROOT, flags=re.U)

  def __init__(self, country_code, local_file, ocd_id_list=None):
    """Initialize the class.

    If a list is provided, that list will be used to initialize the set of OCD
    IDs. If a file is provided, the OCD IDs will be pulled from the local file.
    Otherwise, the OCD IDs will be fetched from Github.

    Args:
      country_code: the code for the country to fetch OCD IDs for
      local_file: the file containing the OCD IDs
      ocd_id_list: a list of OCD IDs
    """
    if ocd_id_list:
      self.ocd_ids = frozenset(ocd_id_list)
    else:
      extractor = OcdIdsExtractor(country_code, local_file)
      self.ocd_ids = extractor.extract()

  def is_valid_ocd_id(self, ocd_id):
    """Check whether the given OCD ID is valid.

    An OCD ID is valid if:
    - it is in the list of existing OCD IDs
    - it is properly formatted
    - it has a valid country code

    Args:
      ocd_id: the OCD ID of interest

    Returns:
      True if the OCD ID is valid. False otherwise.
    """
    ocd_id = str(ocd_id)
    return (
        ocd_id in self.ocd_ids
        and self.OCD_MATCHER.match(ocd_id)
        and self.is_valid_country_code(ocd_id)
    )

  @classmethod
  def is_valid_country_code(cls, ocd_id):
    """Check whether country code in the given OCD ID is valid."""
    match_object = re.match(cls.OCD_PATTERN, ocd_id)
    if match_object is None:
      return False
    country_code = match_object.groupdict().get("country_code")
    if "region" in country_code:
      return True
    code = country_code.split(":")[1]
    for country in pycountry.countries:
      if code == country.alpha_2.lower():
        return True
    return False

  @classmethod
  def is_country_or_region_ocd_id(cls, ocd_id):
    """Check whether the given OCD ID represents a country or region."""
    return cls.OCD_MATCHER_ROOT.match(str(ocd_id))


class OcdIdsExtractor(object):
  """Extract OCD IDs from github or from a local file if defined.

  The complete OCD ID definition can be found at
  https://open-civic-data.readthedocs.io/en/latest/proposals/0002.html
  """

  CACHE_DIR = "~/.cache"
  GITHUB_REPO = "opencivicdata/ocd-division-ids"
  GITHUB_DIR = "identifiers"
  EU_COUNTRIES = frozenset([
      "at",
      "be",
      "bg",
      "hr",
      "cy",
      "cz",
      "dk",
      "eu",
      "ee",
      "fi",
      "fr",
      "de",
      "gr",
      "hu",
      "ie",
      "it",
      "lv",
      "lt",
      "lu",
      "mt",
      "nl",
      "pl",
      "pt",
      "ro",
      "sk",
      "si",
      "es",
      "se",
  ])

  @attrs.define(frozen=True)
  class OcdIdsExtractorConfig:
    country_code: str
    github_filename: str
    github_raw_url: str
    local_filepath: str

  def __init__(self, country_code=None, local_file=None):
    self.country_code = country_code
    self.local_file = local_file

  def extract(self) -> set[str]:
    return self._get_ocd_data()

  def _get_ocd_data(self) -> set[str]:
    """Returns a list of OCD-ID codes.

    This list is populated using either a local file or a downloaded file
    from GitHub.
    """
    # Value `local_file` is not provided by default, only by cmd line arg.
    # Short circuit to read from local file if provided.
    if self.local_file:
      return self._read_csv([
          self.OcdIdsExtractorConfig(
              country_code=self.country_code,
              github_filename="",
              github_raw_url="",
              local_filepath=self.local_file,
          )
      ])

    cache_directory = os.path.expanduser(self.CACHE_DIR)

    # Generate configs.
    configs = self._generate_configs(self.country_code, cache_directory)

    # Create the cache directory if it doesn't exist.
    self._create_cache(cache_directory)

    # Check if the necessary cached files exist and how fresh they are. Then
    # download them.
    self._download_data(self._check_cache_freshness(configs))

    return self._read_csv(configs)

  def _create_cache(self, cache_directory: str) -> None:
    """Creates a cache directory if it doesn't exist."""
    if not os.path.exists(cache_directory):
      os.makedirs(cache_directory)

  def _check_for_cached_file(self, local_filepath: str) -> bool:
    """Checks if a cached file exists."""
    return os.path.exists(local_filepath)

  def _check_cache_freshness(
      self, configs: list[OcdIdsExtractorConfig]
  ) -> list[OcdIdsExtractorConfig]:
    """Determines if the cache is fresh (enough).

    Args:
      configs: A list of OcdIdsExtractorConfig objects.

    Returns:
      A list of OcdIdsExtractorConfig objects that need to be downloaded.
    """
    need_download = []
    for config in configs:
      # Check if the cached file exists. If not, add it to the list of files
      # that need to be downloaded and move on to the next config.
      if not self._check_for_cached_file(config.local_filepath):
        need_download.append(config)
        continue

      # Calculate the time since the last modification of the cached file.
      last_mod_date = datetime.datetime.fromtimestamp(
          os.path.getmtime(config.local_filepath), datetime.timezone.utc
      )
      seconds_since_mod = (
          datetime.datetime.now(datetime.timezone.utc) - last_mod_date
      ).total_seconds()

      # Check if the file is more than an hour old. If so, redownlaod.
      if (seconds_since_mod / 3600) > 1:
        need_download.append(config)

    return need_download

  def _generate_configs(
      self, given_country_code: str, cache_directory: str
  ) -> list[OcdIdsExtractorConfig]:
    """Generates configs for the given country code.

    If the country code is EU, generate configs for all EU countries. Otherwise,
    generate a config for the given country code.

    Args:
      given_country_code: The country code to generate configs for.
      cache_directory: The directory to store the configs in.

    Returns:
      A list of OcdIdsExtractorConfig objects.
    """
    configs = []

    # Check if the given country code is EU. If so, generate configs for all
    # EU countries. Otherwise, generate a config for the given country code.
    country_codes = (
        self.EU_COUNTRIES
        if given_country_code == "eu"
        else [given_country_code]
    )
    for country in country_codes:
      github_filename = generate_country_filename(country)
      configs.append(
          self.OcdIdsExtractorConfig(
              country_code=country,
              github_filename=github_filename,
              github_raw_url=generate_github_raw_url(
                  self.GITHUB_REPO, self.GITHUB_DIR, github_filename
              ),
              local_filepath=generate_absolute_path(cache_directory, country),
          )
      )

    return configs

  def _download_data(self, configs: list[OcdIdsExtractorConfig]) -> None:
    """Download OCD ID files from Github and verify the SHA."""

    # Download the file(s) from Github.
    for config in configs:
      local_tmp_filepath = "{0}.tmp".format(config.local_filepath)
      r = requests.get(config.github_raw_url)
      with io.open(local_tmp_filepath, mode="wb") as fd:
        for chunk in r.iter_content():
          fd.write(chunk)
      shutil.copy(local_tmp_filepath, config.local_filepath)
      os.remove(local_tmp_filepath)

  def _read_csv(self, configs: list[OcdIdsExtractorConfig]) -> set[str]:
    """Reads in OCD IDs from CSV file."""
    ocd_id_codes = set()

    # Condense all given CSV file ocd ids into a single set.
    for config in configs:
      with io.open(config.local_filepath, encoding="utf-8", mode="r") as fd:
        csv_reader = csv.DictReader(fd)
        for row in csv_reader:
          if "id" in row and row["id"]:
            ocd_id_codes.add(row["id"])

    return ocd_id_codes

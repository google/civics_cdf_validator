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
import hashlib
import io
import os
import re
import shutil

from civics_cdf_validator import loggers
import github
import pycountry
import requests


class GpUnitOcdIdValidator(object):
  """Validates GpUnit OCD-IDs.

  This class fetches and stores existing OCD IDs to be used for validity checks.
  It should be initialized with the user input.
  """

  ocd_ids = set()
  OCD_PATTERN = r"^ocd-division\/(?P<country_code>(country|region):[a-z]{2})(\/(\w|-)+:(\w|-|\.|~)+)*$"
  ocd_matcher = re.compile(OCD_PATTERN, flags=re.U)
  OCD_PATTERN_ROOT = r"^ocd-division\/(country:[a-z]{2}|region:eu)$"
  ocd_matcher_root = re.compile(OCD_PATTERN_ROOT, flags=re.U)

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
  def initialize_ocd_ids(
      cls, country_code, local_file, check_github, ocd_id_list=None
  ):
    """Initialize the set of existing OCD IDs.

    If a list is provided, that list will be used to initialize the set of OCD
    IDs. If a file is provided, the OCD IDs will be pulled from the local file.
    Otherwise, the OCD IDs will be fetched from Github.

    Args:
      country_code: the code for the country to fetch OCD IDs for
      local_file: the file containing the OCD IDs
      check_github: boolean that indicates if OCD IDs should be fetched from
        Github
      ocd_id_list: a list of OCD IDs
    """
    if ocd_id_list:
      cls.ocd_ids = set(ocd_id_list)
    else:
      extractor = OcdIdsExtractor(country_code, local_file, check_github)
      cls.ocd_ids = extractor.extract()

  @classmethod
  def is_valid_ocd_id(cls, ocd_id):
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
        ocd_id in cls.ocd_ids
        and cls.ocd_matcher.match(ocd_id)
        and cls.is_valid_country_code(ocd_id)
    )

  @classmethod
  def is_country_or_region_ocd_id(cls, ocd_id):
    """Check whether the given OCD ID represents a country or region."""
    return cls.ocd_matcher_root.match(str(ocd_id))


class OcdIdsExtractor(object):
  """Extract OCD IDs from github or from a local file if defined.

  The complete OCD ID definition can be found at
  https://open-civic-data.readthedocs.io/en/latest/proposals/0002.html
  """

  CACHE_DIR = "~/.cache"
  GITHUB_REPO = "opencivicdata/ocd-division-ids"
  GITHUB_DIR = "identifiers"

  def __init__(self, country_code=None, local_file=None, check_github=True):
    self.check_github = check_github
    self.country_code = country_code
    self.github_file = None
    self.github_repo = None
    self.local_file = local_file

  def extract(self):
    if self.local_file is None:
      self.github_file = "country-%s.csv" % self.country_code
    return self._get_ocd_data()

  def _read_csv(self, reader, ocd_id_codes):
    """Reads in OCD IDs from CSV file."""
    for row in reader:
      if "id" in row and row["id"]:
        ocd_id_codes.add(row["id"])

  def _get_ocd_data(self):
    """Returns a list of OCD-ID codes.

    This list is populated using either a local file or a downloaded file
    from GitHub.
    """
    # Value `local_file` is not provided by default, only by cmd line arg.
    if self.local_file:
      countries_file = self.local_file
    else:
      cache_directory = os.path.expanduser(self.CACHE_DIR)
      countries_filename = "{0}/{1}".format(cache_directory, self.github_file)

      if not os.path.exists(countries_filename):
        # Only initialize `github_repo` if there's no cached file.
        github_api = github.Github()
        self.github_repo = github_api.get_repo(self.GITHUB_REPO)
        if not os.path.exists(cache_directory):
          os.makedirs(cache_directory)
        self._download_data(countries_filename)
      else:
        if self.check_github:
          last_mod_date = datetime.datetime.fromtimestamp(
              os.path.getmtime(countries_filename))

          seconds_since_mod = (datetime.datetime.now() -
                               last_mod_date).total_seconds()

          # If 1 hour has elapsed, check GitHub for the last file update.
          if (seconds_since_mod / 3600) > 1:
            github_api = github.Github()
            self.github_repo = github_api.get_repo(self.GITHUB_REPO)
            # Re-download the file if the file on GitHub was updated.
            if last_mod_date < self._get_latest_commit_date():
              self._download_data(countries_filename)
            # Update the timestamp to reflect last GitHub check.
            os.utime(countries_filename, None)
      countries_file = open(countries_filename, encoding="utf-8")
    ocd_id_codes = set()
    csv_reader = csv.DictReader(countries_file)
    self._read_csv(csv_reader, ocd_id_codes)

    return ocd_id_codes

  def _get_latest_commit_date(self):
    """Returns the latest commit date to country-*.csv."""
    latest_commit = self.github_repo.get_commits(
        path="{0}/{1}".format(self.GITHUB_DIR, self.github_file))[0]
    latest_commit_date = latest_commit.commit.committer.date
    return latest_commit_date

  def _download_data(self, file_path):
    """Makes a request to Github to download the file."""
    ocdid_url = "https://raw.github.com/{0}/master/{1}/{2}".format(
        self.GITHUB_REPO, self.GITHUB_DIR, self.github_file)
    r = requests.get(ocdid_url)
    with io.open("{0}.tmp".format(file_path), "wb") as fd:
      for chunk in r.iter_content():
        fd.write(chunk)
    valid = self._verify_data("{0}.tmp".format(file_path))
    if not valid:
      raise loggers.ElectionError.from_message(
          ("Could not successfully download OCD ID data files. Please try "
           "downloading the file manually and place it in ~/.cache"))
    else:
      shutil.copy("{0}.tmp".format(file_path), file_path)

  def _verify_data(self, file_path):
    """Validates a file's SHA."""
    file_sha1 = hashlib.sha1()
    file_info = os.stat(file_path)
    # GitHub calculates the blob SHA like this:
    # sha1("blob "+filesize+"\0"+data)
    file_sha1.update(b"blob %d\0" % file_info.st_size)
    with io.open(file_path, mode="rb") as fd:
      for line in fd:
        file_sha1.update(line)
    latest_file_sha = self._get_latest_file_blob_sha()
    return latest_file_sha == file_sha1.hexdigest()

  def _get_latest_file_blob_sha(self):
    """Returns the GitHub blob SHA of country-*.csv."""
    blob_sha = None
    dir_contents = self.github_repo.get_contents(self.GITHUB_DIR)
    for content_file in dir_contents:
      if content_file.name == self.github_file:
        blob_sha = content_file.sha
        break
    return blob_sha

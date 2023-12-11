# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import inspect
import io
import time

from absl.testing import absltest
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
import github
from mock import create_autospec
from mock import MagicMock
from mock import patch


class GpUnitOcdIdValidatorTest(absltest.TestCase):

  def testIsValidCountryCodeWithInvalidCountry_returnsFalse(self):
    ocd_value = "ocd-division/country:usa"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def testIsValidCountryCodeWithValidCountry_returnsTrue(self):
    ocd_value = "ocd-division/country:us"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def testIsValidCountryCodeWithWrongPattern_returnsFalse(self):
    ocd_value = "ocd-division/wrong_id_pattern"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def testIsValidCountryCodeWithRegion_returnsTrue(self):
    ocd_value = "ocd-division/region:la"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def testIsValidOcdIdWithWrongPattern_returnsFalse(self):
    ocd_value = "regionalwahlkreis:burgenland_sued"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithInvalidCharacter_returnsFalse(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland*d"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWIthMissingOcdId_returnsFalse(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:kärnten_west"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set(
        ["ocd-division/country:la/regionalwahlkreis:burgenland_süd"]
    )
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithValidId_returnsTrue(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithValidCountryId_returnsTrue(self):
    ocd_value = "ocd-division/country:la"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithInvalidCountryId_returnsFalse(self):
    ocd_value = "ocd-division/country:lan"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithRegionId_returnsTrue(self):
    ocd_value = "ocd-division/region:la"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsValidOcdIdWithStateId_returnsTrue(self):
    ocd_value = "ocd-division/country:us/state:la"
    gpunit_rules.GpUnitOcdIdValidator.ocd_ids = set([ocd_value])
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_ocd_id(ocd_value)
    )

  def testIsCountryOrRegionOcdIdWithNonString_returnsFalse(self):
    ocd_value = 1
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def testIsCountryOrRegionOcdIdWithWrongPattern_returnsFalse(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def testIsCountryOrRegionOcdIdWithCountryId_returnsTrue(self):
    ocd_value = "ocd-division/country:la"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def testIsCountryOrRegionOcdIdWithRegionId_returnsTrue(self):
    ocd_value = "ocd-division/region:eu"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def testIsCountryOrRegionOcdIdWithRegionId_returnsFalse(self):
    ocd_value = "ocd-division/region:us"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def testInitializeOcdIdsFromList(self):
    list_of_ids = ["ocd-division/country:la"]
    local_file = io.StringIO("id,\nocd-division/country:us,\n")
    gpunit_rules.GpUnitOcdIdValidator.initialize_ocd_ids(
        country_code="us",
        local_file=local_file,
        check_github=False,
        ocd_id_list=list_of_ids,
    )
    self.assertEqual(
        gpunit_rules.GpUnitOcdIdValidator.ocd_ids, set(list_of_ids)
    )

  def testInitializeOcdIdsFromLocalFile(self):
    local_file = io.StringIO(
        "id,\nocd-division/country:la,\nocd-division/country:us,\n"
    )
    gpunit_rules.GpUnitOcdIdValidator.initialize_ocd_ids(
        country_code="us",
        local_file=local_file,
        check_github=False,
        ocd_id_list=None,
    )
    self.assertEqual(
        gpunit_rules.GpUnitOcdIdValidator.ocd_ids,
        set(["ocd-division/country:la", "ocd-division/country:us"]),
    )


class OcdIdsExtractorTest(absltest.TestCase):

  def setUp(self):
    super(OcdIdsExtractorTest, self).setUp()
    self.ocdid_extractor = gpunit_rules.OcdIdsExtractor()

    open_mod = inspect.getmodule(open)
    self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = MagicMock(
        return_value=io.StringIO(downloaded_ocdid_file)
    )

  def testSetsDefaultValuesUponCreation(self):
    self.assertTrue(self.ocdid_extractor.check_github)
    self.assertIsNone(self.ocdid_extractor.country_code)
    self.assertIsNone(self.ocdid_extractor.github_file)
    self.assertIsNone(self.ocdid_extractor.github_repo)
    self.assertIsNone(self.ocdid_extractor.local_file)

  # setup tests
  def testSetOCDsToResultOfGetOcdData(self):
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_extractor._get_ocd_data = mock
    self.ocdid_extractor.local_file = "://file/path"
    ocds = self.ocdid_extractor.extract()

    self.assertIsNone(self.ocdid_extractor.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, ocds)

  def testSetsGithubFileIfNoLocalFile(self):
    self.ocdid_extractor.country_code = "us"
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_extractor._get_ocd_data = mock
    ocds = self.ocdid_extractor.extract()

    self.assertEqual("country-us.csv", self.ocdid_extractor.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, ocds)

  # _get_latest_commit_date tests
  def testReturnsTheLatestCommitDateForTheCountryCSV(self):
    self.ocdid_extractor.github_file = "country-ar.csv"
    self.ocdid_extractor.github_repo = github.Repository.Repository(
        None, [], [], None
    )
    now = datetime.datetime.now()
    formatted_commit_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = github.Commit.Commit(
        None,
        {},
        dict({
            "commit": dict({"committer": dict({"date": formatted_commit_date})})
        }),
        None,
    )

    mock_get_commits = MagicMock(return_value=[commit])
    self.ocdid_extractor.github_repo.get_commits = mock_get_commits

    latest_commit_date = self.ocdid_extractor._get_latest_commit_date()
    self.assertEqual(
        now.replace(microsecond=0).replace(tzinfo=datetime.timezone.utc),
        latest_commit_date.replace(tzinfo=datetime.timezone.utc),
    )
    mock_get_commits.assert_called_with(path="identifiers/country-ar.csv")

  # _download_data tests
  def testItCopiesDownloadedDataToCacheFileWhenValid(self):
    self.ocdid_extractor.github_file = "country-ar.csv"
    self.ocdid_extractor._verify_data = MagicMock(return_value=True)
    mock_request = MagicMock()
    mock_io_open = MagicMock()
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", mock_request), patch(
        "io.open", mock_io_open
    ), patch("shutil.copy", mock_copy):
      self.ocdid_extractor._download_data("/usr/cache")

    request_url = "https://raw.github.com/{0}/master/{1}/country-ar.csv".format(
        self.ocdid_extractor.GITHUB_REPO, self.ocdid_extractor.GITHUB_DIR
    )
    mock_request.assert_called_with(request_url)
    mock_io_open.assert_called_with("/usr/cache.tmp", "wb")
    mock_copy.assert_called_with("/usr/cache.tmp", "/usr/cache")

  def testItRaisesAnErrorAndDoesNotCopyDataWhenTheDataIsInvalid(self):
    self.ocdid_extractor.github_file = "country-ar.csv"
    self.ocdid_extractor._verify_data = MagicMock(return_value=False)
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", MagicMock()), patch(
        "io.open", MagicMock()
    ), patch("shutil.copy", mock_copy), self.assertRaises(
        loggers.ElectionError
    ):
      self.ocdid_extractor._download_data("/usr/cache")

    self.assertEqual(0, mock_copy.call_count)

  # _get_ocd_data tests
  def testParsesLocalCSVFileIfProvidedAndReturnsOCDIDs(self):
    # set local file so that countries_file is set to local

    with patch("{}.open".format(self.builtins_name), self.mock_open_func):
      self.ocdid_extractor.local_file = open("/path/to/file")

    codes = self.ocdid_extractor._get_ocd_data()

    expected_codes = set(["ocd-division/country:ar"])

    self.assertEqual(expected_codes, codes)

  def testDownloadsDataIfNoLocalFileAndNoCachedFile(self):
    # mock os call to return file path to be used for countries_file
    mock_expanduser = MagicMock(return_value="/usr/cache")
    # 1st call checks for existence of countries_file - return false
    # 2nd call to os.path.exists check for cache directory - return true
    mock_exists = MagicMock(side_effect=[False, True])

    # stub out live call to github api
    mock_github = create_autospec(github.Github)
    mock_github.get_repo = MagicMock()

    self.ocdid_extractor.github_file = "country-ar.csv"
    self.ocdid_extractor._download_data = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("os.path.expanduser", mock_expanduser), patch(
        "os.path.exists", mock_exists
    ), patch("github.Github", mock_github), patch(
        "{}.open".format(self.builtins_name), self.mock_open_func
    ):
      codes = self.ocdid_extractor._get_ocd_data()

    expected_codes = set(["ocd-division/country:ar"])

    self.assertTrue(
        mock_github.get_repo.called_with(self.ocdid_extractor.GITHUB_REPO)
    )
    self.assertTrue(
        self.ocdid_extractor._download_data.called_with(
            "/usr/cache/country-ar.csv"
        )
    )
    self.assertEqual(expected_codes, codes)

  def testDownloadsDataIfCachedFileIsStale(self):
    # mock os call to return file path to be used for countries_file
    mock_expanduser = MagicMock(return_value="/usr/cache")
    # call to os.path.exists checks for existence of countries_file-return True
    mock_exists = MagicMock(return_value=True)

    # set modification date to be over an hour behind current time
    stale_time = datetime.datetime.now() - datetime.timedelta(minutes=62)
    mock_timestamp = time.mktime(stale_time.timetuple())
    mock_getmtime = MagicMock(return_value=mock_timestamp)

    # stub out live call to github api
    mock_github = create_autospec(github.Github)
    mock_github.get_repo = MagicMock()

    # mock update time function on countries file to make sure it's being called
    mock_utime = MagicMock()

    self.ocdid_extractor.github_file = "country-ar.csv"
    self.ocdid_extractor._download_data = MagicMock()
    self.ocdid_extractor._get_latest_commit_date = MagicMock(
        return_value=datetime.datetime.now()
    )

    # pylint: disable=g-backslash-continuation
    with patch("os.path.expanduser", mock_expanduser), patch(
        "os.path.exists", mock_exists
    ), patch("github.Github", mock_github), patch(
        "{}.open".format(self.builtins_name), self.mock_open_func
    ), patch(
        "os.path.getmtime", mock_getmtime
    ), patch(
        "os.utime", MagicMock()
    ):
      codes = self.ocdid_extractor._get_ocd_data()

    expected_codes = set(["ocd-division/country:ar"])

    self.assertTrue(
        mock_github.get_repo.called_with(self.ocdid_extractor.GITHUB_REPO)
    )
    self.assertTrue(self.ocdid_extractor._get_latest_commit_date.called_once)
    self.assertTrue(mock_utime.called_once)
    self.assertTrue(
        self.ocdid_extractor._download_data.called_with(
            "/usr/cache/country-ar.csv"
        )
    )
    self.assertEqual(expected_codes, codes)

  # _verify_data tests
  def testItReturnsTrueWhenTheFileShasMatch(self):
    mock_sha1 = MagicMock
    mock_sha1.update = MagicMock()
    mock_sha1.hexdigest = MagicMock(return_value="abc123")

    mock_stat = MagicMock()
    self.ocdid_extractor._get_latest_file_blob_sha = MagicMock(
        return_value="abc123"
    )
    # pylint: disable=g-backslash-continuation
    with patch("os.stat", mock_stat), patch("hashlib.sha1", mock_sha1), patch(
        "io.open", self.mock_open_func
    ):
      valid = self.ocdid_extractor._verify_data("/usr/cache/country-ar.tmp")

    self.assertTrue(valid)
    self.assertEqual(3, mock_sha1.update.call_count)

  def testItReturnsFalseWhenTheFileShasDontMatch(self):
    mock_sha1 = MagicMock
    mock_sha1.update = MagicMock()
    mock_sha1.hexdigest = MagicMock(return_value="abc123")

    mock_stat = MagicMock()
    self.ocdid_extractor._get_latest_file_blob_sha = MagicMock(
        return_value="abc456"
    )

    # pylint: disable=g-backslash-continuation
    with patch("os.stat", mock_stat), patch("hashlib.sha1", mock_sha1), patch(
        "io.open", self.mock_open_func
    ):
      valid = self.ocdid_extractor._verify_data("/usr/cache/country-ar.tmp")

    self.assertFalse(valid)
    self.assertEqual(3, mock_sha1.update.call_count)

  # _get_latest_file_blob_sha tests
  def testItReturnsTheBlobShaOfTheGithubFileWhenFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({"name": "country-ar.csv", "sha": "abc123"}), None
    )
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_contents = MagicMock(return_value=[content_file])
    self.ocdid_extractor.github_repo = repo
    self.ocdid_extractor.github_file = "country-ar.csv"

    blob_sha = self.ocdid_extractor._get_latest_file_blob_sha()
    self.assertEqual("abc123", blob_sha)

  def testItReturnsNoneIfTheFileCantBeFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({"name": "country-ar.csv", "sha": "abc123"}), None
    )
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_contents = MagicMock(return_value=[content_file])
    self.ocdid_extractor.github_repo = repo
    self.ocdid_extractor.github_file = "country-us.csv"

    blob_sha = self.ocdid_extractor._get_latest_file_blob_sha()
    self.assertIsNone(blob_sha)


if __name__ == "__main__":
  absltest.main()

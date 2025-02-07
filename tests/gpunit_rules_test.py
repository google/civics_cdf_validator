# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import io

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator import gpunit_rules
from mock import call
from mock import MagicMock
from mock import patch


_US_COUNTRY_CODE = "us"
_EU_COUNTRY_CODE = "eu"
_CACHE_DIRECTORY = "~/.cache"


def generate_config(
    country_code: str,
) -> gpunit_rules.OcdIdsExtractor.OcdIdsExtractorConfig:
  return gpunit_rules.OcdIdsExtractor.OcdIdsExtractorConfig(
      country_code=country_code,
      github_filename="country-{0}.csv".format(country_code),
      local_filepath="{0}/country-{1}.csv".format(
          _CACHE_DIRECTORY, country_code
      ),
      github_raw_url=(
          "https://raw.github.com/opencivicdata/ocd-division-ids/master/identifiers/country-{0}.csv"
          .format(country_code)
      ),
  )


def rewind_clock(minutes: int) -> float:
  now_utc = datetime.datetime.now(datetime.timezone.utc)
  past_time = now_utc - datetime.timedelta(minutes=minutes)
  return past_time.timestamp()


def generate_temp_file_path(filepath: str) -> str:
  return "{0}.tmp".format(filepath)


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
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWithInvalidCharacter_returnsFalse(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland*d"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWIthMissingOcdId_returnsFalse(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:kärnten_west"
    non_existant_ocd_id = (
        "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    )
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(non_existant_ocd_id))

  def testIsValidOcdIdWithValidId_returnsTrue(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWithValidCountryId_returnsTrue(self):
    ocd_value = "ocd-division/country:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWithInvalidCountryId_returnsFalse(self):
    ocd_value = "ocd-division/country:lan"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWithRegionId_returnsTrue(self):
    ocd_value = "ocd-division/region:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )
    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def testIsValidOcdIdWithStateId_returnsTrue(self):
    ocd_value = "ocd-division/country:us/state:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, set([ocd_value])
    )
    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

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
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        country_code="us",
        local_file=local_file,
        ocd_id_list=list_of_ids,
    )

    self.assertEqual(ocd_id_validator.ocd_ids, set(list_of_ids))


class OcdIdsExtractorTest(parameterized.TestCase, absltest.TestCase):

  def testOcdIdsExtractor_setsDefaultValues(self):
    extractor = gpunit_rules.OcdIdsExtractor()

    self.assertIsNone(extractor.country_code)
    self.assertIsNone(extractor.local_file)

  def testOcdIdsExtractor_SetOCDsToResultOfGetOcdData(self):
    expected_ocd_ids = set(["ocdid1", "ocdid2"])
    mock = MagicMock(return_value=expected_ocd_ids)
    extractor = gpunit_rules.OcdIdsExtractor()
    extractor._get_ocd_data = mock
    extractor.local_file = "://file/path"

    actual_ocd_ids = extractor.extract()

    mock.assert_called_once()
    self.assertEqual(expected_ocd_ids, actual_ocd_ids)

  @parameterized.named_parameters([
      (
          "_returnsExpected",
          "id\nocd-division/country:us\n",
          set(["ocd-division/country:us"]),
      ),
      ("_returnsEmpty", "name,sameAsNote\nUnited States,Other note\n", set()),
  ])
  def testReadCsv(self, csv_data, expected):
    config = generate_config(_US_COUNTRY_CODE)
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    mock_io_open = MagicMock(return_value=io.StringIO(csv_data))

    with patch("io.open", mock_io_open):
      actual = extractor._read_csv([config])

    mock_io_open.assert_called_once_with(
        config.local_filepath, encoding="utf-8", mode="r"
    )
    self.assertEqual(actual, expected)

  def testDownloadData_downloadsDataFromGithub(self):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    config = generate_config(_US_COUNTRY_CODE)
    local_tmp_filepath = "{0}.tmp".format(config.local_filepath)
    mock_io_open = MagicMock(
        return_value=io.StringIO("id\nocd-division/country:us\n")
    )
    mock_request = MagicMock()
    mock_copy = MagicMock()
    mock_os_remove = MagicMock()

    with patch("requests.get", mock_request), patch(
        "io.open", mock_io_open
    ), patch("shutil.copy", mock_copy), patch("os.remove", mock_os_remove):
      extractor._download_data([config])

    mock_request.assert_called_once_with(config.github_raw_url)
    mock_io_open.assert_called_once_with(local_tmp_filepath, mode="wb")
    mock_copy.assert_called_once_with(local_tmp_filepath, config.local_filepath)
    mock_os_remove.assert_called_once_with(local_tmp_filepath)

  @parameterized.named_parameters([
      (
          "_forSingularCountry",
          _US_COUNTRY_CODE,
          [generate_config(_US_COUNTRY_CODE)],
      ),
      (
          "_forEuSupranaturalOrganization",
          _EU_COUNTRY_CODE,
          [
              generate_config(country)
              for country in gpunit_rules.OcdIdsExtractor.EU_COUNTRIES
          ],
      ),
  ])
  def testGenerateConfigs(self, country_code, expected):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=country_code,
        local_file=None,
    )

    actual = extractor._generate_configs(country_code, _CACHE_DIRECTORY)

    self.assertEqual(expected, actual)

  def testCheckCacheFreshnessWithNonExistentCacheFile_returnsExpected(self):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    config = generate_config(_US_COUNTRY_CODE)
    mock_os_path_exists = MagicMock(return_value=False)

    with patch("os.path.exists", mock_os_path_exists):
      actual = extractor._check_cache_freshness([config])

    mock_os_path_exists.assert_called_once_with(config.local_filepath)
    self.assertEqual(actual, [config])

  @parameterized.named_parameters([
      (
          "_freshCacheFile",
          15,
          [],
      ),
      (
          "_staleCacheFile",
          75,
          [generate_config(_US_COUNTRY_CODE)],
      ),
  ])
  def testCheckCacheFreshness(self, rewind_in_minutes, expected):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    config = generate_config(_US_COUNTRY_CODE)
    mock_os_path_exists = MagicMock(return_value=True)
    mock_os_path_getmtime = MagicMock(
        return_value=rewind_clock(rewind_in_minutes)
    )

    with patch("os.path.exists", mock_os_path_exists), patch(
        "os.path.getmtime", mock_os_path_getmtime
    ):
      actual = extractor._check_cache_freshness([config])

    mock_os_path_exists.assert_called_once_with(config.local_filepath)
    mock_os_path_getmtime.assert_called_once_with(config.local_filepath)
    self.assertEqual(actual, expected)

  def testCreateCacheWithExistingCacheDirectory_doesNotCreateCache(self):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    mock_os_path_exists = MagicMock(return_value=True)
    mock_os_makedirs = MagicMock()

    with patch("os.path.exists", mock_os_path_exists), patch(
        "os.makedirs", mock_os_makedirs
    ):
      extractor._create_cache(_CACHE_DIRECTORY)

    mock_os_path_exists.assert_called_once_with(_CACHE_DIRECTORY)
    mock_os_makedirs.assert_not_called()

  def testCreateCacheWithNonExistentCacheDirectory_createsCache(self):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    mock_os_path_exists = MagicMock(return_value=False)
    mock_os_makedirs = MagicMock()

    with patch("os.path.exists", mock_os_path_exists), patch(
        "os.makedirs", mock_os_makedirs
    ):
      extractor._create_cache(_CACHE_DIRECTORY)

    mock_os_path_exists.assert_called_once_with(_CACHE_DIRECTORY)
    mock_os_makedirs.assert_called_once_with(_CACHE_DIRECTORY)

  def testGetOcdDataWithLocalFile_returnsExpected(self):
    local_filepath = "://file/path"
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=local_filepath,
    )
    mock_os_path_expanduser = MagicMock(return_value=_CACHE_DIRECTORY)
    mock_io_open = MagicMock(
        return_value=io.StringIO("id\nocd-division/country:us\n")
    )

    with patch("os.path.expanduser", mock_os_path_expanduser), patch(
        "io.open", mock_io_open
    ):
      actual = extractor._get_ocd_data()

    mock_os_path_expanduser.assert_not_called()
    mock_io_open.assert_called_once_with(
        local_filepath, encoding="utf-8", mode="r"
    )
    self.assertEqual(actual, set(["ocd-division/country:us"]))

  def testGetOcdDataWithNonExistingCacheDirectory_returnsExpected(self):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_EU_COUNTRY_CODE,
        local_file=None,
    )
    configs = [generate_config(country) for country in extractor.EU_COUNTRIES]
    mock_os_path_expanduser = MagicMock(return_value=_CACHE_DIRECTORY)
    # Generate a False response for each EU country and an extra one for the
    # cache directory check.
    mock_os_path_exists = MagicMock(
        side_effect=([False] * (len(extractor.EU_COUNTRIES) + 1))
    )
    mock_os_makedirs = MagicMock()
    mock_request_get = MagicMock()
    mock_io_open = MagicMock()
    mock_copy = MagicMock()
    mock_os_remove = MagicMock()

    with patch("os.path.expanduser", mock_os_path_expanduser), patch(
        "os.path.exists", mock_os_path_exists
    ), patch("os.makedirs", mock_os_makedirs), patch(
        "requests.get", mock_request_get
    ), patch(
        "io.open", mock_io_open
    ), patch(
        "shutil.copy", mock_copy
    ), patch(
        "os.remove", mock_os_remove
    ):
      actual = extractor._get_ocd_data()

    mock_os_path_expanduser.assert_called_once_with(_CACHE_DIRECTORY)
    # Confirm the cache directory is checked for existence and each EU country's
    # cache file is checked for existence.
    mock_os_path_exists.assert_has_calls(
        [call(_CACHE_DIRECTORY)]
        + [call(config.local_filepath) for config in configs],
        any_order=True,
    )
    mock_os_makedirs.assert_called_once_with(_CACHE_DIRECTORY)
    # Confirm all EU country's Github URLs are requested.
    mock_request_get.assert_has_calls(
        [call(config.github_raw_url) for config in configs], any_order=True
    )
    # Confirm all EU country's cache files are written to.
    # First pass is for writing to the tmp file within _download_data. The
    # second pass is for reading CSV files to combine into a single set within
    # _read_csv.
    first_pass_calls = [
        call(generate_temp_file_path(config.local_filepath), mode="wb")
        for config in configs
    ]
    second_pass_calls = [
        call(config.local_filepath, encoding="utf-8", mode="r")
        for config in configs
    ]
    mock_io_open.assert_has_calls(
        first_pass_calls + second_pass_calls, any_order=True
    )
    # Confirm all EU country's temporary cache files are copied to CSV files.
    mock_copy.assert_has_calls(
        [
            call(
                generate_temp_file_path(config.local_filepath),
                config.local_filepath,
            )
            for config in configs
        ],
        any_order=True,
    )
    # Confirm all EU country's cache files are removed.
    mock_os_remove.assert_has_calls(
        [
            call(generate_temp_file_path(config.local_filepath))
            for config in configs
        ],
        any_order=True,
    )
    self.assertEmpty(actual)


if __name__ == "__main__":
  absltest.main()

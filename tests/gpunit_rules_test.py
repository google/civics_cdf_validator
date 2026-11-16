# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import io
import os
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import patch
import zipfile

from absl.testing import absltest
from absl.testing import parameterized
import attrs
from civics_cdf_validator import gpunit_rules
import freezegun

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


class _FakeOcdId:
  """Non-string object whose string form is an OCD ID."""

  def __init__(self, ocd_id: str) -> None:
    self.ocd_id = ocd_id

  def __str__(self) -> str:
    return self.ocd_id


def build_zip_bytes(entries: dict[str, str]) -> bytes:
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, mode="w") as archive:
    for name, content in entries.items():
      archive.writestr(name, content)
  return buffer.getvalue()


class GpUnitOcdIdValidatorTest(absltest.TestCase):

  def test_is_valid_country_code_invalid_country_returns_false(self):
    ocd_value = "ocd-division/country:usa"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def test_is_valid_country_code_valid_country_returns_true(self):
    ocd_value = "ocd-division/country:us"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def test_is_valid_country_code_wrong_pattern_returns_false(self):
    ocd_value = "ocd-division/wrong_id_pattern"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def test_is_valid_country_code_region_returns_true(self):
    ocd_value = "ocd-division/region:la"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(ocd_value)
    )

  def test_is_valid_ocd_id_wrong_pattern_returns_false(self):
    ocd_value = "regionalwahlkreis:burgenland_sued"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_invalid_character_returns_false(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland*d"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_missing_id_returns_false(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:kärnten_west"
    non_existant_ocd_id = (
        "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    )
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(non_existant_ocd_id))

  def test_is_valid_ocd_id_valid_id_returns_true(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_valid_country_returns_true(self):
    ocd_value = "ocd-division/country:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_invalid_country_returns_false(self):
    ocd_value = "ocd-division/country:lan"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )

    self.assertFalse(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_region_returns_true(self):
    ocd_value = "ocd-division/region:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )
    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_valid_ocd_id_state_returns_true(self):
    ocd_value = "ocd-division/country:us/state:la"
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        "us", None, {ocd_value}
    )
    self.assertTrue(ocd_id_validator.is_valid_ocd_id(ocd_value))

  def test_is_country_or_region_ocd_id_non_string_returns_false(self):
    ocd_value = 1
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def test_is_country_or_region_ocd_id_wrong_pattern_returns_false(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def test_is_country_or_region_ocd_id_country_returns_true(self):
    ocd_value = "ocd-division/country:la"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def test_is_country_or_region_ocd_id_region_returns_true(self):
    ocd_value = "ocd-division/region:eu"
    self.assertTrue(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def test_is_country_or_region_ocd_id_us_region_returns_false(self):
    ocd_value = "ocd-division/region:us"
    self.assertFalse(
        gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(ocd_value)
    )

  def test_initialize_from_list_sets_ocd_ids(self):
    list_of_ids = ["ocd-division/country:la"]
    local_file = io.StringIO("id,\nocd-division/country:us,\n")
    ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
        country_code="us",
        local_file=local_file,
        ocd_id_list=list_of_ids,
    )

    self.assertEqual(ocd_id_validator.ocd_ids, set(list_of_ids))

  def test_initialize_without_list_reads_local_file(self):
    local_file = self.create_tempfile(
        content="id\nocd-division/country:us/state:fake\n"
    ).full_path

    validator = gpunit_rules.GpUnitOcdIdValidator(
        country_code="us",
        local_file=local_file,
    )

    self.assertEqual(validator.ocd_ids, {"ocd-division/country:us/state:fake"})

  def test_is_valid_ocd_id_non_string_value_uses_string_form(self):
    validator = gpunit_rules.GpUnitOcdIdValidator(
        country_code="us",
        local_file=None,
        ocd_id_list=["ocd-division/country:us/state:fake"],
    )

    is_valid = validator.is_valid_ocd_id(
        _FakeOcdId("ocd-division/country:us/state:fake")
    )

    self.assertTrue(is_valid)

  def test_is_valid_country_code_region_not_a_country_returns_true(self):
    ocd_value = "ocd-division/region:eu"

    is_valid = gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(
        ocd_value
    )

    self.assertTrue(is_valid)

  def test_is_valid_country_code_unassigned_country_returns_false(self):
    ocd_value = "ocd-division/country:zz"

    is_valid = gpunit_rules.GpUnitOcdIdValidator.is_valid_country_code(
        ocd_value
    )

    self.assertFalse(is_valid)

  def test_initialize_from_empty_list_sets_empty_ocd_ids_without_extracting(
      self,
  ):
    mock_extractor = MagicMock()
    with patch.object(gpunit_rules, "OcdIdsExtractor", mock_extractor):
      ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
          country_code=None,
          local_file=None,
          ocd_id_list=[],
      )

    mock_extractor.assert_not_called()
    self.assertEmpty(ocd_id_validator.ocd_ids)

  def test_initialize_without_country_passes_none_to_extractor(self):
    mock_extractor = MagicMock()
    mock_extractor.return_value.extract.return_value = {
        "ocd-division/country:de"
    }
    with patch.object(gpunit_rules, "OcdIdsExtractor", mock_extractor):
      ocd_id_validator = gpunit_rules.GpUnitOcdIdValidator(
          country_code=None,
          local_file=None,
      )

    mock_extractor.assert_called_once_with(None, None)
    self.assertEqual(ocd_id_validator.ocd_ids, {"ocd-division/country:de"})


class OcdIdsExtractorTest(parameterized.TestCase, absltest.TestCase):

  def test_extractor_init_sets_default_values(self):
    extractor = gpunit_rules.OcdIdsExtractor()

    self.assertIsNone(extractor.country_code)
    self.assertIsNone(extractor.local_file)

  def test_extract_returns_ocd_ids(self):
    expected_ocd_ids = {"ocdid1", "ocdid2"}
    mock = MagicMock(return_value=expected_ocd_ids)
    extractor = gpunit_rules.OcdIdsExtractor()
    extractor._get_ocd_data = mock
    extractor.local_file = "://file/path"

    actual_ocd_ids = extractor.extract()

    mock.assert_called_once()
    self.assertEqual(actual_ocd_ids, expected_ocd_ids)

  @parameterized.named_parameters([
      (
          "_returns_expected",
          "id\nocd-division/country:us\n",
          {"ocd-division/country:us"},
      ),
      ("_returns_empty", "name,sameAsNote\nUnited States,Other note\n", set()),
  ])
  def test_read_csv_returns_expected_set(self, csv_data, expected):
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

  def test_download_data_downloads_from_github(self):
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
          "_for_singular_country",
          _US_COUNTRY_CODE,
          [generate_config(_US_COUNTRY_CODE)],
      ),
      (
          "_for_eu_supranational_organization",
          _EU_COUNTRY_CODE,
          [
              generate_config(country)
              for country in gpunit_rules.OcdIdsExtractor.EU_COUNTRIES
          ],
      ),
  ])
  def test_generate_configs_returns_expected(self, country_code, expected):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=country_code,
        local_file=None,
    )

    actual = extractor._generate_configs(country_code, _CACHE_DIRECTORY)

    self.assertEqual(actual, expected)

  def test_check_cache_freshness_missing_file_returns_config(self):
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
          "_fresh_cache_file",
          15,
          [],
      ),
      (
          "_stale_cache_file",
          75,
          [generate_config(_US_COUNTRY_CODE)],
      ),
  ])
  def test_check_cache_freshness_returns_expected(
      self, rewind_in_minutes, expected
  ):
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

  def test_extractor_config_is_immutable(self):
    config = generate_config(_US_COUNTRY_CODE)

    with self.assertRaises(attrs.exceptions.FrozenInstanceError):
      config.country_code = "fake"

  def test_download_data_writes_downloaded_content_to_cache_file(self):
    cache_directory = self.create_tempdir().full_path
    config = gpunit_rules.OcdIdsExtractor.OcdIdsExtractorConfig(
        country_code=_US_COUNTRY_CODE,
        github_filename="country-us.csv",
        github_raw_url="http://www.fake.com/country-us.csv",
        local_filepath=f"{cache_directory}/country-us.csv",
    )
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [
        b"id\n",
        b"ocd-division/country:us/state:fake\n",
    ]

    with patch("requests.get", MagicMock(return_value=mock_response)):
      extractor._download_data([config])

    with open(config.local_filepath, encoding="utf-8") as cache_file:
      cache_content = cache_file.read()
    self.assertEqual(cache_content, "id\nocd-division/country:us/state:fake\n")
    self.assertFalse(
        os.path.exists(generate_temp_file_path(config.local_filepath))
    )

  @parameterized.named_parameters([
      ("_exactly_one_hour_old_is_fresh", 3600, []),
      (
          "_just_over_one_hour_old_is_stale",
          3601,
          [generate_config(_US_COUNTRY_CODE)],
      ),
  ])
  @freezegun.freeze_time("2026-01-01 12:00:00")
  def test_check_cache_freshness_at_one_hour_boundary_returns_expected(
      self, age_in_seconds, expected
  ):
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    config = generate_config(_US_COUNTRY_CODE)
    now_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
    modification_timestamp = now_timestamp - age_in_seconds

    with patch("os.path.exists", MagicMock(return_value=True)), patch(
        "os.path.getmtime", MagicMock(return_value=modification_timestamp)
    ):
      actual = extractor._check_cache_freshness([config])

    self.assertEqual(actual, expected)

  def test_create_cache_directory_exists_does_not_create(self):
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

  def test_create_cache_directory_missing_creates(self):
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

  def test_get_ocd_data_with_local_file_returns_expected(self):
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
    self.assertEqual(actual, {"ocd-division/country:us"})

  def test_get_ocd_data_missing_cache_directory_returns_expected(self):
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

  def test_get_ocd_data_without_country_downloads_archive_and_extracts_csvs(
      self,
  ):
    cache_directory = self.create_tempdir().full_path
    archive_bytes = build_zip_bytes({
        "ocd-division-ids-master/identifiers/country-us.csv": (
            "id\nocd-division/country:us\n"
        ),
        "ocd-division-ids-master/identifiers/country-de.csv": (
            "id\nocd-division/country:de\n"
        ),
        "ocd-division-ids-master/identifiers/country-eu.csv": (
            "id\nocd-division/region:eu\n"
        ),
        "ocd-division-ids-master/identifiers/country-ad/top_level.csv": (
            "id\nocd-division/country:ad/ignored_subdir\n"
        ),
        "ocd-division-ids-master/README.md": "ignored",
    })
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [archive_bytes]
    mock_request_get = MagicMock(return_value=mock_response)
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=None,
        local_file=None,
    )

    with patch("os.path.expanduser", MagicMock(return_value=cache_directory)), (
        patch("requests.get", mock_request_get)
    ):
      actual = extractor._get_ocd_data()

    mock_request_get.assert_called_once_with(
        "https://github.com/opencivicdata/ocd-division-ids/archive/refs/heads/master.zip"
    )
    self.assertTrue(
        os.path.exists(f"{cache_directory}/ocd-division-ids-master.zip")
    )
    self.assertTrue(os.path.exists(f"{cache_directory}/country-de.csv"))
    self.assertEqual(
        actual,
        {
            "ocd-division/country:us",
            "ocd-division/country:de",
            "ocd-division/region:eu",
        },
    )

  def test_get_ocd_data_with_empty_country_and_fresh_archive_skips_download(
      self,
  ):
    cache_directory = self.create_tempdir().full_path
    archive_filepath = f"{cache_directory}/ocd-division-ids-master.zip"
    with io.open(archive_filepath, mode="wb") as fd:
      fd.write(
          build_zip_bytes({
              "ocd-division-ids-master/identifiers/country-de.csv": (
                  "id\nocd-division/country:de/from_archive\n"
              ),
          })
      )
    with io.open(
        f"{cache_directory}/country-de.csv",
        encoding="utf-8",
        mode="w",
    ) as fd:
      fd.write("id\nocd-division/country:de\n")
    mock_request_get = MagicMock()
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code="",
        local_file=None,
    )

    with patch("os.path.expanduser", MagicMock(return_value=cache_directory)), (
        patch("requests.get", mock_request_get)
    ):
      actual = extractor._get_ocd_data()

    mock_request_get.assert_not_called()
    self.assertEqual(actual, {"ocd-division/country:de"})

  def test_get_ocd_data_without_country_and_stale_archive_redownloads(self):
    cache_directory = self.create_tempdir().full_path
    archive_filepath = f"{cache_directory}/ocd-division-ids-master.zip"
    with io.open(archive_filepath, mode="wb") as fd:
      fd.write(
          build_zip_bytes({
              "ocd-division-ids-master/identifiers/country-de.csv": (
                  "id\nocd-division/country:de/stale\n"
              ),
          })
      )
    stale_timestamp = rewind_clock(75)
    os.utime(archive_filepath, (stale_timestamp, stale_timestamp))
    with io.open(
        f"{cache_directory}/country-de.csv",
        encoding="utf-8",
        mode="w",
    ) as fd:
      fd.write("id\nocd-division/country:de/stale\n")
    fresh_archive_bytes = build_zip_bytes({
        "ocd-division-ids-master/identifiers/country-de.csv": (
            "id\nocd-division/country:de/fresh\n"
        ),
    })
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [fresh_archive_bytes]
    mock_request_get = MagicMock(return_value=mock_response)
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=None,
        local_file=None,
    )

    with patch("os.path.expanduser", MagicMock(return_value=cache_directory)), (
        patch("requests.get", mock_request_get)
    ):
      actual = extractor._get_ocd_data()

    mock_request_get.assert_called_once_with(
        "https://github.com/opencivicdata/ocd-division-ids/archive/refs/heads/master.zip"
    )
    self.assertEqual(actual, {"ocd-division/country:de/fresh"})

  def test_download_data_http_error_raises_without_writing_cache(self):
    cache_directory = self.create_tempdir().full_path
    config = gpunit_rules.OcdIdsExtractor.OcdIdsExtractorConfig(
        country_code=_US_COUNTRY_CODE,
        github_filename="country-us.csv",
        github_raw_url="http://www.fake.com/country-us.csv",
        local_filepath=f"{cache_directory}/country-us.csv",
    )
    extractor = gpunit_rules.OcdIdsExtractor(
        country_code=_US_COUNTRY_CODE,
        local_file=None,
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = (
        gpunit_rules.requests.HTTPError("500 Server Error")
    )

    with patch("requests.get", MagicMock(return_value=mock_response)):
      with self.assertRaises(gpunit_rules.requests.HTTPError):
        extractor._download_data([config])

    self.assertFalse(os.path.exists(config.local_filepath))
    self.assertFalse(
        os.path.exists(generate_temp_file_path(config.local_filepath))
    )


if __name__ == "__main__":
  absltest.main()

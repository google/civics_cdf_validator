# -*- coding: utf-8 -*-
"""Unit test for rule_util.py."""

from absl.testing import absltest
from absl.testing import parameterized
from civics_cdf_validator.rulesets import rule_util
from lxml import etree


class HelpersTest(absltest.TestCase):

  # get_external_id_values tests
  def test_get_external_id_values_returns_values(self):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_id = "ocd-division/country:us/state:ma"
    expected_other_stable = "stable-gpu-abc123"

    actual_ocd_ids = rule_util.get_external_id_values(gp_unit_elem, "ocd-id")
    actual_stable_ids = rule_util.get_external_id_values(gp_unit_elem, "stable")

    self.assertEqual(actual_ocd_ids, [expected_ocd_id])
    self.assertEqual(actual_stable_ids, [expected_other_stable])

  def test_get_external_id_values_with_return_elements_returns_elements(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>stable</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_id = b"<Value>ocd-division/country:us/state:ma</Value>"
    expected_other_stable = b"<Value>stable-gpu-abc123</Value>"

    actual_ocd_ids = rule_util.get_external_id_values(
        gp_unit_elem, "ocd-id", True
    )
    actual_stable = rule_util.get_external_id_values(
        gp_unit_elem, "stable", True
    )

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(etree.tostring(actual_ocd_ids[0]).strip(), expected_ocd_id)
    self.assertLen(actual_stable, 1)
    self.assertEqual(
        etree.tostring(actual_stable[0]).strip(), expected_other_stable
    )

  def test_get_external_id_values_with_invalid_types_returns_empty_list(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>blamo</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>ocd-id</OtherType>
            <Value>stable-gpu-abc123</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)

    invalid_type_values = rule_util.get_external_id_values(
        gp_unit_elem, "blamo"
    )
    other_type_values = rule_util.get_external_id_values(gp_unit_elem, "ocd-id")

    self.assertEmpty(invalid_type_values)
    self.assertEmpty(other_type_values)

  # get_additional_type_values tests
  def test_get_additional_type_values_returns_values(self):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">ocd-division/country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)
    expected_ocd_id = "ocd-division/country:us"

    actual_ocd_ids = rule_util.get_additional_type_values(office_elem, "ocd-id")

    self.assertEqual(actual_ocd_ids, [expected_ocd_id])

  def test_get_additional_type_values_with_return_elements_returns_elements(
      self,
  ):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id">country:us</AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)
    expected = b'<AdditionalData type="ocd-id">country:us</AdditionalData>'

    actual_ocd_ids = rule_util.get_additional_type_values(
        office_elem, "ocd-id", True
    )
    actual_ocd_id = etree.tostring(actual_ocd_ids[0]).strip()

    self.assertLen(actual_ocd_ids, 1)
    self.assertEqual(actual_ocd_id, expected)

  def test_get_additional_type_values_with_missing_elements_returns_empty_list(
      self,
  ):
    office = """
      <Office objectId="off-0">
        <AdditionalData type="ocd-id"></AdditionalData>
      </Office>
    """
    office_elem = etree.fromstring(office)

    actual_ocd_ids = rule_util.get_additional_type_values(office_elem, "ocd-id")
    not_found = rule_util.get_additional_type_values(office_elem, "not-found")

    self.assertEmpty(actual_ocd_ids)
    self.assertEmpty(not_found)

  # get_entity_info_for_value_type tests
  def test_get_entity_info_for_value_type_returns_values(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>external-id-ocd-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <AdditionalData type="ocd-id">addtl-data-ocd-id</AdditionalData>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_ocd_ids = ["addtl-data-ocd-id", "external-id-ocd-id"]

    actual_ocd_ids = rule_util.get_entity_info_for_value_type(
        gp_unit_elem, "ocd-id"
    )

    self.assertEqual(actual_ocd_ids, expected_ocd_ids)

  def test_get_entity_info_for_value_type_with_return_elements_returns_elements(
      self,
  ):
    gp_unit = """
      <GpUnit objectId="gpu0">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>external-id</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
        <AdditionalData type="ocd-id">addtl-data</AdditionalData>
      </GpUnit>
    """
    gp_unit_elem = etree.fromstring(gp_unit)
    expected_data = b'<AdditionalData type="ocd-id">addtl-data</AdditionalData>'
    expected_external = b"<Value>external-id</Value>"

    actual_ocd_ids = rule_util.get_entity_info_for_value_type(
        gp_unit_elem, "ocd-id", True
    )
    actual_data = etree.tostring(actual_ocd_ids[0]).strip()
    actual_external = etree.tostring(actual_ocd_ids[1]).strip()

    self.assertEqual(actual_data, expected_data)
    self.assertEqual(actual_external, expected_external)

  # element_has_text tests
  def test_element_has_text_returns_true(self):
    element_string = "<FirstName>Jerry</FirstName>"

    elem_has_text = rule_util.element_has_text(etree.fromstring(element_string))

    self.assertTrue(elem_has_text)

  def test_element_has_text_when_element_is_none_returns_false(self):
    elem_has_text = rule_util.element_has_text(None)

    self.assertFalse(elem_has_text)

  def test_element_has_text_when_element_is_empty_returns_false(self):
    element_string = "<FirstName></FirstName>"

    elem_has_text = rule_util.element_has_text(etree.fromstring(element_string))

    self.assertFalse(elem_has_text)

  def test_element_has_text_when_element_is_whitespace_returns_false(self):
    element_string = "<FirstName>   </FirstName>"

    elem_has_text = rule_util.element_has_text(etree.fromstring(element_string))

    self.assertFalse(elem_has_text)


class GetAdditionalTypeValuesTest(absltest.TestCase):

  def test_get_additional_type_values_with_no_elements_returns_empty_list(self):
    root = etree.fromstring("<Office></Office>")
    elements = rule_util.get_additional_type_values(
        root, "jurisdiction-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_no_values_returns_empty_list(self):
    root = etree.fromstring("""
      <Office>
        <AdditionalData type="jurisdiction-id"></AdditionalData>
      </Office>
    """)
    elements = rule_util.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_whitespace_value_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <Office>
        <AdditionalData type="jurisdiction-id">      </AdditionalData>
      </Office>
    """)
    elements = rule_util.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_no_type_attribute_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <Office>
        <AdditionalData>ru-gpu2</AdditionalData>
      </Office>
    """)
    elements = rule_util.get_additional_type_values(root, "jurisdiction-id")

    self.assertEmpty(elements, 0)

  def test_get_additional_type_values_with_return_elements_returns_elements(
      self,
  ):
    root = etree.fromstring("""
      <OfficeCollection>
        <Office>
          <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
        </Office>
        <Office>
          <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
        </Office>
      </OfficeCollection>
    """)
    elements = rule_util.get_additional_type_values(
        root, "jurisdiction-id", return_elements=True
    )

    self.assertLen(elements, 2)
    self.assertEqual(elements[0].text, "ru-gpu2")
    self.assertEqual(elements[1].text, "ru-gpu3")

  def test_get_additional_type_values_returns_values(self):
    root = etree.fromstring("""
      <OfficeCollection>
        <Office>
          <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
        </Office>
        <Office>
          <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
        </Office>
      </OfficeCollection>
    """)
    elements = rule_util.get_additional_type_values(root, "jurisdiction-id")

    self.assertEqual(elements, ["ru-gpu2", "ru-gpu3"])


class GetExternalIDValuesTest(parameterized.TestCase):

  def test_get_external_id_values_with_empty_type_and_no_ids_returns_empty_list(
      self,
  ):
    root = etree.fromstring("<ExternalIdentifiers></ExternalIdentifiers>")
    elements = rule_util.get_external_id_values(root, "")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_no_ids_returns_empty_list(self):
    root = etree.fromstring("<ExternalIdentifiers></ExternalIdentifiers>")
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_no_type_element_returns_empty_list(self):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_missing_text_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type></Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_is_whitespace_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>                   </Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_value_is_missing_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value></Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_empty_type_and_no_ids_returns_empty_elements(
      self,
  ):
    root = etree.fromstring("<ExternalIdentifiers></ExternalIdentifiers>")
    elements = rule_util.get_external_id_values(root, "", return_elements=True)

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_no_ids_returns_empty_elements(self):
    root = etree.fromstring("<ExternalIdentifiers></ExternalIdentifiers>")
    elements = rule_util.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_no_type_element_returns_empty_elements(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_missing_text_returns_empty_elements(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type></Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_is_whitespace_returns_empty_elements(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>                   </Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_type_element_value_is_missing_returns_empty_elements(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value></Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, "ocd-id", return_elements=True
    )
    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_missing_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_missing_text_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType></OtherType>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_when_other_type_element_is_whitespace_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>          </OtherType>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "something-else")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_with_mismatched_other_type_returns_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>ocd-id</OtherType>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertEmpty(elements, 0)

  def test_get_external_id_values_ignores_other_type_of_non_other_identifier(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <OtherType>fake-type</OtherType>
          <Value>fake-value</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)

    values = rule_util.get_external_id_values(root, "fake-type")

    self.assertEmpty(values)

  def test_get_external_id_values_when_value_is_whitespace_returns_non_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>ocd-id</Type>
          <Value>       </Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "ocd-id")

    self.assertLen(elements, 1)
    self.assertIsInstance(elements[0], str)

  def test_get_external_id_values_when_other_type_value_is_whitespace_returns_non_empty_list(
      self,
  ):
    root = etree.fromstring("""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>something-else</OtherType>
          <Value>    </Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, "something-else")

    self.assertLen(elements, 1)
    self.assertIsInstance(elements[0], str)

  @parameterized.parameters(
      "local-level", "national-level", "ocd-id", "state-level"
  )
  def test_get_external_id_values_with_return_elements_returns_all_valid_elements(
      self, en_type
  ):
    root = etree.fromstring(f"""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>{en_type}</Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>{en_type}</Type>
          <Value>ocd-division/country:us/state:ma</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, en_type, return_elements=True
    )

    self.assertLen(elements, 2)
    self.assertEqual(elements[0].text, "ocd-division/country:us/state:va")
    self.assertEqual(elements[1].text, "ocd-division/country:us/state:ma")

  @parameterized.parameters(
      "local-level", "national-level", "ocd-id", "state-level"
  )
  def test_get_external_id_values_returns_all_valid_values(self, en_type):
    root = etree.fromstring(f"""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>{en_type}</Type>
          <Value>ocd-division/country:us/state:va</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>{en_type}</Type>
          <Value>ocd-division/country:us/state:ma</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, en_type)

    self.assertEqual(
        elements,
        [
            "ocd-division/country:us/state:va",
            "ocd-division/country:us/state:ma",
        ],
    )

  @parameterized.parameters("hi", "there")
  def test_get_external_id_values_with_return_elements_returns_other_type_elements(
      self, other_type
  ):
    root = etree.fromstring(f"""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>{other_type}</OtherType>
          <Value>hi</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>{other_type}</OtherType>
          <Value>there</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(
        root, other_type, return_elements=True
    )

    self.assertLen(elements, 2)
    self.assertEqual(elements[0].text, "hi")
    self.assertEqual(elements[1].text, "there")

  @parameterized.parameters("hi", "there")
  def test_get_external_id_values_returns_other_type_values(self, other_type):
    root = etree.fromstring(f"""
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>{other_type}</OtherType>
          <Value>hi</Value>
        </ExternalIdentifier>
        <ExternalIdentifier>
          <Type>other</Type>
          <OtherType>{other_type}</OtherType>
          <Value>there</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """)
    elements = rule_util.get_external_id_values(root, other_type)

    self.assertEqual(elements, ["hi", "there"])


class GetLanguageToTextMapTest(absltest.TestCase):

  def test_get_language_to_text_map_groups_text_by_language(self):
    name = etree.fromstring("""
      <Name>
        <Text language="en">Fake Name</Text>
        <Text language="es">Nombre Falso</Text>
        <Text language="en">Other Fake Name</Text>
      </Name>
    """)

    language_map = rule_util.get_language_to_text_map(name)

    self.assertEqual(
        language_map,
        {"en": ["Fake Name", "Other Fake Name"], "es": ["Nombre Falso"]},
    )

  def test_get_language_to_text_map_skips_text_without_content(self):
    name = etree.fromstring("""
      <Name>
        <Text language="en"></Text>
        <Text language="es">Nombre Falso</Text>
      </Name>
    """)

    language_map = rule_util.get_language_to_text_map(name)

    self.assertEqual(language_map, {"es": ["Nombre Falso"]})

  def test_get_language_to_text_map_skips_text_without_language(self):
    name = etree.fromstring("""
      <Name>
        <Text>Fake Name</Text>
        <Text language="">Other Fake Name</Text>
        <Text language="es">Nombre Falso</Text>
      </Name>
    """)

    language_map = rule_util.get_language_to_text_map(name)

    self.assertEqual(language_map, {"es": ["Nombre Falso"]})

  def test_get_language_to_text_map_none_element_returns_empty_map(self):
    language_map = rule_util.get_language_to_text_map(None)

    self.assertEmpty(language_map)


class GetFloatTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ("integer", "<Count>5</Count>", 5.0),
      ("decimal", "<Count>12.5</Count>", 12.5),
      ("negative", "<Count>-0.5</Count>", -0.5),
      ("exponent", "<Count>1e3</Count>", 1000.0),
      ("surrounding_whitespace", "<Count> 7.25 </Count>", 7.25),
  )
  def test_get_float_returns_float(self, element_string, expected_float):
    element = etree.fromstring(element_string)

    self.assertEqual(rule_util.get_float(element), expected_float)

  @parameterized.named_parameters(
      ("empty", "<Count/>"),
      ("whitespace", "<Count> </Count>"),
      ("word", "<Count>five</Count>"),
  )
  def test_get_float_without_float_text_returns_none(self, element_string):
    element = etree.fromstring(element_string)

    self.assertIsNone(rule_util.get_float(element))

  def test_get_float_none_element_returns_none(self):
    self.assertIsNone(rule_util.get_float(None))


if __name__ == "__main__":
  absltest.main()

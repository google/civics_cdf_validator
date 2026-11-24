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
"""Helper functions and constants shared by validation rules."""

from __future__ import print_function

from lxml import etree
import pycountry


_XML_TRUE_VALUES = frozenset(["true", "1"])

PARTY_LEADERSHIP_TYPES = ["party-leader-id", "party-chair-id"]

_IDENTIFIER_TYPES = frozenset(
    ["local-level", "national-level", "ocd-id", "state-level"]
)


def is_xml_true(element: etree._Element | None) -> bool:
  return (
      element_has_text(element)
      and element.text.strip().lower() in _XML_TRUE_VALUES
  )


def get_external_id_values(
    element: etree._Element | etree._ElementTree,
    value_type: str,
    return_elements: bool = False,
    search_subelements: bool = True,
) -> list[str] | list[etree._Element]:
  """Helper to gather all Values of external ids for a given type.

  If search_subelements is True, will search all subelements, if False, will
  only search child elements.

  Args:
    element: element to be processed
    value_type: external id value type
    return_elements: Boolean if True return elements, if False return values.
    search_subelements: Boolean to instruct the function to recursively search
      subelements.

  Returns:
    A list of external id values or external identifier elements
  """
  external_ids = []
  if search_subelements:
    external_ids = element.findall(".//ExternalIdentifier")
  else:
    external_ids = element.findall("ExternalIdentifiers/ExternalIdentifier")
  values = []
  for extern_id in external_ids:
    id_type = extern_id.find("Type")
    if id_type is None or not id_type.text:
      continue
    matches_type = False
    id_text = id_type.text.strip()
    if id_text in _IDENTIFIER_TYPES and id_text == value_type:
      matches_type = True
    elif id_text == "other":
      other_type = extern_id.find("OtherType")
      if (
          other_type is not None
          and other_type.text
          and other_type.text.strip() == value_type
          and value_type not in _IDENTIFIER_TYPES
      ):
        matches_type = True
    if matches_type:
      value = extern_id.find("Value")
      # Could include empty text; check in calling function.
      # Not checked here because errors should be raised in some cases.
      if value is not None and value.text:
        if return_elements:
          values.append(value)
        else:
          values.append(value.text)
  return values


def get_additional_type_values(
    element: etree._Element, value_type: str, return_elements: bool = False
) -> list[str] | list[etree._Element]:
  """Helper to gather all nested additional type values for a given type."""
  elements = element.findall(f".//AdditionalData[@type='{value_type}']")
  if not return_elements:
    return [
        val.text
        for val in elements
        if val is not None and val.text and val.text.strip()
    ]
  return elements


def get_entity_info_for_value_type(
    element: etree._Element, info_type: str, return_elements: bool = False
) -> list[str] | list[etree._Element]:
  info_collection = get_additional_type_values(
      element, info_type, return_elements
  )
  info_collection.extend(
      list(get_external_id_values(element, info_type, return_elements))
  )
  return info_collection


def get_language_to_text_map(
    element: etree._Element | None,
) -> dict[str, list[str]]:
  """Return a map of languages to text in an InternationalizedText element."""
  language_map = {}
  if element is None:
    return language_map
  intl_strings = element.findall("Text")

  for intl_string in intl_strings:
    text = intl_string.text
    if text is None or not text:
      continue
    language = intl_string.get("language")
    if language is None or not language:
      continue
    if language not in language_map:
      language_map[language] = [text]
    else:
      language_map[language].append(text)
  return language_map


def element_has_text(element: etree._Element | None) -> bool:
  return (
      element is not None
      and element.text is not None
      and not element.text.isspace()
  )


def get_type_or_other_type(element: etree._Element) -> str:
  """Returns the OtherType text if Type is "other", else the Type text."""
  type_element = element.find("Type")
  other_type_element = element.find("OtherType")
  type_text = (
      type_element.text.strip() if element_has_text(type_element) else ""
  )
  other_type_text = (
      other_type_element.text.strip()
      if element_has_text(other_type_element)
      else ""
  )
  return other_type_text if type_text == "other" else type_text


def get_integer(element: etree._Element | None) -> int | None:
  """Returns the element's text as an integer, or None if it isn't one."""
  if not element_has_text(element):
    return None
  try:
    return int(element.text.strip())
  except ValueError:
    return None


def get_float(element: etree._Element | None) -> float | None:
  """Returns the element's text as a float, or None if it isn't one."""
  if not element_has_text(element):
    return None
  try:
    return float(element.text.strip())
  except ValueError:
    return None


def country_code_is_valid(country_code: str) -> bool:
  # EU is part of ISO 3166/MA
  return (
      country_code.lower() == "eu"
      or pycountry.countries.get(alpha_2=country_code.upper()) is not None
  )

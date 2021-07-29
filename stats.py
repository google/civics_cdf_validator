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


class BaseEntity(object):
  """Base for keeping meta-statistics on attributes in a NIST XML feed."""

  def __init__(self, name, attributes, count):
    self.name = name
    self.count = count
    self.attribute_counts = {attr: 0 for attr in attributes}

  def __str__(self):
    """Returns counts of each top level entities and nested attributes."""
    output = []
    row_format = "{:<30s}{:^8s}{:>15s}"
    output.append("\n" + " " * 8 + "-" * 65)
    output.append(" " * 8 + "{:<30s}{:^20s}{:>12s}".format(
        "{0} (Total: {1})".format(self.name, self.count), "| # with attribute",
        "| # missing attribute"))
    output.append(" " * 8 + "-" * 65)
    for attr, attr_count in sorted(
        self.attribute_counts.items(), key=lambda x: x[1], reverse=True):
      output.append(" " * 8 + row_format.format(attr, str(attr_count),
                                                str(self.count - attr_count)))
    return "\n".join(output)

  def increment_attribute(self, attr, count):
    """Counts the number of entities containing attr."""
    if attr in self.attribute_counts and count:
      self.attribute_counts[attr] += 1


class Party(BaseEntity):
  """Class for for keeping meta-stats on Party attributes."""
  children = [
      "Abbreviation", "Color", "ExternalIdentifiers", "Name",
      "InternationalizedAbbreviation"
  ]

  def __init__(self, count):
    super(Party, self).__init__("Party", self.children, count)


class Office(BaseEntity):
  """Class for for keeping meta-stats on Office attributes."""
  children = [
      "ContactInformation", "ElectoralDistrictId", "ExternalIdentifiers",
      "FilingDeadline", "Name", "OfficeHolderPersonIds", "Term"
  ]

  def __init__(self, count):
    super(Office, self).__init__("Office", self.children, count)


class GpUnit(BaseEntity):
  """Class for for keeping meta-stats on GpUnit attributes."""
  children = [
      "ComposingGpUnitIds", "ExternalIdentifiers", "Name", "SummaryCounts"
  ]

  def __init__(self, count):
    super(GpUnit, self).__init__("GpUnit", self.children, count)


class Person(BaseEntity):
  """Class for for keeping meta-stats on Person attributes."""
  children = [
      "ContactInformation", "DateOfBirth", "FirstName", "FullName", "Gender",
      "LastName", "MiddleName", "Nickname", "PartyId", "Prefix", "Profession",
      "Suffix", "Title"
  ]

  def __init__(self, count):
    super(Person, self).__init__("Person", self.children, count)


class Candidate(BaseEntity):
  """Class for for keeping meta-stats on Candidate attributes."""
  children = [
      "BallotName", "ExternalIdentifiers", "FileDate", "IsIncumbent", "PartyId",
      "PersonId"
  ]

  def __init__(self, count):
    super(Candidate, self).__init__("Candidate", self.children, count)


class Contest(BaseEntity):
  """Class for for keeping meta-stats on Contest attributes."""
  children = [
      "BallotSelection", "ElectoralDistrictId", "ExternalIdentifiers", "Name",
      "TotalSubUnits"
  ]

  def __init__(self, count):
    super(Contest, self).__init__("Contest", self.children, count)


ENTITY_STATS = {
    "Party": Party,
    "Office": Office,
    "Person": Person,
    "GpUnit": GpUnit,
    "Candidate": Candidate,
    "Contest": Contest
}

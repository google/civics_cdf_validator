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
"""Validation rules for voter information feeds of the CDF XML validator."""

from __future__ import print_function

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import common_rules


class ElectoralCommissionCollectionExists(base.BaseRule):
  """ElectoralCommissionCollection should exist."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("ElectoralCommissionCollection") is None:
      raise loggers.ElectionError.from_message(
          "ElectoralCommissionCollection should exist.", [element]
      )


class VoterInformationCollectionExists(base.BaseRule):
  """Warn if there is no VoterInformationCollection."""

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("VoterInformationCollection") is None:
      raise loggers.ElectionWarning.from_message(
          "VoterInformationCollection should exist.", [element]
      )


class NoExtraElectionElements(base.BaseRule):
  """Elections for voter information feeds should not have certain elements.

  BallotStyleCollection, CandidateCollection, ContestCollection, CountStatus
  should all be excluded.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    if element.find("BallotStyleCollection") is not None:
      raise loggers.ElectionError.from_message(
          "BallotStyleCollection should not exist.", [element]
      )

    if element.find("CandidateCollection") is not None:
      raise loggers.ElectionError.from_message(
          "CandidateCollection should not exist.", [element]
      )
    if element.find("ContestCollection") is not None:
      raise loggers.ElectionError.from_message(
          "ContestCollection should not exist.", [element]
      )

    if element.find("CountStatus") is not None:
      raise loggers.ElectionError.from_message(
          "CountStatus should not exist.", [element]
      )


class WarnOnElementsNotRecommendedForElection(base.BaseRule):
  """Warn on ContactInformation on an Election for voter information feeds."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    if element.find("ContactInformation") is not None:
      raise loggers.ElectionWarning.from_message(
          "ContactInformation is not recommended for Election, prefer using an"
          " ElectionAdministration.",
          [element],
      )


class NoExtraElectionReportCollections(base.BaseRule):
  """ElectionReports for voter information feeds should not have certain elements.

  CommitteeCollection, GovernmentBodyCollection, OfficeCollection,
  OfficeHolderTenureCollection, PartyCollection, PersonCollection should all be
  excluded.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, element):
    if element.find("CommitteeCollection") is not None:
      raise loggers.ElectionError.from_message(
          "CommitteeCollection should not exist.", [element]
      )

    if element.find("GovernmentBodyCollection") is not None:
      raise loggers.ElectionError.from_message(
          "GovernmentBodyCollection should not exist.", [element]
      )

    if element.find("OfficeCollection") is not None:
      raise loggers.ElectionError.from_message(
          "OfficeCollection should not exist.", [element]
      )

    if element.find("OfficeHolderTenureCollection") is not None:
      raise loggers.ElectionError.from_message(
          "OfficeHolderTenureCollection should not exist.", [element]
      )

    if element.find("PartyCollection") is not None:
      raise loggers.ElectionError.from_message(
          "PartyCollection should not exist.", [element]
      )

    if element.find("PersonCollection") is not None:
      raise loggers.ElectionError.from_message(
          "PersonCollection should not exist.", [element]
      )


VOTER_INFORMATION_RULES = common_rules.COMMON_RULES + (
    # go/keep-sorted start
    ElectoralCommissionCollectionExists,
    NoExtraElectionElements,
    NoExtraElectionReportCollections,
    VoterInformationCollectionExists,
    WarnOnElementsNotRecommendedForElection,
    # go/keep-sorted end
)

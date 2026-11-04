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
"""Validation rules for officeholder feeds of the CDF XML validator."""

from __future__ import print_function

import datetime
import hashlib

from civics_cdf_validator import base
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import rule_util


class PersonHasOffice(base.ValidReferenceRule):
  """Ensure that each non-party-leader Person object linked to one Office."""

  def _gather_reference_values(self):
    root = self.election_tree.getroot()

    person_ids = set()
    person_collection = root.find("PersonCollection")
    if person_collection is not None:
      person_ids = {p.attrib["objectId"] for p in person_collection}
    return person_ids

  def _gather_defined_values(self):
    root = self.election_tree.getroot()

    person_reference_ids = set()
    # Add party leaders provided in the External Identifier
    for external_id in root.findall(".//Party//ExternalIdentifier"):
      other_type = external_id.find("OtherType")
      if (
          other_type is not None
          and other_type.text in rule_util.PARTY_LEADERSHIP_TYPES
      ):
        person_reference_ids.add(external_id.find("Value").text)
    # Add party leaders provided in the Leadership entity
    for leader_id in root.findall(".//Party//PartyLeaderId"):
      if leader_id.text:
        person_reference_ids.add(leader_id.text)

    office_holder_tenure_collection = root.find("OfficeHolderTenureCollection")
    if office_holder_tenure_collection is not None:
      for office_holder_tenure in office_holder_tenure_collection.findall(
          "OfficeHolderTenure"
      ):
        id_obj = office_holder_tenure.find("OfficeHolderPersonId")
        if id_obj is not None and id_obj.text:
          person_reference_ids.add(id_obj.text.strip())

    office_collection = root.find("OfficeCollection")
    if (
        office_holder_tenure_collection is None
        and office_collection is not None
    ):
      for office in office_collection.findall("Office"):
        id_obj = office.find("OfficeHolderPersonIds")
        if id_obj is not None and id_obj.text:
          ids = id_obj.text.strip().split()
          if len(ids) > 1:
            msg = "Office has {} OfficeHolders. Must have exactly one.".format(
                str(len(ids))
            )
            raise loggers.ElectionError.from_message(msg, [office])
          person_reference_ids.update(ids)

    return person_reference_ids


class DateOfBirthIsInPast(base.DateRule):
  """Date of Birth should not be in the future."""

  def elements(self):
    return ["PersonCollection"]

  def check(self, element):
    for person_element in element:
      date_of_birthday = person_element.find("DateOfBirth")
      if date_of_birthday is not None and date_of_birthday.text:
        date_of_birthday = base.PartialDate.init_partial_date(
            date_of_birthday.text
        )
        self.check_for_date_in_past(date_of_birthday, person_element)
        if self.error_log:
          raise loggers.ElectionError(self.error_log)


class OfficeSelectionMethodMatch(base.BaseRule):
  """Office and OfficeHolderTenure need to have matching selection methods.

  Ensure that the OfficeSelectionMethod of a given OfficeHolderTenure is
  also
  present in the list of SelectionMethods of the Office it points to.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.office_selection_methods = {}
    officeholder_tenure_elements = self.get_elements_by_class(
        election_tree, "OfficeHolderTenure"
    )
    office_elements = self.get_elements_by_class(election_tree, "Office")
    if officeholder_tenure_elements:
      for element in office_elements:
        office_id = element.get("objectId")
        selection_methods = {
            selection_method.text
            for selection_method in element.findall("SelectionMethod")
        }
        self.office_selection_methods[office_id] = selection_methods

  def elements(self):
    return ["OfficeHolderTenure"]

  def check(self, element):
    office_id = element.find("OfficeId").text
    office_selection_method = element.find("OfficeSelectionMethod").text
    if (
        office_id not in self.office_selection_methods
        or office_selection_method
        not in self.office_selection_methods[office_id]
    ):
      raise loggers.ElectionError.from_message(
          "OfficeSelectionMethod does not have a matching SelectionMethod"
          " in the corresponding Office element.",
          [element],
      )


class OfficeHolderTenureTermDates(base.DateRule):
  """OfficeHolderTenure elements should contain valid term dates."""

  def elements(self):
    return ["OfficeHolderTenure"]

  def check(self, element):
    start_date = element.find("StartDate")
    end_date = element.find("EndDate")
    if rule_util.element_has_text(start_date) and rule_util.element_has_text(
        end_date
    ):
      start_date_obj = base.PartialDate.init_partial_date(start_date.text)
      end_date_obj = base.PartialDate.init_partial_date(end_date.text)
      if end_date_obj < start_date_obj:
        raise loggers.ElectionError.from_message(
            "OfficeHolderTenure element has an EndDate that is before the"
            " StartDate.",
            [element],
        )


class OfficeTermDates(base.DateRule):
  """Office elements should contain valid term dates.

  Offices with OfficeHolderPersonIds should have a Term declared. Given
  term should have a start date. If term also has an end date then end date
  should come after start date. Post Office split feed office objects should
  not have a Term element.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    self.is_post_office_split_feed = False
    officeholder_tenure_collection_element = self.get_elements_by_class(
        election_tree, "OfficeHolderTenureCollection"
    )
    if officeholder_tenure_collection_element:
      self.is_post_office_split_feed = True

  def elements(self):
    return ["Office"]

  def check(self, element):
    self.reset_instance_vars()
    if self.is_post_office_split_feed:
      term = element.find("Term")
      if term is not None:
        raise loggers.ElectionError.from_message(
            "Office should not contain Term data in post Office split feed.",
            [element],
        )
      if self.error_log:
        raise loggers.ElectionError(self.error_log)
    else:
      off_per_id = element.find("OfficeHolderPersonIds")
      if rule_util.element_has_text(off_per_id):
        term = element.find("Term")
        if term is None:
          raise loggers.ElectionWarning.from_message(
              "The Office is missing a Term.", [element]
          )

        self.gather_dates(term)
        if self.start_date is None:
          raise loggers.ElectionWarning.from_message(
              "The Office is missing a Term > StartDate.", [element]
          )
        elif self.end_date is not None:
          self.check_end_after_start()

      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class RemovePersonAndOfficeHolderId60DaysAfterEndDate(base.TreeRule):
  """Office elements should contain valid term dates.

  Check if 60 days after the specified office term EndDate,
  the associated Person and OfficeholderId may be removed from the feed.
  However, if the Person is elected to another office,
  they will be kept in the feed with the same stable ID.
  """

  def check(self):
    info_log = []
    persons = self.get_elements_by_class(self.election_tree, "Person")
    offices = self.get_elements_by_class(self.election_tree, "Office")
    officeholder_tenure_collection = self.get_elements_by_class(
        self.election_tree, "OfficeHolderTenureCollection"
    )
    is_post_office_split_feed = bool(officeholder_tenure_collection)
    person_office_dict = dict()
    outdated_offices = []
    outdated_officeholder_tenures = []
    outdated_officetenure_persons = dict()
    if is_post_office_split_feed:
      officeholder_tenures = self.get_elements_by_class(
          self.election_tree, "OfficeHolderTenure"
      )
      for officeholder_tenure in officeholder_tenures:
        office_holder_person_elem = officeholder_tenure.find(
            "OfficeHolderPersonId"
        )
        person_id = office_holder_person_elem.text
        date_validator = base.DateRule(None, None)
        date_validator.gather_dates(officeholder_tenure)
        end_date = date_validator.end_date
        if end_date is not None:
          sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
              days=-60
          )
          partial_date_sixty_days = base.PartialDate(
              sixty_days_earlier.year,
              sixty_days_earlier.month,
              sixty_days_earlier.day,
          )
          if end_date < partial_date_sixty_days:
            outdated_officeholder_tenures.append(officeholder_tenure)
          if person_id in outdated_officetenure_persons.keys():
            outdated_officetenure_persons[person_id].append(
                (office_holder_person_elem, end_date)
            )
          else:
            outdated_officetenure_persons[person_id] = [
                (office_holder_person_elem, end_date)
            ]
      for outdated_officeholder_tenure in outdated_officeholder_tenures:
        info_message = (
            "The officeholder tenure end date is more than 60 days"
            " in the past; this OfficeHolderTenure element can be removed"
            " from the feed."
        )
        info_log.append(
            loggers.LogEntry(info_message, [outdated_officeholder_tenure])
        )
      for person_id, value_list in outdated_officetenure_persons.items():
        has_recent_tenure = False
        office_holder_person_elem = None
        for value in value_list:
          office_holder_person_elem = value[0]
          end_date = value[1]
          sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
              days=-60
          )
          partial_date_sixty_days = base.PartialDate(
              sixty_days_earlier.year,
              sixty_days_earlier.month,
              sixty_days_earlier.day,
          )
          if end_date > partial_date_sixty_days:
            has_recent_tenure = True
        if not has_recent_tenure and office_holder_person_elem is not None:
          info_message = (
              "All officeholder tenures ended more than 60 days ago. "
              "Therefore, you can remove the person and the "
              "related officeholder tenures from the feed."
          )
          info_log.append(
              loggers.LogEntry(info_message, [office_holder_person_elem])
          )
    else:
      for office in offices:
        person_id = office.find("OfficeHolderPersonIds").text
        if person_id in person_office_dict:
          person_office_dict[person_id].append(office.get("objectId"))
        else:
          person_office_dict[person_id] = [office.get("objectId")]
        term = office.find(".//Term")
        if term is not None:
          date_validator = base.DateRule(None, None)
          date_validator.gather_dates(term)
          end_date_person = date_validator.end_date
          if end_date_person is not None:
            sixty_days_earlier = datetime.datetime.now() + datetime.timedelta(
                days=-60
            )
            partial_date_sixty_days = base.PartialDate(
                sixty_days_earlier.year,
                sixty_days_earlier.month,
                sixty_days_earlier.day,
            )
            if end_date_person < partial_date_sixty_days:
              outdated_offices.append(office.get("objectId"))
      for person in persons:
        pid = person.get("objectId")
        if person_office_dict.get(pid) is not None:
          check_person_outdated = all(
              item in outdated_offices for item in person_office_dict.get(pid)
          )
          if check_person_outdated:
            info_message = (
                "The officeholder mandates ended more than 60 days ago. "
                "Therefore, you can remove the person and the related offices "
                "from the feed."
            )
            info_log.append(loggers.LogEntry(info_message, [person]))
    if info_log:
      raise loggers.ElectionInfo(info_log)


class UniqueStartDatesForOfficeRoleAndJurisdiction(base.BaseRule):
  """Office StartDates should be unique within a certain group.

  Office StartDates should be unique amongst a group of Office entries
  with the same jurisdiction-id and office-role.
  """

  def elements(self):
    return ["OfficeCollection"]

  def _filter_out_past_end_dates(self, offices):
    valid_offices = []
    for office in offices:
      term = office.find(".//Term")
      if term is not None:
        date_validator = base.DateRule(None, None, ocd_id_validator=None)
        try:
          date_validator.gather_dates(term)
          if date_validator.end_date is not None:
            date_validator.check_for_date_not_in_past(
                date_validator.end_date, date_validator.end_elem
            )
          if not date_validator.error_log:
            valid_offices.append(office)
        except loggers.ElectionError:
          continue
    return valid_offices

  def _count_start_dates_by_jurisdiction_role(self, element):
    offices = element.findall("Office")
    offices = self._filter_out_past_end_dates(offices)
    jurisdiction_role_mapping = {}
    for office in offices:
      office_role = ""
      jurisdiction_id = ""
      start_date = ""

      start_date_elem = office.find(".//Term//StartDate")
      if not rule_util.element_has_text(start_date_elem):
        continue
      start_date = start_date_elem.text

      office_roles = rule_util.get_entity_info_for_value_type(
          office, "office-role"
      )
      if office_roles:
        office_role = office_roles[0]

      jurisdiction_ids = rule_util.get_entity_info_for_value_type(
          office, "jurisdiction-id"
      )
      if jurisdiction_ids:
        jurisdiction_id = jurisdiction_ids[0]

      office_hash = hashlib.sha256(
          (office_role + jurisdiction_id).encode("utf-8")
      ).hexdigest()
      if office_hash not in jurisdiction_role_mapping.keys():
        jurisdiction_role_mapping[office_hash] = dict({
            "jurisdiction_id": jurisdiction_id,
            "office_role": office_role,
            "start_dates": dict({}),
        })

      office_date_info = jurisdiction_role_mapping[office_hash]
      if start_date not in office_date_info["start_dates"].keys():
        office_date_info["start_dates"][start_date] = set()

      office_date_info["start_dates"][start_date].add(office)

    return jurisdiction_role_mapping

  def check(self, element):
    warning_log = []

    start_counts = self._count_start_dates_by_jurisdiction_role(element)
    for start_info in start_counts.values():
      start_date_map = start_info["start_dates"]
      if len(start_date_map.keys()) == 1:
        start_date = list(start_date_map.keys())[0]
        # this accounts for offices with only one entry (i.e. US Pres)
        if len(start_date_map[start_date]) > 1:
          warning_log.append(
              loggers.LogEntry(
                  (
                      "Only one unique StartDate found for each"
                      " jurisdiction-id: {} and office-role: {}. {} appears {}"
                      " times."
                  ).format(
                      start_info["jurisdiction_id"],
                      start_info["office_role"],
                      start_date,
                      len(start_date_map[start_date]),
                  ),
                  start_date_map[start_date],
              )
          )

    if warning_log:
      raise loggers.ElectionWarning(warning_log)


class UnreferencedEntitiesOfficeholders(common_rules.UnreferencedEntitiesBase):
  """CDF offices and party leadership entities are top-level in officeholders feeds.

  This rule is a warning for CDF parties since we ask for all parties for some
  LatAm feeds.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    office_holder_tenure_collection = self.get_elements_by_class(
        election_tree, "OfficeHolderTenure"
    )
    is_post_office_split = False
    if office_holder_tenure_collection:
      is_post_office_split = True
    super(UnreferencedEntitiesOfficeholders, self).__init__(
        election_tree,
        schema_tree,
        (
            frozenset(["OfficeHolderTenure", "Leadership"])
            if is_post_office_split
            else frozenset(["Office", "Leadership"])
        ),
        frozenset(["Party"]),
        **kwargs,
    )


OFFICEHOLDER_RULES = common_rules.COMMON_RULES + (
    # go/keep-sorted start
    DateOfBirthIsInPast,
    OfficeHolderTenureTermDates,
    OfficeSelectionMethodMatch,
    OfficeTermDates,
    PersonHasOffice,
    RemovePersonAndOfficeHolderId60DaysAfterEndDate,
    UniqueStartDatesForOfficeRoleAndJurisdiction,
    UnreferencedEntitiesOfficeholders,
    common_rules.ProhibitElectionData,
    # go/keep-sorted end
)

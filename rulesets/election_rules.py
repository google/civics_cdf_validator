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
"""Validation rules for election feeds of the CDF XML validator."""

from __future__ import print_function

import collections
import datetime

from civics_cdf_validator import base
from civics_cdf_validator import gpunit_rules
from civics_cdf_validator import loggers
from civics_cdf_validator.rulesets import common_rules
from civics_cdf_validator.rulesets import rule_util
import networkx


_CONTEST_STAGE_TYPES = frozenset([
    "exit-polls",
    "estimates",
    "projections",
    "preliminary",
    "official",
    "unnamed",
])

_INTERNATIONALIZED_TEXT_ELEMENTS_WITH_ONLY_ONE_TEXT_PER_LANGUAGE = [
    # go/keep-sorted start
    "BallotName",
    "BallotSubTitle",
    "BallotText",
    "BallotTitle",
    "ConStatement",
    "Directions",
    "DisplayName",
    "EffectOfAbstain",
    "FullName",
    "FullText",
    "InternationalizedAbbreviation",
    "InternationalizedName",
    "Name",
    "PartyLabel",
    "PassageThreshold",
    "ProStatement",
    "Profession",
    "Selection",
    "SummaryText",
    "Title",
    # go/keep-sorted end
]


_WINNER_POST_ELECTION_STATUSES = frozenset([
    "winner",
    "projected-winner",
])


def _get_type_or_other_type(element):
  """Returns the OtherType text if Type is "other", else the Type text."""
  type_element = element.find("Type")
  other_type_element = element.find("OtherType")
  type_text = (
      type_element.text.strip()
      if rule_util.element_has_text(type_element)
      else ""
  )
  other_type_text = (
      other_type_element.text.strip()
      if rule_util.element_has_text(other_type_element)
      else ""
  )
  return other_type_text if type_text == "other" else type_text


class PercentSum(base.BaseRule):
  """Check that Contest elements have percents summing to 0 or 100."""

  def elements(self):
    return ["Contest"]

  @staticmethod
  def fuzzy_equals(a, b, epsilon=1e-6):
    return abs(a - b) < epsilon

  def check(self, element):
    sum_percents = 0.0
    for ballot_selection in element.findall("BallotSelection"):
      for vote_counts in ballot_selection.find("VoteCountsCollection").findall(
          "VoteCounts"
      ):
        other_type = vote_counts.find("OtherType")
        if other_type is not None and other_type.text == "total-percent":
          sum_percents += float(vote_counts.find("Count").text)
    if not PercentSum.fuzzy_equals(
        sum_percents, 0
    ) and not PercentSum.fuzzy_equals(sum_percents, 100):
      raise loggers.ElectionError.from_message(
          "Contest percents do not sum to 0 or 100: %f" % sum_percents,
          [element],
      )


class GpUnitsHaveSingleRoot(base.TreeRule):
  """Ensure that GpUnits form a single-rooted tree."""

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(GpUnitsHaveSingleRoot, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.error_log = []

  def check(self):
    # Make sure there's at most one GpUnit as a root.
    # The root is defined as having ComposingGpUnitIds but
    # is not in the ComposingGpUnitIds of any other GpUnit.

    gpunit_ids = dict()
    composing_gpunits = set()
    for element in self.get_elements_by_class(self.election_tree, "GpUnit"):
      object_id = element.get("objectId")
      if object_id is not None:
        gpunit_ids[object_id] = element
      composing_gpunit = element.find("ComposingGpUnitIds")
      if composing_gpunit is not None and composing_gpunit.text is not None:
        composing_gpunits.update(composing_gpunit.text.split())

    roots = gpunit_ids.keys() - composing_gpunits

    if not roots:
      self.error_log.append(
          loggers.LogEntry(
              "GpUnits have no geo district root. "
              "There should be one or more root geo district."
          )
      )
    else:
      for object_id in roots:
        element = gpunit_ids.get(object_id)
        ocd_ids = rule_util.get_external_id_values(element, "ocd-id")
        for ocd_id in ocd_ids:
          if not gpunit_rules.GpUnitOcdIdValidator.is_country_or_region_ocd_id(
              ocd_id
          ):
            msg = (
                "GpUnits tree roots needs to be either a country or the EU"
                " region, please check the value %s." % (ocd_id)
            )
            self.error_log.append(loggers.LogEntry(msg, [element]))

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class PartisanPrimary(base.BaseRule):
  """Partisan elections should link to the correct political party.

  For an Election element of Election type primary, partisan-primary-open,
  or partisan-primary-closed, the Contests in that ContestCollection should
  have a PrimartyPartyIds that is present and non-empty.
  """

  election_type = None

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(PartisanPrimary, self).__init__(election_tree, schema_tree, **kwargs)
    # There can only be one election element in a file.
    election_elem = self.election_tree.find("Election")
    if election_elem is not None:
      election_type_elem = election_elem.find("Type")
      if election_type_elem is not None:
        self.election_type = election_type_elem.text.strip()

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_type_elem = election_elem.find("Type")
    election_type = None
    if rule_util.element_has_text(election_type_elem):
      election_type = election_type_elem.text.strip()

    if not election_type or election_type not in (
        "partisan-primary-open",
        "partisan-primary-closed",
    ):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      primary_party_ids = contest_elem.find("PrimaryPartyIds")
      if not rule_util.element_has_text(primary_party_ids):
        msg = (
            "Election is of ElectionType %s but PrimaryPartyIds is not present"
            " or is empty" % (self.election_type)
        )
        raise loggers.ElectionWarning.from_message(msg, [election_elem])


class PartisanPrimaryHeuristic(base.BaseRule):
  """Attempts to identify partisan primaries not marked up as such."""

  # Add other strings that imply this is a primary contest.
  party_text = ["(dem)", "(rep)", "(lib)"]

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_type_elem = election_elem.find("Type")
    election_type = None
    if rule_util.element_has_text(election_type_elem):
      election_type = election_type_elem.text.strip()

    if election_type is not None and election_type in (
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    ):
      return

    contests = self.get_elements_by_class(election_elem, "CandidateContest")
    for contest_elem in contests:
      contest_name = contest_elem.find("Name")
      if rule_util.element_has_text(contest_name):
        c_name = contest_name.text.replace(" ", "").lower()
        for p_text in self.party_text:
          if p_text in c_name:
            msg = (
                "Name of contest - %s, contains text that implies it is a "
                "partisan primary but is not marked up as such."
                % (contest_name.text)
            )
            raise loggers.ElectionWarning.from_message(msg, [contest_elem])


class CoalitionParties(base.BaseRule):
  """Coalitions should always define the Party IDs."""

  def elements(self):
    return ["Coalition"]

  def check(self, element):
    party_id = element.find("PartyIds")
    if party_id is None or not party_id.text or not party_id.text.strip():
      raise loggers.ElectionError.from_message(
          "Coalition must define PartyIDs", [element]
      )


class CandidatesReferencedInRelatedContests(base.BaseRule):
  """Candidate should not be referred to by multiple unrelated contests.

  A Candidate object should only be referenced from one contest, unless the
  contests are related (connected by ComposingContestIds or
  SubsequentContestId). If a Person is running in multiple unrelated Contests,
  then that Person is a Candidate several times over, but a Candida(te|cy)
  can't span unrelated contests.
  """

  def __init__(self, election_tree, schema_tree, **kwargs):
    super(CandidatesReferencedInRelatedContests, self).__init__(
        election_tree, schema_tree, **kwargs
    )
    self.error_log = []
    self.contest_graph = networkx.Graph()

  def elements(self):
    return ["ElectionReport"]

  def _register_person_to_candidate_to_contests(self, election_report):
    person_candidate_contest_mapping = {}

    candidate_to_contest_mapping = {}
    contests = self.get_elements_by_class(election_report, "Contest")
    for contest in contests:
      contest_id = contest.get("objectId", None)
      candidate_ids_elements = self.get_elements_by_class(
          contest, "CandidateIds"
      )
      candidate_id_elements = self.get_elements_by_class(contest, "CandidateId")
      id_elements = candidate_ids_elements + candidate_id_elements
      for id_element in id_elements:
        if rule_util.element_has_text(id_element):
          for candidate_id in id_element.text.split():
            candidate_to_contest_mapping.setdefault(candidate_id, []).append(
                contest_id
            )

    candidates = self.get_elements_by_class(election_report, "Candidate")
    for candidate in candidates:
      candidate_id = candidate.get("objectId", None)
      person_id = candidate.find("PersonId")
      if rule_util.element_has_text(person_id):
        if candidate_id not in candidate_to_contest_mapping.keys():
          raise loggers.ElectionError.from_message(
              (
                  "A Candidate should be referenced in a Contest. Candidate {} "
                  "is not referenced."
              ).format(candidate_id)
          )
        contest_list = candidate_to_contest_mapping[candidate_id]
        person_candidate_contest_mapping.setdefault(person_id.text, {})[
            candidate_id
        ] = contest_list

    return person_candidate_contest_mapping

  def _construct_contest_graph(self, election_report):
    contests = self.get_elements_by_class(election_report, "Contest")
    # create a node for each contest
    for contest in contests:
      self.contest_graph.add_node(contest.get("objectId"))

    for contest in contests:
      subsequent_contest = contest.find("SubsequentContestId")
      if rule_util.element_has_text(subsequent_contest):
        subsequent_contest_id = subsequent_contest.text
        # subsequent contest id is not valid if it isn't in the graph
        if not self.contest_graph.has_node(subsequent_contest_id):
          raise loggers.ElectionError.from_message(
              (
                  "Contest {} contains a subsequent Contest Id ({}) that does "
                  "not exist."
              ).format(contest.get("objectId"), subsequent_contest_id),
              [subsequent_contest],
          )
        self.contest_graph.add_edge(
            contest.get("objectId"), subsequent_contest_id
        )
      # Add the composing contest if it exists
      composing_contests = contest.find("ComposingContestIds")
      if rule_util.element_has_text(composing_contests):
        children = composing_contests.text.split()
        for child in children:
          # composing contest id is not valid if it isn't in the graph
          if not self.contest_graph.has_node(child):
            raise loggers.ElectionError.from_message(
                (
                    "Contest {} contains a composing Contest Id ({}) that does "
                    "not exist."
                ).format(contest.get("objectId"), child),
                [composing_contests],
            )
          self.contest_graph.add_edge(contest.get("objectId"), child)

  def _check_candidate_contests_are_related(self, contest_id_list):
    for i in range(len(contest_id_list) - 1):
      contest_one = contest_id_list[i]
      contest_two = contest_id_list[i + 1]
      # every unique contest should be related, but since paths are transitive
      # checking each subsequent pair is enough to ensure this
      if not networkx.has_path(self.contest_graph, contest_one, contest_two):
        return False

    return True

  def _check_separate_candidates_not_related(self, candidate_contest_mapping):
    for contests in candidate_contest_mapping.values():
      for other_contests in [
          con for con in candidate_contest_mapping.values() if con != contests
      ]:
        for contest in contests:
          for other_contest in other_contests:
            if networkx.has_path(self.contest_graph, contest, other_contest):
              return False
    return True

  def check(self, election_report):
    self._construct_contest_graph(election_report)
    person_candidate_to_contest_map = (
        self._register_person_to_candidate_to_contests(election_report)
    )
    for person, cand_con_mapping in person_candidate_to_contest_map.items():
      for cand, contests in cand_con_mapping.items():
        related_contests = self._check_candidate_contests_are_related(contests)
        if not related_contests:
          error_message = (
              "Candidate {} appears in the following contests "
              "which are not all related: {}"
          ).format(cand, ", ".join(contests))
          self.error_log.append(
              loggers.LogEntry(error_message, [election_report])
          )

      sep_cand_not_related = self._check_separate_candidates_not_related(
          cand_con_mapping
      )
      if not sep_cand_not_related:
        error_message = (
            "Person {} has separate candidates in contests that "
            "are related.".format(person)
        )
        self.error_log.append(
            loggers.LogEntry(error_message, [election_report])
        )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ProperBallotSelection(base.BaseRule):
  """BallotSelections should be correct for that type of contest.

  Ensure that the BallotSelection elements in a CandidateContest are
  CandidateSelections, PartyContests have PartySelections, etc, etc.
  """

  con_sel_mapping = {
      "BallotMeasureContest": "BallotMeasureSelection",
      "CandidateContest": "CandidateSelection",
      "PartyContest": "PartySelection",
      "RetentionContest": "BallotMeasureSelection",
  }

  def elements(self):
    return self.con_sel_mapping.keys()

  def check(self, element):
    tag = self.get_element_class(element)
    selections = []
    for c in self.con_sel_mapping:
      selections += self.get_elements_by_class(element, self.con_sel_mapping[c])
    for selection in selections:
      selection_tag = self.get_element_class(selection)
      if selection_tag != self.con_sel_mapping[tag]:
        selection_id = selection.get("objectId")
        msg = (
            "The Contest does not contain the right BallotSelection. %s "
            "must have a %s but contains a %s, %s"
            % (tag, self.con_sel_mapping[tag], selection_tag, selection_id)
        )
        raise loggers.ElectionError.from_message(msg, [element])


class CorrectCandidateSelectionCount(base.BaseRule):
  """CandidateSelections should only reference one candidate.

  This rule will throw a warning if a CandidateSelection references multiple
  candidates or does not reference any candidates at all. We currently do not
  support tickets (i.e. CandidateSelections with multiple candidates) except for
  party list elections.
  """

  def elements(self):
    return ["CandidateSelection"]

  def check(self, element):
    selection_id = element.get("objectId")
    candidate_ids = element.findall("CandidateIds")
    if not candidate_ids:
      msg = (
          f"The CandidateSelection {selection_id} does not reference any"
          " candidates."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])
    if len(candidate_ids) > 1:
      msg = (
          f"The CandidateSelection {selection_id} is expected to have one"
          f" CandidateIds but {len(candidate_ids)} were found."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])
    candidates = candidate_ids[0].text.split()
    if len(candidates) != 1:
      msg = (
          f"CandidateIds for CandidateSelection {selection_id} is expected to"
          f" reference one candidate but {len(candidates)} candidates were"
          " found. This warning can be ignored for party list elections."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])


class SingularPartySelection(base.BaseRule):
  """Each PartySelection should have exactly one Party in the PartyIds.

  While technically the schema allows multiple IDs, currently our pipeline does
  not support this. Having multiple parties can cause undefined behavior.
  """

  def elements(self):
    return ["PartySelection"]

  def check(self, element):
    party_ids = element.find("PartyIds")
    if party_ids is None or not party_ids.text or not party_ids.text.strip():
      raise loggers.ElectionError.from_message(
          "PartySelection has no associated parties.", [element]
      )
    elif len(party_ids.text.split()) != 1:
      raise loggers.ElectionError.from_message(
          "PartySelection has more than one associated party.", [element]
      )


class ValidatePartyCollection(base.BaseRule):
  """Generic party collection validation rule.

  All partyCollection validation rules can inherit from this class since it
  contains basic checks.
  """

  def elements(self):
    return ["PartyCollection"]

  def check_specific(self, parties):
    """Return a list of info log to be raised."""
    raise NotImplementedError

  def check(self, element):
    info_log = []
    parties = element.findall("Party")
    if len(parties) < 1:
      info_message = "<PartyCollection> does not have <Party> objects"
      info_log.append(loggers.LogEntry(info_message, element))
    info_log.extend(self.check_specific(parties))
    if info_log:
      raise loggers.ElectionInfo(info_log)


class ValidateDuplicateColors(base.TreeRule):
  """Parties under the same contest should have unique color.

  A Party object that has duplicate color and referenced under the same contest
  should be picked up within this class and returned to the user as a warning
  message.
  """

  def check(self):
    party_colors_by_id = {}
    party_objects = {}
    for party in self.get_elements_by_class(self.election_tree, "Party"):
      party_id = party.get("objectId")
      party_objects[party_id] = party
      party_colors_by_id[party_id] = {}
      color_element = party.find("Color")
      if rule_util.element_has_text(color_element):
        party_colors_by_id[party_id]["Color"] = color_element.text.lower()
      colors_element = party.find("Colors")
      if colors_element is not None:
        for color_field in ("DarkThemeColor", "LightThemeColor"):
          sub_color_element = colors_element.find(color_field)
          if rule_util.element_has_text(sub_color_element):
            party_colors_by_id[party_id][
                color_field
            ] = sub_color_element.text.lower()

    warning_log = []
    for party_contest in self.get_elements_by_class(
        element=self.election_tree, element_name="PartyContest"
    ):
      contest_colors = {
          "Color": collections.defaultdict(list),
          "DarkThemeColor": collections.defaultdict(list),
          "LightThemeColor": collections.defaultdict(list),
      }
      for party_ids_element in self.get_elements_by_class(
          element=party_contest, element_name="PartyIds"
      ):
        for party_id in party_ids_element.text.split():
          if party_id not in party_colors_by_id:
            continue
          party_colors = party_colors_by_id[party_id]
          party_element = party_objects[party_id]

          has_party_colors = "Color" in party_colors or (
              "DarkThemeColor" in party_colors
              and "LightThemeColor" in party_colors
          )
          if not has_party_colors:
            warning_log.append(
                loggers.LogEntry(
                    f"Party ({party_id}) in PartyContest should have either"
                    " Color or Colors.DarkThemeColor and Colors.LightThemeColor"
                    " set.",
                    [party_element],
                )
            )

          for color_field in ("Color", "DarkThemeColor", "LightThemeColor"):
            if color_field in party_colors:
              color_val = party_colors[color_field]
              contest_colors[color_field][color_val].append(party_element)

      for color_field in ("Color", "DarkThemeColor", "LightThemeColor"):
        for color, parties in contest_colors[color_field].items():
          if len(parties) > 1:
            warning_log.append(
                loggers.LogEntry(
                    f"Parties have the same {color_field} {color}.",
                    parties,
                )
            )
    if warning_log:
      raise loggers.ElectionWarning(warning_log)


class DuplicatedPartyAbbreviation(ValidatePartyCollection):
  """Party abbreviation should be used once in a given language.

  If an abbreviation is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    party_abbrs_by_language = {}
    for party in parties:
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = (
            "<Party> does not have <InternationalizedAbbreviation> objects"
        )
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_abbrs = abbr_element.findall("Text")
      for party_abbr in party_abbrs:
        language = party_abbr.get("language")
        abbr = party_abbr.text
        if language not in party_abbrs_by_language:
          party_abbrs_by_language[language] = {}
        if abbr in party_abbrs_by_language[language]:
          party_abbrs_by_language[language][abbr].append(party)
        else:
          party_abbrs_by_language[language][abbr] = [party]

    for language, abbrs in party_abbrs_by_language.items():
      for abbr, parties in abbrs.items():
        if len(parties) > 1:
          info_message = "Parties have the same abbreviation in %s." % language
          info_log.append(loggers.LogEntry(info_message, parties))
    return info_log


class DuplicatedPartyName(ValidatePartyCollection):
  """Party name should be used once in a given language.

  If a party name is duplicated, the corresponding party should be picked up
  within this class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    party_names_by_language = {}
    for party in parties:
      name_element = party.find("Name")
      if name_element is None:
        info_message = "<Party> does not have <Name> objects"
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_names = name_element.findall("Text")
      for party_name in party_names:
        language = party_name.get("language")
        name = party_name.text
        if language not in party_names_by_language:
          party_names_by_language[language] = {}
        if name in party_names_by_language[language]:
          party_names_by_language[language][name].append(party)
        else:
          party_names_by_language[language][name] = [party]

    for language, names in party_names_by_language.items():
      for name, parties in names.items():
        if len(parties) > 1:
          info_message = "Parties have the same name in %s." % language
          info_log.append(loggers.LogEntry(info_message, parties))
    return info_log


class MissingPartyNameTranslation(ValidatePartyCollection):
  """All Parties should have their name translated to the same languages.

  If there is a party name that is not translated to all the feed languages,
  the party should be picked up within this class and returned to the user as
  an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      name_element = party.find("Name")
      if name_element is None:
        info_message = "<Party> does not have <Name> objects"
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_names = name_element.findall("Text")
      party_languages = set()
      for party_name in party_names:
        language = party_name.get("language")
        if language not in feed_languages:
          feed_languages.add(language)
          if feed_party_ids:
            info_message = (
                "The feed is missing names translation to %s for parties : %s."
                % (language, feed_party_ids)
            )
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party name is not translated to all feed languages %s. You "
            "did it only for the following languages : %s."
            % (feed_languages, party_languages)
        )
        info_log.append(loggers.LogEntry(info_message, [party]))
    return info_log


class MissingPartyAbbreviationTranslation(ValidatePartyCollection):
  """Every party's abbreviation should be translated to the same languages.

  If a party is missing a name translation, it should be picked up within this
  class and returned to the user as an Info message.
  """

  def check_specific(self, parties):
    info_log = []
    feed_languages, feed_party_ids = set(), set()
    for party in parties:
      party_object_id = party.get("objectId")
      abbr_element = party.find("InternationalizedAbbreviation")
      if abbr_element is None:
        info_message = (
            "<Party> does not have <InternationalizedAbbreviation> objects"
        )
        info_log.append(loggers.LogEntry(info_message, [party]))
        continue
      party_abbrs = abbr_element.findall("Text")
      party_languages = set()
      for party_abbr in party_abbrs:
        language = party_abbr.get("language")
        if language not in feed_languages:
          feed_languages.add(language)
          if feed_party_ids:
            info_message = (
                "The feed is missing abbreviation translation to %s for parties"
                " : %s." % (language, feed_party_ids)
            )
            info_log.append(loggers.LogEntry(info_message))
        party_languages.add(language)
      feed_party_ids.add(party_object_id)
      if len(party_languages) != len(feed_languages):
        info_message = (
            "The party abbreviation is not translated to all feed languages %s."
            " You only did it for the following languages : %s."
            % (feed_languages, party_languages)
        )
        info_log.append(loggers.LogEntry(info_message, [party]))
    return info_log


class DuplicateContestNames(base.BaseRule):
  """Check that an election contains unique ContestNames.

  Add Warning if duplicate ContestName found.
  """

  def elements(self):
    return ["ContestCollection"]

  def check(self, election_elt):
    # Mapping for <Name> and its Contest ObjectId.
    error_log = []
    name_contest_id = {}
    contest_elts = election_elt.findall("Contest")
    if contest_elts is None:
      error_message = "ContestCollection is Empty."
      error_log.append(loggers.LogEntry(error_message, [election_elt]))
    for element in contest_elts:
      name = element.find("Name")
      if name is None or not name.text:
        error_message = "The contest is missing a <Name> "
        error_log.append(loggers.LogEntry(error_message, [element]))
        continue
      name_contest_id.setdefault(name.text, []).append(element)

    for name, contests in name_contest_id.items():
      if len(contests) > 1:
        error_log.append(
            loggers.LogEntry("Contests have the same name %s." % name, contests)
        )
    if error_log:
      raise loggers.ElectionError(error_log)


class DuplicateBallotTitleSeatPair(base.BaseRule):
  """Checks that each English (BallotTitle, Seat) combination is unique.

  Adds Warning/Error if duplicate English (BallotTitle, Seat) combinations are
  found.
  """

  def elements(self):
    return ["ContestCollection"]

  def check(self, element):
    error_log = []
    contest_elements = element.findall("Contest")
    contests_by_title_and_seat = collections.defaultdict(list)

    for contest in contest_elements:
      ballot_title_element = rule_util.get_language_to_text_map(
          contest.find("BallotTitle")
      )
      english_title = ballot_title_element.get("en")
      seat_element = contest.find("Seat")

      ballot_title = english_title[0].strip() if english_title else ""
      seat = (
          seat_element.text.strip()
          if rule_util.element_has_text(seat_element)
          else ""
      )

      if not ballot_title:
        continue

      ballot_title_and_seat = (ballot_title, seat)
      contests_by_title_and_seat[ballot_title_and_seat].append(contest)

    for ballot_title_and_seat, contests in contests_by_title_and_seat.items():
      if len(contests) > 1:
        ballot_title, seat = ballot_title_and_seat
        error_message = (
            "Multiple Contests found with the same BallotTitle"
            f" ('{ballot_title}') and Seat ('{seat}')."
        )
        error_log.append(loggers.LogEntry(error_message, contests))

    if error_log:
      raise loggers.ElectionError(error_log)


class MultipleCandidatesPointToTheSamePersonInTheSameContest(base.TreeRule):
  """Raise an error when multiple candidates point to the same person in the same contest."""

  def check(self):
    # Keep track of rule violations
    error_log = []
    rule_violations = []
    # Get all Candidate objects in the feed
    candidates = self.get_elements_by_class(self.election_tree, "Candidate")
    # Store link between candidate_id and person_id for each Candidate object
    person_id_by_candidate_id = {
        candidate.get("objectId"): candidate.find("PersonId").text
        for candidate in candidates
    }
    # Get all Contest objects in the feed
    contests = self.get_elements_by_class(self.election_tree, "Contest")
    for contest in contests:
      rule_violations.extend(
          self._check_for_bad_candidates(person_id_by_candidate_id, contest)
      )
    # Combine rule violations into one error message
    if rule_violations:
      for rule_violation in rule_violations:
        contest_id = rule_violation[0]
        person_id = rule_violation[1]
        candidate_list = rule_violation[2]
        error_message = (
            "Multiple candidates in Contest {} reference the same Person "
            "{}. Candidates: {}"
        ).format(contest_id, person_id, candidate_list)
        error_log.append(loggers.LogEntry((error_message), [contest_id]))
    if error_log:
      raise loggers.ElectionError(error_log)

  def _check_for_bad_candidates(self, person_id_by_candidate_id, contest):
    candidate_ids_by_person_id = dict()
    rule_violating_person_ids = []
    contest_id = contest.get("objectId")
    for candidate_id in self._get_candidate_ids_for_contest(contest):
      person_id = person_id_by_candidate_id[candidate_id]
      if person_id not in candidate_ids_by_person_id:
        candidate_ids_by_person_id[person_id] = [candidate_id]
      else:
        candidate_ids_by_person_id[person_id].append(candidate_id)
        rule_violating_person_ids.append(person_id)
    return [
        (contest_id, person_id, str(candidate_ids_by_person_id[person_id]))
        for person_id in rule_violating_person_ids
    ]

  def _get_candidate_ids_for_contest(self, contest):
    candidate_id_elements = self.get_elements_by_class(contest, "CandidateIds")
    candidate_ids = []
    for candidate_id_element in candidate_id_elements:
      candidate_ids.extend(candidate_id_element.text.split())
    return candidate_ids


class SelfDeclaredCandidateMethod(base.BaseRule):
  """A self declared candidate cannot have an "electoral-commission" id.

  Please update the candidate Pre election Status.
  """

  def elements(self):
    return ["Candidate"]

  def check(self, element):
    status = element.find("PreElectionStatus")
    if status is not None and status.text == "self-declared":
      externalidvalues = rule_util.get_external_id_values(
          element, "electoral-commission"
      )
      length = len(externalidvalues)
      if length > 0:
        msg = (
            "A self declared candidate cannot have an electoral-commission"
            " id. Please update the candidate Pre election Status."
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class ContestHasMultipleOffices(base.BaseRule):
  """Ensure that each contest has exactly one Office."""

  def elements(self):
    return ["CandidateContest", "PartyContest"]

  def check(self, element):
    # for each contest, get the <officeids> entity
    office_ids = element.find("OfficeIds")
    if office_ids is not None and office_ids.text:
      ids = office_ids.text.split()
      if len(ids) > 1:
        raise loggers.ElectionWarning.from_message(
            "Contest has more than one associated office.", [element]
        )
    else:
      raise loggers.ElectionWarning.from_message(
          "Contest has no associated offices.", [element]
      )


class VoteCountTypesCoherency(base.BaseRule):
  """Ensure VoteCount types describe the appropriate votable."""

  PARTY_VC_TYPES = {
      "seats-won",
      "seats-leading",
      "party-votes",
      "seats-no-election",
      "seats-total",
      "seats-delta",
      "seats-delta-mandate",
      "seats-delta-institutional",
  }
  # Ibid.
  CAND_VC_TYPES = {"candidate-votes"}

  def elements(self):
    return ["Contest"]

  def check(self, element):
    invalid_vc_types = None
    contest_type = ""
    if element.get("type", "") == "CandidateContest":
      invalid_vc_types = self.PARTY_VC_TYPES
      contest_type = "Candidate"
    elif element.get("type", "") == "PartyContest":
      invalid_vc_types = self.CAND_VC_TYPES
      contest_type = "Party"
    if invalid_vc_types:
      errors = []
      for ballot_selection in element.findall("BallotSelection"):
        for vote_counts in ballot_selection.find(
            "VoteCountsCollection"
        ).findall("VoteCounts"):
          vc_type = vote_counts.find("OtherType").text
          if vc_type in invalid_vc_types:
            errors.append(vc_type)
      if errors:
        msg = "VoteCount types {0} should not be nested in {1} Contest".format(
            ", ".join(errors), contest_type
        )
        raise loggers.ElectionError.from_message(msg, [element])


class VoteCountValidSeatsDeltaTypes(base.BaseRule):
  """Ensure VoteCount seats delta types are valid."""

  def elements(self):
    return ["BallotSelection"] + list(
        self.get_element_names_for_type("SpecialBallotSelection")
    )

  def check(self, element):
    vote_count_types = set()
    vote_counts_collection = element.find("VoteCountsCollection")
    if vote_counts_collection is None:
      return
    for vote_counts in vote_counts_collection.findall("VoteCounts"):
      vote_count_types.add(_get_type_or_other_type(vote_counts))
    if "seats-delta" in vote_count_types:
      raise loggers.ElectionError.from_message(
          "Legacy VoteCounts type seats-delta is no longer supported as of"
          " July 1, 2026. Please update your implementation to use"
          " seats-delta-mandate and/or seats-delta-institutional.",
          [element],
      )


class OfficeHasjurisdictionSameAsElectoralDistrict(base.BaseRule):
  """In election feeds, office has the electoral district same as jurisdiction."""

  def elements(self):
    return ["Office"]

  def check(self, element):
    jurisdiction_values = rule_util.get_entity_info_for_value_type(
        element, "jurisdiction-id"
    )
    jurisdiction_values = [
        j_id.strip() for j_id in jurisdiction_values if j_id.strip()
    ]
    if not jurisdiction_values or len(jurisdiction_values) > 1:
      return

    electoral_district = element.find(".//ElectoralDistrictId")
    if electoral_district is None:
      return
    if electoral_district.text.strip() != jurisdiction_values[0]:
      raise loggers.ElectionInfo.from_message(
          "Office has electoral district different from jurisdiction.",
          [element],
      )


class ContestHasValidContestStage(base.BaseRule):
  """Each Contest must have a valid contest-stage."""

  def elements(self):
    return ["CandidateContest", "PartyContest", "BallotMeasureContest"]

  def check(self, element):
    contest_stage_values = [
        contest_stage_value.strip()
        for contest_stage_value in rule_util.get_external_id_values(
            element, "contest-stage"
        )
    ]
    for contest_stage_value in contest_stage_values:
      if contest_stage_value not in _CONTEST_STAGE_TYPES:
        raise loggers.ElectionError.from_message(
            "The contest has invalid contest-stage '{}'.".format(
                contest_stage_value
            ),
            [element],
        )


class ElectionContainsStartAndEndDates(base.DateRule):
  """Election elements should have start and end dates populated."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_elem is None:
      self.error_log.append(
          loggers.LogEntry(
              "Election {} is missing a start date.".format(
                  element.get("objectId")
              )
          )
      )

    if self.end_elem is None:
      self.error_log.append(
          loggers.LogEntry(
              "Election {} is missing an end date.".format(
                  element.get("objectId")
              )
          )
      )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ElectionStartDates(base.DateRule):
  """Election elements should contain valid start dates.

  Start dates in the past should raise a warning. This is not an error
  as validator could conceivably be run during an ongoing election.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_date:
      self.check_for_date_not_in_past(self.start_date, self.start_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ElectionEndDatesInThePast(base.DateRule):
  """Election elements would be in the present or in the future.

  Using a past end date needs to be notified. The warning is useful to prevent
  using a wrong date.

  A bounded election with a past end date is an error since the date should be
  confirmed. The only exception to this is elections that are postponed or
  canceled.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)
    date_type = element.find("ElectionDateType")
    if date_type is not None and date_type.text.lower() == "bounded":
      if self.end_date:
        self.check_for_date_not_in_past(self.end_date, self.end_elem)
      if self.error_log:
        date_status = element.find("ElectionDateStatus")
        if date_status is None or date_status.text.lower() not in [
            "postponed",
            "canceled",
        ]:
          raise loggers.ElectionError.from_message(
              "A bounded election should not have an end date in the past.",
              [element],
          )
        self.reset_instance_vars()
    for contest in self.get_elements_by_class(element, "Contest"):
      subsequent_contest_id_element = contest.find("SubsequentContestId")
      if subsequent_contest_id_element is not None:
        continue
      else:
        if self.end_date:
          self.check_for_date_not_in_past(self.end_date, self.end_elem)
    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ElectionEndDatesOccurAfterStartDates(base.DateRule):
  """Election elements should contain a coherent start and end dates.

  End dates should not occur before the start date.
  """

  def elements(self):
    return ["Election"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class ElectionDatesSpanContestDates(base.DateRule):
  """Election start/end dates should span the Contest start/end dates.

  The start date of the Election should be on or before the start date of every
  included Contest. The end date of the Election should be on or after the end
  date of every included Contest. Only Contests that have the dates populated
  will be considered.
  """

  def elements(self):
    return ["ElectionReport"]

  def _validate_contest_dates_within_election(self, election, contest):
    self.reset_instance_vars()
    self.gather_dates(election)
    election_start_date = self.start_date
    election_end_date = self.end_date
    election_id = election.get("objectId")
    self.reset_instance_vars()
    self.gather_dates(contest)
    contest_id = contest.get("objectId")
    contest_date_status = contest.find("ContestDateStatus")
    if (
        election_end_date is not None
        and self.end_date is not None
        and election_end_date < self.end_date
        # Only compare election end date to contests that are not canceled
        and (
            contest_date_status is None
            or contest_date_status.text.lower() != "canceled"
        )
    ):
      self.error_log.append(
          loggers.LogEntry(
              "Contest {} with end date {} occurs after Election {} with"
              " end date {}. Election end date should be on or after any"
              " Contest end date.".format(
                  contest_id,
                  self.end_date,
                  election_id,
                  election_end_date,
              )
          )
      )
    if (
        election_start_date is not None
        and self.start_date is not None
        and self.start_date < election_start_date
    ):
      self.error_log.append(
          loggers.LogEntry(
              "Contest {} with start date {} occurs before Election {} with"
              " start date {}. Election start date should be on or before"
              " any Contest start date.".format(
                  contest_id,
                  self.start_date,
                  election_id,
                  election_start_date,
              )
          )
      )

  def check(self, election_report_element):
    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      for contest in self.get_elements_by_class(election, "Contest"):
        self._validate_contest_dates_within_election(election, contest)

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ElectionTypesAreCompatible(base.BaseRule):
  """Election element Type values cannot be both a general and primary type."""

  def elements(self):
    return ["Election"]

  def check(self, element):
    election_types = element.findall("Type")
    if election_types:
      for i in range(len(election_types)):
        election_types[i] = election_types[i].text
      if "general" in election_types and (
          "primary" in election_types
          or "partisan-primary-open" in election_types
          or "partisan-primary-closed" in election_types
      ):
        raise loggers.ElectionError.from_message(
            "Election element has incompatible election-type values.", [element]
        )


class ElectionTypesAndCandidateContestTypesAreCompatible(base.BaseRule):
  """Election elements should contain CandidateContests with compatible types.

  Elections with the general type should not have any CandidateContests with the
  primary types. Elections with the primary types should not have any
  CandidateContests with the general type.
  """

  def _extract_text_from_elements(self, elements):
    return {
        element.text.strip().lower()
        for element in elements
        if rule_util.element_has_text(element)
    }

  def elements(self):
    return ["Election"]

  def check(self, element):
    errors = []
    contests = self.get_elements_by_class(element, "CandidateContest")
    election_types = self._extract_text_from_elements(element.findall("Type"))
    primary_types = {
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    }
    for contest in contests:
      contest_types = self._extract_text_from_elements(contest.findall("Type"))
      if "general" in election_types and primary_types.intersection(
          contest_types
      ):
        errors.append(
            loggers.LogEntry(
                "Election %s includes CandidateContest %s with incompatible"
                " type(s). General elections cannot include primary contests."
                % (element.get("objectId"), contest.get("objectId")),
                element,
            )
        )
      elif (
          primary_types.intersection(election_types)
          and "general" in contest_types
      ):
        errors.append(
            loggers.LogEntry(
                "Election %s includes CandidateContest %s with incompatible"
                " type(s). Primary elections cannot include general contests."
                % (element.get("objectId"), contest.get("objectId")),
                element,
            )
        )

    if errors:
      raise loggers.ElectionError(errors)


class DateStatusMatches(base.DateRule):
  """In most cases, ContestDateStatus should match ElectionDateStatus.

  If all contests contained in an election have the same status, and this status
  does not match the status on the election, it is probably incorrect - raise
  warning.  Differing values among ContestDateStatus in an election are possible
  but uncommon - raise Info level message.
  """

  def elements(self):
    return ["Election"]

  def check(self, election_elem):
    election_date_status = "confirmed"  # default value
    election_status_elem = election_elem.find("ElectionDateStatus")

    if rule_util.element_has_text(election_status_elem):
      election_date_status = election_status_elem.text.strip()

    contest_statuses = set()
    for contest_elem in self.get_elements_by_class(election_elem, "Contest"):
      contest_status_elem = contest_elem.find("ContestDateStatus")
      if rule_util.element_has_text(contest_status_elem):
        contest_statuses.add(contest_status_elem.text.strip())
      else:
        contest_statuses.add("confirmed")

    if len(contest_statuses) == 1:
      contest_status = contest_statuses.pop()
      if contest_status != election_date_status:
        msg = (
            "All contests on election {} have a date status of {}, but the "
            "election has a date status of {}.".format(
                election_elem.get("objectId"),
                contest_status,
                election_date_status,
            )
        )
        raise loggers.ElectionWarning.from_message(msg, [election_elem])
    elif len(contest_statuses) > 1:
      msg = (
          "There are multiple date statuses present for the contests on "
          "election {}.  This may be correct, but is an unusal case.  Please "
          "confirm.".format(election_elem.get("objectId"))
      )
      raise loggers.ElectionInfo.from_message(msg, [election_elem])


class ValidateInfoUriAnnotation(base.BaseRule):
  """InfoUri is an annotated Uri that accepts the following annotations.

  wikipedia, ballotpedia, official-website, fulltext.
  Adding a check for this.
  """

  info_array = [
      "wikipedia",
      "ballotpedia",
      "official-website",
      "fulltext",
      "logo-uri",
  ]

  def elements(self):
    return ["InfoUri"]

  def check(self, element):
    error_log = []
    annotation = element.attrib["Annotation"]
    if annotation not in self.info_array:
      error_log.append(
          loggers.LogEntry(annotation + " is an invalid annotation.", [element])
      )
    if error_log:
      raise loggers.ElectionError(error_log)


class FullTextMaxLength(base.BaseRule):
  """FullText field should not be longer than MAX_LENGTH."""

  MAX_LENGTH = 30000  # about 8-10 pages of text, 4500-5000 words

  def elements(self):
    return ["FullText"]

  def check(self, element):
    intl_text_list = element.findall("Text")
    for intl_text in intl_text_list:
      if len(intl_text.text) > self.MAX_LENGTH:
        msg = (
            "FullText is longer than %s characters. Please remove and "
            "include a link to the full text via InfoUri with Annotation "
            "'fulltext'." % (self.MAX_LENGTH)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class FullTextOrBallotText(base.BaseRule):
  """Warn if BallotText is missing and FullText is short."""

  SUGGESTION_CUTOFF_LENGTH = 2500  # about 3 paragraphs, 250-300 words

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    full_text_map = rule_util.get_language_to_text_map(element.find("FullText"))
    if not full_text_map:
      return

    ballot_text_map = rule_util.get_language_to_text_map(
        element.find("BallotText")
    )
    for language, full_text_strings in full_text_map.items():
      full_text_string = full_text_strings[0]
      if (
          language not in ballot_text_map.keys()
          and len(full_text_string) < self.SUGGESTION_CUTOFF_LENGTH
      ):
        msg = (
            "Language: %s.  BallotText is missing but FullText is present "
            "for the same language. Please confirm that FullText contains "
            "only supplementary text and not text on the ballot itself."
            % (language)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class BallotTitle(base.BaseRule):
  """BallotTitle must exist and should usually be shorter than BallotText."""

  def elements(self):
    return ["BallotMeasureContest"]

  def check(self, element):
    ballot_title_map = rule_util.get_language_to_text_map(
        element.find("BallotTitle")
    )
    if not ballot_title_map:
      raise loggers.ElectionError.from_message(
          "BallotMeasureContest is missing BallotTitle.", [element]
      )

    ballot_text_map = rule_util.get_language_to_text_map(
        element.find("BallotText")
    )
    if not ballot_text_map:
      msg = (
          "BallotText is missing. Please confirm that the ballot "
          "text/question is not in BallotTitle."
      )
      raise loggers.ElectionWarning.from_message(msg, [element])

    for language, ballot_title_strings in ballot_title_map.items():
      ballot_title_string = ballot_title_strings[0]
      if language not in ballot_text_map.keys() or len(
          ballot_text_map[language][0]
      ) < len(ballot_title_string):
        msg = (
            "Language: %s. BallotText is missing or shorter than "
            " Please confirm that the ballot text/question is not "
            "in BallotTitle." % (language)
        )
        raise loggers.ElectionWarning.from_message(msg, [element])


class ImproperCandidateContest(base.TreeRule):
  """Detect CandidateContest elements that should be a BallotMeasureContest."""

  _BALLOT_SELECTION_OPTIONS = frozenset({"yes", "no", "for", "against"})

  def _gather_contest_candidates(self, contest):
    """Return candidate ids for given contest element."""
    candidate_ids = []
    cand_id_elems = contest.findall("BallotSelection//CandidateIds")
    for cand_id_elem in cand_id_elems:
      for cand_id in cand_id_elem.text.split():
        candidate_ids.append(cand_id)
    return candidate_ids

  def _gather_invalid_candidates(self):
    """Return candidate ids that appear to be BallotMeasureSelections."""
    invalid_candidates = []
    candidates = self.get_elements_by_class(
        self.election_tree, "CandidateCollection//Candidate"
    )
    for candidate in candidates:
      ballot_name = candidate.find(".//BallotName/Text[@language='en']")
      if ballot_name is not None:
        if ballot_name.text.lower() in self._BALLOT_SELECTION_OPTIONS:
          invalid_candidates.append(candidate.get("objectId"))
    return invalid_candidates

  def check(self):
    candidate_contest_mapping = {}
    candidate_contests = self.get_elements_by_class(
        self.election_tree, "CandidateContest"
    )
    for cc in candidate_contests:
      cand_ids = self._gather_contest_candidates(cc)
      contest_id = cc.get("objectId")
      candidate_contest_mapping[contest_id] = cand_ids

    invalid_candidates = self._gather_invalid_candidates()

    warning_log = []
    for contest_id, cand_ids in candidate_contest_mapping.items():
      flagged_candidates = []
      for cand_id in cand_ids:
        if cand_id in invalid_candidates:
          flagged_candidates.append(cand_id)
      if flagged_candidates:
        warning_message = (
            "Candidates {} should be BallotMeasureSelection "
            "elements. Similarly, Contest {} should be changed "
            "to a BallotMeasureContest instead of a "
            "CandidateContest."
        ).format(", ".join(flagged_candidates), contest_id)
        warning_log.append(loggers.LogEntry(warning_message))
    if invalid_candidates:
      warning_message = (
          "There are CandidateContests that appear to be "
          "BallotMeasureContests based on the "
          "BallotName values."
      )
      raise loggers.ElectionWarning(warning_log)


class WinnerCountLimit(base.BaseRule):
  """Number of winners must be less than or equal to NumberElected."""

  def setup(self):
    self.candidate_post_election_status_by_object_id = (
        self._get_candidate_post_election_status_by_object_id()
    )

  def _get_candidate_post_election_status_by_object_id(self):
    candidate_post_election_status_by_object_id = {}
    candidates = self.get_elements_by_class(
        self.election_tree, "CandidateCollection//Candidate"
    )
    for candidate in candidates:
      object_id = candidate.get("objectId")
      post_election_status = candidate.find("PostElectionStatus")
      if object_id and rule_util.element_has_text(post_election_status):
        candidate_post_election_status_by_object_id[object_id] = (
            post_election_status.text.strip()
        )
    return candidate_post_election_status_by_object_id

  def elements(self):
    return ["CandidateContest"]

  def check(self, element):
    number_elected_element = element.find("NumberElected")
    number_elected = (
        int(number_elected_element.text)
        if rule_util.element_has_text(number_elected_element)
        else 1
    )

    candidate_ids_elements = element.findall("BallotSelection//CandidateIds")
    candidate_ids = set()
    for candidate_ids_element in candidate_ids_elements:
      if rule_util.element_has_text(candidate_ids_element):
        candidate_ids.update(candidate_ids_element.text.split())

    winner_count = 0
    for candidate_id in candidate_ids:
      status = self.candidate_post_election_status_by_object_id.get(
          candidate_id
      )
      if status in _WINNER_POST_ELECTION_STATUSES:
        winner_count += 1

    if winner_count > number_elected:
      raise loggers.ElectionError.from_message(
          f"Contest {element.get('objectId')} has {winner_count} candidates"
          " with PostElectionStatus of 'winner' or 'projected-winner',"
          f" which exceeds NumberElected: {number_elected}.",
          [element],
      )


class SubsequentContestIdIsValidRelatedContest(base.DateRule):
  """Check that SubsequentContests are valid.

  Conditions for a valid SubsequentContest:
  - OfficeId, if present, must match the original contest.
  - PrimaryPartyIds, if present, must match the original contest.
  - EndDate, if present, must not be after EndDate of the original contest.
  - ComposingContestIds must not contain the original contest.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    error_log = []
    contest_by_id = {}
    contest_end_date_by_id = {}

    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      self.gather_dates(election)
      election_end_date = self.end_date
      for contest in self.get_elements_by_class(election, "Contest"):
        self.reset_instance_vars()
        self.gather_dates(contest)
        contest_by_id[contest.get("objectId")] = contest
        contest_end_date_by_id[contest.get("objectId")] = (
            self.end_date or election_end_date
        )

    for contest_id, contest in contest_by_id.items():
      element = contest.find("SubsequentContestId")
      if not rule_util.element_has_text(element):
        continue
      subsequent_contest_id = element.text.strip()

      # Check that subsequent contest exists
      if subsequent_contest_id not in contest_by_id:
        error_log.append(
            loggers.LogEntry(
                "Could not find SubsequentContest"
                f" {subsequent_contest_id} referenced by Contest {contest_id}."
            )
        )
        continue

      subsequent_contest = contest_by_id[subsequent_contest_id]
      # Check that the subsequent contest has a later end date
      if subsequent_contest is not None and contest is not None:
        contest_end_date = contest_end_date_by_id[contest_id]
        subsequent_contest_end_date = contest_end_date_by_id[
            subsequent_contest_id
        ]
        if subsequent_contest_end_date < contest_end_date:
          error_log.append(
              loggers.LogEntry(
                  f"Contest {contest_id} references a subsequent contest with"
                  " an earlier end date.",
                  [contest],
                  [contest.sourceline],
              )
          )

      # Check that office ids match
      contest_office_id = None
      subsequent_contest_office_id = None
      element = contest.find("OfficeIds")
      if rule_util.element_has_text(element):
        contest_office_id = element.text
      element = subsequent_contest.find("OfficeIds")
      if rule_util.element_has_text(element):
        subsequent_contest_office_id = element.text

      if contest_office_id != subsequent_contest_office_id:
        error_log.append(
            loggers.LogEntry(
                f"Contest {contest_id} references a subsequent contest with a"
                " different office id.",
                [contest],
                [contest.sourceline],
            )
        )

      # Check that primary party ids match or that the subsequent contest does
      # not have a primary party (e.g. primary -> general election)
      contest_primary_party_ids = None
      subsequent_contest_primary_party_ids = None
      element = contest.find("PrimaryPartyIds")
      if rule_util.element_has_text(element):
        contest_primary_party_ids = set(element.text.split())
      element = subsequent_contest.find("PrimaryPartyIds")
      if rule_util.element_has_text(element):
        subsequent_contest_primary_party_ids = set(element.text.split())

      if (
          subsequent_contest_primary_party_ids is not None
          and contest_primary_party_ids != subsequent_contest_primary_party_ids
      ):
        error_log.append(
            loggers.LogEntry(
                "Contest %s references a subsequent contest with different "
                "primary party ids." % contest_id,
                [contest],
                [contest.sourceline],
            )
        )

      # Check that there is not a subsequent contest <-> composing contest loop
      element = subsequent_contest.find("ComposingContestIds")
      if rule_util.element_has_text(element):
        subsequent_composing_ids = element.text.split()
        if contest_id in subsequent_composing_ids:
          error_log.append(
              loggers.LogEntry(
                  f"Contest {contest_id} is listed as a composing contest for"
                  " its subsequent contest. Two contests can be linked by"
                  " SubsequentContestId or ComposingContestId, but not both.",
                  [contest],
                  [contest.sourceline],
              )
          )

    if error_log:
      raise loggers.ElectionError(error_log)


class ComposingContestIdsAreValidRelatedContests(base.BaseRule):
  """Check that ComposingContestIds are valid.

  Conditions for a valid ComposingContest:
  - OfficeId, if present, must match the parent contest.
  - PrimaryPartyIds, if present, must match the parent contest.
  - ComposingContests must not be referenced by more than one parent contest.
  - ComposingContests must not reference each other.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    error_log = []

    contests = self.get_elements_by_class(election_report_element, "Contest")
    contest_ids = {cc.get("objectId"): cc for cc in contests}
    composing_contests = {}
    for contest_id, contest in contest_ids.items():
      element = contest.find("ComposingContestIds")
      if not rule_util.element_has_text(element):
        continue
      composing_contests[contest_id] = element.text.split()

    # Check for composing contests that appear more than once
    unique_contests = set()
    for contest_list in composing_contests.values():
      for contest_id in contest_list:
        if contest_id not in unique_contests:
          unique_contests.add(contest_id)
        else:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s is listed as a ComposingContest for more "
                  "than one parent contest.  ComposingContests should be a "
                  "strict hierarchy." % contest_id
              )
          )

    for contest_id, composing_contest_ids in composing_contests.items():
      contest = contest_ids[contest_id]
      for cc_id in composing_contest_ids:
        # Check that the composing contests exist
        if cc_id not in contest_ids.keys():
          error_log.append(
              loggers.LogEntry(
                  "Could not find ComposingContest % referenced by Contest %s."
                  % (contest_id, cc_id)
              )
          )
          continue

        composing_contest = contest_ids[cc_id]
        # Check that the office ids match
        c_office_id = None
        cc_office_id = None
        element = contest.find("OfficeIds")
        if rule_util.element_has_text(element):
          c_office_id = element.text
        element = composing_contest.find("OfficeIds")
        if rule_util.element_has_text(element):
          cc_office_id = element.text

        if c_office_id != cc_office_id:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and composing contest %s have different office "
                  "ids." % (contest_id, cc_id)
              )
          )

        # Check that primary party ids match
        c_primary_party_ids = None
        cc_primary_party_ids = None
        element = contest.find("PrimaryPartyIds")
        if rule_util.element_has_text(element):
          c_primary_party_ids = set(element.text.split())
        element = composing_contest.find("PrimaryPartyIds")
        if rule_util.element_has_text(element):
          cc_primary_party_ids = set(element.text.split())

        if c_primary_party_ids != cc_primary_party_ids:
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and composing contest %s have different primary "
                  "party ids." % (contest_id, cc_id)
              )
          )

        # Check that composing contests don't reference each other
        if (
            cc_id in composing_contests
            and contest_id in composing_contests[cc_id]
        ):
          error_log.append(
              loggers.LogEntry(
                  "Contest %s and contest %s reference each other as composing "
                  "contests." % (contest_id, cc_id)
              )
          )

    if error_log:
      raise loggers.ElectionError(error_log)


class MultipleInternationalizedTextWithSameLanguageCode(base.BaseRule):
  """Checks for multiple InternationalizedText with the same language code."""

  def elements(self):
    return _INTERNATIONALIZED_TEXT_ELEMENTS_WITH_ONLY_ONE_TEXT_PER_LANGUAGE

  def check(self, element):
    language_map = rule_util.get_language_to_text_map(element)

    for language, texts in language_map.items():
      if len(texts) > 1:
        raise loggers.ElectionError.from_message(
            'Multiple "%s" texts found for "%s"' % (language, texts[0].strip())
        )


class ContestContainsValidStartDate(base.DateRule):
  """Contest elements should contain valid start dates.

  A warning will be raised for start dates in the past. These dates are still
  valid because the validator could be run during an ongoing election.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_date:
      self.check_for_date_not_in_past(self.start_date, self.start_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ContestContainsValidEndDate(base.DateRule):
  """Contest elements should contain valid end dates.

  A warning will be raised for end dates in the past. These dates are still
  valid because the validator could be run during an ongoing election.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date:
      self.check_for_date_not_in_past(self.end_date, self.end_elem)

    if self.error_log:
      raise loggers.ElectionWarning(self.error_log)


class ContestEndDateOccursAfterStartDate(base.DateRule):
  """Contest elements should have end dates that occur after the start dates."""

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.end_date and self.start_date:
      self.check_end_after_start()
      if self.error_log:
        raise loggers.ElectionError(self.error_log)


class ContestEndDateOccursBeforeSubsequentContestStartDate(base.DateRule):
  """Contest end dates should occur before subsequent contest start dates.

  This rule will trigger if a Contest has a valid Subsequent Contest and both
  Contests have dates.
  """

  def elements(self):
    return ["ElectionReport"]

  def check(self, election_report_element):
    contest_by_contest_id = {}
    dates_by_contest_id = {}

    for election in self.get_elements_by_class(
        election_report_element, "Election"
    ):
      for contest in self.get_elements_by_class(election, "Contest"):
        contest_id = contest.get("objectId")
        self.reset_instance_vars()
        self.gather_dates(contest)
        contest_by_contest_id[contest_id] = contest
        dates_by_contest_id[contest_id] = (self.start_date, self.end_date)

    for contest_id, contest in contest_by_contest_id.items():
      # ignore contests that don't have a subsequent contest
      subsequent_element = contest.find("SubsequentContestId")
      if not rule_util.element_has_text(subsequent_element):
        continue
      # ignore invalid subsequent contest ids
      subsequent_contest_id = subsequent_element.text.strip()
      if subsequent_contest_id not in contest_by_contest_id:
        continue
      # compare contest end date with subsequent contest start date
      _, contest_end = dates_by_contest_id[contest_id]
      subsequent_contest_start, _ = dates_by_contest_id[subsequent_contest_id]
      if contest_end is not None and subsequent_contest_start is not None:
        if subsequent_contest_start < contest_end:
          self.error_log.append(
              loggers.LogEntry(
                  "Contest {} with end date {} does not occur before"
                  " subsequent contest {} with start date {}".format(
                      contest_id,
                      contest_end,
                      subsequent_contest_id,
                      subsequent_contest_start,
                  )
              )
          )

    if self.error_log:
      raise loggers.ElectionError(self.error_log)


class ContestStartDateContainsCorrespondingEndDate(base.DateRule):
  """Contest start dates must always have corresponding end dates.

  A Contest can either have both StartDate and EndDate populated or neither at
  all.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    self.reset_instance_vars()
    self.gather_dates(element)

    if self.start_elem is None and self.end_elem is not None:
      raise loggers.ElectionError.from_message(
          "Contest has an EndDate but is missing a StartDate. Every EndDate"
          " must have a corresponding StartDate.",
          [element],
      )

    if self.start_elem is not None and self.end_elem is None:
      raise loggers.ElectionError.from_message(
          "Contest has a StartDate but is missing an EndDate. Every StartDate"
          " must have a corresponding EndDate.",
          [element],
      )


class ValidatePollsCloseDatetimes(base.BaseRule):
  """Checks that LatestPollsClose is not before EarliestPollsClose."""

  def elements(self):
    return ["Contest"]

  def check(self, element):
    earliest_polls_close_element = element.find("EarliestPollsClose")
    latest_polls_close_element = element.find("LatestPollsClose")

    if not rule_util.element_has_text(
        earliest_polls_close_element
    ) or not rule_util.element_has_text(latest_polls_close_element):
      return

    earliest_polls_close_text = earliest_polls_close_element.text.strip()
    latest_polls_close_text = latest_polls_close_element.text.strip()

    try:
      earliest_polls_close = datetime.datetime.fromisoformat(
          earliest_polls_close_text
      )
      latest_polls_close = datetime.datetime.fromisoformat(
          latest_polls_close_text
      )

      if latest_polls_close < earliest_polls_close:
        raise loggers.ElectionError.from_message(
            f"LatestPollsClose ({latest_polls_close_text}) must not be before"
            f" EarliestPollsClose ({earliest_polls_close_text}) for Contest"
            f" {element.get('objectId')}.",
            [element],
        )
    except ValueError as e:
      raise loggers.ElectionError.from_message(
          "Invalid PollsClose datetime format in Contest"
          f" {element.get('objectId')}: {e}",
          [element],
      )


class ValidateResultsExpected(base.BaseRule):
  """Checks that ResultsExpected is not before the first ResultsReportingStage.

  The ResultsExpected datetime must not be before the ExpectedStartDateTime
  of the earliest ResultsReportingStage excluding the no-results stage.
  """

  def elements(self):
    return ["Contest"]

  def check(self, element):
    results_expected_element = element.find("ResultsExpected")
    if not rule_util.element_has_text(results_expected_element):
      return

    results_expected_text = results_expected_element.text.strip()

    try:
      results_expected = datetime.datetime.fromisoformat(results_expected_text)
    except ValueError as e:
      raise loggers.ElectionError.from_message(
          "Invalid ResultsExpected datetime format in Contest"
          f" {element.get('objectId')}: {e}",
          [element],
      )

    stage_collection = element.find("ResultsReportingStageCollection")
    if stage_collection is None:
      return

    earliest_start = None
    earliest_start_text = None
    for stage in stage_collection.findall("ResultsReportingStage"):
      stage_type_element = stage.find("StageType")
      if (
          rule_util.element_has_text(stage_type_element)
          and stage_type_element.text.strip() == "no-results"
      ):
        continue

      start_element = stage.find("ExpectedStartDateTime")
      if not rule_util.element_has_text(start_element):
        continue

      start_text = start_element.text.strip()
      try:
        start = datetime.datetime.fromisoformat(start_text)
        if earliest_start is None or start < earliest_start:
          earliest_start = start
          earliest_start_text = start_text
      except ValueError as e:
        raise loggers.ElectionError.from_message(
            "Invalid ExpectedStartDateTime datetime format for the"
            f" '{stage_type_element.text.strip()}' ResultsReportingStage in"
            f" Contest {element.get('objectId')}: {e}",
            [element],
        )

    if earliest_start and results_expected < earliest_start:
      raise loggers.ElectionError.from_message(
          f"ResultsExpected ({results_expected_text}) must not be before the"
          f" ExpectedStartDateTime ({earliest_start_text}) of the earliest"
          f" ResultsReportingStage for Contest {element.get('objectId')}.",
          [element],
      )


class ValidateResultsEmbargoEnd(base.BaseRule):
  """Checks that ResultsEmbargoEnd is not after the official ResultsReportingStage start."""

  def elements(self):
    return ["Contest"]

  def check(self, element):
    results_embargo_end_element = element.find("ResultsEmbargoEnd")
    if not rule_util.element_has_text(results_embargo_end_element):
      return

    results_embargo_end_text = results_embargo_end_element.text.strip()

    try:
      results_embargo_end = datetime.datetime.fromisoformat(
          results_embargo_end_text
      )
    except ValueError as e:
      raise loggers.ElectionError.from_message(
          "Invalid ResultsEmbargoEnd datetime format in Contest"
          f" {element.get('objectId')}: {e}",
          [element],
      )

    stage_collection = element.find("ResultsReportingStageCollection")
    if stage_collection is None:
      return

    official_start = None
    official_start_text = None
    for stage in stage_collection.findall("ResultsReportingStage"):
      stage_type_element = stage.find("StageType")
      if (
          rule_util.element_has_text(stage_type_element)
          and stage_type_element.text.strip() == "official"
      ):
        start_element = stage.find("ExpectedStartDateTime")
        if not rule_util.element_has_text(start_element):
          continue

        start_text = start_element.text.strip()
        try:
          official_start = datetime.datetime.fromisoformat(start_text)
          official_start_text = start_text
          break
        except ValueError as e:
          raise loggers.ElectionError.from_message(
              "Invalid ExpectedStartDateTime datetime format for the"
              " 'official' ResultsReportingStage in Contest"
              f" {element.get('objectId')}: {e}",
              [element],
          )

    if official_start and official_start < results_embargo_end:
      raise loggers.ElectionError.from_message(
          f"ResultsEmbargoEnd ({results_embargo_end_text}) must not be after"
          f" the ExpectedStartDateTime ({official_start_text}) of the official"
          f" ResultsReportingStage for Contest {element.get('objectId')}.",
          [element],
      )


class ResultsReportingStagesMustHaveUniqueType(base.BaseRule):
  """Checks that each ResultsReportingStage has a unique StageType per Contest."""

  def elements(self):
    return ["ResultsReportingStageCollection"]

  def check(self, element):
    stages_by_type = collections.defaultdict(list)
    for stage in element.findall("ResultsReportingStage"):
      stage_type_element = stage.find("StageType")
      if rule_util.element_has_text(stage_type_element):
        stage_type = stage_type_element.text.strip()
        stages_by_type[stage_type].append(stage)

    errors = []
    for stage_type, stages in stages_by_type.items():
      if len(stages) > 1:
        errors.append(
            loggers.LogEntry(
                f"Duplicate ResultsReportingStage StageType '{stage_type}'"
                " found in the same ResultsReportingStageCollection.",
                stages,
            )
        )
    if errors:
      raise loggers.ElectionError(errors)


class ValidateResultReportingStages(base.BaseRule):
  """Validates ResultsReportingStage elements in a stage collection."""

  def setup(self):
    self.composing_contest_ids = self._get_composing_contest_ids()

  def _get_composing_contest_ids(self):
    composing_contest_ids = set()
    for contest in self.get_elements_by_class(self.election_tree, "Contest"):
      composing_contest_ids_element = contest.find("ComposingContestIds")
      if rule_util.element_has_text(composing_contest_ids_element):
        composing_contest_ids.update(composing_contest_ids_element.text.split())
    return composing_contest_ids

  def elements(self):
    return ["ResultsReportingStageCollection"]

  def check(self, element):
    inherit_from_composed = rule_util.is_xml_true(
        element.find("InheritFromComposedContest")
    )
    stages = element.findall("ResultsReportingStage")

    if inherit_from_composed:
      error_log = []
      if stages:
        error_log.append(
            loggers.LogEntry(
                "ResultsReportingStageCollection must not contain any"
                " ResultsReportingStage elements when"
                " InheritFromComposedContest is true.",
                [element],
            )
        )
      contest = element.getparent()
      contest_id = contest.get("objectId") if contest is not None else None
      if contest_id not in self.composing_contest_ids:
        error_log.append(
            loggers.LogEntry(
                f"Contest {contest_id} sets InheritFromComposedContest to"
                " true but is not listed in the ComposingContestIds of any"
                " other Contest.",
                [contest],
            )
        )
      if error_log:
        raise loggers.ElectionError(error_log)
      return

    if not stages:
      raise loggers.ElectionError.from_message(
          "ResultsReportingStageCollection must contain at least one"
          " ResultsReportingStage element when InheritFromComposedContest is"
          " not true.",
          [element],
      )

    stage_types = set()
    for stage in stages:
      stage_type_element = stage.find("StageType")
      if rule_util.element_has_text(stage_type_element):
        stage_types.add(stage_type_element.text.strip())

    if (
        len(stages) < 2
        or "no-results" not in stage_types
        or stage_types.isdisjoint({"preliminary", "official"})
    ):
      raise loggers.ElectionWarning.from_message(
          "ResultsReportingStageCollection should contain at least two"
          " ResultsReportingStage elements, including one of StageType"
          " 'no-results' and at least one of StageType 'preliminary' or"
          " 'official', when InheritFromComposedContest is not true.",
          [element],
      )


class CandidateContestTypesAreCompatible(base.BaseRule):
  """CandidateContest Type values cannot have both a general and primary type."""

  def elements(self):
    return ["CandidateContest"]

  def check(self, element):
    primary_types = {
        "primary",
        "partisan-primary-open",
        "partisan-primary-closed",
    }
    contest_type_elements = element.findall("Type")
    if contest_type_elements:
      contest_types = {
          type_element.text.strip().lower()
          for type_element in contest_type_elements
          if rule_util.element_has_text(type_element)
      }
      if "general" in contest_types and primary_types.intersection(
          contest_types
      ):
        raise loggers.ElectionError.from_message(
            "CandidateContest {} has incompatible type values. A contest cannot"
            " have both a general and primary type.".format(
                element.get("objectId")
            ),
            [element],
        )


class NotEmptyUniqueDataSourceUris(base.BaseRule):
  """Checks that DataSource entities have globally unique URIs and they are not empty."""

  def elements(self):
    return ["DataSourceCollection"]

  def check(self, element):
    data_source_ids_by_uri = collections.defaultdict(set)
    error_log = []

    for data_source in element.findall("DataSource"):
      datasource_id = data_source.get("objectId")
      for uri_element in data_source.findall("Uri"):
        if not rule_util.element_has_text(uri_element):
          error_log.append(
              loggers.LogEntry(
                  "DataSource {} has an empty Uri.".format(datasource_id),
                  [data_source],
              )
          )
          continue
        uri = uri_element.text.strip()
        data_source_ids_by_uri[uri].add(data_source)

    for uri, data_sources in data_source_ids_by_uri.items():
      if len(data_sources) <= 1:
        continue
      sorted_data_sources = sorted(
          data_sources, key=lambda ds: ds.get("objectId")
      )
      data_source_ids = [
          data_source.get("objectId") for data_source in sorted_data_sources
      ]
      error_log.append(
          loggers.LogEntry(
              "DataSource entities {} have duplicate Uri '{}'.".format(
                  ", ".join(data_source_ids), uri
              ),
              sorted_data_sources,
          )
      )

    if error_log:
      raise loggers.ElectionError(error_log)


class UniqueDataSourceLanguages(base.BaseRule):
  """Checks that Uri elements have unique languages within a DataSource."""

  def elements(self):
    return ["DataSourceCollection"]

  def check(self, element):
    error_log = []

    for data_source in element.findall("DataSource"):
      data_source_id = data_source.get("objectId")
      seen_uri_languages = set()
      for uri_element in data_source.findall("Uri"):
        language = uri_element.get("language")
        if not language:
          error_log.append(
              loggers.LogEntry(
                  "DataSource {} has a Uri element without a language.".format(
                      data_source_id
                  ),
                  [uri_element],
              )
          )
          continue
        language = language.strip()
        if language in seen_uri_languages:
          error_log.append(
              loggers.LogEntry(
                  "DataSource {} has multiple Uri elements with the same"
                  " language '{}'.".format(data_source_id, language),
                  [element],
              )
          )
        else:
          seen_uri_languages.add(language)

    if error_log:
      raise loggers.ElectionError(error_log)


class UniqueDataSourceDisplayNames(base.BaseRule):
  """Checks that DataSource entities have globally unique DisplayNames."""

  def elements(self):
    return ["DataSourceCollection"]

  def check(self, element):
    data_source_ids_by_name = collections.defaultdict(set)
    error_log = []

    for data_source in element.findall("DataSource"):
      data_source_id = data_source.get("objectId")
      display_name_element = data_source.find("DisplayName")
      for text_element in display_name_element.findall("Text"):
        if not rule_util.element_has_text(text_element):
          error_log.append(
              loggers.LogEntry(
                  "DataSource {} has a DisplayName element without"
                  " text.".format(data_source_id),
                  [data_source],
              )
          )
          continue
        name_text = text_element.text.strip()
        data_source_ids_by_name[name_text].add(data_source)

    for name_text, data_sources in data_source_ids_by_name.items():
      if len(data_sources) <= 1:
        continue
      sorted_data_sources = sorted(
          data_sources, key=lambda ds: ds.get("objectId")
      )
      datasource_ids = [ds.get("objectId") for ds in sorted_data_sources]
      error_log.append(
          loggers.LogEntry(
              "DataSource entities {} have duplicate DisplayName '{}'.".format(
                  ", ".join(datasource_ids), name_text
              ),
              sorted_data_sources,
          )
      )

    if error_log:
      raise loggers.ElectionError(error_log)


def _get_attribution_depth(element):
  """Helper to recursively get the maximum depth of an Attribution tree."""
  children = element.findall("Attribution")
  if not children:
    return 1
  return 1 + max(_get_attribution_depth(child) for child in children)


def _get_datasource_id(element):
  """Helper to safely extract and strip the text of the DataSourceId child."""
  ds_element = element.find("DataSourceId")
  return (
      ds_element.text.strip() if rule_util.element_has_text(ds_element) else ""
  )


class AttributionDepthLimit(base.BaseRule):
  """Checks that each top-level Attribution in a ResultsReportingStage has at most three levels of depth."""

  def elements(self):
    return ["ResultsReportingStage"]

  def check(self, element):
    error_log = []
    # This findall query is non-recursive and only returns direct children.
    for attribution in element.findall("Attribution"):
      depth = _get_attribution_depth(attribution)
      if depth > 3:
        data_source_id = _get_datasource_id(attribution)
        error_log.append(
            loggers.LogEntry(
                f"Attribution starting with DataSourceId '{data_source_id}'"
                f" has a depth of {depth}, exceeding the limit of 3.",
                [attribution],
            )
        )
    if error_log:
      raise loggers.ElectionError(error_log)


def _canonicalize_cycle(cycle):
  """Canonicalizes a cycle by rotating it to start with the min element."""
  if not cycle:
    return []
  min_node = min(cycle)
  min_idx = cycle.index(min_node)
  return cycle[min_idx:] + cycle[:min_idx]


class AttributionContainsNoCycles(base.TreeRule):
  """Checks that there are no cycles between Attribution elements."""

  def check(self):
    graph = networkx.DiGraph()

    attributions = self.get_elements_by_class(self.election_tree, "Attribution")
    for attribution in attributions:
      data_source = _get_datasource_id(attribution)
      if not data_source:
        continue
      graph.add_node(data_source)
      for child in attribution.findall("Attribution"):
        child_data_source = _get_datasource_id(child)
        if child_data_source:
          graph.add_edge(data_source, child_data_source)

    # Find all nodes in the graph that are part of a cycle based on directed
    # paths.
    nodes_in_a_cycle = set()
    for component in networkx.strongly_connected_components(graph):
      # If the component has multiple nodes, it must be a cycle.
      if len(component) > 1:
        nodes_in_a_cycle.update(component)
        continue
      # Only include single-node components if they have a self-loop.
      (node,) = component
      if graph.has_edge(node, node):
        nodes_in_a_cycle.add(node)

    if not nodes_in_a_cycle:
      return

    error_log = []
    # Optimize performance for large graphs by excluding non-cyclic nodes.
    all_cycles_subgraph = graph.subgraph(sorted(nodes_in_a_cycle))
    for cycle in networkx.simple_cycles(all_cycles_subgraph):
      canonical = _canonicalize_cycle(cycle)
      # Append the starting node to the end to represent a closed loop.
      error_log.append(
          loggers.LogEntry(
              f"Cycle detected in Attribution: {' -> '.join(canonical)} ->"
              f" {canonical[0]}"
          )
      )
    raise loggers.ElectionError(error_log)


class ValidateSpecialBallotSelectionCountedInTotal(base.BaseRule):
  """Enforces constraints on CountedInTotal for SpecialBallotSelections.

  More specifically, BlankBallotSelection, NullBallotSelection, and
  NoneOfTheAboveSelection must have an explicit value for CountedInTotal, and
  AggregateBallotSelection must not have this set.
  """

  def elements(self):
    return [
        "BlankBallotSelection",
        "NullBallotSelection",
        "NoneOfTheAboveBallotSelection",
        "AggregateBallotSelection",
    ]

  def check(self, element):
    counted_in_total = element.find("CountedInTotal")
    tag = element.tag

    if tag in (
        "BlankBallotSelection",
        "NullBallotSelection",
        "NoneOfTheAboveBallotSelection",
    ) and not rule_util.element_has_text(counted_in_total):
      raise loggers.ElectionError.from_message(
          f"{tag} must have an explicit value for CountedInTotal.",
          [element],
      )
    elif tag == "AggregateBallotSelection" and counted_in_total is not None:
      raise loggers.ElectionError.from_message(
          "AggregateBallotSelection must not have CountedInTotal set.",
          [element],
      )


class ValidateIncludeInAggregationBallotSelections(base.BaseRule):
  """Validates BallotSelections with IncludedInAggregation.

  Checks that the sum of all vote counts for a BallotSelection with
  IncludedInAggregation must not be > the total vote counts for the
  AggregateBallotSelection on that same Contest for the same vote count type.
  Also requires that if IncludedInAggregation is set on any BallotSelection then
  the AggregateBallotSelection must also be present on that Contest.
  """

  def elements(self):
    return ["CandidateContest", "PartyContest"]

  def _gather_vote_counts(self, element):
    """Gathers vote counts from a selection element grouped by type."""
    count_by_type_and_gp_unit = collections.defaultdict(float)
    vote_counts_collection = element.find("VoteCountsCollection")
    if vote_counts_collection is None:
      return count_by_type_and_gp_unit

    for vote_counts in vote_counts_collection.findall("VoteCounts"):
      count_element = vote_counts.find("Count")
      if not rule_util.element_has_text(count_element):
        continue
      count = float(count_element.text)

      vote_count_type = _get_type_or_other_type(vote_counts)
      gp_unit_id_element = vote_counts.find("GpUnitId")
      gp_unit_id = (
          gp_unit_id_element.text.strip()
          if rule_util.element_has_text(gp_unit_id_element)
          else ""
      )

      type_and_gp_unit = (vote_count_type, gp_unit_id)
      count_by_type_and_gp_unit[type_and_gp_unit] += count

    return count_by_type_and_gp_unit

  def check(self, element):
    contest_id = element.get("objectId")

    candidate_selections = self.get_elements_by_class(
        element, "CandidateSelection"
    )
    party_selections = self.get_elements_by_class(element, "PartySelection")
    all_selections = candidate_selections + party_selections

    included_selections = []
    for selection in all_selections:
      if rule_util.is_xml_true(selection.find("IncludedInAggregation")):
        included_selections.append(selection)
    if not included_selections:
      return

    aggregate_selection = element.find("AggregateBallotSelection")
    if aggregate_selection is None:
      raise loggers.ElectionError.from_message(
          f"Contest {contest_id} has selections marked as IncludedInAggregation"
          " but is missing AggregateBallotSelection.",
          [element],
      )

    aggregate_count_by_type_and_gp_unit = self._gather_vote_counts(
        aggregate_selection
    )

    selections_count_sum_by_type_and_gp_unit = collections.defaultdict(float)
    for selection in included_selections:
      for (
          type_and_gp_unit,
          count,
      ) in self._gather_vote_counts(selection).items():
        selections_count_sum_by_type_and_gp_unit[type_and_gp_unit] += count

    error_log = []
    for (
        type_and_gp_unit,
        total_count,
    ) in selections_count_sum_by_type_and_gp_unit.items():
      aggregate_count = aggregate_count_by_type_and_gp_unit[type_and_gp_unit]
      if total_count > aggregate_count:
        resolved_type, gp_unit_id = type_and_gp_unit
        error_log.append(
            loggers.LogEntry(
                f"In Contest {contest_id}, the sum of vote counts"
                f" ({total_count}) for selections marked as"
                " IncludedInAggregation exceeds the vote count"
                f" ({aggregate_count}) for the AggregateBallotSelection for"
                f" vote count type='{resolved_type}' (GpUnit: '{gp_unit_id}').",
                [element],
            )
        )

    if error_log:
      raise loggers.ElectionError(error_log)


ELECTION_RULES = common_rules.COMMON_RULES + (
    # go/keep-sorted start
    AttributionContainsNoCycles,
    AttributionDepthLimit,
    BallotTitle,
    CandidateContestTypesAreCompatible,
    CandidatesReferencedInRelatedContests,
    CoalitionParties,
    ComposingContestIdsAreValidRelatedContests,
    ContestContainsValidEndDate,
    ContestContainsValidStartDate,
    ContestEndDateOccursAfterStartDate,
    ContestEndDateOccursBeforeSubsequentContestStartDate,
    ContestHasMultipleOffices,
    ContestHasValidContestStage,
    ContestStartDateContainsCorrespondingEndDate,
    CorrectCandidateSelectionCount,
    DateStatusMatches,
    DuplicateBallotTitleSeatPair,
    DuplicateContestNames,
    DuplicatedPartyAbbreviation,
    DuplicatedPartyName,
    ElectionContainsStartAndEndDates,
    ElectionDatesSpanContestDates,
    ElectionEndDatesInThePast,
    ElectionEndDatesOccurAfterStartDates,
    ElectionStartDates,
    ElectionTypesAndCandidateContestTypesAreCompatible,
    ElectionTypesAreCompatible,
    FullTextMaxLength,
    FullTextOrBallotText,
    GpUnitsHaveSingleRoot,
    ImproperCandidateContest,
    MissingPartyAbbreviationTranslation,
    MissingPartyNameTranslation,
    MultipleCandidatesPointToTheSamePersonInTheSameContest,
    MultipleInternationalizedTextWithSameLanguageCode,
    NotEmptyUniqueDataSourceUris,
    OfficeHasjurisdictionSameAsElectoralDistrict,
    PartisanPrimary,
    PartisanPrimaryHeuristic,
    PercentSum,
    ProperBallotSelection,
    ResultsReportingStagesMustHaveUniqueType,
    SelfDeclaredCandidateMethod,
    SingularPartySelection,
    SubsequentContestIdIsValidRelatedContest,
    UniqueDataSourceDisplayNames,
    UniqueDataSourceLanguages,
    ValidateDuplicateColors,
    ValidateIncludeInAggregationBallotSelections,
    ValidateInfoUriAnnotation,
    ValidatePollsCloseDatetimes,
    ValidateResultReportingStages,
    ValidateResultsEmbargoEnd,
    ValidateResultsExpected,
    ValidateSpecialBallotSelectionCountedInTotal,
    VoteCountTypesCoherency,
    VoteCountValidSeatsDeltaTypes,
    WinnerCountLimit,
    # go/keep-sorted end
)

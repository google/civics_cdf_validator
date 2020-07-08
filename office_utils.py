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
"""Utilities to validate offices in the XML feed."""

from __future__ import print_function


valid_office_level_values = {
    "Country", "Municipality", "Neighbourhood", "District", "Region",
    "International", "Ward", "Administrative Area 1", "Administrative Area 2"
}

valid_office_role_values = {
    "auditor", "attorney general", "bailiff", "board of regents",
    "chief of police", "circuit clerk", "circuit court", "city clerk",
    "city council", "civil court at law", "constable", "coroner",
    "county assessor", "county attorney", "county clerk", "county commissioner",
    "county council", "county court", "county recorder", "county surveyor",
    "court at law", "court at law clerk", "court of last resort",
    "criminal appeals court", "criminal court at law", "deputy state executive",
    "district attorney", "district clerk", "district court", "fire",
    "governors council", "head of government", "head of state", "health care",
    "intermediate appellate court", "jailer", "justice of the peace",
    "lower house", "mayor", "other", "parks", "president",
    "probate court at law", "prosecutor", "public administrator",
    "public defender", "referenda", "register deeds", "registrar of voters",
    "sanitation", "secretary agriculture", "secretary education",
    "secretary insurance", "secretary labor", "secretary land",
    "secretary state", "school board", "sheriff", "solicitor general",
    "state board education", "state executive", "state lower house",
    "state tribal relations", "state upper house", "subcounty executive",
    "superior clerk", "superior court", "tax court", "taxes", "treasurer",
    "upper house", "utilities", "vice president", "water",
    "workers compensation court"
}

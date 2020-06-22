# -*- coding: utf-8 -*-
"""Unit test for loggers.py."""

from absl.testing import absltest
from civics_cdf_validator import loggers
from lxml import etree


class ParentHierarchyObjectIdStrTest(absltest.TestCase):

  def testParentHierarchyIsEmpty(self):
    uri = "<Uri>www.facebook.com/michael_scott</Uri>"
    uri_element = etree.fromstring(uri)
    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Uri", actual_value)

  def testParentHierarchyStopWhenObjectIdIsdefined(self):
    election_feed = """
      <ElectionReport>
        <PersonCollection>
          <Person objectId="per1">
            <ContactInformation>
              <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
              </Uri>
            </ContactInformation>
          </Person>
        </PersonCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find(
        "PersonCollection/Person/ContactInformation/Uri")

    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("Person:per1 > ContactInformation > Uri", actual_value)

  def testParentHierarchyToTheTopIfNoObjectIdIsdefined(self):
    election_feed = """
      <ElectionReport>
        <Election>
          <ContactInformation>
            <Uri Annotation="personal-facebook">www.facebook.com/michael_scott
            </Uri>
          </ContactInformation>
        </Election>
      </ElectionReport>
    """
    election_tree = etree.fromstring(election_feed)
    uri_element = election_tree.find("Election/ContactInformation/Uri")

    actual_value = loggers.get_parent_hierarchy_object_id_str(uri_element)
    self.assertEqual("ElectionReport > Election > ContactInformation > Uri",
                     actual_value)


if __name__ == "__main__":
  absltest.main()

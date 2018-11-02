#    Copyright 2019 StackHPC
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from oslo_config import cfg
from oslo_utils.fixture import uuidsentinel as uuids

from nova import context
from nova import objects
from nova.limits import local as local_limits
from nova import exception
from nova import test

CONF = cfg.CONF


class TestLocalLimits(test.NoDBTestCase):

    def setUp(self):
        super(TestLocalLimits, self).setUp()
        # TODO
        CONF.set_override("use_oslo_limit", True, group="quota")
        self._ctxt = context.RequestContext()
        self._ctxt.project_id = uuids.project_id
        self._ctxt.user_id = uuids.user_id

    def test_check_count_raises_for_invalid_entity(self):
        e = self.assertRaises(ValueError,
                              local_limits.check_count,
                              local_limits.KEY_PAIRS, 42)
        self.assertEqual("entity_type", str(e))

    def test_check_count_metadata(self):
        local_limits.check_count(local_limits.SERVER_METADATA_ITEMS, 42)

        CONF.set_override("metadata_items", 41, group="quota")
        e = self.assertRaises(exception.OverQuota,
                              local_limits.check_count,
                              local_limits.SERVER_METADATA_ITEMS, 42)
        self.assertEqual("Quota exceeded for resources: ['metadata_items']",
                         str(e))

    def test_check_injected_files(self):
        local_limits.check_count(local_limits.INJECTED_FILES, 5)
        local_limits.check_count(local_limits.INJECTED_FILES_CONTENT, 42)
        local_limits.check_count(local_limits.INJECTED_FILES_PATH, 42)

        CONF.set_override("injected_files", 41, group="quota")
        CONF.set_override("injected_file_content_bytes", 41, group="quota")
        CONF.set_override("injected_file_path_length", 41, group="quota")

        e = self.assertRaises(exception.OverQuota,
                              local_limits.check_count,
                              local_limits.INJECTED_FILES, 42)
        self.assertEqual("Quota exceeded for resources: ['injected_files']",
                         str(e))
        e = self.assertRaises(exception.OverQuota,
                              local_limits.check_count,
                              local_limits.INJECTED_FILES_CONTENT, 42)
        self.assertEqual("Quota exceeded for resources: "
                         "['injected_file_content_bytes']",
                         str(e))
        e = self.assertRaises(exception.OverQuota,
                              local_limits.check_count,
                              local_limits.INJECTED_FILES_PATH, 42)
        self.assertEqual("Quota exceeded for resources: "
                         "['injected_file_path_bytes']",
                         str(e))

    @mock.patch.object(objects.KeyPairList, "get_count_by_user")
    def test_check_data_keypairs(self, mock_count):
        mock_count.return_value = 99
        local_limits.check_delta(self._ctxt, local_limits.KEY_PAIRS,
                                 self._ctxt.user_id, 1)
        mock_count.assert_called_once_with(self._ctxt, self._ctxt.user_id)

        self.assertRaises(exception.OverQuota,
                          local_limits.check_delta,
                          self._ctxt, local_limits.KEY_PAIRS,
                          self._ctxt.user_id, 2)

    @mock.patch.object(objects.InstanceGroupList, "get_counts")
    def test_check_data_server_groups(self, mock_count):
        mock_count.return_value = {'project': 9}
        local_limits.check_delta(self._ctxt, local_limits.SERVER_GROUPS,
                                 uuids.project_id, 1)
        mock_count.assert_called_once_with(self._ctxt, uuids.project_id)

        self.assertRaises(exception.OverQuota,
                          local_limits.check_delta,
                          self._ctxt, local_limits.SERVER_GROUPS,
                          uuids.project_id, 2)

    @mock.patch.object(objects.InstanceGroup, "get_by_uuid")
    def test_check_data_server_group_members(self, mock_get):
        mock_get.return_value = objects.InstanceGroup(Members=[])
        local_limits.check_delta(self._ctxt, local_limits.SERVER_GROUP_MEMBERS,
                                 uuids.server_group, 10)
        mock_get.assert_called_once_with(uuids.server_group)

        self.assertRaises(exception.OverQuota,
                          local_limits.check_delta,
                          self._ctxt, local_limits.SERVER_GROUP_MEMBERS,
                          uuids.server_group, 11)

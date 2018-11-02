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

from oslo_limit import limit
from oslo_config import cfg
from oslo_utils.fixture import uuidsentinel as uuids

from nova import context
from nova import objects
from nova.limits import keystone as keystone_limits
from nova.scheduler import utils
from nova import test

CONF = cfg.CONF


class TestKeystoneLimits(test.NoDBTestCase):
    def setUp(self):
        super(TestKeystoneLimits, self).setUp()
        CONF.set_override("use_oslo_limit", True, group="quota")
        self._ctxt = context.RequestContext()
        self._ctxt.project_id = uuids.project_id
        self._ctxt.user_id = uuids.user_id
        self._flavor = objects.Flavor(ram=100, cpu=10, root_disk=5)
        self._instance = objects.Instance(uuid=uuids.instance_id,
                                          flavor=objects.Flavor(ram=10))

        keystone_limits._ENFORCER = mock.Mock(limit.EndpointEnforcerContext)

    def test_check_limits(self):
        keystone_limits.check_limits(self._ctxt, uuids.project_id)

        keystone_limits._ENFORCER.check_all_limits.assert_called_once_with(
            self._ctxt, uuids.project_id, None)

    @mock.patch.object(utils, "resources_from_flavor")
    def test_check_limits_build(self, mock_ff):
        mock_ff.return_value = {"a": 1}
        keystone_limits.check_limits(self._ctxt, uuids.project_id,
                                     self._instance)
        mock_ff.assert_called_once_with(self._instance, self._instance.flavor)
        keystone_limits._ENFORCER.check_all_limits.assert_called_once_with(
            self._ctxt, uuids.project_id, {"a": 1})

    @mock.patch.object(utils, "resources_from_flavor")
    def test_check_limits_resize(self, mock_ff):
        mock_ff.return_value = {"b": 1}
        keystone_limits.check_limits(self._ctxt, uuids.project_id,
                                     self._instance, self._flavor)
        mock_ff.assert_called_once_with(self._instance, self._flavor)
        keystone_limits._ENFORCER.check_all_limits.assert_called_once_with(
            self._ctxt, uuids.project_id, {"b": 1})
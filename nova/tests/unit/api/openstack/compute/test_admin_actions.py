#   Copyright 2011 OpenStack Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import mock
from oslo_utils.fixture import uuidsentinel as uuids

from nova.api.openstack.compute import admin_actions as admin_actions_v21
from nova import context
from nova import exception
from nova import objects
from nova import test
from nova.tests import fixtures as nova_fixtures
from nova.tests.unit.api.openstack.compute import admin_only_action_common
from nova.tests.unit.api.openstack import fakes
from nova.tests.unit import policy_fixture


class AdminActionsTestV21(admin_only_action_common.CommonTests):
    admin_actions = admin_actions_v21
    _api_version = '2.1'

    def setUp(self):
        super(AdminActionsTestV21, self).setUp()
        self.controller = self.admin_actions.AdminActionsController()
        self.compute_api = self.controller.compute_api
        self.stub_out('nova.api.openstack.compute.admin_actions.'
                      'AdminActionsController',
                      lambda *a, **k: self.controller)

    def test_actions(self):
        actions = ['_reset_network', '_inject_network_info']
        method_translations = {'_reset_network': 'reset_network',
                               '_inject_network_info': 'inject_network_info'}

        self._test_actions(actions, method_translations)

    def test_actions_with_non_existed_instance(self):
        actions = ['_reset_network', '_inject_network_info']
        self._test_actions_with_non_existed_instance(actions)

    def test_actions_with_locked_instance(self):
        actions = ['_reset_network', '_inject_network_info']
        method_translations = {'_reset_network': 'reset_network',
                               '_inject_network_info': 'inject_network_info'}

        self._test_actions_with_locked_instance(actions,
            method_translations=method_translations)


class PolicyEnforcementBase(test.NoDBTestCase):
    USES_DB_SELF = True

    def setUp(self):
        super(PolicyEnforcementBase, self).setUp()

        self.policy = self.useFixture(policy_fixture.RealPolicyFixture())

        self.project_id = uuids.project_id
        self.project_id_other = uuids.project_id_other
        self.legacy_admin_project = uuids.legacy_admin_project

        self.system_admin = context.RequestContext(
                "system_admin", None,
                roles=['admin'], system_scope='all')

        self.legacy_system_admin = context.RequestContext(
                "legacy_system_admin",  self.legacy_admin_project,
                roles=['admin'])

        self.project_member = context.RequestContext(
                "project_member", self.project_id,
                roles=['member'])

        self.legacy_project_member = context.RequestContext(
                "legacy_project_member", self.project_id,
                roles=['foo'])

        self.other_project_member = context.RequestContext(
                "other_project_member", self.project_id_other,
                roles=['member'])

        self.useFixture(nova_fixtures.Database(database='api'))
        fix = nova_fixtures.CellDatabases()
        fix.add_cell_database('cell1')
        self.useFixture(fix)

        mapping = objects.CellMapping(context=self.project_member,
                                       uuid=uuids.cell_mapping,
                                       database_connection='cell1',
                                       transport_url='none:///')
        mapping.create()
        with context.target_cell(self.project_member, mapping) as cctxt:
            instance = objects.Instance(
                context=cctxt,
                project_id=self.project_id,
                uuid=uuids.fake_id)
            instance.create()
        im = objects.InstanceMapping(context=self.project_member,
                                     instance_uuid=instance.uuid,
                                     cell_mapping=mapping,
                                     project_id=self.project_id)
        im.create()
        self.fake_id = uuids.fake_id


class AdminActionsPolicyEnforcementV21(PolicyEnforcementBase):

    def setUp(self):
        super(AdminActionsPolicyEnforcementV21, self).setUp()
        self.controller = admin_actions_v21.AdminActionsController()
        self.req = fakes.HTTPRequest.blank('')

    def common_policy_check(self, rule_name, fun_name, req, *arg, **kwarg):
        func = getattr(self.controller, fun_name)

        def ensure_raises(req):
            exc = self.assertRaises(
                exception.PolicyNotAuthorized, func, req, *arg, **kwarg)
            self.assertEqual(
                "Policy doesn't allow %s to be performed." %
                rule_name, exc.format_message())

        req.environ['nova.context'] = self.project_member
        ensure_raises(req)
        req.environ['nova.context'] = self.legacy_project_member
        ensure_raises(req)
        req.environ['nova.context'] = self.other_project_member
        ensure_raises(req)

        # TODO add required mox to make this work
        req.environ['nova.context'] = self.system_admin
        func(req, *arg, **kwarg)

        # TODO this now fails due to adding the system_scope check
        req.environ['nova.context'] = self.legacy_system_admin
        ensure_raises(req)
        #func(req, *arg, **kwarg)


    def test_reset_network_policy_failed(self):
        rule_name = "os_compute_api:os-admin-actions:reset_network"
        with mock.patch.object(self.controller.compute_api, "reset_network"):
            self.common_policy_check(
                rule_name, "_reset_network", self.req, self.fake_id, body={})

    def test_inject_network_info_policy_failed(self):
        rule_name = "os_compute_api:os-admin-actions:inject_network_info"
        with mock.patch.object(self.controller.compute_api,
                               "inject_network_info"):
            self.common_policy_check(
                rule_name, "_inject_network_info", self.req, self.fake_id,
                body={})

    def test_reset_state_policy_failed(self):
        rule_name = "os_compute_api:os-admin-actions:reset_state"
        self.common_policy_check(
            rule_name, "_reset_state", self.req,
            self.fake_id, body={"os-resetState": {"state": "active"}})

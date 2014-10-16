# Copyright (c) 2014 Rackspace
# All Rights Reserved.
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

from nova import test
from nova.tests.unit.virt.xenapi import plugins

glance = plugins.load_plugin("glance")


class TestGlance(test.NoDBTestCase):
    @mock.patch.object(glance.utils, "cleanup_staging_area")
    @mock.patch.object(glance, "_upload_tarball")
    @mock.patch.object(glance.utils, "prepare_staging_area")
    @mock.patch.object(glance.utils, "make_staging_area")
    def test_upload_vhd(self, mock_make, mock_prepare, mock_upload,
                        mock_cleanup):
        glance.upload_vhd(None, None, None, None, None, None, None, None, None)

        self.assertTrue(mock_make.called)
        self.assertTrue(mock_prepare.called)
        self.assertTrue(mock_upload.called)
        self.assertTrue(mock_cleanup.called)

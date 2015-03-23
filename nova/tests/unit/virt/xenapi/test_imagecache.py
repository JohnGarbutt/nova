# Copyright 2015 Rackspace
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

from oslo_utils import timeutils

from nova.tests.unit.virt.xenapi import stubs
from nova.virt.xenapi.client import session as xenapi_session
from nova.virt.xenapi import fake as xenapi_fake
from nova.virt.xenapi import glance_utils
from nova.virt.xenapi import imagecache
from nova.virt.xenapi import vm_utils


class ImageCacheTestCase(stubs.XenAPITestBaseNoDB):
    def setUp(self):
        super(ImageCacheTestCase, self).setUp()
        self._setup_imagecache()
        self.vms = []

    def _setup_imagecache(self):
        stubs.stubout_session(self.stubs, xenapi_fake.SessionBase)
        self.session = xenapi_session.XenAPISession('test_url', 'root',
                                                    'test_pass')
        self.imagecache = imagecache.ImageCacheManager(self.session)

    @mock.patch.object(imagecache.ImageCacheManager,
            "_list_running_instances")
    @mock.patch.object(imagecache.ImageCacheManager,
            "_age_and_verify_cached_images")
    def test_update(self, mock_age, mock_list_running):
        mock_list_running.return_value = {"used_images": []}

        context = "ctx"
        all_instances = ["instance"]
        self.imagecache.update("ctx", all_instances)

        mock_list_running.assert_called_once_with(context, all_instances)
        mock_age.assert_called_once_with()

    def test_get_current_base_image_list_not_glance(self):
        self.flags(cache_glance_base_images=False, group="xenserver")
        result = self.imagecache._get_current_base_image_list("context")
        self.assertEqual([], result)

    @mock.patch.object(glance_utils, "list_images")
    def test_get_current_base_image_list_glance(self, mock_list):
        self.flags(cache_glance_base_images=True, group="xenserver")
        mock_list.return_value = [
            {"id": "uuid1", "visibility": "public"},
            {"id": "uuid2", "visibility": "private"},
        ]

        result = self.imagecache._get_current_base_image_list("context")

        self.assertEqual(["uuid1"], result)
        mock_list.assert_called_once_with("context")

    def test_get_expiry_has_date(self):
        time = timeutils.utcnow()
        time_str = timeutils.strtime(time)
        vdi_info = {
            "ref": "vdi_ref",
            "rec": {"other_config": {"cache-expiry": time_str}}}

        result = self.imagecache._get_expiry(vdi_info)

        self.assertEqual(result, time)

    def test_get_expiry_no_date(self):
        vdi_info = {"ref": "vdi_ref", "rec": {}}
        result = self.imagecache._get_expiry(vdi_info)
        self.assertIsNone(result)

    def test_estimate_size(self):
        vdi_info = {"rec": {"virtual_size": '10'}}
        result = self.imagecache._estimate_size(vdi_info)
        self.assertEqual(result, 10)

    @mock.patch.object(vm_utils, "try_clear_cached_vdi_expiry")
    def test_clear_expiry_flag_no_expiry(self, mock_clear):
        vdi_info = {"ref": "base_ref", "rec": {}}
        self.imagecache._clear_expiry_flag("uuid", vdi_info)
        self.assertFalse(mock_clear.called)

    @mock.patch.object(vm_utils, "try_clear_cached_vdi_expiry")
    @mock.patch.object(imagecache.ImageCacheManager, "_get_expiry")
    def test_clear_expiry_flag_has_expiry(self, mock_expiry, mock_clear):
        mock_expiry.return_value = "fake"
        vdi_info = {"ref": "vdi_ref", "rec": {}}

        self.imagecache._clear_expiry_flag("uuid", vdi_info)

        mock_clear.assert_called_once_with(self.imagecache.session, "vdi_ref")

    @mock.patch.object(vm_utils, "find_all_cached_images")
    def test_age_and_verify_cached_images_no_images(self, mock_find):
        mock_find.return_value = {}
        self.imagecache._age_and_verify_cached_images()
        mock_find.assert_called_once_with(self.session)

    @mock.patch.object(imagecache.ImageCacheManager, "_estimate_size")
    @mock.patch.object(imagecache.ImageCacheManager, "_clear_expiry_flag")
    @mock.patch.object(imagecache.ImageCacheManager, "_is_cached_vdi_expired")
    @mock.patch.object(vm_utils, "try_delete_cached_image")
    @mock.patch.object(vm_utils, "find_all_cached_images")
    def test_age_and_verify_cached_images_with_images(self, mock_find,
                mock_delete, mock_expired, mock_clear, mock_size):
        base_info = {"ref": "base_ref"}
        used_info = {"ref": "used_ref"}
        old_info = {"ref": "old_ref"}
        expired_info = {"ref": "expired_ref"}
        mock_find.return_value = {
            "base": base_info,
            "used": used_info,
            "old_not_expired": old_info,
            "expired": expired_info,
            }
        self.imagecache.current_base_images.append("base")
        self.imagecache.used_images["used"] = "stuff"
        mock_expired.side_effect = lambda a, b: a == "expired"

        self.imagecache._age_and_verify_cached_images()
        mock_find.assert_called_once_with(self.session)
        mock_delete.assert_called_once_with(
                self.session, "expired", "expired_ref")
        self.assertEqual(2, mock_expired.call_count)
        self.assertEqual(2, mock_clear.call_count)
        self.assertEqual(4, mock_size.call_count)
        expired_calls = [mock.call("expired", expired_info),
                         mock.call("old_not_expired", old_info)]
        mock_expired.assert_has_calls(expired_calls, any_order=True)
        clear_calls = [mock.call("base", base_info),
                       mock.call("used", used_info)]
        mock_clear.assert_has_calls(clear_calls, any_order=True)

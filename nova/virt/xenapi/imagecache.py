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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

from nova.i18n import _LI, _LW
from nova.virt import imagecache
from nova.virt.xenapi import glance_utils
from nova.virt.xenapi import vm_utils

LOG = logging.getLogger(__name__)

imagecache_opts = [
    cfg.BoolOpt("cache_glance_base_images", default=False,
               help='If true, keep current glance public images cached.'),
    cfg.IntOpt("cache_unused_expiry_seconds", default=60,
               help='If 0 delete unused images immediately, otherwise'
                    ' delete when checked after the given expiry seconds.'),
]

CONF = cfg.CONF
CONF.register_opts(imagecache_opts, group='xenserver')


class ImageCacheManager(imagecache.ImageCacheManager):
    def __init__(self, session):
        super(ImageCacheManager, self).__init__()
        self.session = session
        self.used_images = {}
        self.current_base_images = []

    def update(self, context, all_instances):
        running = self._list_running_instances(context, all_instances)
        self.used_images = running['used_images']
        self.current_base_images = self._get_current_base_image_list(context)
        self._age_and_verify_cached_images()

    def _get_current_base_image_list(self, context):
        if not CONF.xenserver.cache_glance_base_images:
            return []

        images = glance_utils.list_images(context)
        base_images = [image['id'] for image in images
                        if image['visibility'] == 'public']
        LOG.debug("Number of base images from glance: %s", len(base_images))
        return base_images

    def _get_expiry(self, vdi_info):
        vdi_rec = vdi_info["rec"]
        expiry_str = vdi_rec.get("other_config", {}).get('cache-expiry', None)
        if not expiry_str:
            return None
        return timeutils.parse_strtime(expiry_str)

    def _estimate_size(self, vdi_info):
        vdi_rec = vdi_info["rec"]
        # NOTE(johngarbutt) while the image could be significantly less
        # than this size, that involves walking the VDI chain,
        # so using virtual size to avoid that expensive operation.
        return int(vdi_rec["virtual_size"])

    def _is_cached_vdi_expired(self, image_uuid, vdi_info):
        expiry = self._get_expiry(vdi_info)
        now = timeutils.utcnow()

        if not expiry:
            LOG.debug("Add expiry to vdi for image: %s", image_uuid)
            expiry_str = timeutils.strtime(now)
            vdi_ref = vdi_info["ref"]
            vm_utils.set_cached_vdi_expiry(self.session, vdi_ref, expiry_str)
            return False

        delta_sec = timeutils.delta_seconds(expiry, now)
        return delta_sec >= CONF.xenserver.cache_unused_expiry_seconds

    def _clear_expiry_flag(self, image_uuid, vdi_info):
        expiry = self._get_expiry(vdi_info)
        if expiry:
            LOG.debug("Clearing expiry flag: %s", image_uuid)
            vdi_ref = vdi_info["ref"]
            expiry = vm_utils.try_clear_cached_vdi_expiry(
                    self.session, vdi_ref)

    def _age_and_verify_cached_images(self):
        cached_images = vm_utils.find_all_cached_images(self.session)
        LOG.debug("Number of images in cache: %s", len(cached_images))

        sizes = []
        current_base = []
        in_use = []
        not_in_use_not_expired = []
        deleted = []
        errors = []

        for image_uuid, vdi_info in cached_images.items():
            is_in_use = image_uuid in self.used_images
            is_current_base = image_uuid in self.current_base_images

            if not is_in_use and not is_current_base:
                is_expired = self._is_cached_vdi_expired(image_uuid, vdi_info)
            else:
                is_expired = False
                self._clear_expiry_flag(image_uuid, vdi_info)

            if not is_in_use and not is_current_base and is_expired:
                vdi_ref = vdi_info["ref"]
                was_deleted = vm_utils.try_delete_cached_image(
                        self.session, image_uuid, vdi_ref)

                if was_deleted:
                    deleted.append(image_uuid)
                else:
                    errors.append(image_uuid)

            if is_in_use:
                in_use.append(image_uuid)
            if is_current_base:
                current_base.append(image_uuid)
            if not is_in_use and not is_current_base and not is_expired:
                not_in_use_not_expired.append(image_uuid)

            sizes.append(self._estimate_size(vdi_info))

        if sizes:
            LOG.debug("Estimated image cache size (bytes): %s", sum(sizes))
            LOG.debug("Estimated max image cache size (bytes): %s", max(sizes))
        LOG.debug("In use images in cache: %s", in_use)
        LOG.debug("Current base images in cache: %s", current_base)
        if not_in_use_not_expired:
            LOG.debug(_LI("Images not deleted as not yet expired: %s"),
                            not_in_use_not_expired)
        for image in deleted:
            LOG.info(_LI("Image deleted from cache: %s"), image)
        for image in errors:
            LOG.warning(_LW("Image unable to be deleted from cache: %s"),
                        image)

        # TODO(johngarbutt) need to verify all md5

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

from oslo_log import log as logging

import nova.conf
from nova import exception
from nova import objects

LOG = logging.getLogger(__name__)
CONF = nova.conf.CONF

# Cache to avoid repopulating ksa state
PLACEMENT_CLIENT = None

KEY_PAIRS = "key_pairs"
SERVER_GROUPS = "server_groups"
SERVER_GROUP_MEMBERS = "server_group_members"

SERVER_METADATA_ITEMS = "metadata_items"
INJECTED_FILES = "injected_files"
INJECTED_FILES_CONTENT = "injected_file_content_bytes"
INJECTED_FILES_PATH = "injected_file_path_bytes"

COUNT_LIMITS = {
    SERVER_METADATA_ITEMS: "metadata_items",
    INJECTED_FILES: "injected_files",
    INJECTED_FILES_CONTENT: "injected_file_content_bytes",
    INJECTED_FILES_PATH: "injected_file_path_length",
}


def _keypair_count(context, user_id):
    return objects.KeyPairList.get_count_by_user(context, user_id)


def _server_group_count(context, project_id):
    raw_counts = objects.InstanceGroupList.get_counts(context, project_id)
    return raw_counts['project']


def _server_group_members_count(context, server_group_uuid):
    # NOTE(johngarbutt) we used to count members added per user
    server_group = objects.InstanceGroup.get_by_uuid(server_group_uuid)
    return len(server_group.Members)


COUNTABLE_ENTITIES = {
    KEY_PAIRS: (CONF.quota.key_pairs, _keypair_count),
    SERVER_GROUPS: (CONF.quota.server_groups, _server_group_count),
    SERVER_GROUP_MEMBERS: (CONF.quota.server_group_members,
                           _server_group_members_count)
}


def check_delta(context, entity_type, entity_scope, delta):
    """Check provided delta does not put resource over limit.

    Firstly we count the current usage given the specified scope.
    We then add that count to the specified  delta to see if we
    are over the limit for that kind of entity.

    Note previously we used to recheck these limits.
    However these are really soft DDoS protections,
    not hard resource limits, so we don't do the recheck for these.

    The scope is specific to the limit type:
    * key_pairs scope is context.user_id
    * server_groups scope is context.project_id
    * server_group_members scope is server_group_uuid
    """
    if not CONF.quota.use_oslo_limit:
        return
    if entity_type not in COUNTABLE_ENTITIES:
        raise ValueError("entity_type")
    if int(delta) <= 0:
        raise ValueError("delta must be a non-zero positive integer")

    limit, count_function = COUNTABLE_ENTITIES[entity_type]
    count = count_function(context, entity_scope)

    if count + int(delta) > limit:
        raise exception.OverQuota(overs=[entity_type],
                                  quotas={entity_type: limit})


def check_count(entity_type, count):
    """Check if the values given are over the limit for that key.

    This is generally used for limiting the size of certain API requests
    that get stored in the database.
    """
    if not CONF.quota.use_oslo_limit:
        return
    if entity_type not in COUNT_LIMITS:
        raise ValueError("entity_type")

    limit = getattr(CONF.quota, COUNT_LIMITS[entity_type])
    if count > limit:
        raise exception.OverQuota(overs=[entity_type])

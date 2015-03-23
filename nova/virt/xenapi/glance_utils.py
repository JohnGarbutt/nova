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

from glanceclient import Client
from keystoneclient.auth.identity import v2 as identity
from keystoneclient import session as keystone_session
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

glance_opts = [
    cfg.StrOpt("glance_v2_url",
               default="http://localhost:9292",
               help='Address where glance service lives'),
    cfg.StrOpt("glance_auth_url",
               default="http://localhost:5000/v2.0",
               help='Address where auth service lives'),
    cfg.StrOpt("glance_username",
               help='Admin user to authenticate against the auth service'),
    cfg.StrOpt("glance_password",
               help='Auth password for the admin user'),
    cfg.StrOpt("glance_tenant_name",
               help='Tenant name for the admin user'),
]

CONF = cfg.CONF
CONF.register_opts(glance_opts, group='xenserver')


def list_images(context):
    LOG.debug("Fetching base images from glance.")
    # TODO(johngarbutt) there must be a better way to do this
    auth = identity.Password(
            auth_url=CONF.xenserver.glance_auth_url,
            username=CONF.xenserver.glance_username,
            password=CONF.xenserver.glance_password,
            tenant_name=CONF.xenserver.glance_tenant_name)
    session = keystone_session.Session(auth=auth)
    token = auth.get_token(session)
    glance = Client('2',
            endpoint=CONF.xenserver.glance_v2_url,
            token=token)
    return glance.images.list()

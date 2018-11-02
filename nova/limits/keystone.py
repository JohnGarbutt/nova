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

from oslo_limit import limit
from oslo_limit import exception as limit_exceptions
from oslo_log import log as logging
import os_resource_classes as orc

import nova.conf
from nova import exception
from nova import objects
from nova.scheduler.client import report
from nova.scheduler import utils
from nova import quota

LOG = logging.getLogger(__name__)
CONF = nova.conf.CONF

# Cache to avoid repopulating ksa state
PLACEMENT_CLIENT = None

_ENFORCER = None

def _get_placement_usages(context, project_id):
    global PLACEMENT_CLIENT
    if not PLACEMENT_CLIENT:
        PLACEMENT_CLIENT = report.SchedulerReportClient()
    resp = PLACEMENT_CLIENT._usages()
    if not resp:
        PLACEMENT_CLIENT._handle_usages_error_from_placement(resp, project_id)
        return {}
    data = resp.json()
    return data['usages']


def _count_dynamic_limits(context, project_id, resource_names):
    """Called by os.limits enforcer"""
    if not CONF.quota.use_oslo_limit:
        raise Exception("oslo_limit checking is disabled")

    count_servers = False
    resource_classes = []

    for resource in resource_names:
        if resource == "servers":
            count_servers = True
        elif resource.startswith("class:"):
            r_class = resource.lstrip("class:")
            if r_class in orc.STANDARDS or orc.is_custom(r_class):
                resource_names.append()
            else:
                raise Exception("Unknown resource class: %s" % resource)
        else:
            raise Exception("Unknown resource type: %s" % resource)

    counts = {}
    if count_servers:
        if not quota.is_qfd_populated():
            LOG.error('Must migrate all instance mappings before using '
                      'unified limits')
        mappings = objects.InstanceMappingList.get_counts(context, project_id)
        counts['servers'] = mappings['project']['instances']

    if len(resource_classes) > 0:
        usages = _get_placement_usages(context, project_id)
        for resource_class in resource_classes:
            # Placement doesn't know about classes with zero usage
            counts[resource_class] = usages.get(resource_class, 0)

    return counts


def _get_enforcer():
    # Cache enforcer so we keep creating new keystone auth contexts
    global _ENFORCER
    if _ENFORCER is None:
        _ENFORCER = limit.EndpointEnforcerContext(_count_dynamic_limits)
    return _ENFORCER


def check_limits(context, project_id, instance=None, flavor=None):
    """
    We check all registered limits in keystone vs current usage from placement

    If an instance is specified we check to see if any limits would be
    exceeded if placement included the resources needed for that instance.

    If a flavor and an instance are passed, it must be a resize. In this case
    we ensure if the additional resources needed for the new flavor are
    also given allocations in placement we will not exceed the limits
    specified in keystone.

    We raise an OverQuota exception if the limits are exceeded.
    """
    if not CONF.quota.use_oslo_limit:
        return

    # default to checking all limits
    deltas = None
    if instance is not None and flavor is not None:
        # doing a resize
        deltas = utils.resources_from_flavor(instance, flavor)
    elif instance is not None:
        # doing a build
        deltas = utils.resources_from_flavor(instance, instance.flavor)
    elif flavor is not None:
        raise ValueError("can't have flavor and no instance")

    enforcer = _get_enforcer()
    try:
        enforcer.check_all_limits(context, project_id, deltas)
    except limit_exceptions.ClaimExceedsLimit as e:
        # TODO(johngarbutt) need much better error translation here
        raise exception.OverQuota(e)

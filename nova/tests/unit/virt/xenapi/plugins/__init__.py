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

import imp
import os
import sys


def _get_plugin_path():
    current_path = os.path.realpath(__file__)
    rel_path = os.path.join(current_path,
            "../../../../../../../plugins/xenserver/xenapi/etc/xapi.d/plugins")
    plugin_path = os.path.abspath(rel_path)
    return plugin_path


def load_plugin(name):
    plugin_path = _get_plugin_path()

    if plugin_path not in sys.path:
        sys.path.append(plugin_path)

    # be sure not to create c files next to the plugins
    sys.dont_write_bytecode = True

    path = os.path.join(plugin_path, name)
    return imp.load_source(name, path)

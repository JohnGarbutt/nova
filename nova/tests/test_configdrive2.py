# Copyright 2012 Michael Still and Canonical Inc
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


import contextlib
import mock
import mox
import os
import tempfile

from nova import test

from nova.openstack.common import fileutils
from nova import utils
from nova.virt import configdrive


class ConfigDriveTestCase(test.NoDBTestCase):

    def test_create_configdrive_iso(self):
        imagefile = None

        try:
            self.mox.StubOutWithMock(utils, 'execute')

            utils.execute('genisoimage', '-o', mox.IgnoreArg(), '-ldots',
                          '-allow-lowercase', '-allow-multidot', '-l',
                          '-publisher', mox.IgnoreArg(), '-quiet', '-J', '-r',
                          '-V', 'config-2', mox.IgnoreArg(), attempts=1,
                          run_as_root=False).AndReturn(None)

            self.mox.ReplayAll()

            with configdrive.ConfigDriveBuilder() as c:
                c._add_file('this/is/a/path/hello', 'This is some content')
                (fd, imagefile) = tempfile.mkstemp(prefix='cd_iso_')
                os.close(fd)
                c._make_iso9660(imagefile)

            # Check cleanup
            self.assertFalse(os.path.exists(c.tempdir))

        finally:
            if imagefile:
                fileutils.delete_if_exists(imagefile)

    def test_create_configdrive_vfat(self):
        imagefile = None
        try:
            self.mox.StubOutWithMock(utils, 'mkfs')
            self.mox.StubOutWithMock(utils, 'execute')
            self.mox.StubOutWithMock(utils, 'trycmd')

            utils.mkfs('vfat', mox.IgnoreArg(),
                       label='config-2').AndReturn(None)
            utils.trycmd('mount', '-o', mox.IgnoreArg(), mox.IgnoreArg(),
                         mox.IgnoreArg(),
                         run_as_root=True).AndReturn((None, None))
            utils.execute('umount', mox.IgnoreArg(),
                          run_as_root=True).AndReturn(None)

            self.mox.ReplayAll()

            with configdrive.ConfigDriveBuilder() as c:
                c._add_file('this/is/a/path/hello', 'This is some content')
                (fd, imagefile) = tempfile.mkstemp(prefix='cd_vfat_')
                os.close(fd)
                c._make_vfat(imagefile)

            # Check cleanup
            self.assertFalse(os.path.exists(c.tempdir))

            # NOTE(mikal): we can't check for a VFAT output here because the
            # filesystem creation stuff has been mocked out because it
            # requires root permissions

        finally:
            if imagefile:
                fileutils.delete_if_exists(imagefile)

    @mock.patch.object(configdrive.ConfigDriveBuilder, 'make_drive')
    @mock.patch.object(utils, 'tempdir')
    @mock.patch.object(utils, "execute")
    @mock.patch.object(utils, "make_dev_path")
    def test_create_drive_at_path(self, mock_make_dev_path, mock_utils_execute,
                                  mock_utils_tmp_dir, mock_make_drive):
        device_path = "config/drive/path"
        mock_make_dev_path.return_value = 'device'
        mock_utils_tmp_dir.return_value = contextified('tmp/dir/')

        config_drive_builder = configdrive.ConfigDriveBuilder()
        config_drive_builder.create_drive(device_path)

        mock_make_drive.assert_called_with('tmp/dir/configdrive')
        mock_make_dev_path.assert_called_with(device_path)
        mock_utils_execute.assert_called_with('dd', 'if=tmp/dir/configdrive',
            'of=device', 'oflag=direct,sync', run_as_root=True)


@contextlib.contextmanager
def contextified(result):
    yield result

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

import os

import mock

from nova import test
from nova.tests.unit.virt.xenapi import plugins

swift = plugins.load_plugin("swift")


class TestSwift(test.NoDBTestCase):
    @mock.patch.object(swift.utils, "cleanup_staging_area")
    @mock.patch.object(swift, "_upload_tarball_with_retry")
    @mock.patch.object(swift, "_create_tar_file")
    @mock.patch.object(swift.utils, "prepare_staging_area")
    @mock.patch.object(swift.utils, "make_dir")
    @mock.patch.object(swift.utils, "make_staging_area")
    def test_upload_vhd(self, mock_make, mock_dir, mock_prepare, mock_tar,
                        mock_upload, mock_cleanup):
        mock_make.return_value = "path"
        mock_upload.return_value = ("etag", "tar_size")

        session = "session"
        vdi_uuids = "uuids"
        sr_path = "sr_path"
        image_id = 42
        params = {"max_size": 0}
        swift.upload_vhd(session, vdi_uuids, sr_path, image_id, **params)

        mock_make.assert_called_once_with(sr_path)
        mock_dir.assert_called_once_with("path_swift")
        mock_prepare.assert_called_once_with(sr_path, "path", vdi_uuids)
        mock_tar.assert_called_once_with("path", "path_swift/42")
        mock_upload.assert_called_once_with("path_swift/42", "42", **params)
        expected_cleanup_calls = [mock.call("path"), mock.call("path_swift")]
        mock_cleanup.assert_has_calls(expected_cleanup_calls)

    @mock.patch.object(swift, "_cleanup_after_failed_upload")
    @mock.patch.object(swift, "_upload_tarball")
    def test_upload_tarball_with_retry_error(self, mock_upload, mock_cleanup):

        def fake_upload(tar_path, obj_name, uploaded_chunks, **params):
            self.assertEqual(0, len(uploaded_chunks))
            uploaded_chunks.append("chunk1")
            raise test.TestingException()

        mock_upload.side_effect = fake_upload
        params = {"a": "b"}

        self.assertRaises(swift.PluginError,
                          swift._upload_tarball_with_retry,
                          "path", "obj", **params)

        self.assertEqual(3, mock_upload.call_count)
        self.assertEqual(3, mock_cleanup.call_count)
        mock_upload.assert_called_with("path", "obj", mock.ANY, **params)
        mock_cleanup.assert_called_with(["chunk1"], **params)

    @mock.patch.object(swift, "_cleanup_after_failed_upload")
    @mock.patch.object(swift, "_upload_tarball")
    def test_upload_tarball_with_retry_good(self, mock_upload, mock_cleanup):
        mock_upload.side_effect = [test.TestingException(), "result"]
        params = {"a": "b"}

        result = swift._upload_tarball_with_retry("path", "obj", **params)

        self.assertEqual("result", result)
        self.assertEqual(2, mock_upload.call_count)
        self.assertEqual(1, mock_cleanup.call_count)

    @mock.patch.object(swift, "_make_swift_connection")
    def test_cleanup_after_failed_upload(self, mock_conn):
        chunks = [("a", 1), ("b", 2)]
        params = {"a": "b"}
        swift_conn = mock.Mock()
        mock_conn.return_value = swift_conn

        swift._cleanup_after_failed_upload(chunks, **params)

        swift_conn.assert_has_calls([
                mock.call.delete_object("a", 1),
                mock.call.delete_object("b", 2)])

    @mock.patch.object(swift, "_upload_tarball_to_swift")
    @mock.patch.object(os.path, "getsize")
    @mock.patch.object(swift, "_create_container_if_missing")
    @mock.patch.object(swift, "_make_swift_connection")
    def test_upload_tarball_create_container(self, mock_conn, mock_create,
                                             mock_getsize, mock_upload):
        params = {
            "swift_store_container": "cont",
            "swift_store_create_container_on_put": True,
            "swift_store_large_object_size": 2,
            "swift_store_large_object_chunk_size": 1,
        }
        mock_conn.return_value = "conn"
        mock_getsize.return_value = 42
        mock_open = mock.mock_open()

        name = "%s.open" % swift.__name__
        with mock.patch(name, mock_open, create=True):
            swift._upload_tarball("path", "obj", [], **params)

        mock_conn.assert_called_once_with(**params)
        mock_create.assert_called_once_with("conn", "cont")
        mock_getsize.assert_called_once_with("path")
        mock_upload.assert_called_once_with("conn", "obj", mock.ANY, [],
                tar_size=42, large_object_size=2097152,
                large_object_chunk_size=1048576, container="cont",
                project_id=None)
        mock_open.assert_has_calls([
            mock.call("path", "r"),
            mock.call().__enter__(),
            mock.call().__exit__(None, None, None)])

    def test_create_container_if_missing(self):
        swift_conn = mock.Mock()
        error = swift.swift_client.ClientException("", http_status=404)
        swift_conn.head_container.side_effect = error

        swift._create_container_if_missing(swift_conn, "container")

        swift_conn.head_container.assert_called_once_with("container")
        swift_conn.put_container.assert_called_once_with("container")

    @mock.patch.object(swift.swift_client, "Connection")
    def test_make_swift_connection_single_tenant(self, mock_connection):
        params = {
            "swift_enable_snet": True,
            "full_auth_address": "url",
            "swift_store_auth_version": "1",
            "swift_store_user": "user",
            "swift_store_key": "key",
            "region_name": "lon",
        }
        mock_connection.return_value = "result"

        result = swift._make_swift_connection(**params)

        self.assertEqual("result", result)
        mock_connection.assert_called_once_with("url/", "user", "key",
                snet=True, auth_version="1",
                os_options={"region_name": "lon"})

    @mock.patch.object(swift.swift_client, "Connection")
    def test_make_swift_connection_multi_tenant(self, mock_connection):
        params = {
            "token": "token",
            "swift_store_user": "user",
            "storage_url": "url",
        }
        mock_connection.return_value = "result"

        result = swift._make_swift_connection(**params)

        self.assertEqual("result", result)
        mock_connection.assert_called_once_with(None, "user", None,
                preauthurl="url", preauthtoken="token", snet=False,
                auth_version="2")

    def test_upload_tarball_to_swift_put_raises(self):
        swift_conn = mock.Mock()
        swift_conn.put_object.side_effect = test.TestingException()
        undo_chunks = []

        self.assertRaises(test.TestingException,
                          swift._upload_tarball_to_swift,
                          swift_conn, "obj", "tar_file", undo_chunks)

        self.assertEqual([], undo_chunks)
        swift_conn.put_object.assert_called_once_with("images", "obj-00001",
                mock.ANY, content_length=None)

    @mock.patch.object(swift, "_get_reader")
    def test_upload_tarball_to_swift_delete_not_raises(self, mock_get):
        swift_conn = mock.Mock()
        error = swift.swift_client.ClientException("")
        swift_conn.delete_object.side_effect = error
        undo_chunks = []
        mock_reader = mock.Mock()
        bytes_read = mock.PropertyMock(side_effect=[10, 10, 0])
        type(mock_reader).bytes_read = bytes_read
        mock_get.return_value = mock_reader

        return_value = swift._upload_tarball_to_swift(swift_conn, "obj",
                "tar_file", undo_chunks, project_id="asdf")

        self.assertEqual("d41d8cd98f00b204e9800998ecf8427e", return_value)
        self.assertEqual([('images', 'obj-00001'), ('images', 'obj-00002')],
                         undo_chunks)
        swift_conn.delete_object.assert_called_once_with("images",
                                                         "obj-00003")
        expected_headers = {
            'x-tenant-id': 'asdf',
            'ETag': 'd41d8cd98f00b204e9800998ecf8427e',
            'X-Object-Manifest': 'images/obj'
        }
        swift_conn.put_object.assert_has_calls([
            mock.call("images", "obj-00001", mock.ANY, content_length=None),
            mock.call("images", "obj-00002", mock.ANY, content_length=None),
            mock.call("images", "obj-00003", mock.ANY, content_length=None),
            mock.call("images", "obj", None, headers=expected_headers),
            ])

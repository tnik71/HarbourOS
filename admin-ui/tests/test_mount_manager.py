"""Tests for the mount manager service."""

import os
import json
import tempfile

os.environ["HARBOUROS_DEV"] = "1"

from harbouros_admin.services import mount_manager


def test_sanitize_name():
    assert mount_manager._sanitize_name("My Movies!") == "my-movies-"
    assert mount_manager._sanitize_name("test_share") == "test_share"
    assert mount_manager._sanitize_name("  spaces  ") == "spaces"


def test_systemd_escape():
    assert mount_manager._systemd_escape("/media/nas/movies") == "media-nas-movies"
    assert mount_manager._systemd_escape("/a/b/c") == "a-b-c"


def test_generate_mount_unit_nfs():
    mount = {
        "name": "movies",
        "type": "nfs",
        "host": "192.168.1.100",
        "share": "/media/Movies",
    }
    content, unit_name = mount_manager._generate_mount_unit(mount)
    assert "Type=nfs" in content
    assert "192.168.1.100:/media/Movies" in content
    assert "nfsvers=4" in content
    assert "media-nas-movies" in unit_name


def test_generate_mount_unit_smb():
    mount = {
        "name": "docs",
        "type": "smb",
        "host": "192.168.1.200",
        "share": "Documents",
    }
    content, unit_name = mount_manager._generate_mount_unit(mount)
    assert "Type=cifs" in content
    assert "//192.168.1.200/Documents" in content
    assert "vers=3.0" in content


def test_generate_automount_unit():
    mount = {
        "name": "music",
        "type": "nfs",
        "host": "192.168.1.100",
        "share": "/media/Music",
    }
    content, unit_name = mount_manager._generate_automount_unit(mount)
    assert "[Automount]" in content
    assert "TimeoutIdleSec=600" in content


def test_add_and_list_mount():
    mount = mount_manager.add_mount(
        name="TestShare",
        mount_type="nfs",
        host="10.0.0.1",
        share="/vol/test",
    )
    assert mount["name"] == "TestShare"
    assert mount["type"] == "nfs"
    assert "id" in mount

    mounts = mount_manager.list_mounts()
    found = [m for m in mounts if m["id"] == mount["id"]]
    assert len(found) == 1
    assert found[0]["host"] == "10.0.0.1"


def test_remove_mount():
    mount = mount_manager.add_mount(
        name="ToRemove",
        mount_type="nfs",
        host="10.0.0.2",
        share="/vol/remove",
    )
    assert mount_manager.remove_mount(mount["id"]) is True
    assert mount_manager.remove_mount(mount["id"]) is False  # Already removed


def test_mount_unmount_share():
    mount = mount_manager.add_mount(
        name="MountTest",
        mount_type="nfs",
        host="10.0.0.3",
        share="/vol/mount",
    )
    success, msg = mount_manager.mount_share(mount["id"])
    assert success is True

    success, msg = mount_manager.unmount_share(mount["id"])
    assert success is True

    success, msg = mount_manager.mount_share("nonexistent")
    assert success is False


def test_test_connection():
    success, msg = mount_manager.test_connection("192.168.1.1", "nfs")
    assert success is True
    assert "dev mode" in msg

"""H5/L1 — cloud-init user-data generation and honest root_password_set flag."""

import base64
import json

import pytest
from httpx import AsyncClient

from app.providers.base import InstanceSpec
from app.providers.lxd import LXDProvider, build_cloud_init_user_data
from tests.security.helpers import create_vps, enroll_node, login


def _decode(ud: str) -> dict:
    return json.loads(base64.b64decode(ud))


def test_empty_when_nothing_requested() -> None:
    assert build_cloud_init_user_data(hostname=None, ssh_keys=None, root_password=None) == ""
    assert build_cloud_init_user_data(hostname="", ssh_keys=[], root_password=None) == ""


def test_ssh_keys_and_hostname_present() -> None:
    ud = build_cloud_init_user_data(
        hostname="web01.cvx.test",
        ssh_keys=["ssh-ed25519 AAAAC3Nza me@host"],
        root_password=None,
    )
    cfg = _decode(ud)
    assert cfg["hostname"] == "web01.cvx.test"
    assert cfg["ssh_authorized_keys"] == ["ssh-ed25519 AAAAC3Nza me@host"]
    assert "openssh-server" in cfg["packages"]


def test_root_password_applied_via_chpasswd() -> None:
    ud = build_cloud_init_user_data(
        hostname=None, ssh_keys=None, root_password="S3cure!pass",
    )
    cfg = _decode(ud)
    assert cfg["chpasswd"]["users"][0]["password"] == "S3cure!pass"


def test_hostile_inputs_are_json_encoded_not_interpreted() -> None:
    nasty_key = 'ssh-ed25519 AAAA "; rm -rf /; $(whoami)" x'
    nasty_pw = 'p\nass;$(reboot)`id`'
    ud = build_cloud_init_user_data(
        hostname="h; $(touch /tmp/pwn)",
        ssh_keys=[nasty_key],
        root_password=nasty_pw,
    )
    cfg = _decode(ud)
    # Values survive verbatim inside the JSON document — never shell-interpolated.
    assert cfg["ssh_authorized_keys"] == [nasty_key]
    assert cfg["chpasswd"]["users"][0]["password"] == nasty_pw
    assert cfg["hostname"] == "h; $(touch /tmp/pwn)"
    # And the whole thing round-trips as valid base64/JSON.
    assert isinstance(_decode(ud), dict)


def test_build_config_includes_user_data_only_when_relevant() -> None:
    # Nothing to configure -> config stays clean.
    spec = InstanceSpec(
        name="n1", image_source="img", cpu_limit=1, ram_mb=512, swap_mb=0,
        disk_gb=5, process_limit=100, hostname=None,
    )
    config = LXDProvider._build_config(spec)
    assert "user.user-data" not in config
    assert "user.cvx_hostname" not in config

    # Hostname alone is worth a cloud-init payload (applied in-guest).
    spec_h = InstanceSpec(
        name="n1h", image_source="img", cpu_limit=1, ram_mb=512, swap_mb=0,
        disk_gb=5, process_limit=100, hostname="host-only",
    )
    config_h = LXDProvider._build_config(spec_h)
    assert "user.user-data" in config_h
    assert _decode(config_h["user.user-data"])["hostname"] == "host-only"
    assert config_h["user.cvx_hostname"] == "host-only"

    # Keys ride along in the same payload.
    spec2 = InstanceSpec(
        name="n2", image_source="img", cpu_limit=1, ram_mb=512, swap_mb=0,
        disk_gb=5, process_limit=100, hostname="h",
        ssh_keys=["ssh-ed25519 AAAA a@b"],
    )
    config2 = LXDProvider._build_config(spec2)
    assert "user.user-data" in config2
    assert "ssh_authorized_keys" in _decode(config2["user.user-data"])


@pytest.mark.asyncio
async def test_create_vps_reports_root_password_set(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)

    resp = await create_vps(
        client, node["id"], str(ubuntu_image.id),
        password_auth_enabled=True, root_password="BootStrap!2026",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("root_password_set") is True

    # The provider received the password via the spec.
    spec = fake_provider.created[0]
    assert spec.root_password == "BootStrap!2026"

    # Without password auth, flag stays false.
    resp2 = await create_vps(
        client, node["id"], str(ubuntu_image.id), name="no-pw",
        hostname="nopw.cvx.test", password_auth_enabled=False,
    )
    assert resp2.json().get("root_password_set") is False


@pytest.mark.asyncio
async def test_ssh_keys_reach_the_provider(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test@example.com"
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id), ssh_keys=[key])
    assert resp.status_code == 200, resp.text
    spec = fake_provider.created[0]
    assert spec.ssh_keys == [key]

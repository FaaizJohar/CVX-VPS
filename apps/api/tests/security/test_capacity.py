"""H7 — disk capacity is enforced against node storage."""

import uuid

import pytest

from tests.security.helpers import create_vps, enroll_node, login

pytestmark = pytest.mark.asyncio


async def test_disk_overallocation_rejected(
    client, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    from app.models import Node

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    row = await db_session.get(Node, uuid.UUID(node["id"]))
    row.storage_total_gb = 50.0
    await db_session.commit()

    # First VPS: 30 GB — fits.
    resp = await create_vps(client, node["id"], str(ubuntu_image.id),
                            name="disk-a", disk_gb=30)
    assert resp.status_code == 201, resp.text

    # Second: 30 GB more would total 60 > 50 — rejected.
    resp = await create_vps(client, node["id"], str(ubuntu_image.id),
                            name="disk-b", disk_gb=30)
    assert resp.status_code == 422
    assert "storage" in resp.json()["error"]["message"].lower()

    # Exactly at the limit passes.
    resp = await create_vps(client, node["id"], str(ubuntu_image.id),
                            name="disk-c", disk_gb=20)
    assert resp.status_code == 201, resp.text


async def test_deleted_vps_frees_disk_capacity(
    client, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    from app.models import Node

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    row = await db_session.get(Node, uuid.UUID(node["id"]))
    row.storage_total_gb = 30.0
    await db_session.commit()

    resp = await create_vps(client, node["id"], str(ubuntu_image.id), disk_gb=25)
    vps_id = resp.json()["id"]
    assert resp.status_code == 201

    # No room now.
    resp = await create_vps(client, node["id"], str(ubuntu_image.id),
                            name="disk-d", disk_gb=10)
    assert resp.status_code == 422

    # Delete frees space.
    assert (await client.delete(f"/api/v1/vps/{vps_id}")).status_code == 200
    resp = await create_vps(client, node["id"], str(ubuntu_image.id),
                            name="disk-e", disk_gb=10)
    assert resp.status_code == 201, resp.text


async def test_unlimited_when_storage_unknown(
    client, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    from app.models import Node

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    row = await db_session.get(Node, uuid.UUID(node["id"]))
    row.storage_total_gb = None
    await db_session.commit()
    resp = await create_vps(client, node["id"], str(ubuntu_image.id), disk_gb=4096)
    assert resp.status_code == 201, resp.text


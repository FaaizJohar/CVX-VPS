"""LXDClient error mapping — LXD API failures become typed LXDError."""

import asyncio

import pytest

from cvx_agent.lxd import LXDError, LXDClient
from tests_agent.conftest import StubResponse


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_lxd_error_carries_status_and_message(make_lxd):
    client, _ = make_lxd(
        StubResponse(403, {"type": "error", "error": "Permission denied"})
    )
    with pytest.raises(LXDError) as exc_info:
        _run(client.delete_snapshot("c1", "s1"))
    assert exc_info.value.status == 403
    assert "Permission denied" in exc_info.value.message


def test_get_instance_returns_none_on_404(make_lxd):
    client, _ = make_lxd(
        StubResponse(404, {"type": "error", "error": "Instance not found"})
    )
    assert _run(client.get_instance("missing")) is None


def test_get_instance_reraises_other_errors(make_lxd):
    client, _ = make_lxd(
        StubResponse(500, {"type": "error", "error": "storage pool degraded"})
    )
    with pytest.raises(LXDError) as exc_info:
        _run(client.get_instance("c1"))
    assert exc_info.value.status == 500


def test_non_json_response_raises_lxd_error(make_lxd):
    client, _ = make_lxd(StubResponse(502, ValueError("no json")))
    with pytest.raises(LXDError) as exc_info:
        _run(client.server_info())
    assert exc_info.value.status == 502
    assert "non-JSON" in exc_info.value.message


def test_success_response_passes_through(make_lxd):
    client, stub = make_lxd(
        StubResponse(
            200,
            {
                "type": "sync",
                "metadata": {"environment": {"server_version": "5.21"}},
            },
        )
    )
    info = _run(client.server_info())
    assert info["lxd_version"] == "5.21"
    assert stub.calls[0][0] == "GET"
    assert stub.calls[0][1] == "/1.0"


def test_error_type_on_2xx_still_raises(make_lxd):
    # LXD reports operation failures with type=error even over 200.
    client, _ = make_lxd(
        StubResponse(200, {"type": "error", "error": "operation failed"})
    )
    with pytest.raises(LXDError) as exc_info:
        _run(client.start_instance("c1"))
    assert exc_info.value.status == 500


def test_delete_instance_is_snapshot_safe():
    """delete_instance removes snapshots first and tolerates their failure."""
    calls: list[tuple] = []

    class SeqClient:
        async def list_snapshots(self, name):
            calls.append(("list", name))
            return [{"name": "s1"}, {"name": "s2"}]

        async def delete_snapshot(self, name, snap):
            calls.append(("del-snap", snap))
            if snap == "s1":
                raise RuntimeError("boom")

        async def stop_instance(self, name, timeout=30, force=False):
            calls.append(("stop", name))

        async def _request(self, method, path, json_body=None, wait=True):
            calls.append((method, path))

    client = object.__new__(LXDClient)
    seq = SeqClient()
    client.list_snapshots = seq.list_snapshots  # type: ignore[method-assign]
    client.delete_snapshot = seq.delete_snapshot  # type: ignore[method-assign]
    client.stop_instance = seq.stop_instance  # type: ignore[method-assign]
    client._request = seq._request  # type: ignore[method-assign]

    _run(client.delete_instance("c1"))
    kinds = [c[0] for c in calls]
    assert kinds[0] == "list"
    assert ("del-snap", "s1") in calls and ("del-snap", "s2") in calls
    assert ("DELETE", "/1.0/instances/c1") in calls
    # Instance delete happens after snapshot attempts.
    assert kinds.index("DELETE") > kinds.index("del-snap")

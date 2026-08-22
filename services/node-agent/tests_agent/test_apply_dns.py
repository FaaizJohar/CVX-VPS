"""apply_dns — defense-in-depth filtering before any command construction."""

import asyncio

from cvx_agent.lxd import LXDClient


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _client_with_exec(recorder: list):
    client = object.__new__(LXDClient)

    async def fake_exec(name, command):
        recorder.append((name, command))
        return 0, ""

    client.exec_command = fake_exec  # type: ignore[method-assign]
    return client


def test_valid_ips_reach_exec():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(client.apply_dns("c1", ["1.1.1.1", "8.8.8.8"]))
    assert len(recorded) == 1
    name, command = recorded[0]
    assert name == "c1"
    script = command[-1]
    assert "DNS=1.1.1.1 8.8.8.8" in script


def test_invalid_entries_are_dropped_not_interpolated():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(
        client.apply_dns(
            "c1",
            ["1.1.1.1", "not-an-ip", "$(reboot)", "`id`", "; rm -rf /", "8.8.4.4"],
        )
    )
    _, command = recorded[0]
    script = command[-1]
    assert "DNS=1.1.1.1 8.8.4.4" in script
    for hostile in ("reboot", "rm -rf", "`id`"):
        assert hostile not in script


def test_all_invalid_means_no_exec():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(client.apply_dns("c1", ["nope", "$(whoami)", ""]))
    assert recorded == []


def test_empty_list_is_noop():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(client.apply_dns("c1", []))
    assert recorded == []


def test_ipv6_entries_accepted():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(client.apply_dns("c1", ["2606:4700:4700::1111"]))
    _, command = recorded[0]
    assert "DNS=2606:4700:4700::1111" in command[-1]


def test_non_string_entries_survive_via_str_conversion():
    recorded: list = []
    client = _client_with_exec(recorded)
    _run(client.apply_dns("c1", [134744074]))  # int form of 80.80.80.74... invalid dotted? str() then parsed
    # 134744074 parses as an integer address — accepted and normalized.
    assert len(recorded) == 1

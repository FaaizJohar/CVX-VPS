"""Instance/snapshot name validation — the agent's injection firewall."""

import pytest
from fastapi import HTTPException

from cvx_agent.server import validate_instance_name, validate_snapshot_name


class TestInstanceNames:
    @pytest.mark.parametrize("name", ["web-01", "Web_1", "a", "a" * 64, "cvx-abc123"])
    def test_valid_names_pass(self, name):
        assert validate_instance_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "-leading-dash",
            ".leading-dot",
            "_leading-underscore",
            "has space",
            "slash/name",
            "../etc/passwd",
            "..",
            "semi;colon",
            "back\\slash",
            "dollar$sign",
            "back`tick",
            "pipe|x",
            "new\nline",
            "tab\there",
            "quote'double\"quoted",
            "$(whoami)",
            "${VAR}",
            "colon:inside",
            "a" * 65,
            "üñíçø∂é",
            None,
            123,
            [],
        ],
    )
    def test_hostile_names_rejected(self, name):
        with pytest.raises(HTTPException) as exc:
            validate_instance_name(name)
        assert exc.value.status_code == 422


class TestSnapshotNames:
    @pytest.mark.parametrize(
        "name", ["snap1", "pre-release_2.3", "b" * 128, "2026-08-21T1000"]
    )
    def test_valid_snapshot_names_pass(self, name):
        assert validate_snapshot_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            ".hidden",
            "-dash",
            "../../escape",
            "a/b",
            "c" * 129,
            "sp ace",
            None,
            42,
        ],
    )
    def test_hostile_snapshot_names_rejected(self, name):
        with pytest.raises(HTTPException) as exc:
            validate_snapshot_name(name)
        assert exc.value.status_code == 422

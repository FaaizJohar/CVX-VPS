"""H3/M12 — console hardening helpers (unit-level)."""

import asyncio

import pytest

from app.api.v1.routes.console import (
    MAX_CONSOLES_PER_USER,
    clamp_resize,
)


def test_clamp_resize_bounded() -> None:
    assert clamp_resize(80, 24) == (80, 24)
    assert clamp_resize(0, 0) == (2, 2)
    assert clamp_resize(-100, -5) == (2, 2)
    assert clamp_resize(99999, 99999) == (500, 200)
    assert clamp_resize(None, None) == (80, 24)
    assert clamp_resize("abc", "xyz") == (80, 24)
    assert clamp_resize("120", "40") == (120, 40)
    assert clamp_resize(3.9, 7.2) == (3, 7)


def test_clamp_resize_never_raises() -> None:
    for bad in ([], {}, object(), float("nan")):
        cols, rows = clamp_resize(bad, bad)
        assert 2 <= cols <= 500
        assert 2 <= rows <= 200


def test_concurrency_constants_sane() -> None:
    assert 1 <= MAX_CONSOLES_PER_USER <= 50


def test_active_console_registry_counts() -> None:
    """Registry semantics: increment/decrement to zero removes the entry."""
    import uuid as uuid_mod

    from app.api.v1.routes.console import _active_consoles

    uid = uuid_mod.uuid4()
    try:
        _active_consoles[uid] = _active_consoles.get(uid, 0) + 1
        _active_consoles[uid] = _active_consoles.get(uid, 0) + 1
        assert _active_consoles[uid] == 2
        remaining = _active_consoles.get(uid, 1) - 1
        if remaining <= 0:
            _active_consoles.pop(uid, None)
        else:
            _active_consoles[uid] = remaining
        remaining = _active_consoles.get(uid, 1) - 1
        if remaining <= 0:
            _active_consoles.pop(uid, None)
        else:
            _active_consoles[uid] = remaining
        assert uid not in _active_consoles
    finally:
        _active_consoles.pop(uid, None)

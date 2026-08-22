import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class StubResponse:
    def __init__(self, status_code: int, data: object) -> None:
        self.status_code = status_code
        self._data = data

    def json(self):
        if isinstance(self._data, ValueError):
            raise self._data
        return self._data


class StubHTTP:
    """Replaces httpx.AsyncClient inside LXDClient for unit tests."""

    def __init__(self, response: StubResponse) -> None:
        self.response = response
        self.calls: list[tuple] = []

    async def request(self, method, path, json=None, params=None):
        self.calls.append((method, path, json, params))
        return self.response


@pytest.fixture
def make_lxd():
    """Build an LXDClient whose HTTP layer is a stub returning `response`."""

    def _make(response: StubResponse):
        from cvx_agent.lxd import LXDClient

        client = LXDClient(socket_path="/tmp/cvx-test.sock")
        stub = StubHTTP(response)
        client._client = stub  # type: ignore[assignment]
        return client, stub

    return _make

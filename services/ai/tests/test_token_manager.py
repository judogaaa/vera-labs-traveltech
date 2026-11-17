from __future__ import annotations

import threading
import time

from services.ai.gigachat_token_manager import GigaChatTokenManager
from services.ai.gigachat_types import GigaChatError


class FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def post(self, *args, **kwargs):
        with self.lock:
            self.calls += 1
            # Simulate network latency so parallel callers contend
            time.sleep(0.05)
            return FakeResp(200, {"access_token": f"tok-{self.calls}", "expires_in": 1800})


def test_single_flight_refresh():
    http = FakeClient()
    tm = GigaChatTokenManager(client=http, auth_key="dGVzdDp0ZXN0", scope="GIGACHAT_API_PERS")
    tokens = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        tokens.append(tm.get_token())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Single-flight: one refresh serves all waiters
    assert http.calls == 1
    assert len(set(tokens)) == 1

def test_missing_key():
    tm = GigaChatTokenManager(client=FakeClient(), auth_key="")
    try:
        tm.get_token()
        assert False, "expected error"
    except GigaChatError as exc:
        assert exc.code == "auth_missing"

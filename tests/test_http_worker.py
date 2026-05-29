# tests/test_http_worker.py
"""HttpWorker — generic HTTP fetch with retry/backoff for InternetPanel.

Tests run synchronously via `worker.run()` (not `start()`) so signal
slots fire inline and assertions stay simple — same pattern the
flash-integration tests use. `requests.get` is monkeypatched per-test.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _qapp():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    created = False
    if app is None:
        app = QCoreApplication([os.environ.get("PYTEST_CURRENT_TEST", "test")])
        created = True
    yield
    if created:
        app.quit()


class _FakeResponse:
    def __init__(self, *, content=b"", json_data=None, headers=None, status=200):
        self.content = content
        self._json = json_data
        self.headers = headers or {}
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=8192):
        yield self.content


def _captured(slot_holder, key):
    """Connect-helper: stash the emitted value into slot_holder[key]."""

    def _slot(value):
        slot_holder[key] = value

    return _slot


def test_ok_path_with_parser(monkeypatch):
    from internet_panel import HttpWorker

    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout=None: _FakeResponse(json_data={"devices": [{"id": 1}]}),
    )
    captured = {}
    w = HttpWorker(
        "https://example/api/devices",
        parser=lambda r: r.json().get("devices", []),
        retries=0,
    )
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.run()

    assert captured.get("ok") == [{"id": 1}]
    assert "fail" not in captured


def test_ok_path_raw_bytes(monkeypatch):
    from internet_panel import HttpWorker

    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout=None: _FakeResponse(content=b"\x89PNG..."),
    )
    captured = {}
    w = HttpWorker("https://example/img.png", retries=0)
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.run()

    assert captured.get("ok") == b"\x89PNG..."


def test_stream_to_temp_bin(monkeypatch, tmp_path):
    from pathlib import Path

    from internet_panel import HttpWorker

    payload = b"firmware-bytes" * 100

    def fake_get(url, timeout=None, stream=False):
        # `stream=True` path must produce iter_content; both return paths
        # share the FakeResponse class for simplicity.
        return _FakeResponse(
            content=payload,
            headers={"Content-Length": str(len(payload))},
        )

    monkeypatch.setattr("requests.get", fake_get)
    captured = {}
    progress_log = []
    w = HttpWorker(
        "https://example/fw.bin", stream_to_temp_bin=True, retries=0
    )
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.progress.connect(progress_log.append)
    w.run()

    out_path = captured.get("ok")
    assert out_path and Path(out_path).exists()
    assert Path(out_path).read_bytes() == payload
    assert 100 in progress_log


@pytest.mark.parametrize(
    "headers",
    [
        {},                              # missing Content-Length
        {"Content-Length": "0"},         # zero
        {"Content-Length": "not-a-num"},  # malformed — #81: must not crash
    ],
    ids=["missing", "zero", "malformed"],
)
def test_stream_tolerates_bad_content_length(monkeypatch, headers):
    """#81: a missing/zero/non-numeric Content-Length means 'unknown size' —
    the download streams to completion without crashing the worker thread.
    The malformed case previously raised ValueError, which escapes
    _HTTP_FAILURES and would kill the thread with no fail signal."""
    from pathlib import Path

    from internet_panel import HttpWorker

    payload = b"firmware-bytes" * 10

    def fake_get(url, timeout=None, stream=False):
        return _FakeResponse(content=payload, headers=headers)

    monkeypatch.setattr("requests.get", fake_get)
    captured = {}
    progress_log = []
    w = HttpWorker("https://example/fw.bin", stream_to_temp_bin=True, retries=0)
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.progress.connect(progress_log.append)
    w.run()

    out_path = captured.get("ok")
    assert out_path and Path(out_path).exists()
    assert Path(out_path).read_bytes() == payload
    assert "fail" not in captured
    # Unknown size -> no intermediate %, but the final 100 still fires.
    assert progress_log[-1] == 100


def test_retry_then_success(monkeypatch):
    from internet_panel import HttpWorker

    calls = {"n": 0}

    def fake_get(url, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            import requests

            raise requests.exceptions.ConnectionError("boom")
        return _FakeResponse(content=b"ok")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("internet_panel.time.sleep", lambda _s: None)

    captured = {}
    log_messages = []
    w = HttpWorker("https://example", retries=3, backoff=0.01)
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.log.connect(log_messages.append)
    w.run()

    assert captured.get("ok") == b"ok"
    assert "fail" not in captured
    assert calls["n"] == 3
    # Two retry attempts logged before the third succeeded.
    assert sum(1 for m in log_messages if "retrying" in m) == 2


def test_retry_exhausted_then_fail(monkeypatch):
    from internet_panel import HttpWorker

    def fake_get(url, timeout=None):
        import requests

        raise requests.exceptions.ConnectionError("permanent failure")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("internet_panel.time.sleep", lambda _s: None)

    captured = {}
    log_messages = []
    w = HttpWorker("https://example", retries=2, backoff=0.01)
    w.ok.connect(_captured(captured, "ok"))
    w.fail.connect(_captured(captured, "fail"))
    w.log.connect(log_messages.append)
    w.run()

    assert "ok" not in captured
    assert "permanent failure" in captured.get("fail", "")
    # 1 initial attempt + 2 retries = 3 total; 2 retry log lines.
    assert sum(1 for m in log_messages if "retrying" in m) == 2


def test_default_retry_count_is_two():
    """ARC-1 + #37 acceptance: retries default to 2 (so 3 total attempts).
    Pin in code so a future tweak is deliberate."""
    from internet_panel import HttpWorker

    w = HttpWorker("https://example")
    assert w.retries == 2


def test_default_timeout_is_15s():
    """Default timeout matches the legacy LoadDevicesWorker / LoadFirmwaresWorker
    value — not an arbitrary number, those were the load-list endpoints."""
    from internet_panel import HttpWorker

    w = HttpWorker("https://example")
    assert w.timeout == 15.0

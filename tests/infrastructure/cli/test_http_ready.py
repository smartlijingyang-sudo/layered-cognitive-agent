"""http_ready must not treat 4xx/5xx as healthy (kernel /health 误报回归)。

health_body_ok is the post-0213 stricter variant: HTTP 200 + body
``status == "ok"``. A 200 with body ``status == "degraded"`` must NOT
report the kernel as ready.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lca.infrastructure.cli.service.service import health_body_ok, http_ready


def _curl_result(*, code: str, returncode: int = 0) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = code
    return result


def test_http_ready_true_on_2xx() -> None:
    with patch("subprocess.run", return_value=_curl_result(code="200")) as run:
        assert http_ready("http://127.0.0.1:8765/health") is True
    assert "-w" in run.call_args.args[0]


def test_http_ready_true_on_3xx() -> None:
    with patch("subprocess.run", return_value=_curl_result(code="302")):
        assert http_ready("http://127.0.0.1:3010/") is True


def test_http_ready_false_on_5xx() -> None:
    with patch("subprocess.run", return_value=_curl_result(code="500")):
        assert http_ready("http://127.0.0.1:8765/health") is False


def test_http_ready_false_on_4xx() -> None:
    with patch("subprocess.run", return_value=_curl_result(code="404")):
        assert http_ready("http://127.0.0.1:8765/missing") is False


def test_http_ready_false_on_curl_failure() -> None:
    with patch("subprocess.run", return_value=_curl_result(code="000", returncode=7)):
        assert http_ready("http://127.0.0.1:9/health") is False


# ── health_body_ok (post-0213 PR-2) ────────────────────────────────


def _curl_body_result(*, body: str, code: str, returncode: int = 0) -> MagicMock:
    """Build a curl stdout with ``body\\n<code>`` shape (matches curl -w '\\n%{http_code}')."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = f"{body}\n{code}"
    return result


def test_health_body_ok_true_on_200_ok() -> None:
    """HTTP 200 + body status=ok → True."""
    body = '{"status": "ok", "runs": {}, "live": {}}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="200")):
        assert health_body_ok("http://127.0.0.1:8765/health") is True


def test_health_body_ok_false_on_200_degraded() -> None:
    """HTTP 200 but body status=degraded → False (kernel alive but degraded)."""
    body = '{"status": "degraded", "event_bus": {"dropped_total": 5}}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="200")):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_on_200_loading() -> None:
    """HTTP 200 but body status=loading → False (boot in progress)."""
    body = '{"status": "loading"}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="200")):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_on_5xx() -> None:
    """HTTP 5xx → False (kernel failure surface)."""
    body = '{"status": "ok"}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="500")):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_on_3xx() -> None:
    """HTTP 3xx → False (we never follow redirects for /health probes)."""
    body = '{"status": "ok"}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="302")):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_on_malformed_body() -> None:
    """HTTP 200 but body is not JSON → False."""
    with patch(
        "subprocess.run",
        return_value=_curl_body_result(body="not json at all", code="200"),
    ):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_on_curl_failure() -> None:
    """curl exit non-zero → False."""
    with patch(
        "subprocess.run",
        return_value=_curl_body_result(body="", code="000", returncode=7),
    ):
        assert health_body_ok("http://127.0.0.1:8765/health") is False


def test_health_body_ok_false_when_status_field_missing() -> None:
    """HTTP 200 + JSON without ``status`` field → False."""
    body = '{"runs": {}, "live": {}}'
    with patch("subprocess.run", return_value=_curl_body_result(body=body, code="200")):
        assert health_body_ok("http://127.0.0.1:8765/health") is False

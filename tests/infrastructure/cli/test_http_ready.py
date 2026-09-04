"""http_ready must not treat 4xx/5xx as healthy (kernel /health 误报回归)。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lca.infrastructure.cli.service import http_ready


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

"""用户身份解析（ADR-0252 D4）—— ``handlers.auth.user``。

覆盖 dev_mode 放行、非 dev 模式 401、bearer/头两种 token 形态。
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.plugins.transport.webserver.handlers.auth.user import (
    DEFAULT_DEV_USER_ID,
    DEFAULT_EXPECTED_TOKEN,
    user_id_from_request,
)


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/assistants",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
        "app": type("App", (), {"state": type("State", (), {})()})(),
    }
    return Request(scope)


def test_dev_mode_missing_user_falls_back_to_local_dev() -> None:
    request = _make_request({})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=True
    )
    assert error is None
    assert user_id == DEFAULT_DEV_USER_ID


def test_dev_mode_accepts_wrong_token() -> None:
    request = _make_request({"authorization": "Bearer wrong", "x-lca-user-id": "alice"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=True
    )
    assert error is None
    assert user_id == "alice"


def test_non_dev_mode_requires_token() -> None:
    request = _make_request({"x-lca-user-id": "alice"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=False
    )
    assert user_id is None
    assert isinstance(error, JSONResponse)
    assert error.status_code == 401


def test_non_dev_mode_rejects_wrong_token() -> None:
    request = _make_request({"authorization": "Bearer wrong", "x-lca-user-id": "alice"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=False
    )
    assert user_id is None
    assert isinstance(error, JSONResponse)
    assert error.status_code == 401


def test_non_dev_mode_requires_user_id() -> None:
    request = _make_request({"authorization": "Bearer lca-local"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=False
    )
    assert user_id is None
    assert isinstance(error, JSONResponse)
    assert error.status_code == 401


def test_non_dev_mode_accepts_valid_token_and_user() -> None:
    request = _make_request({"authorization": "Bearer lca-local", "x-lca-user-id": "alice"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=False
    )
    assert error is None
    assert user_id == "alice"


def test_x_lca_token_header_accepted() -> None:
    request = _make_request({"x-lca-token": "lca-local", "x-lca-user-id": "alice"})
    user_id, error = user_id_from_request(
        request, expected_token=DEFAULT_EXPECTED_TOKEN, dev_mode=False
    )
    assert error is None
    assert user_id == "alice"

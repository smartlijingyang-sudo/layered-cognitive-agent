"""degradation 四分类 + 不杀 run 不变量（直接用例）。

``lca/cognition/body/degradation/__init__.py`` 的 ``classify_error()``/``degrade()``
在 tests/ 全仓此前 0 直接用例（sweep 里相关用例全为间接覆盖）。
本文件钉住四分类边界（status_code/marker 双通道）、优先级交叉，
以及 ``degrade()`` 的返回不变量：单工具失败永不抛错杀 run。
"""

import pytest

from lca.cognition.body.degradation import (
    DegradationKind,
    DegradedResult,
    classify_error,
    degrade,
)


class TestClassifyPermission:
    @pytest.mark.parametrize("code", [401, 403])
    def test_status_code_channel(self, code):
        assert classify_error("anything at all", status_code=code) is DegradationKind.PERMISSION

    @pytest.mark.parametrize(
        "message",
        [
            "permission denied for tool",
            "Unauthorized: invalid credentials",
            "Forbidden by policy",
            "insufficientPermissions on resource",
            "bad api_key value",
            "missing apikey header",
            "broken auth_config entry",
            "access denied to table",
        ],
    )
    def test_marker_channel(self, message):
        assert classify_error(message) is DegradationKind.PERMISSION

    def test_marker_matching_is_case_insensitive(self):
        assert classify_error("PERMISSION DENIED") is DegradationKind.PERMISSION


class TestClassifyNotFound:
    def test_status_code_channel(self):
        assert classify_error("anything at all", status_code=404) is DegradationKind.NOT_FOUND

    @pytest.mark.parametrize(
        "message",
        [
            "resource not found",
            "404 page gone",
            "record does not exist",
            "no such tool registered",
        ],
    )
    def test_marker_channel(self, message):
        assert classify_error(message) is DegradationKind.NOT_FOUND


class TestClassifyTransient:
    @pytest.mark.parametrize(
        "message",
        [
            "request timeout after 30s",
            "timed out waiting for upstream",
            "connection reset by peer",
            "network unreachable",
            "temporary failure in name resolution",
            "please try again later",
            "rate limit exceeded",
            "HTTP 429 too many requests",
            "503 service unavailable",
            "502 bad gateway",
        ],
    )
    def test_marker_channel(self, message):
        assert classify_error(message) is DegradationKind.TRANSIENT


class TestClassifyDefault:
    def test_unknown_error_is_deterministic(self):
        assert classify_error("some weird internal bug") is DegradationKind.DETERMINISTIC

    def test_empty_message_is_deterministic(self):
        assert classify_error("") is DegradationKind.DETERMINISTIC


class TestClassifyPriority:
    def test_permission_wins_over_not_found(self):
        assert classify_error("404 permission denied on secret") is DegradationKind.PERMISSION

    def test_not_found_wins_over_transient(self):
        assert classify_error("record not found, request timeout") is DegradationKind.NOT_FOUND

    def test_permission_status_code_wins_over_everything(self):
        assert classify_error("404 not found", status_code=403) is DegradationKind.PERMISSION


class TestDegradeInvariants:
    def test_permission_result_shape(self):
        r = degrade("search", "403 Forbidden", status_code=403, invocation_id="inv-1")
        assert isinstance(r, DegradedResult)
        assert r.kind is DegradationKind.PERMISSION
        assert r.ok is False
        # 用户可修复：给出指引，且明确不是 terminal
        assert r.user_guidance is not None and "search" in r.user_guidance
        assert r.terminal_hint is False
        assert r.original_error == "403 Forbidden"
        assert r.extra == {"invocation_id": "inv-1", "status_code": 403}

    def test_transient_result_shape(self):
        r = degrade("search", "timeout", invocation_id="inv-2")
        assert r.kind is DegradationKind.TRANSIENT
        assert r.ok is False
        assert r.user_guidance is not None
        assert r.terminal_hint is False
        assert r.extra == {"invocation_id": "inv-2"}

    def test_not_found_result_shape(self):
        r = degrade("search", "404 gone", invocation_id="inv-3")
        assert r.kind is DegradationKind.NOT_FOUND
        assert r.ok is False
        # agent 自行决定：无指引、无 terminal 判据
        assert r.user_guidance is None
        assert r.terminal_hint is None
        assert r.extra == {"invocation_id": "inv-3"}

    def test_deterministic_result_shape(self):
        r = degrade("search", "internal logic bug", invocation_id="inv-4")
        assert r.kind is DegradationKind.DETERMINISTIC
        assert r.ok is False
        assert r.user_guidance is None
        assert r.terminal_hint is None
        assert r.extra == {"invocation_id": "inv-4"}

    def test_result_is_frozen(self):
        r = degrade("search", "timeout")
        with pytest.raises(AttributeError):
            r.kind = DegradationKind.PERMISSION  # type: ignore[misc]

    @pytest.mark.parametrize(
        "message,status",
        [
            ("403 Forbidden", 403),
            ("permission denied", None),
            ("404 gone", 404),
            ("not found", None),
            ("timeout", None),
            ("connection reset", None),
            ("some weird internal bug", None),
            ("", None),
        ],
    )
    def test_degrade_never_raises(self, message, status):
        # 单工具失败永不直接杀 run：degrade 永远返回结构化结果而不是抛错
        r = degrade("search", message, status_code=status)
        assert isinstance(r, DegradedResult)
        assert r.ok is False
        assert r.summary and "search" in r.summary

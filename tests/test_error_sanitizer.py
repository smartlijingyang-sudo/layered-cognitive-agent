"""Tests for error sanitizer."""

from gateway.timeline.error_sanitizer import (
    PassthroughSanitizer,
    RegexSanitizer,
    SanitizerChain,
    sanitize_error,
)


class TestSanitizeError:
    """Error sanitizer tests."""

    def test_content_filter_dashscope(self) -> None:
        """DashScope DataInspectionFailed 应被脱敏。"""
        error = "<400> InternalError.Algo.DataInspectionFailed: Output data may contain inappropriate content."
        result = sanitize_error(error)
        assert "DataInspectionFailed" not in result
        assert "内容安全" in result

    def test_api_http_error(self) -> None:
        """HTTP 状态码错误应被脱敏。"""
        error = "<500> APIError: internal server error"
        result = sanitize_error(error)
        assert "APIError" not in result
        assert "模型服务" in result

    def test_network_timeout(self) -> None:
        """超时错误应被脱敏。"""
        error = "ConnectionError: timeout after 30s"
        result = sanitize_error(error)
        assert "timeout" not in result.lower()
        assert "网络" in result

    def test_unknown_error_passthrough(self) -> None:
        """未知错误原样返回。"""
        error = "some custom error message"
        result = sanitize_error(error)
        assert result == error

    def test_empty_error(self) -> None:
        """空字符串返回空。"""
        assert sanitize_error("") == ""


class TestRegexSanitizer:
    """RegexSanitizer unit tests."""

    def test_match(self) -> None:
        sanitizer = RegexSanitizer(pattern=r"foo", replacement="bar")
        result = sanitizer.sanitize("hello foo world")
        assert result.matched is True
        assert result.message == "bar"

    def test_no_match(self) -> None:
        sanitizer = RegexSanitizer(pattern=r"foo", replacement="bar")
        result = sanitizer.sanitize("hello world")
        assert result.matched is False


class TestSanitizerChain:
    """SanitizerChain unit tests."""

    def test_first_match_wins(self) -> None:
        chain = SanitizerChain(
            [
                RegexSanitizer(pattern=r"foo", replacement="first"),
                RegexSanitizer(pattern=r"foo", replacement="second"),
            ]
        )
        assert chain.sanitize("foo") == "first"

    def test_fallback_to_passthrough(self) -> None:
        chain = SanitizerChain(
            [
                RegexSanitizer(pattern=r"nomatch", replacement="x"),
                PassthroughSanitizer(),
            ]
        )
        assert chain.sanitize("original") == "original"

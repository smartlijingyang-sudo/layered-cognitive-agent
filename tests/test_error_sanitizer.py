"""Three-regex error sanitizer — no protocol chain."""

from gateway.runs.execute import sanitize_error


class TestSanitizeError:
    def test_content_filter_dashscope(self) -> None:
        error = "<400> InternalError.Algo.DataInspectionFailed: Output data may contain inappropriate content."
        result = sanitize_error(error)
        assert "DataInspectionFailed" not in result
        assert "内容安全" in result

    def test_api_http_error(self) -> None:
        error = "<500> APIError: internal server error"
        result = sanitize_error(error)
        assert "APIError" not in result
        assert "模型服务" in result

    def test_network_timeout(self) -> None:
        error = "ConnectionError: timeout after 30s"
        result = sanitize_error(error)
        assert "timeout" not in result.lower()
        assert "网络" in result

    def test_unknown_error_passthrough(self) -> None:
        error = "some custom error message"
        result = sanitize_error(error)
        assert result == error

    def test_empty_error(self) -> None:
        assert sanitize_error("") == ""

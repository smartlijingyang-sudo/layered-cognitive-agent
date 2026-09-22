from collections.abc import Sequence


class VocalToolFilter:
    """声带工具过滤器：依据执行者身份（协调者 vs 子代理）实施声带物理隔离。

    根据 ADR-0248 §5.3 铁律：
    子代理（Subagent）无 SendMessage 声带，绝不直接对用户发声，重活无杂音，
    必须仅向父进程汇报，由父协调者统一开口。
    """

    VOCAL_TOOL_NAME: str = "send_message"

    def filter_tools_for_runtime(
        self, tools: Sequence[str], origin: str | None = None
    ) -> list[str]:
        if origin == "subagent":
            return [t for t in tools if t != self.VOCAL_TOOL_NAME]
        return list(tools)

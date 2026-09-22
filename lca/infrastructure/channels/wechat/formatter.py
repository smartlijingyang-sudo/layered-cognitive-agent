"""WeChat message formatter ensuring strict parity with LobeHub replyTemplate.ts."""

from __future__ import annotations

from typing import Any

# Use raw Unicode emoji matching LobeHub replyTemplate.ts
EMOJI_THINKING = "💭"
TOOL_PENDING_ICON = "○"
TOOL_COMPLETED_ICON = "⏺"
BRANCH_ICON = "⎿"


class WechatMessageFormatter:
    """Formats reasoning and tool execution progress for WeChat delivery."""

    @classmethod
    def format_step_progress(
        cls,
        step_type: str,
        thinking_text: str | None = None,
        tools_calling: list[dict[str, Any]] | None = None,
        tools_result: list[dict[str, Any]] | None = None,
        total_tool_calls: int = 0,
        elapsed_seconds: float = 0.0,
    ) -> str:
        lines: list[str] = []

        # 1. Header with call count and elapsed time
        if total_tool_calls > 0:
            time_part = f" · {elapsed_seconds:.1f}s" if elapsed_seconds > 0 else ""
            lines.append(f"> 共 **{total_tool_calls}** 次工具调用{time_part}\n")

        # 2. Thinking reasoning
        if thinking_text and thinking_text.strip():
            lines.append(f"{EMOJI_THINKING} {thinking_text.strip()}")

        # 3. Tools calling list
        if tools_calling:
            for i, tool in enumerate(tools_calling):
                identifier = tool.get("identifier", "builtin")
                api_name = tool.get("api_name", "tool")
                summary_arg = tool.get("summary_arg")
                tool_label = f"**{identifier}·{api_name}**"
                call_repr = f"{tool_label}({summary_arg})" if summary_arg else tool_label

                if tools_result and i < len(tools_result):
                    res = tools_result[i]
                    is_success = res.get("is_success", True)
                    status = "success" if is_success else "error"
                    output_text = res.get("output", "")
                    char_count = len(output_text.strip())
                    lines.append(
                        f"{TOOL_COMPLETED_ICON} {call_repr}\n{BRANCH_ICON}  {status}: {char_count:,} chars"
                    )
                else:
                    lines.append(f"{TOOL_PENDING_ICON} {call_repr}")

        return "\n\n".join(lines).strip()

    @classmethod
    def format_final_reply(cls, text: str) -> str:
        return text.rstrip()

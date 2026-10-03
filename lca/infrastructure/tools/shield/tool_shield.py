"""Tool Pitfall Shield — 工具避坑哨兵。

在 Agent 调用具体工具之前，毫秒级自 TOOLS.md 或本地踩坑知识库中提取针对该工具的
安全红线与踩坑提醒，注入到前置执行守护或模型 Prompt 中，避免重复掉入同一陷阱。
"""

from __future__ import annotations

import re
from pathlib import Path


class ToolPitfallShield:
    """工具避坑哨兵：管理与查询针对具体工具的安全红线与踩坑警示。"""

    def __init__(self, guards: dict[str, str] | None = None) -> None:
        self._guards: dict[str, str] = dict(guards or {})

    @classmethod
    def from_markdown(cls, markdown_content: str) -> ToolPitfallShield:
        """从 TOOLS.md 格式的 Markdown 文本中解析工具避坑红线。

        支持两种标准结构：
        1. 章节标题结构：
           ### ssh
           - 宿主机远程请优先使用 ssh252 别名，且禁依赖 /root 软链。
        2. 列表结构：
           - ssh: 宿主机远程请优先使用 ssh252 别名，且禁依赖 /root 软链
        """
        guards: dict[str, str] = {}
        lines = markdown_content.splitlines()

        current_tool: str | None = None
        tool_bullets: list[str] = []

        header_re = re.compile(r"^#{2,4}\s+([\w\-_]+(?:\s*[/,]\s*[\w\-_]+)*)\s*$")
        inline_re = re.compile(r"^[-*]\s*([a-zA-Z0-9_\-]+)\s*[:：]\s*(.+)$")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 1. 尝试匹配内联单行形式: - ssh: ...
            inline_match = inline_re.match(stripped)
            if inline_match:
                tool_key = inline_match.group(1).strip().lower()
                guard_text = inline_match.group(2).strip()
                guards[tool_key] = guard_text
                continue

            # 2. 尝试匹配标题形式: ### ssh 或 ### run_command / bash
            header_match = header_re.match(stripped)
            if header_match:
                if current_tool and tool_bullets:
                    guards[current_tool] = "；".join(tool_bullets)
                    tool_bullets = []
                tools_in_header = [
                    t.strip().lower() for t in re.split(r"[/,]", header_match.group(1)) if t.strip()
                ]
                current_tool = tools_in_header[0] if tools_in_header else None
                continue

            # 3. 收集当前标题下的 bullet
            if current_tool and (stripped.startswith("- ") or stripped.startswith("* ")):
                bullet_text = stripped.lstrip("-* ").strip()
                tool_bullets.append(bullet_text)

        if current_tool and tool_bullets:
            guards[current_tool] = "；".join(tool_bullets)

        return cls(guards=guards)

    @classmethod
    def from_file(cls, path: Path | str) -> ToolPitfallShield:
        """从文件路径加载 TOOLS.md。若文件不存在则返回空哨兵。"""
        p = Path(path)
        if not p.is_file():
            return cls()
        return cls.from_markdown(p.read_text(encoding="utf-8"))

    def get_pre_execution_guard(self, tool_name: str) -> str:
        """毫秒级查询针对该工具的安全警示。未命中返回空字符串。"""
        key = tool_name.strip().lower()
        return self._guards.get(key, "")

    def register_guard(self, tool_name: str, redline: str) -> None:
        """注册针对特定工具的安全红线。"""
        self._guards[tool_name.strip().lower()] = redline.strip()


__all__ = ["ToolPitfallShield"]

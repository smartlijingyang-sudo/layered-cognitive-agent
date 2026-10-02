from __future__ import annotations

from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


class ActivityStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivityCategory(StrEnum):
    COMMAND = "command"
    SUBAGENT = "subagent"
    BROWSER = "browser"
    CRON = "cron"
    TOOL = "tool"


class ActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    run_id: str
    assistant_id: str
    category: ActivityCategory
    title: str
    summary: str
    status: ActivityStatus
    start_time: str
    end_time: str | None = None
    duration_ms: int | None = None
    icon: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    is_system: bool = False


class ActivityIntentNamer:
    @staticmethod
    def name(tool_name: str, arguments: dict[str, Any] | None = None) -> tuple[str, str, str]:
        """Returns (title, summary, icon_type)."""
        args = arguments or {}
        lowered = tool_name.lower()

        # Connectors: Gmail / Mail
        if "gmail" in lowered or (lowered == "hatch_gws_cli" and args.get("service") == "gmail"):
            action = str(args.get("action") or "").lower()
            if "send" in action or "send" in lowered:
                to = args.get("to") or args.get("recipient") or "联系人"
                subj = args.get("subject") or "新邮件"
                return f"正在发送邮件到 {to}", str(subj), "mail"
            query = args.get("query") or args.get("search") or ""
            return "正在搜索 Gmail 邮件", f"检索: {query}" if query else "检索未读重要邮件", "mail"

        # Connectors: Drive
        if "drive" in lowered or (lowered == "hatch_gws_cli" and args.get("service") == "drive"):
            return "正在访问 Google Drive 文档", str(args.get("query") or "浏览文档目录"), "document"

        # Connectors: GitHub
        if "github" in lowered:
            return "正在检索 GitHub 仓库", str(args.get("repo") or args.get("query") or "查看代码与 Issue"), "github"

        # Shell / Box Command
        if lowered in ("run_shell", "shell", "box_run_command") or "exec" in lowered:
            cmd = str(args.get("command") or args.get("cmd") or "")
            summary = (cmd[:40] + "...") if len(cmd) > 40 else (cmd or "系统命令")
            return "Running command", summary, "terminal"

        # Browser
        if "browser" in lowered:
            url = str(args.get("url") or "")
            domain = urlparse(url).netloc if url else "网页"
            task = str(args.get("task") or args.get("goal") or "")
            return f"Browsing {domain}", task or "自动化网页浏览", "browser"

        # Subagent
        if "subagent" in lowered:
            role = str(args.get("role") or args.get("name") or "协同助手")
            prompt = str(args.get("prompt") or args.get("task") or "")
            return f"执行子任务: {role}", prompt[:40] if prompt else "后台协同任务", "robot"

        # Cron Worker
        if "cron" in lowered:
            job_title = str(args.get("title") or args.get("job_title") or "定时提醒")
            return f"定时运行: {job_title}", "按计划执行例程", "clock"

        # Fallback with description
        desc = args.get("description")
        if isinstance(desc, str) and desc.strip():
            return desc.strip(), str(args.get("summary") or tool_name), "tool"

        return f"执行操作: {tool_name}", str(args.get("summary") or "处理中"), "tool"


__all__ = (
    "ActivityCategory",
    "ActivityIntentNamer",
    "ActivityItem",
    "ActivityStatus",
)

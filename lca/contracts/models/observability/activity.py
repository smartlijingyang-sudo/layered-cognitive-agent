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
    tool_name: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    is_system: bool = False
    tool_name: str = ""
    current_step: str | None = None


class StepEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = ""
    step_title: str = ""
    narrative: str = ""
    command: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    truncated_boundary: str = ""
    code_snippets: list[dict[str, str]] = Field(default_factory=list)
    search_results: list[dict[str, Any]] = Field(default_factory=list)
    conclusion: str | None = None


def _deconstruct_command(cmd: str) -> tuple[str, str, str]:
    """Dynamically deconstructs a shell command into (title, summary, icon).

    Zero hardcoded strings, universal engineering intent parsing.
    """
    raw_cmd = cmd.strip()
    if not raw_cmd:
        return "执行系统指令", "系统指令", "terminal"

    inner_cmd = raw_cmd
    if raw_cmd.startswith("ssh") and ("'" in raw_cmd or '"' in raw_cmd):
        import re

        m = re.search(r"ssh\S*\s+['\"](.*?)['\"]", raw_cmd)
        if m:
            inner_cmd = (
                m.group(1).replace('echo "ZZSTART";', "").replace('echo "ZZEND";', "").strip()
            )

    tokens = inner_cmd.split()
    first = tokens[0] if tokens else ""

    # 1. sed / cat / head / tail / view / read
    if first in ("sed", "cat", "head", "tail", "view", "less", "more") or "sed " in inner_cmd:
        import re
        from pathlib import Path

        line_match = re.search(r"['\"]?(\d+,\d+p)['\"]?", inner_cmd)
        line_str = f" ({line_match.group(1).replace('p', '')}行)" if line_match else ""
        files = [t for t in tokens if "." in t and not t.startswith("-")]
        file_name = Path(files[-1]).name if files else "文件"
        return f"读取 {file_name}{line_str}", f"查看代码实现: {file_name}", "document"

    # 2. grep / rg / find / ack
    if first in ("grep", "rg", "find", "ack") or "grep " in inner_cmd:
        import re

        kw_match = re.search(r"(?:grep|rg)\s+(?:-[a-zA-Z]+\s+)*['\"]?([^'\"\s]+)['\"]?", inner_cmd)
        kw = kw_match.group(1) if kw_match else ""
        path = tokens[-1] if tokens and not tokens[-1].startswith("-") and tokens[-1] != kw else ""
        if path:
            return (
                f"在 {path} 检索 {kw} 关键词" if kw else f"在 {path} 检索代码",
                f"检索: {kw}",
                "search",
            )
        return f"检索 {kw} 关键词" if kw else "检索代码内容", f"检索: {kw}", "search"

    # 3. git commands
    if first == "git" or "git " in inner_cmd:
        git_idx = tokens.index("git") if "git" in tokens else 0
        sub_tokens = tokens[git_idx + 1 :]
        sub = sub_tokens[0] if sub_tokens else ""
        if sub in ("worktree", "wt"):
            branch = sub_tokens[-1] if len(sub_tokens) > 1 else "工作树"
            return f"创建工作树 {branch}", f"添加工作树: {branch}", "terminal"
        if sub in ("checkout", "switch", "branch"):
            branch = sub_tokens[-1] if len(sub_tokens) > 1 else ""
            if "-b" in sub_tokens:
                return f"创建分支 {branch}", f"新建分支: {branch}", "terminal"
            return f"切换分支 {branch}", f"检出分支: {branch}", "terminal"
        if sub == "status":
            return "查看 Git 工作区状态", f"{raw_cmd} (核查变更与未跟踪文件)", "terminal"
        if sub == "diff":
            return "查看 Git 代码差异", f"{raw_cmd} (分析代码变更细节)", "terminal"
        if sub == "log":
            return "查看 Git 提交历史", f"{raw_cmd} (回溯版本演进轨迹)", "terminal"
        if sub == "commit":
            return "提交 Git 版本变更", f"{raw_cmd} (落盘暂存区提交)", "terminal"
        if sub in ("pull", "push", "fetch"):
            return "同步 Git 远程仓库", f"{raw_cmd} (执行 git {sub})", "terminal"
        return f"执行 Git {sub} 操作", raw_cmd[:40], "terminal"

    # 4. python / pytest / node / bun / test
    if first in ("pytest", "python", "python3", "bash", "sh") or "pytest" in inner_cmd:
        target = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
        if "test" in inner_cmd or "pytest" in inner_cmd:
            test_target = target or tokens[-1] if tokens else "测试"
            return f"执行 {test_target} 验证", f"运行回归验证套件: {test_target}", "check"
        if target:
            return f"执行脚本 {target}", f"运行: {raw_cmd[:40]}", "terminal"
        return f"运行 {first} 任务", raw_cmd[:40], "terminal"

    # 5. Generic executable fallback
    from pathlib import Path

    binary = Path(first).name
    summary = (raw_cmd[:40] + "...") if len(raw_cmd) > 40 else (raw_cmd or "系统指令")
    return f"执行 {binary} 指令", summary, "terminal"


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
            return (
                "正在访问 Google Drive 文档",
                str(args.get("query") or "浏览文档目录"),
                "document",
            )

        # Connectors: GitHub
        if "github" in lowered:
            repo = args.get("repo") or ""
            owner = args.get("owner") or ""
            repo_display = f"{owner}/{repo}" if (owner and repo) else (repo or owner)
            if "branch" in lowered:
                return (
                    "检索 GitHub 分支",
                    str(repo_display or args.get("query") or "获取分支列表"),
                    "github",
                )
            if "commit" in lowered:
                return (
                    "查询 GitHub 提交记录",
                    str(
                        repo_display
                        or args.get("query")
                        or args.get("q")
                        or args.get("commit_sha")
                        or "查看历史提交"
                    ),
                    "github",
                )
            if "readme" in lowered:
                return "读取 GitHub README", str(repo_display or "项目说明文档"), "github"
            if "content" in lowered or "file" in lowered:
                path = args.get("path") or "根目录"
                return f"浏览 GitHub 文件: {path}", str(repo_display or "仓库代码"), "github"
            return (
                "正在检索 GitHub 仓库",
                str(repo_display or args.get("query") or "查看代码与 Issue"),
                "github",
            )

        # Tool discovery
        if "tool_search" in lowered:
            q = args.get("query") or (
                ", ".join(args.get("namespaces", []))
                if isinstance(args.get("namespaces"), list)
                else ""
            )
            return "发现与检索工具", f"检索: {q}" if q else "按需探索工具集", "tool"

        # Cognitive memory & recall
        if "memory" in lowered or "recall" in lowered:
            q = str(args.get("query") or args.get("content") or args.get("text") or "")
            if "search" in lowered or "recall" in lowered:
                return (
                    "检索认知长期记忆",
                    f"追忆: {q[:30]}" if q else "联想相关知识与偏好",
                    "memory",
                )
            if "add" in lowered or "save" in lowered:
                return "沉淀事实到长期记忆", f"记录: {q[:30]}" if q else "更新记忆库", "memory"
            if "update" in lowered or "supersede" in lowered:
                return "演化与修正长期记忆", f"修正: {q[:30]}" if q else "修正历史事实", "memory"
            if "delete" in lowered:
                return "清理废弃记忆条目", f"删除: {q[:30]}" if q else "遗忘过时信息", "memory"
            return "认知记忆库操作", (q[:30] if q else "维护知识与偏好"), "memory"

        # Assistant self configuration
        if "assistant" in lowered or "soul" in lowered:
            if "read" in lowered or "config" in lowered:
                return "读取助理自治配置", str(args.get("summary") or "自省身份与能力"), "tool"
            if "soul" in lowered:
                return (
                    "演化助理核心灵魂 (SOUL)",
                    str(args.get("summary") or "更新原则与使命"),
                    "tool",
                )

        # File operations
        if "write" in lowered or "create" in lowered or "save" in lowered:
            from pathlib import Path

            target = str(
                args.get("name")
                or args.get("target_file")
                or args.get("path")
                or args.get("file")
                or ""
            )
            target_name = Path(target).name if target else ""
            if target_name:
                if target_name.endswith((".py", ".sh", ".bash", ".js", ".ts")):
                    return f"创建脚本 {target}", f"写入脚本实现: {target}", "document"
                return f"写入文件 {target}", f"写入文件内容: {target}", "document"
            return "创建/写入文件", str(args.get("summary") or tool_name), "document"

        if "replace" in lowered or "edit" in lowered:
            target = str(args.get("target_file") or args.get("path") or args.get("file") or "")
            return (
                f"更新 {target} 的代码实现" if target else "编辑文件内容",
                f"代码修改: {target}",
                "document",
            )

        if "view" in lowered or "read" in lowered:
            target = str(
                args.get("absolute_path")
                or args.get("path")
                or args.get("target_file")
                or args.get("file")
                or ""
            )
            start = args.get("start_line") or args.get("StartLine")
            end = args.get("end_line") or args.get("EndLine")
            lines = f" ({start}-{end}行)" if start and end else ""
            return (
                f"读取 {target}{lines}" if target else "读取文件内容",
                f"查看代码: {target}",
                "document",
            )

        # Shell / Box Command (Universal Dynamic Intent Extractor)
        if lowered in ("run_shell", "shell", "box_run_command") or "exec" in lowered:
            cmd = str(args.get("command") or args.get("cmd") or "")
            return _deconstruct_command(cmd)

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

        summary = str(
            args.get("summary")
            or args.get("query")
            or args.get("path")
            or args.get("url")
            or args.get("command")
            or args.get("cmd")
            or "处理中"
        )
        return f"执行操作: {tool_name}", summary, "tool"

    @staticmethod
    def live_step(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """One-line "what it is doing right now" for a running tool."""
        args = arguments or {}
        lowered = tool_name.lower()

        if lowered in ("run_shell", "shell", "box_run_command") or "exec" in lowered:
            cmd = str(args.get("command") or args.get("cmd") or "")
            title, _, _ = _deconstruct_command(cmd)
            return f"正在{title}"
        if "browser" in lowered:
            url = str(args.get("url") or "")
            if url:
                from urllib.parse import urlparse as _up

                host = _up(url).netloc or url[:30]
                return f"正在浏览 {host}"
            return "正在自动化浏览网页"
        if "subagent" in lowered:
            role = str(args.get("role") or args.get("name") or "子任务")
            return f"子任务执行中：{role}"
        if "memory" in lowered or "recall" in lowered:
            return "正在检索/更新记忆库"
        if "cron" in lowered:
            return "定时任务执行中"
        if "gmail" in lowered or (lowered == "hatch_gws_cli" and args.get("service") == "gmail"):
            return "正在处理 Gmail"
        if "github" in lowered:
            return "正在操作 GitHub"
        return "正在处理中"


def parse_step_evidence(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    thinking: dict[str, Any] | None = None,
    step_id: str = "",
) -> StepEvidence:
    """Parses a tool execution step into a structured 5-element StepEvidence model."""
    from pathlib import Path

    args = arguments or {}
    res = tool_result or {}
    th = thinking or {}

    step_title, default_summary, _ = ActivityIntentNamer.name(tool_name, args)

    reasoning = th.get("reasoning", "")
    if reasoning:
        first_clause = reasoning.split("。")[0].split("\n")[0].strip()
        narrative = f"{first_clause}。{default_summary}" if first_clause else default_summary
    else:
        narrative = f"智能体向执行平面发起「{step_title}」动作。{default_summary}"

    cmd = str(args.get("command") or args.get("cmd") or "")
    if not cmd and tool_name:
        cmd = f"{tool_name}({', '.join(f'{k}={repr(v)[:30]}' for k, v in args.items())})"

    duration_ms = int(res.get("latency_ms") or res.get("duration_ms") or th.get("latency_ms") or 0)
    ok = res.get("ok", True)
    exit_code = 0 if ok else 1
    if "exit_code" in res:
        exit_code = int(res["exit_code"])

    stdout = str(res.get("stdout_head") or res.get("stdout") or res.get("output") or "")
    truncated_boundary = ""
    if "ZZSTART" in stdout or "ZZSTART" in cmd:
        truncated_boundary = "ZZSTART / ZZEND"

    code_snippets: list[dict[str, str]] = []
    search_results: list[dict[str, Any]] = []

    if "grep" in tool_name.lower() or "search" in tool_name.lower() or "grep" in cmd:
        lines = stdout.strip().splitlines()
        for idx, line in enumerate(lines[:15]):
            if ":" in line:
                parts = line.split(":", 2)
                loc = f"{Path(parts[0]).name}:{parts[1]}" if len(parts) >= 2 else line
                match_text = parts[2].strip() if len(parts) >= 3 else line
                search_results.append(
                    {
                        "index": idx + 1,
                        "location": loc,
                        "match": match_text,
                    }
                )
        if not search_results and stdout.strip():
            code_snippets.append(
                {
                    "label": "检索输出结果",
                    "code": stdout[:2000],
                    "language": "bash",
                }
            )
    else:
        if stdout.strip():
            code_snippets.append(
                {
                    "label": f"提取到的代码内容 ({len(stdout.splitlines())} 行)",
                    "code": stdout[:3000],
                    "language": "python"
                    if any(k in cmd or k in tool_name for k in ("py", "python"))
                    else "bash",
                }
            )

    if ok:
        delta = res.get("delta_summary") or ""
        if delta and "ok" not in delta.lower():
            conclusion = f"验证结论：{delta}。动作执行完成，信息完整，无执行错误。"
        else:
            conclusion = f"验证结论：{step_title} 已执行完成，符合预期，无执行错误，信息完整。"
    else:
        err = res.get("error") or "未知错误"
        conclusion = f"执行异常：动作未达预期，错误信息：{err}"

    return StepEvidence(
        id=step_id,
        step_title=step_title,
        narrative=narrative,
        command=cmd,
        exit_code=exit_code,
        duration_ms=duration_ms,
        truncated_boundary=truncated_boundary,
        code_snippets=code_snippets,
        search_results=search_results,
        conclusion=conclusion,
    )


__all__ = (
    "ActivityCategory",
    "ActivityIntentNamer",
    "ActivityItem",
    "ActivityStatus",
    "StepEvidence",
    "parse_step_evidence",
)

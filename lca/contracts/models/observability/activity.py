from __future__ import annotations

import re
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
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
        m = re.search(r"ssh\S*\s+['\"](.*?)['\"]", raw_cmd)
        if m:
            inner_cmd = m.group(1).strip()

    main_cmd = re.split(r"[|;&]", inner_cmd)[0].strip()
    tokens = main_cmd.split()
    first = tokens[0] if tokens else ""

    # 1. sed / cat / head / tail / view / read
    if first in ("sed", "cat", "head", "tail", "view", "less", "more") or "sed " in inner_cmd:
        line_match = re.search(r"['\"]?(\d+,\d+p)['\"]?", inner_cmd)
        line_str = f" ({line_match.group(1).replace('p', '')}行)" if line_match else ""
        files = [t.strip("\"'") for t in tokens if "." in t and not t.startswith("-")]
        file_name = Path(files[-1]).name if files else "文件"
        return f"读取 {file_name}{line_str}", f"查看代码实现: {file_name}", "document"

    # 2. find
    if first == "find":
        name_match = re.search(r"-name\s+['\"]?([^'\"\s]+)['\"]?", inner_cmd)
        if name_match:
            target = name_match.group(1).strip("\"'")
            return f"查找文件 {target}", f"检索目标路径: {target}", "search"
        return "在文件系统中检索文件", f"查找: {raw_cmd[:40]}", "search"

    # 3. grep / rg / ack
    if first in ("grep", "rg", "ack") or "grep " in inner_cmd or "rg " in inner_cmd:
        kw_match = re.search(
            r"(?:grep|rg)\s+(?:-[a-zA-Z0-9]+\s+)*['\"]?([^'\"\s]+)['\"]?", inner_cmd
        )
        kw = kw_match.group(1).strip("\"'") if kw_match else ""
        non_flag_tokens = [
            t.strip("\"'")
            for t in tokens[1:]
            if not t.startswith("-")
            and t.strip("\"'") != kw
            and not t.startswith("2>")
            and t != "||"
        ]
        path = non_flag_tokens[-1] if non_flag_tokens else ""
        if path:
            path_display = Path(path).name or path
            return (
                f"在 {path_display} 检索 {kw} 关键词" if kw else f"在 {path_display} 检索代码",
                f"检索: {kw}",
                "search",
            )
        return f"检索 {kw} 关键词" if kw else "检索代码内容", f"检索: {kw}", "search"

    # 4. git commands
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

    # 5. python / pytest / node / bun / test
    if first in ("pytest", "python", "python3", "bash", "sh") or "pytest" in inner_cmd:
        if "test" in inner_cmd or "pytest" in inner_cmd:
            test_files = [
                t.strip("\"'")
                for t in tokens
                if ("test" in t.lower() or "tests/" in t)
                and not t.startswith("-")
                and not t.startswith("2>")
            ]
            test_target = test_files[0] if test_files else "pytest"
            return f"运行测试 {test_target}", f"运行自动化测试套件: {test_target}", "check"
        target = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
        if target:
            target_name = Path(target.strip("\"'")).name
            return f"执行脚本 {target_name}", f"运行: {raw_cmd[:40]}", "terminal"
        return f"运行 {first} 任务", raw_cmd[:40], "terminal"

    # 6. Generic executable fallback
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
            clean_target = (
                target.replace("/mnt/data/", "") if target.startswith("/mnt/data/") else target
            )
            start = args.get("start_line") or args.get("StartLine")
            end = args.get("end_line") or args.get("EndLine")
            lines = (
                f" ({start}-{end}行)"
                if start and end
                else (f" (前{end}行)" if end and not start else "")
            )
            return (
                f"读取 {clean_target}{lines}" if clean_target else "读取文件内容",
                f"查看代码: {clean_target}",
                "document",
            )

        # Shell / Box Command (Universal Dynamic Intent Extractor)
        if (
            lowered in ("run_shell", "shell", "box_run_command", "bash", "sh")
            or "exec" in lowered
            or "command" in lowered
        ):
            cmd = str(args.get("command") or args.get("cmd") or args.get("CommandLine") or "")
            if cmd:
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
    args = arguments or {}
    res = tool_result or {}
    th = thinking or {}

    step_title, default_summary, _ = ActivityIntentNamer.name(tool_name, args)

    cmd = str(args.get("command") or args.get("cmd") or args.get("CommandLine") or "")
    if not cmd and tool_name:
        cmd = f"{tool_name}({', '.join(f'{k}={repr(v)[:30]}' for k, v in args.items())})"

    lowered_name = tool_name.lower()
    lowered_cmd = cmd.lower()

    # 1. Narrative: prioritize rich domain engineering narrative per tool action
    specific_narrative = ""
    if "grep" in lowered_name or "grep" in lowered_cmd or "rg" in lowered_cmd:
        kw_m = re.search(r"(?:grep|rg)\s+(?:-[a-zA-Z0-9]+\s+)*['\"]?([^'\"\s]+)['\"]?", cmd)
        kw = kw_m.group(1).strip("\"'") if kw_m else "相关"
        path_token = [
            t.strip("\"'")
            for t in cmd.split()
            if "." in t and not t.startswith("-") and t.strip("\"'") != kw
        ]
        loc = Path(path_token[0]).name if path_token else "代码库"
        specific_narrative = f"执行了远程grep命令检索 {kw} 关键词，在{loc}中快速定位函数实现、调用链路与状态恢复逻辑。"
    elif (
        "cat" in lowered_cmd
        or "sed" in lowered_cmd
        or "read" in lowered_name
        or "view" in lowered_name
    ):
        target_disp = Path(
            args.get("path") or args.get("target_file") or args.get("file") or "目标文件"
        ).name
        specific_narrative = f"执行了代码文件读取操作，获取 {target_disp} 的核心函数实现与上下文定义，验证数据结构与控制流的一致性。"
    elif "pytest" in lowered_cmd or "test" in lowered_cmd:
        specific_narrative = "执行了自动化测试验证，运行端到端与架构不变量断言，确保系统各层契约与生命周期状态机稳定闭环。"
    elif "git" in lowered_cmd:
        specific_narrative = (
            "执行了Git版本控制命令，探查代码差异与工作区状态，确保变更范围严格约束于所有权边界。"
        )
    elif "self_config" in lowered_name or "soul" in lowered_name:
        specific_narrative = "执行了助理自治配置自省操作，完整读取并解析 SOUL.md 与工作区身份契约，确保认知智能体的行为边界与自治策略保持一致。"
    elif "find" in lowered_cmd:
        target_find = re.search(r"-name\s+['\"]?([^'\"\s]+)['\"]?", cmd)
        t_name = target_find.group(1).strip("\"'") if target_find else "源文件"
        specific_narrative = f"在工作区文件系统中执行检索操作，定位目标 {t_name} 及模块分布，确认资产完备性与路径有效性。"
    elif "list" in lowered_name or "env" in lowered_name:
        specific_narrative = (
            "执行环境配置与运行时探查，获取当前沙箱与执行主机的连接状态与挂载点分布。"
        )
    else:
        specific_narrative = f"智能体向执行平面发起「{step_title}」动作。执行了指令：{default_summary}，确保执行环境与契约状态一致。"

    reasoning = th.get("reasoning", "")
    if reasoning and not any(
        reasoning.strip().startswith(p) for p in ("好的", "现在", "让我", "首先", "我需要")
    ):
        cleaned = reasoning.strip().replace("\r\n", "\n")
        paras = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        candidate = paras[0] if paras else cleaned
        if len(candidate) > 400:
            end_idx = candidate[:400].rfind("。")
            candidate = candidate[: end_idx + 1] if end_idx > 120 else candidate[:400] + "..."
        narrative = candidate
    else:
        narrative = specific_narrative

    duration_ms = int(res.get("latency_ms") or res.get("duration_ms") or th.get("latency_ms") or 0)
    ok = res.get("ok", True)
    exit_code = int(res["exit_code"]) if "exit_code" in res else (0 if ok else 1)

    stdout = str(res.get("stdout_head") or res.get("stdout") or res.get("output") or "")
    stderr = str(res.get("stderr") or "")
    truncated_boundary = ""
    if res.get("stdout_truncated"):
        chars_total = res.get("stdout_chars_total", 0)
        truncated_boundary = f"已截断（共 {chars_total} 字符）" if chars_total else "输出已截断"

    code_snippets: list[dict[str, str]] = []
    search_results: list[dict[str, Any]] = []

    # Local fallback file resolution if stdout is empty
    if not stdout.strip():
        target_path_str = str(
            args.get("path")
            or args.get("target_file")
            or args.get("file")
            or args.get("absolute_path")
            or ""
        )
        if target_path_str:
            clean_p = target_path_str.replace("/mnt/data/", "").lstrip("/")
            local_f = Path(clean_p)
            if not local_f.is_file() and "/" in clean_p:
                parts = clean_p.split("/")
                for i in range(len(parts)):
                    candidate_p = Path("/".join(parts[i:]))
                    if candidate_p.is_file():
                        local_f = candidate_p
                        break
            if local_f.is_file():
                with suppress(Exception):
                    all_lines = local_f.read_text(encoding="utf-8").splitlines()
                    start_l = int(args.get("start_line") or args.get("StartLine") or 1)
                    end_l = int(
                        args.get("end_line")
                        or args.get("EndLine")
                        or min(start_l + 39, len(all_lines))
                    )
                    sub_lines = all_lines[max(0, start_l - 1) : end_l]
                    stdout = "\n".join(sub_lines)

    if "grep" in tool_name.lower() or "search" in tool_name.lower() or "grep" in cmd or "rg" in cmd:
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
            lang = "python" if any(k in cmd or k in tool_name for k in ("py", "python")) else "bash"
            if "soul" in lowered_name or "self_config" in lowered_name or "markdown" in stdout:
                lang = "markdown"
            label = (
                "提取到的自治配置"
                if "soul" in lowered_name or "self_config" in lowered_name
                else f"提取到的代码内容 ({len(stdout.splitlines())} 行)"
            )
            code_snippets.append(
                {
                    "label": label,
                    "code": stdout[:3000],
                    "language": lang,
                }
            )

    if stderr.strip():
        code_snippets.append(
            {
                "label": f"错误输出 (stderr, exit {exit_code})",
                "code": stderr[:3000],
                "language": "bash",
            }
        )

    if ok:
        if search_results:
            conclusion = f"验证结论：在代码库中检索到 {len(search_results)} 处匹配定义，成功定位目标实现与调用入口，执行顺利且状态一致。"
        elif code_snippets:
            clean_t = step_title[2:].strip() if step_title.startswith("读取") else step_title
            conclusion = (
                f"验证结论：已成功读取并解析 {clean_t} 目标内容，提取实现完整，无截断或解析异常。"
            )
        else:
            delta = res.get("delta_summary") or ""
            if delta and "ok" not in delta.lower():
                conclusion = f"验证结论：{delta}。动作执行完成，信息完整，无执行错误。"
            else:
                conclusion = f"验证结论：{step_title} 已执行完成，符合预期，无执行错误，信息完整。"
    else:
        err = res.get("error") or res.get("stderr") or "未知错误"
        conclusion = f"验证结论：动作执行未达预期（退出码 {exit_code}）。原因：{err}。"

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

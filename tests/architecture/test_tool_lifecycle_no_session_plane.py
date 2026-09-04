"""Session 平面不承载 tool lifecycle —— 长期回归锁。

Tool 事实的 SSOT 在 Journal 平面（``ToolStarted`` / ``ToolInvoked`` /
``ToolDenied``，经 ``invocation_id`` join，ADR-0101 PR-2），step 证据走
LoopCursor（``step.tool_call.record`` / ``step.tool_result.record``）。
Session 词表再引入 ``tool.*.v1`` 会为同一事实制造第二真值，故锁死。

resume/approval 的 durable 点继续走 ``approval.persisted.v1`` /
``approval.resolved.v1``，不在本锁限制范围。

长期回归锁；delete-when: N/A。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVENTS_MODULE = _REPO_ROOT / "lca" / "contracts" / "harness" / "memory" / "events.py"

_FORBIDDEN_TYPES = (
    "tool.called.v1",
    "tool.completed.v1",
    "tool.approval_requested.v1",
    "tool.approval_resolved.v1",
)


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path, *, glob: str = "*.py") -> list[str]:
    """Run ripgrep over python sources; empty list = no matches."""
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                "--glob",
                glob,
                pattern,
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    out: list[str] = []
    for path in root.rglob(glob):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.strip('"') in line:
                out.append(f"{path}:{lineno}:{line}")
    return out


def test_session_vocabulary_has_no_tool_lifecycle_types() -> None:
    """events.py 不得声明 tool.*.v1 session_event 词表。"""
    text = _EVENTS_MODULE.read_text(encoding="utf-8")
    for forbidden in _FORBIDDEN_TYPES:
        assert forbidden not in text, (
            f"Session 词表重新引入 {forbidden!r}；tool 事实归 Journal 平面，"
            "见 ADR-0101 PR-2 与本测试文件头注。"
        )


def test_no_code_constructs_tool_lifecycle_session_events() -> None:
    """lca/ 不得构造已删除的 Tool* session 事件类。"""
    matches = _rg(r"ToolCalled\(|ToolCompleted\(|ToolApprovalRequested\(", _REPO_ROOT / "lca")
    assert matches == [], f"发现 Session 平面 tool 事件构造: {matches}"


def test_no_consumer_reads_tool_lifecycle_session_types() -> None:
    """lca/ 不得再读 tool.*.v1 session 类型字符串。"""
    for forbidden in _FORBIDDEN_TYPES:
        matches = _rg(forbidden, _REPO_ROOT / "lca")
        assert matches == [], f"{forbidden!r} 仍有消费方: {matches}"

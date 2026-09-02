"""Architecture guard: Agent / Brain / Body / Perceive 不直接写 EP（ADR-0167 D11 / I-PLUG1 / ADR-0169 L10 L11）。

PR-2 强化:
- L10:business 层不直接 import FileSink / RoutingFileSink 实例(走 spine Protocol)
- L11:business 层不 emit LlmCallCompleted / LlmCallStarted(走 spine EP)
- L4:business 层不 import EventSpine / Serializer / Storage(已存在)

PR-27 强化(L10 默认文件名):
- FileSink / RunRoutingFileSink / RoutingFileStorage 默认 ``file_name`` = ``$run_id.spine.jsonl``
- FilesystemJournalStore.DEFAULT_FILENAME = ``$run_id.spine.jsonl``
- 不允许关键 sink / storage 源码把 ``"events.jsonl"`` 作为 ``file_name=`` /
  ``DEFAULT_FILENAME=`` / ``cfg.get("file_name"`` 等默认字面量传入。
  显式传入(测试 fixture 等)允许。

退出码 0 = pass；非 0 = 列出违规（CI 必须 fail-fast）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED_IMPORTS = (
    "lca.infrastructure.observability.spine.event_spine",
    "lca.infrastructure.observability.spine.sinks.file_sink",
    "lca.infrastructure.observability.spine.sinks.routing_file_sink",
    "lca.runtime.step_emitter",
    "lca.runtime.observability_firewall",
)
BANNED_NAMES = (
    "step_emitter",
    "bridge_firewall",
    "bridge_perceive_",
    "bridge_think_",
    "bridge_act_",
    "bridge_tool_",
    "bridge_llm_",
    "bridge_step_",
)
DIRECTORIES = (ROOT / "lca/cognition", ROOT / "lca/runtime", ROOT / "lca/agent")

# L11:business 层禁止 emit 旧 journal LLM 事件(ADR-0169 L11 / ADR-0167 D11)
LLM_CALL_EMIT_PATTERN = re.compile(r"\bLlmCall(?:Completed|Started)\s*\(")

# PR-27:扫描的关键 sink / storage 文件
L10_FILENAME_SCAN_FILES = (
    "lca/infrastructure/observability/spine/sinks/file_sink.py",
    "lca/infrastructure/observability/spine/sinks/routing_file_sink.py",
    "lca/infrastructure/observability/writable_matrix/defaults.py",
    "lca/infrastructure/observability/journal/backends/filesystem.py",
    "lca/plugins/observability/spine/sinks/file.py",
)

# PR-27:这些位置若把 ``"events.jsonl"`` 当作 ``file_name=`` / ``DEFAULT_FILENAME=`` /
# ``filename=`` / ``cfg.get("file_name"`` 默认值,违反 L10。
# 匹配模式 1:file_name / filename / DEFAULT_FILENAME 作为赋值或参数 → ``events.jsonl``
DEFAULT_EVENTS_JSONL_PATTERN = re.compile(r"""(?:DEFAULT_FILENAME)\s*=\s*["']events\.jsonl["']""")
# 匹配模式 2:cfg.get / dict.get("file_name", "events.jsonl") / cfg["file_name"] = "events.jsonl"
DEFAULT_EVENTS_JSONL_GET_PATTERN = re.compile(
    r"""\.get\(\s*["'](?:file_name|filename)["']\s*,\s*["']events\.jsonl["']\s*\)"""
)
# 匹配模式 3:参数签名如 ``file_name: str = "events.jsonl"`` 或 ``file_name = "events.jsonl"``
DEFAULT_EVENTS_JSONL_KWARG_PATTERN = re.compile(
    r"""file_name\s*[:=][^"'\n]*?["']events\.jsonl["']"""
)


def _check_l10_default_filename() -> list[str]:
    """ADR-0169 PR-27 L10:默认文件名必须 = ``$run_id.spine.jsonl`` 模板。

    检查关键 sink / storage 文件,确保不再把 ``"events.jsonl"`` 作为
    默认 ``file_name`` / ``DEFAULT_FILENAME`` 等字面量。
    跳过 docstring / 注释 / 反引号 example 提及。
    """
    errors: list[str] = []
    for relpath in L10_FILENAME_SCAN_FILES:
        fp = ROOT / relpath
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8")
        for ln_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            # 跳过 docstring 行(行首是引号或 """ 区块)
            if stripped.startswith(('"', "'", '"""', "'''")):
                continue
            # 跳过 docstring 内的 bullet 行(以 - 开头或缩进后 - 开头)
            if stripped.startswith("-") and "events.jsonl" in stripped:
                continue
            # 跳过反引号 example 行(``...`` 包裹字面)
            if "``" in line:
                continue
            if (
                DEFAULT_EVENTS_JSONL_PATTERN.search(line)
                or DEFAULT_EVENTS_JSONL_GET_PATTERN.search(line)
                or DEFAULT_EVENTS_JSONL_KWARG_PATTERN.search(line)
            ):
                errors.append(
                    f"{relpath}:{ln_no}: L10 PR-27 violation: "
                    f"默认文件名不应再为 events.jsonl,应改为 $run_id.spine.jsonl"
                )
    return errors


def _check_l10_l11() -> list[str]:
    """扫描 business 层,验证 L10 / L11 不被破坏。"""
    errors: list[str] = []
    for d in DIRECTORIES:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for ln_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                # 跳过注释行
                if stripped.startswith("#"):
                    continue
                # L11:跳过 docstring 提及(启发式:行首是引号)
                if stripped.startswith(('"', "'", '"""', "'''")):
                    continue
                if LLM_CALL_EMIT_PATTERN.search(line):
                    errors.append(
                        f"{py.relative_to(ROOT)}:{ln_no}: L11 violation: "
                        f"business 层禁止 emit LlmCallCompleted/Started"
                    )
    return errors


def _check() -> list[str]:
    errors: list[str] = []
    py_files: list[Path] = []
    for d in DIRECTORIES:
        if not d.exists():
            continue
        py_files.extend(p for p in d.rglob("*.py") if p.is_file())

    for path in py_files:
        text = path.read_text(encoding="utf-8")
        for banned in BANNED_IMPORTS:
            if banned in text:
                errors.append(f"{path.relative_to(ROOT)}: bans import {banned!r}")
        for name in BANNED_NAMES:
            if name in text:
                errors.append(f"{path.relative_to(ROOT)}: bans identifier {name!r}")
    errors.extend(_check_l10_l11())
    errors.extend(_check_l10_default_filename())
    return errors


def main() -> int:
    errs = _check()
    if errs:
        print("Writable-matrix boundary guard FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("Writable-matrix boundary guard OK (L4 + L10 + L10-default + L11)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

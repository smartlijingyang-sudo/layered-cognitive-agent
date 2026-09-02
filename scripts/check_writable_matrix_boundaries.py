"""Architecture guard: Agent / Brain / Body / Perceive 不直接写 EP（ADR-0167 D11 / I-PLUG1 / ADR-0169 L10 L11）。

PR-2 强化:
- L10:business 层不直接 import FileSink / RoutingFileSink 实例(走 spine Protocol)
- L11:business 层不 emit LlmCallCompleted / LlmCallStarted(走 spine EP)
- L4:business 层不 import EventSpine / Serializer / Storage(已存在)

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
    return errors


def main() -> int:
    errs = _check()
    if errs:
        print("Writable-matrix boundary guard FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("Writable-matrix boundary guard OK (L4 + L10 + L11)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

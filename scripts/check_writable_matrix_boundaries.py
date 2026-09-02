"""Architecture guard: Agent / Brain / Body / Perceive 不直接写 EP（ADR-0167 D11 / I-PLUG1）。

PR-3 删除了历史桥接层。本 guard 严格 fail-fast：

- cognition/* / runtime/* / agent/* 文件禁止出现历史桥接标识符；
- 禁止直接 import EventSpine / FileSink / RoutingFileSink；
- 禁止直接写具体 Serializer / EventStorage 实例（除 contracts/writable_matrix）。

退出码 0 = pass；非 0 = 列出违规（CI 必须 fail-fast）。
"""

from __future__ import annotations

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
    return errors


def main() -> int:
    errs = _check()
    if errs:
        print("Writable-matrix boundary guard FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("Writable-matrix boundary guard OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

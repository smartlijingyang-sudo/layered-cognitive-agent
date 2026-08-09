#!/usr/bin/env python3
"""从 gateway 模式目录 + HTTP 契约生成 web/src/contracts/*.generated.ts（ADR-0052）。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gateway.contracts import CreateRunRequest, CreateRunResponse  # noqa: E402
from gateway.mode_catalog import (  # noqa: E402
    ALL_MODES,
    EXAMPLE_PROMPTS,
    MODE_HELP,
    SOLO_MODE_KEY,
)
from gateway.run_registry import RunStatus  # noqa: E402
from scripts._ts_codegen import dataclass_interface, ts_type  # noqa: E402

_MODES_OUT = _ROOT / "web" / "src" / "contracts" / "modes.generated.ts"
_RUNS_OUT = _ROOT / "web" / "src" / "contracts" / "runs.generated.ts"


def _escape_ts_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _literal_record(name: str, mapping: dict[str, str]) -> str:
    lines = [f"export const {name} = {{"]
    for key in ALL_MODES:
        value = mapping[key]
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  {key}: "{escaped}",')
    # solo 不进 MODE_DEFINITIONS，单独加
    lines.append(f'  {SOLO_MODE_KEY}: "",')
    lines.append("} as const;")
    return "\n".join(lines)


def _example_prompts_record() -> str:
    lines = ["export const EXAMPLE_PROMPTS = {"]
    for key in ALL_MODES:
        prompts = EXAMPLE_PROMPTS[key]
        items = ", ".join(f'"{_escape_ts_string(prompt)}"' for prompt in prompts)
        lines.append(f"  {key}: [{items}],")
    lines.append(f"  {SOLO_MODE_KEY}: [],")
    lines.append("} as const;")
    return "\n".join(lines)


def generate_modes() -> str:
    # 前端可选模式 = solo + team（ADR-0052）
    all_ui_modes = [SOLO_MODE_KEY, *ALL_MODES]
    parts = [
        "/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */",
        "",
        f"export const ALL_MODES = {all_ui_modes!r} as const;",
        "export type Mode = (typeof ALL_MODES)[number];",
        "",
        f'export const SOLO_MODE_KEY = "{SOLO_MODE_KEY}";',
        "",
        _literal_record("MODE_HELP", MODE_HELP),
        "",
        _example_prompts_record(),
        "",
    ]
    return "\n".join(parts) + "\n"


def generate_runs() -> str:
    parts = [
        "/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */",
        "",
        f"export type RunStatus = {ts_type(RunStatus)};",
        "",
        dataclass_interface("CreateRunRequest", CreateRunRequest),
        "",
        dataclass_interface("CreateRunResponse", CreateRunResponse),
        "",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    for path, content in (
        (_MODES_OUT, generate_modes()),
        (_RUNS_OUT, generate_runs()),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()

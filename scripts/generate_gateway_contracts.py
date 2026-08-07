#!/usr/bin/env python3
"""从 gateway 模式目录 + HTTP 契约生成 web/src/contracts/*.generated.ts。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gateway.contracts import CreateRunRequest, CreateRunResponse  # noqa: E402
from gateway.mode_catalog import (  # noqa: E402
    ALL_MODES,
    AUTO_EXAMPLE_PROMPTS,
    AUTO_MODE_HELP,
    AUTO_MODE_KEY,
    EXAMPLE_PROMPTS,
    MODE_HAS_LEAD,
    MODE_HELP,
)
from gateway.run_registry import RunStatus  # noqa: E402
from scripts._ts_codegen import dataclass_interface, ts_type  # noqa: E402

_MODES_OUT = _ROOT / "web" / "src" / "contracts" / "modes.generated.ts"
_RUNS_OUT = _ROOT / "web" / "src" / "contracts" / "runs.generated.ts"


def _literal_record(name: str, mapping: dict[str, str | bool]) -> str:
    lines = [f"export const {name} = {{"]
    for key in ALL_MODES:
        value = mapping[key]
        if isinstance(value, bool):
            lines.append(f"  {key}: {str(value).lower()},")
        else:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  {key}: "{escaped}",')
    lines.append("} as const;")
    return "\n".join(lines)


def _escape_ts_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _example_prompts_record() -> str:
    lines = ["export const EXAMPLE_PROMPTS = {"]
    for key in ALL_MODES:
        prompts = EXAMPLE_PROMPTS[key]
        items = ", ".join(f'"{_escape_ts_string(prompt)}"' for prompt in prompts)
        lines.append(f"  {key}: [{items}],")
    lines.append("} as const;")
    return "\n".join(lines)


def generate_modes() -> str:
    parts = [
        "/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */",
        "",
        f"export const ALL_MODES = {list(ALL_MODES)!r} as const;",
        "export type Mode = (typeof ALL_MODES)[number];",
        "",
        # 自动组队入口独立于 MODE_DEFINITIONS（ADR-0040 静态目录前提，ADR-0042）
        f'export const AUTO_MODE_KEY = "{AUTO_MODE_KEY}";',
        f'export const AUTO_MODE_HELP = "{AUTO_MODE_HELP}";',
        f"export const AUTO_EXAMPLE_PROMPTS = {list(AUTO_EXAMPLE_PROMPTS)!r} as const;",
        "",
        _literal_record("MODE_HELP", MODE_HELP),
        "",
        _literal_record("MODE_HAS_LEAD", {k: MODE_HAS_LEAD[k] for k in ALL_MODES}),
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

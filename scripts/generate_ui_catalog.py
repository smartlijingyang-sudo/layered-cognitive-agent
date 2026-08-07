#!/usr/bin/env python3
"""从 modes.py + gateway 契约生成 web/src/contracts/catalog.generated.ts。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gateway.contracts import CreateRunRequest, CreateRunResponse  # noqa: E402
from gateway.run_registry import RunStatus  # noqa: E402
from scripts._ts_codegen import dataclass_interface  # noqa: E402
from tests.harness.modes import (  # noqa: E402
    _SCENARIOS,
    ALL_MODES,
    MODE_HAS_LEAD,
    MODE_HELP,
)

_OUT = _ROOT / "web" / "src" / "contracts" / "catalog.generated.ts"


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


def _run_status_type() -> str:
    members = [m.value for m in RunStatus]
    members.append("canceled")
    return " | ".join(f'"{m}"' for m in members)


def generate() -> str:
    parts = [
        "/** AUTO-GENERATED — scripts/generate_ui_catalog.py */",
        "",
        f"export const ALL_MODES = {list(ALL_MODES)!r} as const;",
        "export type Mode = (typeof ALL_MODES)[number];",
        "",
        _literal_record("MODE_HELP", MODE_HELP),
        "",
        _literal_record("MODE_HAS_LEAD", {k: MODE_HAS_LEAD[k] for k in ALL_MODES}),
        "",
        _literal_record(
            "MODE_DEFAULT_OBJECTIVE",
            {k: _SCENARIOS[k].default_objective for k in ALL_MODES},
        ),
        "",
        f"export type RunStatus = {_run_status_type()};",
        "",
        dataclass_interface("CreateRunRequest", CreateRunRequest),
        "",
        dataclass_interface("CreateRunResponse", CreateRunResponse),
        "",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    content = generate()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""从 gateway 模式目录 + HTTP 契约生成 web/src/contracts/catalog.generated.ts。"""

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
    MODE_HAS_LEAD,
    MODE_HELP,
)
from gateway.run_registry import RunStatus  # noqa: E402
from scripts._ts_codegen import dataclass_interface  # noqa: E402

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


def _example_prompts_record() -> str:
    lines = ["export const EXAMPLE_PROMPTS = {"]
    for key in ALL_MODES:
        prompts = EXAMPLE_PROMPTS[key]
        items = ", ".join(
            f'"{prompt.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))}"'
            for prompt in prompts
        )
        lines.append(f"  {key}: [{items}],")
    lines.append("} as const;")
    return "\n".join(lines)


def _run_status_type() -> str:
    members = [m.value for m in RunStatus]
    members.append("canceled")
    unique = dict.fromkeys(members)
    return " | ".join(f'"{m}"' for m in unique)


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
        _example_prompts_record(),
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

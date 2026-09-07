"""Patch: LCA-specific chat persistence + tool-rendering helpers.

Replaces the persistence half of the legacy ``lca_run_driver`` patch.
No lobehub-ui source modifications — this module only creates the
helper TS files; the ``lca_runtime_agent_gateway`` patch owns the
4 source modifications that ``lca_run_driver`` used to make.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta
from lca.plugins.transport.webserver.handlers.runs.wire import WIRE

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"

meta = PatchMeta(
    name="lca_runtime_chat_persistence",
    description="LCA message-write + tool-render helpers (chat persistence).",
    files=(
        f"{_UI_TRANSPORTS}/lcaChatRow.ts",
        f"{_UI_TRANSPORTS}/lcaPersist.ts",
        f"{_UI_TRANSPORTS}/lcaFinishChat.ts",
        f"{_UI_TRANSPORTS}/lcaError.ts",
        f"{_UI_TRANSPORTS}/lcaArtifacts.ts",
        f"{_UI_TRANSPORTS}/lcaWire.ts",
        f"{_UI_TRANSPORTS}/lcaToolRender/contracts.generated.ts",
    ),
    risk="medium",
    category="runtime",
    depends_on=(),
    why=(
        "LCA-specific message-write and tool-rendering helpers have no "
        "native equivalent. The transport is replaced in P1 (see "
        "lca_runtime_agent_gateway) but the persistence layer stays."
    ),
    technical_detail=(
        "Files are copied as-is. lcaWire.ts is generated at patch apply "
        "time from the WIRE table in the Python gateway. The 4 "
        "lobehub-ui source modifications of the legacy lca_run_driver "
        "are NOT in this module — they are owned by "
        "lca_runtime_agent_gateway (P1 changes) or retired (reconcile)."
    ),
    verify_file=f"{_UI_TRANSPORTS}/lcaChatRow.ts",
    verify_marker="/* LCA: chat persistence helpers */",
)


def render_wire_ts(wire: Mapping[str, tuple[str, str]]) -> str:
    """Mirror of the legacy generator: produce lcaWire.ts from WIRE."""
    lines = [
        "/** Generated from lca.plugins.transport.webserver.handlers.runs.wire.WIRE. Do not edit. */",
        "",
        "export const WIRE: Record<string, readonly [string, string]> = {",
    ]
    for name, (identifier, api_name) in wire.items():
        lines.append(f"  '{name}': ['{identifier}', '{api_name}'],")
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


_PERSIST_FILES = (
    "lcaChatRow.ts",
    "lcaPersist.ts",
    "lcaFinishChat.ts",
    "lcaError.ts",
    "lcaArtifacts.ts",
)


def apply(ctx: PatchContext) -> bool:
    """Copy the 5 LCA-only TS helpers + generate lcaWire.ts."""
    changed = False

    for name in _PERSIST_FILES:
        rel = f"{_UI_TRANSPORTS}/{name}"
        src = _HERE / name
        if not src.is_file():
            raise SystemExit(f"missing patch source: {src}")
        text = src.read_text(encoding="utf-8")
        # Make sure the file carries the marker (idempotent).
        marker = "/* LCA: chat persistence helpers */"
        if marker not in text:
            text = text + "\n" + marker + "\n"
        if ctx.write_if_changed(rel, text):
            changed = True

    # Generate lcaWire.ts from the WIRE table.
    wire_rel = f"{_UI_TRANSPORTS}/lcaWire.ts"
    wire_text = render_wire_ts(WIRE)
    if ctx.write_if_changed(wire_rel, wire_text):
        changed = True

    # contracts.generated.ts is pre-built by codegen_ts.py; just copy.
    contracts_rel = f"{_UI_TRANSPORTS}/lcaToolRender/contracts.generated.ts"
    contracts_src = _HERE / "lcaToolRender" / "contracts.generated.ts"
    if not contracts_src.is_file():
        raise SystemExit(f"missing patch source: {contracts_src}")
    if ctx.write_if_changed(contracts_rel, contracts_src.read_text(encoding="utf-8")):
        changed = True

    return changed
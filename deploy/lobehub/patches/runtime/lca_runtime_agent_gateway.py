"""Patch: front-end WS gateway client + minimal source modifications.

This module owns:
- 8 new TS files under src/store/chat/agents/transports/lcaGateway/
- 6 marker insertions into lobehub-ui source files; each insertion
  carries a unique ``/* LCA-P1: <purpose> */`` marker that THIS module
  appends (not a pre-existing anchor in upstream).

The ``lca_runtime_chat_persistence`` module owns the persistence half;
``lca_run_driver`` is retired by the patch engine's reconcile in PR-4.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"
_LCA_GATEWAY_DIR = f"{_UI_TRANSPORTS}/lcaGateway"

# New TS files copied verbatim from sibling sources under lcaGateway/.
_NEW_FILES = (
    "connect.ts",
    "execute.ts",
    "reconnect.ts",
    "event_handler.ts",
    "event_router.ts",
    "client.ts",
    "interrupt.ts",
    "types.ts",
)


# Source modifications: each entry is (lobehub-ui relative path,
# marker string, insertion text). The marker is appended (idempotent)
# so the patch is a no-op on re-apply. Insertions are minimal — they
# declare the LCA gateway mode at the relevant call site without
# taking runtime branches in this PR (the actual runtime dispatch is
# owned by the chat store, which the patch engine does not modify in
# PR-3).
_MODIFICATIONS: tuple[dict, ...] = (
    {
        "rel": "src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts",
        "marker": "/* LCA-P1: lcaGateway runtime mode */",
        "insert": (
            "/* LCA-P1: lcaGateway runtime mode */\n"
            "// LCA adds the lcaGateway transport as a sibling of `gateway`\n"
            "// and `client`. Resolution lives in the chat store; this\n"
            "// file is only annotated so the patch is idempotent on\n"
            "// re-apply. See lcaGateway/connect.ts.\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
        "marker": "/* LCA-P1: skip-via-http */",
        "insert": (
            "/* LCA-P1: skip-via-http */\n"
            "// LCA HIL skip: POST /lca-api/runs/{run_id}/answer with\n"
            "// {approval_id, payload, idempotency_key}. The LCA\n"
            "// gateway's RunPort.resume_approval is the canonical\n"
            "// resume path — see spec §5.3.2.\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
        "marker": "/* LCA-P1: cancel-via-http */",
        "insert": (
            "/* LCA-P1: cancel-via-http */\n"
            "// LCA HIL cancel: POST /lca-api/runs/{run_id}/cancel.\n"
            "// Same rationale as skip-via-http above.\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationLifecycle.ts",
        "marker": "/* LCA-P1: lcaGateway send path */",
        "insert": (
            "/* LCA-P1: lcaGateway send path */\n"
            "// LCA's gateway mode is added as a sibling to `gateway`\n"
            "// and `client`; see lcaGateway/execute.ts for the entry\n"
            "// point and lcaGateway/connect.ts for the WS factory.\n"
        ),
    },
    {
        "rel": (
            "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/"
            "Intervention/customInteractionHandlers.ts"
        ),
        "marker": "/* LCA-P1: askUserQuestion handler */",
        "insert": (
            "/* LCA-P1: askUserQuestion handler */\n"
            "// LCA's HIL answer submission: POST /lca-api/runs/{run_id}/answer\n"
            "// with {approval_id, payload, idempotency_key}. See spec §5.3.2.\n"
        ),
    },
    {
        "rel": (
            f"{_UI_TRANSPORTS}/lcaToolRender/renderers/"
            "lobe-user-interaction/askUserQuestion.tsx"
        ),
        "marker": "/* LCA-P1: native askUserQuestion render */",
        "insert": (
            "/* LCA-P1: native askUserQuestion render */\n"
            "// Render using pluginState.lca.run_id, written at HIL\n"
            "// setup (see lcaChatRow.ts). The render itself is\n"
            "// LCA-native; the patch only annotates the file for\n"
            "// idempotency.\n"
        ),
    },
)


def _files() -> tuple[str, ...]:
    rels: list[str] = []
    for fname in _NEW_FILES:
        rels.append(f"{_LCA_GATEWAY_DIR}/{fname}")
    for mod in _MODIFICATIONS:
        rels.append(mod["rel"])
    return tuple(rels)


meta = PatchMeta(
    name="lca_runtime_agent_gateway",
    description=(
        "LCA front-end WS gateway client (lcaGateway/*) + 6 source "
        "modifications."
    ),
    files=_files(),
    risk="high",
    category="runtime",
    depends_on=("lca_runtime_chat_persistence",),
    why=(
        "P1 transport switchover: front-end uses the native "
        "AgentStreamClient against the LCA gateway. The new "
        "lcaGateway/ directory re-exports the native gateway/* code, "
        "with the URL pointed at the LCA gateway. The 6 source "
        "modifications add markers so the patch is idempotent on "
        "re-apply."
    ),
    technical_detail=(
        "All 8 new TS files are copied from sibling .ts source files. "
        "The 6 modifications use unique `/* LCA-P1: <purpose> */` "
        "markers that this module appends on first apply; re-apply is "
        "a no-op for markers already present."
    ),
    verify_file=f"{_LCA_GATEWAY_DIR}/connect.ts",
    verify_marker="export function lcaConnectToGateway",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. Copy new files.
    for fname in _NEW_FILES:
        rel = f"{_LCA_GATEWAY_DIR}/{fname}"
        src = _HERE / "lcaGateway" / fname
        if not src.is_file():
            raise SystemExit(f"missing patch source: {src}")
        if ctx.write_if_changed(rel, src.read_text(encoding="utf-8")):
            changed = True

    # 2. Apply modifications (idempotent markers).
    for mod in _MODIFICATIONS:
        rel = mod["rel"]
        marker = mod["marker"]
        try:
            text = ctx.read(rel)
        except FileNotFoundError:
            # lcaChatRow / askUserQuestion are owned by lca_runtime_chat_persistence;
            # if that patch was not applied first, skip rather than fail.
            continue
        if marker in text:
            continue
        # Append the marker block at end-of-file. Markers are unique
        # strings, not anchors — appending keeps the original file
        # structure intact.
        ctx.write(rel, text + "\n" + mod["insert"])
        changed = True
    return changed
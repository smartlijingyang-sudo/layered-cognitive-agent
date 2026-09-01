"""Patch: copy Journal projector TS; hook executeClientAgent.

Implementation lives in the sibling .ts files. This module only copies
them, generates lcaWire.ts from the WIRE table at
``lca.plugins.transport.webserver.handlers.runs.wire``, and shorts the
LobeHub AgentRuntime entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta
from lca.plugins.transport.webserver.handlers.runs.wire import WIRE

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"

meta = PatchMeta(
    name="lca_run_driver",
    description="Project Journal SSE; LCA owns the loop",
    files=(
        f"{_UI_TRANSPORTS}/LcaRunDriver.ts",
        f"{_UI_TRANSPORTS}/LcaRunDriver.test.ts",
        f"{_UI_TRANSPORTS}/lcaChatRow.ts",
        f"{_UI_TRANSPORTS}/lcaFinishChat.ts",
        f"{_UI_TRANSPORTS}/lcaJournal.ts",
        f"{_UI_TRANSPORTS}/lcaError.ts",
        f"{_UI_TRANSPORTS}/lcaPersist.ts",
        f"{_UI_TRANSPORTS}/lcaArtifacts.ts",
        f"{_UI_TRANSPORTS}/lcaWire.ts",
        "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
    ),
    risk="high",
    category="runtime",
    depends_on=(),
    why="LobeHub AgentRuntime owns a client tool loop; LCA already ran the loop on the server",
    technical_detail=(
        "executeClientAgent enters runLcaJournal then finishLcaChat. "
        "TS sources are copied; lcaWire.ts is generated from WIRE."
    ),
    verify_file="src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
    verify_marker="/* LCA: every chat is a Run */",
)


def render_wire_ts(wire: Mapping[str, tuple[str, str]]) -> str:
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


_STALE = (
    "src/store/chat/agents/transports/JournalTransport.ts",
    "src/store/chat/agents/transports/LcaResolvedToolTransport.ts",
    "src/store/chat/agents/transports/AgentTimelineTransport.ts",
)

_NEW_MARKER = "/* LCA: every chat is a Run */"

_IMPORT_NEEDLE = (
    "import { createClientRuntimeExecutors } from "
    "'@/store/chat/agents/transports/createClientRuntimeExecutors';\n"
)
_IMPORT_INSERT = (
    _IMPORT_NEEDLE
    + "import { runLcaJournal } from '@/store/chat/agents/transports/LcaRunDriver';\n"
    + "import { finishLcaChat } from '@/store/chat/agents/transports/lcaFinishChat';\n"
)

_IMPORT_NEEDLE_DQ = (
    "import { createClientRuntimeExecutors } from "
    '"@/store/chat/agents/transports/createClientRuntimeExecutors";\n'
)
_IMPORT_INSERT_DQ = (
    _IMPORT_NEEDLE_DQ
    + 'import { runLcaJournal } from "@/store/chat/agents/transports/LcaRunDriver";\n'
    + 'import { finishLcaChat } from "@/store/chat/agents/transports/lcaFinishChat";\n'
)

_RUN_BLOCK = """    /* LCA: every chat is a Run */
    const lcaModel = model === 'team' || model === 'auto' ? model : 'solo';
    if (lcaModel === 'solo' || lcaModel === 'team' || lcaModel === 'auto') {
      const projected = await runLcaJournal(this.#get, {
        messages,
        model: lcaModel,
        operationId,
        parentMessageId,
        reuseAssistantId: params.skipCreateFirstMessage ? params.parentMessageId : undefined,
        userMessageId: params.userMessageId,
      });
      await finishLcaChat(this.#get, {
        context,
        operationId,
        parentMessageId,
        parentMessageType,
        projected,
        scope,
      });
      return { model: lcaModel, provider: 'openai' };
    }
"""


def apply(ctx: PatchContext) -> bool:
    changed = False
    for name in (
        "LcaRunDriver.ts",
        "LcaRunDriver.test.ts",
        "lcaChatRow.ts",
        "lcaFinishChat.ts",
        "lcaJournal.ts",
        "lcaError.ts",
        "lcaPersist.ts",
        "lcaArtifacts.ts",
    ):
        if ctx.write_if_changed(
            f"{_UI_TRANSPORTS}/{name}", (_HERE / name).read_text(encoding="utf-8")
        ):
            changed = True
    if ctx.write_if_changed(f"{_UI_TRANSPORTS}/lcaWire.ts", render_wire_ts(WIRE)):
        changed = True

    executor = "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts"
    text = ctx.read(executor)
    if "finishLcaChat" not in text:
        if "import { runLcaJournal }" in text and "lcaFinishChat" not in text:
            text = text.replace(
                "import { runLcaJournal } from '@/store/chat/agents/transports/LcaRunDriver';\n",
                "import { runLcaJournal } from '@/store/chat/agents/transports/LcaRunDriver';\n"
                "import { finishLcaChat } from '@/store/chat/agents/transports/lcaFinishChat';\n",
                1,
            )
        elif _IMPORT_NEEDLE in text:
            text = text.replace(_IMPORT_NEEDLE, _IMPORT_INSERT, 1)
        elif _IMPORT_NEEDLE_DQ in text:
            text = text.replace(_IMPORT_NEEDLE_DQ, _IMPORT_INSERT_DQ, 1)
        else:
            raise SystemExit("[lca_run_driver] import anchor not found")

        if _NEW_MARKER in text:
            start = text.index(_NEW_MARKER)
            after = text.find("const modelRuntimeConfig", start)
            if after < 0:
                raise SystemExit("[lca_run_driver] modelRuntimeConfig after LCA block not found")
            text = text[:start] + _RUN_BLOCK + "\n" + text[after:]
        else:
            anchor = (
                "    const { agentConfig: agentConfigData } = agentConfig;\n"
                "    const model = agentConfigData.model;\n"
                "    const provider = agentConfigData.provider;\n"
            )
            if anchor not in text:
                raise SystemExit("[lca_run_driver] model/provider anchor not found")
            text = text.replace(anchor, anchor + "\n" + _RUN_BLOCK, 1)
        ctx.write(executor, text)
        changed = True

    for rel in _STALE:
        path = ctx.path(rel)
        if path.is_file():
            path.unlink()
            changed = True
    return changed

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
        f"{_UI_TRANSPORTS}/lcaChatRow.ts",
        f"{_UI_TRANSPORTS}/lcaFinishChat.ts",
        f"{_UI_TRANSPORTS}/lcaJournal.ts",
        f"{_UI_TRANSPORTS}/lcaError.ts",
        f"{_UI_TRANSPORTS}/lcaPersist.ts",
        f"{_UI_TRANSPORTS}/lcaArtifacts.ts",
        f"{_UI_TRANSPORTS}/lcaWire.ts",
        "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
        "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts",
        "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/index.tsx",
        "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
    ),
    risk="high",
    category="runtime",
    depends_on=(),
    why="LobeHub AgentRuntime owns a client tool loop; LCA already ran the loop on the server",
    technical_detail=(
        "executeClientAgent enters runLcaJournal then finishLcaChat. "
        "TS sources are copied; lcaWire.ts is generated from WIRE. "
        "askUserQuestion reuses native lobe-user-interaction Inspector/Intervention/Render; "
        "LCA resume is wired via customInteractionHandlers."
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

    # askUserQuestion: 复用原生 lobe-user-interaction 包的 Inspector + Intervention + Render。
    # LCA resume 路径由 customInteractionHandlers 的 handleLcaAskUserSubmit 处理。
    # 不再拷贝自定义 renderer。

    # customInteractionHandlers: 注入 LCA askUserQuestion resume handler。
    handlers_path = (
        "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/"
        "customInteractionHandlers.ts"
    )
    handlers_text = ctx.read(handlers_path)
    if "handleLcaAskUserSubmit" not in handlers_text:
        # Add import for conversation store + LCA token.
        import_anchor = "import { topicService } from '@/services/topic';"
        if import_anchor not in handlers_text:
            raise SystemExit("[lca_run_driver] customInteractionHandlers import anchor not found")
        handlers_text = handlers_text.replace(
            import_anchor,
            import_anchor
            + "\nimport { dataSelectors, useConversationStore } from '@/features/Conversation/store';\n"
            + "\nconst LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';",
            1,
        )

        # Add messageId to CustomInteractionContext.
        ctx_anchor = "interface CustomInteractionContext {\n  apiName?: string;"
        if ctx_anchor not in handlers_text:
            raise SystemExit("[lca_run_driver] CustomInteractionContext anchor not found")
        handlers_text = handlers_text.replace(
            ctx_anchor,
            "interface CustomInteractionContext {\n  apiName?: string;\n  messageId?: string;",
            1,
        )

        # Add skipResume to SubmitToolInteractionOptions.
        opts_anchor = "interface SubmitToolInteractionOptions {\n  createUserMessage?: boolean;"
        if opts_anchor not in handlers_text:
            raise SystemExit("[lca_run_driver] SubmitToolInteractionOptions anchor not found")
        handlers_text = handlers_text.replace(
            opts_anchor,
            "interface SubmitToolInteractionOptions {\n  createUserMessage?: boolean;\n  skipResume?: boolean;",
            1,
        )

        # Replace the generic askUserQuestion handler with the LCA-aware one.
        old_handler = (
            "  {\n"
            "    handler: async (payload) => ({\n"
            "      options: { pluginState: { askUserAnswers: payload } },\n"
            "      payload,\n"
            "    }),\n"
            "    match: isAskUserQuestionCall,\n"
            "  },"
        )
        new_handler = (
            "  {\n"
            "    handler: handleLcaAskUserSubmit,\n"
            "    match: isAskUserQuestionCall,\n"
            "  },"
        )
        if old_handler not in handlers_text:
            raise SystemExit("[lca_run_driver] askUserQuestion handler anchor not found")
        handlers_text = handlers_text.replace(old_handler, new_handler, 1)

        # Insert the handleLcaAskUserSubmit function before customInteractionSubmitHandlers.
        lca_handler_fn = '''
/**
 * LCA askUserQuestion resume: POST the answer to the LCA gateway and store
 * structured answers in pluginState. The LCA run resumes on the same live
 * stream that LcaRunDriver keeps consuming.
 */
const handleLcaAskUserSubmit: CustomInteractionSubmitHandler = async (payload, context) => {
  const messageId = context?.messageId;
  if (!messageId)
    return {
      options: { createUserMessage: false, pluginState: { askUserAnswers: payload }, skipResume: true },
      payload,
    };

  const msg = dataSelectors.getDbMessageById(messageId)(useConversationStore.getState());
  const lca = (msg?.pluginState as Record<string, unknown> | undefined)?.lca as
    | { run_id?: string; status?: string }
    | undefined;
  const runId = typeof lca?.run_id === 'string' ? lca.run_id : '';
  if (!runId)
    return {
      options: { createUserMessage: false, pluginState: { askUserAnswers: payload }, skipResume: true },
      payload,
    };

  const FREEFORM_KEY = '__freeform__';
  const freeform = payload[FREEFORM_KEY];
  let answerText: string;
  if (typeof freeform === 'string' && freeform.trim()) {
    answerText = freeform.trim();
  } else {
    const lines: string[] = [];
    for (const [key, value] of Object.entries(payload)) {
      if (key === FREEFORM_KEY || value == null) continue;
      const text = Array.isArray(value) ? value.join(', ') : String(value);
      if (text) lines.push(`${key} ${text}`);
    }
    answerText = lines.length > 0 ? lines.join('\\n') : JSON.stringify(payload);
  }

  try {
    await fetch(`/lca-api/runs/${runId}/answer`, {
      body: JSON.stringify({
        approval_id: 'askUserQuestion',
        idempotency_key: `${runId}:${messageId}`,
        payload: answerText,
      }),
      headers: {
        Authorization: `Bearer ${LCA_TOKEN}`,
        'Content-Type': 'application/json',
      },
      method: 'POST',
    });
  } catch (error) {
    console.error('[LCA] askUserQuestion answer failed', error);
  }

  return {
    options: { createUserMessage: false, pluginState: { askUserAnswers: payload }, skipResume: true },
    payload,
  };
};

'''
        handlers_anchor = "const customInteractionSubmitHandlers: Array<{"
        if handlers_anchor not in handlers_text:
            raise SystemExit("[lca_run_driver] customInteractionSubmitHandlers anchor not found")
        handlers_text = handlers_text.replace(
            handlers_anchor, lca_handler_fn + handlers_anchor, 1
        )

        ctx.write(handlers_path, handlers_text)
        changed = True

    # Intervention/index.tsx: pass messageId to prepareCustomInteractionSubmit.
    intervention_path = (
        "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/index.tsx"
    )
    intervention_text = ctx.read(intervention_path)
    old_ctx = (
        "              {\n"
        "                apiName,\n"
        "                requestArgs: parsedArgs,\n"
        "                topicId,\n"
        "              },"
    )
    new_ctx = (
        "              {\n"
        "                apiName,\n"
        "                messageId: id,\n"
        "                requestArgs: parsedArgs,\n"
        "                topicId,\n"
        "              },"
    )
    if old_ctx in intervention_text:
        intervention_text = intervention_text.replace(old_ctx, new_ctx, 1)
        ctx.write(intervention_path, intervention_text)
        changed = True

    # conversationControl.ts: honour skipResume so LCA askUserQuestion doesn't
    # double-resume (the LCA run is already resumed by POST /runs/<id>/answer).
    control_path = "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts"
    control_text = ctx.read(control_path)
    if "skipResume" not in control_text:
        # Add skipResume to the options type.
        type_anchor = "      toolResultContent?: string;\n    },\n  ): Promise<void> => {"
        if type_anchor not in control_text:
            raise SystemExit("[lca_run_driver] conversationControl type anchor not found")
        control_text = control_text.replace(
            type_anchor,
            "      skipResume?: boolean;\n      toolResultContent?: string;\n    },\n  ): Promise<void> => {",
            1,
        )

        # Skip the resume step when skipResume is set (LCA already resumed).
        resume_anchor = (
            "    // NOTE: intentionally do NOT bail on Stop here. `intervention: approved`\n"
            "    // and the tool result are already persisted above; returning early would\n"
            "    // leave the submission recorded but never resumed — a stuck conversation.\n"
            "    // Same best-effort rationale as approveToolCalling: complete atomically and\n"
            "    // honor the next Stop normally."
        )
        if resume_anchor not in control_text:
            raise SystemExit("[lca_run_driver] conversationControl resume anchor not found")
        control_text = control_text.replace(
            resume_anchor,
            resume_anchor
            + "\n\n    // LCA: the run is already resumed by POST /runs/<id>/answer; skip the\n"
            + "    // client/gateway resume to avoid creating a duplicate run.\n"
            + "    if (options?.skipResume) {\n"
            + "      completeOperation(operationId);\n"
            + "      return;\n"
            + "    }",
            1,
        )
        ctx.write(control_path, control_text)
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

    # Register the LCA tool renderers (askUserQuestion question card etc.).
    # Upstream only calls registerBuiltinToolSurfaces(); without this the LCA
    # renderers never register and tool messages fall back to the accordion.
    tool_surfaces = "src/spa/initialize/toolSurfaces.ts"
    ts_text = ctx.read(tool_surfaces)
    if "ensureLcaToolRenderRegistered" not in ts_text:
        ts_anchor = (
            "      .then(({ registerBuiltinToolSurfaces }) => {\n"
            "        registerBuiltinToolSurfaces();\n"
            "      })"
        )
        ts_replacement = (
            "      .then(async ({ registerBuiltinToolSurfaces }) => {\n"
            "        registerBuiltinToolSurfaces();\n"
            "        /* LCA: register LCA tool renderers (question card etc.) */\n"
            "        const { ensureLcaToolRenderRegistered } = await import(\n"
            "          '@/store/chat/agents/transports/lcaToolRender/lca_tool_render_register'\n"
            "        );\n"
            "        ensureLcaToolRenderRegistered();\n"
            "      })"
        )
        if ts_anchor not in ts_text:
            raise SystemExit("[lca_run_driver] toolSurfaces anchor not found")
        ctx.write(tool_surfaces, ts_text.replace(ts_anchor, ts_replacement, 1))
        changed = True

    for rel in _STALE:
        path = ctx.path(rel)
        if path.is_file():
            path.unlink()
            changed = True
    return changed

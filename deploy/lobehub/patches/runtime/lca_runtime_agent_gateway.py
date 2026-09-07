"""Patch: front-end WS gateway client + lobehub-ui source modifications.

This module owns:
- 9 new TS files under ``src/store/chat/agents/transports/lcaGateway/``
- Source modifications migrated from the retired ``lca_run_driver`` patch:
  ``streamingExecutor.ts`` (gateway-only dispatch),
  ``customInteractionHandlers.ts``, ``intervention/index.tsx``,
  ``conversationControl.ts`` (HIL skip/cancel/resume),
  ``toolSurfaces.ts``, and ``agentDispatcher.ts`` (``isLcaGatewayMode``).

The ``lca_runtime_chat_persistence`` module owns the persistence half.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"
_LCA_GATEWAY_DIR = f"{_UI_TRANSPORTS}/lcaGateway"

_NEW_FILES = (
    "LcaAgentStreamClient.ts",
    "connect.ts",
    "execute.ts",
    "executeGatewayRun.ts",
    "reconnect.ts",
    "event_handler.ts",
    "event_router.ts",
    "client.ts",
    "interrupt.ts",
    "types.ts",
)

_NEW_MARKER = "/* LCA: every chat is a Run */"

_RUN_BLOCK = """    /* LCA: every chat is a Run */
    const lcaModel = model === 'team' || model === 'auto' ? model : 'solo';
    if (lcaModel === 'solo' || lcaModel === 'team' || lcaModel === 'auto') {
      const { isLcaGatewayMode } = await import(
        '@/store/chat/slices/agentRun/actions/dispatch/agentDispatcher'
      );
      if (isLcaGatewayMode()) {
        const { lcaExecuteGatewayRun } = await import(
          '@/store/chat/agents/transports/lcaGateway/executeGatewayRun'
        );
        return await lcaExecuteGatewayRun(this.#get, {
          context,
          messages,
          model: lcaModel,
          operationId,
          parentMessageId,
          parentMessageType,
          scope,
          params,
        });
      }
      // LCA: hard fail. Per ADR-0200 §1 chat is exclusively routed through
      // the LCA agent-gateway WS (LcaAgentStreamClient → /v1/runs/<id>/ws).
      // Falling back to GeneralChatAgent would expose provider selection
      // (e.g. /webapi/chat/qwen) which is exactly the bug this guard
      // exists to prevent. The env must be wired before the front-end is
      // shipped; see NEXT_PUBLIC_LCA_GATEWAY_URL in deploy/lobehub/.env.lca.
      throw new Error(
        '[LCA] chat attempted without LCA gateway configured. Set NEXT_PUBLIC_LCA_GATEWAY_URL.'
      );
    }
"""

_IS_LCA_GATEWAY_MODE = (
    "/* LCA-P1: lcaGateway runtime mode */\n"
    "// ``LCA_GATEWAY_WS_URL`` is the build-time literal baked into\n"
    "// ``lcaGateway/client.ts`` by the LCA patch engine (see that\n"
    "// file's LCA_PATCH_BEGIN/END markers). Reading it here avoids the\n"
    "// ``process.env.NEXT_PUBLIC_*`` reference that Vite dev mode does\n"
    "// not expose to the browser bundle.\n"
    "import { LCA_GATEWAY_WS_URL as LCA_GATEWAY_URL } from "
    "'@/store/chat/agents/transports/lcaGateway/client';\n"
    "export function isLcaGatewayMode(_agentId?: string): boolean {\n"
    "  try {\n"
    "    return !!(LCA_GATEWAY_URL && LCA_GATEWAY_URL.length > 0);\n"
    "  } catch {\n"
    "    return false;\n"
    "  }\n"
    "}\n"
)

_MARKER_INSERTIONS: tuple[dict[str, str], ...] = (
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


def _modified_files() -> tuple[str, ...]:
    rels = [
        "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
        (
            "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/"
            "Intervention/customInteractionHandlers.ts"
        ),
        (
            "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/"
            "Intervention/index.tsx"
        ),
        "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
        "src/spa/initialize/toolSurfaces.ts",
        "src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts",
    ]
    for entry in _MARKER_INSERTIONS:
        rels.append(entry["rel"])
    for fname in _NEW_FILES:
        rels.append(f"{_LCA_GATEWAY_DIR}/{fname}")
    return tuple(rels)


meta = PatchMeta(
    name="lca_runtime_agent_gateway",
    description=(
        "LCA front-end WS gateway client (lcaGateway/*) + lobehub-ui "
        "source modifications for gateway dispatch and HIL."
    ),
    files=_modified_files(),
    risk="high",
    category="runtime",
    depends_on=("lca_runtime_chat_persistence",),
    why=(
        "P1 transport switchover: front-end uses the native "
        "AgentStreamClient against the LCA gateway WebSocket."
    ),
    technical_detail=(
        "Copies lcaGateway/* TS files and patches streamingExecutor, "
        "customInteractionHandlers, intervention, conversationControl, "
        "toolSurfaces, and agentDispatcher."
    ),
    verify_file=f"{_LCA_GATEWAY_DIR}/connect.ts",
    verify_marker="export function lcaConnectToGateway",
)


def _append_marker(ctx: PatchContext, rel: str, marker: str, insert: str) -> bool:
    try:
        text = ctx.read(rel)
    except FileNotFoundError:
        return False
    if marker in text:
        return False
    ctx.write(rel, text + "\n" + insert)
    return True


def _patch_streaming_executor(ctx: PatchContext) -> bool:
    executor = "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts"
    text = ctx.read(executor)
    if _NEW_MARKER in text:
        return False

    anchor = (
        "    const { agentConfig: agentConfigData } = agentConfig;\n"
        "    const model = agentConfigData.model;\n"
        "    const provider = agentConfigData.provider;\n"
    )
    if anchor not in text:
        raise SystemExit("[lca_runtime_agent_gateway] model/provider anchor not found")
    text = text.replace(anchor, anchor + "\n" + _RUN_BLOCK, 1)
    ctx.write(executor, text)
    return True


def _patch_agent_dispatcher(ctx: PatchContext) -> bool:
    rel = "src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts"
    text = ctx.read(rel)
    if "export function isLcaGatewayMode" in text:
        return False
    ctx.write(rel, text + "\n" + _IS_LCA_GATEWAY_MODE)
    return True


def _patch_custom_interaction_handlers(ctx: PatchContext) -> bool:
    handlers_path = (
        "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/"
        "customInteractionHandlers.ts"
    )
    handlers_text = ctx.read(handlers_path)
    changed = False

    broken_read = (
        "  // Read pluginState.lca from the conversation store to get the run_id.\n"
        "  const msg = dataSelectors.getDbMessageById(messageId)(useConversationStore.getState());\n"
        "  const lca = (msg?.pluginState as Record<string, unknown> | undefined)?.lca as\n"
        "    | { run_id?: string; status?: string }\n"
        "    | undefined;\n"
        "  const runId = typeof lca?.run_id === 'string' ? lca.run_id : '';"
    )
    fixed_read = (
        "  const reqArgs = (context?.requestArgs ?? {}) as Record<string, unknown>;\n"
        "  const runId = typeof reqArgs.lca_run_id === 'string' ? reqArgs.lca_run_id : '';"
    )
    if broken_read in handlers_text:
        handlers_text = handlers_text.replace(broken_read, fixed_read, 1)
        handlers_text = handlers_text.replace(
            "import { dataSelectors, useConversationStore } from '@/features/Conversation/store';\n",
            "",
            1,
        )
        ctx.write(handlers_path, handlers_text)
        changed = True
        handlers_text = ctx.read(handlers_path)

    if "handleLcaAskUserSubmit" in handlers_text:
        return changed

    import_anchor = "import { topicService } from '@/services/topic';"
    if import_anchor not in handlers_text:
        raise SystemExit("[lca_runtime_agent_gateway] customInteractionHandlers import anchor not found")
    handlers_text = handlers_text.replace(
        import_anchor,
        import_anchor
        + "\nimport { dataSelectors, useConversationStore } from '@/features/Conversation/store';\n"
        + "\nconst LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';",
        1,
    )

    ctx_anchor = "interface CustomInteractionContext {\n  apiName?: string;"
    if ctx_anchor not in handlers_text:
        raise SystemExit("[lca_runtime_agent_gateway] CustomInteractionContext anchor not found")
    handlers_text = handlers_text.replace(
        ctx_anchor,
        "interface CustomInteractionContext {\n  apiName?: string;\n  messageId?: string;",
        1,
    )

    opts_anchor = "interface SubmitToolInteractionOptions {\n  createUserMessage?: boolean;"
    if opts_anchor not in handlers_text:
        raise SystemExit("[lca_runtime_agent_gateway] SubmitToolInteractionOptions anchor not found")
    handlers_text = handlers_text.replace(
        opts_anchor,
        "interface SubmitToolInteractionOptions {\n  createUserMessage?: boolean;\n  skipResume?: boolean;",
        1,
    )

    old_handler = (
        "  {\n"
        "    handler: async (payload) => ({\n"
        "      options: { pluginState: { askUserAnswers: payload } },\n"
        "      payload,\n"
        "    }),\n"
        "    match: isAskUserQuestionCall,\n"
        "  },"
    )
    new_handler = "  {\n    handler: handleLcaAskUserSubmit,\n    match: isAskUserQuestionCall,\n  },"
    if old_handler not in handlers_text:
        raise SystemExit("[lca_runtime_agent_gateway] askUserQuestion handler anchor not found")
    handlers_text = handlers_text.replace(old_handler, new_handler, 1)

    lca_handler_fn = """
/**
 * LCA askUserQuestion resume: POST the answer to the LCA gateway and store
 * structured answers in pluginState. The LCA run resumes on the gateway WS.
 */
const handleLcaAskUserSubmit: CustomInteractionSubmitHandler = async (payload, context) => {
  const messageId = context?.messageId;
  if (!messageId)
    return {
      options: { createUserMessage: false, pluginState: { askUserAnswers: payload }, skipResume: true },
      payload,
    };

  const reqArgs = (context?.requestArgs ?? {}) as Record<string, unknown>;
  const runId = typeof reqArgs.lca_run_id === 'string' ? reqArgs.lca_run_id : '';
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

"""
    handlers_anchor = "const customInteractionSubmitHandlers: Array<{"
    if handlers_anchor not in handlers_text:
        raise SystemExit("[lca_runtime_agent_gateway] customInteractionSubmitHandlers anchor not found")
    handlers_text = handlers_text.replace(handlers_anchor, lca_handler_fn + handlers_anchor, 1)
    ctx.write(handlers_path, handlers_text)
    return True


def _patch_intervention_index(ctx: PatchContext) -> bool:
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
    if old_ctx not in intervention_text:
        return False
    ctx.write(intervention_path, intervention_text.replace(old_ctx, new_ctx, 1))
    return True


def _patch_conversation_control(ctx: PatchContext) -> bool:
    control_path = "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts"
    control_text = ctx.read(control_path)
    changed = False

    if "skipResume" not in control_text:
        type_anchor = "      toolResultContent?: string;\n    },\n  ): Promise<void> => {"
        if type_anchor not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl type anchor not found")
        control_text = control_text.replace(
            type_anchor,
            "      skipResume?: boolean;\n      toolResultContent?: string;\n    },\n  ): Promise<void> => {",
            1,
        )
        resume_anchor = (
            "    // NOTE: intentionally do NOT bail on Stop here. `intervention: approved`\n"
            "    // and the tool result are already persisted above; returning early would\n"
            "    // leave the submission recorded but never resumed — a stuck conversation.\n"
            "    // Same best-effort rationale as approveToolCalling: complete atomically and\n"
            "    // honor the next Stop normally."
        )
        if resume_anchor not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl resume anchor not found")
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
        control_text = ctx.read(control_path)

    if "LCA askUserQuestion skip answer" not in control_text:
        if "const LCA_TOKEN" not in control_text:
            lifecycle_import_anchor = (
                "import { buildRunLifecycle } from '../lifecycle/buildRunLifecycle';"
            )
            if lifecycle_import_anchor not in control_text:
                raise SystemExit("[lca_runtime_agent_gateway] conversationControl token anchor not found")
            control_text = control_text.replace(
                lifecycle_import_anchor,
                lifecycle_import_anchor
                + "\n\nconst LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';",
                1,
            )

        skip_anchor = (
            "    if (this.#wasInterimOpStopped(operationId)) return;\n"
            "\n"
            "    // 2. Create a user message indicating the skip"
        )
        if skip_anchor not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl skip anchor not found")
        skip_block = (
            "    if (this.#wasInterimOpStopped(operationId)) return;\n"
            "\n"
            "    // LCA askUserQuestion skip answer: the run is paused server-side at\n"
            "    // waiting_input. Ship the skip as an answer so it resumes there; do NOT\n"
            "    // start a fresh executeClientAgent run.\n"
            "    const lcaSkipState = (toolMessage.pluginState as\n"
            "      | Record<string, unknown>\n"
            "      | undefined)?.lca as { run_id?: string } | undefined;\n"
            "    const lcaSkipRunId = typeof lcaSkipState?.run_id === 'string' ? lcaSkipState.run_id : '';\n"
            "    if (lcaSkipRunId) {\n"
            "      try {\n"
            "        await fetch(`/lca-api/runs/${lcaSkipRunId}/answer`, {\n"
            "          body: JSON.stringify({\n"
            "            approval_id: 'askUserQuestion',\n"
            "            idempotency_key: `${lcaSkipRunId}:${toolMessageId}:skip`,\n"
            "            payload: toolContent,\n"
            "          }),\n"
            "          headers: {\n"
            "            Authorization: `Bearer ${LCA_TOKEN}`,\n"
            "            'Content-Type': 'application/json',\n"
            "          },\n"
            "          method: 'POST',\n"
            "        });\n"
            "      } catch (error) {\n"
            "        console.error('[LCA] askUserQuestion skip answer failed', error);\n"
            "      }\n"
            "      completeOperation(operationId);\n"
            "      return;\n"
            "    }\n"
            "\n"
            "    // 2. Create a user message indicating the skip"
        )
        control_text = control_text.replace(skip_anchor, skip_block, 1)
        ctx.write(control_path, control_text)
        changed = True
        control_text = ctx.read(control_path)

    if "LCA askUserQuestion cancel" not in control_text:
        if "const LCA_TOKEN" not in control_text:
            lifecycle_import_anchor = (
                "import { buildRunLifecycle } from '../lifecycle/buildRunLifecycle';"
            )
            if lifecycle_import_anchor not in control_text:
                raise SystemExit("[lca_runtime_agent_gateway] conversationControl token anchor not found")
            control_text = control_text.replace(
                lifecycle_import_anchor,
                lifecycle_import_anchor
                + "\n\nconst LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';",
                1,
            )

        cancel_anchor = "    const toolContent = 'User cancelled this interaction.';\n"
        if cancel_anchor not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl cancel anchor not found")
        cancel_block = (
            "    const toolContent = 'User cancelled this interaction.';\n"
            "\n"
            "    // LCA askUserQuestion cancel: the run is paused server-side at\n"
            "    // waiting_input. Forward the cancel to the LCA gateway so the run\n"
            "    // leaves waiting_input; otherwise it stays stuck waiting for an\n"
            "    // answer that will never arrive.\n"
            "    const lcaCancelState = (toolMessage.pluginState as\n"
            "      | Record<string, unknown>\n"
            "      | undefined)?.lca as { run_id?: string } | undefined;\n"
            "    const lcaCancelRunId = typeof lcaCancelState?.run_id === 'string' ? lcaCancelState.run_id : '';\n"
            "    if (lcaCancelRunId) {\n"
            "      try {\n"
            "        await fetch(`/lca-api/runs/${lcaCancelRunId}/cancel`, {\n"
            "          headers: { Authorization: `Bearer ${LCA_TOKEN}` },\n"
            "          method: 'POST',\n"
            "        });\n"
            "      } catch (error) {\n"
            "        console.error('[LCA] askUserQuestion cancel failed', error);\n"
            "      }\n"
            "    }\n"
        )
        control_text = control_text.replace(cancel_anchor, cancel_block, 1)
        ctx.write(control_path, control_text)
        changed = True

    return changed


def _patch_tool_surfaces(ctx: PatchContext) -> bool:
    tool_surfaces = "src/spa/initialize/toolSurfaces.ts"
    ts_text = ctx.read(tool_surfaces)
    if "ensureLcaToolRenderRegistered" in ts_text:
        return False
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
        raise SystemExit("[lca_runtime_agent_gateway] toolSurfaces anchor not found")
    ctx.write(tool_surfaces, ts_text.replace(ts_anchor, ts_replacement, 1))
    return True


def apply(ctx: PatchContext) -> bool:
    import os

    changed = False

    # Inject the build-time LCA gateway WS URL into lcaGateway/client.ts
    # so the browser bundle carries the URL as a literal (the lobehub-spa
    # Vite dev server does NOT expose ``process.env.NEXT_PUBLIC_*`` to the
    # client bundle by default — only ``VITE_*``). The placeholder in the
    # patch source carries an obvious sentinel value
    # (``ws://lca-gateway-unset:0000``) so a forgotten inject is loud.
    gateway_http = os.environ.get("LCA_GATEWAY_PUBLIC_URL", "").rstrip("/")
    gateway_ws = (
        gateway_http.replace("http://", "ws://", 1).replace(
            "https://", "wss://", 1
        )
        if gateway_http
        else "ws://lca-gateway-unset:0000"
    )

    for fname in _NEW_FILES:
        rel = f"{_LCA_GATEWAY_DIR}/{fname}"
        src = _HERE / "lcaGateway" / fname
        if not src.is_file():
            raise SystemExit(f"missing patch source: {src}")
        text = src.read_text(encoding="utf-8")
        if fname == "client.ts":
            # Replace the placeholder literal with the env-derived URL.
            text = text.replace(
                "'__LCA_GATEWAY_WS_URL__:ws://lca-gateway-unset:0000__'",
                f"'{gateway_ws}'",
            )
        if ctx.write_if_changed(rel, text):
            changed = True

    for patch_fn in (
        _patch_streaming_executor,
        _patch_agent_dispatcher,
        _patch_custom_interaction_handlers,
        _patch_intervention_index,
        _patch_conversation_control,
        _patch_tool_surfaces,
    ):
        if patch_fn(ctx):
            changed = True

    for entry in _MARKER_INSERTIONS:
        if _append_marker(ctx, entry["rel"], entry["marker"], entry["insert"]):
            changed = True

    return changed

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
        "src/store/chat/slices/agentRun/actions/transports/gateway/gateway.ts",
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


def _patch_gateway_create_client(ctx: PatchContext) -> bool:
    """Route connectToGateway through LcaAgentStreamClient when LCA mode is on."""
    rel = "src/store/chat/slices/agentRun/actions/transports/gateway/gateway.ts"
    text = ctx.read(rel)
    marker = "/* LCA-P1: LcaAgentStreamClient factory */"
    if marker in text:
        return False

    import_anchor = "import { messageMapKey } from '@/store/chat/utils/messageMapKey';"
    if import_anchor not in text:
        raise SystemExit("[lca_runtime_agent_gateway] gateway.ts import anchor not found")
    text = text.replace(
        import_anchor,
        import_anchor
        + "\nimport { lcaConnectToGateway } from "
        + "'@/store/chat/agents/transports/lcaGateway/connect';"
        + "\nimport { isLcaGatewayMode } from "
        + "'@/store/chat/slices/agentRun/actions/dispatch/agentDispatcher';",
        1,
    )

    old = (
        "  /** Overridable factory for testing */\n"
        "  createClient: (options: AgentStreamClientOptions) => GatewayConnection['client'] = (options) =>\n"
        "    new AgentStreamClient(options);"
    )
    new = (
        "  /** Overridable factory for testing */\n"
        "  /* LCA-P1: LcaAgentStreamClient factory */\n"
        "  createClient: (options: AgentStreamClientOptions) => GatewayConnection['client'] = (options) => {\n"
        "    if (isLcaGatewayMode()) {\n"
        "      return lcaConnectToGateway({\n"
        "        operationId: options.operationId,\n"
        "        resumeOnConnect: options.resumeOnConnect,\n"
        "        token: options.token,\n"
        "      });\n"
        "    }\n"
        "    return new AgentStreamClient(options);\n"
        "  };"
    )
    if old not in text:
        raise SystemExit("[lca_runtime_agent_gateway] gateway createClient anchor not found")
    ctx.write(rel, text.replace(old, new, 1))
    return True


def _patch_gateway_lca_routing(ctx: PatchContext) -> bool:
    """Keep LCA chat off execAgentTask; wire reconnect token for run_* WS."""
    rel = "src/store/chat/slices/agentRun/actions/transports/gateway/gateway.ts"
    text = ctx.read(rel)
    marker = "/* LCA-P1: disable native gateway routing when LCA WS is active */"
    if marker in text:
        return False

    import_anchor = "import { isLcaGatewayMode } from '@/store/chat/slices/agentRun/actions/dispatch/agentDispatcher';"
    if import_anchor not in text:
        raise SystemExit("[lca_runtime_agent_gateway] gateway isLcaGatewayMode import missing")
    text = text.replace(
        import_anchor,
        "import { getLcaGatewayUrl } from '@/store/chat/agents/transports/lcaGateway/client';\n"
        + import_anchor,
        1,
    )

    old_enabled = (
        "  isGatewayModeEnabled = (agentId?: string): boolean => {\n"
        "    const serverConfig = window.global_serverConfigStore?.getState()?.serverConfig;"
    )
    new_enabled = (
        "  isGatewayModeEnabled = (agentId?: string): boolean => {\n"
        "    /* LCA-P1: disable native gateway routing when LCA WS is active */\n"
        "    // LCA chat: POST /runs + LCA WS via executeClientAgent→lcaExecuteGatewayRun.\n"
        "    if (isLcaGatewayMode()) return false;\n"
        "\n"
        "    const serverConfig = window.global_serverConfigStore?.getState()?.serverConfig;"
    )
    if old_enabled not in text:
        raise SystemExit("[lca_runtime_agent_gateway] isGatewayModeEnabled anchor not found")
    text = text.replace(old_enabled, new_enabled, 1)

    old_reconnect_sig = (
        "  reconnectToGatewayOperation = async (params: {\n"
        "    assistantMessageId: string;\n"
        "    operationId: string;\n"
        "    scope?: string;\n"
        "    threadId?: string | null;\n"
        "    topicId: string;\n"
        "  }): Promise<void> => {\n"
        "    const { assistantMessageId, operationId, topicId, scope, threadId } = params;\n"
        "\n"
        "    const agentGatewayUrl =\n"
        "      window.global_serverConfigStore?.getState()?.serverConfig?.agentGatewayUrl;\n"
        "    if (!agentGatewayUrl) return;"
    )
    new_reconnect_sig = (
        "  reconnectToGatewayOperation = async (params: {\n"
        "    assistantMessageId: string;\n"
        "    operationId: string;\n"
        "    scope?: string;\n"
        "    threadId?: string | null;\n"
        "    topicId: string;\n"
        "    token?: string;\n"
        "  }): Promise<void> => {\n"
        "    const { assistantMessageId, operationId, topicId, scope, threadId, token: suppliedToken } =\n"
        "      params;\n"
        "\n"
        "    const agentGatewayUrl = isLcaGatewayMode()\n"
        "      ? getLcaGatewayUrl()\n"
        "      : window.global_serverConfigStore?.getState()?.serverConfig?.agentGatewayUrl;\n"
        "    if (!agentGatewayUrl) return;"
    )
    if old_reconnect_sig not in text:
        raise SystemExit("[lca_runtime_agent_gateway] reconnectToGatewayOperation sig anchor not found")
    text = text.replace(old_reconnect_sig, new_reconnect_sig, 1)

    old_token = (
        "    // Get a fresh JWT token (original expired after 5 min). The server throws\n"
        "    // TRPCError NOT_FOUND when it has no running operation on this topic — our\n"
        "    // local marker is stale (e.g. an error run cleared the server marker but not\n"
        "    // the store). Clear it and bail silently so the reconnect SWR fetcher resolves\n"
        "    // and does not retry the 404 forever.\n"
        "    let token: string;\n"
        "    try {\n"
        "      ({ token } = await aiAgentService.refreshGatewayToken(topicId));\n"
        "    } catch (error) {\n"
        "      if (isTrpcErrorCode(error, 'NOT_FOUND')) {\n"
        "        this.clearLocalRunningOperation({ operationId, topicId });\n"
        "        return;\n"
        "      }\n"
        "      throw error;\n"
        "    }"
    )
    new_token = (
        "    // Mint or reuse JWT for WS auth (LCA: run_* + ws_token; native: tRPC).\n"
        "    let token: string;\n"
        "    if (isLcaGatewayMode()) {\n"
        "      if (suppliedToken && suppliedToken.length > 0) {\n"
        "        token = suppliedToken;\n"
        "      } else {\n"
        "        const { lcaRefreshWsToken } = await import(\n"
        "          '@/store/chat/agents/transports/lcaGateway/reconnect'\n"
        "        );\n"
        "        try {\n"
        "          token = await lcaRefreshWsToken(operationId, 'lca-local');\n"
        "        } catch {\n"
        "          this.clearLocalRunningOperation({ operationId, topicId });\n"
        "          return;\n"
        "        }\n"
        "      }\n"
        "    } else {\n"
        "      try {\n"
        "        ({ token } = await aiAgentService.refreshGatewayToken(topicId));\n"
        "      } catch (error) {\n"
        "        if (isTrpcErrorCode(error, 'NOT_FOUND')) {\n"
        "          this.clearLocalRunningOperation({ operationId, topicId });\n"
        "          return;\n"
        "        }\n"
        "        throw error;\n"
        "      }\n"
        "    }"
    )
    if old_token not in text:
        raise SystemExit("[lca_runtime_agent_gateway] reconnect token anchor not found")
    text = text.replace(old_token, new_token, 1)

    old_cancel = (
        "    this.#get().onOperationCancel(gatewayOpId, async () => {\n"
        "      await aiAgentService\n"
        "        .interruptTask({ operationId })\n"
        "        .catch((err) => console.error('[Gateway] interruptTask failed:', err));\n"
        "    });\n"
        "\n"
        "    const eventHandler = createGatewayEventHandler(this.#get, {\n"
        "      assistantMessageId,\n"
        "      context,\n"
        "      // Server-side operation id — needed for tool_result dispatch back over\n"
        "      // the same WS that gatewayConnections is keyed on.\n"
        "      gatewayOperationId: operationId,\n"
        "      operationId: gatewayOpId,\n"
        "      runLifecycle: buildRunLifecycle(this.#get, {\n"
        "        context,\n"
        "        parentMessageId: assistantMessageId,\n"
        "        parentMessageType: 'assistant',\n"
        "        runId: gatewayOpId,\n"
        "        runScope: (context.scope === 'sub_agent' ? 'sub_agent' : 'top_level') as RunScope,\n"
        "        runtimeType: 'gateway',\n"
        "      }),\n"
        "    });\n"
        "\n"
        "    // Same demux as the initial-run path: a reconnected supervisor WS can also"
    )
    new_cancel = (
        "    this.#get().onOperationCancel(gatewayOpId, async () => {\n"
        "      if (isLcaGatewayMode()) {\n"
        "        const lcaToken = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';\n"
        "        await fetch(`/lca-api/runs/${operationId}/cancel`, {\n"
        "          headers: { Authorization: `Bearer ${lcaToken}` },\n"
        "          method: 'POST',\n"
        "        }).catch((err) => console.error('[LCA] cancel failed:', err));\n"
        "        return;\n"
        "      }\n"
        "      await aiAgentService\n"
        "        .interruptTask({ operationId })\n"
        "        .catch((err) => console.error('[Gateway] interruptTask failed:', err));\n"
        "    });\n"
        "\n"
        "    const eventHandler = createGatewayEventHandler(this.#get, {\n"
        "      assistantMessageId,\n"
        "      context,\n"
        "      // Server-side operation id — needed for tool_result dispatch back over\n"
        "      // the same WS that gatewayConnections is keyed on.\n"
        "      gatewayOperationId: operationId,\n"
        "      operationId: gatewayOpId,\n"
        "      runLifecycle: buildRunLifecycle(this.#get, {\n"
        "        context,\n"
        "        parentMessageId: assistantMessageId,\n"
        "        parentMessageType: 'assistant',\n"
        "        runId: gatewayOpId,\n"
        "        runScope: (context.scope === 'sub_agent' ? 'sub_agent' : 'top_level') as RunScope,\n"
        "        runtimeType: 'gateway',\n"
        "      }),\n"
        "    });\n"
        "\n"
        "    // Same demux as the initial-run path: a reconnected supervisor WS can also"
    )
    if old_cancel not in text:
        raise SystemExit("[lca_runtime_agent_gateway] reconnect cancel anchor not found")
    ctx.write(rel, text.replace(old_cancel, new_cancel, 1))
    return True


def _patch_gateway_event_handler_lca_stream(ctx: PatchContext) -> bool:
    """Keep in-memory streamed tools when LCA gateway skips hollow DB refetches."""
    rel = (
        "src/store/chat/slices/agentRun/actions/transports/gateway/"
        "gatewayEventHandler.ts"
    )
    text = ctx.read(rel)
    marker = "/* LCA-P1: mergeToolsCallingChunks */"
    if marker in text or "shouldSkipMidStreamMessageFetch" in text:
        return False

    old_skip = (
        "const shouldSkipMessageFetch = (\n"
        "  event: AgentStreamEvent,\n"
        "  runtimeType: 'gateway' | 'hetero',\n"
        "): boolean => runtimeType === 'hetero' && event.data?.skipMessageFetch === true;\n"
    )
    new_skip = (
        "const shouldSkipMessageFetch = (\n"
        "  event: AgentStreamEvent,\n"
        "  runtimeType: 'gateway' | 'hetero',\n"
        "): boolean => runtimeType === 'hetero' && event.data?.skipMessageFetch === true;\n"
        "\n"
        "/** LCA gateway streams tools/content in-memory; mid-run DB rows are hollow. */\n"
        "const shouldSkipMidStreamMessageFetch = (\n"
        "  event: AgentStreamEvent,\n"
        "  runtimeType: 'gateway' | 'hetero',\n"
        "  preserveStreamedContentOnTerminal?: boolean,\n"
        "): boolean =>\n"
        "  shouldSkipMessageFetch(event, runtimeType) || preserveStreamedContentOnTerminal === true;\n"
        "\n"
        "/* LCA-P1: mergeToolsCallingChunks */\n"
        "const mergeToolsCallingChunks = <T extends { id: string }>(\n"
        "  existing: readonly T[] | undefined,\n"
        "  incoming: readonly T[],\n"
        "): T[] => {\n"
        "  if (!existing?.length) return [...incoming];\n"
        "  const byId = new Map(existing.map((tool) => [tool.id, tool]));\n"
        "  for (const tool of incoming) {\n"
        "    byId.set(tool.id, { ...byId.get(tool.id), ...tool });\n"
        "  }\n"
        "  return Array.from(byId.values());\n"
        "};\n"
    )
    if old_skip not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler shouldSkipMessageFetch anchor not found"
        )
    text = text.replace(old_skip, new_skip, 1)

    old_tools = (
        "            const toolsCalling = preserveToolResultMessageIds(\n"
        "              data.toolsCalling as unknown[],\n"
        "              dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(get())?.tools,\n"
        "            ) as NonNullable<StreamChunkData['toolsCalling']>;\n"
        "\n"
        "            get().internal_dispatchMessage(\n"
    )
    new_tools = (
        "            const existingTools = dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(\n"
        "              get(),\n"
        "            )?.tools;\n"
        "            const preserved = preserveToolResultMessageIds(\n"
        "              data.toolsCalling as unknown[],\n"
        "              existingTools,\n"
        "            ) as NonNullable<StreamChunkData['toolsCalling']>;\n"
        "            /* LCA-P1: spine emits one tool per chunk — merge by id instead of replace */\n"
        "            const toolsCalling = params.preserveStreamedContentOnTerminal\n"
        "              ? (mergeToolsCallingChunks(\n"
        "                  existingTools as { id: string }[] | undefined,\n"
        "                  preserved,\n"
        "                ) as NonNullable<StreamChunkData['toolsCalling']>)\n"
        "              : preserved;\n"
        "\n"
        "            get().internal_dispatchMessage(\n"
    )
    if old_tools not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler tools_calling anchor not found"
        )
    text = text.replace(old_tools, new_tools, 1)

    old_tool_end = (
        "        enqueue(async () => {\n"
        "          const maybeRefresh = shouldSkipMessageFetch(event, runtimeType)\n"
        "            ? Promise.resolve()\n"
        "            : fetchAndReplaceMessages(get, context, { skipWorks: true }).catch(console.error);\n"
        "          const payload = unwrapToolPayload(data?.payload);\n"
    )
    new_tool_end = (
        "        enqueue(async () => {\n"
        "          /* LCA-P1: hollow DB rows clobber in-memory tools — refetch only on native path */\n"
        "          const skipToolEndFetch = shouldSkipMidStreamMessageFetch(\n"
        "            event,\n"
        "            runtimeType,\n"
        "            params.preserveStreamedContentOnTerminal,\n"
        "          );\n"
        "          const maybeRefresh = skipToolEndFetch\n"
        "            ? Promise.resolve()\n"
        "            : fetchAndReplaceMessages(get, context, { skipWorks: true }).catch(console.error);\n"
        "          const payload = unwrapToolPayload(data?.payload);\n"
    )
    if old_tool_end not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler tool_end anchor not found"
        )
    text = text.replace(old_tool_end, new_tool_end, 1)

    old_step = (
        "            if (!shouldSkipMessageFetch(event, runtimeType)) {\n"
        "              await fetchAndReplaceMessages(get, context, { skipWorks: true }).catch(console.error);\n"
        "            }\n"
        "          });\n"
        "        }\n"
        "        break;\n"
        "      }\n"
        "\n"
        "      case 'agent_runtime_end': {\n"
    )
    new_step = (
        "            if (\n"
        "              !shouldSkipMidStreamMessageFetch(\n"
        "                event,\n"
        "                runtimeType,\n"
        "                params.preserveStreamedContentOnTerminal,\n"
        "              )\n"
        "            ) {\n"
        "              await fetchAndReplaceMessages(get, context, { skipWorks: true }).catch(console.error);\n"
        "            }\n"
        "          });\n"
        "        }\n"
        "        break;\n"
        "      }\n"
        "\n"
        "      case 'agent_runtime_end': {\n"
    )
    if old_step not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler step_complete anchor not found"
        )
    text = text.replace(old_step, new_step, 1)

    ctx.write(rel, text)
    return True


def _patch_gateway_event_handler_lca_tool_lifecycle(ctx: PatchContext) -> bool:
    """LCA gateway tool rows + pluginState: merge chunks, optimistic create, skip hollow refetch."""
    rel = (
        "src/store/chat/slices/agentRun/actions/transports/gateway/"
        "gatewayEventHandler.ts"
    )
    text = ctx.read(rel)
    marker = "/* LCA-P1: ensureLcaGatewayToolMessages */"
    if marker in text or "ensureLcaGatewayToolMessages" in text:
        return False

    old_merge_lca = (
        "const getToolResultMessageId = (tool: unknown): string | undefined =>\n"
        "  isRecord(tool) ? pickNonEmptyString(tool.result_msg_id) : undefined;\n"
        "\n"
        "const isToolStateChunkData = (data: unknown): data is ToolStateChunkData =>\n"
    )
    new_merge_lca = (
        "const getToolResultMessageId = (tool: unknown): string | undefined =>\n"
        "  isRecord(tool) ? pickNonEmptyString(tool.result_msg_id) : undefined;\n"
        "\n"
        "/** LCA gateway: merge tool chunks without clobbering args / result_msg_id. */\n"
        "const mergeLcaToolsCallingChunks = <T extends { id: string }>(\n"
        "  existing: readonly T[] | undefined,\n"
        "  incoming: readonly T[],\n"
        "): T[] => {\n"
        "  if (!existing?.length) return [...incoming];\n"
        "  const byId = new Map(existing.map((tool) => [tool.id, tool]));\n"
        "  for (const tool of incoming) {\n"
        "    const prev = byId.get(tool.id);\n"
        "    if (!prev) {\n"
        "      byId.set(tool.id, tool);\n"
        "      continue;\n"
        "    }\n"
        "    const merged = { ...prev, ...tool } as T & Record<string, unknown>;\n"
        "    const prevArgs = (prev as Record<string, unknown>).arguments;\n"
        "    const nextArgs = (tool as Record<string, unknown>).arguments;\n"
        "    if (isRecord(prevArgs) && isRecord(nextArgs) && Object.keys(nextArgs).length === 0) {\n"
        "      merged.arguments = prevArgs;\n"
        "    } else if (isRecord(prevArgs) && isRecord(nextArgs)) {\n"
        "      merged.arguments = { ...prevArgs, ...nextArgs };\n"
        "    }\n"
        "    const prevResultMsgId = getToolResultMessageId(prev);\n"
        "    if (prevResultMsgId && !getToolResultMessageId(tool)) {\n"
        "      merged.result_msg_id = prevResultMsgId;\n"
        "    }\n"
        "    byId.set(tool.id, merged as T);\n"
        "  }\n"
        "  return Array.from(byId.values());\n"
        "};\n"
        "\n"
        "const isToolStateChunkData = (data: unknown): data is ToolStateChunkData =>\n"
    )
    if old_merge_lca not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler getToolResultMessageId anchor not found"
        )
    text = text.replace(old_merge_lca, new_merge_lca, 1)

    old_ensure = (
        "  const getToolMessageByCallId = (toolCallId: string): UIChatMessage | undefined => {\n"
        "    const messages = get().dbMessagesMap[messageMapKey(context)] ?? [];\n"
        "    // Tool-call ids are operation-scoped, not topic-global. Codex can reuse an\n"
        "    // id in a later run while that run's newly persisted tool row has not yet\n"
        "    // reached the store. Parent scoping prevents us from mistaking the prior\n"
        "    // run's row for the current one and skipping the bootstrap refetch.\n"
        "    return messages.findLast(\n"
        "      (message) =>\n"
        "        message.tool_call_id === toolCallId && message.parentId === currentAssistantMessageId,\n"
        "    );\n"
        "  };\n"
        "\n"
        "  const applyLatestToolState = (toolCallId: string, reapplyAfterRefetch = false): boolean => {\n"
    )
    new_ensure = (
        "  const getToolMessageByCallId = (toolCallId: string): UIChatMessage | undefined => {\n"
        "    const messages = get().dbMessagesMap[messageMapKey(context)] ?? [];\n"
        "    // Tool-call ids are operation-scoped, not topic-global. Codex can reuse an\n"
        "    // id in a later run while that run's newly persisted tool row has not yet\n"
        "    // reached the store. Parent scoping prevents us from mistaking the prior\n"
        "    // run's row for the current one and skipping the bootstrap refetch.\n"
        "    return messages.findLast(\n"
        "      (message) =>\n"
        "        message.tool_call_id === toolCallId && message.parentId === currentAssistantMessageId,\n"
        "    );\n"
        "  };\n"
        "\n"
        "  /** LCA gateway: native server creates tool rows; LCA must mirror via optimistic create. */\n"
        "  /* LCA-P1: ensureLcaGatewayToolMessages */\n"
        "  const ensureLcaGatewayToolMessages = async (\n"
        "    toolsCalling: NonNullable<StreamChunkData['toolsCalling']>,\n"
        "  ): Promise<NonNullable<StreamChunkData['toolsCalling']>> => {\n"
        "    const ensured: NonNullable<StreamChunkData['toolsCalling']> = [...toolsCalling];\n"
        "    let changed = false;\n"
        "\n"
        "    for (let index = 0; index < ensured.length; index += 1) {\n"
        "      const tool = ensured[index];\n"
        "      if (!isRecord(tool)) continue;\n"
        "\n"
        "      const toolId = getToolId(tool);\n"
        "      const existingResultMsgId = getToolResultMessageId(tool);\n"
        "      if (!toolId || existingResultMsgId) continue;\n"
        "\n"
        "      const existingRow = getToolMessageByCallId(toolId);\n"
        "      if (existingRow?.id) {\n"
        "        ensured[index] = { ...tool, result_msg_id: existingRow.id };\n"
        "        changed = true;\n"
        "        continue;\n"
        "      }\n"
        "\n"
        "      const identifier = typeof tool.identifier === 'string' ? tool.identifier : undefined;\n"
        "      const apiName = typeof tool.apiName === 'string' ? tool.apiName : undefined;\n"
        "      if (!identifier || !apiName) continue;\n"
        "\n"
        "      const rawArgs = tool.arguments;\n"
        "      const argsStr =\n"
        "        typeof rawArgs === 'string' ? rawArgs : JSON.stringify(isRecord(rawArgs) ? rawArgs : {});\n"
        "\n"
        "      const created = await get().optimisticCreateMessage(\n"
        "        {\n"
        "          content: '',\n"
        "          parentId: currentAssistantMessageId,\n"
        "          plugin: {\n"
        "            apiName,\n"
        "            arguments: argsStr,\n"
        "            identifier,\n"
        "            id: toolId,\n"
        "            type: 'builtin',\n"
        "          },\n"
        "          role: 'tool',\n"
        "          tool_call_id: toolId,\n"
        "          topicId: context.topicId ?? undefined,\n"
        "          ...(context.agentId ? { agentId: context.agentId } : {}),\n"
        "          ...(context.threadId ? { threadId: context.threadId } : {}),\n"
        "        },\n"
        "        { operationId },\n"
        "      );\n"
        "\n"
        "      if (created?.id) {\n"
        "        ensured[index] = { ...tool, result_msg_id: created.id };\n"
        "        changed = true;\n"
        "      }\n"
        "    }\n"
        "\n"
        "    return changed ? ensured : toolsCalling;\n"
        "  };\n"
        "\n"
        "  const applyLatestToolState = (toolCallId: string, reapplyAfterRefetch = false): boolean => {\n"
    )
    if old_ensure not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler getToolMessageByCallId anchor not found"
        )
    text = text.replace(old_ensure, new_ensure, 1)

    old_tools = (
        "            /* LCA-P1: spine emits one tool per chunk — merge by id instead of replace */\n"
        "            const toolsCalling = params.preserveStreamedContentOnTerminal\n"
        "              ? (mergeToolsCallingChunks(\n"
        "                  existingTools as { id: string }[] | undefined,\n"
        "                  preserved,\n"
        "                ) as NonNullable<StreamChunkData['toolsCalling']>)\n"
        "              : preserved;\n"
        "\n"
        "            get().internal_dispatchMessage(\n"
    )
    new_tools = (
        "            /* LCA-P1: spine emits one tool per chunk — merge by id instead of replace */\n"
        "            let toolsCalling = params.preserveStreamedContentOnTerminal\n"
        "              ? (mergeLcaToolsCallingChunks(\n"
        "                  existingTools as { id: string }[] | undefined,\n"
        "                  preserved,\n"
        "                ) as NonNullable<StreamChunkData['toolsCalling']>)\n"
        "              : preserved;\n"
        "\n"
        "            if (params.preserveStreamedContentOnTerminal) {\n"
        "              toolsCalling = await ensureLcaGatewayToolMessages(toolsCalling);\n"
        "            }\n"
        "\n"
        "            get().internal_dispatchMessage(\n"
    )
    if old_tools not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler tools_calling lifecycle anchor not found"
        )
    text = text.replace(old_tools, new_tools, 1)

    old_tool_end = (
        "          const payload = unwrapToolPayload(data?.payload);\n"
        "          if (\n"
        "            didToolMutateWorkView({\n"
        "              apiName: typeof payload?.apiName === 'string' ? payload.apiName : undefined,\n"
        "              identifier: typeof payload?.identifier === 'string' ? payload.identifier : undefined,\n"
        "              result: data?.result,\n"
        "              succeeded: data?.isSuccess === true,\n"
        "              workRegistration: Boolean(\n"
        "                (data?.result as { workRegistration?: unknown } | undefined)?.workRegistration,\n"
        "              ),\n"
        "            })\n"
        "          ) {\n"
    )
    new_tool_end = (
        "          const payload = unwrapToolPayload(data?.payload);\n"
        "          const result = data?.result as\n"
        "            { state?: unknown; workRegistration?: unknown } | undefined;\n"
        "          if (params.preserveStreamedContentOnTerminal && completedToolCallId && isRecord(result?.state)) {\n"
        "            const toolMsg =\n"
        "              getToolMessageByCallId(completedToolCallId) ??\n"
        "              (() => {\n"
        "                const assistant = dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(\n"
        "                  get(),\n"
        "                );\n"
        "                const toolRow = assistant?.tools?.find(\n"
        "                  (tool) => getToolId(tool) === completedToolCallId,\n"
        "                );\n"
        "                const toolMsgId = toolRow ? getToolResultMessageId(toolRow) : undefined;\n"
        "                return toolMsgId\n"
        "                  ? dbMessageSelectors.getDbMessageById(toolMsgId)(get())\n"
        "                  : undefined;\n"
        "              })();\n"
        "            if (toolMsg?.id) {\n"
        "              get().internal_dispatchMessage(\n"
        "                {\n"
        "                  id: toolMsg.id,\n"
        "                  type: 'replaceMessagePluginState',\n"
        "                  value: result.state,\n"
        "                },\n"
        "                dispatchContext,\n"
        "              );\n"
        "            }\n"
        "            get().internal_dispatchMessage(\n"
        "              {\n"
        "                id: currentAssistantMessageId,\n"
        "                type: 'updateMessageTools',\n"
        "                tool_call_id: completedToolCallId,\n"
        "                value: { result },\n"
        "              },\n"
        "              dispatchContext,\n"
        "            );\n"
        "          }\n"
        "          if (\n"
        "            didToolMutateWorkView({\n"
        "              apiName: typeof payload?.apiName === 'string' ? payload.apiName : undefined,\n"
        "              identifier: typeof payload?.identifier === 'string' ? payload.identifier : undefined,\n"
        "              result,\n"
        "              succeeded: data?.isSuccess === true,\n"
        "              workRegistration: Boolean(result?.workRegistration),\n"
        "            })\n"
        "          ) {\n"
    )
    if old_tool_end not in text:
        raise SystemExit(
            "[lca_runtime_agent_gateway] gatewayEventHandler tool_end lifecycle anchor not found"
        )
    text = text.replace(old_tool_end, new_tool_end, 1)

    ctx.write(rel, text)
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
        _patch_gateway_create_client,
        _patch_gateway_lca_routing,
        _patch_streaming_executor,
        _patch_agent_dispatcher,
        _patch_custom_interaction_handlers,
        _patch_intervention_index,
        _patch_conversation_control,
        _patch_tool_surfaces,
        _patch_gateway_event_handler_lca_stream,
        _patch_gateway_event_handler_lca_tool_lifecycle,
    ):
        if patch_fn(ctx):
            changed = True

    for entry in _MARKER_INSERTIONS:
        if _append_marker(ctx, entry["rel"], entry["marker"], entry["insert"]):
            changed = True

    return changed

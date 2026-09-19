"""Patch: front-end WS gateway client + lobehub-ui source modifications.

This module owns:
- the TS files under ``lcaGateway/`` (see ``_NEW_FILES``), copied verbatim
  into ``src/store/chat/agents/transports/lcaGateway/``
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
    "LcaAgentStreamClient.test.ts",
    "connect.ts",
    "execute.ts",
    "executeGatewayRun.ts",
    "executeGatewayRun.test.ts",
    "messageService.ts",
    "messageService.test.ts",
    "reconnect.ts",
    "reconnect.test.ts",
    "event_handler.ts",
    "event_handler.test.ts",
    "deliverables.ts",
    "deliverables.test.ts",
    "client.test.ts",
    "lcaStepPersist.ts",
    "lcaStepPersist.test.ts",
    "lcaGatewayEventHandler.test.ts",
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
    "// This checkout is the LCA UI: every chat is a Run through the LCA\n"
    "// agent-gateway WS. A missing URL is a connect-time error, not a\n"
    "// signal to fall back to native execAgentTask.\n"
    "export function isLcaGatewayMode(_agentId?: string): boolean {\n"
    "  return true;\n"
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
        "src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts",
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
        "toolSurfaces, agentDispatcher, and gatewayEventHandler "
        "(LCA-flavored MessageReader / runtimeType / merge-by-id)."
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
    old_gated = (
        "export function isLcaGatewayMode(_agentId?: string): boolean {\n"
        "  try {\n"
        "    return !!(LCA_GATEWAY_URL && LCA_GATEWAY_URL.length > 0);\n"
        "  } catch {\n"
        "    return false;\n"
        "  }\n"
        "}"
    )
    if old_gated in text:
        text = text.replace(old_gated, "export function isLcaGatewayMode(_agentId?: string): boolean {\n  return true;\n}", 1)
        # Drop the URL import; mode no longer reads it.
        text = text.replace(
            "import { LCA_GATEWAY_WS_URL as LCA_GATEWAY_URL } from "
            "'@/store/chat/agents/transports/lcaGateway/client';\n",
            "",
            1,
        )
        ctx.write(rel, text)
        return True
    if "export function isLcaGatewayMode" in text and "return true;" in text.split(
        "export function isLcaGatewayMode", 1
    )[1][:200]:
        return False
    ctx.write(rel, text + "\n" + _IS_LCA_GATEWAY_MODE)
    return True


def _apply_ask_user_handler_upgrade(text: str) -> str | None:
    """Upgrade an already-injected ``handleLcaAskUserSubmit`` to Option B.

    The P1 handler POSTed the answer to ``/lca-api/runs/<id>/answer`` and
    returned ``skipResume`` without reconnecting the WS, so the resumed run's
    stream never reached the UI. Option B removes the POST (the resume now
    lives in ``lcaResumeGatewayRun``) and carries ``lcaRunId`` +
    ``toolResultContent`` so conversationControl can open the resume op.

    Idempotent: returns None when ``lcaRunId`` is already present.
    """
    if "lcaRunId" in text:
        return None

    opts_anchor = (
        "interface SubmitToolInteractionOptions {\n"
        "  createUserMessage?: boolean;\n"
        "  skipResume?: boolean;"
    )
    if opts_anchor not in text:
        msg = "[lca_runtime_agent_gateway] customInteractionHandlers opts upgrade anchor not found"
        raise SystemExit(msg)
    text = text.replace(
        opts_anchor,
        "interface SubmitToolInteractionOptions {\n"
        "  createUserMessage?: boolean;\n"
        "  skipResume?: boolean;\n"
        "  lcaRunId?: string;",
        1,
    )

    old_return = (
        "  try {\n"
        "    await fetch(`/lca-api/runs/${runId}/answer`, {\n"
        "      body: JSON.stringify({\n"
        "        approval_id: 'askUserQuestion',\n"
        "        idempotency_key: `${runId}:${messageId}`,\n"
        "        payload: answerText,\n"
        "      }),\n"
        "      headers: {\n"
        "        Authorization: `Bearer ${LCA_TOKEN}`,\n"
        "        'Content-Type': 'application/json',\n"
        "      },\n"
        "      method: 'POST',\n"
        "    });\n"
        "  } catch (error) {\n"
        "    console.error('[LCA] askUserQuestion answer failed', error);\n"
        "  }\n"
        "\n"
        "  return {\n"
        "    options: { createUserMessage: false, pluginState: { askUserAnswers: payload }, skipResume: true },\n"
        "    payload,\n"
        "  };"
    )
    new_return = (
        "  return {\n"
        "    options: {\n"
        "      createUserMessage: false,\n"
        "      pluginState: { askUserAnswers: payload },\n"
        "      skipResume: true,\n"
        "      lcaRunId: runId,\n"
        "      toolResultContent: answerText,\n"
        "    },\n"
        "    payload,\n"
        "  };"
    )
    if old_return not in text:
        msg = "[lca_runtime_agent_gateway] customInteractionHandlers /answer block anchor not found"
        raise SystemExit(msg)
    text = text.replace(old_return, new_return, 1)

    # The /answer POST was the only consumer of the injected token const, and
    # the store imports only fed the retired broken_read path.
    text = text.replace(
        "\nconst LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';",
        "",
        1,
    )
    text = text.replace(
        "import { dataSelectors, useConversationStore } from '@/features/Conversation/store';\n",
        "",
        1,
    )
    return text


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
        upgraded = _apply_ask_user_handler_upgrade(handlers_text)
        if upgraded is not None:
            ctx.write(handlers_path, upgraded)
            changed = True
        return changed

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
        "interface SubmitToolInteractionOptions {\n  createUserMessage?: boolean;\n  skipResume?: boolean;\n  lcaRunId?: string;",
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
 * LCA askUserQuestion resume: hand the answer to conversationControl, which
 * opens a NEW gateway op that reconnects to the SAME run's WS
 * (resume_tool_result). The run_id comes from the intervention requestArgs.
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

  return {
    options: {
      createUserMessage: false,
      pluginState: { askUserAnswers: payload },
      skipResume: true,
      lcaRunId: runId,
      toolResultContent: answerText,
    },
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
            "      lcaRunId?: string;\n      skipResume?: boolean;\n      toolResultContent?: string;\n    },\n  ): Promise<void> => {",
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
            + "\n\n    // LCA: the answer ships as a resume_tool_result run command; a new\n"
            + "    // gateway op reconnects to the SAME run's WS from the last stream\n"
            + "    // position. The native gateway resume would create a duplicate run,\n"
            + "    // so skip it and open the LCA resume op instead.\n"
            + "    if (options?.skipResume) {\n"
            + "      if (options.lcaRunId) {\n"
            + "        const [{ lcaResumeGatewayRun }, { getLcaStreamPosition }] = await Promise.all([\n"
            + "          import('@/store/chat/agents/transports/lcaGateway/executeGatewayRun'),\n"
            + "          import('@/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient'),\n"
            + "        ]);\n"
            + "        try {\n"
            + "          await lcaResumeGatewayRun(this.#get, {\n"
            + "            context: effectiveContext,\n"
            + "            runId: options.lcaRunId,\n"
            + "            lastEventId: getLcaStreamPosition(options.lcaRunId),\n"
            + "            parentMessageId: toolMessageId,\n"
            + "            topicId: effectiveContext.topicId ?? '',\n"
            + "            toolCallId: toolMessage.tool_call_id ?? '',\n"
            + "            content: options.toolResultContent ?? '',\n"
            + "          });\n"
            + "        } catch (error) {\n"
            + "          console.error('[LCA] askUserQuestion resume op failed', error);\n"
            + "        }\n"
            + "      }\n"
            + "      completeOperation(operationId);\n"
            + "      return;\n"
            + "    }",
            1,
        )
        ctx.write(control_path, control_text)
        changed = True
        control_text = ctx.read(control_path)

    if "lcaRunId" not in control_text:
        type_anchor = "      skipResume?: boolean;\n      toolResultContent?: string;\n    },\n  ): Promise<void> => {"
        if type_anchor not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl type upgrade anchor not found")
        control_text = control_text.replace(
            type_anchor,
            "      lcaRunId?: string;\n      skipResume?: boolean;\n      toolResultContent?: string;\n    },\n  ): Promise<void> => {",
            1,
        )
        ctx.write(control_path, control_text)
        changed = True
        control_text = ctx.read(control_path)

    if "LCA resume op instead" not in control_text:
        old_skip_block = (
            "    // LCA: the run is already resumed by POST /runs/<id>/answer; skip the\n"
            "    // client/gateway resume to avoid creating a duplicate run.\n"
            "    if (options?.skipResume) {\n"
            "      completeOperation(operationId);\n"
            "      return;\n"
            "    }"
        )
        new_skip_block = (
            "    // LCA: the answer ships as a resume_tool_result run command; a new\n"
            "    // gateway op reconnects to the SAME run's WS from the last stream\n"
            "    // position. The native gateway resume would create a duplicate run,\n"
            "    // so skip it and open the LCA resume op instead.\n"
            "    if (options?.skipResume) {\n"
            "      if (options.lcaRunId) {\n"
            "        const [{ lcaResumeGatewayRun }, { getLcaStreamPosition }] = await Promise.all([\n"
            "          import('@/store/chat/agents/transports/lcaGateway/executeGatewayRun'),\n"
            "          import('@/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient'),\n"
            "        ]);\n"
            "        try {\n"
            "          await lcaResumeGatewayRun(this.#get, {\n"
            "            context: effectiveContext,\n"
            "            runId: options.lcaRunId,\n"
            "            lastEventId: getLcaStreamPosition(options.lcaRunId),\n"
            "            parentMessageId: toolMessageId,\n"
            "            topicId: effectiveContext.topicId ?? '',\n"
            "            toolCallId: toolMessage.tool_call_id ?? '',\n"
            "            content: options.toolResultContent ?? '',\n"
            "          });\n"
            "        } catch (error) {\n"
            "          console.error('[LCA] askUserQuestion resume op failed', error);\n"
            "        }\n"
            "      }\n"
            "      completeOperation(operationId);\n"
            "      return;\n"
            "    }"
        )
        if old_skip_block not in control_text:
            raise SystemExit("[lca_runtime_agent_gateway] conversationControl skipResume block anchor not found")
        control_text = control_text.replace(old_skip_block, new_skip_block, 1)
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


_TOOL_END_ENQUEUE_ANCHOR = """        enqueue(async () => {
          /* LCA-P1: hollow DB rows clobber in-memory tools — refetch only on native path */
          const skipToolEndFetch = shouldSkipMidStreamMessageFetch(event, runtimeType);
          const maybeRefresh = skipToolEndFetch
            ? Promise.resolve()
            : fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(
                console.error,
              );
          const payload = unwrapToolPayload(data?.payload);
          const result = data?.result as
            { state?: unknown; workRegistration?: unknown } | undefined;"""

_TOOL_END_ENQUEUE_REPLACEMENT = """        enqueue(async () => {
          /* LCA-P1: hollow DB rows clobber in-memory tools — refetch only on native path */
          const skipToolEndFetch = shouldSkipMidStreamMessageFetch(event, runtimeType);
          const payload = unwrapToolPayload(data?.payload);
          const result = data?.result as
            { content?: unknown; state?: unknown; workRegistration?: unknown } | undefined;

          // LCA skips the DB refetch, so the inspector/render never see
          // pluginState unless we write result onto the in-memory
          // tools array here. Native path keeps the refetch (DB already
          // has pluginState from the coordinator write).
          if (skipToolEndFetch && completedToolCallId && result) {
            const existingTools = dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(
              get(),
            )?.tools;
            if (Array.isArray(existingTools) && existingTools.length > 0) {
              const nextTools = existingTools.map((tool) => {
                if (getToolId(tool) !== completedToolCallId) return tool;
                const previous = isRecord(tool) ? tool : {};
                const previousResult = isRecord(previous.result) ? previous.result : {};
                return {
                  ...previous,
                  result: { ...previousResult, ...result },
                };
              });
              get().internal_dispatchMessage(
                {
                  id: currentAssistantMessageId,
                  type: 'updateMessage',
                  value: { tools: nextTools },
                },
                dispatchContext,
              );
            }
          }

          const maybeRefresh = skipToolEndFetch
            ? Promise.resolve()
            : fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(
                console.error,
              );"""


def _apply_tool_end_in_memory_result(text: str) -> str | None:
    """Write tool_end result onto in-memory tools when LCA skips refetch.

    Returns the patched source, or None when the snippet is already present.
    """
    if "skipToolEndFetch && completedToolCallId && result" in text:
        return None
    if _TOOL_END_ENQUEUE_ANCHOR not in text:
        msg = "[lca_runtime_agent_gateway] tool_end enqueue anchor not found"
        raise SystemExit(msg)
    return text.replace(_TOOL_END_ENQUEUE_ANCHOR, _TOOL_END_ENQUEUE_REPLACEMENT, 1)


_MERGE_LEFTOVER_ANCHOR = """  for (const [id, tool] of existingById) {
    if (!incomingIds.has(id)) merged.push(tool);
  }

  return merged;
};"""

_MERGE_LEFTOVER_REPLACEMENT = """  const existingList = Array.isArray(existingTools) ? existingTools : [];
  const incomingById = new Map<string, Record<string, unknown>>();
  for (const tool of toolsCalling) {
    const id = getToolId(tool);
    if (id && isRecord(tool)) incomingById.set(id, tool);
  }

  const resultMsgIdByToolId2 = new Map<string, string>();
  for (const tool of existingList) {
    const id = getToolId(tool);
    if (!id || !isRecord(tool)) continue;
    const resultMsgId = getToolResultMessageId(tool);
    if (resultMsgId) resultMsgIdByToolId2.set(id, resultMsgId);
  }

  const ordered: unknown[] = [];
  const seen = new Set<string>();
  for (const tool of existingList) {
    const id = getToolId(tool);
    if (!id) {
      ordered.push(tool);
      continue;
    }
    seen.add(id);
    const incoming = incomingById.get(id);
    const existing = isRecord(tool) ? tool : undefined;
    if (incoming) {
      const incomingResultMsgId = getToolResultMessageId(incoming);
      ordered.push({
        ...existing,
        ...incoming,
        ...(incomingResultMsgId ? {} : { result_msg_id: resultMsgIdByToolId2.get(id) }),
        ...(incoming.result ? {} : existing?.result ? { result: existing.result } : {}),
      });
    } else {
      ordered.push(tool);
    }
  }
  for (const tool of toolsCalling) {
    const id = getToolId(tool);
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    ordered.push(tool);
  }

  return ordered;
};"""


def _apply_tool_merge_first_seen_order(text: str) -> str | None:
    """Keep tools in first-seen order instead of newest-first leftover append."""
    if "Keep the order tools first appeared" in text or "const ordered: unknown[] = [];" in text:
        return None
    if _MERGE_LEFTOVER_ANCHOR not in text:
        msg = "[lca_runtime_agent_gateway] tool merge leftover anchor not found"
        raise SystemExit(msg)
    return text.replace(_MERGE_LEFTOVER_ANCHOR, _MERGE_LEFTOVER_REPLACEMENT, 1)


_STREAM_START_RESET_ANCHOR = """          // Reset accumulators for the new stream
          accumulatedContent = '';
          accumulatedReasoning = '';
          get().updateOperationMetadata(operationId, { visibleLoadingDone: false });"""

_STREAM_START_RESET_REPLACEMENT = """          // Reset accumulators for the new stream
          accumulatedContent = '';
          accumulatedReasoning = '';
          get().updateOperationMetadata(operationId, { visibleLoadingDone: false });
          // LCA does not emit stream_end between LLM steps, so the previous
          // tools_calling animation would stay on until agent_runtime_end.
          if (runtimeType === 'lca-gateway') {
            get().internal_toggleToolCallingStreaming(currentAssistantMessageId, undefined);
          }"""


def _apply_stream_start_clear_tool_streaming(text: str) -> str | None:
    """Clear the tool-calling animation at each new LCA LLM step."""
    if "tools_calling animation would stay on until agent_runtime_end" in text:
        return None
    if _STREAM_START_RESET_ANCHOR not in text:
        msg = "[lca_runtime_agent_gateway] stream_start reset anchor not found"
        raise SystemExit(msg)
    return text.replace(_STREAM_START_RESET_ANCHOR, _STREAM_START_RESET_REPLACEMENT, 1)


def _apply_gateway_last_event_id(text: str) -> str | None:
    """Thread ``lastEventId`` through gateway.ts so LCA resume ops replay from
    the last stream position instead of the run start.

    Idempotent: returns None when the plumbing is already present.
    """
    if "lastEventId" in text:
        return None

    params_anchor = (
        "  resumeOnConnect?: boolean;\n"
        "  /**\n"
        "   * Auth token for the Gateway\n"
        "   */\n"
        "  token: string;"
    )
    if params_anchor not in text:
        msg = "[lca_runtime_agent_gateway] gateway ConnectGatewayParams anchor not found"
        raise SystemExit(msg)
    text = text.replace(
        params_anchor,
        "  resumeOnConnect?: boolean;\n"
        "  /** Last stream event id seen for this run; LCA resume replays from it. */\n"
        "  lastEventId?: string;\n"
        "  /**\n"
        "   * Auth token for the Gateway\n"
        "   */\n"
        "  token: string;",
        1,
    )

    destructure_anchor = (
        "    const { operationId, gatewayUrl, token, topicId, onEvent, onSessionComplete, resumeOnConnect } =\n"
        "      params;"
    )
    if destructure_anchor not in text:
        msg = "[lca_runtime_agent_gateway] gateway connectToGateway destructure anchor not found"
        raise SystemExit(msg)
    text = text.replace(
        destructure_anchor,
        "    const {\n"
        "      operationId,\n"
        "      gatewayUrl,\n"
        "      token,\n"
        "      topicId,\n"
        "      onEvent,\n"
        "      onSessionComplete,\n"
        "      resumeOnConnect,\n"
        "      lastEventId,\n"
        "    } = params;",
        1,
    )

    client_anchor = "    const client = this.createClient({ gatewayUrl, operationId, resumeOnConnect, token });"
    if client_anchor not in text:
        msg = "[lca_runtime_agent_gateway] gateway createClient call anchor not found"
        raise SystemExit(msg)
    text = text.replace(
        client_anchor,
        "    const client = this.createClient({ gatewayUrl, operationId, resumeOnConnect, token, lastEventId });",
        1,
    )

    factory_anchor = (
        "  createClient: (options: AgentStreamClientOptions) => GatewayConnection['client'] = (options) => {\n"
        "    if (isLcaGatewayMode()) {\n"
        "      return lcaConnectToGateway({\n"
        "        operationId: options.operationId,\n"
        "        resumeOnConnect: options.resumeOnConnect,\n"
        "        token: options.token,\n"
        "      });\n"
        "    }"
    )
    if factory_anchor not in text:
        msg = "[lca_runtime_agent_gateway] gateway createClient factory anchor not found"
        raise SystemExit(msg)
    text = text.replace(
        factory_anchor,
        "  createClient: (options: AgentStreamClientOptions & { lastEventId?: string }) => GatewayConnection['client'] = (options) => {\n"
        "    if (isLcaGatewayMode()) {\n"
        "      return lcaConnectToGateway({\n"
        "        operationId: options.operationId,\n"
        "        resumeOnConnect: options.resumeOnConnect,\n"
        "        token: options.token,\n"
        "        lastEventId: options.lastEventId,\n"
        "      });\n"
        "    }",
        1,
    )
    return text


def _apply_waiting_for_human_park(text: str) -> str | None:
    """Treat ``waiting_for_human`` as a park, not a completion.

    The LCA run pauses for human input at askUserQuestion; completing the run
    would mark the topic unread and drain the input queue. Instead, complete
    the current op via ``onRunParked`` and let a NEW op resume the same run.

    Idempotent: returns None when the park block is already present.
    """
    if "LCA park: the run is paused waiting for human input" in text:
        return None

    reasons_old = (
        "const NON_COMPLETION_RUNTIME_END_REASONS = "
        "new Set(['interrupted', 'waiting_for_async_tool']);"
    )
    reasons_new = (
        "const NON_COMPLETION_RUNTIME_END_REASONS = "
        "new Set(['interrupted', 'waiting_for_async_tool', 'waiting_for_human']);"
    )
    if reasons_old not in text:
        msg = "[lca_runtime_agent_gateway] gatewayEventHandler NON_COMPLETION_RUNTIME_END_REASONS anchor not found"
        raise SystemExit(msg)
    text = text.replace(reasons_old, reasons_new, 1)

    park_anchor = "          // Terminal run lifecycle. `isCompletedRuntimeEnd` is the clean-vs-not"
    if park_anchor not in text:
        msg = "[lca_runtime_agent_gateway] gatewayEventHandler Terminal run lifecycle anchor not found"
        raise SystemExit(msg)
    park_block = (
        "          if (data?.reason === 'waiting_for_human') {\n"
        "            // LCA park: the run is paused waiting for human input. Complete the\n"
        "            // operation so the loading spinner clears, but fire NO terminal\n"
        "            // side effects (unread / queue drain / notification). A NEW\n"
        "            // operation resumes the same run when the user answers.\n"
        "            if (runLifecycle) {\n"
        "              await runLifecycle.onRunParked({ ...lifecycleEventBase, reason: 'waiting_for_human' });\n"
        "            } else {\n"
        "              get().completeOperation(operationId);\n"
        "            }\n"
        "            return;\n"
        "          }\n"
        "\n"
    )
    text = text.replace(park_anchor, park_block + park_anchor, 1)
    return text


def _patch_gateway_last_event_id(ctx: PatchContext) -> bool:
    """Route ``lastEventId`` through gateway.ts for LCA resume ops."""
    rel = "src/store/chat/slices/agentRun/actions/transports/gateway/gateway.ts"
    text = ctx.read(rel)
    patched = _apply_gateway_last_event_id(text)
    if patched is None:
        return False
    ctx.write(rel, patched)
    return True


def _patch_gateway_event_handler_lca(ctx: PatchContext) -> bool:
    """Emit the LCA-flavored gatewayEventHandler with the runtimeType
    enum, the messageService override, the merge-by-id
    preserveToolResultMessageIds, and the hasStreamedContent skip
    gated on runtimeType != 'lca-gateway'.

    The LCA transport does not persist mid-run state to DB, so the
    shared handler's mid-run DB refetches would clobber streamed
    content with the LOADING_FLAT placeholder. The runtimeType enum
    is the discriminator: 'lca-gateway' reads from
    createLcaInMemoryMessagesReader (live store), 'gateway' and
    'hetero' read from the DB singleton and keep the partial-finalize
    race guard.

    Idempotent: re-running this on an already-patched file is a
    no-op (skip). The marker is the MessageReader type alias.
    """
    rel = (
        "src/store/chat/slices/agentRun/actions/transports/"
        "gateway/gatewayEventHandler.ts"
    )
    text = ctx.read(rel)
    changed = False
    marker = "type MessageReader = " + chr(123)
    if marker not in text:
        new_content = "import type {\n  AgentStreamEvent,\n  StepCompleteData,\n  StreamChunkData,\n  StreamStartData,\n  SubAgentProgressData,\n  ToolEndData,\n  ToolExecuteData,\n  ToolStartData,\n  ToolStateChunkData,\n} from '@lobechat/agent-gateway-client';\nimport type {\n  BuiltinToolResult,\n  ChatMessageError,\n  ConversationContext,\n  UIChatMessage,\n} from '@lobechat/types';\nimport { AgentRuntimeErrorType } from '@lobechat/types';\nimport { isRecord, pickNonEmptyString, toRecord } from '@lobechat/utils/object';\n\nimport { messageService } from '@/services/message';\nimport { didToolMutateWorkView, workService } from '@/services/work';\nimport { emitClientAgentSignalSourceEvent } from '@/store/chat/slices/agentRun/actions/lifecycle/agentSignalBridge';\nimport type {\n  AgentRunLifecycle,\n  RunScope,\n} from '@/store/chat/slices/agentRun/actions/lifecycle/types';\nimport { dbMessageSelectors } from '@/store/chat/slices/message/selectors';\nimport type { ChatStore } from '@/store/chat/store';\nimport { notifyDesktopHumanApprovalRequired } from '@/store/chat/utils/desktopNotification';\nimport { messageMapKey } from '@/store/chat/utils/messageMapKey';\n\n// `agent_runtime_end` reasons that are NOT a clean completion: a mid-stream\n// cancel and a deferred-tool park. These must NOT mark the topic unread, and\n// must take the non-success branch in `onSessionComplete` so the run clears\n// back to 'active' rather than persisting as an unread completion.\nconst NON_COMPLETION_RUNTIME_END_REASONS = new Set(['interrupted', 'waiting_for_async_tool']);\n\n/**\n * Whether an `agent_runtime_end` event represents a clean completion (vs. a\n * cancel / park). A clean completion is the only ending that should surface an\n * unread badge.\n */\nexport const isCompletedRuntimeEnd = (reason?: string | null): boolean =>\n  !NON_COMPLETION_RUNTIME_END_REASONS.has(reason ?? '');\n\n// Lazy-loaded to break the import cycle:\n//   gateway.ts → gatewayEventHandler.ts → executors/index.ts (which pulls in\n//   tool client barrels that import `@/store/chat/store`) → chat store\n//   creation → `new GatewayActionImpl(...)` while gateway.ts is still\n//   mid-evaluation, so the class binding is undefined.\nconst loadGetExecutor = async () => {\n  const mod = await import('@/store/tool/slices/builtin/executors');\n  await mod.registerBuiltinToolExecutors();\n  return mod.getExecutor;\n};\n\n/**\n * Minimal message reader contract. The LCA transport overrides\n * `params.messageService` with an in-memory reader that resolves against\n * `dbMessagesMap` (the same surface the handler writes to), so a mid-run\n * refetch does not clobber streamed content with hollow DB rows. The\n * shared handler keeps the DB singleton as the default reader so the\n * upstream gateway / hetero paths stay unchanged.\n */\ntype MessageReader = {\n  getMessages: (query: ConversationContext & { skipWorks?: boolean }) => Promise<UIChatMessage[]>;\n};\n\n/**\n * Fetch messages from DB and replace them in the chat store's dbMessagesMap.\n * This updates the ConversationArea component via React subscription:\n *   dbMessagesMap → ConversationArea (messages prop) → ConversationStore → UI\n */\nconst fetchAndReplaceMessages = async (\n  get: () => ChatStore,\n  context: ConversationContext,\n  options?: {\n    /**\n     * Mid-stream refetches (stream_start / tool_end / step_complete) skip the\n     * server-side Work-summary assembly — each tool round would otherwise\n     * re-run the per-type Work queries. `preserveWorks` grafts the\n     * already-rendered works back so chips don't flicker; the terminal\n     * agent_runtime_end refetch recomputes them for real.\n     */\n    skipWorks?: boolean;\n  },\n  reader: MessageReader = messageService,\n) => {\n  const skipWorks = options?.skipWorks;\n  const messages = await reader.getMessages(\n    skipWorks ? { ...context, skipWorks } : context,\n  );\n  get().replaceMessages(messages, { context, preserveWorks: skipWorks });\n  return messages;\n};\n\nconst shouldSkipMessageFetch = (\n  event: AgentStreamEvent,\n  runtimeType: 'gateway' | 'lca-gateway' | 'hetero',\n): boolean => runtimeType === 'hetero' && event.data?.skipMessageFetch === true;\n\n/** LCA gateway streams tools/content in-memory; mid-run DB rows are hollow. */\nconst shouldSkipMidStreamMessageFetch = (\n  event: AgentStreamEvent,\n  runtimeType: 'gateway' | 'lca-gateway' | 'hetero',\n): boolean =>\n  shouldSkipMessageFetch(event, runtimeType) || runtimeType === 'lca-gateway';\n\nconst getToolId = (tool: unknown): string | undefined =>\n  isRecord(tool) ? pickNonEmptyString(tool.id) : undefined;\n\nconst getToolResultMessageId = (tool: unknown): string | undefined =>\n  isRecord(tool) ? pickNonEmptyString(tool.result_msg_id) : undefined;\n\nconst isToolStateChunkData = (data: unknown): data is ToolStateChunkData =>\n  isRecord(data) &&\n  data.chunkType === 'tool_state' &&\n  data.snapshotMode === 'replace' &&\n  typeof data.toolCallId === 'string' &&\n  data.toolCallId.length > 0 &&\n  Number.isInteger(data.snapshotSeq) &&\n  (data.snapshotSeq as number) > 0 &&\n  isRecord(data.pluginState);\n\nconst preserveToolResultMessageIds = (\n  toolsCalling: unknown[],\n  existingTools: unknown,\n): unknown[] => {\n  const existingById = new Map<string, Record<string, unknown>>();\n  const resultMsgIdByToolId = new Map<string, string>();\n  for (const tool of existingTools ?? []) {\n    const id = getToolId(tool);\n    if (!id) continue;\n    if (isRecord(tool)) {\n      existingById.set(id, tool);\n      const resultMsgId = getToolResultMessageId(tool);\n      if (resultMsgId) resultMsgIdByToolId.set(id, resultMsgId);\n    }\n  }\n\n  const incomingIds = new Set<string>();\n  const merged: unknown[] = [];\n  for (const tool of toolsCalling) {\n    const id = getToolId(tool);\n    if (!id) {\n      merged.push(tool);\n      continue;\n    }\n    incomingIds.add(id);\n    const existing = existingById.get(id);\n    const incomingTool = isRecord(tool) ? tool : undefined;\n    if (existing && incomingTool) {\n      const incomingResultMsgId = getToolResultMessageId(tool);\n      merged.push({\n        ...incomingTool,\n        ...(incomingResultMsgId ? {} : { result_msg_id: resultMsgIdByToolId.get(id) }),\n      });\n    } else if (incomingTool) {\n      merged.push(incomingTool);\n    } else {\n      merged.push(tool);\n    }\n  }\n\n  for (const [id, tool] of existingById) {\n    if (!incomingIds.has(id)) merged.push(tool);\n  }\n\n  return merged;\n};\n\ninterface ChatToolPayloadLike {\n  apiName?: unknown;\n  arguments?: unknown;\n  id?: unknown;\n  identifier?: unknown;\n}\n\ninterface ToolPayloadIdentity {\n  apiName: string;\n  identifier: string;\n  params: unknown;\n  toolCallId?: string;\n}\n\n/**\n * Extract `{ identifier, apiName, params, toolCallId }` from a stream event's\n * tool payload. Returns `undefined` when the payload is malformed so the\n * caller can skip dispatch without throwing.\n */\nconst readToolPayload = (\n  payload: ChatToolPayloadLike | undefined,\n): ToolPayloadIdentity | undefined => {\n  const identifier = typeof payload?.identifier === 'string' ? payload.identifier : undefined;\n  const apiName = typeof payload?.apiName === 'string' ? payload.apiName : undefined;\n  if (!identifier || !apiName) return undefined;\n\n  let params: unknown = payload?.arguments;\n  if (typeof params === 'string') {\n    try {\n      params = JSON.parse(params);\n    } catch {\n      params = {};\n    }\n  } else if (params == null) {\n    params = {};\n  }\n\n  const toolCallId = typeof payload?.id === 'string' ? payload.id : undefined;\n  return { apiName, identifier, params, toolCallId };\n};\n\n/**\n * Route a `tool_start` event to the executor's optional `onBeforeCall` hook so\n * tool packages can react before their own mutations dispatch (e.g.\n * optimistic UI). Fires for both client- and server-runtime tools.\n */\nconst dispatchOnBeforeCall = async (\n  data: ToolStartData | undefined,\n  topicId?: string,\n): Promise<void> => {\n  const payload = data?.toolCalling as ChatToolPayloadLike | undefined;\n  const identity = readToolPayload(payload);\n  if (!identity) return;\n\n  const getExecutor = await loadGetExecutor();\n  const executor = getExecutor(identity.identifier);\n  if (!executor?.onBeforeCall) return;\n\n  await executor.onBeforeCall({ ...identity, topicId });\n};\n\n/**\n * Real gateway `tool_end` events ship `data.payload` as the\n * `{ parentMessageId, toolCalling }` wrapper, NOT a flat `ChatToolPayload`\n * (see `apps/server/src/modules/AgentRuntime/RuntimeExecutors.ts` — both the\n * single-tool and batch publish sites). Unwrap defensively, falling back to\n * the flat shape so we tolerate test fixtures / future emission paths that\n * pass the payload directly.\n */\nconst unwrapToolPayload = (raw: unknown): ChatToolPayloadLike | undefined => {\n  if (!raw || typeof raw !== 'object') return undefined;\n  const wrapper = raw as { toolCalling?: unknown };\n  if (wrapper.toolCalling && typeof wrapper.toolCalling === 'object') {\n    return wrapper.toolCalling as ChatToolPayloadLike;\n  }\n  return raw as ChatToolPayloadLike;\n};\n\n/**\n * Route a `tool_end` event to the executor's optional `onAfterCall` hook so\n * tool packages can react to their own mutations (e.g. invalidate store\n * caches) regardless of whether the tool ran client- or server-side.\n */\nconst dispatchOnAfterCall = async (\n  data: ToolEndData | undefined,\n  topicId?: string,\n): Promise<void> => {\n  const identity = readToolPayload(unwrapToolPayload(data?.payload));\n  if (!identity) return;\n\n  const getExecutor = await loadGetExecutor();\n  const executor = getExecutor(identity.identifier);\n  if (!executor?.onAfterCall) return;\n\n  await executor.onAfterCall({\n    ...identity,\n    result: (data?.result ?? {}) as BuiltinToolResult,\n    topicId,\n  });\n};\n\ntype GatewayMessageLike = { id: string; role?: string };\ntype HeteroStreamStartData = StreamStartData & { newStep?: boolean };\n\nconst findNextAssistantMessageId = (\n  messages: GatewayMessageLike[] | undefined,\n  currentAssistantMessageId: string,\n) => {\n  if (!messages?.length) return;\n\n  const currentIndex = messages.findIndex((message) => message.id === currentAssistantMessageId);\n  if (currentIndex === -1) return;\n\n  for (let index = currentIndex + 1; index < messages.length; index += 1) {\n    const message = messages[index];\n    if (message.role === 'assistant') {\n      return message.id;\n    }\n  }\n};\n\nconst isErrorType = (value: unknown): value is ChatMessageError['type'] =>\n  typeof value === 'string' || typeof value === 'number';\n\nconst getMessageFromErrorData = (data: unknown): string | undefined => {\n  if (!isRecord(data)) return undefined;\n\n  const message = pickNonEmptyString(data.message);\n  if (message) return message;\n\n  const error = data.error;\n  const errorString = pickNonEmptyString(error);\n  if (errorString) return errorString;\n  if (isRecord(error)) {\n    const errorMessage = pickNonEmptyString(error.message);\n    if (errorMessage) return errorMessage;\n\n    const nestedError = error.error;\n    if (isRecord(nestedError)) {\n      const nestedMessage = pickNonEmptyString(nestedError.message);\n      if (nestedMessage) return nestedMessage;\n    }\n  }\n\n  const responseBody = data._responseBody;\n  const responseBodyMessage = getMessageFromErrorData(responseBody);\n  if (responseBodyMessage) return responseBodyMessage;\n\n  const body = data.body;\n  if (isRecord(body)) {\n    const bodyMessage = pickNonEmptyString(body.message);\n    if (bodyMessage) return bodyMessage;\n  }\n};\n\nconst mergeGatewayPayloadError = (\n  sourceBody: Record<string, unknown>,\n  payloadError: unknown,\n): Record<string, unknown> => {\n  if (payloadError === undefined) return sourceBody;\n  if (!('error' in sourceBody)) return { ...sourceBody, error: payloadError };\n  if (isRecord(sourceBody.error) && isRecord(payloadError)) {\n    return { ...sourceBody, error: { ...payloadError, ...sourceBody.error } };\n  }\n  return sourceBody;\n};\n\nconst buildGatewayRuntimeErrorBody = (\n  data: Record<string, unknown>,\n  message: string,\n): Record<string, unknown> => {\n  const body = toRecord(data.body);\n  const responseBody = toRecord(data._responseBody);\n  const errorBody = toRecord(data.error);\n  const sourceBody = body ?? responseBody ?? errorBody ?? {};\n  const shouldMergePayloadError = body === undefined && data._responseBody !== undefined;\n  const mergedBody = shouldMergePayloadError\n    ? mergeGatewayPayloadError(sourceBody, data.error)\n    : sourceBody;\n\n  return {\n    ...mergedBody,\n    ...(data.budget === undefined || 'budget' in mergedBody ? {} : { budget: data.budget }),\n    ...(typeof data.provider === 'string' && !('provider' in mergedBody)\n      ? { provider: data.provider }\n      : {}),\n    ...('message' in mergedBody ? {} : { message }),\n  };\n};\n\nconst toChatMessageError = (data: unknown): ChatMessageError => {\n  if (isRecord(data) && isErrorType(data.type)) {\n    const message =\n      typeof data.message === 'string' && data.message\n        ? data.message\n        : getMessageFromErrorData({ body: data.body });\n\n    return {\n      ...data,\n      ...(message ? { message } : {}),\n      type: data.type,\n    };\n  }\n\n  // Gateway realtime error events can carry the model-runtime payload shape\n  // (`errorType` + `error`) before the terminal DB message is refreshed. Treat\n  // it as the same semantic error instead of falling back to AgentRuntimeError.\n  if (isRecord(data) && isErrorType(data.errorType)) {\n    const message = getMessageFromErrorData(data) || String(data.errorType);\n\n    return {\n      body: buildGatewayRuntimeErrorBody(data, message),\n      message,\n      type: data.errorType,\n    };\n  }\n\n  const message = getMessageFromErrorData(data) || 'Unknown error';\n\n  return {\n    body: { message },\n    message,\n    type: AgentRuntimeErrorType.AgentRuntimeError,\n  };\n};\n\n/**\n * Creates a handler function that processes Agent Gateway events\n * and maps them to the chat store's message update actions.\n *\n * Supports multi-step agent execution (LLM → tool calls → next LLM → ...)\n * using a hybrid approach:\n * - Current LLM step: real-time streaming via stream_chunk\n * - Step transitions: fetchAndReplaceMessages from DB at stream_start / tool_end / step_complete\n *\n * The handler queues incoming events and processes them sequentially,\n * ensuring that stream_chunk waits for stream_start's DB fetch to resolve\n * before dispatching updates.\n */\nexport const createGatewayEventHandler = (\n  get: () => ChatStore,\n  params: {\n    assistantMessageId: string;\n    context: ConversationContext;\n    /**\n     * Server-side operation id — used to look up the `AgentStreamClient` in\n     * `gatewayConnections` so we can `sendToolResult` back over the same WS.\n     * Defaults to `operationId` when the caller does not distinguish the two.\n     */\n    gatewayOperationId?: string;\n    /**\n     * Override for the message reader. The LCA transport injects an\n     * in-memory reader that resolves against `dbMessagesMap` (the same\n     * surface the handler writes to) so a mid-run refetch does not\n     * clobber streamed content with hollow DB rows. The default reader is\n     * the DB singleton (`messageService`).\n     */\n    messageService?: MessageReader;\n    operationId: string;\n    /**\n     * Shared run lifecycle for this run, assembled by the caller (gateway.ts).\n     * Only the gateway transport supplies it — it drives the terminal lifecycle\n     * (completeRun / afterRunComplete) here. hetero reuses this handler ONLY for\n     * per-event message reconciliation; its executor owns the terminal lifecycle\n     * (completeRun + notification + queue drain) in `onComplete`, so it omits this\n     * and the handler must NOT double-complete or double-notify.\n     *\n     * Injected (not built here) to avoid statically importing `buildRunLifecycle`\n     * — which pulls `@/store/chat/store` into this module's evaluation and breaks\n     * the gateway.ts → gatewayEventHandler import cycle.\n     */\n    runLifecycle?: AgentRunLifecycle;\n    /**\n     * Which transport owns this handler. `gateway` (default) drives the terminal\n     * run lifecycle here (completeRun / afterRunComplete). `lca-gateway` reuses\n     * the handler for in-memory streaming AND skips mid-run DB refetches (the\n     * LCA runtime persists assistant rows only on turn seal, so a mid-run DB\n     * read would clobber content the WS stream already rendered). `hetero`\n     * reuses the handler ONLY for per-event message reconciliation.\n     */\n    runtimeType?: 'gateway' | 'lca-gateway' | 'hetero';\n  },\n) => {\n  const { context, operationId, runLifecycle } = params;\n  const gatewayOperationId = params.gatewayOperationId ?? operationId;\n  const runtimeType = params.runtimeType ?? 'gateway';\n  const reader: MessageReader = params.messageService ?? messageService;\n\n  const runScope: RunScope = context.scope === 'sub_agent' ? 'sub_agent' : 'top_level';\n  const lifecycleEventBase = {\n    context,\n    operationId,\n    runId: operationId,\n    runScope,\n    runtimeType: 'gateway' as const,\n  };\n\n  // Dispatch context — ensures internal_dispatchMessage resolves the correct messageMapKey\n  const dispatchContext = { operationId };\n\n  // Mutable — switches to new assistant message ID on each stream_start\n  let currentAssistantMessageId = params.assistantMessageId;\n  let terminalState: 'completed' | 'error' | undefined;\n  let shouldRefreshWorkViews = false;\n\n  // Accumulated content from stream chunks (reset on each stream_start)\n  let accumulatedContent = '';\n  let accumulatedReasoning = '';\n  // Last applied `replace`-snapshot seqs. Operation-monotonic (the producer\n  // never resets them across messages), so unlike the accumulators they are\n  // NOT reset on stream boundaries — a seq ≤ these is a redelivered duplicate.\n  let lastTextSnapshotSeq = 0;\n  let lastReasoningSnapshotSeq = 0;\n  const latestToolStateByCallId = new Map<string, ToolStateChunkData & { operationId: string }>();\n  const toolStateBootstrapPromiseByCallId = new Map<string, Promise<void>>();\n  const lastAppliedToolStateSeqByCallId = new Map<string, number>();\n  const completedToolStateCallIds = new Set<string>();\n\n  // Tracks whether any server-confirmed state has actually arrived\n  // (server-assigned assistant id, streamed text/reasoning/tools, or a SoT\n  // uiMessages snapshot). Used by `agent_runtime_end` to decide between\n  // preserving in-memory streamed content (when interrupted MID-stream) vs.\n  // falling back to a DB refetch (when interrupted BEFORE any server state\n  // landed — otherwise the optimistic `tmp_*` placeholder messages stay in\n  // the store indefinitely).\n  let hasStreamedContent = false;\n\n  // Active reasoning sub-op id. Mirrors the LLM `StreamingHandler` lifecycle so\n  // `isMessageInReasoning(messageId)` (which drives the Thinking UI's\n  // \"thinking...\" title + auto-expand) flips to `true` while thinking is\n  // streaming. Without this, heterogeneous server-mode messages render the\n  // collapsed \"completed\" state from the first chunk on.\n  let reasoningOperationId: string | undefined;\n\n  const startReasoningIfNeeded = () => {\n    if (reasoningOperationId) return;\n    const { operationId: reasoningOpId } = get().startOperation({\n      context: { ...context, messageId: currentAssistantMessageId },\n      parentOperationId: operationId,\n      type: 'reasoning',\n    });\n    get().associateMessageWithOperation(currentAssistantMessageId, reasoningOpId);\n    reasoningOperationId = reasoningOpId;\n  };\n\n  const endReasoningIfNeeded = () => {\n    if (!reasoningOperationId) return;\n    get().completeOperation(reasoningOperationId);\n    reasoningOperationId = undefined;\n  };\n\n  // Sequential processing queue — ensures stream_chunk waits for stream_start's fetch\n  let processingChain: Promise<void> = Promise.resolve();\n\n  const enqueue = (fn: () => Promise<void> | void): Promise<void> => {\n    processingChain = processingChain.then(fn, fn);\n    return processingChain;\n  };\n\n  const getToolMessageByCallId = (toolCallId: string): UIChatMessage | undefined => {\n    const messages = get().dbMessagesMap[messageMapKey(context)] ?? [];\n    // Tool-call ids are operation-scoped, not topic-global. Codex can reuse an\n    // id in a later run while that run's newly persisted tool row has not yet\n    // reached the store. Parent scoping prevents us from mistaking the prior\n    // run's row for the current one and skipping the bootstrap refetch.\n    return messages.findLast(\n      (message) =>\n        message.tool_call_id === toolCallId && message.parentId === currentAssistantMessageId,\n    );\n  };\n\n  const applyLatestToolState = (toolCallId: string, reapplyAfterRefetch = false): boolean => {\n    const latest = latestToolStateByCallId.get(toolCallId);\n    if (terminalState || completedToolStateCallIds.has(toolCallId)) return true;\n    const toolMessage = getToolMessageByCallId(toolCallId);\n    if (!latest || !toolMessage) return false;\n\n    const storedSeq =\n      toolMessage.metadata?.heterogeneousToolStateOperationId === latest.operationId &&\n      typeof toolMessage.metadata.heterogeneousToolStateSeq === 'number'\n        ? toolMessage.metadata.heterogeneousToolStateSeq\n        : 0;\n    const inMemorySeq = lastAppliedToolStateSeqByCallId.get(toolCallId) ?? 0;\n\n    // A bootstrap refetch can replace an optimistic seq=4 with DB seq=3. In\n    // that path the message's own watermark, not the in-memory map, decides\n    // whether the cached latest snapshot must be re-applied.\n    if (latest.snapshotSeq <= storedSeq) {\n      lastAppliedToolStateSeqByCallId.set(toolCallId, Math.max(inMemorySeq, storedSeq));\n      return true;\n    }\n    if (!reapplyAfterRefetch && latest.snapshotSeq <= inMemorySeq) return true;\n\n    lastAppliedToolStateSeqByCallId.set(toolCallId, latest.snapshotSeq);\n    get().internal_dispatchMessage(\n      {\n        id: toolMessage.id,\n        metadata: {\n          heterogeneousToolStateOperationId: latest.operationId,\n          heterogeneousToolStateSeq: latest.snapshotSeq,\n        },\n        type: 'replaceMessagePluginState',\n        value: latest.pluginState,\n      },\n      dispatchContext,\n    );\n    return true;\n  };\n\n  const scheduleToolState = (\n    data: ToolStateChunkData,\n    eventOperationId: string | undefined,\n    bootstrapRetry = false,\n  ): void => {\n    if (completedToolStateCallIds.has(data.toolCallId)) return;\n\n    const stateOperationId = eventOperationId || gatewayOperationId;\n    const previous = latestToolStateByCallId.get(data.toolCallId);\n    if (!bootstrapRetry) {\n      if (previous?.operationId === stateOperationId && data.snapshotSeq <= previous.snapshotSeq) {\n        return;\n      }\n\n      // Cache synchronously. A later seq can now overtake an in-flight bootstrap\n      // read; the bootstrap completion always reapplies this map's newest value.\n      latestToolStateByCallId.set(data.toolCallId, { ...data, operationId: stateOperationId });\n    }\n\n    if (getToolMessageByCallId(data.toolCallId)) {\n      enqueue(() => {\n        applyLatestToolState(data.toolCallId);\n      });\n      return;\n    }\n\n    if (toolStateBootstrapPromiseByCallId.has(data.toolCallId)) return;\n\n    let reconciled = false;\n    const bootstrapSnapshotSeq = data.snapshotSeq;\n    // Bootstrap reconciliation is part of the same queue as tool_end. If this\n    // read finishes late, the terminal refresh must still run after it so an\n    // intermediate DB snapshot can never become the last store replacement.\n    const bootstrapPromise = enqueue(async () => {\n      // A preceding queued tools_calling handler may have brought the row in.\n      if (!getToolMessageByCallId(data.toolCallId)) {\n        await fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(\n          console.error,\n        );\n      }\n      reconciled = applyLatestToolState(data.toolCallId, true);\n    });\n    const trackedBootstrapPromise = bootstrapPromise.finally(() => {\n      toolStateBootstrapPromiseByCallId.delete(data.toolCallId);\n\n      const latest = latestToolStateByCallId.get(data.toolCallId);\n      // A newer snapshot may have arrived while a failed/empty bootstrap was\n      // in flight. Retry for that newer state, but never spin on the same seq.\n      if (\n        !reconciled &&\n        !terminalState &&\n        !completedToolStateCallIds.has(data.toolCallId) &&\n        latest &&\n        latest.snapshotSeq > bootstrapSnapshotSeq\n      ) {\n        scheduleToolState(latest, latest.operationId, true);\n      }\n    });\n    toolStateBootstrapPromiseByCallId.set(data.toolCallId, trackedBootstrapPromise);\n  };\n\n  return (event: AgentStreamEvent) => {\n    if (terminalState) return;\n\n    // Subagent (`Agent`/`Task`) inner-tool events are tagged `data.subagent` and\n    // belong to an isolation Thread. This handler is main-agent-only, so\n    // dispatching them leaks the subagent's tools into the parent bubble\n    // mid-stream until the terminal fetch corrects it. The local executor drops\n    // them before forwarding; the gateway path doesn't. (DB is unaffected.)\n    if ((event.data as { subagent?: unknown } | undefined)?.subagent) return;\n\n    if (event.type === 'stream_chunk' && isToolStateChunkData(event.data)) {\n      scheduleToolState(event.data, event.operationId);\n      return;\n    }\n\n    if (event.type === 'agent_runtime_end' || event.type === 'error') {\n      terminalState = event.type === 'error' ? 'error' : 'completed';\n    }\n\n    switch (event.type) {\n      case 'stream_start': {\n        enqueue(async () => {\n          const data = event.data as HeteroStreamStartData | undefined;\n\n          const newAssistantMessageId = data?.assistantMessage?.id;\n\n          // Switch to the new assistant message created by the server for this step\n          if (newAssistantMessageId) {\n            currentAssistantMessageId = newAssistantMessageId;\n            // Associate the new message with the operation so UI shows generating state\n            get().associateMessageWithOperation(currentAssistantMessageId, operationId);\n            // Server-confirmed assistant id is durable state — preserve it on\n            // interrupt instead of falling back to a placeholder-clobbering refetch.\n            hasStreamedContent = true;\n          }\n\n          // Close any reasoning op carried over from the previous step.\n          // Safe to run after the assistant-id swap: the op was started with\n          // its own messageId context, so completion doesn't depend on the\n          // current id.\n          endReasoningIfNeeded();\n\n          // Reset accumulators for the new stream\n          accumulatedContent = '';\n          accumulatedReasoning = '';\n          get().updateOperationMetadata(operationId, { visibleLoadingDone: false });\n\n          // Native gateway streams carry `assistantMessage.id` directly on\n          // stream_start, so they skip this DB read — that skip is what\n          // un-blocks the enqueue chain so live chunks can land mid-stream.\n          //\n          // Hetero CLI adapters (Claude Code / Codex) never set\n          // `assistantMessage.id` on stream_start, so the DB read stays\n          // mandatory for them — it (a) pulls the executor-created\n          // placeholder into `dbMessagesMap` so subsequent chunks can\n          // dispatch to it, and (b) resolves the next-step assistant id for\n          // the `newStep` fallback.\n          if (!newAssistantMessageId) {\n            const messages = await fetchAndReplaceMessages(\n              get,\n              context,\n              {\n                skipWorks: true,\n              },\n              reader,\n            ).catch((error) => {\n              console.error(error);\n              return undefined;\n            });\n\n            if (data?.newStep) {\n              const resolvedAssistantMessageId = findNextAssistantMessageId(\n                messages as GatewayMessageLike[] | undefined,\n                currentAssistantMessageId,\n              );\n\n              if (resolvedAssistantMessageId) {\n                currentAssistantMessageId = resolvedAssistantMessageId;\n                get().associateMessageWithOperation(currentAssistantMessageId, operationId);\n              }\n            }\n          }\n\n          void emitClientAgentSignalSourceEvent({\n            payload: {\n              agentId: context.agentId,\n              ...(currentAssistantMessageId\n                ? {\n                    anchorMessageId: currentAssistantMessageId,\n                    assistantMessageId: currentAssistantMessageId,\n                  }\n                : {}),\n              operationId,\n              stepIndex: event.stepIndex,\n              topicId: context.topicId ?? undefined,\n            },\n            sourceId: `${operationId}:gateway:start:${event.stepIndex}`,\n            sourceType: 'client.gateway.stream_start',\n          });\n        });\n        break;\n      }\n\n      case 'stream_chunk': {\n        enqueue(async () => {\n          const data = event.data as StreamChunkData | undefined;\n          if (!data) return;\n\n          if (data.chunkType === 'text' && data.content) {\n            // `lh hetero exec` coalesces main-agent text into full-text\n            // `replace` snapshots; native gateway runs stream plain deltas.\n            const snapshotSeq =\n              data.snapshotMode === 'replace' && typeof data.snapshotSeq === 'number'\n                ? data.snapshotSeq\n                : undefined;\n\n            if (snapshotSeq !== undefined && snapshotSeq <= lastTextSnapshotSeq) {\n              // Redelivered snapshot (producer batch retry / duplicate on the\n              // stream) — already applied, appending it would duplicate text.\n            } else {\n              // Text after reasoning marks the end of the thinking pass — see\n              // `StreamingHandler.handleText` for the same transition.\n              endReasoningIfNeeded();\n              if (snapshotSeq === undefined) {\n                accumulatedContent += data.content;\n              } else {\n                lastTextSnapshotSeq = snapshotSeq;\n                accumulatedContent = data.content;\n              }\n              hasStreamedContent = true;\n              get().internal_dispatchMessage(\n                {\n                  id: currentAssistantMessageId,\n                  type: 'updateMessage',\n                  value: { content: accumulatedContent },\n                },\n                dispatchContext,\n              );\n            }\n          }\n\n          if (data.chunkType === 'reasoning' && data.reasoning) {\n            // Same snapshot semantics as text above: `lh hetero exec`\n            // coalesces reasoning into `replace` snapshots; redelivered seqs\n            // are dropped instead of appended (which would duplicate the\n            // thinking text on a server-side batch retry).\n            const snapshotSeq =\n              data.snapshotMode === 'replace' && typeof data.snapshotSeq === 'number'\n                ? data.snapshotSeq\n                : undefined;\n\n            if (snapshotSeq !== undefined && snapshotSeq <= lastReasoningSnapshotSeq) {\n              // Redelivered snapshot — already applied.\n            } else {\n              startReasoningIfNeeded();\n              if (snapshotSeq === undefined) {\n                accumulatedReasoning += data.reasoning;\n              } else {\n                lastReasoningSnapshotSeq = snapshotSeq;\n                accumulatedReasoning = data.reasoning;\n              }\n              hasStreamedContent = true;\n              get().internal_dispatchMessage(\n                {\n                  id: currentAssistantMessageId,\n                  type: 'updateMessage',\n                  value: { reasoning: { content: accumulatedReasoning } },\n                },\n                dispatchContext,\n              );\n            }\n          }\n\n          if (data.chunkType === 'tools_calling' && data.toolsCalling) {\n            endReasoningIfNeeded();\n            hasStreamedContent = true;\n            const existingTools = dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(\n              get(),\n            )?.tools;\n            const toolsCalling = preserveToolResultMessageIds(\n              data.toolsCalling as unknown[],\n              existingTools,\n            ) as NonNullable<StreamChunkData['toolsCalling']>;\n\n            get().internal_dispatchMessage(\n              {\n                id: currentAssistantMessageId,\n                type: 'updateMessage',\n                value: { tools: toolsCalling },\n              },\n              dispatchContext,\n            );\n\n            // Drive tool calling animation\n            get().internal_toggleToolCallingStreaming(\n              currentAssistantMessageId,\n              toolsCalling.map(() => true),\n            );\n\n            // If the server attached a `toolMessageIds` map, it has persisted\n            // pending tool messages (human approval, deferred async tools).\n            // Fetch the latest messages so ApprovalActions can read them by id\n            // instead of waiting for `agent_runtime_end` (which won't fire while\n            // paused in `waiting_for_human` / `waiting_for_async_tool`).\n            //\n            // AWAITED so the fetch is actually part of the queued work. Anything\n            // enqueued behind this chunk addresses rows that only exist once it\n            // lands — a fire-and-forget fetch would let the next event overtake\n            // it and dispatch onto a message the store doesn't have yet.\n            if ((data as any).toolMessageIds) {\n              await fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(\n                console.error,\n              );\n            }\n          }\n        });\n        break;\n      }\n\n      case 'stream_end': {\n        enqueue(() => {\n          const data = toRecord(event.data);\n          const finalContent = pickNonEmptyString(data?.finalContent);\n          if (finalContent !== undefined) {\n            // Example: reasoning-only answers stream as reasoning chunks, then\n            // the server promotes that text into stream_end.finalContent. Apply\n            // it before ending reasoning so visible_output_end cannot leave an\n            // empty completed assistant bubble while waiting for terminal SoT.\n            accumulatedContent = finalContent;\n            hasStreamedContent = true;\n            get().internal_dispatchMessage(\n              {\n                id: currentAssistantMessageId,\n                type: 'updateMessage',\n                value: { content: accumulatedContent },\n              },\n              dispatchContext,\n            );\n          }\n          get().internal_toggleToolCallingStreaming(currentAssistantMessageId, undefined);\n          endReasoningIfNeeded();\n        });\n        break;\n      }\n\n      case 'visible_output_end': {\n        enqueue(() => {\n          // Guard: only clear visible loading when the streamed content has\n          // actually landed in the store. If the message shell is missing (or\n          // text streamed but never applied), clearing here would show\n          // \"loading done\" with the answer still invisible —\n          // skip the hint instead and let agent_runtime_end reconcile content\n          // and loading in the same frame, i.e. the pre-early-hint behavior.\n          const stored = dbMessageSelectors.getDbMessageById(currentAssistantMessageId)(get());\n          if (!stored || (accumulatedContent && !stored.content)) return;\n\n          get().internal_toggleToolCallingStreaming(currentAssistantMessageId, undefined);\n          endReasoningIfNeeded();\n          // Example: CC/Codex may emit stream_end -> stream_start(newStep) for\n          // assistant-assistant transitions. Only this explicit producer signal\n          // means visible output is done; the operation still waits for\n          // agent_runtime_end to preserve terminal side-effect ordering.\n          get().updateOperationMetadata(operationId, { visibleLoadingDone: true });\n          // From here the sidebar item stops showing the running spinner (the\n          // answer is visibly complete) and — when the user isn't viewing the\n          // topic — shows the unread dot instead, ahead of markTopicUnread's\n          // persisted 'unread' at the terminal. See `isRunningTailUnread` in\n          // the sidebar topic Item.\n        });\n        break;\n      }\n\n      case 'tool_start': {\n        // Server creates tool messages in DB.\n        // Loading is already active from stream_start (not cleared by stream_end).\n        const data = event.data as ToolStartData | undefined;\n        const startedToolCallId =\n          getToolId(data?.toolCalling) ||\n          (isRecord(data) ? pickNonEmptyString(data.toolCallId) : undefined);\n        // A producer may reuse a call id within one operation. A new lifecycle\n        // re-opens state delivery while the seq watermark remains monotonic, so\n        // delayed snapshots from the previous lifecycle are still rejected.\n        if (startedToolCallId) completedToolStateCallIds.delete(startedToolCallId);\n        enqueue(async () => {\n          await dispatchOnBeforeCall(data, context.topicId ?? undefined).catch(console.error);\n        });\n        break;\n      }\n\n      case 'step_start': {\n        const data = event.data as {\n          pendingToolsCalling?: unknown[];\n          phase?: string;\n          requiresApproval?: boolean;\n          uiMessages?: UIChatMessage[];\n        };\n\n        // The server's stepIndex is the authoritative step counter — mirror it\n        // onto the operation so step-based UI (OpStatusTray) stays correct\n        // even across page-refresh reconnects.\n        if (typeof event.stepIndex === 'number') {\n          get().updateOperationMetadata(operationId, { stepCount: event.stepIndex + 1 });\n        }\n\n        // Server attaches the canonical UIChatMessage[] snapshot at every\n        // step boundary (agent-runtime #15152). Use it as Source of Truth\n        // instead of issuing a DB refetch — the refetch returns a stale\n        // assistant placeholder while DB fan-out is still in flight, which\n        // clobbers the in-memory streamed assistantGroup.\n        if (Array.isArray(data?.uiMessages)) {\n          // step_start snapshots are fetched with `skipWorks` server-side —\n          // graft the already-rendered works back so chips don't flicker.\n          get().replaceMessages(data.uiMessages, {\n            action: 'gateway/step_start',\n            context,\n            preserveWorks: true,\n          });\n        }\n\n        if (data?.phase === 'human_approval' && data.requiresApproval && data.pendingToolsCalling) {\n          void notifyDesktopHumanApprovalRequired(get, context);\n          // Persist the explicit \"needs user input\" marker so the sidebar swaps\n          // the running spinner for the hand icon across reloads.\n          if (context.topicId) {\n            const statusWrite = get().updateTopicStatus?.({\n              agentId: context.agentId,\n              groupId: context.groupId,\n              ...(context.scope === 'group' || context.scope === 'group_agent'\n                ? { scope: context.scope }\n                : {}),\n              status: 'waitingForHuman',\n              topicId: context.topicId,\n            });\n            void statusWrite?.catch((error) => {\n              console.error('[gatewayEventHandler] updateTopicStatus failed:', error);\n            });\n          }\n        }\n\n        break;\n      }\n\n      case 'tool_execute': {\n        // Fire-and-forget: the client-side tool may take a long time, and we\n        // must keep processing other events (stream_chunk, tool_end, etc.) on\n        // the same WebSocket. `internal_executeClientTool` guarantees it never\n        // throws and always sends exactly one `tool_result` back.\n        //\n        // Use `gatewayOperationId` (server-side id, the key under\n        // `gatewayConnections`) so the action can look up the WS to reply on\n        // — NOT the local `operationId` used for `dispatchContext`.\n        const data = event.data as ToolExecuteData | undefined;\n        if (!data) break;\n        void get().internal_executeClientTool(data, {\n          localOperationId: operationId,\n          operationId: gatewayOperationId,\n        });\n        break;\n      }\n\n      case 'tool_end': {\n        const data = event.data as ToolEndData | undefined;\n        const completedToolCallId =\n          getToolId(unwrapToolPayload(data?.payload)) ||\n          (isRecord(data) ? pickNonEmptyString(data.toolCallId) : undefined);\n        if (completedToolCallId) {\n          completedToolStateCallIds.add(completedToolCallId);\n          latestToolStateByCallId.delete(completedToolCallId);\n        }\n        enqueue(async () => {\n          /* LCA-P1: hollow DB rows clobber in-memory tools — refetch only on native path */\n          const skipToolEndFetch = shouldSkipMidStreamMessageFetch(event, runtimeType);\n          const maybeRefresh = skipToolEndFetch\n            ? Promise.resolve()\n            : fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(\n                console.error,\n              );\n          const payload = unwrapToolPayload(data?.payload);\n          const result = data?.result as\n            { state?: unknown; workRegistration?: unknown } | undefined;\n          if (\n            didToolMutateWorkView({\n              apiName: typeof payload?.apiName === 'string' ? payload.apiName : undefined,\n              identifier: typeof payload?.identifier === 'string' ? payload.identifier : undefined,\n              result,\n              succeeded: data?.isSuccess === true,\n              workRegistration: Boolean(result?.workRegistration),\n            })\n          ) {\n            shouldRefreshWorkViews = true;\n          }\n\n          await Promise.all([\n            maybeRefresh,\n            dispatchOnAfterCall(data, context.topicId ?? undefined).catch(console.error),\n          ]);\n          // Message-backed summaries refresh with the normal tool payload. Lazy\n          // Work views settle once at runtime-end when a mutating tool was seen.\n        });\n        break;\n      }\n\n      case 'step_complete': {\n        const data = event.data as StepCompleteData | undefined;\n\n        // A parked `callSubAgent` child reporting its running totals. Patch them\n        // onto the placeholder tool message in memory only — the persisted values\n        // are written once, by `completeSubAgentBridge`, when the child finishes.\n        // Kept under a `progress` key so a DB refetch can never leave a stale live\n        // number sitting where the authoritative one belongs.\n        //\n        // ENQUEUED, not dispatched inline: the placeholder row only enters the\n        // store via the `toolMessageIds` refetch that the preceding `tools_calling`\n        // chunk queued. A fast child can emit its first progress event while that\n        // fetch is still in flight, and `updatePluginState` against a row the store\n        // doesn't have is a silent no-op — for a single-step sub-agent that lone\n        // sample is the whole live readout, so there is nothing later to self-heal\n        // it. Queueing puts this behind the fetch that creates its target.\n        if (data?.phase === 'subagent_progress') {\n          const progress = event.data as SubAgentProgressData;\n          if (progress.toolMessageId) {\n            enqueue(() => {\n              get().internal_dispatchMessage(\n                {\n                  id: progress.toolMessageId,\n                  key: 'progress',\n                  type: 'updatePluginState',\n                  value: {\n                    model: progress.model,\n                    totalCost: progress.totalCost,\n                    totalInputTokens: progress.totalInputTokens,\n                    totalOutputTokens: progress.totalOutputTokens,\n                    totalTokens: progress.totalTokens,\n                    totalToolCalls: progress.totalToolCalls,\n                  },\n                },\n                dispatchContext,\n              );\n            });\n          }\n          break;\n        }\n\n        // Refresh on execution_complete to ensure final step state is consistent\n        if (data?.phase === 'execution_complete') {\n          enqueue(async () => {\n            void emitClientAgentSignalSourceEvent({\n              payload: {\n                agentId: context.agentId,\n                operationId,\n                stepIndex: event.stepIndex,\n                topicId: context.topicId ?? undefined,\n              },\n              sourceId: `${operationId}:gateway:step_complete:${event.stepIndex}`,\n              sourceType: 'client.gateway.step_complete',\n            });\n            if (!shouldSkipMidStreamMessageFetch(event, runtimeType)) {\n              await fetchAndReplaceMessages(get, context, { skipWorks: true }, reader).catch(\n                console.error,\n              );\n            }\n          });\n        }\n        break;\n      }\n\n      case 'agent_runtime_end': {\n        enqueue(async () => {\n          const data = event.data as { reason?: string; uiMessages?: UIChatMessage[] } | undefined;\n\n          void emitClientAgentSignalSourceEvent({\n            payload: {\n              agentId: context.agentId,\n              ...(currentAssistantMessageId\n                ? {\n                    anchorMessageId: currentAssistantMessageId,\n                    assistantMessageId: currentAssistantMessageId,\n                  }\n                : {}),\n              operationId,\n              topicId: context.topicId ?? undefined,\n            },\n            sourceId: `${operationId}:gateway:runtime_end`,\n            sourceType: 'client.gateway.runtime_end',\n          });\n          get().internal_toggleToolCallingStreaming(currentAssistantMessageId, undefined);\n          endReasoningIfNeeded();\n\n          // The terminal snapshot, when the server pushed one — the reconciled\n          // Source of Truth for this run's final assistant text.\n          let terminalMessages: UIChatMessage[] | undefined;\n\n          // Reconcile messages FIRST so the terminal run lifecycle's notification\n          // (afterRunComplete) can read the final assistant content from the store.\n          //\n          // Terminal step has no later step_start to carry SoT — server\n          // pushes the canonical snapshot directly on this event. Fall back\n          // to a DB refetch only if the snapshot is absent (older server\n          // builds, or push-event delivery edge cases).\n          if (Array.isArray(data?.uiMessages)) {\n            terminalMessages = data.uiMessages;\n            get().replaceMessages(data.uiMessages, {\n              action: 'gateway/agent_runtime_end',\n              context,\n            });\n          } else if (\n            (data?.reason === 'interrupted' || data?.reason === 'waiting_for_async_tool') &&\n            hasStreamedContent &&\n            runtimeType !== 'lca-gateway'\n          ) {\n            // MID-stream cancel, or a deferred-tool pause\n            // (`waiting_for_async_tool`). The server's\n            // `AgentRuntimeCoordinator.resolveUiMessages` omits uiMessages\n            // for both statuses precisely so we can preserve the\n            // in-memory streamed content here. The executor's partial-\n            // finalize catch writes the real content to DB asynchronously,\n            // but it may not be durable yet — refetching here would race\n            // against that update and clobber the streamed content with\n            // the LOADING_FLAT placeholder. Keep what we have; the next\n            // explicit refresh (route change, user-driven mutate) picks\n            // up the finalized partial content from DB.\n            //\n            // The `hasStreamedContent` guard limits this skip to the case\n            // where server state actually landed (server-assigned assistant\n            // id from stream_start OR any chunk dispatched). The\n            // `runtimeType !== 'lca-gateway'` guard lets the LCA path\n            // fall through to the terminal refetch — LCA's in-memory\n            // reader reconciles against `dbMessagesMap` directly, so the\n            // refetch lands the streamed content cleanly.\n          } else {\n            await fetchAndReplaceMessages(get, context, undefined, reader).catch(console.error);\n          }\n\n          if (runtimeType === 'gateway' && shouldRefreshWorkViews) {\n            await workService\n              .refreshConversationViews(context.topicId, context.threadId)\n              .catch(console.error);\n          }\n\n          // Terminal run lifecycle. `isCompletedRuntimeEnd` is the clean-vs-not\n          // gate (a mid-stream cancel 'interrupted' or deferred-tool park\n          // 'waiting_for_async_tool' is NOT a clean completion):\n          //   • completed → completeRun completes the op, marks the topic unread,\n          //     drains the input queue, then afterRunComplete fires the desktop\n          //     notification (skipped if a queued follow-up was scheduled).\n          //   • cancelled → completeRun only completes the op (no unread badge,\n          //     no queue drain, no notification) — same as the old inline path.\n          if (runtimeType === 'gateway' && runLifecycle) {\n            const status = isCompletedRuntimeEnd(data?.reason) ? 'completed' : 'cancelled';\n            const { requeued } = await runLifecycle.completeRun({\n              ...lifecycleEventBase,\n              status,\n            });\n            if (!requeued && status === 'completed') {\n              // Notification body, resolved most-authoritative first:\n              //\n              // 1. the terminal snapshot's final assistant text — server-\n              //    finalized, so it wins over the optimistic stream even when\n              //    the two disagree (dropped chunks, server-side rewrites);\n              // 2. `accumulatedContent`, the in-memory stream (a closure\n              //    untouched by `replaceMessages`), for the no-snapshot path\n              //    where `fetchAndReplaceMessages` races the executor's DB\n              //    write and would otherwise leave the body empty. Its stale\n              //    predecessor is NOT read back from that refetch: a not-yet-\n              //    written assistant row would surface the PRIOR turn's reply;\n              // 3. nothing (`''`), letting `afterRunComplete` fall back to its\n              //    store read and then to the generic \"generation finished\".\n              const finalAssistantContent = terminalMessages?.findLast(\n                (message) => message.role === 'assistant',\n              )?.content;\n\n              await runLifecycle.afterRunComplete({\n                ...lifecycleEventBase,\n                notification: { content: finalAssistantContent || accumulatedContent },\n                status,\n              });\n            }\n          } else {\n            // hetero reuses this handler only for message reconciliation; its\n            // executor owns completeRun + notification + queue drain. Complete the\n            // op here so loading clears, and mark unread on a clean completion —\n            // matching the legacy inline path the hetero executor still relies on.\n            get().completeOperation(operationId);\n            const completedOp = get().operations[operationId];\n            if (completedOp?.context.agentId && isCompletedRuntimeEnd(data?.reason)) {\n              get().markTopicUnread({\n                agentId: completedOp.context.agentId,\n                groupId: completedOp.context.groupId,\n                topicId: completedOp.context.topicId,\n              });\n            }\n          }\n        });\n        break;\n      }\n\n      case 'notify_update': {\n        // Remote hetero agent (openclaw / hermes) wrote a message to DB via\n        // `lh notify`. DB is the source of truth — just refresh the message list.\n        enqueue(async () => {\n          await fetchAndReplaceMessages(get, context, undefined, reader).catch(console.error);\n        });\n        break;\n      }\n\n      case 'error': {\n        enqueue(async () => {\n          const messageError = toChatMessageError(event.data);\n          const errorMessage = messageError.message;\n\n          void emitClientAgentSignalSourceEvent({\n            payload: {\n              agentId: context.agentId,\n              errorMessage,\n              operationId,\n              topicId: context.topicId ?? undefined,\n            },\n            sourceId: `${operationId}:gateway:error`,\n            sourceType: 'client.gateway.error',\n          });\n\n          get().internal_toggleToolCallingStreaming(currentAssistantMessageId, undefined);\n          endReasoningIfNeeded();\n\n          // An errored run is a FAILED run, not a completed one — failed runs\n          // receive no unread badge, no queue drain, and no notification.\n          // For gateway, drive the terminal disposition through the\n          // shared lifecycle so the op lands in `failed` (no unread badge, no queue\n          // drain, no notification). hetero never forwards `error` to this handler\n          // (its executor routes errors through persistTerminalError), but keep the\n          // legacy completeOperation for any other caller for safety.\n          if (runtimeType === 'gateway' && runLifecycle) {\n            await runLifecycle.completeRun({ ...lifecycleEventBase, status: 'failed' });\n          } else {\n            get().completeOperation(operationId);\n          }\n\n          const updateResult = await messageService\n            .updateMessageError(currentAssistantMessageId, messageError, {\n              agentId: context.agentId,\n              groupId: context.groupId,\n              threadId: context.threadId,\n              topicId: context.topicId,\n            })\n            .catch(console.error);\n\n          if (updateResult?.success && updateResult.messages) {\n            get().replaceMessages(updateResult.messages, { context });\n          } else {\n            // Fallback when the mutation response doesn't include messages.\n            await fetchAndReplaceMessages(get, context, undefined, reader).catch(console.error);\n          }\n\n          // Then overlay the inline error. This ensures the UI always shows the\n          // error even if the server hasn't persisted it into the message yet\n          // (the DB fetch would have returned a message with no error field).\n          get().internal_dispatchMessage(\n            {\n              id: currentAssistantMessageId,\n              type: 'updateMessage',\n              value: {\n                error: messageError,\n              },\n            },\n            dispatchContext,\n          );\n        });\n        break;\n      }\n    }\n  };\n};\n"
        ctx.write(rel, new_content)
        text = new_content
        changed = True
    for apply_fn in (
        _apply_tool_end_in_memory_result,
        _apply_tool_merge_first_seen_order,
        _apply_stream_start_clear_tool_streaming,
        _apply_waiting_for_human_park,
    ):
        patched = apply_fn(text)
        if patched is not None:
            text = patched
            ctx.write(rel, text)
            changed = True
    return changed


def _resolve_gateway_http(ctx: PatchContext) -> str:
    # Source of truth: ``lobehub-ui/.env``. Read by scanning lines, never
    # process env. ``lobehub.py::_ensure_dev_env`` guarantees the file
    # exists and contains the URL on every restart, so this lookup is
    # total in normal operation. Returns ``""`` when the key is missing;
    # the caller treats that as a configuration error.
    env_file = ctx._ui / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LCA_GATEWAY_PUBLIC_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    return ""


def apply(ctx: PatchContext) -> bool:
    changed = False

    # Inject the build-time LCA gateway WS URL into lcaGateway/client.ts
    # so the browser bundle carries the URL as a literal (the lobehub-spa
    # Vite dev server does NOT expose ``process.env.NEXT_PUBLIC_*`` to the
    # client bundle by default — only ``VITE_*``). Sourced from
    # ``lobehub-ui/.env`` — never process env — so the patch engine
    # behaves identically whether called from ``lca-ops`` or directly.
    gateway_http = _resolve_gateway_http(ctx)
    if not gateway_http:
        raise SystemExit(
            "lca_runtime_agent_gateway: LCA_GATEWAY_PUBLIC_URL missing "
            "from lobehub-ui/.env — run `lca-ops lobehub restart` to "
            "regenerate it, or set the key manually."
        )
    gateway_ws = gateway_http.replace("http://", "ws://", 1).replace(
        "https://", "wss://", 1
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
        _patch_gateway_last_event_id,
        _patch_streaming_executor,
        _patch_agent_dispatcher,
        _patch_custom_interaction_handlers,
        _patch_intervention_index,
        _patch_conversation_control,
        _patch_tool_surfaces,
        _patch_gateway_event_handler_lca,
    ):
        if patch_fn(ctx):
            changed = True

    for entry in _MARKER_INSERTIONS:
        if _append_marker(ctx, entry["rel"], entry["marker"], entry["insert"]):
            changed = True

    return changed

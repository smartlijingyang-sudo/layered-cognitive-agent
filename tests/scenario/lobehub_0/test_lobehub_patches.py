"""Patch tests for lca_runtime_agent_gateway (P1 gateway runtime surface)."""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.lobehub.engine import PatchContext, discover_patches
from deploy.lobehub.patches.runtime.lca_runtime_agent_gateway import apply, meta

_EXECUTOR = "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts"
_DRIVER = "src/store/chat/agents/transports/lcaGateway/executeGatewayRun.ts"
_MARKER = "/* LCA: every chat is a Run */"

# Realistic executeClientAgent snippet copied from LobeHub v2.2.13.
_STUB_EXECUTOR = """import { createClientRuntimeExecutors } from '@/store/chat/agents/transports/createClientRuntimeExecutors';
import { buildRunLifecycle } from '../../lifecycle/buildRunLifecycle';
import type { RunParkedReason, RunScope } from '../../lifecycle/types';

export class StreamingExecutorActionImpl {
  executeClientAgent = async (params: {
    context: { scope?: string };
    messages: unknown[];
    parentMessageId: string;
    parentMessageType: 'user' | 'assistant' | 'tool';
    skipCreateFirstMessage?: boolean;
    userMessageId?: string;
  }): Promise<{ model?: string; provider?: string } | void> => {
    const { messages, parentMessageId, parentMessageType, context } = params;
    const operationId = 'op-1';
    const scope = context.scope;
    const agentConfig = { agentConfig: { model: 'solo', provider: 'openai' } };

    // Use model/provider from resolved agentConfig
    const { agentConfig: agentConfigData } = agentConfig;
    const model = agentConfigData.model;
    const provider = agentConfigData.provider;

    const modelRuntimeConfig = {
      model,
      provider: provider!,
      // TODO: Support dedicated compression model from chatConfig.compressionModelId
      compressionModel: { model, provider: provider! },
    };
    const agent = new GeneralChatAgent({
      agentConfig: { maxSteps: 1000 },
      modelRuntimeConfig,
    });
    void agent;
    void messages;
    void parentMessageId;
    void parentMessageType;
    void operationId;
    void scope;
    void buildRunLifecycle;
    return { model, provider };
  };
}
"""


_STUB_HANDLERS = """import { topicService } from '@/services/topic';

interface SubmitToolInteractionOptions {
  createUserMessage?: boolean;
  pluginState?: Record<string, unknown>;
  toolResultContent?: string;
}

interface CustomInteractionContext {
  apiName?: string;
  requestArgs?: Record<string, unknown>;
  topicId?: string | null;
}

type CustomInteractionSubmitHandler = (
  payload: Record<string, unknown>,
  context?: CustomInteractionContext,
) => Promise<{ options?: SubmitToolInteractionOptions; payload: Record<string, unknown> } | undefined>;

const isAskUserQuestionCall = () => true;

const customInteractionSubmitHandlers: Array<{
  handler: CustomInteractionSubmitHandler;
  match: (identifier: string, apiName?: string) => boolean;
}> = [
  {
    handler: async (payload) => ({
      options: { pluginState: { askUserAnswers: payload } },
      payload,
    }),
    match: isAskUserQuestionCall,
  },
];

export const prepareCustomInteractionSubmit = async () => ({ payload: {} });
export const isCustomInteractionIdentifier = () => false;
export const isHeteroInteractionIdentifier = () => false;
export const recordCustomInteractionResolution = async () => {};
"""

_STUB_INTERVENTION = """export const x = async () => {
  await prepareCustomInteractionSubmit(
    identifier,
    action.payload,
    {
      apiName,
      requestArgs: parsedArgs,
      topicId,
    },
  );
};
"""

_STUB_CONVERSATION_CONTROL = """import { buildRunLifecycle } from '../lifecycle/buildRunLifecycle';

export class ConversationControlStub {
  submitToolInteraction = async (
    toolMessageId: string,
    response: Record<string, unknown>,
    context?: unknown,
    options?: {
      createUserMessage?: boolean;
      pluginState?: Record<string, unknown>;
      toolResultContent?: string;
    },
  ): Promise<void> => {
    void toolMessageId;
    void response;
    void context;
    void options;
    // NOTE: intentionally do NOT bail on Stop here. `intervention: approved`
    // and the tool result are already persisted above; returning early would
    // leave the submission recorded but never resumed — a stuck conversation.
    // Same best-effort rationale as approveToolCalling: complete atomically and
    // honor the next Stop normally.
  };

  skipToolInteraction = async () => {
    if (this.#wasInterimOpStopped(operationId)) return;

    // 2. Create a user message indicating the skip
  };

  cancelToolInteraction = async () => {
    const toolContent = 'User cancelled this interaction.';
    void toolContent;
  };

  #wasInterimOpStopped = (_operationId: string): boolean => false;
}
"""

_STUB_TOOL_SURFACES = """let registrationPromise: Promise<void> | undefined;

export const ensureBuiltinToolSurfaces = (): Promise<void> => {
  if (!registrationPromise) {
    registrationPromise = import('@lobechat/builtin-tools/register')
      .then(({ registerBuiltinToolSurfaces }) => {
        registerBuiltinToolSurfaces();
      });
  }
  return registrationPromise;
};
"""


def _seed_ui(tmp_path: Path) -> Path:
    executor = tmp_path / _EXECUTOR
    executor.parent.mkdir(parents=True)
    executor.write_text(_STUB_EXECUTOR, encoding="utf-8")

    handlers = (
        tmp_path
        / "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts"
    )
    handlers.parent.mkdir(parents=True, exist_ok=True)
    handlers.write_text(_STUB_HANDLERS, encoding="utf-8")

    intervention = (
        tmp_path
        / "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/index.tsx"
    )
    intervention.write_text(_STUB_INTERVENTION, encoding="utf-8")

    control = tmp_path / "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(_STUB_CONVERSATION_CONTROL, encoding="utf-8")

    tool_surfaces = tmp_path / "src/spa/initialize/toolSurfaces.ts"
    tool_surfaces.parent.mkdir(parents=True, exist_ok=True)
    tool_surfaces.write_text(_STUB_TOOL_SURFACES, encoding="utf-8")

    dispatcher = (
        tmp_path / "src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts"
    )
    dispatcher.parent.mkdir(parents=True, exist_ok=True)
    dispatcher.write_text("export const dispatchAgent = () => {};\n", encoding="utf-8")

    return tmp_path


def test_gateway_runtime_patches_registered() -> None:
    root = Path("deploy/lobehub/patches")
    assert (root / "runtime" / "lca_runtime_agent_gateway.py").is_file()
    assert not (root / "runtime" / "lca_run_driver.py").exists()
    names = {pm.meta.name for pm in discover_patches()}
    assert "lca_runtime_agent_gateway" in names
    assert "lca_run_driver" not in names
    assert "openai_guard" not in names


def test_apply_injects_gateway_block(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)

    assert apply(ctx) is True

    executor = (ui / _EXECUTOR).read_text(encoding="utf-8")
    assert _MARKER in executor
    assert "lcaExecuteGatewayRun" in executor
    assert "isLcaGatewayMode" in executor
    hijack = executor.split(_MARKER, 1)[1].split("const modelRuntimeConfig", 1)[0]
    assert "await lcaExecuteGatewayRun" in hijack
    assert "runLcaJournal" not in hijack

    assert meta.verify_marker == "export function lcaConnectToGateway"
    assert meta.name == "lca_runtime_agent_gateway"


def test_apply_is_idempotent_when_marker_present(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True
    assert apply(ctx) is False


def test_apply_raises_when_anchor_missing(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    executor = ui / _EXECUTOR
    executor.write_text(
        "import { createClientRuntimeExecutors } from "
        "'@/store/chat/agents/transports/createClientRuntimeExecutors';\n"
        "export const x = 1;\n",
        encoding="utf-8",
    )
    ctx = PatchContext(ui_dir=ui)
    with pytest.raises(SystemExit, match="lca_runtime_agent_gateway"):
        apply(ctx)

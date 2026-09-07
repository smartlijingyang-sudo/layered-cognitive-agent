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

    # Mirror what ``lobehub.py::_ensure_dev_env`` produces on real starts:
    # a ``.env`` carrying the gateway URL is the source of truth for the
    # patch engine. Tests exercising the "no URL" path overwrite or
    # delete this file explicitly.
    (tmp_path / ".env").write_text(
        "LCA_GATEWAY_PUBLIC_URL=http://127.0.0.1:8765\n",
        encoding="utf-8",
    )

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


# ── gateway URL source: lobehub-ui/.env, never os.environ ──────────────


def _write_dotenv(ui: Path, *lines: str) -> None:
    """Write a minimal ``.env`` under the seeded UI tree."""
    (ui / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_resolve_gateway_http_reads_dotenv(tmp_path: Path, monkeypatch) -> None:
    # ``LCA_GATEWAY_PUBLIC_URL`` from ``lobehub-ui/.env`` is the source
    # of truth; shell env is ignored even when set to a wrong value.
    from deploy.lobehub.patches.runtime.lca_runtime_agent_gateway import (
        _resolve_gateway_http,
    )

    ui = _seed_ui(tmp_path)
    _write_dotenv(ui, "LCA_GATEWAY_PUBLIC_URL=http://10.36.6.252:8765")
    monkeypatch.setenv("LCA_GATEWAY_PUBLIC_URL", "http://wrong-host:1")

    ctx = PatchContext(ui_dir=ui)
    assert _resolve_gateway_http(ctx) == "http://10.36.6.252:8765"


def test_resolve_gateway_http_ignores_os_environ_only(tmp_path: Path, monkeypatch) -> None:
    # Regression — the previous implementation read ``os.environ`` and
    # silently wrote a ``ws://lca-gateway-unset:0000`` placeholder into
    # ``client.ts`` whenever shell env was empty. The fix pins the
    # source to ``.env``; the helper returns ``""`` to signal the caller
    # should raise.
    from deploy.lobehub.patches.runtime.lca_runtime_agent_gateway import (
        _resolve_gateway_http,
    )

    ui = _seed_ui(tmp_path)
    (ui / ".env").unlink()
    monkeypatch.setenv("LCA_GATEWAY_PUBLIC_URL", "http://from-shell:8765")

    ctx = PatchContext(ui_dir=ui)
    assert _resolve_gateway_http(ctx) == ""


def test_resolve_gateway_http_returns_empty_when_key_missing(
    tmp_path: Path, monkeypatch
) -> None:
    # ``.env`` exists but lacks the key → ``""``.
    from deploy.lobehub.patches.runtime.lca_runtime_agent_gateway import (
        _resolve_gateway_http,
    )

    ui = _seed_ui(tmp_path)
    _write_dotenv(ui, "OPENAI_API_KEY=sk-test", "FOO=bar")
    monkeypatch.setenv("LCA_GATEWAY_PUBLIC_URL", "http://from-shell:8765")

    ctx = PatchContext(ui_dir=ui)
    assert _resolve_gateway_http(ctx) == ""


# ── attachment forwarding: imageList / fileList / files ────────────────


_EXECUTE_PATCH_PATH = Path("deploy/lobehub/patches/runtime/lcaGateway/execute.ts")
_DRIVER_PATCH_PATH = Path(
    "deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts"
)


def test_patch_source_declares_attachment_extras_in_execute_ts() -> None:
    """``LcaStartRunBody.messages`` must declare imageList/fileList/files so
    the LCA ingress can hydrate attachments before composing the run prompt.

    Regression: prior to the patch, the type only had ``role`` / ``content``;
    UIChatMessage imageList / fileList metadata was silently dropped on the
    wire and the model received no attachment context.
    """
    body = _EXECUTE_PATCH_PATH.read_text(encoding="utf-8")
    assert "imageList?" in body
    assert "fileList?" in body
    assert "files?" in body


def test_patch_source_forwards_attachment_extras_in_driver() -> None:
    """``lcaExecuteGatewayRun`` must build ``attachmentExtras`` from the
    trailing user message and spread it into the messages posted to LCA.
    Empty arrays are dropped to keep the wire shape stable for text turns.
    """
    driver = _DRIVER_PATCH_PATH.read_text(encoding="utf-8")
    assert "attachmentExtras" in driver
    assert "...attachmentExtras" in driver
    # Only forward non-empty arrays; the LobeHub UI side ships `[]` on
    # text-only turns and we must not echo those on the wire.
    assert "imageList.length > 0" in driver
    assert "fileList.length > 0" in driver
    assert "files.length > 0" in driver

"""Patch tests for lca_run_driver (Journal projector hijack, 2026-08-21 surface)."""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.lobehub.engine import PatchContext, discover_patches
from deploy.lobehub.patches.runtime.lca_run_driver import apply, meta

_EXECUTOR = "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts"
_DRIVER = "src/store/chat/agents/transports/LcaRunDriver.ts"
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


def _seed_ui(tmp_path: Path) -> Path:
    executor = tmp_path / _EXECUTOR
    executor.parent.mkdir(parents=True)
    executor.write_text(_STUB_EXECUTOR, encoding="utf-8")
    return tmp_path


def test_journal_driver_and_openai_guard_are_retired() -> None:
    root = Path("deploy/lobehub/patches")
    assert (root / "runtime" / "lca_run_driver.py").is_file()
    # openai_guard retired: the gateway /v1/responses endpoint now adapts the wire
    # shape to LobeHub's Responses parser, so LobeHub code stays untouched and
    # no virtual-model allowlist is hardcoded into the SDK.
    assert not (root / "provider" / "openai_guard.py").exists()
    names = {pm.meta.name for pm in discover_patches()}
    assert "lca_run_driver" in names
    assert "openai_guard" not in names
    assert "lca_agent_driver" not in names
    assert "drop_lca_chat_hijack" not in names


def test_apply_injects_marker_and_writes_driver(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)

    assert apply(ctx) is True

    executor = (ui / _EXECUTOR).read_text(encoding="utf-8")
    assert _MARKER in executor
    assert "runLcaJournal" in executor
    assert "finishLcaChat" in executor
    assert "new GeneralChatAgent" in executor.split(_MARKER, 1)[1]
    hijack = executor.split(_MARKER, 1)[1].split("const modelRuntimeConfig", 1)[0]
    assert "await runLcaJournal" in hijack
    assert "await finishLcaChat" in hijack
    assert "model === 'team' || model === 'auto' ? model : 'solo'" in hijack

    driver = ui / _DRIVER
    assert driver.is_file()
    source = driver.read_text(encoding="utf-8")
    assert "runLcaJournal" in source
    assert "projectJournalFrame" in source
    assert (ui / "src/store/chat/agents/transports/lcaJournal.ts").is_file()
    assert (ui / "src/store/chat/agents/transports/lcaWire.ts").is_file()

    assert meta.verify_marker == _MARKER
    assert meta.name == "lca_run_driver"


def test_apply_is_idempotent_when_marker_present(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True
    assert apply(ctx) is False


def test_apply_raises_when_anchor_missing(tmp_path: Path) -> None:
    executor = tmp_path / _EXECUTOR
    executor.parent.mkdir(parents=True)
    executor.write_text(
        "import { createClientRuntimeExecutors } from "
        "'@/store/chat/agents/transports/createClientRuntimeExecutors';\n"
        "export const x = 1;\n",
        encoding="utf-8",
    )
    ctx = PatchContext(ui_dir=tmp_path)
    with pytest.raises(SystemExit, match="lca_run_driver"):
        apply(ctx)

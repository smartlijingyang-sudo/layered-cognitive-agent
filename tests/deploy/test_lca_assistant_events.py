"""Tests for lca_assistant_events patch (Task 11: avatar event WS client).

Validates:
1. TS source presence (deploy/lobehub/patches/runtime/lcaGateway/assistantEventClient.ts).
2. Client contract: WS URL `/lca-api/v1/assistants/{id}/events`, first-frame
   ``{type:'auth', token}`` handshake, dispatches
   ``lca-assistant-avatar-changed``, exponential backoff reconnect.
3. Vitest source presence for the client.
4. Patch integration: copies files into lcaGateway/ and mounts
   AssistantEventClient in the conversation Header.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext
from deploy.lobehub.patches.runtime.lca_assistant_events import apply, meta

_GATEWAY_DIR_REL = "src/store/chat/agents/transports/lcaGateway"
_HEADER_REL = "src/routes/(main)/agent/features/Conversation/Header/index.tsx"

_STUB_HEADER = """'use client';

import { Flexbox } from '@lobehub/ui';
import { createStaticStyles, cssVar } from 'antd-style';
import { memo, useCallback, useState } from 'react';
import { agentSelectors } from '@/store/agent/selectors';
import AssistantTopMascot from '@/features/Conversation/components/AssistantTopMascot';

import NavHeader from '@/features/NavHeader';
import { useAgentStore } from '@/store/agent';
import { useChatStore } from '@/store/chat';

const Header = memo(() => {
  const agentId = useChatStore((s) => s.activeAgentId);
  const targetAssistantId = agentId;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingFile, setEditingFile] = useState<{
    filename: string;
    filePath?: string;
    initialHash?: string;
  } | null>(null);

  const handleEditFile = useCallback((filename: string, fileInfo: any) => {
    setEditingFile({
      filename,
      filePath: fileInfo.path,
      initialHash: fileInfo.content_hash,
    });
    setEditorOpen(true);
  }, []);

  return <div>header</div>;
});

export default Header;
"""


def _client_ts_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "runtime"
        / "lcaGateway"
        / "assistantEventClient.ts"
    )


def _client_test_ts_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "runtime"
        / "lcaGateway"
        / "assistantEventClient.test.ts"
    )


def _seed_ui(tmp_path: Path) -> Path:
    header = tmp_path / _HEADER_REL
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(_STUB_HEADER, encoding="utf-8")
    return tmp_path


def test_assistant_event_client_ts_exists() -> None:
    assert _client_ts_path().is_file(), "Missing assistantEventClient.ts"


def test_assistant_event_client_contract() -> None:
    content = _client_ts_path().read_text(encoding="utf-8")
    assert "lca-api/v1/assistants" in content
    assert "type: 'auth'" in content
    assert "lca-assistant-avatar-changed" in content
    assert "avatar_updated" in content
    assert "avatar_video_ready" in content
    assert "2 ** this.retry" in content or "Math.min(2 ** this.retry" in content
    assert "export class AssistantEventClient" in content


def test_assistant_event_client_vitest_exists() -> None:
    path = _client_test_ts_path()
    assert path.is_file(), "Missing assistantEventClient.test.ts"
    content = path.read_text(encoding="utf-8")
    assert "lca-assistant-avatar-changed" in content
    assert "auth" in content


def test_lca_assistant_events_patch_module_exists() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "runtime"
        / "lca_assistant_events.py"
    )
    assert path.is_file(), "Missing patch module: lca_assistant_events.py"


def test_lca_assistant_events_patch_meta() -> None:
    assert meta.name == "lca_assistant_events"
    assert meta.verify_marker == "export class AssistantEventClient"
    assert f"{_GATEWAY_DIR_REL}/assistantEventClient.ts" in meta.files
    assert _HEADER_REL in meta.files


def test_lca_assistant_events_apply_copies_files_and_mounts(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)

    assert apply(ctx) is True

    client = (ui / _GATEWAY_DIR_REL / "assistantEventClient.ts").read_text(encoding="utf-8")
    assert "export class AssistantEventClient" in client

    test_file = ui / _GATEWAY_DIR_REL / "assistantEventClient.test.ts"
    assert test_file.is_file()

    header = (ui / _HEADER_REL).read_text(encoding="utf-8")
    assert "import { AssistantEventClient }" in header
    assert "new AssistantEventClient(targetAssistantId)" in header
    assert "client.connect()" in header
    assert "client.disconnect()" in header
    assert "useEffect" in header


def test_lca_assistant_events_apply_is_idempotent(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True
    assert apply(ctx) is False


def test_lca_assistant_events_apply_raises_when_anchor_missing(tmp_path: Path) -> None:
    import pytest

    ui = tmp_path
    header = ui / _HEADER_REL
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text("export const x = 1;\n", encoding="utf-8")

    ctx = PatchContext(ui_dir=ui)
    with pytest.raises(SystemExit, match="lca_assistant_events"):
        apply(ctx)

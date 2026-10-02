"""Tests for AssistantAvatarImage component & patch (Task 11: avatar rendering).

Validates:
1. TSX component source presence (deploy/lobehub/patches/ui/AssistantAvatarImage.tsx).
2. Component contract: fetches GET /v1/assistants/{id}/avatar, listens to
   ``lca-assistant-avatar-changed``, uses NEXT_PUBLIC_LCA_TOKEN / x-lca-user-id
   headers, falls back to SVG mascot.
3. Patch integration: mounts in conversation Header and Assistant/index.tsx
   (message bubble customAvatarRender).
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext
from deploy.lobehub.patches.ui.assistant_avatar_image import apply, meta

_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantAvatarImage.tsx"
_HEADER_REL = "src/routes/(main)/agent/features/Conversation/Header/index.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"

_STUB_HEADER = """'use client';

import { Flexbox } from '@lobehub/ui';
import { createStaticStyles, cssVar } from 'antd-style';
import { memo, useCallback, useState } from 'react';
import { agentSelectors } from '@/store/agent/selectors';
import AssistantStatusDrawer from '@/features/Conversation/components/AssistantStatusDrawer';
import AssistantTopMascot from '@/features/Conversation/components/AssistantTopMascot';
import StandingFileFullscreenEditor from '@/features/Conversation/components/StandingFileFullscreenEditor';

import NavHeader from '@/features/NavHeader';
import { useAgentStore } from '@/store/agent';
import { useChatStore } from '@/store/chat';
import { topicSelectors } from '@/store/chat/selectors';

const Header = memo(() => {
  const agentId = useChatStore((s) => s.activeAgentId);
  const agentTitle = useAgentStore((s) =>
    agentId ? agentSelectors.getAgentMetaById(agentId)(s)?.title : undefined,
  );
  const targetAssistantId = agentId;

  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleEditFile = useCallback((filename: string, fileInfo: any) => {
    setEditingFile({
      filename,
      filePath: fileInfo.path,
      initialHash: fileInfo.content_hash,
    });
    setEditorOpen(true);
  }, []);

  return (
    <div className={headerStyles.container}>
      <NavHeader
        slotClassNames={{
          left: headerStyles.slotLeft,
          right: headerStyles.slotRight,
        }}
      >
        <Flexbox horizontal align={'center'} justify={'center'} style={{ pointerEvents: 'auto' }}>
          <AssistantTopMascot
            assistantId={targetAssistantId}
            name={agentTitle || '架构小助'}
            onOpenDrawer={() => setDrawerOpen(true)}
          />
        </Flexbox>
      </NavHeader>
    </div>
  );
});

export default Header;
"""

_STUB_ASSISTANT = """'use client';

import type { EmojiReaction } from '@lobechat/types';
import isEqual from 'fast-deep-equal';
import type { MouseEventHandler, ReactNode } from 'react';
import { memo, useCallback, useMemo } from 'react';

import { ChatItem } from '@/features/Conversation/ChatItem';
import AssistantAvatarWidget from '../components/AssistantAvatarWidget';

const AssistantMessage = memo<{ id: string; index: number }>(({ id }) => {
  const avatar = { title: 'assistant', avatar: '🤖' };
  const agentId = 'agent-1';
  const hasEmptyErrorMessage = false;
  const footerRender = null;

  return (
      <ChatItem
        showTitle
        avatar={avatar}
        belowMessage={hasEmptyErrorMessage ? footerRender : undefined}
        id={id}
      />
  );
});

export default AssistantMessage;
"""


def _component_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantAvatarImage.tsx"
    )


def _seed_ui(tmp_path: Path) -> Path:
    header = tmp_path / _HEADER_REL
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(_STUB_HEADER, encoding="utf-8")

    assistant = tmp_path / _ASSISTANT_REL
    assistant.parent.mkdir(parents=True, exist_ok=True)
    assistant.write_text(_STUB_ASSISTANT, encoding="utf-8")

    return tmp_path


def test_avatar_image_tsx_exists() -> None:
    path = _component_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_avatar_image_component_contract() -> None:
    content = _component_tsx_path().read_text(encoding="utf-8")

    # REST 端点与事件契约
    assert "lca-api/v1/assistants" in content
    assert "lca-assistant-avatar-changed" in content
    assert (
        "avatar_updated" in content
        or "avatar_video_ready" in content
        or "onAvatarChanged" in content
    )
    # 鉴权头
    assert "NEXT_PUBLIC_LCA_TOKEN" in content
    assert "x-lca-user-id" in content
    # 回退到 SVG 萌宠
    assert "AnimalSvgRenderer" in content or "fallback" in content
    # Props
    assert "assistantId" in content
    assert "size" in content


def test_avatar_image_patch_module_exists() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "assistant_avatar_image.py"
    )
    assert path.is_file(), "Missing patch module: assistant_avatar_image.py"


def test_avatar_image_patch_meta() -> None:
    assert meta.name == "assistant_avatar_image"
    assert meta.verify_marker == "AssistantAvatarImage"
    assert meta.verify_file == _COMPONENT_REL
    assert _HEADER_REL in meta.files
    assert _ASSISTANT_REL in meta.files


def test_avatar_image_apply_writes_component_and_mounts(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)

    assert apply(ctx) is True

    component = (ui / _COMPONENT_REL).read_text(encoding="utf-8")
    assert "export const AssistantAvatarImage" in component

    header = (ui / _HEADER_REL).read_text(encoding="utf-8")
    assert "import AssistantAvatarImage" in header
    assert "<AssistantAvatarImage" in header
    assert "assistantId={targetAssistantId}" in header

    assistant = (ui / _ASSISTANT_REL).read_text(encoding="utf-8")
    assert "import AssistantAvatarImage" in assistant
    assert "customAvatarRender" in assistant
    assert "assistantId={agentId}" in assistant


def test_avatar_image_apply_is_idempotent(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True
    assert apply(ctx) is False


def test_avatar_image_apply_raises_when_header_anchor_missing(tmp_path: Path) -> None:
    import pytest

    ui = tmp_path
    header = ui / _HEADER_REL
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text("export const x = 1;\n", encoding="utf-8")

    ctx = PatchContext(ui_dir=ui)
    with pytest.raises(SystemExit, match="assistant_avatar_image"):
        apply(ctx)

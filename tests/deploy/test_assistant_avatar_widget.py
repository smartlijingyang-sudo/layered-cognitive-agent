"""Tests for AssistantAvatarWidget & generated-image candidate flow (Task 12).

Validates:
1. TSX component source presence (deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx).
2. Candidate source is ``GET /v1/assistants/{id}/avatar/candidates`` (no static
   ``DEFAULT_CANDIDATES`` list).
3. Confirm activates via ``POST /v1/assistants/{id}/avatar/set`` with
   ``candidate_id``, broadcasts ``lca-assistant-avatar-changed`` and shows the
   first-person success copy 「我的头像换好了 🎉」.
4. Empty candidate pool renders the generate-first prompt; set failure keeps
   candidates visible and warns (antd ``message.warning``).
5. Patch integration into Assistant/index.tsx via assistant_avatar_widget.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.lobehub.engine import PatchContext
from deploy.lobehub.patches.ui.assistant_avatar_widget import apply, meta

_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantAvatarWidget.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"

_STUB_ASSISTANT = r"""'use client';

import type { EmojiReaction } from '@lobechat/types';
import isEqual from 'fast-deep-equal';
import type { MouseEventHandler, ReactNode } from 'react';
import { memo, useCallback, useMemo } from 'react';

import { ChatItem } from '@/features/Conversation/ChatItem';
import AssistantNamingWidget from '../components/AssistantNamingWidget';
import ConnectorAuthCard from '../components/ConnectorAuthCard';

const AssistantMessage = memo<{ id: string; index: number }>(({ id }) => {
    const content = '[widget:avatar_picker] 给你换几个新形象，挑一个吧';
    const agentId = 'agent-1';
    const avatar = { title: 'assistant', avatar: '🤖' };
    const hasEmptyErrorMessage = false;
    const footerRender = null;

    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));
    const isConnectorAuthWidget = Boolean(content && content.includes('[widget:connector_auth'));
    let connectorAuthProps: { appName?: string; authUrl?: string; connectionId?: string } | null = null;
    let cleanContent = isNamingWidget
        ? content.replace(/\[widget:name_picker\?token=[^\]]+\]/g, '').trim()
        : content;
    if (isConnectorAuthWidget && cleanContent) {
      cleanContent = cleanContent.replace(/\[widget:connector_auth\?[^\]]+\]/g, '').trim();
    }

    return (
      <ChatItem
        showTitle
        avatar={avatar}
        belowMessage={hasEmptyErrorMessage ? footerRender : undefined}
        id={id}
        messageExtra={
          <>
            {connectorAuthProps && (
              <ConnectorAuthCard
                appName={connectorAuthProps.appName}
                authUrl={connectorAuthProps.authUrl}
                connectionId={connectorAuthProps.connectionId}
              />
            )}
          </>
        }
      />
    );
});

export default AssistantMessage;
"""


def _widget_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantAvatarWidget.tsx"
    )


def _patch_py_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "assistant_avatar_widget.py"
    )


def _seed_ui(tmp_path: Path) -> Path:
    assistant = tmp_path / _ASSISTANT_REL
    assistant.parent.mkdir(parents=True, exist_ok=True)
    assistant.write_text(_STUB_ASSISTANT, encoding="utf-8")
    return tmp_path


# ── Component source contract ────────────────────────────────────


def test_avatar_widget_tsx_exists() -> None:
    path = _widget_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_avatar_widget_fetches_candidates_api() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "avatar/candidates" in content
    assert "candidate_id" in content
    assert "variants" in content


def test_avatar_widget_activates_via_set_endpoint() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "avatar/set" in content
    assert "candidate_id" in content
    assert "lca-assistant-avatar-changed" in content


def test_avatar_widget_first_person_success_copy() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "我的头像换好了 🎉" in content


def test_avatar_widget_empty_state_prompt() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "先让助理生成几个新形象吧" in content


def test_avatar_widget_set_failure_warns() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "message.warning" in content


def test_avatar_widget_no_static_default_candidates() -> None:
    content = _widget_tsx_path().read_text(encoding="utf-8")
    assert "DEFAULT_CANDIDATES" not in content
    assert "AnimalSvgRenderer" not in content


# ── Patch module contract ────────────────────────────────────────────


def test_assistant_avatar_widget_patch_module() -> None:
    path = _patch_py_path()
    assert path.is_file(), f"Missing patch module: {path}"
    content = path.read_text(encoding="utf-8")
    assert "AssistantAvatarWidget" in content
    assert "avatar/candidates" in content or "avatar/set" in content


def test_avatar_widget_patch_meta() -> None:
    assert meta.name == "assistant_avatar_widget"
    assert meta.verify_marker == "avatar/candidates"
    assert meta.verify_file == _COMPONENT_REL
    assert _COMPONENT_REL in meta.files
    assert _ASSISTANT_REL in meta.files


def test_avatar_widget_apply_writes_component_and_mounts(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)

    assert apply(ctx) is True

    component = (ui / _COMPONENT_REL).read_text(encoding="utf-8")
    assert "avatar/candidates" in component
    assert "avatar/set" in component
    assert "我的头像换好了 🎉" in component
    assert "DEFAULT_CANDIDATES" not in component

    assistant = (ui / _ASSISTANT_REL).read_text(encoding="utf-8")
    assert "import AssistantAvatarWidget" in assistant
    assert "isAvatarPickerWidget" in assistant
    assert "<AssistantAvatarWidget" in assistant
    assert "assistantId={agentId}" in assistant


def test_avatar_widget_apply_is_idempotent(tmp_path: Path) -> None:
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True
    assert apply(ctx) is False


def test_avatar_widget_apply_raises_when_anchor_missing(tmp_path: Path) -> None:
    ui = tmp_path
    assistant = ui / _ASSISTANT_REL
    assistant.parent.mkdir(parents=True, exist_ok=True)
    assistant.write_text("export const x = 1;\n", encoding="utf-8")

    ctx = PatchContext(ui_dir=ui)
    with pytest.raises(SystemExit, match="assistant_avatar_widget"):
        apply(ctx)

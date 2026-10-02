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

from deploy.lobehub.engine import (
    Manifest,
    PatchContext,
    PatchEntry,
    PatchModule,
    _compute_patch_hash,
    _read_manifest,
    _write_manifest,
    reconcile,
)
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
    assert "LCA-AVATAR-PICKER-MOUNT" in content


def test_avatar_widget_patch_meta() -> None:
    assert meta.name == "assistant_avatar_widget"
    assert meta.verify_marker == "LCA-AVATAR-PICKER-MOUNT"
    assert meta.verify_file == _ASSISTANT_REL
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
    assert "LCA-AVATAR-PICKER-MOUNT" in assistant


def test_avatar_widget_verify_targets_mount_marker(tmp_path: Path) -> None:
    """The patch's verify marker must live in Assistant/index.tsx next to the
    mount, so a reverted Assistant/index.tsx is detected by verify/reconcile."""
    ui = _seed_ui(tmp_path)
    ctx = PatchContext(ui_dir=ui)
    assert apply(ctx) is True

    assert meta.verify_file == _ASSISTANT_REL
    assert meta.verify_marker == "LCA-AVATAR-PICKER-MOUNT"
    assistant = (ui / _ASSISTANT_REL).read_text(encoding="utf-8")
    assert meta.verify_marker in assistant
    # Marker sits immediately above the mount.
    assert (
        "LCA-AVATAR-PICKER-MOUNT */}\n"
        "            {isAvatarPickerWidget && (\n"
        "              <AssistantAvatarWidget"
    ) in assistant


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


def test_avatar_widget_reconcile_restores_missing_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If Assistant/index.tsx loses the mount (e.g. upstream sync restores it),
    reconcile must detect the missing LCA-AVATAR-PICKER-MOUNT marker, restore
    both declared files from upstream, and mark the patch pending for re-apply.
    This is the regression the old verify_file=_COMPONENT_REL allowed: verify
    would report OK while the mount silently vanished."""
    from deploy.lobehub import engine as eng

    root = tmp_path / "repo"
    ui = root / "lobehub-ui"
    upstream = root / ".lobehub-upstream"
    monkeypatch.setattr(eng, "ROOT", root)
    monkeypatch.setattr(eng, "UI", ui)
    monkeypatch.setattr(eng, "MANIFEST_FILE", ui / ".lca-manifest.json")
    monkeypatch.setattr(eng, "LEGACY_STAMP", ui / ".lca-patched")
    monkeypatch.setattr(eng, "LEGACY_HASHES", ui / ".lca-patch-hashes")
    monkeypatch.setattr(eng, "_UPSTREAM", upstream)

    def write(rel: str, content: str) -> None:
        p = ui / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def write_upstream(rel: str, content: str) -> None:
        p = upstream / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # Upstream = pristine LobeHub files (no widget mount). UI matches upstream,
    # so the mount marker is absent and reconcile must treat the patch as broken.
    write_upstream(_COMPONENT_REL, "/* upstream component */\n")
    write_upstream(_ASSISTANT_REL, _STUB_ASSISTANT)
    write(_COMPONENT_REL, "/* upstream component */\n")
    write(_ASSISTANT_REL, _STUB_ASSISTANT)

    pm = PatchModule(meta=meta, apply=apply)
    sha = _compute_patch_hash(pm)

    manifest = Manifest()
    manifest.patches["assistant_avatar_widget"] = PatchEntry(
        name="assistant_avatar_widget",
        status="applied",
        source_sha=sha,
        written=[_COMPONENT_REL, _ASSISTANT_REL],
    )
    _write_manifest(manifest)

    reconcile(modules=[pm])

    # Files restored to upstream baseline; patch marked pending.
    assert (ui / _ASSISTANT_REL).read_text() == _STUB_ASSISTANT
    assert (ui / _COMPONENT_REL).read_text() == "/* upstream component */\n"
    assert _read_manifest().patches["assistant_avatar_widget"].status == "pending"

    # Re-apply re-injects the mount + marker.
    ctx = PatchContext(ui_dir=ui, manifest=_read_manifest())
    ctx._current_patch = "assistant_avatar_widget"
    assert pm.apply(ctx)
    assistant_text = (ui / _ASSISTANT_REL).read_text()
    assert "LCA-AVATAR-PICKER-MOUNT" in assistant_text
    assert "<AssistantAvatarWidget" in assistant_text
    assert "assistantId={agentId}" in assistant_text

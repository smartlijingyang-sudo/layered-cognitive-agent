"""Patch: render multi-agent collaboration team chips and folded specialist sections."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/CollaborationTeamBar.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "CollaborationTeamBar.tsx"

meta = PatchMeta(
    name="collaboration_team_bar",
    description="Render multi-agent collaboration team chips and folded specialist sections",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide Grok-style team members bar and folded specialist findings in LobeHub run view",
    technical_detail=(
        "Creates CollaborationTeamBar.tsx and patches Assistant/index.tsx to pass it into aboveMessage"
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="CollaborationTeamBar",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 CollaborationTeamBar.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[collaboration_team_bar] missing patch source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    # 添加 import
    if "import CollaborationTeamBar from '../components/CollaborationTeamBar';" not in assistant_text:
        assistant_text = assistant_text.replace(
            "import MessageBranch from '../components/MessageBranch';",
            "import MessageBranch from '../components/MessageBranch';\nimport CollaborationTeamBar from '../components/CollaborationTeamBar';",
        )

    # 替换 aboveMessage={null}
    if "aboveMessage={null}" in assistant_text:
        assistant_text = assistant_text.replace(
            "aboveMessage={null}",
            "aboveMessage={<CollaborationTeamBar content={content} extra={extra} metadata={metadata} />}",
        )

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed

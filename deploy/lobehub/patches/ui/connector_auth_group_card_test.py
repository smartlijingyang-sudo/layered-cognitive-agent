"""Patch: install ConnectorAuthGroupCard regression test into lobehub-ui.

Pins that ContentBlock (AssistantGroup path) strips the
``[widget:connector_auth]`` tag and renders ``ConnectorAuthCard`` with the
parsed intentId / connectionId / appName — the composioConnect rendering path.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_TEST_REL = (
    "src/features/Conversation/Messages/AssistantGroup/components/ConnectorAuthGroupCard.test.tsx"
)
_SOURCE_NAME = "ConnectorAuthGroupCard.test.tsx"

meta = PatchMeta(
    name="connector_auth_group_card_test",
    description="Install regression test for ConnectorAuthCard in AssistantGroup ContentBlock",
    files=(_TEST_REL,),
    risk="low",
    category="ui",
    depends_on=("connector_auth_group_card",),
    why="Pin the composioConnect connector-card rendering path with a regression test",
    technical_detail=(
        "Writes ConnectorAuthGroupCard.test.tsx next to ContentBlock.tsx so the "
        "test verifies tag stripping and ConnectorAuthCard prop forwarding."
    ),
    verify_file=_TEST_REL,
    verify_marker="connector-card",
)


def apply(ctx: PatchContext) -> bool:
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[connector_auth_group_card_test] missing patch source: {source}")
    return ctx.write_if_changed(_TEST_REL, source.read_text(encoding="utf-8"))

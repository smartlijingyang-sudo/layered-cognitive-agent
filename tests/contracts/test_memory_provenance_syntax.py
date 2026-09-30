"""INV-PROVENANCE-SYNTAX — every curated assertion carries a provenance suffix."""

from __future__ import annotations

import re

from lca.infrastructure.memory.contextfiles.domain.curated import (
    CuratedClaim,
    render_curated_markdown,
)

_PATTERN = re.compile(r".*This came from .+ when .+(?:, recorded \d{4}-\d{2}-\d{2})?\.")


def _claims() -> list[CuratedClaim]:
    return [
        CuratedClaim(
            claim_id="c1",
            kind="fact",
            body="用户住在杭州",
            importance=0.9,
            source="user",
            trigger="用户要求记下",
            recorded_on="2026-09-30",
        ),
        CuratedClaim(
            claim_id="c2",
            kind="preference",
            body="偏好短回复",
            importance=0.6,
            source="user",
            trigger="用户纠正回复长度",
        ),
    ]


def test_every_bullet_matches_the_provenance_pattern() -> None:
    text = render_curated_markdown(_claims(), source_note="记录在 `memory/semantic.json`。")
    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(bullets) == 2
    for bullet in bullets:
        assert _PATTERN.match(bullet), bullet


def test_recorded_on_is_optional() -> None:
    text = render_curated_markdown(_claims(), source_note="")
    assert "recorded 2026-09-30" in text
    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    for bullet in bullets:
        assert _PATTERN.match(bullet), bullet


def test_projection_declares_itself_a_projection() -> None:
    text = render_curated_markdown(_claims(), source_note="记录在 `memory/semantic.json`。")
    assert "投影" in text
    assert "下次写入会重写本文件" in text

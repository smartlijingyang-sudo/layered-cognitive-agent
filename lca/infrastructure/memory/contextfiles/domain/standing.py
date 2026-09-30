"""Standing-file assembly and post-compaction re-injection.

The bytes come from a fresh disk read supplied by the caller. This module
only decides which of those bytes survive a character budget. History is
what gets cut. Standing files are packed in a fixed order, and a single
long file cannot spend the whole budget while a later file is still waiting.
"""

from __future__ import annotations

from collections.abc import Sequence

STANDING_ORDER: tuple[str, ...] = (
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
    "AGENTS.md",
    "TOOLS.md",
)


def render_injected(name: str, body: str) -> str:
    """Wrap one standing file so a later reload can find its bounds."""

    return f"<!-- INJECTED FILE: {name} -->\n{body.strip()}\n<!-- END INJECTED FILE: {name} -->"


def assemble_standing(
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
) -> str:
    """Pack standing documents in ``STANDING_ORDER`` within ``budget_chars``."""

    if budget_chars <= 0:
        return ""
    by_name = dict(files)
    pending = [(name, by_name.get(name, "")) for name in STANDING_ORDER]
    pending = [(name, body) for name, body in pending if body.strip()]
    remaining = budget_chars
    blocks: list[str] = []
    for index, (name, body) in enumerate(pending):
        others_follow = index < len(pending) - 1
        cap = _cap(remaining, others_follow=others_follow)
        block = _fit(name, body, cap)
        if block is None:
            continue
        blocks.append(block)
        remaining -= len(block) + 2
        if remaining <= 0:
            break
    return "\n\n".join(blocks)[:budget_chars]


def rehydrate_after_compaction(
    history: str,
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
) -> str:
    """Drop old history first, then append a fresh standing snapshot.

    ``files`` must already be the current disk contents. Injected blocks that
    were sitting inside ``history`` are not reused.
    """

    standing_budget = max(budget_chars // 2, 0)
    standing = assemble_standing(files, budget_chars=standing_budget)
    if not standing:
        return history[-budget_chars:] if budget_chars > 0 else ""
    gap = "\n\n" if history.strip() else ""
    room = budget_chars - len(standing) - len(gap)
    if room <= 0:
        return standing[:budget_chars]
    trimmed = _strip_injected(history)[-room:]
    if not trimmed.strip():
        return standing
    return f"{trimmed}{gap}{standing}"


def _cap(remaining: int, *, others_follow: bool) -> int:
    if not others_follow:
        return remaining
    return min(remaining, max(remaining // 2, min(240, remaining)))


def _fit(name: str, body: str, cap: int) -> str | None:
    wrapped = render_injected(name, body)
    if len(wrapped) <= cap:
        return wrapped
    marker = render_injected(name, "")
    room = cap - len(marker)
    if room < 20:
        return None
    return render_injected(name, body.strip()[:room])


def _strip_injected(history: str) -> str:
    lines: list[str] = []
    skipping = False
    for line in history.splitlines():
        if line.startswith("<!-- INJECTED FILE:"):
            skipping = True
            continue
        if line.startswith("<!-- END INJECTED FILE:"):
            skipping = False
            continue
        if not skipping:
            lines.append(line)
    return "\n".join(lines).strip()


__all__ = [
    "STANDING_ORDER",
    "assemble_standing",
    "rehydrate_after_compaction",
    "render_injected",
]

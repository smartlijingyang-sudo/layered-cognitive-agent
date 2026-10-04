"""Standing-file assembly and post-compaction re-injection.

The bytes come from a fresh disk read supplied by the caller. This module
only decides which of those bytes survive a character budget. History is
what gets cut. File order and the live-copy note come from the layout.
A single long file cannot spend the whole budget while a later file is
still waiting.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Sequence

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout

logger = logging.getLogger(__name__)


class StandingTruncationError(RuntimeError):
    """Raised when a protected standing section is dropped in strict mode.

    Enable with ``LCA_STRICT_STANDING=1`` (development). Production only logs.
    """


_SECTION_HEADING_RE = re.compile(r"^#{2,3}\s")


def split_sections(body: str) -> list[tuple[str | None, str]]:
    """Split a markdown body into ``(heading, section_text)`` in order.

    Text before the first ``##``/``###`` heading is the preamble section
    (heading ``None``). The heading line belongs to its section.
    """
    sections: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    current: list[str] = []
    for line in body.splitlines():
        if _SECTION_HEADING_RE.match(line):
            if current or heading is not None:
                sections.append((heading, current))
            heading = line.strip()
            current = [line]
        else:
            current.append(line)
    if current or heading is not None:
        sections.append((heading, current))
    return [(h, "\n".join(ls).strip()) for h, ls in sections if "\n".join(ls).strip()]


def pack_sections(
    docs: Sequence[tuple[str, str]],
    budget: int,
    *,
    on_drop_section: Callable[[str, str | None], None] | None = None,
) -> tuple[list[str], int]:
    """Pack documents section-by-section within ``budget``.

    Every markdown section (``##``/``###``) is whole-in or whole-dropped;
    sections are never cut mid-way. Returns ``(blocks, remaining)`` in
    document order. ``on_drop_section(name, heading)`` fires per dropped
    section.
    """
    blocks: list[str] = []
    remaining = budget
    for name, body in docs:
        kept: list[str] = []
        for heading, section in split_sections(body):
            candidate = "\n\n".join([*kept, section])
            if len(render_injected(name, candidate)) > remaining:
                if on_drop_section is not None:
                    on_drop_section(name, heading)
                continue
            kept.append(section)
        if not kept:
            continue
        block = render_injected(name, "\n\n".join(kept))
        blocks.append(block)
        remaining -= len(block) + 2
        if remaining <= 0:
            break
    return blocks, remaining


def _warn_protected_drop(name: str, heading: str | None) -> None:
    logger.warning("standing section dropped name=%s heading=%s", name, heading)
    if os.environ.get("LCA_STRICT_STANDING") == "1":
        raise StandingTruncationError(f"protected standing section dropped: {name} {heading}")


def render_injected(name: str, body: str) -> str:
    """Wrap one standing file so a later reload can find its bounds."""

    return f"<!-- INJECTED FILE: {name} -->\n{body.strip()}\n<!-- END INJECTED FILE: {name} -->"


def assemble_standing(
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
    order: Sequence[str] | None = None,
    platform_files: Sequence[str] = (),
    protected_files: Sequence[str] = (),
    protected_budget_chars: int = 0,
) -> str:
    """Assemble the three-tier standing backstory.

    - Tier 1 (platform): injected whole, outside any budget, zero truncation.
    - Tier 2 (protected): packed by markdown section within
      ``protected_budget_chars``; dropped sections log a warning
      (``LCA_STRICT_STANDING=1`` raises instead).
    - Tier 3 (projection): packed by section within
      ``budget_chars - protected_budget_chars``.

    ``order`` defaults to the packaged layout. ``budget_chars`` covers tiers
    2+3; tier 1 never counts against it. Sections are never cut mid-way in
    any tier. Output follows ``order``; tiers only decide the packing rule
    (platform: whole/outside budget; protected: section-packed in its own
    budget with drop warnings; projection: section-packed in the rest).
    """
    names = list(dict.fromkeys([*platform_files, *_order(order)]))
    platform_set = set(platform_files)
    protected_set = set(protected_files)
    by_name = dict(files)
    pending = [(name, by_name.get(name, "")) for name in names]
    pending = [(name, body) for name, body in pending if body.strip()]

    blocks: list[str] = []
    remaining_protected = protected_budget_chars
    remaining_projection = max(budget_chars - protected_budget_chars, 0)
    for name, body in pending:
        if name in platform_set:
            blocks.append(render_injected(name, body.strip()))
        elif name in protected_set:
            packed, remaining_protected = pack_sections(
                [(name, body)],
                remaining_protected,
                on_drop_section=_warn_protected_drop,
            )
            blocks.extend(packed)
        else:
            packed, remaining_projection = pack_sections([(name, body)], remaining_projection)
            blocks.extend(packed)
    return "\n\n".join(blocks)


def rehydrate_after_compaction(
    history: str,
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
    order: Sequence[str] | None = None,
) -> str:
    """Drop old history first, then append a fresh standing snapshot.

    ``files`` must already be the current disk contents. Injected blocks that
    were sitting inside ``history`` are not reused.
    """

    standing_budget = max(budget_chars // 2, 0)
    standing = assemble_standing(files, budget_chars=standing_budget, order=order)
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


def refresh_injected(
    text: str,
    files: Sequence[tuple[str, str]],
    *,
    order: Sequence[str] | None = None,
    live_note: str | None = None,
) -> str:
    """Replace injected standing blocks with the supplied file bodies.

    Text that never used the injection markers is returned unchanged, so a
    historical system prompt without standing blocks stays intact. Bodies are
    not summarized. A file that is missing or blank drops its old block.
    A standing file that was not in the text is appended, in layout order.
    """

    if "<!-- INJECTED FILE:" not in text:
        return text
    names = _order(order)
    note = packaged_layout().live_note if live_note is None else live_note
    by_name = {name: body.strip() for name, body in files}
    lines = text.splitlines()
    output: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(lines):
        name = _injected_name(lines[index])
        if name is None:
            output.append(lines[index])
            index += 1
            continue
        index += 1
        while index < len(lines) and _injected_name(lines[index], end=True) is None:
            index += 1
        if index < len(lines):
            index += 1
        seen.add(name)
        body = by_name.get(name, "")
        if body:
            _append_block(output, name, body)
    for name in names:
        if name in seen:
            continue
        body = by_name.get(name, "")
        if body:
            _append_block(output, name, body)
    _ensure_live_note(output, note)
    return "\n".join(output).strip()


def _append_block(output: list[str], name: str, body: str) -> None:
    if output and output[-1] != "":
        output.append("")
    output.extend(render_injected(name, body).splitlines())


def _order(order: Sequence[str] | None) -> tuple[str, ...]:
    if order is None:
        return packaged_layout().standing_files
    return tuple(order)


def _ensure_live_note(output: list[str], live_note: str) -> None:
    if not live_note or live_note in output:
        return
    for index, line in enumerate(output):
        if "<!-- INJECTED FILE:" in line:
            output.insert(index, live_note)
            output.insert(index + 1, "")
            return


def _injected_name(line: str, *, end: bool = False) -> str | None:
    prefix = "<!-- END INJECTED FILE:" if end else "<!-- INJECTED FILE:"
    marker = f"{prefix} "
    position = line.find(marker)
    if position < 0 or not line.endswith("-->"):
        return None
    return line[position + len(marker) : -len("-->")].strip() or None


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
    "StandingTruncationError",
    "assemble_standing",
    "pack_sections",
    "refresh_injected",
    "rehydrate_after_compaction",
    "render_injected",
    "split_sections",
]

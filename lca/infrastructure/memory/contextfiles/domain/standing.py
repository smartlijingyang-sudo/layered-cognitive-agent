"""Standing-file assembly and post-compaction re-injection.

The bytes come from a fresh disk read supplied by the caller. This module
only decides which of those bytes survive a character budget. History is
what gets cut. File order and the live-copy note come from the layout.
A single long file cannot spend the whole budget while a later file is
still waiting.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout


def render_injected(name: str, body: str) -> str:
    """Wrap one standing file so a later reload can find its bounds."""

    return f"<!-- INJECTED FILE: {name} -->\n{body.strip()}\n<!-- END INJECTED FILE: {name} -->"


def assemble_standing(
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
    order: Sequence[str] | None = None,
) -> str:
    """Pack standing documents in ``order`` within ``budget_chars``.

    ``order`` defaults to the packaged layout. A home passes its own list
    after merging ``memory/contextfiles.toml``.
    """

    if budget_chars <= 0:
        return ""
    names = _order(order)
    by_name = dict(files)
    pending = [(name, by_name.get(name, "")) for name in names]
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
        if line.startswith("<!-- INJECTED FILE:"):
            output.insert(index, live_note)
            output.insert(index + 1, "")
            return


def _injected_name(line: str, *, end: bool = False) -> str | None:
    prefix = "<!-- END INJECTED FILE:" if end else "<!-- INJECTED FILE:"
    if not line.startswith(prefix) or not line.endswith("-->"):
        return None
    return line[len(prefix) : -len("-->")].strip() or None


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
    "assemble_standing",
    "refresh_injected",
    "rehydrate_after_compaction",
    "render_injected",
]

"""Extended catalog events wired through ``meta_event_emit`` production seams."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import lca.contracts.harness.memory.events  # noqa: F401
from lca.contracts.harness.tasks.session import event_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LCA_ROOT = _REPO_ROOT / "lca"
_META_EMIT_MODULE = _LCA_ROOT / "infrastructure" / "observability" / "meta_event_emit.py"

_META_EVENT_EMITTERS: dict[str, tuple[str, ...]] = {
    "skill.catalog.published.v1": ("emit_skill_catalog_published",),
    "skill.loaded.v1": ("emit_skill_loaded",),
    "skill.activated.v1": ("emit_skill_activated",),
    "skill.searched.v1": ("emit_skill_searched",),
    "skill.routed.v1": ("emit_skill_routed",),
    "context.injected.v1": ("emit_context_injected",),
    "attachment.committed.v1": ("emit_attachment_committed", "emit_run_attachments"),
    "inbox.spliced.v1": ("emit_inbox_spliced",),
    "command.rejected.v1": ("emit_command_rejected",),
    "feedback.record.v1": ("emit_feedback_record",),
}

# Wired outside meta_event_emit; architecture guard uses explicit module patterns.
_SPECIAL_PRODUCERS: dict[str, tuple[str, ...]] = {
    "session.title.v1": (r"TITLE_EVENT_TYPE", r"session\.title\.v1"),
    "session.end_seed.v1": (r"SESSION_END_SEED_TYPE", r"session\.end_seed\.v1"),
}


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[tuple[str, int, str]]:
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            ["rg", "--line-number", "--no-heading", "--color", "never", "--glob", "*.py", pattern, str(root)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        rows: list[tuple[str, int, str]] = []
        for raw in result.stdout.splitlines():
            if not raw.strip() or ":" not in raw:
                continue
            path_part, rest = raw.split(":", 1)
            if ":" not in rest:
                continue
            lineno_str, line = rest.split(":", 1)
            rel = Path(path_part).resolve()
            try:
                rel = rel.relative_to(_REPO_ROOT)
            except ValueError:
                rel = Path(path_part)
            rows.append((rel.as_posix(), int(lineno_str), line))
        return rows
    rows = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(pattern, line):
                rows.append((rel, lineno, line))
    return rows


def _meta_event_types() -> tuple[str, ...]:
    return tuple(sorted(_META_EVENT_EMITTERS) + sorted(_SPECIAL_PRODUCERS))


def _production_sites(event_type: str) -> list[str]:
    patterns: list[str] = []
    for fn in _META_EVENT_EMITTERS.get(event_type, ()):
        patterns.append(rf"\b{re.escape(fn)}\s*\(")
    for token in _SPECIAL_PRODUCERS.get(event_type, ()):
        patterns.append(token)

    catalog_cls = event_registry()[event_type].__name__
    patterns.append(re.escape(catalog_cls) + r"\(")

    seen: set[tuple[str, int]] = set()
    sites: list[str] = []
    for pattern in patterns:
        for rel, lineno, line in _rg(pattern, _LCA_ROOT):
            if rel.endswith(_META_EMIT_MODULE.relative_to(_REPO_ROOT).as_posix()) and "def emit_" in line:
                continue
            if rel.endswith("contracts/harness/memory/events.py"):
                continue
            key = (rel, lineno)
            if key in seen:
                continue
            seen.add(key)
            sites.append(f"{rel}:{lineno}:{line.strip()}")
    return sorted(sites)


class TestSessionMetaEventProducers:
    @pytest.mark.parametrize("event_type", _meta_event_types())
    def test_meta_catalog_event_has_production_site(self, event_type: str) -> None:
        sites = _production_sites(event_type)
        assert sites, (
            f"{event_type!r} has no production call site in lca/ "
            f"(expected meta_event_emit helper or documented special producer)."
        )

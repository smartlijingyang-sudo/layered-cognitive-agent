"""Catalog session events must have production call sites in ``lca/``.

Guards the lifecycle map (``docs/specs/session-event-lifecycle-map.md`` §2):
required catalog types are emitted from production seams — primarily
``lca/infrastructure/session/lifecycle_emit.py``, ``emit()``, or
``Session.append`` with a typed wire name — not only consumed or declared.

Harness-only exceptions are explicit until wired; see ``ALLOW_HARNESS_ONLY``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import lca.contracts.harness.memory.events  # noqa: F401 — register @session_event catalog
from lca.contracts.harness.tasks.session import event_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LCA_ROOT = _REPO_ROOT / "lca"
_CATALOG_MODULE = _LCA_ROOT / "contracts" / "harness" / "memory" / "events.py"

# Documented harness-only exceptions (session-event-lifecycle-map.md §2).
# Skill domain + transport/meta events are covered by test_session_meta_event_producers.py.
ALLOW_HARNESS_ONLY: frozenset[str] = frozenset(
    {
        "session.title.v1",
        "session.end_seed.v1",
    }
)

# lifecycle_emit seam helpers → catalog wire types they produce.
_LIFECYCLE_SEAM_PRODUCERS: dict[str, tuple[str, ...]] = {
    "turn.started.v1": ("begin_turn",),
    "turn.ended.v1": ("end_turn",),
    "step.started.v1": ("begin_step", "request_model"),
    "step.ended.v1": ("end_step", "end_turn"),
    "model.requested.v1": ("request_model",),
    "model.completed.v1": ("complete_model",),
    "model.failed.v1": ("fail_model",),
    "message.accepted.v1": ("accept_user_message",),
    "assistant.responded.v1": ("complete_model",),
    "session.created.v1": ("create_session",),
    "session.checkpoint.v1": ("checkpoint", "emit_approval_pause_from_result"),
    "approval.persisted.v1": ("persist_approval", "emit_approval_pause_from_result"),
}

_CONSUMER_LINE = re.compile(
    r"(?:^\s*class\s+\w+)"
    r"|(?:@session_event\()"
    r"|(?:\b(?:if|elif)\b.*\b(?:event\.type|event_type)\s*==)"
    r"|(?:SessionRecoveryError\()"
    r"|(?:frozenset\(\{)"
    r"|(?:^\s*[_A-Z][A-Z0-9_]*\s*=\s*frozenset)"
)

_APPEND_TYPE = re.compile(
    r"""\.append\s*\(\s*['"](?P<type>[^'"]+)['"]"""
    r"""|"""
    r"""(?<![.\w])append\s*\(\s*['"](?P<type2>[^'"]+)['"]"""
)

_TYPE_KW = re.compile(r"""type\s*=\s*['"](?P<type>[^'"]+)['"]""")


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[tuple[str, int, str]]:
    """Return ``(relpath, lineno, line)`` matches under ``root``."""
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                "--glob",
                "*.py",
                pattern,
                str(root),
            ],
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
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(pattern, line):
                rows.append((rel, lineno, line))
    return rows


def _is_lifecycle_required(event_type: str) -> bool:
    if event_type in ALLOW_HARNESS_ONLY:
        return False
    if event_type.startswith("skill."):
        return False
    if event_type.startswith(("turn.", "step.", "model.")):
        return True
    if event_type.startswith("approval."):
        return True
    return event_type in {
        "session.created.v1",
        "session.checkpoint.v1",
        "message.accepted.v1",
        "assistant.responded.v1",
    }


def _class_name_for(event_type: str) -> str:
    cls = event_registry()[event_type]
    return cls.__name__


def _is_production_line(line: str, *, event_type: str, class_name: str) -> bool:
    if _CONSUMER_LINE.search(line):
        return False
    if f"{class_name}(" in line and not line.lstrip().startswith("class "):
        return True
    for match in _APPEND_TYPE.finditer(line):
        wire = match.group("type") or match.group("type2")
        if wire == event_type:
            return True
    for match in _TYPE_KW.finditer(line):
        if match.group("type") == event_type:
            return True
    seam_fns = _LIFECYCLE_SEAM_PRODUCERS.get(event_type, ())
    return any(re.search(rf"\b{re.escape(fn)}\s*\(", line) for fn in seam_fns)


def _production_sites(event_type: str) -> list[str]:
    class_name = _class_name_for(event_type)
    patterns = [
        re.escape(class_name) + r"\(",
        re.escape(event_type),
    ]
    for fn in _LIFECYCLE_SEAM_PRODUCERS.get(event_type, ()):
        patterns.append(rf"\b{re.escape(fn)}\s*\(")

    seen: set[tuple[str, int]] = set()
    sites: list[str] = []
    for pattern in patterns:
        for rel, lineno, line in _rg(pattern, _LCA_ROOT):
            if rel == _CATALOG_MODULE.relative_to(_REPO_ROOT).as_posix():
                continue
            key = (rel, lineno)
            if key in seen:
                continue
            if _is_production_line(line, event_type=event_type, class_name=class_name):
                seen.add(key)
                sites.append(f"{rel}:{lineno}:{line.strip()}")
    return sorted(sites)


def _required_catalog_types() -> tuple[str, ...]:
    return tuple(
        sorted(event_type for event_type in event_registry() if _is_lifecycle_required(event_type))
    )


class TestSessionLifecycleProducers:
    """Lifecycle-map required catalog events have ``lca/`` production seams."""

    def test_catalog_registry_non_empty(self) -> None:
        assert event_registry(), "event_registry() must list @session_event types"

    @pytest.mark.parametrize("event_type", _required_catalog_types())
    def test_required_event_has_production_site(self, event_type: str) -> None:
        sites = _production_sites(event_type)
        assert sites, (
            f"{event_type!r} is lifecycle-required but has no production call site in lca/ "
            f"(expected lifecycle_emit, emit(), Session.append wire name, or harness emit). "
            f"If harness-only, add to ALLOW_HARNESS_ONLY with lifecycle-map §2 reference."
        )

"""Load the context-file layout from TOML.

``layout.toml`` next to this package is the default. A home may replace any
field in the relative path named by ``home_override``. Callers that have a
home must use ``layout_for_home`` so that overlay is visible. A missing
overlay is normal. A broken overlay is ignored and the packaged layout stays
in force, so a bad edit cannot blank persona assembly.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

_PACKAGE_FILE = Path(__file__).resolve().parent.parent / "layout.toml"

_FIELDS = (
    "standing_files",
    "platform_files",
    "platform_heading",
    "protected_files",
    "protected_budget_chars",
    "people_dir",
    "people_index",
    "groups_dir",
    "groups_index",
    "live_note",
    "home_override",
    "backstory_budget_chars",
    "agents_file",
    "agents_heading",
    "projection_file",
    "side_chats_dir",
    "side_chat_memory_file",
    "trail_dir",
    "alignment_synthesis_file",
    "index_db_file",
)


@dataclass(frozen=True, slots=True)
class ContextLayout:
    """Names and budgets for one assistant home's context files."""

    standing_files: tuple[str, ...]
    platform_files: tuple[str, ...]
    platform_heading: str
    protected_files: tuple[str, ...]
    protected_budget_chars: int
    people_dir: str
    people_index: str
    groups_dir: str
    groups_index: str
    live_note: str
    home_override: str
    backstory_budget_chars: int
    agents_file: str
    agents_heading: str
    projection_file: str
    side_chats_dir: str
    side_chat_memory_file: str
    trail_dir: str
    alignment_synthesis_file: str
    index_db_file: str

    def person_page_path(self, slug: str) -> str:
        """Relative path of one person page."""

        return f"{self.people_dir}/{slug}.md"

    @property
    def people_index_path(self) -> str:
        """Relative path of the people index."""

        return f"{self.people_dir}/{self.people_index}"

    def group_page_path(self, slug: str) -> str:
        """Relative path of one group page."""

        return f"{self.groups_dir}/{slug}.md"

    @property
    def groups_index_path(self) -> str:
        """Relative path of the groups index."""

        return f"{self.groups_dir}/{self.groups_index}"

    def side_chat_memory_path(self, chat_id: str) -> str:
        """Relative path of one side chat's branch memory file."""

        return f"{self.side_chats_dir}/{chat_id}/{self.side_chat_memory_file}"

    @property
    def alignment_synthesis_path(self) -> str:
        """Relative path of the alignment synthesis document."""

        return self.alignment_synthesis_file

    @property
    def index_db_path(self) -> str:
        """Relative path of the full-text index database."""

        return self.index_db_file


def read_layout(text: str) -> ContextLayout:
    """Parse a complete layout document."""

    data = _table(text)
    missing = [key for key in _FIELDS if key not in data]
    if missing:
        raise ValueError(f"layout missing {', '.join(missing)}")
    return _from_mapping(data)


def merge_layout(base: ContextLayout, text: str) -> ContextLayout:
    """Replace fields present in ``text``. Absent fields stay on ``base``.

    Tier invariants are sanitized rather than rejected: protected files not
    in the new standing list are dropped, and the protected budget is clamped
    to the total, so a home that customizes its file list or shrinks the
    budget keeps working instead of falling back to the packaged layout.
    """

    data = _table(text)
    if not data:
        return base
    current = {key: getattr(base, key) for key in _FIELDS}
    current.update(data)
    return _from_mapping(current, strict=False)


@lru_cache(maxsize=1)
def packaged_layout() -> ContextLayout:
    """Return the layout shipped with this package."""

    return read_layout(_PACKAGE_FILE.read_text(encoding="utf-8"))


def layout_for_home(home: str | Path) -> ContextLayout:
    """Return the packaged layout overlaid with the home file when it parses."""

    base = packaged_layout()
    override = Path(home) / base.home_override
    try:
        text = override.read_text(encoding="utf-8")
    except OSError:
        return base
    try:
        return merge_layout(base, text)
    except ValueError as exc:
        logger.warning("context layout override ignored path=%s error=%s", override, exc)
        return base


def _table(text: str) -> dict[str, object]:
    data = tomllib.loads(text)
    if not isinstance(data, dict):
        raise ValueError("layout must be a table")
    unknown = sorted(set(data) - set(_FIELDS))
    if unknown:
        raise ValueError(f"unknown layout keys: {', '.join(unknown)}")
    return data


def _from_mapping(data: dict[str, object], *, strict: bool = True) -> ContextLayout:
    standing = data["standing_files"]
    if not isinstance(standing, (list, tuple)) or not standing:
        raise ValueError("standing_files must be a non-empty list")
    names = tuple(_relative(item, key="standing_files") for item in standing)
    if len(set(names)) != len(names):
        raise ValueError("standing_files must be unique")
    platform = data["platform_files"]
    if not isinstance(platform, (list, tuple)):
        raise ValueError("platform_files must be a list")
    platform_names = tuple(
        _relative(item, key="platform_files", single_segment=True) for item in platform
    )
    if len(set(platform_names)) != len(platform_names):
        raise ValueError("platform_files must be unique")
    protected = data["protected_files"]
    if not isinstance(protected, (list, tuple)):
        raise ValueError("protected_files must be a list")
    protected_names = tuple(_relative(item, key="protected_files") for item in protected)
    if len(set(protected_names)) != len(protected_names):
        raise ValueError("protected_files must be unique")
    if strict:
        if not set(protected_names) <= set(names):
            raise ValueError("protected_files must be a subset of standing_files")
        if set(platform_names) & set(names):
            raise ValueError("platform_files must not overlap standing_files")
    else:
        protected_names = tuple(f for f in protected_names if f in names)
        platform_names = tuple(f for f in platform_names if f not in names)
    total_budget = _positive_int(data["backstory_budget_chars"], key="backstory_budget_chars")
    protected_budget = data["protected_budget_chars"]
    if isinstance(protected_budget, bool) or not isinstance(protected_budget, int):
        raise ValueError("protected_budget_chars must be an integer")
    if protected_budget < 0:
        raise ValueError("protected_budget_chars must be >= 0")
    if strict and protected_budget > total_budget:
        raise ValueError("protected_budget_chars must not exceed backstory_budget_chars")
    protected_budget = min(protected_budget, total_budget)
    return ContextLayout(
        standing_files=names,
        platform_files=platform_names,
        platform_heading=_line(data["platform_heading"], key="platform_heading"),
        protected_files=protected_names,
        protected_budget_chars=protected_budget,
        people_dir=_relative(data["people_dir"], key="people_dir"),
        people_index=_relative(data["people_index"], key="people_index", single_segment=True),
        groups_dir=_relative(data["groups_dir"], key="groups_dir"),
        groups_index=_relative(data["groups_index"], key="groups_index", single_segment=True),
        live_note=_line(data["live_note"], key="live_note"),
        home_override=_relative(data["home_override"], key="home_override"),
        backstory_budget_chars=total_budget,
        agents_file=_relative(data["agents_file"], key="agents_file"),
        agents_heading=_line(data["agents_heading"], key="agents_heading"),
        projection_file=_relative(data["projection_file"], key="projection_file"),
        side_chats_dir=_relative(data["side_chats_dir"], key="side_chats_dir"),
        side_chat_memory_file=_relative(
            data["side_chat_memory_file"],
            key="side_chat_memory_file",
            single_segment=True,
        ),
        trail_dir=_relative(data["trail_dir"], key="trail_dir"),
        alignment_synthesis_file=_relative(
            data["alignment_synthesis_file"],
            key="alignment_synthesis_file",
        ),
        index_db_file=_relative(data["index_db_file"], key="index_db_file"),
    )


def _relative(value: object, *, key: str, single_segment: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a relative path")
    text = value.strip()
    if not text or text.startswith(("/", "\\")) or "\\" in text or "\x00" in text:
        raise ValueError(f"{key} must be a relative path")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"{key} must be a relative path")
    if single_segment and len(path.parts) != 1:
        raise ValueError(f"{key} must be a single path segment")
    return text


def _line(value: object, *, key: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\x00" in value:
        raise ValueError(f"{key} must be a single line")
    return value.strip()


def _positive_int(value: object, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def allowed_root_entries(layout: ContextLayout | None = None) -> frozenset[str]:
    """Return the root-level entries an assistant home may contain.

    ADR-0254 §3.1 defines the five standing files plus the memory, side-chat,
    dreams, revisions and skill/workspace directories. The host's own
    manifest, profile and override files are allowed too.
    """

    chosen = packaged_layout() if layout is None else layout
    roots = {name.split("/", 1)[0] for name in chosen.standing_files}
    for relative in (
        chosen.people_dir,
        chosen.groups_dir,
        chosen.side_chats_dir,
        chosen.trail_dir,
        chosen.home_override,
    ):
        roots.add(relative.split("/", 1)[0])
    roots.update(
        {
            "dreams",
            "revisions",
            "skills",
            "presets",
            "plugins",
            "workspace",
            "manifest.json",
            "profile.json",
            "tools.yaml",
            "grants.yaml",
        }
    )
    return frozenset(roots)


def validate_root_entries(
    entries: Sequence[str],
    layout: ContextLayout | None = None,
) -> tuple[str, ...]:
    """Return the root entries that are not allowed, in sorted order."""

    allowed = allowed_root_entries(layout)
    return tuple(sorted(entry for entry in entries if entry not in allowed))


__all__ = [
    "ContextLayout",
    "allowed_root_entries",
    "layout_for_home",
    "merge_layout",
    "packaged_layout",
    "read_layout",
    "validate_root_entries",
]

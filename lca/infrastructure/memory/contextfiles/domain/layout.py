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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

_PACKAGE_FILE = Path(__file__).resolve().parent.parent / "layout.toml"

_FIELDS = (
    "standing_files",
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
)


@dataclass(frozen=True, slots=True)
class ContextLayout:
    """Names and budgets for one assistant home's context files."""

    standing_files: tuple[str, ...]
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


def read_layout(text: str) -> ContextLayout:
    """Parse a complete layout document."""

    data = _table(text)
    missing = [key for key in _FIELDS if key not in data]
    if missing:
        raise ValueError(f"layout missing {', '.join(missing)}")
    return _from_mapping(data)


def merge_layout(base: ContextLayout, text: str) -> ContextLayout:
    """Replace fields present in ``text``. Absent fields stay on ``base``."""

    data = _table(text)
    if not data:
        return base
    current = {key: getattr(base, key) for key in _FIELDS}
    current.update(data)
    return _from_mapping(current)


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


def _from_mapping(data: dict[str, object]) -> ContextLayout:
    standing = data["standing_files"]
    if not isinstance(standing, (list, tuple)) or not standing:
        raise ValueError("standing_files must be a non-empty list")
    names = tuple(_relative(item, key="standing_files") for item in standing)
    if len(set(names)) != len(names):
        raise ValueError("standing_files must be unique")
    return ContextLayout(
        standing_files=names,
        people_dir=_relative(data["people_dir"], key="people_dir"),
        people_index=_relative(data["people_index"], key="people_index", single_segment=True),
        groups_dir=_relative(data["groups_dir"], key="groups_dir"),
        groups_index=_relative(data["groups_index"], key="groups_index", single_segment=True),
        live_note=_line(data["live_note"], key="live_note"),
        home_override=_relative(data["home_override"], key="home_override"),
        backstory_budget_chars=_positive_int(
            data["backstory_budget_chars"],
            key="backstory_budget_chars",
        ),
        agents_file=_relative(data["agents_file"], key="agents_file"),
        agents_heading=_line(data["agents_heading"], key="agents_heading"),
        projection_file=_relative(data["projection_file"], key="projection_file"),
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


__all__ = [
    "ContextLayout",
    "layout_for_home",
    "merge_layout",
    "packaged_layout",
    "read_layout",
]

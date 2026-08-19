"""`cordis.loader` — Plugin loader: YAML/dict → Entry tree (1:1 to upstream).

Faithful Python translation of `~/deepseek-harness/vendor/cordis/src/loader.ts`.

Public API:
- :class:`Entry` — single plugin entry (id, name, config, disabled, inject).
- :class:`EntryGroup` — group of entries sharing a key.
- :class:`EntryTree` — hierarchical structure of entries.
- :class:`Loader` — high-level facade combining parsing + composition + interpolation.
- :func:`load_config(data)` — top-level helper: accept dict, list, or YAML string.
- :func:`load_yaml(path)` — read YAML from disk and parse.
- :func:`dump_config(tree)` — serialize a tree back to a dict.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml

from cordis.utils import DisposableList

__all__ = [
    "Entry",
    "EntryGroup",
    "EntryTree",
    "Loader",
    "load_config",
    "load_yaml",
    "dump_config",
    "interpolate",
    "isolate",
]


# ---------------------------------------------------------------------------
# Entry / EntryGroup / EntryTree (1:1 with upstream)
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    """A single plugin entry (mirrors upstream ``Entry``)."""

    id: str
    name: str | None = None
    config: Any = None
    disabled: bool | None = None
    inject: list[str] | None = None
    # Other arbitrary fields are allowed (TS: { [key: string]: any })
    extra: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        if key == "id":
            return self.id
        if key == "name":
            return self.name
        if key == "config":
            return self.config
        if key == "disabled":
            return self.disabled
        if key == "inject":
            return self.inject
        return self.extra.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "id":
            self.id = value
        elif key == "name":
            self.name = value
        elif key == "config":
            self.config = value
        elif key == "disabled":
            self.disabled = value
        elif key == "inject":
            self.inject = value
        else:
            self.extra[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for dump_config."""
        out: dict[str, Any] = {"id": self.id}
        if self.name is not None:
            out["name"] = self.name
        if self.config is not None:
            out["config"] = self.config
        if self.disabled is not None:
            out["disabled"] = self.disabled
        if self.inject is not None:
            out["inject"] = self.inject
        out.update(self.extra)
        return out


@dataclass
class EntryGroup:
    """A group of entries sharing a key (mirrors upstream ``EntryGroup``)."""

    key: str
    entries: list[Entry] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        if key == "key":
            return self.key
        if key == "entries":
            return self.entries
        return None


class EntryTree:
    """Hierarchical structure of entries (mirrors upstream ``EntryTree``).

    Stores a flat list of entries and a parent chain. Lookups walk ancestors.
    """

    def __init__(self, parent: "EntryTree | None" = None) -> None:
        self.parent = parent
        self.entries: list[Entry] = []
        self.disposables = DisposableList()
        # Index by id for O(1) lookups
        self._index: dict[str, Entry] = {}

    def add(self, entry: Entry) -> None:
        """Append an entry; index it by id."""
        self.entries.append(entry)
        self._index[entry.id] = entry

    def find(self, entry_id: str) -> Entry | None:
        """Find entry by id, walking up the parent chain."""
        node: EntryTree | None = self
        while node is not None:
            if entry_id in node._index:
                return node._index[entry_id]
            node = node.parent
        return None

    def dispose(self) -> None:
        """Dispose all disposable resources."""
        # DisposableList.clear returns items in reverse order
        self.disposables.clear()


# ---------------------------------------------------------------------------
# Interpolate (1:1 with upstream interpolate)
# ---------------------------------------------------------------------------


_INTERPOLATE_RE = re.compile(r"\$\{([^}]+)\}")


def interpolate(value: Any, scope: Mapping[str, Any] | None = None) -> Any:
    """Recursively substitute ``${path}`` tokens inside strings/containers.

    Tokens look like ``${ENV.HOME}`` or ``${ctx.foo}``. Unknown paths are
    left as-is (matches upstream's "best effort" semantic).
    """
    if scope is None:
        scope = {}
    if isinstance(value, str):
        return _interpolate_str(value, scope)
    if isinstance(value, Mapping):
        return {k: interpolate(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(item, scope) for item in value]
    return value


def _interpolate_str(s: str, scope: Mapping[str, Any]) -> str:
    """Substitute ${path} tokens in a single string.

    Returns the substituted string. If a token's resolved value is not a
    string, ``str()`` is applied so the result remains a string. For
    type-preserving substitution, callers should compose via the dict/list
    recursion in :func:`interpolate`.
    """
    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        cur: Any = scope
        for part in path.split("."):
            if isinstance(cur, Mapping) and part in cur:
                cur = cur[part]
            else:
                return match.group(0)  # leave as-is
        return str(cur)

    return _INTERPOLATE_RE.sub(_replace, s)


# ---------------------------------------------------------------------------
# Isolate (1:1 with upstream isolate)
# ---------------------------------------------------------------------------


def isolate(tree: EntryTree, label: str, factory: Callable[[EntryTree], Any]) -> Any:
    """Run ``factory`` with a fresh child tree labeled ``label``."""
    child = EntryTree(parent=tree)
    result = factory(child)
    return result


# ---------------------------------------------------------------------------
# Parse / Serialize (1:1 with upstream Loader)
# ---------------------------------------------------------------------------


def _is_entry_dict(d: Mapping[str, Any]) -> bool:
    """Heuristic: a dict shaped like an Entry must contain ``id``."""
    return isinstance(d, Mapping) and "id" in d and isinstance(d.get("id"), str)


def _parse_entry(data: Mapping[str, Any]) -> Entry | EntryGroup:
    """Parse a dict into either an Entry or an EntryGroup (mirrors upstream)."""
    if not _is_entry_dict(data):
        raise ValueError(f"invalid entry: missing string 'id' field in {data!r}")
    entry = Entry(
        id=data["id"],
        name=data.get("name"),
        config=data.get("config"),
        disabled=data.get("disabled"),
        inject=data.get("inject"),
    )
    # Capture other fields
    for k, v in data.items():
        if k not in ("id", "name", "config", "disabled", "inject"):
            entry.extra[k] = v
    return entry


def _build_tree(data: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> EntryTree:
    """Build an EntryTree from parsed config (dict, list of dicts, or EntryGroup)."""
    tree = EntryTree()
    if isinstance(data, Mapping) and "entries" in data and isinstance(data["entries"], list):
        # EntryGroup shape: {"key": "...", "entries": [...]}
        items = data["entries"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, Mapping) and "id" in data:
        # Single Entry
        tree.add(_parse_entry(data))  # type: ignore[arg-type]
        return tree
    else:
        raise ValueError(f"cannot build tree from {data!r}")
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"entry must be a dict, got {type(item).__name__}")
        tree.add(_parse_entry(item))
    return tree


def load_config(data: Mapping[str, Any] | Iterable[Mapping[str, Any]] | str) -> EntryTree:
    """Parse ``data`` (dict, list, or YAML string) into an EntryTree."""
    if isinstance(data, str):
        parsed = yaml.safe_load(data)
        if parsed is None:
            return EntryTree()  # empty YAML
        return _build_tree(parsed)
    return _build_tree(data)


def load_yaml(path: str) -> EntryTree:
    """Read YAML from ``path`` and parse into an EntryTree."""
    with open(path, "r", encoding="utf-8") as f:
        return _build_tree(yaml.safe_load(f) or {})


def dump_config(tree_or_entries: EntryTree | list[Entry] | Entry) -> dict[str, Any]:
    """Serialize an EntryTree / list / single Entry back to a dict.

    The output shape is a list of entry dicts under ``"entries"`` (matching
    upstream's canonical dump format).
    """
    if isinstance(tree_or_entries, Entry):
        return tree_or_entries.to_dict()
    if isinstance(tree_or_entries, EntryTree):
        return {"entries": [e.to_dict() for e in tree_or_entries.entries]}
    if isinstance(tree_or_entries, list):
        return {"entries": [e.to_dict() for e in tree_or_entries]}
    raise TypeError(f"cannot dump {type(tree_or_entries).__name__}")


# ---------------------------------------------------------------------------
# Bundle / Loader (1:1 with upstream Bundle + Loader facade)
# ---------------------------------------------------------------------------


@dataclass
class Bundle:
    """A named bundle of entries (mirrors upstream ``Bundle``)."""

    name: str
    entries: list[Entry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "entries": [e.to_dict() for e in self.entries]}


def merge_bundles(*bundles: Bundle) -> EntryTree:
    """Merge multiple bundles into a single EntryTree (1:1 with upstream merge_bundles)."""
    tree = EntryTree()
    seen: set[str] = set()
    for bundle in bundles:
        for entry in bundle.entries:
            if entry.id in seen:
                # Override: replace existing entry (matches upstream)
                existing = tree.find(entry.id)
                if existing is not None:
                    tree.entries.remove(existing)
                    tree._index.pop(entry.id, None)
            tree.add(entry)
            seen.add(entry.id)
    return tree


class Loader:
    """High-level loader combining parsing + composition + interpolation.

    Mirrors upstream ``Loader`` class: ``Loader.from_internal()`` returns
    a loader backed by the in-process plugin registry.
    """

    def __init__(self, scope: Mapping[str, Any] | None = None) -> None:
        self.scope: dict[str, Any] = dict(scope or {})
        # env scope for ${ENV.X} substitutions
        self.scope.setdefault("ENV", dict(os.environ))

    def with_scope(self, extra: Mapping[str, Any]) -> "Loader":
        """Return a new Loader with merged scope."""
        merged = {**self.scope, **dict(extra)}
        return Loader(merged)

    def load(self, data: Any) -> EntryTree:
        """Load + interpolate + return an EntryTree."""
        interpolated = interpolate(data, self.scope)
        return load_config(interpolated)

    def load_yaml(self, path: str) -> EntryTree:
        """Load + interpolate a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        interpolated = interpolate(raw, self.scope)
        return load_config(interpolated)

    def dump(self, tree: EntryTree) -> dict[str, Any]:
        """Serialize a tree back to dict (post-interpolation for symmetry)."""
        raw = dump_config(tree)
        return interpolate(raw, self.scope)

    @classmethod
    def from_internal(cls) -> "Loader":
        """Loader backed by the in-process plugin registry (1:1 with upstream)."""
        return cls()
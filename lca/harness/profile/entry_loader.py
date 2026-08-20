"""Boot from already-expanded entry dicts (tests / programmatic trees).

Lives apart from :mod:`lca.harness.profile.boot` so the runtime boot
path stays focused on plugin effect/dispose (ADR-0062 §4). Boot from
``ResolvedProfile`` is the production path; ``boot_entries`` is the
test-only convenience that accepts raw dicts without going through
``resolve_profile``.
"""

from __future__ import annotations

import importlib
from collections import defaultdict, deque
from typing import Any

from lca.harness.plugin_api import definition_from_plugin


def prepare_entries(
    entries: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], Any, Any]]:
    """Validate entry dicts and return (entry, definition, config) tuples.

    Each entry must declare ``$module``; the module's ``setup`` is
    introspected via :func:`definition_from_plugin` and the entry's
    ``id`` is checked against the module Manifest ``id``. Duplicate
    capability providers fail fast.
    """
    prepared: list[tuple[dict[str, Any], Any, Any]] = []
    provide_owner: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if entry.get("disabled") or (
            isinstance(entry.get("config"), dict) and entry["config"].get("disabled")
        ):
            continue
        module_path = entry.get("$module")
        if not module_path:
            raise ValueError(
                f"bundle entry {entry.get('id')!r} has no $module; bare-name resolution was removed"
            )
        module = importlib.import_module(str(module_path))
        setup_obj = getattr(module, "setup", None)
        if setup_obj is None:
            continue
        definition = definition_from_plugin(setup_obj, module=str(module_path))
        entry_id = str(entry.get("id") or definition.id)
        if definition.id and entry_id != definition.id:
            raise ValueError(f"entry id {entry_id!r} != module Manifest id {definition.id!r}")
        config = entry.get("config") or {}
        config_cls = definition.Config or getattr(setup_obj, "Config", None)
        if config_cls is not None and not isinstance(config, config_cls):
            config = config_cls.model_validate(config)
        for key in definition.provides:
            if key in provide_owner:
                raise ValueError(
                    f"duplicate providers for capability {key!r}: "
                    f"{provide_owner[key]} and {entry_id}"
                )
            provide_owner[key] = entry_id
        prepared.append(({"id": entry_id, "index": index, **entry}, definition, config))

    return order_prepared(prepared)


def order_prepared(
    prepared: list[tuple[dict[str, Any], Any, Any]],
) -> list[tuple[dict[str, Any], Any, Any]]:
    """Topologically order prepared entries by provides → requires.

    Stable by original ``entry.index`` on ties; raises on cycles.
    """
    by_id = {definition.id: (entry, definition, config) for entry, definition, config in prepared}
    provide_owner = {
        key: definition.id for _, definition, _ in prepared for key in definition.provides
    }
    dependents: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for _entry, definition, _config in prepared:
        for key in definition.requires:
            owner = provide_owner.get(key)
            if owner and owner != definition.id:
                dependents[owner].add(definition.id)
                reverse[definition.id].add(owner)
    indegree = {did: len(reverse[did]) for did in by_id}
    ready = deque(
        sorted(
            (did for did, deg in indegree.items() if deg == 0),
            key=lambda i: int(by_id[i][0].get("index", 0)),
        )
    )
    ordered: list[tuple[dict[str, Any], Any, Any]] = []
    while ready:
        nid = ready.popleft()
        ordered.append(by_id[nid])
        for child in sorted(dependents[nid], key=lambda i: int(by_id[i][0].get("index", 0))):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        if len(ready) > 1:
            ready = deque(sorted(ready, key=lambda i: int(by_id[i][0].get("index", 0))))
    if len(ordered) != len(prepared):
        raise ValueError("cyclic plugin dependency in boot_entries")
    return ordered

"""事件机制鉴权矩阵（ADR-0180 D2/C）。

``EventRegistry`` 是从 ``lca_kernel/events/config/**/*.yaml`` 加载的单一鉴权矩阵。
加载时把 yaml 字段值**全部解析为 typed Python 实体**：

- ``plane: lca.contracts.event.Plane.STRUCTURAL`` → :class:`Plane.STRUCTURAL`（enum 成员）
- ``payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit`` → class 对象
- ``publishers: [lca.plugins...DelegationCachePlugin]`` → :class:`type` 对象
- ``subscribers: [lca.plugins...JournalSink]`` → :class:`type` 对象

任何字段解析失败 → :class:`UnknownCategoryError`，机制 fail-fast。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.errors import UnknownCategoryError


@dataclass(frozen=True, slots=True)
class EventSpec:
    """单条事件的 SSOT 记录（yaml → typed 实体）。"""

    category: Category
    plane: Plane
    payload_class: type[EventPayload]
    fields: dict[str, str] = field(default_factory=dict)
    publishers: frozenset[type] = frozenset()
    """plugin class 全路径 → 解析后的 type 对象。"""
    subscribers: frozenset[type] = frozenset()
    default_subscribers: frozenset[type] = frozenset()


def _resolve_enum_member(enum_cls: type, full_path: str, *, ctx: str) -> Any:
    """按 ``module.ClassName.MEMBER_NAME`` 全路径解析 enum 成员。"""
    parts = full_path.split(".")
    if len(parts) < 3:
        raise UnknownCategoryError(
            full_path, f"{ctx}: 期望 module.ClassName.MEMBER 格式（至少 3 段）"
        )
    member_name = parts[-1]
    class_name = parts[-2]
    module_path = ".".join(parts[:-2])
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise UnknownCategoryError(full_path, f"{ctx}: import {module_path} 失败") from exc
    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, enum_cls):
        raise UnknownCategoryError(
            full_path, f"{ctx}: {module_path}.{class_name} 不是 {enum_cls.__name__} 子类"
        )
    member = getattr(cls, member_name, None)
    if member is None or not hasattr(cls, "__members__"):
        raise UnknownCategoryError(
            full_path, f"{ctx}: {module_path}.{class_name}.{member_name} 不存在"
        )
    members_map = getattr(cls, "__members__", {})
    if member not in members_map.values():
        raise UnknownCategoryError(
            full_path, f"{ctx}: {module_path}.{class_name}.{member_name} 不是 enum 成员"
        )
    return member


def _resolve_class(full_path: str, *, base_cls: type, ctx: str) -> type:
    """按 ``module.ClassName`` 全路径解析 class；必须是 ``base_cls`` 子类。"""
    module_path, _, class_name = full_path.rpartition(".")
    if not module_path:
        raise UnknownCategoryError(full_path, f"{ctx}: 缺少模块路径")
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise UnknownCategoryError(full_path, f"{ctx}: import 失败") from exc
    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, base_cls):
        raise UnknownCategoryError(
            full_path, f"{ctx}: {full_path} 不可解析或非 {base_cls.__name__} 子类"
        )
    return cls


@dataclass(frozen=True, slots=True)
class EventRegistry:
    """鉴权矩阵 SSOT（ADR-0180 D2/C）。"""

    specs: tuple[EventSpec, ...]
    publishers: dict[Category, frozenset[type]]
    subscribers: dict[Category, frozenset[type]]
    default_subscribers: dict[Category, frozenset[type]]
    payload_by_category: dict[Category, type[EventPayload]]

    @classmethod
    def load(cls, config_dir: Path) -> EventRegistry:
        specs: list[EventSpec] = []
        yaml_files = sorted(config_dir.rglob("*.yaml"))
        if not yaml_files:
            raise FileNotFoundError(f"事件配置 SSOT 目录为空：{config_dir}")
        for yaml_file in yaml_files:
            specs.extend(cls._load_one(yaml_file))
        return cls.from_specs(specs)

    @classmethod
    def from_specs(cls, specs: list[EventSpec]) -> EventRegistry:
        publishers: dict[Category, frozenset[type]] = {}
        subscribers: dict[Category, frozenset[type]] = {}
        default_subscribers: dict[Category, frozenset[type]] = {}
        payload_by: dict[Category, type[EventPayload]] = {}
        seen: set[Category] = set()
        for spec in specs:
            if spec.category in seen:
                msg = f"category={spec.category.value} 在 SSOT 多处登记"
                raise ValueError(msg)
            seen.add(spec.category)
            publishers[spec.category] = spec.publishers
            subscribers[spec.category] = spec.subscribers
            default_subscribers[spec.category] = spec.default_subscribers
            payload_by[spec.category] = spec.payload_class
        return cls(
            specs=tuple(specs),
            publishers=publishers,
            subscribers=subscribers,
            default_subscribers=default_subscribers,
            payload_by_category=payload_by,
        )

    @classmethod
    def _load_one(cls, yaml_file: Path) -> list[EventSpec]:
        with yaml_file.open(encoding="utf-8") as fh:
            data: Any = yaml.safe_load(fh)
        if not isinstance(data, dict) or "events" not in data:
            return []
        out: list[EventSpec] = []
        for entry in data["events"]:
            ctx = f"yaml={yaml_file.name}"
            try:
                category = Category(entry["category"])
            except ValueError as exc:
                raise UnknownCategoryError(entry["category"], ctx) from exc
            plane = _resolve_enum_member(
                Plane, entry["plane"], ctx=f"{ctx} category={entry['category']}"
            )
            payload_cls = _resolve_class(
                entry["payload_class"],
                base_cls=EventPayload,
                ctx=f"{ctx} category={entry['category']}",
            )
            # publishers / subscribers / default_subscribers：plugin class 全路径
            cat_ctx = f"{ctx} category={entry['category']}"
            pubs = frozenset(
                _resolve_class(p, base_cls=object, ctx=f"{cat_ctx} publishers={p!r}")
                for p in entry.get("publishers", ())
            )
            subs = frozenset(
                _resolve_class(s, base_cls=object, ctx=f"{cat_ctx} subscribers={s!r}")
                for s in entry.get("subscribers", ())
            )
            default_subs = frozenset(
                _resolve_class(d, base_cls=object, ctx=f"{cat_ctx} default_subscribers={d!r}")
                for d in entry.get("default_subscribers", ())
            )
            out.append(
                EventSpec(
                    category=category,
                    plane=plane,
                    payload_class=payload_cls,
                    fields=dict(entry.get("fields", {})),
                    publishers=pubs,
                    subscribers=subs,
                    default_subscribers=default_subs,
                )
            )
        return out

    # ── 鉴权查询 ──────────────────────────────────────────────────────────

    def can_publish(self, plugin_cls: type, category: Category) -> bool:
        return plugin_cls in self.publishers.get(category, frozenset())

    def can_subscribe(self, plugin_cls: type, category: Category) -> bool:
        return plugin_cls in self.subscribers.get(category, frozenset())

    def payload_class(self, category: Category) -> type[EventPayload]:
        return self.payload_by_category[category]


__all__ = ["EventRegistry", "EventSpec"]

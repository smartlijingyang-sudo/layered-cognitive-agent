"""事件机制鉴权矩阵（ADR-0180 D2/C、ADR-0183 PR-6）。

``EventRegistry`` 是从 ``lca_kernel/events/config/**/*.yaml`` 加载的单一鉴权矩阵。
加载时把 yaml 字段值**全部解析为 typed Python 实体**：

- ``plane: lca.contracts.event.Plane.STRUCTURAL`` → :class:`Plane.STRUCTURAL`（enum 成员）
- ``payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit`` → class 对象
- ``publishers: [lca.plugins...DelegationCachePlugin]`` → :class:`type` 对象
- 顶层 ``consumer_rules:`` 前缀规则（``config_parser.parse_consumer_rules``）
  → :class:`SubscriberRule` 元组；每 category 的订阅授权 = 逐条
  ``subscribers`` ∪ 命中规则的 subscribers，装载时物化进 ``subscribers``
  映射，`can_subscribe` / ``validate_auth_matrix`` 按物化集合判定。

任何字段解析失败 → :class:`UnknownCategoryError`，机制 fail-fast。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.config_parser import (
    SubscriberRule,
    parse_consumer_rules,
    subscribers_from_rules,
)
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
    """逐 category 订阅授权；与顶层 consumer_rules 命中的规则求并。"""


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
    """鉴权矩阵 SSOT（ADR-0180 D2/C）。

    ``subscribers`` 是装载时物化的每 category 授权集合 = 逐条
    ``subscribers`` ∪ ``consumer_rules`` 前缀命中规则的并集。
    """

    specs: tuple[EventSpec, ...]
    publishers: dict[Category, frozenset[type]]
    subscribers: dict[Category, frozenset[type]]
    consumer_rules: tuple[SubscriberRule[type], ...]
    payload_by_category: dict[Category, type[EventPayload]]

    @classmethod
    def load(cls, config_dir: Path) -> EventRegistry:
        specs: list[EventSpec] = []
        rules: list[SubscriberRule[type]] = []
        yaml_files = sorted(config_dir.rglob("*.yaml"))
        if not yaml_files:
            raise FileNotFoundError(f"事件配置 SSOT 目录为空：{config_dir}")
        for yaml_file in yaml_files:
            file_specs, file_rules = cls._load_one(yaml_file)
            specs.extend(file_specs)
            rules.extend(file_rules)
        return cls.from_specs(specs, consumer_rules=tuple(rules))

    @classmethod
    def from_specs(
        cls,
        specs: list[EventSpec],
        consumer_rules: Sequence[SubscriberRule[type]] = (),
    ) -> EventRegistry:
        publishers: dict[Category, frozenset[type]] = {}
        subscribers: dict[Category, frozenset[type]] = {}
        payload_by: dict[Category, type[EventPayload]] = {}
        seen: set[Category] = set()
        for spec in specs:
            if spec.category in seen:
                msg = f"category={spec.category.value} 在 SSOT 多处登记"
                raise ValueError(msg)
            seen.add(spec.category)
            publishers[spec.category] = spec.publishers
            subscribers[spec.category] = spec.subscribers | subscribers_from_rules(
                spec.category.value, consumer_rules
            )
            payload_by[spec.category] = spec.payload_class
        return cls(
            specs=tuple(specs),
            publishers=publishers,
            subscribers=subscribers,
            consumer_rules=tuple(consumer_rules),
            payload_by_category=payload_by,
        )

    @classmethod
    def _load_one(cls, yaml_file: Path) -> tuple[list[EventSpec], list[SubscriberRule[type]]]:
        with yaml_file.open(encoding="utf-8") as fh:
            data: Any = yaml.safe_load(fh)
        if not isinstance(data, dict) or "events" not in data:
            return [], []
        ctx = f"yaml={yaml_file.name}"

        def resolve_rule_class(full_path: str) -> type:
            return _resolve_class(
                full_path, base_cls=object, ctx=f"{ctx} consumer_rules={full_path!r}"
            )

        rules = list(parse_consumer_rules(data.get("consumer_rules"), resolve_rule_class, ctx=ctx))
        out: list[EventSpec] = []
        for entry in data["events"]:
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
            # publishers / subscribers：plugin class 全路径
            cat_ctx = f"{ctx} category={entry['category']}"
            pubs = frozenset(
                _resolve_class(p, base_cls=object, ctx=f"{cat_ctx} publishers={p!r}")
                for p in entry.get("publishers", ())
            )
            subs = frozenset(
                _resolve_class(s, base_cls=object, ctx=f"{cat_ctx} subscribers={s!r}")
                for s in entry.get("subscribers", ())
            )
            out.append(
                EventSpec(
                    category=category,
                    plane=plane,
                    payload_class=payload_cls,
                    fields=dict(entry.get("fields", {})),
                    publishers=pubs,
                    subscribers=subs,
                )
            )
        return out, rules

    # ── 鉴权查询 ──────────────────────────────────────────────────────────

    def can_publish(self, plugin_cls: type, category: Category) -> bool:
        return plugin_cls in self.publishers.get(category, frozenset())

    def can_subscribe(self, plugin_cls: type, category: Category) -> bool:
        """判定 = 逐条 subscribers 命中 ∨ 某前缀规则命中且授权该 plugin
        （装载时已物化进 ``subscribers`` 映射）。"""
        return plugin_cls in self.subscribers.get(category, frozenset())

    def payload_class(self, category: Category) -> type[EventPayload]:
        return self.payload_by_category[category]


__all__ = ["EventRegistry", "EventSpec"]

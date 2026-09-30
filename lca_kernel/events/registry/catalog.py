"""YAML 事件目录加载：``lca_kernel/events/config/**/*.yaml`` → typed 事件描述。

本模块是 :class:`EventRegistry` 的装载层（ADR-0180 D2/C、ADR-0183 PR-6 +
单入口宇宙 PR-5）。它把 yaml 字段值**全部解析为 typed Python 实体**：

- ``plane: lca.contracts.event.Plane.STRUCTURAL`` → :class:`Plane.STRUCTURAL`（enum 成员）
- ``payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit`` → class 对象
- ``publishers: [lca.plugins...DelegationCachePlugin]`` → :class:`type` 对象（PR-5 前唯一形态）
- ``publishers: [delegation_cache]`` → :class:`type` 对象（PR-5 新增 id 形态，
  由 :class:`EventRegistry` 按 catalog 解析）

顶层 ``consumer_rules:`` 前缀规则在装载期保留为 :class:`_ConsumerRuleTokens`
raw 形态（catalog 尚未填充，id-form token 无法在装载期解析），由
:class:`EventRegistry.from_specs` / :meth:`EventRegistry.refresh` 在 catalog
就位后物化进 ``subscribers`` 映射。

任何字段解析失败 → :class:`UnknownCategoryError`，机制 fail-fast。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.errors.errors import UnknownCategoryError


@dataclass(frozen=True, slots=True)
class _ConsumerRuleTokens:
    """PR-5：consumer_rules 装载期保留的 raw token 形态。

    YAML 装载时 catalog 尚未填充（profile resolve 未完成），id-form token
    无法解析。``EventRegistry.from_specs`` 接受本形态并在 catalog 就位后
    把 subscribers 解析为 ``frozenset[type]``，转成标准
    :class:`SubscriberRule[type]`。这是 PR-5 双轨兼容期的内部载体；外部
    公开面仍是 ``EventRegistry.consumer_rules: tuple[SubscriberRule[type]]``。
    """

    prefix: str
    subscribers_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventSpec:
    """单条事件的 SSOT 记录（yaml → typed 实体）。

    PR-5：``publishers_tokens`` 与 ``subscribers_tokens`` 是 yaml 原文；
    ``publishers`` 与 ``subscribers`` 是按 catalog + legacy class-path 解析
    后的 ``frozenset[type]``。两者保持同步，迁移期内权威来源是
    ``publishers_tokens``，由 ``EventRegistry.from_specs`` 触发解析（catalog
    可在 ``from_specs`` 之后注入）。
    """

    category: Category
    plane: Plane
    payload_class: type[EventPayload]
    fields: dict[str, str] = field(default_factory=dict)
    publishers_tokens: tuple[str, ...] = ()
    """yaml 原文 token（class-path 或 id）。"""
    subscribers_tokens: tuple[str, ...] = ()
    publishers: frozenset[type] = frozenset()
    """按 tokens 解析 + catalog 查表后的 plugin class 集合。"""
    subscribers: frozenset[type] = frozenset()
    """按 tokens 解析 + catalog 查表后的 plugin class 集合；与顶层
    ``consumer_rules`` 命中规则求并后写入 registry.subscribers 映射。"""


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
    """按 ``module.ClassName`` 全路径解析 class；必须是 ``base_cls`` 子类。

    COMPAT(delete-when: rg "lca.plugins.[A-Za-z0-9_]+.[A-Z][A-Za-z]+$" lca_kernel/events/config
    profiles/event-pipeline = 0;tracking: 2026-09-04-plugin-universe-single-entry PR-5)
    """
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


def _looks_like_class_path(token: str) -> bool:
    """PR-5：启发式判定 token 是否为 class-path（``module.ClassName`` 形态）。

    规则：含 1 个以上 ``.``、末段以大写字母开头、其余段至少有一段小写起首
    —— 类路径通常末段是类名（首大写）。id 通常不出现 ``.`` 或末段小写。
    """
    if "." not in token:
        return False
    parts = token.split(".")
    last = parts[-1]
    if not last or not last[0].isupper():
        return False
    # module 段至少有一小写起首（区分 const var 全大写场景）。
    return any(p and p[0].islower() for p in parts[:-1])


def load_catalog(config_dir: Path) -> tuple[list[EventSpec], list[_ConsumerRuleTokens]]:
    """加载目录下全部事件 yaml，返回 ``(specs, consumer rule tokens)``。

    目录下没有 ``*.yaml`` → :class:`FileNotFoundError`。文件按路径排序，
    保证装载顺序确定（与旧 ``EventRegistry.load`` 行为一致）。
    """
    specs: list[EventSpec] = []
    rules: list[_ConsumerRuleTokens] = []
    yaml_files = sorted(config_dir.rglob("*.yaml"))
    if not yaml_files:
        raise FileNotFoundError(f"事件配置 SSOT 目录为空：{config_dir}")
    for yaml_file in yaml_files:
        file_specs, file_rules = _load_one(yaml_file)
        specs.extend(file_specs)
        rules.extend(file_rules)
    return specs, rules


def _load_one(yaml_file: Path) -> tuple[list[EventSpec], list[_ConsumerRuleTokens]]:
    """解析单个事件 yaml 文件为 ``(specs, consumer rule tokens)``。

    非事件 yaml（缺 ``events`` 段）或 ``lca.observability.*`` schema 的
    观测目录 yaml → 返回空。
    """
    with yaml_file.open(encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    if not isinstance(data, dict) or "events" not in data:
        return [], []
    schema = data.get("schema")
    if isinstance(schema, str) and schema.startswith("lca.observability."):
        return [], []
    ctx = f"yaml={yaml_file.name}"

    def parse_rule_entry(entry: Any, *, rule_ctx: str) -> _ConsumerRuleTokens:
        if not isinstance(entry, dict) or not isinstance(entry.get("prefix"), str):
            raise ValueError(f"{rule_ctx}: 规则必须是含字符串 prefix 的 mapping")
        prefix = entry["prefix"]
        if not prefix:
            raise ValueError(f"{rule_ctx}: prefix 不能为空")
        raw_subs = entry.get("subscribers") or []
        if not isinstance(raw_subs, list):
            raise ValueError(f"{rule_ctx}: subscribers 必须是 list")
        return _ConsumerRuleTokens(
            prefix=prefix,
            subscribers_tokens=tuple(str(s) for s in raw_subs),
        )

    raw_entries = data.get("consumer_rules")
    if raw_entries is None:
        rules: list[_ConsumerRuleTokens] = []
    elif isinstance(raw_entries, list):
        rules = [
            parse_rule_entry(entry, rule_ctx=f"{ctx} consumer_rules[{i}]")
            for i, entry in enumerate(raw_entries)
        ]
    else:
        raise ValueError(f"{ctx}: consumer_rules 必须是 list")
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
        cat_ctx = f"{ctx} category={entry['category']}"  # noqa: F841 — reserved for future
        pub_tokens = tuple(str(p) for p in entry.get("publishers", ()))
        sub_tokens = tuple(str(s) for s in entry.get("subscribers", ()))
        out.append(
            EventSpec(
                category=category,
                plane=plane,
                payload_class=payload_cls,
                fields=dict(entry.get("fields", {})),
                publishers_tokens=pub_tokens,
                subscribers_tokens=sub_tokens,
            )
        )
    return out, rules


__all__ = ["EventSpec", "load_catalog"]

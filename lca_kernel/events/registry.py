"""事件机制鉴权矩阵（ADR-0180 D2/C、ADR-0183 PR-6 + 单入口宇宙 PR-5）。

``EventRegistry`` 是从 ``lca_kernel/events/config/**/*.yaml`` 加载的单一鉴权矩阵。
加载时把 yaml 字段值**全部解析为 typed Python 实体**：

- ``plane: lca.contracts.event.Plane.STRUCTURAL`` → :class:`Plane.STRUCTURAL`（enum 成员）
- ``payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit`` → class 对象
- ``publishers: [lca.plugins...DelegationCachePlugin]`` → :class:`type` 对象（PR-5 前唯一形态）
- ``publishers: [delegation_cache]`` → :class:`type` 对象（PR-5 新增 id 形态，按 catalog 解析）
- 顶层 ``consumer_rules:`` 前缀规则（``config_parser.parse_consumer_rules``）
  → :class:`SubscriberRule` 元组；每 category 的订阅授权 = 逐条
  ``subscribers`` ∪ 命中规则的 subscribers，装载时物化进 ``subscribers``
  映射，`can_subscribe` / ``validate_auth_matrix`` 按物化集合判定。

PR-5 兼容语义：

- 同一 yaml 文件可混合使用 class-path 与 id 形态；每条 token 单独解析。
- 双轨迁移期间（class-path 与 id 并存）增 ``PR-5 COMPAT`` 注释，
  delete-when 详见本文件 `delete-when` 注释。
- ``EventRegistry`` 通过 ``register_marker(id, cls)`` 接收 catalog 项；
  catalog 在生产 boot 由 ``lca_kernel.events.manifest.setup_bus`` 在
  profile resolve 完成后填充（详见该函数）。

任何字段解析失败 → :class:`UnknownCategoryError` 或 :class:`UnknownPluginIdError`，
机制 fail-fast。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.config_parser import (
    SubscriberRule,
    subscribers_from_rules,
)
from lca_kernel.events.errors import UnknownCategoryError, UnknownPluginIdError

_log = logging.getLogger(__name__)


# COMPAT(delete-when: rg "lca.plugins.[A-Za-z0-9_]+.[A-Z][A-Za-z]+$" lca_kernel/events/config
# profiles/event-pipeline = 0;tracking: 2026-09-04-plugin-universe-single-entry PR-5)
# class-path 鉴权形态：PR-5 兼容期保留；迁完即删。
_LEGACY_CLASS_PATH_HINT = (
    "class-path 形态（lca.plugins...ClassName）为 PR-5 兼容期形态；"
    "delete-when 详见 2026-09-04-plugin-universe-single-entry PR-5"
)


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
    ``publishers_tokens``，由 ``from_specs`` 触发解析（catalog 可在
    ``from_specs`` 之后注入）。
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


@dataclass(frozen=True, slots=True)
class EventRegistry:
    """鉴权矩阵 SSOT（ADR-0180 D2/C）。

    ``subscribers`` 是装载时物化的每 category 授权集合 = 逐条
    ``subscribers`` ∪ ``consumer_rules`` 前缀命中规则的并集。

    PR-5：``_plugins`` 是 ``id → marker class`` 的 catalog；由
    :meth:`register_marker` 注入。装载 yaml 时遇到 id-form token，先查
    catalog；catalog miss 时按 class-path 解析（向后兼容形态）；两者皆不
    命中 → 抛 :class:`UnknownPluginIdError`。

    PR-5：``_raw_consumer_rules`` 保留 consumer_rules 的 raw token 形态，
    供 :meth:`refresh` 在 catalog 注入后重解析（typed consumer_rules 是
    catalog miss 时的暂存结果）。
    """

    specs: tuple[EventSpec, ...]
    publishers: dict[Category, frozenset[type]]
    subscribers: dict[Category, frozenset[type]]
    consumer_rules: tuple[SubscriberRule[type], ...]
    payload_by_category: dict[Category, type[EventPayload]]
    _plugins: dict[str, type] = field(default_factory=dict)
    """PR-5：catalog，``id → marker class``。"""
    _raw_consumer_rules: tuple[_ConsumerRuleTokens, ...] = ()
    """PR-5：consumer_rules raw 形态（refresh 时按 catalog 重解析）。"""

    @classmethod
    def load(
        cls,
        config_dir: Path,
        *,
        catalog: Mapping[str, type] | None = None,
    ) -> EventRegistry:
        specs: list[EventSpec] = []
        rules: list[_ConsumerRuleTokens] = []
        yaml_files = sorted(config_dir.rglob("*.yaml"))
        if not yaml_files:
            raise FileNotFoundError(f"事件配置 SSOT 目录为空：{config_dir}")
        for yaml_file in yaml_files:
            file_specs, file_rules = cls._load_one(yaml_file)
            specs.extend(file_specs)
            rules.extend(file_rules)
        return cls.from_specs(specs, consumer_rules=tuple(rules), catalog=catalog)

    @classmethod
    def from_specs(
        cls,
        specs: list[EventSpec],
        consumer_rules: Sequence[SubscriberRule[type] | _ConsumerRuleTokens] = (),
        *,
        catalog: Mapping[str, type] | None = None,
    ) -> EventRegistry:
        plugins = dict(catalog) if catalog else {}
        # PR-5 兼容：catalog 缺位时（``load()`` 调用）保留 raw token 形态，
        # ``publishers`` / ``subscribers`` 留待 :meth:`refresh` 在 catalog
        # 就位后重解析。catalog 已就位时，按 token 解析为 type。
        typed_rules: list[SubscriberRule[type]] = []
        raw_rules: list[_ConsumerRuleTokens] = []
        for rule in consumer_rules:
            if isinstance(rule, _ConsumerRuleTokens):
                raw_rules.append(rule)
                if plugins:
                    typed_rules.append(
                        SubscriberRule(
                            prefix=rule.prefix,
                            subscribers=frozenset(
                                _resolve_tokens(rule.subscribers_tokens, plugins)
                            ),
                        )
                    )
                else:
                    # PR-5 兼容：catalog 缺位时按 legacy class-path 解析；
                    # id-form token 抛 :class:`UnknownPluginIdError`。
                    typed_rules.append(
                        SubscriberRule(
                            prefix=rule.prefix,
                            subscribers=frozenset(
                                _resolve_classpath_only(
                                    rule.subscribers_tokens, ctx=rule.prefix
                                )
                            ),
                        )
                    )
            else:
                typed_rules.append(rule)
        publishers: dict[Category, frozenset[type]] = {}
        subscribers: dict[Category, frozenset[type]] = {}
        payload_by: dict[Category, type[EventPayload]] = {}
        seen: set[Category] = set()
        for spec in specs:
            if spec.category in seen:
                msg = f"category={spec.category.value} 在 SSOT 多处登记"
                raise ValueError(msg)
            seen.add(spec.category)
            if plugins:
                # catalog 已就位：按 token 解析（含 id 与 class-path 形态）。
                pub_set = frozenset(_resolve_tokens(spec.publishers_tokens, plugins))
                sub_set = frozenset(_resolve_tokens(spec.subscribers_tokens, plugins))
            else:
                # PR-5 兼容：catalog 缺位时按 legacy class-path 解析。
                # 这条路径只在测试场景（``EventRegistry.load`` 直调）或迁
                # 移前 yaml 全是 class-path 时被走；id-form token 留待
                # :meth:`refresh` 重解析。
                pub_set = frozenset(
                    _resolve_classpath_only(spec.publishers_tokens, ctx=spec.category.value)
                )
                sub_set = frozenset(
                    _resolve_classpath_only(spec.subscribers_tokens, ctx=spec.category.value)
                )
            publishers[spec.category] = pub_set
            subscribers[spec.category] = sub_set | subscribers_from_rules(
                spec.category.value, typed_rules
            )
            payload_by[spec.category] = spec.payload_class
        return cls(
            specs=tuple(specs),
            publishers=publishers,
            subscribers=subscribers,
            consumer_rules=tuple(typed_rules),
            payload_by_category=payload_by,
            _plugins=plugins,
            _raw_consumer_rules=tuple(raw_rules),
        )

    @classmethod
    def _load_one(
        cls, yaml_file: Path
    ) -> tuple[list[EventSpec], list[_ConsumerRuleTokens]]:
        with yaml_file.open(encoding="utf-8") as fh:
            data: Any = yaml.safe_load(fh)
        if not isinstance(data, dict) or "events" not in data:
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

    # ── PR-5：catalog 与 id 解析 ────────────────────────────────────────

    def register_marker(self, plugin_id: str, marker_class: type) -> None:
        """PR-5：注入一条 catalog 项（id → marker class）。

        生产 boot 路径：profile resolve 完成后由 setup_bus 从
        ``ResolvedProfile.plugins`` 中遍历，把声明了 ``marker_class=`` 的
        插件的 id → marker 注入 catalog。再由 ``from_specs`` /
        :meth:`refresh` 触发 token 重解析。

        仅当 ``marker_class`` 是 type 时接受；否则 raise ``TypeError``。
        同 id 重复注入 → 静默覆盖（旧 class 仍可被外部保留，新值生效）。
        """
        if not isinstance(marker_class, type):
            raise TypeError(
                f"register_marker({plugin_id!r}) expects type, got "
                f"{type(marker_class).__name__}"
            )
        self._plugins[plugin_id] = marker_class

    def resolve_entity(self, token: str) -> type | None:
        """PR-5：解析单一 token。

        1. 若 ``token`` 为 id-form（不在 catalog 内视为 miss）且 catalog 有
           该 id → 返回 catalog[class]；
        2. 否则按 class-path 解析（保留 legacy 形态，PR-5 兼容期）；
        3. 两者皆不命中 → 返回 ``None``，调用方负责错误归类。

        返回类型对象；不抛异常（异常路径集中在 yaml load 与鉴权失败）。
        """
        if token in self._plugins:
            return self._plugins[token]
        if _looks_like_class_path(token):
            try:
                return _resolve_class(token, base_cls=object, ctx="resolve_entity")
            except UnknownCategoryError:
                return None
        return None

    def refresh(self) -> None:
        """PR-5：catalog 注入后重解析所有 token → publishers / subscribers。

        通常在 ``register_marker`` 全部完成之后调用一次；事件 yaml 在
        ``EventRegistry.load`` 之后 catalog 未到位的场景下，本方法把
        catalog miss 转为 hit（id-form token 被解析为 marker class）。
        consumer_rules 同样在 refresh 内按当前 catalog 重解析（typed
        状态是 catalog miss 时的暂存结果）。
        """
        # 重解析 consumer_rules（id-form token 在 catalog 注入后转为 hit）。
        typed_rules: list[SubscriberRule[type]] = []
        for raw in self._raw_consumer_rules:
            typed_rules.append(
                SubscriberRule(
                    prefix=raw.prefix,
                    subscribers=frozenset(
                        _resolve_tokens(
                            raw.subscribers_tokens, self._plugins, strict=False
                        )
                    ),
                )
            )
        new_pubs: dict[Category, frozenset[type]] = {}
        new_subs: dict[Category, frozenset[type]] = {}
        for spec in self.specs:
            pub_set = frozenset(
                _resolve_tokens(spec.publishers_tokens, self._plugins, strict=False)
            )
            sub_set = frozenset(
                _resolve_tokens(spec.subscribers_tokens, self._plugins, strict=False)
            )
            new_pubs[spec.category] = pub_set
            new_subs[spec.category] = sub_set | subscribers_from_rules(
                spec.category.value, typed_rules
            )
        object.__setattr__(self, "consumer_rules", tuple(typed_rules))
        object.__setattr__(self, "publishers", new_pubs)
        object.__setattr__(self, "subscribers", new_subs)

    # ── 鉴权查询 ────────────────────────────────────────────────────────

    def can_publish(self, plugin: type | str, category: Category) -> bool:
        """PR-5：接受 ``type`` 或 plugin ``id``。

        id 形态先查 catalog，未命中 → 不授权（fall-through）；type 形态直接
        比对。任一形态命中 publishers 集合即返回 True。
        """
        cls = self._coerce_plugin(plugin)
        if cls is None:
            return False
        return cls in self.publishers.get(category, frozenset())

    def can_subscribe(self, plugin: type | str, category: Category) -> bool:
        """PR-5：接受 ``type`` 或 plugin ``id``。

        判定 = 逐条 subscribers 命中 ∨ 某前缀规则命中且授权该 plugin
        （装载时已物化进 ``subscribers`` 映射）。
        """
        cls = self._coerce_plugin(plugin)
        if cls is None:
            return False
        return cls in self.subscribers.get(category, frozenset())

    def payload_class(self, category: Category) -> type[EventPayload]:
        return self.payload_by_category[category]

    def _coerce_plugin(self, plugin: type | str) -> type | None:
        """PR-5：``type`` 原样返回；``str`` 走 catalog。"""
        if isinstance(plugin, type):
            return plugin
        if isinstance(plugin, str):
            return self._plugins.get(plugin)
        return None


def _resolve_classpath_only(tokens: tuple[str, ...], *, ctx: str) -> list[type]:
    """PR-5 兼容：catalog 缺位时按 legacy class-path 解析。

    仅 class-path 形态被解析；id-form token（catalog miss）**静默跳过**
    （tokens 留待 :meth:`EventRegistry.refresh` 在 catalog 注入后重解析）。
    这条路径只在 boot 期 catalog 未到位时被走：
    - 测试场景（``EventRegistry.load`` 直调后立刻调 :meth:`refresh`）；
    - 生产 boot 期 ``setup_bus`` 调用,后续 ``_register_event_pipeline`` 注入 catalog。
    """
    out: list[type] = []
    for token in tokens:
        if _looks_like_class_path(token):
            out.append(_resolve_class(token, base_cls=object, ctx=f"ctx={ctx} token={token!r}"))
            continue
        # id-form token catalog 缺位 → 静默跳过,留待 refresh 重解析。
    return out


def _resolve_tokens(
    tokens: tuple[str, ...],
    catalog: Mapping[str, type],
    *,
    strict: bool = True,
) -> list[type]:
    """PR-5：把 token 序列解析为 type 列表（catalog 优先 + class-path fallback）。

    - catalog 命中 → 直接用 catalog[type]；
    - class-path 形态且 import 成功 → 用 import 的 type；
    - 都不命中：
      - ``strict=True``（默认）→ 抛 :class:`UnknownPluginIdError`；
      - ``strict=False`` → 跳过该 token,日志记 warning。
        生产 boot ``refresh()`` 走 strict=False；测试 / 验证脚本走 strict=True。
    """
    out: list[type] = []
    for token in tokens:
        if token in catalog:
            out.append(catalog[token])
            continue
        if _looks_like_class_path(token):
            try:
                out.append(_resolve_class(token, base_cls=object, ctx=f"token={token!r}"))
            except UnknownCategoryError as exc:
                msg = f"class-path token import 失败: {token}"
                if strict:
                    raise UnknownPluginIdError(token, msg) from exc
                _log.warning("%s;strict=False 下跳过", msg)
            continue
        msg = f"id-form token catalog miss: {token}"
        if strict:
            raise UnknownPluginIdError(token, msg)
        _log.warning("%s;strict=False 下跳过", msg)
    return out


__all__ = ["EventRegistry", "EventSpec"]

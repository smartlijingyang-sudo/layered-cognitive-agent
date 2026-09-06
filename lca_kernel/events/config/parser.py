"""consumer_rules 前缀规则解析与匹配 —— ADR-0183 PR-6。

事件配置 yaml 的顶层 ``consumer_rules:`` 段把逐 category 的 subscribers
白名单折叠为前缀规则。本模块是该规则形态的唯一解析/匹配实现：

- ``registry.py`` 用 ``resolve=`` typed class 解析器装载鉴权矩阵；
- ``scripts/verify_consumer_rules_equivalence.py`` 用恒等 resolve 在字符串
  级校验折叠前后授权集合全等。

匹配语义：一个 category 命中的**所有**规则的 subscribers 求并集（规则间
是 union，不是覆盖；更细前缀的规则用来给子树追加订阅者）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SubscriberRule(Generic[T]):
    """单条前缀规则：``category.value.startswith(prefix)`` 的事件授予
    ``subscribers`` 内全部插件订阅权。"""

    prefix: str
    subscribers: frozenset[T]


def rule_matches(category_value: str, rule: SubscriberRule[Any]) -> bool:
    """category 值是否命中规则（前缀匹配）。"""
    return category_value.startswith(rule.prefix)


def subscribers_from_rules(category_value: str, rules: Sequence[SubscriberRule[T]]) -> frozenset[T]:
    """category 命中的所有规则的 subscribers 并集；无命中 → 空集。"""
    out: set[T] = set()
    for rule in rules:
        if rule_matches(category_value, rule):
            out.update(rule.subscribers)
    return frozenset(out)


def parse_consumer_rules(
    entries: Any, resolve: Callable[[str], T], *, ctx: str
) -> tuple[SubscriberRule[T], ...]:
    """解析 yaml 顶层 ``consumer_rules`` 段为规则元组。

    每条规则形如 ``{prefix: "spine.", subscribers: [<全限定类路径>...]}``；
    每个条目经 ``resolve`` 解析，解析失败语义由调用方决定（registry 传
    ``_resolve_class``，失败抛 UnknownCategoryError，机制 fail-fast）。

    段缺失（``entries is None``）→ 空元组；结构非法 → ValueError。
    """
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise ValueError(f"{ctx}: consumer_rules 必须是 list")
    out: list[SubscriberRule[T]] = []
    for i, entry in enumerate(entries):
        rule_ctx = f"{ctx} consumer_rules[{i}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("prefix"), str):
            raise ValueError(f"{rule_ctx}: 规则必须是含字符串 prefix 的 mapping")
        prefix = entry["prefix"]
        if not prefix:
            raise ValueError(f"{rule_ctx}: prefix 不能为空")
        raw_subs = entry.get("subscribers") or []
        if not isinstance(raw_subs, list):
            raise ValueError(f"{rule_ctx}: subscribers 必须是 list")
        out.append(
            SubscriberRule(
                prefix=prefix,
                subscribers=frozenset(resolve(str(s)) for s in raw_subs),
            )
        )
    return tuple(out)


__all__ = [
    "SubscriberRule",
    "parse_consumer_rules",
    "rule_matches",
    "subscribers_from_rules",
]

"""Built-in precondition / terminal_predicate registry (ADR-0214 §6).

Callable 名字 → callable 的 SSOT。Profile YAML 用字符串名引用,避免
直接序列化 callable。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.harness.graph.traversal import PhaseTraversal

Predicate = Callable[[PhaseTraversal], bool]
_REGISTRY: dict[str, Predicate] = {}


def register(name: str, predicate: Predicate) -> None:
    """Register a named predicate. Idempotent (overwrite OK)."""
    _REGISTRY[name] = predicate


def resolve(name: str) -> Predicate | None:
    """Look up a registered predicate by name. None = not registered."""
    return _REGISTRY.get(name)


def known_predicates() -> tuple[str, ...]:
    """Return sorted tuple of all registered predicate names."""
    return tuple(sorted(_REGISTRY.keys()))


def reset_for_tests() -> None:
    """Drop every registration. Tests may use this to start from a clean slate.

    Not part of the production API; production code must never call this.
    """
    _REGISTRY.clear()


# ── Built-in predicates (PR-C initial set) ──────────────────────────────


def perceive_has_minimum_context(t: PhaseTraversal) -> bool:
    """perceive 节点 precondition: 至少要看到 user_text 或 attachment。

    不满足 → 不计入 visit_counts, 允许重试 (PR-C Step 2 行为)。
    """
    artifacts = t.artifacts or {}
    # user_text / staged_attachments 任一存在即满足
    return bool(
        artifacts.get("user_text")
        or artifacts.get("staged_attachments")
        or artifacts.get("clock")  # 时钟 always present
    )


def perceive_context_complete(t: PhaseTraversal) -> bool:
    """perceive 节点 terminal_predicate: context 完整 → 可跳过 perceive 后续。

    满足 → 强制 advance 到 stop (PR-C Step 3 行为, 通过 on_terminal 回调)。
    """
    artifacts = t.artifacts or {}
    # 已看到 user_text + 至少 1 个 staged attachment 或 sensor data
    has_user_text = bool(artifacts.get("user_text"))
    has_attachment = bool(artifacts.get("staged_attachments"))
    has_sensor = any(isinstance(key, str) and key.startswith("sensor.") for key in artifacts)
    return has_user_text and (has_attachment or has_sensor)


# 注册 built-in
register("perceive.has_minimum_context", perceive_has_minimum_context)
register("perceive.context_complete", perceive_context_complete)


__all__ = [
    "Predicate",
    "known_predicates",
    "perceive_context_complete",
    "perceive_has_minimum_context",
    "register",
    "reset_for_tests",
    "resolve",
]

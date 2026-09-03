"""Pipeline 声明式编排 —— ADR-0183 §3.3。

Profile 启动时调 ``bus.register_pipeline(pipeline)``；Pipeline 把 hooks /
sinks / consumer_rules 三段声明一次性装载到 EventBus。装载后不可热替换
（按 YAGNI；如需见 ADR-0183 §5）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca_kernel.events.bus import FailureSemantics
from lca_kernel.events.hooks import FailureAction

if TYPE_CHECKING:
    from lca.contracts.event import Category


# ── 公开枚举 / dataclass ─────────────────────────────────────────────────


class Stage(str, Enum):
    """hook 装载阶段。"""

    PRE_DISPATCH = "pre_dispatch"
    POST_DISPATCH = "post_dispatch"
    ON_FAILURE = "on_failure"


@dataclass(frozen=True, slots=True)
class HookSpec:
    """单条 hook 装载声明。"""

    id: str
    hook: type
    stage: Stage
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SinkSpec:
    """单条 sink 装载声明。"""

    id: str
    backend: type
    failure: FailureSemantics
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumerRule:
    """前缀匹配规则,替代 yaml 逐 category 列举。"""

    prefix: str
    plugins: tuple[type, ...]
    failure: FailureSemantics = FailureSemantics.CONTAINED


@dataclass(frozen=True, slots=True)
class Pipeline:
    """Profile 装载的声明式编排；3 段：hooks / sinks / consumer_rules。"""

    name: str
    version: int = 1
    hooks: tuple[HookSpec, ...] = ()
    sinks: tuple[SinkSpec, ...] = ()
    consumer_rules: tuple[ConsumerRule, ...] = ()


# ── 路由 helpers ─────────────────────────────────────────────────────────


def matches_rule(category: Category, rule: ConsumerRule) -> bool:
    """category 是否命中 rule(按 category.value 的前缀匹配)。"""
    return category.value.startswith(rule.prefix)


# ── yaml 解析 ────────────────────────────────────────────────────────────


def parse_pipeline_yaml(path: Path) -> Pipeline:
    """解析 ADR-0183 §3.3 给的 yaml 结构。

    若文件不存在,返回空 Pipeline(stage 全空) —— 允许 Pipeline 装载为可选步骤。
    """
    if not path.exists():
        return Pipeline(name=path.stem or "empty")
    import yaml  # 局部 import:保持本模块可独立 import 无副作用

    with path.open(encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh) or {}
    pipeline = data.get("pipeline") if isinstance(data, dict) else None
    if not isinstance(pipeline, dict):
        return Pipeline(name=path.stem or "empty")
    name = str(pipeline.get("name", path.stem or "empty"))
    version = int(pipeline.get("version", 1))
    hooks = _parse_hooks(pipeline.get("hooks") or [])
    sinks = _parse_sinks(pipeline.get("sinks") or [])
    rules = _parse_rules(pipeline.get("consumer_rules") or [])
    return Pipeline(
        name=name,
        version=version,
        hooks=hooks,
        sinks=sinks,
        consumer_rules=rules,
    )


def _parse_hooks(entries: list[Any]) -> tuple[HookSpec, ...]:
    out: list[HookSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out.append(
            HookSpec(
                id=str(entry.get("id", "")),
                hook=_resolve_type(str(entry.get("hook", "")), ctx="hook"),
                stage=Stage(str(entry.get("stage", Stage.PRE_DISPATCH.value))),
                config=dict(entry.get("config") or {}),
            )
        )
    return tuple(out)


def _parse_sinks(entries: list[Any]) -> tuple[SinkSpec, ...]:
    out: list[SinkSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out.append(
            SinkSpec(
                id=str(entry.get("id", "")),
                backend=_resolve_type(str(entry.get("backend", "")), ctx="sink"),
                failure=FailureSemantics(
                    str(entry.get("failure", FailureSemantics.CONTAINED.value))
                ),
                config=dict(entry.get("config") or {}),
                depends_on=(
                    str(entry["depends_on"]) if entry.get("depends_on") is not None else None
                ),
            )
        )
    return tuple(out)


def _parse_rules(entries: list[Any]) -> tuple[ConsumerRule, ...]:
    out: list[ConsumerRule] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        plugins = tuple(
            _resolve_type(str(p), ctx="rule.plugin")
            for p in entry.get("plugins", entry.get("consumers", ())) or ()
            if p
        )
        out.append(
            ConsumerRule(
                prefix=str(entry.get("prefix", "")),
                plugins=plugins,
                failure=FailureSemantics(
                    str(entry.get("failure", FailureSemantics.CONTAINED.value))
                ),
            )
        )
    return tuple(out)


def _resolve_type(full_path: str, *, ctx: str) -> type:
    """解析 ``module.ClassName`` 全路径到 class 对象。

    解析失败 → 抛 ImportError / AttributeError,parse_pipeline_yaml 透传;
    框架级(lca_kernel.*)的 hook / sink 由 Pipeline 装载时再走实例化。
    """
    from importlib import import_module

    if not full_path:
        raise ValueError(f"{ctx}: 空的全路径")
    module_path, _, class_name = full_path.rpartition(".")
    if not module_path:
        raise ValueError(f"{ctx}: 缺少模块路径: {full_path!r}")
    module = import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type):
        raise ValueError(f"{ctx}: 不可解析 {full_path!r}")
    return cls


__all__ = [
    "ConsumerRule",
    "FailureAction",
    "FailureSemantics",
    "HookSpec",
    "Pipeline",
    "SinkSpec",
    "Stage",
    "matches_rule",
    "parse_pipeline_yaml",
]

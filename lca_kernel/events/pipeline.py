"""Pipeline 声明式编排 —— ADR-0183 §3.3。

Profile 启动时调 ``bus.register_pipeline(pipeline)``；Pipeline 把 hooks /
sinks / consumer_rules 三段声明一次性装载到 EventBus。装载后不可热替换
（按 YAGNI；如需见 ADR-0183 §5）。
"""

from __future__ import annotations

from collections.abc import Mapping
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


def parse_pipeline_yaml(
    path: Path, *, catalog: Mapping[str, type] | None = None
) -> Pipeline:
    """解析 ADR-0183 §3.3 给的 yaml 结构。

    若文件不存在,返回空 Pipeline(stage 全空) —— 允许 Pipeline 装载为可选步骤。

    PR-5：``catalog`` 是可选的 ``id → marker class`` 映射；hooks /
    sinks 段接受 ``plugin: <id>`` 字段，按 catalog 解析为 class。
    缺省 = 仅 class-path 形态可用（向后兼容）。
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
    hooks = _parse_hooks(pipeline.get("hooks") or [], catalog=catalog)
    sinks = _parse_sinks(pipeline.get("sinks") or [], catalog=catalog)
    rules = _parse_rules(pipeline.get("consumer_rules") or [], catalog=catalog)
    return Pipeline(
        name=name,
        version=version,
        hooks=hooks,
        sinks=sinks,
        consumer_rules=rules,
    )


def _parse_hooks(
    entries: list[Any], *, catalog: Mapping[str, type] | None = None
) -> tuple[HookSpec, ...]:
    out: list[HookSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hook_path = str(entry.get("hook", ""))
        plugin_id = entry.get("plugin")
        if plugin_id is not None:
            hook_cls = _resolve_via_catalog(str(plugin_id), catalog=catalog, ctx="hook")
        else:
            hook_cls = _resolve_type(hook_path, ctx="hook")
        out.append(
            HookSpec(
                id=str(entry.get("id", "")),
                hook=hook_cls,
                stage=Stage(str(entry.get("stage", Stage.PRE_DISPATCH.value))),
                config=dict(entry.get("config") or {}),
            )
        )
    return tuple(out)


def _parse_sinks(
    entries: list[Any], *, catalog: Mapping[str, type] | None = None
) -> tuple[SinkSpec, ...]:
    out: list[SinkSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        backend_path = str(entry.get("backend", ""))
        plugin_id = entry.get("plugin")
        if plugin_id is not None:
            backend_cls = _resolve_via_catalog(str(plugin_id), catalog=catalog, ctx="sink")
        else:
            backend_cls = _resolve_type(backend_path, ctx="sink")
        out.append(
            SinkSpec(
                id=str(entry.get("id", "")),
                backend=backend_cls,
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


def _parse_rules(
    entries: list[Any], *, catalog: Mapping[str, type] | None = None
) -> tuple[ConsumerRule, ...]:
    out: list[ConsumerRule] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        plugins: list[type] = []
        for raw in entry.get("plugins", entry.get("consumers", ())) or ():
            if not raw:
                continue
            raw_str = str(raw)
            # PR-5：consumer_rules 不走 registry（由 EventRegistry 解析 yaml
            # 时一并物化），仅保留 class-path 形态；id-form 在 yaml
            # ``subscribers:`` 字段直接表达，与此处解析器正交。
            plugins.append(_resolve_type(raw_str, ctx="rule.plugin"))
        out.append(
            ConsumerRule(
                prefix=str(entry.get("prefix", "")),
                plugins=tuple(plugins),
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

    COMPAT(delete-when: rg "lca.plugins.[A-Za-z0-9_]+.[A-Z][A-Za-z]+$" lca_kernel/events/config
    profiles/event-pipeline = 0;tracking: 2026-09-04-plugin-universe-single-entry PR-5)
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


def _resolve_via_catalog(
    plugin_id: str, *, catalog: Mapping[str, type] | None, ctx: str
) -> type:
    """PR-5：通过 catalog 解析 id 到 class。

    catalog miss → 抛 ``KeyError``（pipeline_loader 转为
    ``FileNotFoundError``-like 错误）；class-path 形态不在本函数处理范围
    （用 ``_resolve_type``）。
    """
    if catalog is None:
        raise ValueError(
            f"{ctx}: plugin={plugin_id!r} 需要 catalog；当前调用方未传 catalog"
        )
    if plugin_id not in catalog:
        raise KeyError(plugin_id)
    return catalog[plugin_id]


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

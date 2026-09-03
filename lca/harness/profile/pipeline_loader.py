"""Event Pipeline 装配 —— Profile ``pipeline:`` 段装载(ADR-0183 §3.3 / PR-7)。

职责(两个公开面):

- :func:`load_pipeline_for_profile` / :func:`load_profile_pipeline`:
  从 Profile 发现并构造 :class:`~lca_kernel.events.pipeline.Pipeline`。
  三级发现,命中即止:

  1. ``pipeline:`` 内联段 —— 直接是 pipeline mapping;
  2. ``pipeline: <path>`` —— 显式文件引用,相对 Profile 所在目录解析,
     文件不存在 → ``FileNotFoundError``(fail-closed,显式声明不可静默丢);
  3. 约定路径 ``<profile 目录>/event-pipeline/<profile stem>.yaml``。

  三者皆无 → 返回 ``None``;Pipeline 装载是可选步骤,缺失不影响 boot。

- :func:`apply_pipeline` / :func:`register_pipeline_once`:
  把 Pipeline 声明挂到 EventBus 已有公开面。bus 本体不改;当前
  ``register_pipeline`` 只装载 hooks,sinks / consumer_rules 的 publish 期
  派发需要 bus 增强(见 ADR-0183 §5 集成阶段),本模块先把实例化与
  订阅接线准备好。

解析复用 :mod:`lca_kernel.events.pipeline` 的段解析器(``_parse_hooks`` /
``_parse_sinks`` / ``_parse_rules``),内联段与文件引用因此只有一套语义。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from weakref import WeakKeyDictionary

import yaml

from lca.harness.profile.resolve import ResolvedProfile
from lca_kernel.events.bus import ConsumerHandle, EventBus
from lca_kernel.events.pipeline import (
    Pipeline,
    _parse_hooks,
    _parse_rules,
    _parse_sinks,
    matches_rule,
    parse_pipeline_yaml,
)

__all__ = [
    "AppliedPipeline",
    "ProfilePipeline",
    "apply_pipeline",
    "load_pipeline_for_profile",
    "load_profile_pipeline",
    "pipeline_from_mapping",
    "register_pipeline_once",
]


@dataclass(frozen=True, slots=True)
class ProfilePipeline:
    """Profile 声明的 Pipeline 装载结果。

    ``options`` 是 yaml ``pipeline.options`` 原样映射;:class:`Pipeline`
    契约不含 options 段,inspect 与运行期元数据从本字段读。
    """

    pipeline: Pipeline
    options: Mapping[str, Any]
    source: str
    """装载来源:文件路径,或 ``<profile path>#pipeline``(内联段)。"""


@dataclass(frozen=True, slots=True)
class AppliedPipeline:
    """apply_pipeline 的装配回执。

    ``sinks`` 已按 ``spec.backend(**spec.config)`` 实例化,**未绑定**
    run_id —— run 开始时由运行时调 ``set_run_id`` 后才可 append。
    """

    pipeline: Pipeline
    sinks: Mapping[str, Any]
    consumer_handles: tuple[ConsumerHandle, ...]


# ── 发现 + 构造 ──────────────────────────────────────────────────────────


def load_pipeline_for_profile(profile: ResolvedProfile | Path | str) -> Pipeline | None:
    """Profile 声明了 Pipeline 则返回之,否则 ``None``(装载可选)。"""
    bundle = load_profile_pipeline(profile)
    return bundle.pipeline if bundle is not None else None


def load_profile_pipeline(profile: ResolvedProfile | Path | str) -> ProfilePipeline | None:
    """三级发现 + 构造;皆无 → ``None``。Profile 文件不存在 → ``None``
    (程序化 entries 无文件,属正常路径)。"""
    profile_path = _profile_path(profile)
    if profile_path is None or not profile_path.is_file():
        return None
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    section = data.get("pipeline") if isinstance(data, dict) else None

    if isinstance(section, str):
        ref = _resolve_reference(profile_path, section)
        pipeline = parse_pipeline_yaml(ref)
        return ProfilePipeline(pipeline=pipeline, options=_read_options(ref), source=str(ref))
    if isinstance(section, Mapping):
        options = section.get("options")
        return ProfilePipeline(
            pipeline=pipeline_from_mapping(section, name_fallback=profile_path.stem),
            options=(
                MappingProxyType(dict(options))
                if isinstance(options, Mapping)
                else MappingProxyType({})
            ),
            source=f"{profile_path}#pipeline",
        )

    conventional = profile_path.parent / "event-pipeline" / f"{profile_path.stem}.yaml"
    if conventional.is_file():
        return ProfilePipeline(
            pipeline=parse_pipeline_yaml(conventional),
            options=_read_options(conventional),
            source=str(conventional),
        )
    return None


def pipeline_from_mapping(
    mapping: Mapping[str, Any], *, name_fallback: str = "pipeline"
) -> Pipeline:
    """从 ``pipeline:`` mapping 构造 Pipeline;段解析复用 pipeline.py 解析器。"""
    return Pipeline(
        name=str(mapping.get("name") or name_fallback),
        version=int(mapping.get("version", 1)),
        hooks=_parse_hooks(list(mapping.get("hooks") or [])),
        sinks=_parse_sinks(list(mapping.get("sinks") or [])),
        consumer_rules=_parse_rules(list(mapping.get("consumer_rules") or [])),
    )


# ── EventBus 装配 ────────────────────────────────────────────────────────

# 同一 bus 实例上 (name, version) 只装载一次。key 挂在 bus 实例上:
# 测试重置 EventBus 单例后新实例自动恢复可装载,无需手工清状态。
_REGISTERED: WeakKeyDictionary[EventBus[Any], set[tuple[str, int]]] = WeakKeyDictionary()


def register_pipeline_once(bus: EventBus[Any], pipeline: Pipeline) -> bool:
    """幂等版 ``bus.register_pipeline``;同名同版重复装载跳过,返回是否装载。"""
    key = (pipeline.name, pipeline.version)
    seen = _REGISTERED.get(bus)
    if seen is None:
        seen = set()
        _REGISTERED[bus] = seen
    if key in seen:
        return False
    bus.register_pipeline(pipeline)
    seen.add(key)
    return True


def apply_pipeline(bus: EventBus[Any], pipeline: Pipeline) -> AppliedPipeline:
    """把 Pipeline 三段挂到 bus 已有公开面(装配用,不取代集成阶段)。

    - hooks: 经 ``bus.register_pipeline`` 装载(bus 当前只实装本段);
    - sinks: 按 ``spec.backend(**spec.config)`` 实例化并随回执返回;
      publish 期落盘派发需 bus 支持(报告:集成阶段增强);
    - consumer_rules: 按前缀展开到闭集 Category,经 ``bus.subscribe``
      逐条订阅;插件必须可无参构造,回调取实例 ``__call__`` 或
      ``on_event``。鉴权失败 → ``UnauthorizedSubscribeError`` 上抛。
    """
    register_pipeline_once(bus, pipeline)
    sinks: dict[str, Any] = {}
    for spec in pipeline.sinks:
        instance = spec.backend(**spec.config)
        sinks[spec.id] = instance
        # 装载到 bus:publish 期经 _dispatch_sinks 派发(FD-1)。
        # run_id 仍由运行时经 set_run_id 绑定;此处只装配实例。
        bus.mount_sink(spec.id, instance, failure=spec.failure)
    handles = _apply_consumer_rules(bus, pipeline)
    return AppliedPipeline(pipeline=pipeline, sinks=sinks, consumer_handles=tuple(handles))


# ── 内部 ─────────────────────────────────────────────────────────────────


def _apply_consumer_rules(bus: EventBus[Any], pipeline: Pipeline) -> list[ConsumerHandle]:
    """前缀规则展开到闭集 Category,经 bus.subscribe 逐条订阅。

    鉴权矩阵是 SSOT:只对 ``registry.can_subscribe`` 已授权的 (plugin,
    category) 订阅;无 spec 的 category 本就无法 publish,跳过。某插件在
    其规则前缀下一个授权 category 都没有 → 配置错误,上抛。
    """
    from lca.contracts.event import Category
    from lca_kernel.events.errors import UnauthorizedSubscribeError

    handles: list[ConsumerHandle] = []
    for rule in pipeline.consumer_rules:
        for plugin in rule.plugins:
            categories = [
                category
                for category in Category
                if matches_rule(category, rule) and bus.registry.can_subscribe(plugin, category)
            ]
            if not categories:
                raise UnauthorizedSubscribeError(plugin.__qualname__, f"{rule.prefix}*")
            callback = _plugin_callback(plugin)
            for category in categories:
                handles.append(
                    bus.subscribe(
                        plugin=plugin,
                        category=category,
                        on_event=callback,
                        failure=rule.failure,
                    )
                )
    return handles


def _plugin_callback(plugin: type) -> Any:
    """实例化插件并取其 ``(payload, ref)`` 回调形态(__call__ 或 on_event)。"""
    instance = plugin()
    if callable(instance):
        return instance
    on_event = getattr(instance, "on_event", None)
    if callable(on_event):
        return on_event
    raise TypeError(
        f"consumer plugin {plugin.__qualname__} 既不可调用也无 on_event,无法作为 pipeline 回调装配"
    )


def _profile_path(profile: ResolvedProfile | Path | str) -> Path | None:
    if isinstance(profile, ResolvedProfile):
        raw = profile.profile_path
        return Path(raw) if raw else None
    return Path(profile)


def _resolve_reference(profile_path: Path, ref: str) -> Path:
    candidate = Path(ref)
    if not candidate.is_absolute():
        candidate = profile_path.parent / candidate
    if not candidate.is_file():
        raise FileNotFoundError(
            f"profile {profile_path} 显式声明 pipeline={ref!r},文件不存在: {candidate}"
        )
    return candidate


def _read_options(path: Path) -> Mapping[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pipeline = data.get("pipeline") if isinstance(data, dict) else None
    options = pipeline.get("options") if isinstance(pipeline, dict) else None
    if isinstance(options, Mapping):
        return MappingProxyType(dict(options))
    return MappingProxyType({})

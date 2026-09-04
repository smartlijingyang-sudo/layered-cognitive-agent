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
  把 Pipeline 声明接到已有公开面。生产 boot 走 ``register_pipeline_once``
  (只装 hooks)。``apply_pipeline`` 另实例化 sinks 写入回执 map(不
  ``bus.mount_sink``);``consumer_rules`` 仅作可检视元数据,不调用
  :meth:`~lca_kernel.events.bus.EventBus.subscribe`。Session SSOT 路径下
  投递 / 持久化由 Session.observe / JsonlSessionPersistence 负责
  (ADR-0186 PR-3f)。

解析复用 :mod:`lca_kernel.events.pipeline` 的段解析器(``_parse_hooks`` /
``_parse_sinks`` / ``_parse_rules``),内联段与文件引用因此只有一套语义。

PR-5：hooks / sinks 段接受 ``plugin: <id>`` 字段,经 catalog 解析为 class。
catalog 来源 = ``EventRegistry._plugins``（同 PR-5 兼容期 token 解析
用同一份）。``load_pipeline_for_profile`` 系列入口接受可选 ``catalog`` 参数,
缺省 = 仅 class-path 形态可用（向后兼容）。
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

    ``sinks`` 已按 ``spec.backend(**spec.config)`` 实例化并放入 map,供调用方
    检视;**不** ``bus.mount_sink``。``consumer_handles`` 恒为空元组:
    consumer_rules 只作声明式元数据,本函数不订阅 EventBus。
    Session SSOT 路径下投递 / 持久化由 Session.observe /
    JsonlSessionPersistence 负责(ADR-0186 PR-3f)。
    """

    pipeline: Pipeline
    sinks: Mapping[str, Any]
    consumer_handles: tuple[ConsumerHandle, ...]


# ── 发现 + 构造 ──────────────────────────────────────────────────────────


def load_pipeline_for_profile(
    profile: ResolvedProfile | Path | str,
    *,
    catalog: Mapping[str, type] | None = None,
) -> Pipeline | None:
    """Profile 声明了 Pipeline 则返回之,否则 ``None``(装载可选)。

    PR-5：``catalog`` 是可选 ``id → marker class`` 映射；hooks / sinks 段
    ``plugin:`` 字段据此解析。
    """
    bundle = load_profile_pipeline(profile, catalog=catalog)
    return bundle.pipeline if bundle is not None else None


def load_profile_pipeline(
    profile: ResolvedProfile | Path | str,
    *,
    catalog: Mapping[str, type] | None = None,
) -> ProfilePipeline | None:
    """三级发现 + 构造;皆无 → ``None``。Profile 文件不存在 → ``None``
    (程序化 entries 无文件,属正常路径)。"""
    profile_path = _profile_path(profile)
    if profile_path is None or not profile_path.is_file():
        return None
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    section = data.get("pipeline") if isinstance(data, dict) else None

    if isinstance(section, str):
        ref = _resolve_reference(profile_path, section)
        pipeline = parse_pipeline_yaml(ref, catalog=catalog)
        return ProfilePipeline(pipeline=pipeline, options=_read_options(ref), source=str(ref))
    if isinstance(section, Mapping):
        options = section.get("options")
        return ProfilePipeline(
            pipeline=pipeline_from_mapping(
                section, name_fallback=profile_path.stem, catalog=catalog
            ),
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
            pipeline=parse_pipeline_yaml(conventional, catalog=catalog),
            options=_read_options(conventional),
            source=str(conventional),
        )
    return None


def pipeline_from_mapping(
    mapping: Mapping[str, Any],
    *,
    name_fallback: str = "pipeline",
    catalog: Mapping[str, type] | None = None,
) -> Pipeline:
    """从 ``pipeline:`` mapping 构造 Pipeline;段解析复用 pipeline.py 解析器。"""
    return Pipeline(
        name=str(mapping.get("name") or name_fallback),
        version=int(mapping.get("version", 1)),
        hooks=_parse_hooks(list(mapping.get("hooks") or []), catalog=catalog),
        sinks=_parse_sinks(list(mapping.get("sinks") or []), catalog=catalog),
        consumer_rules=_parse_rules(list(mapping.get("consumer_rules") or []), catalog=catalog),
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
    """装配 Pipeline:hooks 注册 + sinks 实例化(不 mount)。

    - hooks: 经 ``register_pipeline_once`` → ``bus.register_pipeline``;
    - sinks: 按 ``spec.backend(**spec.config)`` 实例化写入回执 ``sinks`` map,
      **不** ``bus.mount_sink``。持久化由 Session.observe /
      JsonlSessionPersistence 在 Session SSOT 路径负责(ADR-0186 PR-3f);
    - consumer_rules: 声明式元数据,供 inspect / CLI 解析与展示;
      本函数不订阅 EventBus。投递由 Session.observe 负责;需要总线
      订阅时由调用方显式调用 :meth:`EventBus.subscribe`。
      ``consumer_handles`` 恒为空。

    生产 boot 仍只用 ``register_pipeline_once``(hooks);本函数供检视
    sinks map 的调用方。
    """
    register_pipeline_once(bus, pipeline)
    sinks: dict[str, Any] = {}
    for spec in pipeline.sinks:
        sinks[spec.id] = spec.backend(**spec.config)
    return AppliedPipeline(pipeline=pipeline, sinks=sinks, consumer_handles=())


# ── 内部 ─────────────────────────────────────────────────────────────────


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

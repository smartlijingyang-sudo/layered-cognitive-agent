"""EventDescriptor — cordis_name 派生（ADR-0169 L12 / I-CURSOR-4）。

spine.append(canonical_name) 内部查表决定是否 ``ctx.emit(cordis_name)``;业务
路径不直接 ``ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')``。本模块
是该约束的契约层,``scripts/check_cordis_event_derivation.py`` 是其机器
可执行门禁（PR-13 / PR-30 共同生效）。

设计来源:ADR-0169 §L12 + §D6(I-CURSOR-4)+ ADR-0168-final §D14。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.cordis_event_table import (
    UnknownCordisEventError,
    lookup_cordis_name,
)


@dataclass(frozen=True)
class EventDescriptor:
    """单个 spine 事件 EP 的描述（cordis 派生 + schema 版本号）。

    字段语义钉死(ADR-0169 L12 + L15):
    - ``execution_point``:spine EP 字面量,e.g. ``"writable.step.start"``。
    - ``cordis_name``:派生到 cordis 事件总线的事件名,以 ``"agent."``
      前缀收口;或 ``None`` 表示该 EP 不暴露给 cordis(仅 spine)。
    - ``schema_version``:L15 方向感知 journal 格式拒绝的版本号;
      写盘时记录,读盘时 ``< 1`` ⇒ ``VersionTooOld``,``> `` 时段
      当前 ``SCHEMA_VERSION`` ⇒ ``VersionTooNew``。
    - ``ignorable``:未知 event_type + ``ignorable is False`` ⇒
      ``UnknownEventType``(L15 第三子类型)。
    """

    execution_point: str
    cordis_name: str | None
    schema_version: int
    ignorable: bool = False

    @classmethod
    def derive(cls, execution_point: str) -> EventDescriptor:
        """由 execution_point 派生到 EventDescriptor。

        失败模式:EP 未登记 ⇒ ``UnknownCordisEventError``(KeyError 子类);
        调用方可与 L15 第三子类型 ``UnknownEventType`` 对齐。

        派生是 deterministic 与 zero-side-effect:同一 EP 多次派生得到
        字面相同的 EventDescriptor;无 I/O,无全局可变状态。
        """
        try:
            entry = lookup_cordis_name(execution_point)
        except UnknownCordisEventError as exc:
            raise UnknownCordisEventError(
                f"未登记的 execution_point={execution_point!r};所有 spine EP "
                f"必须先在 cordis_event_table 登记才能 derive"
            ) from exc
        return cls(
            execution_point=execution_point,
            cordis_name=entry.cordis_name,
            schema_version=entry.schema_version,
            ignorable=entry.ignorable,
        )


__all__ = ["EventDescriptor", "UnknownCordisEventError"]

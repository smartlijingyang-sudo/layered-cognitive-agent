"""``writable.serializer.label`` —— Label Serializer 替换实现。

输出 ``LABEL|<execution_point>|<sequence>|<run_id>\\n`` 形式，仅保留
metadata（无 payload）。用于归档脱敏场景，或 OII 调试时只看 EP 类型。

注意：本 serializer **不是** Protobuf；如需二进制格式请引入外部
``writable.serializer.protobuf`` 实现，不要在本文件 fake 协议（ADR-0167
D13 设计尊严：禁止「起名 Protobuf 输出文本」的占位假货）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.event_record import EventRecord


@dataclass
class LabelSerializer:
    """Label-only serializer：仅 metadata，不含 payload。"""

    def serialize(self, record: EventRecord) -> bytes:
        body = f"LABEL|{record.execution_point}|{record.sequence}|{record.run_id}\n"
        return body.encode("utf-8")


@plugin(
    id="writable.serializer.label",
    provides=("serializer",),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description="Label-only serializer; metadata only, no payload.",
)
def setup(ctx: PluginContext, config: Any) -> None:
    ctx.provide("serializer", LabelSerializer())

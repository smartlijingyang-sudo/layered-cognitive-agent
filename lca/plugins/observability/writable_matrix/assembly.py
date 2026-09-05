"""Profile-side assembly plugin —— 默认 5 面装配（唯一真理源）。

profile 默认加载本插件即可获得 SSOT 形态；oii-debug / archive / test
通过独立 bundle 或 patch 替换某一面（emitter / driver / coalescer /
serializer / storage 任一）。
"""

from __future__ import annotations

from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.writable_matrix import (
    LineCoalescer,
    NdjsonSerializer,
    NullStorage,
    SpineEmitter,
    StandardDriver,
    WritableFaceRegistry,
)


@plugin(
    id="writable.matrix.default",
    provides=("writable_face_registry",),
    requires=("event_spine",),
    layer="L2",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "Default 5-face writable matrix (ADR-0167 D11). The single source of"
        " truth for default assembly — profile / bundle replacement plugins"
        " only override one face, not duplicate this composition."
    ),
)
def setup(ctx: PluginContext, config: Any) -> None:
    """用 spine 组装默认五面 registry;storage 面固定 Null(不落盘)。"""
    del config  # run_dir 已退役:storage 面不再写文件
    spine = ctx.require("event_spine")
    reg = WritableFaceRegistry()
    emitter = SpineEmitter()
    emitter.bind(spine)
    reg.register("emitter", emitter)
    reg.register("driver", StandardDriver())
    reg.register("coalescer", LineCoalescer())
    reg.register("serializer", NdjsonSerializer())
    # ADR-0186 单写者:<run_id>.spine.jsonl 归 Session / spine-sink 链拥有。
    # 原 RoutingFileStorage(ADR-0167 遗留)会开第二条写链,已退役。
    reg.register("storage", NullStorage())
    ctx.provide("writable_face_registry", reg)

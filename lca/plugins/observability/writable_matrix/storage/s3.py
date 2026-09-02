"""``writable.storage.s3`` —— S3 EventStorage 替换实现(占位 / TODO)。

ADR-0167 PR-10 仅交付 SQLiteStore;S3Sink 留作后续 PR
(避免引入 boto3 依赖 / 增加 LCA 内核依赖面)。

替代路径:
1. profile 注入自定义 storage plugin,writable.storage.s3 外部实现;
2. 用 MultiStorage 包装 SQLiteStore + 外部 boto3 sink;
3. 等 ADR-0167-followup 单独 PR,引入可选依赖组 [s3],boto3 仅在
   安装该组时导入。

按 ADR-0167 D12:不让 Coordinator 直接 import 任何具体实现;
S3 留 TODO 不影响矩阵完整性。

plugin id 仍注册为 ``writable.storage.s3``,profile 装配若误装会立即抛
``NotImplementedError`` (fail-fast),便于尽早暴露误配。
"""

from __future__ import annotations

from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class _S3SinkNotImplementedError(NotImplementedError):
    """S3Sink 是 PR-10 TODO;见本文件 docstring。"""


def _not_implemented() -> None:
    raise _S3SinkNotImplementedError(
        "S3Sink 是 ADR-0167 PR-10 TODO,见 lca/plugins/observability/writable_matrix/storage/s3.py。"
    )


@plugin(
    id="writable.storage.s3",
    provides=("storage",),
    layer="L0",
    kind=PluginKind.SEAM,
    description="S3 EventStorage (PR-10 TODO; not implemented in this milestone).",
)
def setup(ctx: PluginContext, config: Any) -> None:
    del ctx, config
    _not_implemented()

"""Process-local spine / EmitPipeline accessors —— 兼容 re-export。

holder 已下沉 ``lca.contracts.observability.spine_accessors``（SSOT）；
本模块保留旧路径兼容（wrap / 测试经此或经 wrap re-export 引用）。
"""

from __future__ import annotations

from lca.contracts.observability.spine_accessors import (
    _resolve_pipeline as _resolve_pipeline,
)
from lca.contracts.observability.spine_accessors import (
    _resolve_spine as _resolve_spine,
)
from lca.contracts.observability.spine_accessors import (
    resolve_active_pipeline as resolve_active_pipeline,
)
from lca.contracts.observability.spine_accessors import (
    resolve_active_spine as resolve_active_spine,
)
from lca.contracts.observability.spine_accessors import (
    set_active_pipeline_accessor as set_active_pipeline_accessor,
)
from lca.contracts.observability.spine_accessors import (
    set_active_spine_accessor as set_active_spine_accessor,
)

__all__ = [
    "resolve_active_pipeline",
    "resolve_active_spine",
    "set_active_pipeline_accessor",
    "set_active_spine_accessor",
]

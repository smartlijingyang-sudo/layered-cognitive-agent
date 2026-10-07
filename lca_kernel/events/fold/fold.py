"""Header fold — 从 spine.jsonl 重建 effective request header(ADR-0185 PR-0)。

对齐 deepseek-harness ``packages/core/session/src/request-header.ts`` 的
``canonicalHeader`` / ``headerEquals`` / ``sameSchema`` / ``foldRequestHeader``
语义;实现细节独立。本模块:

- 是纯函数集,无 I/O,无 ``print`` / ``logging`` / ``datetime.now`` 等副作用
- 与 PR-1 / PR-2 的 ``SpineLlmRequestHeaderPayload`` 解耦:仅消费
  :class:`SpineEventRecord` 的 ``category`` + ``payload`` dict,fields 由 yaml
  schema 在 PR-1 锁死
- 不依赖具体 LLM/Reasoner/Brain/Body/SafeExecutor:只读 ``SpineEventRecord``
  形态的事件流,任何上游(``<run_id>.spine.jsonl`` 重放、sub-batch 增量 fold、
  viewer 离线重建)都走同一路径

设计原则(ADR-0185 §3.4 + §3.5):

1. **canonicalHeader** — 空 ``system`` / 空 ``adapter_defaults`` / 空 ``tools``
   字段归一为 absent;fold / 比较 / 落盘用同一种表示。匹配 dsh 行为。
2. **headerEquals** — 字节级判等;``config`` 字段逐字段比对(对齐 dsh
   ``callConfigEquals``)、``tools`` 列表按 JSON 序列化对位比较(顺序敏感),
   ``system`` 字符串严格等。
3. **foldRequestHeader** — 单次走完事件流,保留最近一条 ``spine.llm.request.header``
   的 canonical 形态;``from_`` 续接上次 fold 结果,``step_id`` 限定 fold
   范围(对齐 ADR-0185 §3.4 dsh 对位)。
4. **foldSurface** — 单次走完事件流,按 ``surfaceOp`` append / replace 重建
   当前模型可见节点序列(ADR-0186 I-SESSION-2;对齐 dsh
   ``packages/core/session/src/surface.ts`` ``foldSurface``)。词表是 LCA
   spine / model-visible category,不是 dsh ``user/message`` 三件套。

不动 production 行为:无 ``Bus.publish``、无 sink 写入、无 EnvelopeBus 内部状态;
仅作为 viewer / explain / replay / debug-run 的离线重建函数。

delete-when:N/A(纯加法,后续 PR-2 publisher fold 状态、PR-3 viewer 重建、
PR-4 删旁路文件都依赖本模块做语义锚点)。

实现已拆分为 :mod:`lca_kernel.events.fold.inputs`(事件归一)、
:mod:`lca_kernel.events.fold.core`(fold 算法)、
:mod:`lca_kernel.events.fold.projection`(canonical 结果类型);
本模块是 re-export barrel,保持 ``lca_kernel.events.fold.fold`` 公共面不变。
"""

from lca_kernel.events.fold.core import (
    fold_step_tree,
    foldRequestHeader,
    foldSurface,
)
from lca_kernel.events.fold.inputs import (
    REQUEST_HEADER_CATEGORY,
    STEP_END_TYPE,
    STEP_START_TYPE,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_EVENT_TYPES,
    SURFACE_TOOL_RESULT_TYPE,
    SURFACE_USER_TYPE,
    TURN_END_TYPE,
    TURN_START_TYPE,
    SurfaceReplaceOp,
    isAppendSurfaceEvent,
    isReplacementSurfaceEvent,
    isSurfaceEligibleType,
    isSurfaceEvent,
)
from lca_kernel.events.fold.inputs import (
    SurfaceOp as SurfaceOp,
)
from lca_kernel.events.fold.projection import (
    EpochHeader,
    StepEntry,
    StepTree,
    SurfaceFoldReplacement,
    SurfaceFoldResult,
    TurnEntry,
    canonicalHeader,
    headerEquals,
)

__all__ = [
    "REQUEST_HEADER_CATEGORY",
    "STEP_END_TYPE",
    "STEP_START_TYPE",
    "SURFACE_ASSISTANT_TYPE",
    "SURFACE_EVENT_TYPES",
    "SURFACE_TOOL_RESULT_TYPE",
    "SURFACE_USER_TYPE",
    "TURN_END_TYPE",
    "TURN_START_TYPE",
    "EpochHeader",
    "StepEntry",
    "StepTree",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "SurfaceReplaceOp",
    "TurnEntry",
    "canonicalHeader",
    "foldRequestHeader",
    "foldSurface",
    "fold_step_tree",
    "headerEquals",
    "isAppendSurfaceEvent",
    "isReplacementSurfaceEvent",
    "isSurfaceEligibleType",
    "isSurfaceEvent",
]

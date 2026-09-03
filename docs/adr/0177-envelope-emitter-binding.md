# ADR-0177: EnvelopeEmitter binding — collapse runtime/agent reverse imports of spine reflectors

- Status: Proposed
- Date: 2026-09-03
- Supersedes: none
- Depends on:
  - AGENTS.md §1 工程思维 (依赖方向 / 单一职责)
  - AGENTS.md §3 五层单向依赖 (`contracts → infrastructure → cognition → runtime → agent`)
  - ADR-0074 (declarative cutover)
- Scope:
  - `lca/contracts/protocols/runtime/envelope_emitter.py` (new Protocol)
  - `lca/runtime/runtime_bindings.py` (add `envelope: EnvelopeEmitter` field)
  - `lca/runtime/{reducer,runtime_loop,runtime_lifecycle_emitter,checkpoint_resolution}.py`
  - `lca/agent/{cognitive_agent,team_handle}.py`
  - `lca/infrastructure/observability/envelope_emitter.py` (new default impl)
  - tests: `tests/runtime/test_envelope_emitter_binding.py`

## 0. 背景与现状痛点

L2 (`lca/runtime/`) 和 L3 (`lca/agent/`) 模块从 `lca.plugins.observability.spine.reflectors.{runtime,agent_spawn,cognition}` 拉取 envelope-emit helper:

```python
# lca/runtime/reducer.py:74, lca/runtime/runtime_loop.py:218, lca/runtime/runtime_lifecycle_emitter.py:83,
# lca/runtime/checkpoint_resolution.py:48, lca/agent/cognitive_agent.py:144, lca/agent/team_handle.py:62
from lca.plugins.observability.spine.reflectors.runtime import (
    emit_runtime_reducer_apply_start,
    emit_runtime_reducer_apply_end,
    ...
)
```

这是依赖方向反转 —— `runtime → plugin.observability`。`AGENTS.md` §1 用 "网关绑定具体认知实现 / 插件自行读取凭证" 的禁忌作为类比,此处等价的禁忌是 "L2/L3 模块反 import L4 plugin tree"。

最近 `git log --oneline` 的 11+ reducer 提交、8+ `runtime_loop.py` 提交、6+ `checkpoint_resolution.py` 提交每次都会触及其中至少一个文件 —— 副作用就是 envelope-emit helper 在每个调用点 inline 写一份 lazy import。

## 1. 第一性原理(机制,不是补丁)

**机制是什么**:envelope emission(emit reducer apply / lifecycle finally / exception caught / agent loop iteration)是 **runtime 协议**,不是 **plugin 自由函数**。Plugin tree 提供实现;runtime 把实现作为 bound capability 注入;调用方(`runtime_loop`、`reducer`、`runtime_lifecycle_emitter`、`agent`)用协议边界,不直接 import plugin。

**最干净的形态**:
- **协议 SSOT** = `EnvelopeEmitter` Protocol(`lca/contracts/protocols/runtime/envelope_emitter.py`),11 个 `emit_*` 方法
- **默认实现** = `SpineEnvelopeEmitter`(`lca/infrastructure/observability/envelope_emitter.py`),内部 lazy-import spine reflector
- **Bindings 注入** = `DeclarativeRuntimeBindings.envelope: EnvelopeEmitter`
- **调用方零 import** = 所有 8 处 inline import 替换为 `self._bindings.envelope.emit_*`

## 2. 设计

### 2.1 Protocol surface

```python
# lca/contracts/protocols/runtime/envelope_emitter.py
from typing import Protocol

class EnvelopeEmitter(Protocol):
    def emit_reducer_apply_start(self, *, method: str) -> None: ...
    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None: ...
    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...
    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...
    def emit_resume_end(self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str) -> None: ...
    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None: ...
    def emit_exception_caught(self, *, boundary: str, exc_type: str, message: str, trace_id: str) -> None: ...
    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None: ...
    def emit_agent_loop_iteration_start(self, *, role: str, kind: str, scope: str, trace_id: str) -> None: ...
    def emit_agent_loop_iteration_end(self, *, role: str, kind: str, scope: str, trace_id: str, outcome: str) -> None: ...
    def emit_event_publisher_publish(self, *, event_kind: str, outcome: str) -> None: ...
```

### 2.2 默认实现(放在 `lca/infrastructure/observability/`)

不放在 plugin tree:`infrastructure` 比 plugin 低,与 spine reflector 是 "binding" 关系,不会让 plugin 反过来 import L1/L2。

### 2.3 Migration

每个调用方:
1. 删除 `from lca.plugins.observability.spine.reflectors.{runtime,agent_spawn} import (...)`
2. 替换为 `self._bindings.envelope.emit_*(...)`

## 3. 删除条件

- 所有 8 处 inline import 移除: `grep -rn "from lca.plugins.observability.spine.reflectors" lca/runtime/ lca/agent/ | wc -l` 必须为 0。
- `tests/runtime/test_envelope_emitter_binding.py` 100% 覆盖 11 个 emit 方法。
- 既有 runtime/agent 测试 0 regression。

## 4. 风险

- **风险 1**:`SpineEnvelopeEmitter` 的 lazy import 在无 spine 环境下不应抛 ImportError。Mitigation:测试用 monkeypatch 模拟缺 spine 路径。
- **风险 2**:`DeclarativeRuntimeBindings` 当前是 `frozen=True`;新增字段需要 dataclass 默认值。Mitigation:Protocol 字段设默认 `None`,`__post_init__` 注入默认 `SpineEnvelopeEmitter`。
- **风险 3**:AGENTS.md §1 提到 "插件不得自行读取 `os.environ`",本 ADR 不增加任何凭证读取。

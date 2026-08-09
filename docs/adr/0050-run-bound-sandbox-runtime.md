# ADR-0050: Run-Bound Sandbox Runtime — 单一执行平面 + Inspect/Execute 分离

## 状态

Accepted

## 背景

ADR-0044 / 0046 确立 Onlyboxes + `/mnt/data` 挂载契约，但实现演化出现：

1. **双轨执行**：无状态 Onlyboxes HTTP vs 旁路 Docker CLI 会话，挂载语义不一致；
2. **Tool 管 session**：``SandboxCodeTool`` 内 ContextVar 持有会话，与 ``RunScope`` 脱节；
3. **挂载一次**：会话创建后不再 sync 新附件；
4. **非结构化错误**：Agent 看到 ``sandbox execution failed`` + 裸 traceback，误归因基础设施；
5. **Agent 兼运维**：探路、NaN 防御、路径猜测均由 LLM 生成代码承担。

业界范式（OpenAI Code Interpreter、E2B、Jupyter kernel）：**Run 级持久环境 + 声明式挂载 + Inspect/Execute 分离 + 结构化结果**。

## 决定

### 一、RunBoundSandboxRuntime（L0）

- 一个 agent run → 一个 ``RunBoundSandboxRuntime``，在 ``execute_run`` 入口 ``bind``，``finalize_run`` 销毁；
- 工具（``sandbox_inspect`` / ``sandbox_execute`` / ``run_sandbox_code``）**只委托 runtime**，不持有 session；
- Registry：``runtime_scope.py``（``bind`` / ``get`` / ``unbind``），与 ``run_finalizer`` 集成。

### 二、单一 Onlyboxes 执行平面

- **退役** ``docker_session.py`` 旁路；
- 会话：``Onlyboxes /api/v1/sessions``（``onlyboxes_session.py``）；
- 降级：无 session 时无状态 ``pythonExec`` + 每次 exec **幂等 re-mount**（``build_wrapped_code`` / ``build_session_wrapped_code``）；
- 会话 exec 使用 ``build_session_wrapped_code``：挂载 + pickle 状态 + 产出 harvest。

### 三、挂载 Manifest + Hard Fail

- ``MountManifest`` / ``MountEntry`` 写入 ``SandboxExecResult``；
- run 有附件 → ``ensure_ready`` 校验 guest 路径，缺失则 ``error_kind=mount``，Gateway **fail-fast**；
- 每次 ``execute`` 携带当前 ``mount_files``（sync 新附件）。

### 四、工具面

| 工具 | 职责 |
|---|---|
| ``sandbox_inspect`` | 结构化 profile（files、sheets、columns、nan_rows） |
| ``sandbox_execute`` | 在已就绪环境执行 Python |
| ``run_sandbox_code`` | ``sandbox_execute`` 兼容别名 |

``ensure_ready`` 自动 inspect；结果缓存在 runtime，注入 observation ``inspect_profile``。

### 五、结构化 Observation

- ``SandboxExecResult``：``error_kind`` / ``error_summary`` / ``suggested_fix`` / ``partial`` / ``failed_at_line``；
- ``error_parse.py`` 规则解析常见失败（FileNotFound、NaN TypeError、KeyError）；
- ``sandbox_exec_observation.py`` 组装 ``Observation.payload``。

### 六、contracts 扩展

``lca/contracts/models/core/sandbox.py``：

- ``SandboxErrorKind``
- ``MountEntry`` / ``MountManifest``
- ``SandboxExecResult``

## 后果

- 正向：Agent 不再猜路径；挂载失败在 run 入口暴露；错误可行动；与 E2B/Code Interpreter 范式对齐。
- 负向：Onlyboxes 需支持 ``/api/v1/sessions``；否则降级无状态（变量不跨调用持久，除非 pickle 路径生效）。
- 测试：``tests/support/inline_sandbox.py`` VFS；``test_sandbox_runtime.py`` 生命周期。

## 关联

- ADR-0044 代码沙箱适配器
- ADR-0046 文件往返契约
- ADR-0048 操作技能库（skill 挂载走同一 runtime）

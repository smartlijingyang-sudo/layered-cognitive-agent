# 代码库深度架构加深与接缝收敛设计规范 (Codebase Architecture Deepening Design)

**日期**：2026-10-05  
**自治等级**：`DRAFT` (AP-05)  
**触发来源**：`improve-codebase-architecture` 架构扫描与四阶段深度演进  
**状态**：已批准 (Approved)

---

## 1. 架构背景与第一性原理

在智能体认知与传输系统持续演化过程中，部分子系统出现了浅层模块过度拆分（Shallow Modules）、虚设协议接缝（Hypothetical Seams）、缺乏就地理解性（Locality 失效）以及多租户检索遍历泄露的问题。

本项目基于 John Ousterhout *A Philosophy of Software Design* 的核心架构词汇与 LCA 架构守则：
1. **Module & Depth**：接口应远比实现简单（Deep Module）；反对每个只有数十行代码的函数或单一微类独占一个子目录与文件的浅模块碎裂现象。
2. **Deletion Test**：对疑似浅层的微模块实施删除测试——若删除它能将复杂度集中在清晰的协同者内部而非散落各处，则坚决收敛。
3. **Seam & Adapter 原则**：*“One adapter = hypothetical seam, two = real”*。全仓仅单一实现的 Protocol 为过度设计的虚设接缝，应直接对接真实实现。
4. **Locality & Leverage**：将强关联的状态转移与安全防护不变量就地收缩；对外提供高杠杆接口，隐藏物理存储与协调细节。

---

## 2. 严格职责与所有权边界 (Owns vs. Does NOT own, AP-01)

### 2.1 本方案拥有 (Owns)
1. **Phase 1 (Transport)**：收拢 `lca/plugins/transport/webserver/handlers/runs/terminal/` 下分散的 `outcome/`、`status/`、`failure/`、`terminalizer/` 浅层微目录，在 `lifecycle.py` 中建立高内聚的 `RunTerminalCoordinator` 深度类；同步更新调用方与测试。
2. **Phase 2 (Assistant Tools)**：在 `lca/infrastructure/tools/assistant/self_manage_tools.py` 的基类 `_BaseAssistantTool` 中建立模板方法执行接缝，基于 `is_mutating` 属性统一拦截外部指令源写操作，从 9 个子类中彻底切除手写重复校验代码。
3. **Phase 3 (Cron Store)**：加深 `lca/domain/cron/store.py` 中的 `MultiAssistantCronStore`，引入内部 `job_id → assistant_id` 内存索引与缓存，将底层磁盘目录遍历彻底封装在存储内部，消除 $O(N)$ 磁盘扫描。
4. **Phase 4 (ContextFiles)**：切除 `lca/infrastructure/memory/contextfiles/ports/file_store.py` 虚设协议及单一 `adapters/disk.py`，复用标准存储；将细碎的 `domain/diff.py`、`domain/edit.py` 与 `service/memory_edit_sync.py` 收敛为深度上下文文件同步模块 `contextfiles/sync.py`。

### 2.2 本方案严禁触碰 (Does NOT own)
1. **严禁修改认知图声明与拓扑**：禁止变动 `bundles/*.yaml` 或触碰 `lca/nodes/` 认知图节点的注册语义与五相闭集事件（C1, C11, C14）。
2. **严禁修改公共数据 Contracts**：不改动 `lca/contracts/models/` 已冻结的公共 Protocol 与 DTO 字段（如 `Decision`, `CommandEnvelope`, `EffectReceipt`）。
3. **严禁留存跨 PR 兼容垫片**：严禁编写没有明确删除时机的 forwarding shims 或留下未清理的死 import（LCA COMPAT 铁律）。
4. **严禁跨子系统混合提交**：每个 Phase 必须是自闭环的原子提交，包含源码、调用方更新与全绿的单测。
5. **严禁提交宿主机/外部资产**：所有改动严格限定在 LCA 代码仓本身。

---

## 3. 四阶段深度架构设计

```mermaid
flowchart TD
    subgraph P1["Phase 1: Transport 终态生命周期加深"]
        direction LR
        O["outcome.py<br>(46 lines)"] & S["status.py<br>(64 lines)"] & F["failure.py<br>(82 lines)"] & T["terminalizer.py<br>(132 lines)"]
        -->|合并收敛| LC["RunTerminalCoordinator<br>(terminal/lifecycle.py)"]
        LC -->|单一深度 Seam| Carrier["Carrier Run Coordinator"]
    end

    subgraph P2["Phase 2: Assistant Tools 权限 Seam 拦截"]
        direction LR
        Base["_BaseAssistantTool.execute()<br>自动拦截 is_mutating"] --> Sub["9 个派生类<br>实现 execute_tool()"]
        Base -.->|删除各子类中冗余代码| Strip["切除 9 处手写 _check_standing_write_permitted"]
    end

    subgraph P3["Phase 3: Cron 存储多租户索引与 Seam 封装"]
        direction LR
        Multi["MultiAssistantCronStore"] -->|引入 O(1) 内存索引| Index["_job_to_assistant: dict"]
        Index -->|快速分发| Single["Target Assistant CronStore"]
        Multi -.->|消解| Scan["消除无索引磁盘线性多目录扫描"]
    end

    subgraph P4["Phase 4: ContextFiles 虚设 Seam 与微分层治理"]
        direction LR
        Hypo["ports/file_store.py<br>(虚设单一实现 Protocol)"] -->|替换为| Real["lca.infrastructure.file.store.FileStore"]
        Diff["domain/diff.py"] & Edit["domain/edit.py"] & SyncSvc["service/memory_edit_sync.py"] -->|收拢| SyncMod["contextfiles/sync.py"]
    end
```

### 3.1 Phase 1：Transport 终态生命周期加深（Webserver）
* **收敛前结构**：
  * `handlers/runs/terminal/outcome/outcome.py` (46 行): `RunOutcomeApplier`
  * `handlers/runs/terminal/status/status.py` (64 行): `derive_terminal_status`
  * `handlers/runs/terminal/failure/failure.py` (82 行): `record_run_failure`
  * `handlers/runs/terminal/terminalizer/terminalizer.py` (132 行): `RunTerminalizer`
* **收敛后设计**：
  * 在 `lca/plugins/transport/webserver/handlers/runs/terminal/lifecycle.py` 中建立 `RunTerminalCoordinator`。
  * 提供对外高内聚生命周期接缝：
    ```python
    class RunTerminalCoordinator:
        def apply_outcome(self, session: RunSession, outcome: DriverOutcome) -> bool: ...
        def derive_terminal_status(self, session: RunSession, success: bool) -> RunLifecycleStatus: ...
        def record_failure(self, session: RunSession, error: Any) -> None: ...
        async def terminalize(self, session: RunSession, *, success: bool) -> None: ...
    ```
  * 同步清理上述 4 个空 `__init__.py` 与冗余微目录，更新 `carrier/runs/lifecycle/lifecycle.py` 与 `terminal/registry/commands.py`。

### 3.2 Phase 2：Assistant Tools 基类统一拦截 Seam
* **收敛前结构**：
  * `_BaseAssistantTool` 定义了 `_check_standing_write_permitted()`，但 9 个具有写副作用的子类各自在 `execute()` 手动调用该方法并做空值判定。
* **收敛后设计**：
  * 在基类引入模板方法与 `is_mutating` 声明：
    ```python
    class _BaseAssistantTool(Tool):
        is_mutating: bool = False

        async def execute(self, args: dict[str, Any]) -> Observation:
            start = time.monotonic()
            if self.is_mutating:
                refused = self._check_standing_write_permitted()
                if refused is not None:
                    return self._fail(start, refused)
            return await self.execute_tool(args, start)

        @abstractmethod
        async def execute_tool(self, args: dict[str, Any], start: float) -> Observation: ...
    ```
  * 9 个子工具声明 `is_mutating = True`，业务逻辑迁移至 `execute_tool()`，彻底去除子类手动防御代码。

### 3.3 Phase 3：Cron 存储多租户索引与 Seam 封装
* **收敛前结构**：
  * `MultiAssistantCronStore` 对 `get_job`, `record_handoff_runs`, `close_run_receipts` 等每一个操作都在没有索引的情况下轮询扫描所有助理目录。
* **收敛后设计**：
  * 引入 `_job_to_assistant: dict[str, str]` 内存映射。
  * 在初始化与 Job 增删改时维护索引；调用 `record_handoff_runs(job_id, ...)` 时直接获取目标助理的 `CronStore`，将 $O(N)$ 磁盘扫描收缩为 $O(1)$ 分发；若索引未命中则做兜底扫描并回填。

### 3.4 Phase 4：ContextFiles 虚设 Seam 与微分层收敛
* **收敛前结构**：
  * `ports/file_store.py` 声明 `FileStore` 协议，全仓仅 `adapters/disk.py` 一个实现。
  * 37 个微文件在 `domain/`、`service/` 间极度碎片化传递文本与差异。
* **收敛后设计**：
  * 剔除虚设协议，改用平台既有 `LocalFileStore` 或标准文件路径操作。
  * 将 `domain/diff.py`、`domain/edit.py`、`service/memory_edit_sync.py` 收敛为 `contextfiles/sync.py`，对外提供简洁的同步接口：`sync_memory_markdown(home, text, memory_system) -> CuratedProjectionReceipt`。

---

## 4. 测试不变量矩阵与实施验收 (AP-02)

| 不变量编号 | 归属阶段 | 核心验证断言 (Invariant Assertion) | 自动化测试落脚点 |
|---|---|---|---|
| **INV-ARCH-01** | Phase 1 (Transport) | `RunTerminalCoordinator.terminalize()` 必须严格执行一次终态闭环：根据 `success` 正确派生 `COMPLETED`/`ERROR` 状态、记录 `CloseReason`、写入失败轨迹（若失败）、发出终态载体观测事实，并调用清理回调。 | `tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py` |
| **INV-ARCH-02** | Phase 1 (Transport) | `apply_outcome()` 在驱动结果携带 `waiting_input=True` 时，必须原子更新会话为 `WAITING_INPUT`，缓存活跃快照与审批请求，且绝不提前终态化。 | `tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py` |
| **INV-ARCH-03** | Phase 2 (Tools) | 标记为 `is_mutating = True` 的全部 9 个助手工具，在外部指令源（`ContentOrigin.EXTERNAL`）的决策上下文下执行时，必须由基类 `_BaseAssistantTool.execute()` **强制拦截**并返回鉴权失败，业务方法 `execute_tool()` 绝不被调用。 | `tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py` |
| **INV-ARCH-04** | Phase 2 (Tools) | 只读工具（`ListAssistantSkillsTool`、`ReadAssistantSelfConfigTool` 等，`is_mutating = False`）在外部指令源上下文下可正常透传执行，不被基类误拦截。 | `tests/infrastructure/tools/test_assistant_tools_standing_writer_seam.py` |
| **INV-ARCH-05** | Phase 3 (Cron) | `MultiAssistantCronStore` 执行 `record_handoff_runs`、`close_run_receipts` 与 `get_job` 时，必须通过内部内存索引直接命中所属助理的存储实例，不引发全局全量磁盘目录遍历；并在重复关闭不同回执时确定性抛出 `CronRunConflictError`。 | `tests/domain/cron/test_multi_assistant_cron_store_indexing.py` |
| **INV-ARCH-06** | Phase 4 (ContextFiles) | 收拢后的 `contextfiles/sync.py` 在执行 Markdown 编辑同步时，能正确比对活跃记录并派生出正确的 ADD/SUPERSEDE/DELETE 原子指令，不再引用已删除的 `ports/file_store.py`。 | `tests/infrastructure/memory/test_contextfiles_unified_sync.py` |
| **INV-ARCH-07** | 架构卫生与门禁 | 全仓运行 `ruff check` 零报错、`ruff format --check` 全通、全仓无指向已删除旧微模块的死 import、严格遵守 Does NOT own 负向边界。 | `scripts/lca-ops check-imports` & Pre-push 门禁套件 |

---

## 5. 实施流水线与交接

本设计文档一经落盘，即转入 `writing-plans` 技能，按单流单任务原则制定实施计划 `docs/plans/2026-10-05-codebase-architecture-deepening-plan.md`，每个 Phase 严格遵循：
*TDD 编写不变量测试 → 源码实现/收敛合并 → 全量调用点修正 → 门禁与回归检验*。

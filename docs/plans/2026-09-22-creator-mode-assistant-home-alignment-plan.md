# Creator Mode Assistant Home Alignment & Closed-Loop Execution Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底打通 Agent 私有自治域（Assistant Home）的插件与预置创造模式，实现动态自感知、同会话零重启即时执行、跨会话自加载、跨 Agent 共享复用与全链路易调试可观测性。

**Architecture:** 基于 DDD 分层与端口适配器模式，建立 `PresetPackage` 聚合根与 `FileSystemPresetRepository`；通过 `DynamicToolBridge` 监听 `cordis_control.promote` 并即时穿透注册至 `ToolsService` 与 `SafeExecutor` 白名单；通过 `AssistantPresetDiscovery` 建立会话启动期双层自动装配与感知链；通过 `PresetPromotionService` 实现资产的三级演化（私有 -> 共享 -> 平台）。

**Tech Stack:** Python 3.12, Cordis, Pydantic v2, pytest, structlog, LCA Observability & Journal Engine.

---

### Task 1: 修复既有历史测试 Import 路径断裂 (P0 基线恢复)

**Files:**
- Modify: `tests/scenario/cordis/test_cordis_creator_audit_log.py:38-44`
- Modify: `tests/scenario/cordis/test_cordis_creator_e2e.py:14-20`
- Modify: `tests/scenario/cordis/test_cordis_creator_preset_reuse.py:36-42`
- Modify: `tests/scenario/cordis/test_cordis_creator_real_scenario.py:55-61`
- Test: `tests/scenario/cordis/`
- Does NOT own: `lca/contracts/`, `lca/infrastructure/`, `lca/domain/`, AP-01
- Invariants to test: 修正后既有 30 个测试全部正常 collected 且无 `ModuleNotFoundError`

**Step 1: 编写或确认当前报错现场**
运行: `/opt/lca/venv/bin/pytest tests/scenario/cordis/ -k "test_four_faces"`
预期: FAIL with `ModuleNotFoundError: No module named 'lca.plugins.think.composition.composer_provider'`

**Step 2: 修正 import 路径**
将 4 个文件中：
```python
from lca.plugins.think.composition.composer_provider import (
    CordisComposer,
    build_default_invariant_checker,
)
```
替换为：
```python
from lca.plugins.composer.composition.cordis_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
```

**Step 3: 运行验证**
运行: `/opt/lca/venv/bin/pytest tests/scenario/cordis/ -v`
预期: 历史测试恢复通过（30/30 passed 或退出码 0）

**Step 4: Commit**
```bash
git add tests/scenario/cordis/
git commit -m "fix(tests): restore obsolete composer import paths in cordis scenario tests"
```

---

### Task 2: DDD 领域契约与文件仓储适配器 (PresetPackage & FileSystemPresetRepository)

**Files:**
- Create: `lca/contracts/models/preset/package.py`
- Create: `lca/contracts/protocols/preset/repository.py`
- Create: `lca/infrastructure/preset/fs_repository.py`
- Test: `tests/domain/preset/test_preset_repository.py`
- Does NOT own: `lca/infrastructure/sandbox/`, `lca/infrastructure/computer/`, AP-01
- Invariants to test: `PresetPackage` 序列化与文件落盘幂等性、`PresetScope` 路径解析隔离不穿越（INV-AP01）

**Step 1: 编写测试**
在 `tests/domain/preset/test_preset_repository.py` 中测试：
1. `save_package`: 保存私有预置到 `{assistant_home}/presets/<preset_id>/`，落盘 `bundle.yaml` 与 `plugins/<name>.py`；
2. `find_by_id`: 从目录成功反序列化 `PresetPackage`；
3. `list_presets`: 列出指定 Assistant 目录与共享目录下的所有合法预置；
4. `path_traversal_prevention`: 验证包含 `..` 或非法字符的 `preset_id` 被拒绝抛出 `ValueError`。

**Step 2: 运行测试验证失败**
运行: `/opt/lca/venv/bin/pytest tests/domain/preset/test_preset_repository.py -v`
预期: FAIL with `ModuleNotFoundError: No module named 'lca.contracts.models.preset'`

**Step 3: 实现最小领域模型与仓储**
- 在 `package.py` 中实现 `PresetScope` (`PRIVATE`, `SHARED`, `PLATFORM`)、`AuthoredPlugin` 与 `PresetPackage`；
- 在 `repository.py` 中定义 `PresetRepositoryProtocol`；
- 在 `fs_repository.py` 中实现 `FileSystemPresetRepository`，支持路径安全解析与原子写入。

**Step 4: 运行测试验证通过**
运行: `/opt/lca/venv/bin/pytest tests/domain/preset/test_preset_repository.py -v`
预期: 4/4 passed

**Step 5: Commit**
```bash
git add lca/contracts/models/preset/ lca/contracts/protocols/preset/ lca/infrastructure/preset/ tests/domain/preset/
git commit -m "feat(preset): implement DDD preset domain models and file system repository"
```

---

### Task 3: 动态工具桥接器与执行面 Seam (DynamicToolBridge & cordis_control 穿透)

**Files:**
- Create: `lca/infrastructure/tools/dynamic/bridge.py`
- Modify: `lca/plugins/tools/cordis_control/tool.py:112-140`
- Modify: `lca/plugins/tools/cordis_control/__init__.py:42-70`
- Modify: `lca/plugins/tools/cordis_control/creator_promotion.py:85-120`
- Test: `tests/infrastructure/tools/dynamic/test_dynamic_tool_bridge.py`
- Does NOT own: `lca/infrastructure/session/`, `Session.append`, AP-01
- Invariants to test: 动态挂载工具成功注入 `ToolsService` 且动态同步 `SafeExecutor` 白名单（INV-C5/即时生效）

**Step 1: 编写测试**
在 `tests/infrastructure/tools/dynamic/test_dynamic_tool_bridge.py` 中测试：
1. `DynamicPluginToolAdapter`: 将 Python Callable 包装为 `Tool`，正确提取参数 schema 与执行；
2. `DynamicToolBridge.register_and_allow`: 注册新工具至 `ToolsService` 并将工具名并入 `SafeExecutor.permission_manifest.allowed_tools`；
3. `cordis_control.promote` 触发时，自动调用已配置的 bridge 并发射 `DynamicToolBridged` Typed JournalEvent。

**Step 2: 运行测试验证失败**
运行: `/opt/lca/venv/bin/pytest tests/infrastructure/tools/dynamic/test_dynamic_tool_bridge.py -v`
预期: FAIL with `ModuleNotFoundError: No module named 'lca.infrastructure.tools.dynamic.bridge'`

**Step 3: 实现 DynamicToolBridge 与连接**
- 在 `bridge.py` 中落地 `DynamicPluginToolAdapter` 与 `DynamicToolBridge`；
- 在 `cordis_control/__init__.py` 与 `tool.py` 中支持接收可选的 `bridge: DynamicToolBridge`，在 `_publish_release` 与 `on_mounted` 时触发桥接，并使用 `FileSystemPresetRepository` 落盘至 Assistant 自治域。

**Step 4: 运行测试验证通过**
运行: `/opt/lca/venv/bin/pytest tests/infrastructure/tools/dynamic/test_dynamic_tool_bridge.py -v`
预期: 3/3 passed

**Step 5: Commit**
```bash
git add lca/infrastructure/tools/dynamic/ lca/plugins/tools/cordis_control/ tests/infrastructure/tools/dynamic/
git commit -m "feat(creator): implement DynamicToolBridge for same-session tool execution"
```

---

### Task 4: Assistant 自治预置发现装载与感知注入 (AssistantPresetDiscovery)

**Files:**
- Create: `lca/infrastructure/preset/discovery.py`
- Modify: `lca/plugins/transport/webserver/carrier/runs/lifecycle/runnable_assembly.py:45-80`
- Modify: `lca/plugins/collaboration/modes/cordis_creator.py:64-93`
- Modify: `lca/plugins/prompts/sections.py:60-90`
- Test: `tests/infrastructure/preset/test_preset_discovery.py`
- Does NOT own: `lca/plugins/transport/wechat/`, `lobehub-ui/`, AP-01
- Invariants to test: 损坏预置隔离容错（INV-RESILIENCE）、多源预置装载与 Prompt 零幻觉感知（INV-C3）

**Step 1: 编写测试**
在 `tests/infrastructure/preset/test_preset_discovery.py` 中测试：
1. `discover_assistant_presets`: 扫描 `{assistant_home}/presets/` 与 `plugins/`，成功加载健康预置；
2. `broken_preset_quarantine`: 注入语法错误的插件，验证被标记为 `BROKEN` 并记录 Journal 告警，其余健康项照常加载；
3. `prompt_section_injection`: 验证 Prompt Section 自动生成 `Autonomous Presets & Custom Tools` 概览描述。

**Step 2: 运行测试验证失败**
运行: `/opt/lca/venv/bin/pytest tests/infrastructure/preset/test_preset_discovery.py -v`
预期: FAIL with `ModuleNotFoundError: No module named 'lca.infrastructure.preset.discovery'`

**Step 3: 实现 Discovery 与装配接入**
- 在 `discovery.py` 中实现 `AssistantPresetDiscovery`；
- 在 `runnable_assembly.py` 与 `cordis_creator.py` 中挂载 discovery，将 Assistant 专属预置动态合入 `request.tools`；
- 在 `sections.py` 中增加对动态预置清单的结构化渲染。

**Step 4: 运行测试验证通过**
运行: `/opt/lca/venv/bin/pytest tests/infrastructure/preset/test_preset_discovery.py -v`
预期: 3/3 passed

**Step 5: Commit**
```bash
git add lca/infrastructure/preset/discovery.py lca/plugins/transport/ lca/plugins/collaboration/ lca/plugins/prompts/ tests/infrastructure/preset/
git commit -m "feat(preset): implement AssistantPresetDiscovery and prompt perception injection"
```

---

### Task 5: 跨 Agent 共享与平台提升服务 (PresetPromotionService)

**Files:**
- Create: `lca/application/preset/promotion.py`
- Test: `tests/application/preset/test_preset_promotion.py`
- Does NOT own: `contracts/`, AP-01
- Invariants to test: 跨 Agent 共享元数据不可变性、平台 Bundle 编译规范性（INV-AP01）

**Step 1: 编写测试**
在 `tests/application/preset/test_preset_promotion.py` 中测试：
1. `promote_to_shared`: 将 `{assistant_home}/presets/<id>` 发布到 `~/.lca/shared/presets/<id>`，校验 `metadata.json` 包含作者与校验和；
2. `export_to_platform`: 将预置编译为平台 Bundle YAML 格式，可直接被外部加载；
3. 验证发射 `PresetShared` 与 `PresetExported` 事件。

**Step 2: 运行测试验证失败**
运行: `/opt/lca/venv/bin/pytest tests/application/preset/test_preset_promotion.py -v`
预期: FAIL with `ModuleNotFoundError: No module named 'lca.application.preset.promotion'`

**Step 3: 实现 PresetPromotionService**
- 落地 `PresetPromotionService`，实现基于 SHA256 校验和的跨目录安全复制与平台导出逻辑。

**Step 4: 运行测试验证通过**
运行: `/opt/lca/venv/bin/pytest tests/application/preset/test_preset_promotion.py -v`
预期: 3/3 passed

**Step 5: Commit**
```bash
git add lca/application/preset/ tests/application/preset/
git commit -m "feat(preset): implement PresetPromotionService for sharing and platform export"
```

---

### Task 6: 五大端到端闭环场景测试与回归门禁 (Comprehensive E2E Closed-Loop Suite)

**Files:**
- Create: `tests/scenario/cordis/test_cordis_creator_assistant_closed_loop.py`
- Test: `tests/scenario/cordis/`
- Does NOT own: 外层任何业务代码（纯测试与架构验证）
- Invariants to test: INV-C3, INV-C4, INV-C5, INV-RESILIENCE, INV-AP01

**Step 1: 编写 5 大场景闭环测试**
在 `test_cordis_creator_assistant_closed_loop.py` 中串联实现：
1. `test_scenario_1_data_engineering_preset_creation`: Agent 在私有目录自主创建并落盘漏斗分析预置；
2. `test_scenario_2_same_session_zero_restart_trigger`: 同一会话紧接着直接调用新工具并得到正确分析结果；
3. `test_scenario_3_cross_session_perception_and_replay`: 销毁内存新启 Session，0 控制调用直接感知并执行；
4. `test_scenario_4_cross_agent_sharing_and_inheritance`: Agent A 提升至共享域，Agent B 成功挂载并复用；
5. `test_scenario_5_hot_upgrade_and_safe_rollback`: 动态热升级与故障安全回滚。

**Step 2: 运行端到端测试**
运行: `/opt/lca/venv/bin/pytest tests/scenario/cordis/test_cordis_creator_assistant_closed_loop.py -v`
预期: 5/5 passed

**Step 3: 全套门禁与回归检验**
运行:
1. `/opt/lca/venv/bin/pytest tests/scenario/cordis/ -v` (全部历史与新用例全绿)
2. `ruff check lca/ tests/` (0 报错)
3. `git diff --check` (干净无告警)

**Step 4: Commit**
```bash
git add tests/scenario/cordis/test_cordis_creator_assistant_closed_loop.py
git commit -m "test(creator): add 5 rich E2E closed-loop scenario tests for creator mode"
```

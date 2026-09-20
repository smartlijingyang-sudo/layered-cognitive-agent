# Assistant Evolution Flow Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 为助理演化闭环（创建助理 → 自我感知 → 对话修改 USER 画像并自动回填 → 自主创建并安装 Skill → 激活并使用该 Skill 解决问题）构建确定性集成回归测试与真实模型端到端测试套件。

**Architecture:** 采用分层联动双模套件：`tests/integration/test_assistant_evolution_flow.py` 基于真实 `AssistantCatalog`、`PerceiveObserveExecutor`、`AssistantMemory`、`ProfileBackfillService` 及 `AssistantSkillOverlay`，在零外部依赖与零网络开销下验证全流程契约；`tests/e2e/test_assistant_evolution_flow_live.py` 连接本地运行的 `http://127.0.0.1:8765` 内核，驱动真实模型多轮会话并断言文件系统变化与工具执行闭环。

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, LCA Assistant Catalog & Overlay (ADR-0187/ADR-0242), Memory Knowledge Layer & Backfill (ADR-0246/ADR-0247), urllib.request.

---

### Task 1: 编写确定性集成回归测试套件

**Files:**
- Create: `tests/integration/test_assistant_evolution_flow.py`

**Step 1: 编写多轮状态转移测试逻辑**
- Turn 0: 实例化真实 `AssistantCatalogImpl` 并调用 `create_assistant`，断言初始目录与默认 `USER.md`；
- Turn 1: 构造真实 `PerceiveObserveExecutor` 并注入 `assistant_bootstrap`，断言投影出的 `ContextManifest` 携带 `SOUL.md`、`USER.md`、`AGENTS.md`；
- Turn 2: 组装带 `ProfileBackfillService` 的 `AssistantMemory`，写入 `identity` 与 `preference` 记录，断言自动触发 `USER.md` 回填且物理文件包含结构化内容；
- Turn 3: 再次执行感知投影，断言输出的 `USER.md` 包含新回填的架构师身份与偏好；
- Turn 4: 组装 `AssistantCreateSkillTool` 与真实 `AssistantSkillOverlayImpl`，传入合法的 `code-review-helper` 的 `skill_md`，断言通过 0067 三闸并落盘至 `{home}/skills/code-review-helper/SKILL.md`，manifest 为 `verified`；
- Turn 5: 调用 `overlay.activate` 激活该技能并断言获取到包含审查 SOP 的内容。

**Step 2: 运行测试并验证通过**
- 命令: `pytest tests/integration/test_assistant_evolution_flow.py -v`
- 预期: 6 个断言阶段全部通过（100% 确定性，< 2 秒）。

**Step 3: 提交代码**
- 命令: `git add tests/integration/test_assistant_evolution_flow.py && git commit -m "test(integration): add assistant evolution deterministic flow test"`

---

### Task 2: 编写真实大模型端到端多轮测试套件

**Files:**
- Create: `tests/e2e/test_assistant_evolution_flow_live.py`

**Step 1: 编写带有 `@pytest.mark.real_llm` 的 5 轮 Live 测试**
- 接入点与跳过保护：`_has_llm_key()` 和 `_kernel_ready()`（`http://127.0.0.1:8765/health`）；
- Turn 0: `POST /v1/assistants` 创建新助理；
- Turn 1: 发起 run 询问“请介绍你自己与可用工具/技能”，断言 run 成功且助理准确自我感知；
- Turn 2: 发起 run 说明“我是系统架构师李超，技术栈 Python/Rust，偏好简洁代码优先”，等待 run 完成后断言磁盘 `{home}/USER.md` 物理出现用户画像；
- Turn 3: 发起 run 询问“你还记得我是谁以及偏好吗”，断言大模型回答中识别身份并遵循偏好；
- Turn 4: 发起 run 要求大模型通过 `create_assistant_skill` 安装 `code-review-helper` 技能，轮询等待 `manifest.json` 状态为 `verified`；
- Turn 5: 发起 run 要求大模型使用 `code-review-helper` 审查包含未关闭句柄的 Python 代码，断言模型调用 `activate_skill` 并按 SOP 指出文件句柄泄露风险并给出修复。
- 清理逻辑：测试结束或失败时，保留 run_id 便于调试，必要时清理临时 Home 目录。

**Step 2: 本地运行验证**
- 快速跳过验证: `pytest tests/e2e/test_assistant_evolution_flow_live.py -v`（默认不带 `-m real_llm`，应报告 1 skipped）；
- 真实内核运行: `pytest tests/e2e/test_assistant_evolution_flow_live.py -v -m real_llm -s`（在当前运行的内核与大模型下验证真实 5 轮闭环）。

**Step 3: 提交代码**
- 命令: `git add tests/e2e/test_assistant_evolution_flow_live.py && git commit -m "test(e2e): add assistant evolution multi-turn live test"`

---

### Task 3: 门禁检查、回归测试与收尾汇报

**Files:**
- Modify: `docs/plans/task.md`

**Step 1: 运行代码规范检查**
- 命令: `ruff check tests/integration/test_assistant_evolution_flow.py tests/e2e/test_assistant_evolution_flow_live.py`
- 命令: `ruff format --check tests/integration/test_assistant_evolution_flow.py tests/e2e/test_assistant_evolution_flow_live.py`

**Step 2: 运行集成回归**
- 命令: `pytest tests/integration/test_assistant_evolution_flow.py`

**Step 3: 更新任务清单与输出完整报告**
- 更新 `docs/plans/task.md` 状态与 Evidence，向用户汇总测试结果。

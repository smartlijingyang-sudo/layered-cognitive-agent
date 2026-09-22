# Agent 认知记忆闭环与多场景真实验证实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底闭环 LCA Agent 的长期记忆与三位一体感知能力（感知自己、感知环境、感知用户），打通门禁环境加载、情景记忆自省落盘、相关性检索算法与 Prompt 零冗余呈现，并落地 5 大场景确定性端到端回归套件。

**Architecture:** 基于领域驱动设计（DDD）与第一性原理，在 L1 基础设施层修复 `FallbackMemoryFilter` 凭证加载与本地词表，在 `AssistantMemory` 中闭环 `EPISODIC` 情景记忆写入与 `LayeredRetrievalPolicy` 多维相关性检索，在 L2 呈现层实现 `UserProfileSection` 与 `ContextSection` 互斥去重，并通过真实的端到端场景矩阵对行为不变量进行确定性守护。

**Tech Stack:** Python 3.12, Pytest, Pydantic, TypeSafe Jev Noul SDK, LayeredCognitiveAgent (LCA) Contracts/Infrastructure/Plugins.

---

### Task 1: 预过滤门禁韧性与环境加载（Pre-Filter Robustness & Dotenv Loading）

**Files:**
- Modify: `lca/infrastructure/memory/pre_filter/fallback_filter.py:1-40`
- Modify: `lca/infrastructure/memory/pre_filter/typesafe_filter.py:15-45`
- Modify: `lca/infrastructure/memory/pre_filter/tokens.py:1-42`
- Test: `tests/reflect/test_memory_pre_filter_enhanced.py`
- Does NOT own: `lca/nodes/`（图节点不修改）、`lca/contracts/`（契约接口保持不变，AP-01）
- Invariants to test: `INV-01 (自动加载 .env 并在有 key 时调用 TypeSafe)`、`INV-02 (偏好与环境无主句不被拦截)`

**Step 1: Write the failing test**

创建 `tests/reflect/test_memory_pre_filter_enhanced.py`：
```python
import pytest
from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter
from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter

@pytest.mark.asyncio
async def test_fallback_filter_loads_dotenv_and_detects_facts():
    filter_ = FallbackMemoryFilter()
    # 验证环境事实不被本地规则与门禁漏判
    for statement in [
        "生产数据库端口是 5433，只能读不能写",
        "记住：所有代码提交前必须执行 lint",
        "我不喜欢啰嗦，请直接给代码",
    ]:
        decision = await filter_.evaluate(statement)
        assert decision.should_extract is True, f"Failed on: {statement}"
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/reflect/test_memory_pre_filter_enhanced.py`
Expected: FAIL（因 `RegexMemoryFilter` 未命中词表或阈值偏高拦截）

**Step 3: Write minimal implementation**

1. 在 `fallback_filter.py` 中引入 `from lca.infrastructure.llm_adapter.factory.factory import load_dotenv_if_present`，并在 `__init__` 中调用 `load_dotenv_if_present()`；
2. 在 `typesafe_filter.py` 中将 `threshold` 默认值设为 `0.50`，更新提问指导词涵盖“系统约束或环境配置”；
3. 在 `tokens.py` 的 `DEFAULT_MEMORY_TOKENS` 中追加：“记住”、“别忘”、“环境”、“配置”、“生产”、“服务器”、“数据库”、“端口”、“约定”、“规范”。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/reflect/test_memory_pre_filter_enhanced.py`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/pre_filter/ tests/reflect/test_memory_pre_filter_enhanced.py
git commit -m "feat(memory): enhance pre-filter with dotenv loading and environmental tokens"
```

---

### Task 2: 情景记忆生成与自我感知闭环（Episodic Memory Generation）

**Files:**
- Modify: `lca/infrastructure/memory/assistant_memory.py:127-185`
- Test: `tests/plugins/assistant/test_assistant_episodic_memory.py`
- Does NOT own: `lca/session/`（Session 只读追加不改）、`lca/nodes/remember/`（不改变图节点端口，AP-01）
- Invariants to test: `INV-03 (工具调用后必须落盘 episodic.json 且容量受限 <= 50)`

**Step 1: Write the failing test**

创建 `tests/plugins/assistant/test_assistant_episodic_memory.py`：
```python
import pytest
from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.memory.assistant_memory import AssistantMemory

@pytest.mark.asyncio
async def test_assistant_memory_persists_episodic_on_tool_execution(tmp_path):
    mem = AssistantMemory(tmp_path / "asst")
    state = AgentState(trace_id="t1", task="执行代码检查", step=1, budget=Budget())
    obs = Observation(observation_id="o1", success=True, payload={"tool": "run_command", "output": "ok"})
    refl = Reflection(reflection_id="r1", verdict="on_track", extra={})
    
    await mem.update(state, obs, refl)
    
    episodic = mem.query(MemoryLayer.EPISODIC)
    assert len(episodic) == 1
    assert "执行代码检查" in episodic[0].content
    assert "run_command" in episodic[0].content
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/assistant/test_assistant_episodic_memory.py`
Expected: FAIL（因为此前 `update` 只写 `WORKING`，`episodic` 为 0）

**Step 3: Write minimal implementation**

在 `lca/infrastructure/memory/assistant_memory.py` 的 `update` 方法中：
- 识别工具执行证据（`observation.payload` 或 `state.step > 0` 且有工具迹象）；
- 生成一条 `MemoryLayer.EPISODIC` 记录落盘；
- 限制 `episodic.json` 保存最近 50 条事实（FIFO 淘汰）。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/assistant/test_assistant_episodic_memory.py`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/assistant_memory.py tests/plugins/assistant/test_assistant_episodic_memory.py
git commit -m "feat(memory): implement episodic memory persistence for self-awareness"
```

---

### Task 3: 接入多维相关性检索（Layered Relevance Retrieval Integration）

**Files:**
- Modify: `lca/infrastructure/memory/assistant_memory.py:100-126`
- Test: `tests/plugins/assistant/test_assistant_memory_relevance.py`
- Does NOT own: `lca/nodes/perceive/memory_retrieve/`（保持端口与调用参数不变，AP-01）
- Invariants to test: `INV-04 (检索结果按 relevance * recency * importance 降序排列)`

**Step 1: Write the failing test**

创建 `tests/plugins/assistant/test_assistant_memory_relevance.py`：
```python
import pytest
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory

@pytest.mark.asyncio
async def test_assistant_memory_retrieves_relevant_records_first(tmp_path):
    mem = AssistantMemory(tmp_path / "asst")
    mem.upsert(MemoryRecord(record_id="m1", content="系统使用 Python 3.12", memory_type=MemoryLayer.SEMANTIC, importance=0.8, category=MemoryCategory.FACT))
    mem.upsert(MemoryRecord(record_id="m2", content="Redis 集群端口为 6379", memory_type=MemoryLayer.SEMANTIC, importance=0.8, category=MemoryCategory.FACT))
    
    # 搜索 Redis，相关项必须排在第一位
    results = await mem.retrieve(None, query="Redis 缓存配置", token_budget=1000)
    assert len(results) >= 1
    assert "Redis" in results[0].content
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/assistant/test_assistant_memory_relevance.py`
Expected: FAIL（因为旧实现做 `del manifest, query`，按文件顺序返回 `Python` 在首位）

**Step 3: Write minimal implementation**

在 `AssistantMemory.retrieve` 中接入 `LayeredRetrievalPolicy` 或实现其加权评分机制：
- 对 `SEMANTIC`、`EPISODIC` 记录计算 `relevance(query, content) * recency * importance`；
- 按得分降序排序；
- 依 `token_budget` 截断返回。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/assistant/test_assistant_memory_relevance.py`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/assistant_memory.py tests/plugins/assistant/test_assistant_memory_relevance.py
git commit -m "feat(memory): integrate layered relevance retrieval into AssistantMemory"
```

---

### Task 4: Prompt 呈现去重与纯净化（Prompt Clean Presentation & Deduplication）

**Files:**
- Modify: `lca/plugins/prompts/sections.py:295-353`
- Modify: `lca/cognition/brain/sections/types.py:154-186`
- Test: `tests/plugins/prompts/test_prompt_memory_deduplication.py`
- Test: `tests/plugins/prompts/test_home_memory_sections.py` (修复旧测试中 sections 结尾断言)
- Does NOT own: `lca/plugins/prompts/assembler.py`（Prompt 组装器主流程不改，AP-01）
- Invariants to test: `INV-05 (ContextSection 与 UserProfileSection 零行交叉)`

**Step 1: Write the failing test**

创建 `tests/plugins/prompts/test_prompt_memory_deduplication.py`：
```python
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.team.role.team import RoleProfile
from lca.plugins.prompts.sections import ContextSection, UserProfileSection

def test_user_profile_and_context_do_not_duplicate_identity_preference():
    rec_id = MemoryRecord(record_id="1", content="用户身份：总架构师", memory_type=MemoryLayer.SEMANTIC, importance=1.0, category=MemoryCategory.IDENTITY)
    rec_pref = MemoryRecord(record_id="2", content="偏好：只看代码", memory_type=MemoryLayer.SEMANTIC, importance=1.0, category=MemoryCategory.PREFERENCE)
    rec_fact = MemoryRecord(record_id="3", content="数据库端口：5433", memory_type=MemoryLayer.SEMANTIC, importance=1.0, category=MemoryCategory.FACT)
    
    manifest = ContextManifest(items=(ContextItem(kind="memory", payload=[rec_id, rec_pref, rec_fact], provenance="test"),))
    role_profile = RoleProfile(role="assistant", goal="help", backstory="")
    
    profile_out = UserProfileSection().render(role_profile=role_profile, task="", awareness=None, manifest=manifest, tools=(), activated_skills=())
    context_out = ContextSection().render(role_profile=role_profile, task="", awareness=None, manifest=manifest, tools=(), activated_skills=())
    
    assert "总架构师" in profile_out.text
    assert "只看代码" in profile_out.text
    assert "总架构师" not in context_out.text  # 必须排除
    assert "只看代码" not in context_out.text  # 必须排除
    assert "数据库端口：5433" in context_out.text  # FACT 正常渲染
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/prompts/test_prompt_memory_deduplication.py`
Expected: FAIL（因 `ContextSection` 包含了 `[identity] 用户身份：总架构师`）

**Step 3: Write minimal implementation**

1. 在 `lca/cognition/brain/sections/types.py` 的 `render_context_lines` 中，过滤掉 `category in (IDENTITY, PREFERENCE)` 的语义条目；
2. 修复 `tests/plugins/prompts/test_home_memory_sections.py` 中因新增 `autonomous_presets` 导致的 `names[-1] == "home"` 断言，改为 `assert "home" in names`。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/plugins/prompts/test_prompt_memory_deduplication.py tests/plugins/prompts/test_home_memory_sections.py`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/prompts/ lca/cognition/brain/ tests/plugins/prompts/
git commit -m "fix(prompts): eliminate duplicate memory lines and clean section presentation"
```

---

### Task 5: 5 大多场景端到端闭环验证（Multi-Scenario E2E Closed-Loop Suite）

**Files:**
- Create: `tests/scenario/memory/test_memory_closed_loop_scenarios.py`
- Does NOT own: 业务核心代码（本 Task 为纯测试集成验证，AP-01）
- Invariants to test: `INV-01 ~ INV-06 (全部 6 大不变量)`

**Step 1: Write the comprehensive scenario test file**

覆盖场景 1 至 场景 5：
- `test_scenario_1_user_profile_evolution_and_supersede`
- `test_scenario_2_environmental_facts_and_constraints`
- `test_scenario_3_self_awareness_and_episodic_memory`
- `test_scenario_4_relevance_retrieval_and_budget_pruning`
- `test_scenario_5_governed_tools_and_sensitive_delete_guard`

**Step 2: Run test suite**

Run: `/opt/lca/venv/bin/pytest -o addopts="" tests/scenario/memory/test_memory_closed_loop_scenarios.py -v`
Expected: ALL 5 SCENARIOS PASS

**Step 3: Commit**

```bash
git add tests/scenario/memory/test_memory_closed_loop_scenarios.py
git commit -m "test(memory): add 5 comprehensive E2E scenario tests for memory closed loop"
```

---

### Task 6: 全链路回归、代码门禁与架构守卫验证（Full Regression & Gate Verification）

**Files:**
- Does NOT modify code.
- Verification command set:
  1. `/opt/lca/venv/bin/pytest -o addopts="" tests/assistant/test_memory* tests/reflect/test_memory* tests/plugins/assistant/test_*memory* tests/scenario/memory/`
  2. `ruff check lca/ tests/`
  3. `git diff --check`
- Invariants to verify: 负向边界（Does NOT own）零破坏，代码门禁 0 报错。

**Step 1: Execute verification commands**
**Step 2: Verify zero regression across repo**
**Step 3: Commit and update task.md**

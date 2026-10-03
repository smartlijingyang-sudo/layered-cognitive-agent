# 认知记忆与持续演化架构落地实施计划 (Cognitive Memory & Evolution Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于人类认知双系统理论与开放实体知识图谱，落地极简冷启动（<500 Token）、渐进式分层召回、纯净 Markdown File-as-SSOT、工具避坑哨兵与自主技能演化底座，并跑通 7 大维度 28 项认知基准测试。

**Architecture:** 采用 DDD 分层架构。Contracts 层冻结不可变四层认知实体（Frozen Pydantic/Dataclass）；Infrastructure 层实现 File-as-SSOT 读写、遥测伴生库与 SQLite FTS5+Graph 派生索引；Cognition 层实现双系统渐进调度、模态摄入门控、表达分寸防火墙与工具避坑哨兵；Nodes/Plugins 接入主认知循环。

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (FTS5 + Recursive CTE), Pytest.

---

### Task 1: 契约层与四层认知记忆领域模型 (Contracts)

**Files:**
- Create: `lca/contracts/models/memory/cognitive.py`
- Create: `lca/contracts/protocols/memory/cognitive.py`
- Test: `tests/contracts/test_cognitive_memory_contracts.py`
- Does NOT own: 基础设施持久化、图节点拓扑、Session 事件底层 (AP-01)
- Invariants to test: 模型不可变（`frozen=True, extra="forbid"`）、Zep 双时间线校验、`dedupe_key` 格式校验 (AP-02)

**Step 1: Write the failing test**

```python
# tests/contracts/test_cognitive_memory_contracts.py
import pytest
from datetime import datetime, UTC
from pydantic import ValidationError
from lca.contracts.models.memory.cognitive import (
    SemanticClaim,
    EpisodicTrace,
    WorkingMemoryPercept,
)

def test_semantic_claim_immutability_and_double_timeline():
    claim = SemanticClaim(
        claim_id="claim_01",
        category="preference",
        dedupe_key="preference:tech_stack",
        statement="全栈使用 Rust 与 Go",
        confidence=1.0,
        sources=("trace_01",),
        valid_from=datetime.now(UTC),
    )
    with pytest.raises(ValidationError):
        claim.confidence = 0.5  # immutable
    assert claim.valid_to is None
    assert claim.sensitivity == "normal"
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/contracts/test_cognitive_memory_contracts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.contracts.models.memory.cognitive'`

**Step 3: Write minimal implementation**
创建 `lca/contracts/models/memory/cognitive.py` 定义 `SemanticClaim`, `EpisodicTrace`, `WorkingMemoryPercept`, `ProceduralSkill` 及枚举。

**Step 4: Run test to verify it passes**
Run: `pytest tests/contracts/test_cognitive_memory_contracts.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/contracts/models/memory/cognitive.py tests/contracts/test_cognitive_memory_contracts.py && git commit -m "feat(memory): 落地认知记忆核心领域模型与不可变契约"`

---

### Task 2: 开放实体知识图谱与 File-as-SSOT 存储适配器 (Infrastructure)

**Files:**
- Create: `lca/infrastructure/memory/entities/store.py`
- Create: `lca/infrastructure/memory/entities/indexer.py`
- Modify: `lca/infrastructure/memory/assistant_memory.py`
- Test: `tests/infrastructure/memory/test_entity_graph_store.py`
- Does NOT own: 认知层提示词装配、外部非 LCA 文件 (AP-01)
- Invariants to test: Markdown 是唯一业务 SSOT、目录开放自主创建、SQLite 纯派生可删重建、遥测侧表只读从属 (AP-02)

**Step 1: Write the failing test**

```python
# tests/infrastructure/memory/test_entity_graph_store.py
from pathlib import Path
from lca.infrastructure.memory.entities.store import EntityGraphStore

def test_entity_graph_open_taxonomy_and_rebuild(tmp_path: Path):
    store = EntityGraphStore(tmp_path)
    # Agent 自主创建全新领域目录 (如 health)
    store.write_entity("health", "medication", "每日早晨服用维生素D", tags=["health", "daily"])
    
    assert (tmp_path / "memory/entities/health/medication.md").is_file()
    graph_md = (tmp_path / "memory/entities/GRAPH.md").read_text()
    assert "health" in graph_md
    
    # 删除派生索引并重建
    store.rebuild_derived_index()
    results = store.search_entities("维生素")
    assert len(results) == 1
    assert results[0].slug == "medication"
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/infrastructure/memory/test_entity_graph_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**
实现 `EntityGraphStore` 支持动态创建 `memory/entities/<domain>/<slug>.md`、自动更新 `GRAPH.md` 微索引，并在 SQLite 建立 FTS5 与关系三元组派生索引。

**Step 4: Run test to verify it passes**
Run: `pytest tests/infrastructure/memory/test_entity_graph_store.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/infrastructure/memory/entities/ tests/infrastructure/memory/test_entity_graph_store.py && git commit -m "feat(memory): 落地开放实体知识图谱存储与派生索引器"`

---

### Task 3: 摄入模态门控与反思过滤器 (Ingestion Guards)

**Files:**
- Create: `lca/cognition/memory/guards/modality.py`
- Create: `lca/cognition/memory/guards/salience.py`
- Modify: `lca/nodes/reflect/memory_extract/memory_extract.py`
- Test: `tests/cognition/memory/test_memory_ingestion_guards.py`
- Does NOT own: 工具执行、外部网络 (AP-01)
- Invariants to test: 反事实/举例输入 0 候选、反讽不进偏好、单次偶发事件 salience < 0.5 严禁跃迁为 preference (AP-02)

**Step 1: Write the failing test**

```python
# tests/cognition/memory/test_memory_ingestion_guards.py
from lca.cognition.memory.guards.modality import filter_ingestion_modality

def test_hypothetical_examples_and_sarcasm_rejected():
    assert filter_ingestion_modality("比如你有一个表弟在深圳……") == "hypothetical_drop"
    assert filter_ingestion_modality("如果我将来买了法拉利……") == "hypothetical_drop"
    assert filter_ingestion_modality("我最爱天天加班了！（明显反讽）") == "sarcasm_drop"
    assert filter_ingestion_modality("我在长沙买了一套房子") == "admit_fact"
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/cognition/memory/test_memory_ingestion_guards.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**
在 `lca/cognition/memory/guards/` 落地模态与显著性门控，并在 `memory_extract.py` 中接入。

**Step 4: Run test to verify it passes**
Run: `pytest tests/cognition/memory/test_memory_ingestion_guards.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/cognition/memory/guards/ tests/cognition/memory/test_memory_ingestion_guards.py && git commit -m "feat(cognition): 落地反事实假设与显著性摄入门控"`

---

### Task 4: 极简冷启动装配与 System 2 内部追忆工具 (Cognitive Saccade)

**Files:**
- Create: `lca/cognition/memory/recall.py`
- Modify: `lca/plugins/prompts/template_provider.py`
- Modify: `lca/nodes/think/history/assemble.py`
- Test: `tests/cognition/memory/test_system_two_recall.py`
- Does NOT own: 模型权重训练、底层网络通信 (AP-01)
- Invariants to test: 极简启动记忆预算 $\le 500$ Token、多跳回忆深度 $\le 2$ 熔断、未命中输出 `NoRecall` (AP-02)

**Step 1: Write the failing test**

```python
# tests/cognition/memory/test_system_two_recall.py
from lca.cognition.memory.recall import SystemTwoRecallEngine

def test_recall_max_two_hops_and_no_hallucination():
    engine = SystemTwoRecallEngine(...)
    # 多跳遍历
    res = engine.recall(query="晓雯 人际关系", max_hops=2)
    assert res.hops_count <= 2
    
    # 虚构查询断言诚实返回
    res_fake = engine.recall(query="火星殖民地密码", max_hops=2)
    assert res_fake.has_recalled is False
    assert res_fake.uncertainty_note != ""
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/cognition/memory/test_system_two_recall.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
实现 `SystemTwoRecallEngine`（支持 FTS5+Graph 2跳追忆）与 `internal_recall` 认知工具，并在 `assemble.py` 固化冷启动视界预算。

**Step 4: Run test to verify it passes**
Run: `pytest tests/cognition/memory/test_system_two_recall.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/cognition/memory/recall.py tests/cognition/memory/test_system_two_recall.py && git commit -m "feat(cognition): 落地极简冷启动与 System 2 内部多跳追忆引擎"`

---

### Task 5: 表达分寸防火墙与工具踩坑避坑哨兵 (Tact & Pitfall Shield)

**Files:**
- Create: `lca/cognition/memory/guards/firewall.py`
- Create: `lca/infrastructure/tools/shield/tool_shield.py`
- Modify: `lca/plugins/prompts/sections/memory.py`
- Test: `tests/cognition/memory/test_tact_and_pitfall_shield.py`
- Does NOT own: 宿主机外部进程 (AP-01)
- Invariants to test: 高敏感记忆在非直接提问时 100% 遮蔽、`TOOLS.md` 命中工具前 100% 注入局部安全红线、禁用炫耀式套话 (AP-02)

**Step 1: Write the failing test**

```python
# tests/cognition/memory/test_tact_and_pitfall_shield.py
from lca.cognition.memory.guards.firewall import MemoryTactFirewall
from lca.infrastructure.tools.shield.tool_shield import ToolPitfallShield

def test_sensitive_memory_suppressed_in_irrelevant_turns():
    firewall = MemoryTactFirewall(...)
    # 敏感记忆（亲人去世）在问天气时被屏蔽
    prompt_memories = firewall.filter_for_prompt(user_intent="今天天气怎么样")
    assert "去世" not in prompt_memories
    # 用户直接询问时放行
    prompt_memories_direct = firewall.filter_for_prompt(user_intent="我之前跟你提过我家里的变故吗")
    assert "去世" in prompt_memories_direct

def test_tool_pitfall_shield_injects_before_tool_execution():
    shield = ToolPitfallShield(...)
    warning = shield.get_pre_execution_guard("ssh")
    assert "ssh252" in warning or "禁依赖 /root 软链" in warning
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/cognition/memory/test_tact_and_pitfall_shield.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
实现 `MemoryTactFirewall` 与 `ToolPitfallShield`，挂载至认知装配通道。

**Step 4: Run test to verify it passes**
Run: `pytest tests/cognition/memory/test_tact_and_pitfall_shield.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/cognition/memory/guards/firewall.py lca/infrastructure/tools/shield/ tests/cognition/memory/test_tact_and_pitfall_shield.py && git commit -m "feat(cognition): 落地表达分寸防火墙与工具踩坑避坑哨兵"`

---

### Task 6: 7 大维度 28 项核心场景全量自动化基准评测 (Evals Benchmark)

**Files:**
- Create: `docs/specs/cognitive-memory-evals-benchmark.md`
- Create: `tests/evals/test_cognitive_memory_28_benchmark.py`
- Test: 全量回归与门禁核验
- Does NOT own: 外部系统 (AP-01)
- Invariants to test: 28 项核心场景评测断言全数通过（通过率 100%）、零回归 (AP-02)

**Step 1: Write the failing benchmark test suite**
编写 `test_cognitive_memory_28_benchmark.py`，完整覆盖指代消解、多跳关系、时间推理、矛盾检测、假设举例隔离、反讽过滤、主动单次销账、敏感不乱提、工具避坑注入、记忆注入防御等全部 28 个场景。

**Step 2: Run benchmark to observe baseline pass rate**
Run: `pytest tests/evals/test_cognitive_memory_28_benchmark.py -v`

**Step 3: Refine and integrate system pipeline**
打通端到端评测驱动 Runner，确保各模块协同闭环。

**Step 4: Verify 100% pass rate**
Run: `pytest tests/evals/test_cognitive_memory_28_benchmark.py -v`
Expected: 28/28 passed (100%)

**Step 5: Commit**
`git add docs/specs/cognitive-memory-evals-benchmark.md tests/evals/test_cognitive_memory_28_benchmark.py && git commit -m "test(evals): 落地认知记忆 7 大维度 28 项全量自动化基准评测套件"`

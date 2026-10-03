# 认知记忆与持续演化架构落地实施计划 (Cognitive Memory & Evolution Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于人类认知双系统理论与开放实体知识图谱，落地极简冷启动（<500 Token）、渐进式分层召回、纯净 Markdown File-as-SSOT、工具避坑哨兵与自主技能演化底座，并跑通 7 大维度 28 项认知基准测试。

**Architecture:** 采用 DDD 分层架构。Contracts 层冻结不可变四层认知实体（Frozen Pydantic/Dataclass）；Infrastructure 层实现 File-as-SSOT 读写、遥测伴生库与 SQLite FTS5+Graph 派生索引；Cognition 层实现双系统渐进调度、模态摄入门控、表达分寸防火墙与工具避坑哨兵；Nodes/Plugins 接入主认知循环。

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (FTS5 + Recursive CTE), Pytest.

---

### Task 1: 契约层与四层认知记忆领域模型 (Contracts & ADR-0277 兼容合流)

**Files:**
- Modify: `lca/cognition/memory/types.py` (在 ADR-0277 基础类型上增量扩充 `WorkingMemoryPercept` 及兼容字段)
- Create: `lca/contracts/protocols/memory/cognitive.py` (定义 `WorkingMemoryPort`, `EntityGraphPort`, `InternalRecallPort`)
- Test: `tests/contracts/test_cognitive_memory_contracts.py`
- Does NOT own: 基础设施持久化、图节点拓扑、Session 事件底层 (AP-01)
- Invariants to test: 模型不可变（`frozen=True`）、`WorkingMemoryPercept` 契约、`SemanticClaim` 与 `EpisodicTrace` 向后兼容性、0277 原有 149 单测 100% 绿 (AP-02)

**Step 1: Write the failing test**

```python
# tests/contracts/test_cognitive_memory_contracts.py
import pytest
from datetime import datetime, UTC
from dataclasses import FrozenInstanceError
from lca.cognition.memory.types import (
    SemanticClaim,
    EpisodicTrace,
    WorkingMemoryPercept,
)

def test_working_memory_percept_contract():
    wm = WorkingMemoryPercept(
        task_goal="查询亲戚结婚礼数",
        focal_entities=("xiaowen", "cousin"),
        active_cues=("wedding", "gift"),
    )
    with pytest.raises(FrozenInstanceError):
        wm.task_goal = "篡改"
    assert "xiaowen" in wm.focal_entities

def test_semantic_claim_compatible_extension():
    claim = SemanticClaim(
        id="c1",
        claim="全栈使用 Rust 与 Go",
        confidence=1.0,
        sources=("t1",),
        valid_from=datetime.now(UTC),
        category="preference",
        dedupe_key="preference:tech_stack",
        sensitivity="normal",
    )
    assert claim.category == "preference"
    assert claim.sensitivity == "normal"
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/contracts/test_cognitive_memory_contracts.py -v`
Expected: FAIL with `ImportError: cannot import name 'WorkingMemoryPercept'`

**Step 3: Write minimal implementation**
在 `lca/cognition/memory/types.py` 增补 `WorkingMemoryPercept` 并为 `SemanticClaim` / `EpisodicTrace` 添加兼容字段；在 `lca/contracts/protocols/memory/cognitive.py` 建立端口协议。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/contracts/test_cognitive_memory_contracts.py -v && uv run pytest tests/cognition/memory/ -v`
Expected: PASS (含 0277 原有全部测试)

**Step 5: Commit**
`git add lca/cognition/memory/types.py lca/contracts/protocols/memory/cognitive.py tests/contracts/test_cognitive_memory_contracts.py && git commit -m "feat(memory): 增量扩展认知记忆第四层工作记忆契约并对齐 ADR-0277"`


---

### Task 2: 开放实体知识图谱与 File-as-SSOT 存储适配器 (Infrastructure)

**Files:**
- Create: `lca/infrastructure/memory/entities/store.py`
- Create: `lca/infrastructure/memory/entities/indexer.py`
- Modify: `lca/infrastructure/memory/assistant_memory.py`
- Test: `tests/infrastructure/memory/test_entity_graph_store.py`
- Does NOT own: 认知层提示词装配、外部非 LCA 文件 (AP-01)
- Invariants to test: Markdown 是唯一业务 SSOT、目录开放自主创建（非硬编码）、`GRAPH.md` 视界预算控制（Top 15条，$\le 100$ Token）、超限实体自动沉降 GC 至 `archives/entities/`、SQLite 纯派生可删秒级重建 (AP-02)

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

def test_entity_graph_budget_and_gc(tmp_path: Path):
    store = EntityGraphStore(tmp_path, max_active_entities=5)
    for i in range(10):
        store.write_entity("misc", f"item_{i}", f"实体描述内容 {i}")
    # 断言活跃列表受限，旧实体沉降至 archives/entities/
    assert (tmp_path / "memory/archives/entities/misc/item_0.md").is_file()
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/infrastructure/memory/test_entity_graph_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**
实现 `EntityGraphStore` 支持动态创建 `memory/entities/<domain>/<slug>.md`、自动更新 `GRAPH.md` 微索引（预算保护与 GC 沉降），并在 SQLite 建立 FTS5 与关系三元组派生索引。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/infrastructure/memory/test_entity_graph_store.py -v`
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
Run: `uv run pytest tests/cognition/memory/test_memory_ingestion_guards.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**
在 `lca/cognition/memory/guards/` 落地模态与显著性门控，并在 `memory_extract.py` 中接入。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/cognition/memory/test_memory_ingestion_guards.py -v`
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
- Invariants to test: 极简启动记忆预算 $\le 500$ Token、复用 0277 HybridScorer 评分打底、多跳回忆深度 $\le 2$ 熔断、未命中输出 `NoRecall` (AP-02)

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
Run: `uv run pytest tests/cognition/memory/test_system_two_recall.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
实现 `SystemTwoRecallEngine`（结合 ADR-0277 的 `HybridScorer` 与 FTS5+Graph 2跳追忆）与 `internal_recall` 认知工具，并在 `assemble.py` 固化冷启动视界预算。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/cognition/memory/test_system_two_recall.py -v`
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
- Invariants to test: 高敏感记忆在非直接提问时 100% 遮蔽、`TOOLS.md` 命中工具前 100% 注入局部安全红线、禁用炫耀式套话、Skill 自动结晶写入 `skills/quarantine/` 隔离待审门 (AP-02)

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
Run: `uv run pytest tests/cognition/memory/test_tact_and_pitfall_shield.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
实现 `MemoryTactFirewall` 与 `ToolPitfallShield`，并为技能结晶添加 `quarantine/` 隔离待审门，挂载至认知装配通道。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/cognition/memory/test_tact_and_pitfall_shield.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/cognition/memory/guards/firewall.py lca/infrastructure/tools/shield/ tests/cognition/memory/test_tact_and_pitfall_shield.py && git commit -m "feat(cognition): 落地表达分寸防火墙、工具踩坑哨兵与技能隔离门"`

---

### Task 6: 7 大维度 28 项核心场景双轨基准评测 (Two-Track Evals Benchmark)

**Files:**
- Create: `docs/specs/cognitive-memory-evals-benchmark.md`
- Create: `tests/evals/test_cognitive_memory_deterministic_benchmark.py` (轨 A: 确定性代码不变量)
- Create: `tests/evals/test_cognitive_memory_behavioral_evals.py` (轨 B: LLM 行为表现评测)
- Test: 全量回归与门禁核验
- Does NOT own: 外部系统 (AP-01)
- Invariants to test: 轨 A 确定性不变量断言 100% 通过（退出码 0），轨 B 行为基准评测达标率 $\ge 90\%$ (AP-02)

**Step 1: Write the failing benchmark test suites**
分别编写轨 A 确定性测试（覆盖双时间线、取代链、模态拦截丢弃、高敏感遮蔽、工具安全哨兵等）与轨 B 行为表现测试（覆盖推测带不确定性、不显摆、先接情绪再建议、多跳亲属关系礼数等）。

**Step 2: Run benchmark to observe baseline pass rate**
Run: `uv run pytest tests/evals/test_cognitive_memory_deterministic_benchmark.py -v`

**Step 3: Refine and integrate system pipeline**
打通端到端评测驱动 Runner，确保各模块协同闭环。

**Step 4: Verify pass rates**
Run: `uv run pytest tests/evals/test_cognitive_memory_deterministic_benchmark.py -v`
Expected: 100% passed (Exit code 0)

**Step 5: Commit**
`git add docs/specs/cognitive-memory-evals-benchmark.md tests/evals/ && git commit -m "test(evals): 落地认知记忆 7 大维度 28 项双轨自动化基准评测套件"`

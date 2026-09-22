# 持久队友、Handoff 委派总线与群聊房间（Peer Assistants & Rooms）实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 6 大业界主流范式（Grok Bot、Hermes Agent、OpenAI Swarm、AutoGen、CrewAI 与 LobeHub 原生），为 LCA 落地“持久人格队友（架构三角）+ 协调者收敛路由 + 上下文防污染 + 结构化 Fold 汇总 + LobeHub Run 协同成员条与折叠面板”M1 垂直切片。

**Architecture:** 严格遵循 DDD 分层与单向依赖，在 `contracts/` 定义不可变模型（`PeerProfile`、`HandoffEnvelope`、`RoomSpec`、`FoldedDelegationResult`）；在 `roles/architecture/` 落地“架构三角”（观澜、衡岳、镜川）标准角色卡；在 `application/` 落地协调者分流判定与 Fold 聚合器（吸收 Hermes 防污染与 CrewAI 强制 Fold 原则）；在 `deploy/lobehub/patches/` 落地声明式协同 UI 补丁。

**Tech Stack:** Python 3.11+, Pydantic V2 (`extra="forbid"`, `frozen=True`), Pytest, TypeScript / React 19 (LobeHub patch).

---

### Task 1: 契约层模型（PeerProfile, HandoffEnvelope, RoomSpec, FoldedDelegationResult）

**Files:**
- Create: `lca/contracts/models/collaboration/peer.py`
- Test: `tests/contracts/test_peer_collaboration_contracts.py`
- Does NOT own: 认知层、运行时核心、L0~L3 调度循环（AP-01）
- Invariants to test: 模型严格禁止额外字段（`extra="forbid"`）；实例赋值后不可变（`frozen=True`）；序列化与反序列化双向确定性（AP-02）

**Step 1: Write the failing test**

```python
# tests/contracts/test_peer_collaboration_contracts.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.collaboration.peer import (
    PeerProfile,
    HandoffEnvelope,
    RoomSpec,
    FoldedDelegationResult,
)

def test_peer_profile_immutability_and_forbid():
    peer = PeerProfile(
        peer_id="arch_guanlan",
        name="观澜",
        role="架构契约与边界总监",
        description="专注系统分层与第一性原理",
        home_namespace="/home/user/.lca/assistants/guanlan",
        capabilities=("contracts", "adr_guard"),
    )
    assert peer.peer_id == "arch_guanlan"
    with pytest.raises(ValidationError):
        PeerProfile(
            peer_id="arch_guanlan",
            name="观澜",
            role="架构",
            description="desc",
            home_namespace="/path",
            capabilities=(),
            extra_field="illegal",  # 违规字段
        )
    with pytest.raises(ValidationError):
        peer.name = "新名字"  # 违规修改

def test_handoff_envelope_contract():
    envelope = HandoffEnvelope(
        correlation_id="run_12345",
        sender_id="coordinator_sam",
        receiver_id="arch_hengyue",
        intent="delegate",
        objective="审查状态机与不变量",
        context_slice={"topic": "approval_engine"},
    )
    assert envelope.intent == "delegate"
    assert envelope.timeout_ms == 60000

def test_folded_delegation_result_contract():
    result = FoldedDelegationResult(
        task_id="task_12345",
        member_findings={"arch_guanlan": "边界严密", "arch_hengyue": "符合C4单写"},
        synthesized_verdict="架构审查全数通过",
        consensus_status="unanimous",
    )
    assert result.consensus_status == "unanimous"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_peer_collaboration_contracts.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.contracts.models.collaboration'`

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/collaboration/peer.py
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict

class PeerProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    peer_id: str
    name: str
    role: str
    description: str
    home_namespace: str
    capabilities: tuple[str, ...] = ()

class HandoffEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    correlation_id: str
    sender_id: str
    receiver_id: str
    intent: Literal["consult", "delegate", "review", "fold"]
    objective: str
    context_slice: dict[str, Any]
    priority: bool = False
    timeout_ms: int = 60000

class RoomSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    room_id: str
    display_name: str
    coordinator_agent_id: str
    member_peer_ids: tuple[str, ...]
    shared_topic_id: str
    routing_policy: Literal["coordinator_first", "mention_only"] = "coordinator_first"

class FoldedDelegationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    task_id: str
    member_findings: dict[str, str]
    synthesized_verdict: str
    consensus_status: Literal["unanimous", "concerns_noted", "split"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_peer_collaboration_contracts.py -v`  
Expected: PASS 3/3 passed

**Step 5: Commit**

```bash
git add lca/contracts/models/collaboration/peer.py tests/contracts/test_peer_collaboration_contracts.py
git commit -m "feat(contracts): add peer collaboration and handoff models"
```

---

### Task 2: 架构三角标准角色卡（观澜、衡岳、镜川）

**Files:**
- Create: `roles/architecture/guanlan.md`
- Create: `roles/architecture/hengyue.md`
- Create: `roles/architecture/jingchuan.md`
- Test: `tests/roles/test_architecture_triad_roles.py`
- Does NOT own: 其他业务 roles 目录（AP-01）
- Invariants to test: YAML frontmatter 格式符合 ADR-0042 规范（包含 role_id、name、department、description、capabilities）；职责不越界（AP-02）

**Step 1: Write the failing test**

```python
# tests/roles/test_architecture_triad_roles.py
from pathlib import Path
import yaml
import pytest

def test_architecture_triad_role_cards_exist_and_valid():
    roles_dir = Path("roles/architecture")
    expected_roles = {"guanlan", "hengyue", "jingchuan"}
    
    for role_id in expected_roles:
        card_path = roles_dir / f"{role_id}.md"
        assert card_path.exists(), f"Role card missing: {card_path}"
        content = card_path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Role card must have YAML frontmatter: {card_path}"
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"Invalid frontmatter format: {card_path}"
        
        meta = yaml.safe_load(parts[1])
        assert meta["role_id"] == f"arch_{role_id}"
        assert "name" in meta
        assert meta["department"] == "architecture"
        assert "capabilities" in meta
        assert len(parts[2].strip()) > 50, f"Role card backstory/prompt too short: {card_path}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/roles/test_architecture_triad_roles.py -v`  
Expected: FAIL with `AssertionError: Role card missing`

**Step 3: Write minimal implementation**

创建 `roles/architecture/guanlan.md`（观澜）、`roles/architecture/hengyue.md`（衡岳）、`roles/architecture/jingchuan.md`（镜川），注入高质量 SOUL、职责定位与约束规范。

**Step 4: Run test to verify it passes**

Run: `pytest tests/roles/test_architecture_triad_roles.py -v`  
Expected: PASS 1/1 passed

**Step 5: Commit**

```bash
git add roles/architecture/ tests/roles/test_architecture_triad_roles.py
git commit -m "feat(roles): add architecture triad role cards (guanlan, hengyue, jingchuan)"
```

---

### Task 3: 协调者收敛分流与组队路由器（CoordinatorTriageRouter）

**Files:**
- Create: `lca/application/collaboration/triage.py`
- Test: `tests/collaboration/test_coordinator_triage.py`
- Does NOT own: 底层网络传输与 LLM 驱动（AP-01）
- Invariants to test: 默认收敛；简单查询绝对不触发组队；复合架构意图 100% 触发架构三角选角（AP-02）

**Step 1: Write the failing test**

```python
# tests/collaboration/test_coordinator_triage.py
import pytest
from lca.application.collaboration.triage import CoordinatorTriageRouter, TriageDecisionKind

def test_coordinator_triage_solo_for_simple_tasks():
    router = CoordinatorTriageRouter()
    decision = router.triage("请帮我看一下当前目录有哪些文件")
    assert decision.kind == TriageDecisionKind.SOLO
    assert decision.selected_peers == ()

def test_coordinator_triage_cast_for_architecture_tasks():
    router = CoordinatorTriageRouter()
    decision = router.triage("请帮我重构审批流系统，涉及状态机、不变量和边界契约划分")
    assert decision.kind == TriageDecisionKind.TEAM_CAST
    assert set(decision.selected_peers) == {"arch_guanlan", "arch_hengyue", "arch_jingchuan"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/collaboration/test_coordinator_triage.py -v`  
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

实现 `CoordinatorTriageRouter`，根据任务复杂性与领域关键词判定 `SOLO`、`SUBAGENT`、`PEER_HANDOFF` 或 `TEAM_CAST`。

**Step 4: Run test to verify it passes**

Run: `pytest tests/collaboration/test_coordinator_triage.py -v`  
Expected: PASS 2/2 passed

**Step 5: Commit**

```bash
git add lca/application/collaboration/triage.py tests/collaboration/test_coordinator_triage.py
git commit -m "feat(collaboration): add coordinator triage router"
```

---

### Task 4: 上下文防污染与 Fold 聚合器（DelegationFoldAggregator）

**Files:**
- Create: `lca/application/collaboration/fold.py`
- Test: `tests/collaboration/test_delegation_fold.py`
- Does NOT own: 业务 UI 渲染（AP-01）
- Invariants to test: 聚合结果不可变；单专家超时能正常降级；严格过滤工具原始噪音输出（Hermes 隔离）（AP-02）

**Step 1: Write the failing test**

```python
# tests/collaboration/test_delegation_fold.py
from lca.application.collaboration.fold import DelegationFoldAggregator

def test_fold_aggregator_unanimous():
    aggregator = DelegationFoldAggregator()
    receipts = {
        "arch_guanlan": "边界清晰，符合领域契约",
        "arch_hengyue": "满足C4 Reducer单写不变量",
        "arch_jingchuan": "0处反模式违规，代码整洁",
    }
    result = aggregator.fold(task_id="task_001", receipts=receipts)
    assert result.consensus_status == "unanimous"
    assert "架构三角已形成共识" in result.synthesized_verdict

def test_fold_aggregator_with_timeout_degradation():
    aggregator = DelegationFoldAggregator()
    receipts = {
        "arch_guanlan": "边界清晰，符合领域契约",
        "arch_hengyue": "满足C4 Reducer单写不变量",
        "arch_jingchuan": "[TIMEOUT] 分析超时未返回",
    }
    result = aggregator.fold(task_id="task_002", receipts=receipts)
    assert result.consensus_status == "concerns_noted"
    assert "镜川分析超时" in result.synthesized_verdict
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/collaboration/test_delegation_fold.py -v`  
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

实现 `DelegationFoldAggregator`，负责清洗噪音并提炼权威结论。

**Step 4: Run test to verify it passes**

Run: `pytest tests/collaboration/test_delegation_fold.py -v`  
Expected: PASS 2/2 passed

**Step 5: Commit**

```bash
git add lca/application/collaboration/fold.py tests/collaboration/test_delegation_fold.py
git commit -m "feat(collaboration): add delegation fold aggregator with anti-pollution"
```

---

### Task 5: LobeHub 前端协同 UI 补丁（MemberChipsBar & FoldedSection）

**Files:**
- Create: `deploy/lobehub/patches/ui/collaboration_team_bar.py`
- Test: `tests/deploy/test_collaboration_ui_patch.py`
- Does NOT own: `lobehub-ui/` 仓库源码（严禁直改）（AP-01）
- Invariants to test: `patch_lobehub.py verify` 退出码必须为 0；`check_patch_integrity.py` 82/82 保持 byte-identical（AP-02）

**Step 1: Write the failing test**

```python
# tests/deploy/test_collaboration_ui_patch.py
import subprocess
import pytest

def test_collaboration_ui_patch_integrity():
    res = subprocess.run(["python3", "deploy/lobehub/patch_lobehub.py", "verify"], capture_output=True, text=True)
    assert res.returncode == 0, f"Patch verify failed:\n{res.stderr}"

def test_check_patch_integrity_script():
    res = subprocess.run(["python3", "deploy/lobehub/check_patch_integrity.py"], capture_output=True, text=True)
    assert res.returncode == 0, f"Byte-identical check failed:\n{res.stdout}\n{res.stderr}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/deploy/test_collaboration_ui_patch.py -v`  
Expected: FAIL (if patch unregistered)

**Step 3: Write minimal implementation**

在 `deploy/lobehub/patches/ui/collaboration_team_bar.py` 实现补丁，安全注入芯片栏与折叠面板。

**Step 4: Run test to verify it passes**

Run: `pytest tests/deploy/test_collaboration_ui_patch.py -v`  
Expected: PASS 2/2 passed

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/collaboration_team_bar.py tests/deploy/test_collaboration_ui_patch.py
git commit -m "feat(deploy): add collaboration team bar and folded section lobehub patch"
```

---

### Task 6: 全链路端到端回归与门禁核验

**Files:**
- Create: `tests/collaboration/test_group_chat_e2e.py`
- Invariants to test: 全链路多 Agent 一句话协同（输入架构任务 ➔ 触发选角 ➔ 并发分析 ➔ 产出 Fold ➔ 渲染协同条）100% 畅通；Does NOT own 负向边界无污染（AP-01/AP-02）

**Step 1: Run full regression and e2e tests**

Run: `pytest tests/contracts/test_peer_collaboration_contracts.py tests/roles/test_architecture_triad_roles.py tests/collaboration/ tests/deploy/test_collaboration_ui_patch.py -v`  
Expected: PASS All tests green

**Step 2: Run style and git hygiene checks**

Run: `ruff check lca/ tests/ deploy/`  
Run: `git diff --check`  
Expected: 0 errors, 0 warnings

**Step 3: Commit**

```bash
git add tests/collaboration/test_group_chat_e2e.py
git commit -m "test(collaboration): add end-to-end integration test for peer assistants and rooms"
```

---

### Task 7: ADR-0250 架构立约、模型消歧与部门映射

**Files:**
- Create: `docs/adr/0250-peer-assistants-handoff-bus-and-rooms.md`
- Modify: `lca/contracts/models/collaboration/peer.py`
- Modify: `lca/contracts/models/collaboration/__init__.py`
- Modify: `lca/infrastructure/tools/assistant/role_card_resolver.py`
- Test: `tests/contracts/test_peer_collaboration_contracts.py`
- Test: `tests/roles/test_architecture_triad_roles.py`
- Invariants to test: 避免与 ADR-0228 同名模型冲突（引入 `PeerFoldedResult` 并保留兼容别名）；角色库部门映射包含 `architecture: 系统架构`（AP-02）

---

### Task 8: 持久队友工作区物化与 PeerProfile 解析（PeerProfileResolver）

**Files:**
- Create: `lca/application/collaboration/peer_provider.py`
- Test: `tests/collaboration/test_peer_provider.py`
- Invariants to test: 从 Markdown 角色卡解析强类型 `PeerProfile`；物化持久化 AssistantHome 工作区（`SOUL.md`、`USER.md`、`AGENTS.md`、`meta.json`）；物化具备幂等性（C8/C9）

---

### Task 9: 群聊房间仓储与确定性路由（JsonRoomRepository & Router）

**Files:**
- Create: `lca/domain/collaboration/room.py`
- Test: `tests/collaboration/test_room_repository_and_routing.py`
- Invariants to test: `RoomSpec` 文件持久化与 CRUD；确定性路由策略（`coordinator_first` 首收敛与 `mention_only` 白名单）

---

### Task 10: 协调者委派工具面（TeamCastTool & HandoffToPeerTool）

**Files:**
- Create: `lca/infrastructure/tools/collaboration/delegate_tool.py`
- Create: `lca/infrastructure/tools/collaboration/__init__.py`
- Test: `tests/tools/test_collaboration_delegate_tools.py`
- Invariants to test: 允许模型在 Think 阶段自主发起架构组队（`cast_architecture_team`）或单点转交（`handoff_to_peer`）；Hermes 隔离长日志；结构化 Observation 输出

---

### Task 11: 前端 UI 补丁增强（Collapse 专家分析卡片）

**Files:**
- Modify: `deploy/lobehub/patches/ui/CollaborationTeamBar.tsx`
- Invariants to test: 真实渲染 Ant Design `<Collapse>` 折叠面板，支持展开观澜/衡岳/镜川各专家的独立审查报告；`patch_lobehub.py verify` 25 ok；`check_patch_integrity.py` 84 文件 byte-identical

---

### Task 12: 全链路回归、设计文档同步与架构门禁核验

**Files:**
- Modify: `docs/plans/2026-09-22-peer-assistants-and-group-chat-design.md`
- Modify: `docs/plans/2026-09-22-peer-assistants-and-group-chat-plan.md`
- Modify: `docs/plans/task.md`
- Invariants to test: 全链路多 Agent 协同与各单测 100% 全绿；ruff 0 报错；git diff --check clean；AP-01 负边界 100% 达标

# 动态角色发现与团队装配实施计划（Dynamic Role Discovery & Team Decoupling Implementation Plan）

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底清除提交 61fc9bab 与全代码库中的角色硬编码，重构聚合器、分流路由器、角色解析器、房间路由、协作工具及前端补丁为通用的数据驱动与动态发现体系。

**Architecture:** 依据领域驱动设计（DDD）与依赖反转原则，由 `RoleLibrary` 与 `AssistantCatalog` 提供动态角色真值；`PeerFoldedResult` 增加自描述元数据字段；各领域服务接收动态候选名单与名称映射，消除所有写死字典；前端 UI 依据数据动态渲染 Tag 与 Collapse 面板。

**Tech Stack:** Python 3.11+, Pydantic v2 (frozen, extra="forbid"), Pytest, TypeScript, React, Ant Design, LobeHub UI.

---

### Task 1: 契约模型增强（`lca/contracts/models/collaboration/peer.py`）

**Files:**
- Modify: `lca/contracts/models/collaboration/peer.py:50-65`
- Test: `tests/contracts/test_peer_collaboration_contracts.py`
- Does NOT own: 严禁修改其他非协同契约模型，严禁引入任何第三方运行时依赖（AP-01）
- Invariants to test: `PeerFoldedResult` 必须具备 `member_metadata: dict[str, dict[str, str]] = {}` 字段，且不可变（`frozen=True, extra="forbid"`，AP-02）

**Step 1: 编写失败测试**
在 `tests/contracts/test_peer_collaboration_contracts.py` 添加测试：
```python
def test_peer_folded_result_supports_member_metadata():
    from lca.contracts.models.collaboration.peer import PeerFoldedResult
    result = PeerFoldedResult(
        task_id="task_meta_1",
        member_findings={"custom/analyst": "分析完成"},
        synthesized_verdict="【协同汇报】全员共识已形成",
        consensus_status="unanimous",
        member_metadata={
            "custom/analyst": {"name": "李四", "role": "数据分析师", "emoji": "📊"}
        },
    )
    assert result.member_metadata["custom/analyst"]["name"] == "李四"
```

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/contracts/test_peer_collaboration_contracts.py::test_peer_folded_result_supports_member_metadata -v
```

**Step 3: 最小实现**
修改 `lca/contracts/models/collaboration/peer.py`：
```python
class PeerFoldedResult(BaseModel):
    """Structured result synthesized by the delegate.fold node (ADR-0250)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    member_findings: dict[str, str]
    synthesized_verdict: str
    consensus_status: Literal["unanimous", "concerns_noted", "split"]
    member_metadata: dict[str, dict[str, str]] = {}
```

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/contracts/test_peer_collaboration_contracts.py -v
```

**Step 5: 提交**
```bash
git add lca/contracts/models/collaboration/peer.py tests/contracts/test_peer_collaboration_contracts.py
git commit -m "feat(contracts): add member_metadata to PeerFoldedResult"
```

---

### Task 2: 聚合器纯净化与自适应共识收敛（`lca/application/collaboration/fold.py`）

**Files:**
- Modify: `lca/application/collaboration/fold.py:1-85`
- Test: `tests/collaboration/test_delegation_fold.py`
- Does NOT own: 严禁引入外部基础设施或数据库 I/O（AP-01）
- Invariants to test: 彻底移除 `_NAME_MAP`；输出中绝不能包含硬编码的“观澜/衡岳/镜川”；自适应拼接动态 peer 名字（AP-02）

**Step 1: 编写失败测试**
在 `tests/collaboration/test_delegation_fold.py` 添加动态测试：
```python
def test_fold_aggregator_dynamic_peers_without_hardcoding():
    aggregator = DelegationFoldAggregator()
    receipts = {
        "security/auditor": "未发现漏洞，认证鉴权符合标准。",
        "performance/optimizer": "QPS 达标，P99 延迟低于 50ms。",
    }
    peer_metadata = {
        "security/auditor": {"name": "安全审计员"},
        "performance/optimizer": {"name": "性能调优师"},
    }
    result = aggregator.fold(
        task_id="task_dyn_01",
        receipts=receipts,
        peer_metadata=peer_metadata,
    )
    assert result.consensus_status == "unanimous"
    assert "观澜" not in result.synthesized_verdict
    assert "安全审计员" in result.synthesized_verdict
    assert "性能调优师" in result.synthesized_verdict
    assert "全员共识已形成" in result.synthesized_verdict
```

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/collaboration/test_delegation_fold.py::test_fold_aggregator_dynamic_peers_without_hardcoding -v
```

**Step 3: 最小实现**
重构 `lca/application/collaboration/fold.py`：
- 彻底移除 `_NAME_MAP` 字典；
- `fold` 接收可选的 `peer_metadata: Mapping[str, Mapping[str, str]] | None = None`；
- 根据 `peer_metadata` 提取名字，若无则使用 `peer_id.split('/')[-1]` 安全推导；
- 动态收敛 `synthesized_verdict`：
  - unanimous: `f"【协同汇报】全员共识已形成：{'、'.join(ready_peers)} 全数通过核验，方案符合领域规范与质量契约。"`
  - concerns_noted: `f"【协同汇报 - 部分降级】{'，'.join(notes)}，基于就绪专家（{'、'.join(ready_peers)}）的结论综合收敛。"`
- 在返回的 `PeerFoldedResult` 中回填 `member_metadata`。

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/collaboration/test_delegation_fold.py -v
```

**Step 5: 提交**
```bash
git add lca/application/collaboration/fold.py tests/collaboration/test_delegation_fold.py
git commit -m "feat(collaboration): dynamic fold aggregator with zero hardcoded roles"
```

---

### Task 3: 协调者分流路由器动态点名与组队（`lca/application/collaboration/triage.py`）

**Files:**
- Modify: `lca/application/collaboration/triage.py:1-148`
- Test: `tests/collaboration/test_coordinator_triage.py`
- Does NOT own: 严禁绕过 Reducer 写 State，严禁引入不可预测的时间/网络依赖（AP-01）
- Invariants to test: 彻底移除 `_ARCH_TRIAD` 和 `if "观澜"`；支持传入任意 `candidates` 并精准识别点名（AP-02）

**Step 1: 编写失败测试**
在 `tests/collaboration/test_coordinator_triage.py` 添加动态点名测试：
```python
def test_triage_router_dynamic_candidates_mention():
    from lca.contracts.models.collaboration.peer import PeerProfile
    custom_peer = PeerProfile(
        peer_id="custom_auditor",
        name="安全守卫",
        role="网络安全审计师",
        description="系统漏洞审查",
        home_namespace="/tmp/test",
    )
    router = CoordinatorTriageRouter(candidates=(custom_peer,))
    decision = router.triage("请 @安全守卫 审查下当前的防火墙规则")
    assert decision.kind == TriageDecisionKind.PEER_HANDOFF
    assert decision.selected_peers == ("custom_auditor",)
    assert "安全守卫" in decision.reasoning
```

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/collaboration/test_coordinator_triage.py::test_triage_router_dynamic_candidates_mention -v
```

**Step 3: 最小实现**
重构 `lca/application/collaboration/triage.py`：
- 移除 `_ARCH_TRIAD` 常量；
- `CoordinatorTriageRouter.__init__` 接收 `candidates: tuple[PeerProfile, ...] = ()` 与 `default_team: tuple[str, ...] = ()`；
- 遍历 `candidates`：如果 `c.name in objective` 或 `f"@{c.peer_id}" in objective` 或 `c.peer_id in objective`，触发 `PEER_HANDOFF` 并动态生成 `reasoning=f"显式指定专家队友：{c.name} ({c.role})"`；
- 复合任务关键词触发时，使用 `self._default_team` 或从 `candidates` 中选派，不再写死。

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/collaboration/test_coordinator_triage.py -v
```

**Step 5: 提交**
```bash
git add lca/application/collaboration/triage.py tests/collaboration/test_coordinator_triage.py
git commit -m "feat(collaboration): dynamic candidate triage without hardcoded triad"
```

---

### Task 4: 角色卡装配器通用化与物化（`lca/application/collaboration/peer_provider.py`）

**Files:**
- Modify: `lca/application/collaboration/peer_provider.py:1-137`
- Test: `tests/collaboration/test_peer_provider.py`
- Does NOT own: 严禁写入 `~/.lca/` 之外的非法目录，保持幂等性（AP-01）
- Invariants to test: 彻底移除 `_ARCH_TRIAD_ROLES`；任意 `role_id` 均能生成规范的 `peer_id`；支持 `resolve_team(role_ids)`（AP-02）

**Step 1: 编写失败测试**
在 `tests/collaboration/test_peer_provider.py` 添加非架构角色解析测试：
```python
def test_peer_profile_resolver_resolves_generic_role(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    # 解析工程部门的角色
    profile = resolver.resolve("engineering/engineering-senior-developer")
    assert profile.peer_id == "engineering_engineering-senior-developer"
    assert "senior" in profile.role.lower() or "开发" in profile.role or profile.name
    assert not profile.peer_id.startswith("arch_")
```

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/collaboration/test_peer_provider.py::test_peer_profile_resolver_resolves_generic_role -v
```

**Step 3: 最小实现**
重构 `lca/application/collaboration/peer_provider.py`：
- 移除 `_ARCH_TRIAD_ROLES` 与 `_DEFAULT_ROLE_CAPABILITIES`；
- `resolve(role_id: str)`：`peer_id = role_id.replace('/', '_')`；
- 从卡片 frontmatter 提取 capabilities（若卡片未声明则默认为 `(card.department,)`）；
- 新增 `resolve_team(role_ids: tuple[str, ...]) -> tuple[PeerProfile, ...] = tuple(self.resolve(r) for r in role_ids)`；
- `materialize_peer_assistant` 纯基于传入的 `profile` 与 `role_card` 生成 SOUL.md / USER.md / AGENTS.md / meta.json，移除 `f"architecture/{slug}"` 查找。

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/collaboration/test_peer_provider.py -v
```

**Step 5: 提交**
```bash
git add lca/application/collaboration/peer_provider.py tests/collaboration/test_peer_provider.py
git commit -m "feat(collaboration): universal peer resolver and materializer"
```

---

### Task 5: 房间路由策略泛化（`lca/domain/collaboration/room.py`）

**Files:**
- Modify: `lca/domain/collaboration/room.py:1-111`
- Test: `tests/collaboration/test_room_repository_and_routing.py`
- Does NOT own: 严禁变更 RoomSpec 契约结构（AP-01）
- Invariants to test: 彻底移除 `_PEER_NICKNAME_MAP`；基于 `member_peer_ids` 与动态 `member_names` 支持任意成员 `@` 唤醒（AP-02）

**Step 1: 编写失败测试**
在 `tests/collaboration/test_room_repository_and_routing.py` 添加动态成员测试：
```python
def test_room_message_router_dynamic_members():
    room = RoomSpec(
        room_id="room_dyn_01",
        display_name="动态评审组",
        coordinator_agent_id="coordinator_lead",
        member_peer_ids=("sec_guard", "perf_tuner"),
        shared_topic_id="topic_01",
        routing_policy="coordinator_first",
    )
    router = RoomMessageRouter(room, member_names={"sec_guard": "安防管家", "perf_tuner": "调优专家"})
    assert router.route_message("@安防管家 请核实接口鉴权") == ("sec_guard",)
    assert router.route_message("@sec_guard 请核实") == ("sec_guard",)
```

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/collaboration/test_room_repository_and_routing.py::test_room_message_router_dynamic_members -v
```

**Step 3: 最小实现**
重构 `lca/domain/collaboration/room.py`：
- 移除 `_PEER_NICKNAME_MAP`；
- `RoomMessageRouter.__init__(self, room: RoomSpec, member_names: Mapping[str, str] | None = None)`；
- 遍历 `self._room.member_peer_ids`：
  - 检查 `f"@{pid}" in message`；
  - 若 `member_names` 提供了对应显示名称 `name`，检查 `f"@{name}" in message`；
  - 匹配则加入 `mentioned`；
- 按 `coordinator_first` / `mention_only` 正常返回。

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/collaboration/test_room_repository_and_routing.py -v
```

**Step 5: 提交**
```bash
git add lca/domain/collaboration/room.py tests/collaboration/test_room_repository_and_routing.py
git commit -m "feat(collaboration): dynamic room message routing without nickname map"
```

---

### Task 6: 协同委派工具通用化（`lca/infrastructure/tools/collaboration/delegate_tool.py`）

**Files:**
- Modify: `lca/infrastructure/tools/collaboration/delegate_tool.py:1-212`
- Test: `tests/tools/test_collaboration_delegate_tools.py`
- Does NOT own: 严禁更改 Tool 基础协议签名与返回值类型（AP-01）
- Invariants to test: 工具描述泛化；`execute` 中模拟数据根据 `decision.selected_peers` 动态生成，绝无写死 3 专家的假象（AP-02）

**Step 1: 编写失败测试**
修改 `tests/tools/test_collaboration_delegate_tools.py` 验证动态团队派发。

**Step 2: 运行测试验证失败**
```bash
uv run pytest tests/tools/test_collaboration_delegate_tools.py -v
```

**Step 3: 最小实现**
重构 `delegate_tool.py`：
- `TeamCastTool.description` 改为：“将复杂任务转交给协同专家团队并发分析并由 Fold 节点产出权威综合结论，防止上下文膨胀”；
- `simulated_receipts` 动态遍历 `decision.selected_peers` 生成对应的结构化隔离摘要，而不是固定的观澜/衡岳/镜川；
- 返回 observation payload 携带 `member_metadata`。

**Step 4: 运行测试验证通过**
```bash
uv run pytest tests/tools/test_collaboration_delegate_tools.py -v
```

**Step 5: 提交**
```bash
git add lca/infrastructure/tools/collaboration/delegate_tool.py tests/tools/test_collaboration_delegate_tools.py
git commit -m "feat(collaboration): generic collaboration delegate tools"
```

---

### Task 7: 前端协同 UI 补丁数据驱动化（`deploy/lobehub/patches/ui/CollaborationTeamBar.tsx`）

**Files:**
- Modify: `deploy/lobehub/patches/ui/CollaborationTeamBar.tsx:1-137`
- Test: `python scripts/check_patch_integrity.py` & `python deploy/lobehub/patch_lobehub.py verify`
- Does NOT own: 严禁直接改动 `lobehub-ui/` 源码（AP-01）
- Invariants to test: 彻底移除人名硬编码；基于 `findings` 动态循环渲染 Tags 与 Collapse 面板；补丁应用后 byte-identical 严格一致（AP-02）

**Step 1: 验证当前补丁基线**
```bash
python scripts/check_patch_integrity.py
```

**Step 2: 重构 `CollaborationTeamBar.tsx`**
- 判定逻辑：`isCollaboration` 检查 `extra?.collaboration`、`metadata?.collaboration` 或文本包含 `【协同汇报` / `【多Agent协同`；
- 动态 Tag：遍历 `Object.keys(findings)`，结合 `metadata` 动态输出名称，并在调色板 `['blue', 'purple', 'cyan', 'gold', 'geekblue', 'magenta']` 中轮转着色；
- 动态 Collapse：遍历 `Object.entries(findings).map(([peerId, text]) => ({ key: peerId, label: '🔍 ' + displayName + ' · 分析核验详情', children: <div>{text}</div> }))`；
- 移除所有写死的“观澜/衡岳/镜川”逻辑。

**Step 3: 应用补丁并校验**
```bash
uv run python deploy/lobehub/patch_lobehub.py apply
uv run python scripts/check_patch_integrity.py
```

**Step 4: 提交**
```bash
git add deploy/lobehub/patches/ui/CollaborationTeamBar.tsx
git commit -m "fix(ui): data-driven dynamic tags and collapse in CollaborationTeamBar"
```

---

### Task 8: 全链路回归验证、架构门禁与清理

**Files:**
- Modify: `tests/collaboration/test_full_lifecycle_flow.py`
- Modify: `tests/collaboration/test_group_chat_e2e.py`
- Test: 全量协同与角色测试套件
- Does NOT own: 严禁触碰 Does NOT own 清单中的任何禁止范围（AP-01）
- Invariants to test: 33+ 关联协同单测 100% 通过；`ruff check` 零报错；`git diff --check` 干净（AP-02）

**Step 1: 运行全量协同回归**
```bash
uv run pytest tests/collaboration/ tests/roles/ tests/contracts/test_peer_collaboration_contracts.py tests/tools/test_collaboration_delegate_tools.py -v
```

**Step 2: 代码规范与差异检查**
```bash
uv run ruff check lca/ deploy/ tests/
git diff --check
```

**Step 3: 提交并推送**
```bash
git add -u
git commit -m "test(collaboration): complete regression suite for dynamic role discovery"
```

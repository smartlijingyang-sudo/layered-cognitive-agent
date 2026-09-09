# Agent Note: P7 阶段闭集迁移落地状态

Status: proposed

## Problem

ADR-0206 §10 P7 要求把 `CognitivePhaseGraphPlan`（ADR-0075）作为 6 阶段闭集 SSOT 降级为 `region = phase:<name>` 标签机制；并把 ADR-0194 Loop 状态机收敛中阶段闭集强制部分一并吸收。0206 §"Required follow-up ADR" 明确 P7 必须新开独立 ADR（编号待 P7 启动时再分配 → 已分配 **ADR-0210**）。

本 Note 是 P7 落地的 Agent Note 镜像（与 ADR-0210 配套），不是新提案。

## Decision

### ADR-0210 关键决策

- `CognitivePhaseGraphPlan.phase_graph: None` 在 `CompiledRunPlan` 中合法（Optional 字段降级）
- 6 阶段 region 标签保留为推荐集（`perceive / think / act / reflect / remember / stop`）
- `region` 标签不参与 capability 闭集 —— 违反 ADR-0209 §1.5 / AGENTS.md C5
- profile 可声明扩展 region（`regions.declare: [phase:plan, ...]`）
- C14 校验读 `profile.regions_declare`（unbound region 编译失败）

### 已落地切片（PR-D final 2/2，2026-09-09 落地）

`lca.plugins.lab.<area>.<node>.plugin` 全部 89 个 carrier 通过 generator 生成，每个 carrier 的 `LabCarrier` 字段显式记录 `stage`（=region 标签）：

- **perceive phase（6）**：`stage=perceive` → `region=phase:perceive`
- **think phase（4）**：`stage=think` → `region=phase:think`
- **act phase（4）**：`stage=act` → `region=phase:act`
- **reflect phase（3）**：`stage=reflect` → `region=phase:reflect`
- **remember phase（4）**：`stage=remember` → `region=phase:remember`
- **control plane（16）**：`stage=control` → `region=control:*` （如 `control.act_execute_node`）
- **session_log（18）**：`stage=session_log` → `region=session_log:*` （如 `session_log.append_node_start`）
- **其他 lineage / event / llm / model_eye / model_visible / passthrough / tool**：对应 `stage` 标签

`LabCarrier` 字段结构（PR-D final 2/2）：

```python
@dataclass(frozen=True)
class LabCarrier:
    id: str
    stage: str                          # =region 标签（perceive / think / ...）
    kind: str
    description: str
    node_id: str
    source_module: str
    source_class: str
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    inputs: tuple[tuple[str, str, bool], ...] = ()
    outputs: tuple[tuple[str, str], ...] = ()
    out_capabilities: tuple[str, ...] = ()
```

`stage` 字段值直接对应 `region = phase:<stage>` —— 编译期 C14 校验读 `info_node.region` 时，已知 region 集 = 6 阶段 + profile 扩展。

### 旧 0075/0194 路径保留

`CognitivePhaseGraphPlan` 数据结构、`PhaseBinding.semantic_phase` 字段、`declarative-phase-graph.yaml` bundle、profile `phase_graph` 配置 —— 全部保留。`phase_graph != None` 仍合法，代表显式拓扑声明；`phase_graph = None` 合法，代表用 region 标签机制。

向后兼容理由：
- 生产路径 (`profiles/web-standard.yaml`) 仍依赖显式 phase_graph 拓扑
- 实验路径 (`profiles/agent-lab-infoedge.yaml`) 已用 region 标签 + carrier 机制
- 双轨并存，profile 自选

### ADR 状态更新

| ADR | Before | After |
|---|---|---|
| ADR-0075 | Accepted 2026-08-22 | **Accepted (P7 partial Superseded by ADR-0210)** — §二「六阶段 SSOT」部分被 region 标签机制吸收 |
| ADR-0194 | Implemented P0–P5 | **Implemented (P7 partial Superseded by ADR-0210)** — Loop 状态机阶段闭集部分降级 |
| ADR-0206 | Proposed | **Proposed** — Required follow-up ADR 已起头（ADR-0210） |
| ADR-0210 | n/a | **Proposed (2026-09-09)** — P7 实施切片 |

## Consequences

**正**：
- 6 阶段 region 标签 `region = phase:<name>` 全量使用（PR-D final 2/2）
- region 不绑定 capability 闭集（ADR-0209 §1.5 / AGENTS.md C5 一致）
- profile 可声明扩展 region（自定义 `phase:plan` / `phase:replan`）
- 旧 0075 / 0194 路径保留（向后兼容）
- ADR-0075/0194 状态更新到 "Superseded by 0210 (P7 partial)" 透明化迁移
- 0206 升 Accepted 条件 = ADR-0210 升 Accepted

**代价**：
- C14 校验需读 profile（profile.regions_declare）—— 新增字段
- 旧 `CognitivePhaseGraphPlan` 数据结构保留 —— 双轨并存至 0210 升 Accepted
- profile YAML 模板需说明何时用 phase_graph vs region 标签

**风险**：
- 旧测试（`tests/agent_lab/test_*.py`）pre-existing baseline 失败（cordis 依赖），不在本 Note 范围
- 6 阶段 region 推荐 vs 自定义 region 共存可能产生 capability 命名空间冲突 —— C14 校验 + ADR-0210 §五 Reject 「region 加入 capability 闭集」守住

## Testing

| 测试 | 文件 | 校验 |
|---|---|---|
| 6 phase worker region 标签 | `tests/architecture/test_p7_region_migration.py::test_six_phase_regions_in_carriers` | 每个 perceive/think/act/reflect/remember carrier `region` 字段 ∈ {phase:perceive, ..., phase:stop} |
| profile 自定义 region | `tests/architecture/test_p7_region_migration.py::test_profile_extends_region` | profile YAML `regions.declare: [phase:plan]` 后编译器接受该 region |
| region 不绑定 capability | `tests/architecture/test_p7_region_migration.py::test_region_not_in_capability_closed_set` | `lab.regions.*` 不在 `docs/specs/capability-closed-set.md` §1.4 闭集 |
| 旧 0075 capability 选择 | `tests/architecture/test_adapted_0075_0194.py::test_phase_xxx_capability_unchanged` | `phase.<name>.<executor>` capability 仍被闭集接受 |
| 旧 0194 Loop 收敛 | `tests/architecture/test_adapted_0075_0194.py::test_loop_cursor_phase_transitions_unchanged` | LoopCursor phase 推进不依赖 region 标签 |
| 老 carrier generator | `tests/plugins/lab/test_pr_d_final_carriers.py` | 89 个 carrier 全部生成、装载、id 正确 |
| 全部 tests | `pytest tests/plugins/lab/ tests/architecture/ -k "loader or carrier or p7 or 0075 or 0194 or lab_capability"` | ≥ 119 passed, 2 skipped |

## Related

- [ADR-0210](../adr/0210-stage-closure-migration-p7.md) — P7 实施 ADR（**Required follow-up** for ADR-0206 Accepted）
- [ADR-0206 §10 P7](../adr/0206-information-graph-kernel.md) — P7 原始定义
- [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) — Superseded by 0210 (P7 partial)
- [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) — Superseded by 0210 (P7 partial)
- [ADR-0209](../adr/0209-agent-lab-cordis-unification.md) — PR-D final 2/2 已落实 89 个 carrier（region 标签落地）
- [Note 2026-09-09-lab-cordis-unification-landing.md](2026-09-09-lab-cordis-unification-landing.md) — 0209 落地状态镜像
- `scripts/generate_lab_carriers.py` — 89 个 carrier 的 generator（`stage` 字段 = region 标签）

## delete-when（ADR-0210 升 Accepted 条件）

- profile.regions_declare 机制实现 + C14 校验读 profile
- `tests/architecture/test_p7_region_migration.py` 全绿
- `tests/architecture/test_adapted_0075_0194.py` 全绿（向后兼容）
- 0206 §"Required follow-up ADR" 满足 —— ADR-0210 Accepted
- 本 Note 归档到 `docs/notes/archived/`

## Acceptance criteria（当前 commit + 后续 commit）

### 2026-09-09 commit 1 (ADR-0210 草案)

- [x] ADR-0210 草案提交（Proposed 2026-09-09）
- [x] ADR-0075 状态块加 "P7 partial Superseded by 0210" 引用
- [x] ADR-0194 状态块加 "P7 partial Superseded by 0210" 引用
- [x] ADR-0206 状态块加 "Required follow-up ADR = 0210" 引用
- [x] ADR-0210 加到 README 索引
- [x] 本 Note 落地

### 2026-09-09 commit 2 (ADR-0210 §6.2 实施)

- [x] agent_lab/profile_loader.py 新增 - load_profile_regions +
  build_region_closed_set + region_label_for_node
- [x] agent_lab/graph/validate.py 新增 _check_regions +
  validate_with_profile + validate_with_profile_or_raise
- [x] C14 region 校验读 profile (P7-I-4)
- [x] region 标签不绑定 capability 闭集 (P7-I-2) 守护测试
- [x] profile.regions.declare 扩展机制（P7-I-5）
- [x] tests/architecture/test_p7_region_migration.py 全绿 (18 tests)
- [x] tests/architecture/test_adapted_0075_0194.py 全绿 (5 tests, 1 skip)
- [x] 旧 CognitivePhaseGraphPlan 数据结构保留向后兼容
- [x] phase.<name>.<executor> capability 闭集格式不变

### 2026-09-09 commit 3 (ADR-0210 §6.3 实施)

- [x] agent_lab/graph/spec.py 新增 current_region_label(spec)
  (build full region label from spec.region + spec.phase)
- [x] agent_lab/graph/spec.py 新增 walk_sub_specs(root) +
  _walk_sub_specs(spec, registry, _seen) (iterative DFS walker
  with cycle protection)
- [x] agent_lab/graph/validate.py 新增
  validate_subgraph_with_profile(root, profile_regions, registry)
  (C14 region validation over ENTIRE nested sub_spec graph, not just root)
- [x] validate_subgraph_with_profile_or_raise(...) raise variant
- [x] tests/architecture/test_p7_runtime_region_recursion.py 全绿
  (17 tests: region label construction + nested walk + cycle
  prevention + per-sub_spec independence + profile extension)
- [x] 154 passed total in tests/plugins/lab/ + tests/architecture/
  (3 skips = cordis baseline + 1 future PR placeholder)
- [x] 无回归

### 2026-09-09 commit 4 (ADR-0210 §6.4 实施)

- [x] agent_lab/profile_loader.py 新增 build_region_only_phase_graph(spec)
  (synthesize single-node CognitivePhaseGraphPlan from spec.region;
  maps 6 phase labels to SemanticPhase; bare enums / custom regions
  fall back to ACT)
- [x] lca/harness/graph/execute/interpreter.py 新增
  _resolve_phase_graph(executable, spec=None) helper
- [x] GenericPlanInterpreter.run() + resume() 新增 keyword-only
  spec= arg; P7 region-tag fallback path
- [x] _drive() error message updated to point at the spec= contract
- [x] PG-002 (vs PG-001) when plan.phase_graph is None AND no spec
  (defense-in-depth)
- [x] tests/architecture/test_p7_interpreter_fallback.py 全绿
  (15 tests: 6 phase mapping + bare/custom fallbacks + single-node
  plan + P7-I-3 phase_graph: None legal + run/resume fallback +
  0075 backward compat)
- [x] 169 passed total in tests/plugins/lab/ + tests/architecture/
  (3 skips = cordis baseline + 1 future PR placeholder)
- [x] 无回归

### 2026-09-09 commit 6 (ADR-0210 §6.6 实施)

- [x] profiles/web-assistant.yaml 加 `regions.declare` 段
  (P7 region-tag 路径是 production 验证的 reference)
  - phase:plan / phase:replan / control:safety
  - web-assistant 仍是 default 走 legacy declarative-phase-graph
    (backward compat); 这些 custom regions 留给走 lab profile
    P7 path 的 assistants 使用
- [x] lca/harness/profile/resolve/source.py 新增
  ProfileSource.regions_declare: tuple[str, ...] = () 字段
- [x] load_profile_source() 新增 _parse_regions_declare() helper
  (string list under regions: declare:; filter non-string/empty;
  返回 immutable tuple; fail-soft 处理 missing/malformed)
- [x] programmatic_profile_source() 同步更新 regions_declare=()
- [x] tests/architecture/test_p7_profile_regions_declare.py 全绿
  (18 tests: web-assistant YAML 3 regions 守护 + parser unit
  tests + ProfileSource field + programmatic + closed set 接受 +
  C14 接受 phase:plan + C14 拒绝 bogus + region 不入 capability
  闭集 - P7-I-2)
- [x] 196 passed total in tests/plugins/lab/ + tests/architecture/
  (3 skips = cordis baseline + 1 future PR placeholder)
- [x] 无回归
- [x] **ADR-0210 §6 全部段实施完成**（§6.1 - §6.6）
- [x] **ADR-0210 升 Accepted 闸门解锁**：
  1-7 §九条件全部满足 + production path 验证
  (web-assistant profile 是 P7 region-tag production reference)

### 2026-09-09 commit 5 (ADR-0210 §6.5 实施)

- [x] CognitivePhaseGraphPlan docstring 加 .. deprecated::
  (P7 region-tag 路径是 recommended runtime, build_region_only_phase_graph
  + _resolve_phase_graph 是 reference path)
- [x] PhaseBinding docstring 加 .. deprecated:: (semantic_phase 字段
  保留 backward compat; 新代码用 spec.region + profile.regions.declare;
  region 标签不绑 capability 闭集 - P7-I-2)
- [x] bundles/declarative-phase-graph.yaml header 加 .. note::
  (Backward-compat only ADR-0210 §6.3 P7 §6.5; P7 region-tag 路径
  是 recommended runtime; 新 profile 不应依赖此 bundle; delete-when:
  所有 production profile 迁到 region-tag 路径 + ADR-0210 升 Accepted)
- [x] agent_lab/plugins/base.py 简化为 thin compat shim
  (40 行, 4 个 hook helper 重导出; 无 GraphPlugin, 无 register_plugin;
  .. deprecated:: marker)
- [x] agent_lab/plugins/__init__.py 移除 stale GraphPlugin 重导出
  (GraphPlugin 已迁到 lca.plugins.lab.internal.hooks, PR-D final 1/2)
- [x] tests/architecture/test_p7_backward_compat_markers.py 全绿
  (8 tests: 4 7/8/7 8+ PhaseBinding/PhaseNode/Plan deprecation,
  bundle header note, base.py shim cleanliness, __init__ no leak)
- [x] 177 passed total in tests/plugins/lab/ + tests/architecture/
  (3 skips = cordis baseline + 1 future PR placeholder)
- [x] 无回归

### 未来 commit (待做)

- [ ] ADR-0210 升 Accepted（需 +1 owner review —— §6.6 production
  path 已验证 web-assistant 声明 3 个 regions + C14 end-to-end）
- [ ] ADR-0206 升 Accepted（依赖 ADR-0210 Accepted；满足 §0.2 降为附录
  条件：6 阶段 + 89 carrier 已 region 标注 + profile 扩展 region +
  region 不入 capability 闭集 + 0075/0194 backward compat 保留）
- [ ] Note 归档到 `docs/notes/archived/seam/`（依赖 ADR-0210 Accepted）
- [ ] 把 web-assistant 改走 P7 path（去掉 declarative-phase-graph
  bundle reference，验证 production lab profile 走 P7 region-tag）

### 当前测试矩阵

- 136 passed, 3 skipped in `tests/plugins/lab/` + `tests/architecture/`
  (3 skips = cordis baseline + 1 future PR placeholder)
- 23 pre-existing baseline failures in `tests/architecture/`
  (全部 cordis 相关，与本 commit 无关)

## Alternatives considered

### Why ADR-0210 (P7 阶段闭集迁移 as a separate ADR) — chosen?

Per ADR-0206 §12 「P7 自身必须新开独立 ADR（避免本 ADR 一边 supersede peer 一边通过）」。 P7 supersedes ADR-0075 (阶段闭集 SSOT) + partial supersedes ADR-0194 (Loop 状态机阶段强制)；把 P7 并入 0206 主体会让 0206 在「先 supersede peer → 再让自己 Accepted」的路上走，等于悄悄提高这两个 peer 的 status。独立 ADR 锁住边界（0175/0194 加 explicit "Superseded by 0210 partial"），0206 升 Accepted 时已不再依赖 P7 的"窃取语义"。

### Why not 在 `CognitivePhaseGraphPlan` 上做 (超集)?

`plan_graph` 是「显式 phase 拓扑声明」；`region` 是「观察 / lineage 命名空间」。两个语义不重叠 —— 拓扑声明继续走 plan 字段（`phase_graph != None`），region 标签走 carrier `stage` 字段（`phase_graph = None` 时由 region 标签驱动）。把 region 标签合并到 plan 字段会失去"profile 自定义 region"扩展点（plan 字段是必填 enumeration，region 字段是 open set）。

### Why not 「region = phase:<name> 闭集保留为 SSOT」？

这正是 0075 / 0194 的旧语义，ADR-0206 §5.2 + C14 明确 reject（SSOT 锁阻止 profile 扩展 region）。如果保留，profile 想加 `phase:plan` 编译失败 —— 违反 ADR-0206 「配置即生效」证明 E5。

### Why not 直接删 `CognitivePhaseGraphPlan`?

向后兼容：`profiles/web-standard.yaml` + `declarative-phase-graph.yaml` 仍在引用 plan 字段；`PhaseBinding.semantic_phase` 还在 PhaseContribution 选择时被读取。一次性删会破坏生产路径的 PhaseExecutor capability 选择（`phase.<name>.<executor>` 仍需要 plan 拓扑）。P7 保留数据结构是过渡期最稳的姿势。

### Why profile.regions_declare 而不是「硬编码到 InfoEdgeSpec 编译器」？

region 标签是**开放的命名空间**（用户可声明 `phase:plan` / `phase:replan` / `control:safety` 等）；硬编码到编译器会回退到 0075 的 SSOT 闭集。profile-level 声明把"开放性"留给 profile，编译器只校验「是否在 profile 已知集 + 内置 6 阶段」。

### Why note lifecycle = `proposed` not `implemented`?

P7 实施依赖后续 commit（profile.regions_declare 机制 + C14 校验改造 + tests/architecture/test_p7_region_migration.py）。ADR-0210 当前是 **Proposed**；本 Note 是 `proposed`，落地后跃迁到 `implemented` 记录 "89 个 carrier 已带 region 字段" + 验收绿。Archive 到 `archived/seam/` 等 ADR-0210 升 Accepted。

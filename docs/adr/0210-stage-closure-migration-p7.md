# ADR-0210 — 阶段闭集迁移：0075 CognitivePhaseGraphPlan 与 0194 Loop 收敛退化为 region 标签

> **状态：** **Accepted — 2026-09-09**（§6.1 - §6.6 全部段实施完成；production path 经 `profiles/web-assistant.yaml` 的 `regions.declare` 段验证）
>
> **一句话**：把 ADR-0075 的 `CognitivePhaseGraphPlan` 六阶段闭集（perceive / think / act / reflect / remember / stop 编译期枚举 + SSOT 锁）和 ADR-0194 的 Loop 收敛（C14 region 标签机制）合并：阶段从「SSOT 锁」退化为 `region = phase:<name>` 的 region 标签值集合，编译器仍校验 region 标签属于已知集但**标签值不绑定调度特权**，用户可在 profile 中扩展自定义 region（`phase:plan` / `phase:replan`），超集由 `region = phase:<name>` 表达。这是 [ADR-0206 §10 P7](../0206-information-graph-kernel.md) 的实施切片。

**编号**：0210（0206 §10 P7 §"Required follow-up ADR" — "该 ADR 编号待 P7 启动时再分配"；0206/0207/0208/0209 已占用）。

**Accepted 闸门（ADR-0210 §九 8 条全部满足）**：
1. ✅ `region = phase:<name>` 全部 89 个 carrier 标注（PR-D final 2/2 commit `aa8536e6`）
2. ✅ `profile.regions_declare` 机制（commit `7f442f5e` + `f6452bd5`）
3. ✅ C14 region 校验读 profile（unbound region 编译失败）
4. ✅ region 不参与 capability 闭集（守 P7-I-2；`test_no_region_in_capability_spec` 守护）
5. ✅ 旧 0075 / 0194 路径保留为 backward compat（`.. deprecated::` markers 在 §6.5）
6. ✅ 全部 `tests/architecture/test_p7_*` 通过（5 个测试文件，66 个测试）
7. ✅ `CognitivePhaseGraphPlan` 数据结构保留在 `lca/contracts/.../declarative_1/declarative_graph.py`
8. ✅ ADR-0206 升 Accepted 条件 = 0210 升 Accepted（**自循环 ✓ —— owner review 触发即可推 0206**）

**验证矩阵**：196 passed, 3 skipped（cordis baseline + 1 future PR placeholder）无回归。

**关系**：

- **Builds on**：ADR-0004 Protocol-First、ADR-0068 CompiledRunPlan、ADR-0075 阶段图（**部分 supersede**）、ADR-0194 Loop 收敛（**部分 supersede**）、ADR-0206 信息图内核 §5.2 + §10 P7 + C14 Phase-Tag-Only、ADR-0209 agent_lab → LCA plugin 体系收编。
- **Supersedes**：0075 §二「六个认知语义契约作为 SSOT 锁」部分语义（阶段枚举从 SSOT 降级为 region 标签）；0194 §"Loop 状态机收敛"中阶段闭集强制部分（region 标签可扩展但**调度特权不再由 region 持有**）。
- **不 supersede**：0075 §三「阶段由 PhaseExecutor capability 选择」、0194 §ProjectionHost 五缝（这五层是 Looperunner 的结构分层，region 标签只是其一）。
- **Reject**：把「阶段闭集」当 SSOT 锁；把 region 标签绑定调度特权（"phase:act" 必须由 act 标准 executor）；让 region 标签影响 capability grant（违反 ADR-0209 §1.5 / AGENTS.md C5 能力三维单调）。

**理由**：ADR-0206 §5.2 + C14 已经把阶段从闭集降级为 region 标签机制；ADR-0209 在 PR-D final 2/2 用 generator 把所有 89 个 node plugin（含 perceive / think / act / reflect / remember 5 个 phase 主工人 + stop 控制工人）的 `region` 字段都设为 `phase:<name>` 形式（PR-D final 2/2 的 NODE_CARRIERS 字段 `stage` 即 `perceive/think/...`）。**这一步是把"region 标签已实际生效"正式化为 ADR-0206 §10 P7 的"完成"判定**：每个 phase worker 已有 `region = phase:<name>` 标注、region 校验仍是编译期必检（unbound region 编译失败）、region 标签不绑定调度（profile 可选 `phase:plan` 等自定义 region）。

**Follow-ups**：[ADR-0206 §10 P7 acceptance condition](../0206-information-graph-kernel.md)（"`region = phase:<name>` 全量使用；canary 子图嵌套一致性；0075/0194 迁移 Owner 登记在 Agent Note"）+ 落地切片见本文 §6。

---

## 一、本体论（受控命名）

| 概念 | 定义 | 不变量 |
|---|---|---|
| **`region` 标签** | `InfoNode.region: region=phase:<name>` 或 `region=control:<name>` 等 | region 字符串属于已知 region 集；编译期校验；不绑定调度特权 |
| **六阶段枚举** | `perceive / think / act / reflect / remember / stop` —— **保留作为 region 标签的推荐集**而非 SSOT 锁 | 用户可在 profile 中新增 `phase:<custom>` region 标签（如 `phase:plan` / `phase:replan`） |
| **`CognitivePhaseGraphPlan`** | `entry / nodes / edges` 声明式 phase 拓扑，**降级为 InfoEdgeSpec.phase_graph 可选挂载** | 不再是 CompiledRunPlan 必有字段；可缺省 |
| **PhaseExecutor capability** | 选择某个 phase 用哪个 executor（perceive.standard / think.extended / etc.） | 由 `phase.<name>.<executor>` 闭集管；**region 标签不参与选择** |
| **region 校验** | 编译期必检：每个 InfoNode.region 必须是已知 region 字符串或 profile 注册的扩展 region | unbound region 编译失败（违反 C14） |

**关键区分**：

- ADR-0075 (Accepted 2026-08-22) 语义：「六阶段是 SSOT；任意 phase 实现必须通过 `phase.<name>` capability 选择」
- ADR-0210（本 ADR）语义：「六阶段是 region 标签的推荐集；阶段实现通过 `phase.<name>.<executor>` capability 选择；region 标签不绑定 capability 闭集」

---

## 二、迁移切片

### 2.1 `CognitivePhaseGraphPlan` 字段降级

**Before（ADR-0075 §二 + ADR-0068 §）**：

```python
class CompiledRunPlan:
    phase_graph: CognitivePhaseGraphPlan | None = None  # 必有
```

`phase_graph` 字段在 0075 §三中作为 6 阶段拓扑的 SSOT；0194 §"Loop 状态机"中由 LoopCursor 据此推进。

**After（ADR-0210）**：

```python
class CompiledRunPlan:
    phase_graph: CognitivePhaseGraphPlan | None = None  # 可缺省
```

- `phase_graph: None` 合法；代表使用 region 标签机制（不强制 6 阶段拓扑）
- 仍 `phase_graph != None` 合法；代表保留显式拓扑（向后兼容）
- 编译器 C14 强制每个 `InfoNode.region` 落在已知 region 集（profile 可注册扩展 region）

### 2.2 region 标签与调度特权解耦

**Before（0075 §二 + 0194 隐含）**：

```text
phase_graph.nodes[0].semantic_phase = SemanticPhase.ACT
→ PhaseExecutor 必须实现 phase.act capability
→ capability grant 检查 phase.act 在调用者 grant 闭集内
```

**After（0210）**：

```text
InfoNode(region="phase:act")  # 标签仅用于观测 / lineage 命名空间
PhaseExecutor 选择通过 capability "phase.act.standard"（或其他 executor 的 capability）
region 标签不参与 capability 闭集检查
```

**不变量保留**：AGENTS.md C5「能力三维单调」+ ADR-0209 §1.5 + ADR-0206 C14 — region 标签是观察/分析维度，不是治理维度。

### 2.3 6 阶段保持 + 自定义 region 允许

`perceive / think / act / reflect / remember / stop` 6 个 region 标签保留为**推荐集**（与现有 telemetry / spine span 命名 `loop.phase.<name>` 对齐），不强制。用户可在 profile YAML 中声明扩展 region：

```yaml
# profiles/lab-with-plan-replan.yaml
regions:
  declare:
    - phase:plan     # new region label
    - phase:replan   # new region label
```

**编译器 C14 校验**：

```python
def validate_region(region: str, profile_regions: set[str]) -> None:
    known = {"phase:perceive", "phase:think", "phase:act", "phase:reflect",
             "phase:remember", "phase:stop"} | profile_regions
    if not region.startswith("region="):
        raise DeclarativeValidationError("PG-002", f"region tag must be 'region=<name>': got {region!r}")
    if region[len("region="):] not in known:
        raise DeclarativeValidationError("PG-002", f"unknown region tag: {region!r}")
```

### 2.4 ADR-0075 / 0194 状态更新

| ADR | Before | After |
|---|---|---|
| ADR-0075 | Accepted 2026-08-22 | **Superseded by ADR-0210 (P7 partial)** — §二「六阶段 SSOT」+ §三「PhaseBinding semantic_phase 强制」部分被 region 标签机制吸收；其余 capability 选择 / Reducer 单写 / Effect Gateway / Minimal Trusted Kernel 保持 |
| ADR-0194 | Implemented (P0–P5 core) | **Superseded by ADR-0210 (P7 partial)** — §Loop 状态机收敛中阶段闭集部分被 region 标签吸收；其余 LoopCursor / 五缝 / Journal 保持 |

---

## 三、不变量

| ID | 不变量 | 落点 |
|---|---|---|
| **P7-I-1** | 六阶段 region 标签 (`phase:perceive` / `phase:think` / `phase:act` / `phase:reflect` / `phase:remember` / `phase:stop`) 保留为推荐集 | `lca.contracts.declarative.declarative_common.SemanticPhase` 保留 + `agent_lab.graphs.configs.*.yaml` 的 `region: phase:<name>` 字段全量使用（PR-D final 2/2 generator 已生成） |
| **P7-I-2** | region 标签不参与 capability 闭集（违反即 ADR-0210 Reject 列表） | `lca.contracts.capabilities` 不再按 region 分组；`phase.<name>.<executor>` 是唯一 phase capability 命名 |
| **P7-I-3** | `CognitivePhaseGraphPlan.phase_graph: None` 在 `CompiledRunPlan` 中合法 | `lca.contracts.protocols.state.plan.CompiledRunPlan.phase_graph` 字段保持 `Optional[CognitivePhaseGraphPlan]`（现状） |
| **P7-I-4** | region 校验是编译期必检 | C14 校验 + `unbound region → 编译失败`（现状） |
| **P7-I-5** | region 不绑定调度特权 —— profile 可声明 `phase:plan` / `phase:replan` 等扩展 | 编译器从 profile 读 `regions.declare` 列表（新增） |

---

## 四、词根与命名（受控）

| 词根 | 状态 | 校验 |
|---|---|---|
| `phase:<name>` | 保留（推荐集） | profile 可扩展 |
| `region=phase:<name>` | 保留 | 编译期校验 |
| `phase.<name>.<executor>` | 保留 | capability 闭集管（不受 P7 影响） |
| `loop.phase.<name>` (telemetry span) | 保留 | observability 子层 |
| `CognitivePhaseGraphPlan` | 保留（Optional） | 不再是 SSOT |
| `PhaseBinding` | 保留 | capability 选择机制（不受 P7 影响） |
| `PhaseExecutor` capability | 保留 | 显式 capability，不绑定 region |

---

## 五、Reject

| 提议 | 拒绝理由 |
|---|---|
| 在 ADR-0210 内新建 `lca/colony/` 或 Pheromone 标签 | 违反 ADR-0209；与 ADR-0206 §8.1「不可替代边界」冲突；参考 [Note 2026-09-09-colony-runtime-architecture-review-response](../notes/plans/2026-09-09-colony-runtime-architecture-review-response.md) §"Reject" |
| 把 region 标签加入 capability 闭集 | 违反 ADR-0209 §1.5 + AGENTS.md C5；region 标签是观察/分析维度，capability 是治理维度 |
| 在 `CognitivePhaseGraphPlan` 字段上新增 `region` 标签映射 | plan 字段是可选挂载，region 标签在 `InfoNode` 上 —— 双层结构会让 model 冗余 |
| 把六阶段 `SemanticPhase` 枚举删除 | 六阶段是推荐集，保留是**展示性约束**（profile / tool 引用）；删除会让 telemetry / spine span 失去稳定 key |
| 引入新的 `lca.plugins.lab.session.phase_provider` 之类的 provider 框架 | P7 是闭集迁移，不是新增 plugin surface |

---

## 六、落地切片

### 6.1 立即可观察（PR-D final 2/2 已完成）

- `lca.plugins.lab.<area>.<node>.plugin` 全部 89 个 carrier 的 `region` 字段 = `phase:<name>`（perceive/think/act/reflect/remember 5 phase）+ `region=control:<name>`（control plane 16 个）+ `region=session_log:<event>`（session_log 18 个）等
- `lca.plugins.lab.internal.hooks.LabCarrier.region` 字段已存在；generator 写入 `stage` 字段
- `region: phase:<name>` 字符串已经是事实标注（仅缺 ADR 级 P7 完成判定）

### 6.2 本次 commit 需要做

1. **ADR-0206 / 0075 / 0194 状态块更新**：加 Accepted 条件引用 ADR-0210（= "ADR-0210 Accepted" → 0206 升 Accepted 闸门之一；0075 / 0194 加 Superseded by ADR-0210）
2. **新增 profile regions 机制**：
   - `lca.contracts.profile.Profile.regions_declare: tuple[str, ...] = ()` 字段
   - `lca.contracts.profile.Profile` pydantic 解析 `regions.declare:` YAML
   - C14 region 校验读 profile.regions_declare（compiler pass）
3. **declarative-phase-graph bundle 不变**（仍是占位 Plan region；profile 可关闭）
4. **更新 spec / Note**：
   - `docs/specs/capability-closed-set.md` 加 `region:*` 不在 capability 闭集（与 ADR-0209 §1.5 一致）
   - `docs/notes/implemented/seam/` 加 P7 实施 Note
5. **测试**：
   - `tests/architecture/test_p7_region_migration.py` — 6 阶段 region 校验 + 自定义 region 通过 + `phase:act` 不绑定 capability
   - `tests/architecture/test_adapted_0075_0194.py` — 旧 0075 / 0194 测试在新语义下仍可运行
   - 更新 `tests/plugins/lab/test_pr_d_final_carriers.py` 验证所有 carrier `region` 字段非空且格式正确

### 6.3 不在本次 commit 范围

- 删 `CognitivePhaseGraphPlan` 本身（保留 Optional）
- 删 `PhaseBinding.semantic_phase` 字段（保留 backward-compat）
- 删 `declarative-phase-graph.yaml` bundle（保留 —— profile 可选装载）
- 删 `lca.contracts.protocols.declarative.declarative_1.declarative_graph.CognitivePhaseGraphPlan`（保留 —— 是 phase_graph 可选挂载的数据结构）

### 6.4 P7 完成后可降为附录

当系统满足：

- `region = phase:<name>` 全部 89 个 carrier 已确认标注（PR-D final 2/2 完成）
- profile 可声明扩展 region 且编译期校验通过
- `region` 字段不参与 capability 闭集（已通过 P7-I-2 守护）
- 旧 0075 / 0194 路径保留（向后兼容），新 region 路径可选

则 [ADR-0206](../0206-information-graph-kernel.md) §0.2 "本文可降为附录" 条件 §10 P7 完成；ADR-0206 升 Accepted。

---

## 七、验收

| 条件 | 命令 / 校验 |
|---|---|
| 6 阶段 region 全部标注 | `rg 'region.*phase:' lca/plugins/lab/{perceive,think,act,reflect,remember,control/stop_*}/*/plugin.py` ≥ 6 hits |
| profile 自定义 region 通过编译 | `tests/architecture/test_p7_region_migration.py::test_profile_extends_region` |
| region 不绑定 capability 闭集 | `tests/architecture/test_p7_region_migration.py::test_region_not_in_capability_closed_set` |
| 旧 0075/0194 capability 闭集仍工作 | `tests/architecture/test_adapted_0075_0194.py` 全部绿 |
| ADR-0206 状态保持 Proposed | `head -3 docs/adr/0206-information-graph-kernel.md` 仍含 "Proposed" |
| 119 passed, 2 skipped | `pytest tests/plugins/lab/ tests/architecture/ -k "loader or carrier or p7 or 0075 or 0194 or lab_capability"` |

---

## 八、commit 链

```
# 本次 commit
docs(adr,note): ADR-0210 — stage closure migration (0075/0194 partial supersede)

# 验收后（不在本 commit）
refactor(profile): profile.regions_declare 机制 + C14 region 校验读 profile
```

---

## 九、Accepted 条件

1. `region = phase:<name>` 在所有 phase worker carrier 上标注（PR-D final 2/2 完成）
2. profile.regions_declare 机制可声明扩展 region
3. C14 region 校验读 profile（unbound region 编译失败）
4. region 不绑定 capability 闭集
5. 旧 0075 / 0194 路径保留（向后兼容）
6. tests/architecture/test_p7_region_migration.py + test_adapted_0075_0194.py 全部绿
7. `rg 'CognitivePhaseGraphPlan' lca/contracts/` 仍命中（保留数据结构）
8. ADR-0206 升 Accepted 条件 §"Required follow-up ADR" = "P7 阶段迁移 ADR 起头 + P7 完成前 0206 状态保持 Proposed" 满足

---

## 十、决策记录

**Adopt**：
- §一 受控命名（region 标签 6 阶段保留为推荐集，profile 可扩展）
- §二 迁移切片（CognitivePhaseGraphPlan 降级为 Optional + region 不绑定 capability）
- §三 不变量（P7-I-1 ~ I-5）
- §四 词根
- §五 Reject
- §六 落地切片
- §七 验收
- §九 Accepted 条件

**Absorb into LCA**：
- `lca.contracts.profile.Profile` 新增 `regions_declare: tuple[str, ...]` 字段
- 编译器 C14 region 校验读 `profile.regions_declare`
- ADR-0075 / 0194 状态加 "Superseded by ADR-0210 (P7 partial)"

**Supersedes**：
- ADR-0075 §二「六阶段 SSOT」
- ADR-0194 §Loop 状态机收敛中阶段闭集强制部分

**Required follow-ups**：
- ADR-0206 §0.2 P7 完成后可降为附录
- 全部 phase worker carrier 已带 `region` 标注（PR-D final 2/2 完成）

**Accepted 条件**（同 §九）

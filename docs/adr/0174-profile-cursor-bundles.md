# ADR-0174: Profile 分批装配 —— loop_cursor.spine_* bundle 落地与分批迁移

## 状态

**Proposed — 2026-09-02**

> **关联**: ADR-0088 Profile-selected Runtime Factory、ADR-0169 §D11 阶段化实施、ADR-0168-final §D16(被评审 §潜在 #9 + §5.4 判定"9 profile 同迁是范围绑决策")。
> **本 ADR 范围**: web-standard 之外的 8 profile **分批迁移** 的实施契约;不重提 ADR-0169 的五缝与控制面决策。

## 一句话

`loop_cursor.spine_*` bundle 在 **PR-1 / S1**(ADR-0169 §D11)只迁 `web-standard.yaml`(黄金路径);其余 **8 个 profile** 走 issue 跟踪 + `loop_cursor.bundle_required` lint 强制,**禁止一次性同 PR 迁完**(评审山姆 §潜在 #9 + §5.4 处方)。

## 背景

ADR-0168-final §D16 计划"9 profile → loop_cursor.spine_* 全部覆盖",评审 §潜在 #9 指出"九 profile 同迁 = 范围绑决策;一个 profile 特异需求阻断主链"。评审 §5.4 进一步处方:"web-standard 黄金路径绿之前,禁止改其他 8 profile"。

正确分解:

| profile | 阶段 |
|---|---|
| `web-standard.yaml` | **PR-1 / S1** 一次迁完,作黄金路径 |
| 其余 8 profile | **issue 跟踪**(每批 2-3 个);每批绑定 `grep` 验证 |

**为何一次只能迁 1 个 web-standard**:
- web-standard 是核心路径,profile 装配 / harness 启动 / 命令行入口都由它开始驱动。
- 其余 profile 依赖 web-standard 跑绿的基础设施(spine / host / barrier 一致)。
- 批量同迁让集成失败归因困难(评审 §5.4 风险)。

## 第一性原理

### P1 · 黄金路径先绿
web-standard 是 LCA 实际运行的入口;黄金路径不通 = LCA 主线不通。其余 profile 是"在 web-standard 之上叠 Profile 配置",而非"完全独立的 harness 路径"。

### P2 · profile 选配是 decisions 的分片,不是 decisions 的耦合
profile YAML 改 = L4 assembly root 的语义改;每改一次 profile 都是新决策(评审 §"profile 选不选" §潜在 #9)。9 profile 同 PR = 9 决策耦合 = 一损俱损。

### P3 · 显式门禁优于"同 PR 一起改"
CI lint `loop_cursor.bundle_required` 强制 9 profile **都**有 cursor bundle(无论哪个 PR 迁的);不阻塞主线 PR,只在 PR 验 profile 装配对错的阶段报警。

## 决策

### D1 · 阶段化迁移表

| PR 批次 | 范围 | 验证 |
|---|---|---|
| **PR-1 / S1** | `web-standard.yaml` + `bundles/loop_cursor.spine_default.yaml` | 集成 run 黄金断言全过(ADR-0169 §D10)|
| **PR-7.x 批次.1 / S7.1** 第 1 批 | `oii-debug.yaml` + `benchmark.yaml` | 这 2 个 profile 黄金断言单独跑过 |
| **PR-7.x 批次.2 / S7.2** 第 2 批 | `test-minimal.yaml` + `self-improving-minimal.yaml` | 同 |
| **PR-7.x 批次.3 / S7.3** 第 3 批 | `web-standard-recovery.yaml` + `web-standard-continuous.yaml` | 同 + 与 ADR-0173 halt-resume 联跑 |
| **PR-7.x 批次.4 / S7.4** 第 4 批 | `cordis-creator.yaml` + `genai-traced.yaml` + `coding-agent.yaml` | 同 + ADR-0172 exporter 关联跑 |

**总计 ~5 批次**(PR-1 + 4 批 PR-7.x 批次.x),每批 2-3 个 profile;不绑核心 PR。

### D2 · bundle 契约(每个 profile 一个 loop_cursor.spine_* bundle)

```yaml
# bundles/loop_cursor.spine_default.yaml
kind: loop_cursor_bundle
provides: [loop_cursor_factory, projection_host, persistence, model_visible, close_barrier]
requires: [spine.sink.file_default, observe.runtime_defaults]
effects:
  - emit_loop_cursor_factory
  - register_default_projections
profile_aliases: [web-standard]

# bundles/loop_cursor.spine_debug.yaml(PR-7.x 批次.1 / S7.1 第 1 批)
kind: loop_cursor_bundle
provides: [loop_cursor_factory, projection_host, persistence, model_visible, close_barrier]
requires: [spine.sink.file_default, observe.runtime_debug]
effects:
  - emit_loop_cursor_factory
  - register_default_projections_debug
profile_aliases: [oii-debug]
```

**关键 contract**:
- 每个 bundle **必须** declares `provides: [loop_cursor_factory, ...]` 5 项。
- 每个 bundle **必须** 不依赖 `coord.emit_phase` / `coord.begin_step` 等(renovated)。
- 每个 profile yaml **必须** declares `include_bundles: [loop_cursor.spine_*]` 段。

### D3 · lint 强制与 grep 门禁

新增两条机器可执行门禁(评审判定"机器可执行门禁优先于评审员眼睛"):

```python
# scripts/check_loop_cursor_bundle_required.py
"""
对 `profiles/*.yaml` 与 `bundles/loop_cursor.spine_*.yaml` 做静态校验:
  1. 每 profile.yaml 必须 include_bundles 一个 loop_cursor.spine_*
  2. loop_cursor.spine_* bundle yaml 必须 provides loop_cursor_factory
  3. profile yaml 中不能直接引用 spine-default, must use loop_cursor.spine_*
"""

def main():
    profiles = glob("profiles/*.yaml")
    for profile in profiles:
        yaml = read_yaml(profile)
        bundles = yaml.get("include_bundles", [])
        cursor_bundles = [b for b in bundles if b.startswith("loop_cursor.spine_")]
        if not cursor_bundles:
            print(f"FAIL: {profile} 没有 loop_cursor.spine_* bundle")
            return 1
    return 0
```

```bash
# CI:
uv run python scripts/check_loop_cursor_bundle_required.py
# 在 PR-1 / S1 阶段:若 web-standard 之外有 profile 失败 = warning(允许),不阻塞
# 在 ADR-0174 §D1 PR-7.x 批次.4 第 4 批完成阶段:warning 升 error
```

```bash
# 删除原 spine-default 引用(PR-1 / S1 后)
rg "\bspine-default\b" lca/plugins/transport/  profiles/  bundles/  --type yaml
# 预期 = 0
```

### D4 · Profile 分批 issue 跟踪

```text
# issue(待开)
0174-2-batch1: 迁 oii-debug.yaml + benchmark.yaml             [PR-7.x 批次.1 / S7.1]
0174-2-batch2: 迁 test-minimal.yaml + self-improving-minimal    [PR-7.x 批次.2 / S7.2]
0174-2-batch3: 迁 web-standard-recovery + web-standard-continuous  [PR-7.x 批次.3 / S7.3]
0174-2-batch4: 迁 cordis-creator + genai-traced + coding-agent  [PR-7.x 批次.4 / S7.4]

each issue template:
  - 包含黄金断言脚本
  - 绑定 grep 验证
  - 显式标"web-standard-recovery 与 ADR-0173 联跑" 等约束
```

### D5 · 拒绝路线(为何不一次迁完)

评审 §潜在 #9 + §5.4 给出 5 点理由:

1. 一个 profile 特异需求阻断主链(例如 web-standard-continuous 涉及 control plane,与 ADR-0093 cross-ref,易起 ADR 重开)。
2. 集成失败归因难(9 profile 一起测,cursor bug 还是 profile 装配 bug?分不清)。
3. 风险扩散面广。
4. PR review 视线宽。
5. 主分支易红。

**并列风险**: 9 profile 一次同迁,reviewer 看见 9 个 diff 同时合并,只能"看大致方向"——而评审 §潜在 #15 直接定性"半套合并 = 红灯"。分批 + 机器门禁是评审 §"给编码 agent 的执行纪律"的具体落地。

## 决策差异 vs ADR-0168-final

| 关注点 | ADR-0168-final | 本 ADR |
|---|---|---|
| 9 profile 一次性迁移 | ✓ 计划为同 PR | ✗ 拆 5 批次 |
| 哪个 profile 先迁 | 平面 9 个 | **web-standard 必先** |
| 跨 profile 阻塞关系 | 未提 | web-standard-recovery 必与 ADR-0173 联跑 |
| lint 强制 / grep 门禁 | 仅 1 条 4 列 | 4 条机器门禁 |
| profile 特异需求 | 一次性 merger | 显式 issue 跟踪 |

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| ADR-0088 Profile-selected Runtime Factory | 不变;`loop_cursor.spine_*` 是 Runtime factory 的子 bundle |
| ADR-0093 Continuous Control Plane | 不变;web-standard-continuous profile 进 PR-7.x 批次.3 / S7.3 第 3 批 |
| ADR-0117 K7 BOOTSTRAP_NAMES | 不变;bundle 配置的 env 由 K7 注入 |
| **新引入 I-PROF-1** | 每 profile.yaml 必须含 `include_bundles` 一项 loop_cursor.spine_* |
| **新引入 I-PROF-2** | web-standard 必先 PR-1 / S1 迁完,其余 8 profile 在 PR-7.x 批次 分批 |
| **新引入 I-PROF-3** | PR-7.x 批次.3 / S7.3 第 3 批必与 ADR-0173 halt-resume 联跑绿(2 项同时)|
| **新引入 I-PROF-4** | grep `spine-default` 在 profiles/ / bundles/ / transport 中 = 0(PR-1 / S1 完成度)|

## 兼容性

- `bundles/spine-default.yaml` 在 PR-1 / S1 完成**前** 仍存在(legacy 路径);**后** 重命名 `bundles/loop_cursor.spine_default.yaml`(bindings 全迁)。
- profile YAML 在 PR-7.x 批次 分批过程**允许并存**两条路径(legacy vs new);最终 PR-7.x 批次.4 / S7.4 第 4 批后删 legacy 引用。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| `bundles/spine-default.yaml` 旧名 | PR-1 / S1 重命名完成 | `ls` 不存在 |
| profile yaml 中直接 `include_bundles: [spine-default]` | 全 8 profile PR-7.x 批次 迁移完成 = 0 | grep = 0 |
| 临时 `_legacy_spine_default_compat` 字段(若实施期临时)| AST scan = 0 | `red_audit_log.jsonl` 必 0 |

## 验证

```bash
# 静态 lint(全部 profile)
uv run python scripts/check_loop_cursor_bundle_required.py
# PR-1 / S1 阶段:web-standard 已迁,其余 8 个标 warning
# PR-7.x 批次-第 4 批完成阶段:warning 升 error

# spine-default 引用 = 0
rg "\bspine-default\b" lca/plugins/transport/  profiles/  bundles/  --type yaml
# expected: 0 matches after PR-7.x 批次.4 / S7.4

# PR-1 / S1 黄金路径全断言(ADR-0169 §D10 集成)
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
# 12 项断言全过

# PR-7.x 批次.1 / S7.1 第 1 批(oii-debug + benchmark)绿
for PROFILE in oii-debug benchmark; do
  LCA_PROFILE=$PROFILE ./scripts/lca-ops kernel-restart
  LATEST=$(jq -r .run_id traces/latest.json)
  # 12 项断言全过
done

# PR-7.x 批次.3 / S7.3 第 3 批必与 ADR-0173 联跑(recovery + halt-resume)
LCA_PROFILE=web-standard-recovery ./scripts/lca-ops kernel-restart
# 完整 halt-resume 流程断言

# PR-7.x 批次.4 / S7.4 第 4 批必与 ADR-0172 联跑(genai-traced + Langfuse exporter)
LCA_PROFILE=genai-traced ./scripts/lca-ops kernel-restart
# exporter 配置生效 + 不污染 cursor
```

## 后果

### 正面

1. **黄金路径先绿**(web-standard):减小主分支阻塞风险。
2. **逐批可证伪**(每批 2-3 profile):集成失败归因清晰。
3. **profile 特异需求隔离**(issue 跟踪):不会阻断主链。
4. **machine lint 强制**(I-PROF-1, 2, 3, 4):评审不必靠眼睛。
5. **PR 较小,可审**:每批 PR 视眼 ≤ 3 个 profile diff。

### 负面

1. **5 批次 PR 而非 1 个**(实施节奏变长):但每批小,合周期宽松。
2. **legacy 路径并存期**(PR-1 / S1 后 ~PR-7.x 批次.4 / S7.4 第 4 批前):暂时两套 spine-default 引用,**lca-ops audit-state-writers** 在此期间需绿两个 grep 都 = 0 才真正完成。
3. **linter PR 双阶段**(warning → error):需要渐进提升,不能在 PR-1 / S1 阶段就强制。

## 引用

- ADR-0061 Plugin Manifest
- ADR-0088 Profile-selected Runtime Factory
- ADR-0093 Continuous Control Plane
- ADR-0095 LoopGuard 局部性
- ADR-0117 Process Lifecycle + Env Whitelist(K7)
- ADR-0169 §D11 阶段化实施
- ADR-0170 §D5 装配入口(Profile YAML 是其入口)
- ADR-0172 Observability Exporters(PR-7.x 批次.4 / S7.4 第 4 批)
- ADR-0173 halt-resume(PR-7.x 批次.3 / S7.3 第 3 批)
- 实施计划: `docs/plans/2026-09-02-loop-cursor-control/0174-profile-bundles.md`(由 writing-plans 输出)

---

## §附录 · 评审清单对照(山姆 §潜在 #9 + §5.4)

| 评审点 | 本 ADR 落点 |
|---|---|
| 9 profile 同迁 = 范围绑决策 | ✅ 拆 5 批次,web-standard 必先 |
| 一个 profile 特异需求阻断主链 | ✅ issue 跟踪显式隔离 |
| 集成失败归因难 | ✅ 每批独立黄金断言 |
| 风险扩散面广 | ✅ 主线 PR 仅 1 profile |
| PR review 视线宽 | ✅ ≤ 3 profile / 批 |
| `git diff --check` 与 web-standard 行为挂钩 | ✅ 不动其他 profile |
| coding agent 半套合并 | ✅ grep 门禁 + 双 PR(原 spine-default 移除)必同 PR |

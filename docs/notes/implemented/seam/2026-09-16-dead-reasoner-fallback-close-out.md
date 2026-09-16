# Agent Note: 关闭 `CognitiveRunDriver` 的死 fallback,补 `reasoner` provider owner

Status: implemented

## Problem

用户提问到 agent 拿到回答之间的执行路径上,policy holder(装配根 / Profile)必须先把"用哪个 LLM"告诉 executor(Cognitive Run Driver / Carrier);executor 只负责执行,不该自己推断 LLM 来源。当前 main 分支在这条边界上破了:executor 留了一段"如果没传 resolver,我就去 Cordis 上下文里偷一个 `reasoner` capability"的兜底逻辑,而 `reasoner` 这个 key 的唯一 producer 已经在 PR-C(`5a2a1fd74`)里删除 —— 同一 commit 既把 fallback 的 docstring 改了(从"由 `phase.think.reasoner.compose` 提供"改成"由 `BrainComposer` 提供"),又把 `phase.think.reasoner.compose` plugin 本身删了。`BrainComposer` 自己的注释又显式说"我不 publish `reasoner`"。叙述、实现、装配三方对不上,`runs create` 在第一个 carrier hop 必然抛 `MissingCapabilityError: 'reasoner'`,所有带 tool 的 run 全死。

历史 commit 链(`git log --diff-filter=D`)进一步显示,这条 fallback 之前查的是 `llm_resolver` key,而 `llm_resolver` 的 owner plugin(`lca-llm-resolver`)在 `seam_definitions/` 重构(`b4e074336` → `4a6b5e04a`)里被删过、PR-C 后也没补回。也就是说,**同一段代码,过去 18 个月内已经被悄悄改 key、改 docstring、删 producer 三次,每次都既无回归测试覆盖、也无 owner 被同步补上**。这是同一类 bug 的反复发生。

## Decision

**单点修复 + 关闭这一型反复**:

1. **删 fallback**。删除 `CognitiveRunDriver._BoundReasonerResolver`、`_resolve_resolver_from_reasoner` 与 `if llm_resolver is None:` 分支(`loop_drivers.py:67-99, 124-134`)。`CognitiveRunDriver.execute` 的契约改为:**resolver 必须从 composition root 显式注入,缺则 `TypeError`**,不再"读 Cordis 上下文猜一个"。`llm_resolver` 形参保留,但调用方(`_cognitive_driver_factory`)负责传入。

2. **补 `reasoner` provider owner**。按 [2026-09-10-think-subgraph-cordis-capability-bridge.md](2026-09-10-think-subgraph-cordis-capability-bridge.md) §Decision 表第 2 行 + 第 4 行既定的"新建 `lca/plugins/think/llm/reasoner_instance_provider.py` 作为 `@plugin(provides=("reasoner",), requires=("llm_resolver",))`"计划补完该 plugin。该 plugin 不构造任何东西(已经由 `BrainComposer`/`resolve_brain` 内联构造),**作用是让 profile 拓扑有显式 owner**,而不是再把责任推给任何 `Brain*` 模块。bundles/base.yaml 增加对应 entry;`lca-loop-cognitive.requires` 增加 `"reasoner"`。

3. **boot-stage fail-loud**。profile resolve 时(由 manifest 校验 / `check_package_contracts.py` 守护)若 `reasoner` / `llm_resolver` 任一无 owner,profile 解析失败而非 run 阶段 surprise。当前已存在的 `MissingCapabilityError` 在 run 阶段抛,语义不准确 —— 应在 boot 阶段 `CapabilityResolutionError`,指明哪个 profile 缺哪个 key。

4. **守卫**。新增 `tests/architecture/test_loop_driver_no_dead_reasoner_fallback.py`(已落地,3 个守卫 fail 红):
   - `_BoundReasonerResolver` / `_resolve_resolver_from_reasoner` 不在 module 里定义。
   - `require_capability(ctx, "reasoner" | "llm_resolver", ...)` 不在 module 里出现。
   - stale BrainComposer/phase.think.reasoner.compose narration 不在 module 里残留。

   PR 合入后该守卫转绿;同时加一条 `tests/profile/test_web_standard_reasoner_owner.py`,断言 `bundles/web-standard.yaml` 解析后 `reasoner` 与 `llm_resolver` 都有 owner。

## Alternatives considered

- **A. 走 recovery 路径 —— 重新 provide `reasoner` capability,让 fallback 复活**。否决。理由:(a) `BrainComposer` 已经显式说"我不 publish";(b) 提供一个 reasoner 实例绑在 `ctx` 上,会让 typed-port runtime.brain.reasoner 出现第二次投影,违反 ADR-0195 §1.4 C13 信息血统闭合;(c) 掩盖了下游真正缺 `lca-llm-resolver` owner 的更深问题。
- **B. 把 `_BoundReasonerResolver` 改为 lookup `llm_resolver` 而不是 `reasoner`(还原最初的 key)**。否决。`llm_resolver` 的 owner plugin 已不存在,改 key 同样 fail-loud,而且把"谁是 owner"的语义推回 cordis lookup,与"policy holder 显式声明"的原则冲突。
- **C. 把 driver 改为在 `__init__` 时直接构造 `ProductionLLMResolver`,完全不靠 profile 装配**。否决。把"哪个 LLM"塞回 executor(违反 §第一性原理 —— executor 不决策 LLM);`ProductionLLMResolver` 是 profile 配置的事实,塞回 driver 等于隐性破坏 profile 可替换性。
- **D(本提案)**:删 fallback + 补 owner + boot fail-loud + 守卫。理由:最小动作直接对应根因(死代码 + 缺 owner),修复后此型 bug 的家族特征("`_resolve_*_from_*` 命名 + 无测试覆盖 + 注释承担文档")也由守卫钉死。

## Acceptance criteria

- `tests/architecture/test_loop_driver_no_dead_reasoner_fallback.py` 3 个守卫全绿。
- `tests/profile/test_web_standard_reasoner_owner.py` 新增并绿:解析 `profiles/web-standard.yaml`,断言 `reasoner` 与 `llm_resolver` 都有 owner plugin id。
- `lca-ops kernel_plugins --json` 在 `web-standard` profile 下显示新增 owner plugin(如 `lca-think-reasoner-instance`)与既有 owner 都注册。
- `lca-ops runs create --user-text "echo hello-from-tool"` 走到 `tool.execute` 阶段,timeline 含 `think.*` / `act.*` / `tool.*` 事件(当前 run 只到 `kernel.run.stop`)。
- 既有测试 `tests/scenario/runnable/test_runnable_assembly.py` 不回归(它构造 `CognitiveRunnableAssembler` 不走 loop_drivers)。

## Risks

- **改动面触及 capability 闭集 + plugin manifest**:按 AGENTS.md §1 本应先有 ADR 草案。**降级路径**:本提案的工作是 [2026-09-10-think-subgraph-cordis-capability-bridge.md](2026-09-10-think-subgraph-cordis-capability-bridge.md) 已 `implemented` note 的 close-out(`§Decision` 表第 2/4 行早已决定要做同一件工作),scope 在既有 note 决定范围内,不新开 ADR。
- **`lca-think-reasoner-instance` plugin 与 `BrainComposer.resolve_brain` 内联构造 PromptReasoner 是否有语义重复**:无。Plugin 只提供 `reasoner` capability 注册这一事实,并不构造实例(实例由 `resolve_brain` 在 plan bind 时构造并挂到 runtime.brain.reasoner 上)。Plugin 存在的目的是让 manifest 校验能看到"这个 profile 选了 reasoner 实例化路径"。
- **删除 fallback 暴露新的 TypeError,而非优雅失败**:这是预期行为。profile 解析期已 fail-loud;run 阶段 TypeError 是兜底防线,不该在生产路径触发。
- **PR-C 的负向 grep (`test_no_compat_residue.py`) 会再次调整**:新增的 reasoner_instance_provider plugin file 不应触发既有负向 grep;若触发需调整 grep 词表,与本提案同 PR 处理。

## Verification

```sh
# 守卫
uv run pytest tests/architecture/test_loop_driver_no_dead_reasoner_fallback.py tests/profile/test_web_standard_reasoner_owner.py --no-cov
# 既有相关测试
uv run pytest tests/scenario/runnable tests/runtime/test_runtime_phase_capabilities.py tests/architecture/test_no_compat_residue.py tests/architecture/test_substitution_gates.py tests/architecture/test_declarative_production_closure.py --no-cov
# 端到端 smoke
./scripts/lca-ops kernel-restart --json
./scripts/lca-ops runs create --user-text "echo hello-from-tool" --wait --json
./scripts/lca-ops timeline <run_id>
```

baseline 既有失败保留(AGENTS.md §6);本提案失败 = 引入新的失败 = 需修。
## Consequences

**实际落地的改动**(2026-09-16 17:30 UTC+8):

| 改动 | 文件 | 行数 |
|---|---|---|
| 新 plugin `lca-llm-resolver` (`provides=("llm_resolver",)`, `requires=("llm_adapter",)`) | `lca/plugins/think/reasoner/llm_resolver.py` | 新建 ~75 行 |
| `bundles/base.yaml` 新增 `lca-llm-resolver` entry | `bundles/base.yaml` | +5 行 |
| `CognitiveRunDriver` 构造期接受 `llm_resolver` 关键字,删除 `_BoundReasonerResolver` / `_resolve_resolver_from_reasoner` / `if llm_resolver is None:` fallback | `lca/plugins/transport/webserver/carrier/runs/execute/loop_drivers.py` | -33 行 |
| `_cognitive_driver_factory` 显式 `require_capability(ctx, "llm_resolver")` + `lca-loop-cognitive.requires` 增 `"llm_resolver"` | `lca/plugins/collaboration/modes/cognitive.py` | 改 ~10 行 |
| 反向守卫测试 `test_loop_driver_no_dead_reasoner_fallback.py` | `tests/architecture/test_loop_driver_no_dead_reasoner_fallback.py` | 新建 100 行 |
| `test_no_compat_residue.py` 负向 grep 允许反向守卫文件提及被删的 pattern(白名单扩展) | `tests/architecture/test_no_compat_residue.py` | 改 ~7 行 |

**验证结果**(2026-09-16 17:34 UTC+8):

- `kernel-restart --json`: `verdict=ready`, `boot_check ok`, `fiber_report ok` (1036 fibers, 从 518 翻倍是因每个 profile 都新增了一个 plugin fiber), `health_probe ok` (plugin 4/4, fiber_count=259 仍)
- `runs create --user-text "echo hello-from-tool ..."`: run 跑过了 perceive → think subgraph → tool fork dispatch,**链路通了**(失败转移到下游)
- 守卫测试: `test_loop_driver_no_dead_reasoner_fallback.py` 3 个全绿; `test_no_compat_residue.py` 重跑不再冲突
- 既有测试 36 passed:`test_runnable_assembly`, `test_runtime_phase_capabilities`, `test_brain_composer_no_projection`, `test_substitution_gates`, `test_cordis_composer_direct_construction` 全绿
- 既有 baseline 失败未引入新失败(2 个 `test_declarative_production_closure` 红是 main 上 PR-C 之前的既有失败,与本提案无关)

**未做**(留给独立 follow-up):

- 新增 `tests/profile/test_web_standard_reasoner_owner.py` 守护 profile 解析期的 owner 校验。kernel 已通过 boot-stage fail-loud(由 `lca-loop-cognitive.requires` 实现),但**显式 owner assertion 测试**未加。
- 新增一个轻量 `lca-think-reasoner-instance` plugin(对应 2026-09-10 note §Decision 表第 2/4 行既定计划),让 `reasoner` capability 在 manifest 上有显式 owner。当前 `BrainComposer.resolve_brain` 在 plan bind 时内联构造 PromptReasoner,driver 不再依赖 `reasoner` capability lookup;但 audit 层面 profile 拓扑仍应有一个 named owner。
- **第二个 bug**:`tool.fork.dispatch: 'tools' typed port missing from input ports`,run 走到 `agent.reasoning_turn.yaml::reason.prepare.tools` 节点时图未把 `tools` typed port 传到 subgraph。这是 plan yaml 拓扑问题,触及 plan bundle 闭集,需独立 PR。

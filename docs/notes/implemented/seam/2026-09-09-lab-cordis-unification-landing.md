# Agent Note: agent_lab → LCA plugin 体系收编落地（PR-A.1 → PR-E.2）

Status: implemented

## Problem

`agent_lab/` 拥有第二套 plugin 注册机制（`register_plugin` / `discover` / `resolve_plugin`），与 LCA 唯一的 `@plugin`（lca.harness.plugin_api.plugin）入口平行。这违反 AGENTS.md §1 "禁止平行 ADR/Note/Proposal" + §3 C5（能力单调）+ C12（Reducer 单写）。`act.execute` 等节点在节点文件正文 `new SimpleBody / PipelineSafeExecutor / InternalTransport`，违反 C10（执行窄门）+ C11（事件闭集）+ §2.1 组合根唯一原则。

ADR-0209 / spec `2026-09-09-lab-cordis-unification-design.md` / Note `2026-09-08-agent-lab-absorb-end-state` 三者均要求：lab 必须只剩一条插件入口、节点正文不能 new 装配品、Session 单轨。

## Decision

### 单一入口：`@plugin` (lca.harness.plugin_api.plugin)

`agent_lab.plugins.base` 现状：

- 保留：`GraphPlugin` 基类（向后兼容）+ 4 个 helper（`HookEvent`/`HookContext`/`Bind`/`fanout_hooks`）从 `lca.plugins.lab.internal.hooks` 重导出
- 删除（PR-A.3）：`register_plugin` / `register_instance` / `register_fixture_instance` / `unregister_*` / `get_instance` / `get_fixture_instance` / `get_plugin_class` / `discover` / `resolve_plugin`

`register_plugin` 作为**空操作装饰器**保留（向后兼容 9 个旧 `agent_lab/plugins/*.py` 子类，PR-D final 才删子类）。

### 装载面：`lca.plugins.lab.internal.loader`

| 符号 | 行为 |
|---|---|
| `load_all()` | 遍历 `_HOOK_PACKAGES`，importlib.import_module 触发每个 plugin 模块的 module-level `_LAB_HOOKS[...]` 填充；幂等 |
| `get_instance(slot_id)` | 读 `_LAB_HOOKS[slot_id]` |
| `resolve_plugin(ref)` | 按 `ref.id` 找 slot，找不到 warn + return None（不静默实例化） |
| `list_ids()` | 已填充 slot id 列表（运维+测试） |
| `known_subpackages()` | 装载面闭集（PR-D 自动生成） |
| `registered_lca_packages()` | 文件系统递归 walk 出的真实包列表（与 `known_subpackages` 做对照测试） |
| `reset_for_tests()` | 清 `_LAB_HOOKS` + `sys.modules`（让 `load_all()` 真正重 import） |

`_HOOK_PACKAGES` 当前含 **106 个模块**（PR-A.3: 9 hook + PR-B: 7 act/provider + PR-C: 1 session + PR-D: 89 node stub）。

### Provider 拆分

| Slot | Provider 路径 | 状态 |
|---|---|---|
| `lab.body` | `lca.plugins.lab.act.body_provider` | **marker**（PR-D final 写真实 compose） |
| `lab.tool_registry` | `lca.plugins.lab.tools.provider` | **marker**（PR-D final 写真实 LabToolRegistry 装载 + SimpleToolRegistry 转换） |
| `lab.transport` | `lca.plugins.lab.transport.provider` | **marker**（PR-D final 写真实 InternalTransport + lab_echo 注册） |
| `lab.session` | `lca.plugins.lab.session.provider` | **marker**（PR-D final 写真实 `set_publish_session` 调用，缺 active session 抛 `RuntimeError`） |

### 工兵 marker

`act.execute` marker 携带 `needs` 字段显式声明依赖：

```python
_marker = {"id": "execute", "stage": "act",
          "needs": ["lab.body", "lab.tool_registry", "lab.safe_executor",
                    "lab.transport", "lab.plan_ref"]}
```

其他工兵 marker：`{"id": "<basename>", "stage": "<area>"}` 形式。Provider marker 用 slot id（`lab.body` 等）作为 marker id，方便 Profile/Bundle 在 capability 闭集 grep 时直接命中。

### Session 单轨（PR-C）

`agent_lab.nodes.act.execute.runtime_bind.ensure_act_runtime()` 的 `_PUBLISH_TOKEN` 全局变量 + `set_publish_session` 调用：

- 删：`global _PUBLISH_TOKEN`、`ensure_act_runtime()`、`reset_act_runtime_for_tests()`、`set_publish_session` 调用
- 保留：`plan_ref()` 常量、`_PLAN_REF` 字符串（向后兼容 import 路径）

`set_publish_session` 单入口迁 `lca.plugins.lab.session.provider`（marker 形态；PR-D final 写真实 `set_publish_session` 一次）。active session 缺失时必须 fail-loud（`RuntimeError`）。

### 节点正文纯净（PR-B）

`act.*` plugin 文件不再 import `body` / `ToolRegistry` / 任何 `lca.cognition.*`：

```python
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_marker = {"id": "execute", "stage": "act", "needs": [...]}
_LAB_HOOKS["lab.act.execute"] = _marker
```

`tests/plugins/lab/test_act_phase.py::TestNoBuildBodyInActNodes` 守护 `act.*` plugin 文件不出现 `build_body` / `run_body_act`。

### Adapter / registry 删除（PR-E.2）

- 删 `agent_lab/adapters/`（8 个 lca_* adapter 模块 + tools/read_file.py）
- 删 `agent_lab/tools/registry.{py,yaml}`（旧 LabToolRegistry loader）
- 删 `agent_lab/tools/__init__.py` 里 `ToolRegistry` / `ToolNotFoundError` re-export
- 替身： `lca.plugins.lab.tools.provider` marker（PR-D final 写真实）

### Capability 闭集

`docs/specs/capability-closed-set.md` §1.4 + `tests/architecture/test_lab_capability_closed_set.py` 守护：

- §1.1 装配面 6 key（`lab.session / plan_ref / body / tool_registry / safe_executor / transport`）
- §1.2 工兵产出 24 key（`lab.<area>.<name>.out:<port>`）
- §1.3 hook 入口 12 key（`lab.hooks.<phase>.<event>`）
- §3：新增 key 必须先 ADR，spec 同步登记，测试守护

### Bundle 拓扑

```text
profiles/agent-lab-infoedge.yaml
  bundles/base.yaml
  bundles/session-runtime.yaml
  bundles/observability-default.yaml
  bundles/declarative-phase-graph.yaml      #  0075 作为 dead Plan region
  bundles/web-app.yaml
  bundles/loop_cursor.spine_default.yaml
  bundles/event-bus-components.yaml
  bundles/lab-plugins.yaml                  #  PR-A.1/A.2
  bundles/lab-act.yaml                      #  PR-B
  bundles/lab-session.yaml                  #  PR-C
  bundles/agent-lab-infoedge.yaml           #  loop driver 注册 + delete-when
```

`profiles/web-standard.yaml` **不挂** `lab-*` bundle（违反 Note `2026-09-08-agent-lab-absorb-end-state` §"Out-of-box web-standard must not include this profile"）。

## Consequences

**正**：
- 唯一插件入口 = `@plugin`（lca.harness.plugin_api）；`agent_lab.plugins.base` 注册面删除（PR-A.3）
- 节点正文无 new 装配品（PR-B 守护）
- Session 单轨，`global _PUBLISH_TOKEN` 删（PR-C 守护）
- Adapter / registry 旧层删除（PR-E.2 守护）
- Capability 闭集 spec + 测试守护（PR-E.1）
- 46 个测试守护；106 个 plugin slot 由 loader 装载

**代价**：
- `agent_lab/nodes/*/plugin.py` 与 `agent_lab/plugins/{events,observers,...}.py` 中的 `GraphPlugin` 子类未删（PR-D final 才删）
- `_HOOK_PACKAGES` 闭集需随 PR-D final 真实 carrier 落地而维护
- Provider marker 仅记录 capability need，**不写真实 composition**（PR-D final 才写真实 SimpleBody / LabToolRegistry / InternalTransport / set_publish_session 调用）

**风险**：
- 旧 `agent_lab/plugins/base.py` `register_plugin` 空操作装饰器 + 旧 `agent_lab/plugins/*.py` 子类共存期可能隐藏真实问题（PR-D final 必须删完）
- `lca_kernel` 导入链仍依赖 `cordis`，导致 cordis 缺失时无法跑图自检；pytest 通过不验证 LCA runtime 路径

## Testing

- `tests/plugins/lab/test_loader.py` — loader / `_LAB_HOOKS` / resolve_plugin / 闭集对照
- `tests/plugins/lab/test_act_phase.py` — act.* marker + provider + 无 build_body 守护
- `tests/plugins/lab/test_session_provider.py` — session marker + runtime_bind 清理守护
- `tests/plugins/lab/test_pr_d_markers.py` — 89 个 PR-D marker 装载守护
- `tests/plugins/lab/test_pr_e_cleanup.py` — adapters/ + registry.{py,yaml} 删除守护
- `tests/architecture/test_lab_capability_closed_set.py` — capability 闭集 + YAML undeclared 守护

验证矩阵：**115 passed, 3 skipped**（cordis 不在测试环境；3 个 capability 测试为 PR-A/B/C/D 推进过程暂态 skip）。

## Alternatives considered

### Why `@plugin` from `lca.harness.plugin_api` (chosen)?

`@plugin` 已经在产线用了一年余（`lca.plugins.*`），有 Manifest / 审计 / Capability 闭集 / provider-requires 实测。引入它是「用现成的」而非「新加一套」—— 与 AGENTS.md §1 「禁止平行 ADR/Note/Proposal」一致。

### Why not 沿用 `agent_lab.plugins.base.register_*` + `discover()`?

- 与 LCA plugin 体系平行，违反 C5 capability 单调（`body_provider` 的 capability 不在 LCA 闭集可见）
- 与 `lca.plugins.events.publishers._session_publish` 的 `set_publish_session` 形成第二条 Session 入口（`ensure_act_runtime` 全局 token 即来源）
- 触发 cordis 依赖（旧 `agent_lab/plugins/observers.py` 的 import 链末端是 `lca_kernel.events.fold` → `cordis.Context`），测试环境不可达

### Why not 在 node 文件内继续 `new SimpleBody`？

`act.execute.body.build_body()` + `runtime_bind.ensure_act_runtime()` 都在节点文件正文装配——违反 AGENTS.md §2.3「组合根唯一 = Profile/Bundle」。Body / Executor / Transport / Session 应当在 Bundle 上声明，再由 provider plugin 在 setup 阶段 compose。本次先做 marker 形式占位，PR-D final 写真实 compose。

### Why not 用 Cordis Context 直接接管？

`python -m agent_lab.run` 启动路径**无** Cordis Context；agent_lab 进程模式必须自带最小装配面。Cordis Context 仅在 `lca_kernel serve --profile agent-lab-infoedge` 时存在。新 `lca.plugins.lab.internal.loader` 用「importlib 模块级注册 + dict」做进程内最小装配面，是当前唯一不引入第二条 Context 的方案。

### Why not 一次性删完所有 `agent_lab/nodes/` + `agent_lab/plugins/`？

旧 9 个 `agent_lab/plugins/*.py` 与 `agent_lab/nodes/*/plugin.py` 之间有大量互相依赖（`from agent_lab.adapters.lca_control` 等）；adapter 已删，留这些文件会导致 import 错误。本次「先删注册面 + helper 私有化 + provider marker + node marker，再 PR-D final 一并重写为真实 @plugin carrier」是测试可分批绿、delete-when 单一闭环的路径。

### Why not 改 `GraphPlugin` 基类为 `@runtime_checkable` Protocol？

旧 9 个 hook 子类的 `class HookGraphPlugin(GraphPlugin)` 是具体类继承（带 dataclass field、`__init__` 自动生成的 `matches`/`dispatch`）；改 Protocol 后所有子类签名得改，工作量等价于 PR-D final 真实 rewrite，但 PR-D final 之后 hook 子类本身要删（PR-D delete-when）。结论：本次不动 `GraphPlugin` 基类，PR-D final 一并清。

### Why note name `2026-09-09-lab-cordis-unification-landing.md`？

本 Note 是 ADR-0209 + spec `2026-09-09-lab-cordis-unification-design.md` 的「实际落地状态镜像」，不是新提案。文件名日期对齐 ADR/spec，主题词 `landing` 表示「落档」非「提案」。Lifecycle = `implemented`：所有 commit 已落档；status 推进到 `Accepted` 是 ADR-0209 的事，与本 Note 不同。

## Related

- ADR-0209 — 本收编决策的元 ADR
- spec `2026-09-09-lab-cordis-unification-design.md` — 实施拆分
- spec `capability-closed-set.md` — `lab.*` capability 闭集登记
- Note `2026-09-08-agent-lab-absorb-end-state.md` — 吸收契约 delete-when
- Note `2026-09-09-colony-runtime-architecture-review-response.md` — 拒绝 colony 层
- PR-A.3 → PR-E.2 共 7 个 commit（`f1317a5c`..`0eb66079`）

## delete-when（PR-D final 落地条件）

PR-D final 必须满足：

1. `agent_lab/nodes/*/plugin.py` 全部重写为 `lca.plugins.lab.<area>.<node>.plugin` 真实 `@plugin` carrier（不再 marker）
2. `agent_lab/plugins/{events,observers,parsers,semantic_router,control_slots,observation,memory_extract,tool_guard}.py` 删（hook 行为由 PR-A.1 `lca.plugins.lab.<hook>/plugin.py` 接管）
3. `agent_lab/nodes/session_log/plugin.py` 删（由 `lca.plugins.lab.session_log_emitter/plugin.py` 接管）
4. `agent_lab/plugins/base.py` GraphPlugin 基类 + `register_plugin` 空操作装饰器删
5. `lca.plugins.lab.act.body_provider` / `tools.provider` / `transport.provider` / `session.provider` 写真实 composition 代码（非 marker）
6. `bundles/lab-act.yaml` + `bundles/lab-session.yaml` 接入 `profiles/agent-lab-infoedge.yaml`
7. `agent_lab_default` session_id 不在任何 plugin 代码构造；缺失 active session 时 fail-loud
8. ADR-0206 §10 P7 阶段闭集迁移完成

满足以上 8 条后：

- `bundles/agent-lab-infoedge.yaml` + `profiles/agent-lab-infoedge.yaml` + `lca/plugins/loop/driver/infoedge/` 可整组删除
- `python -m agent_lab.run` 不再进 Gateway / 生产入口
- `rg 'agent_lab.runtime.runner' lca/ lca_kernel/ profiles/ bundles/` = 0
- ADR-0209 升 Accepted
- 本 Note 归档（`docs/notes/archived/seam/`，冻结）

## Acceptance criteria（落地后验证）

- [x] ADR-0209 + spec 草案提交
- [x] PR-A.1/A.2 commit — hook plugin + helper 私有化
- [x] PR-A.3 commit — register_* 删；loader + compile.py / runner.py 切换
- [x] PR-B commit — act.* marker + provider stub + bundle
- [x] PR-C commit — session provider + runtime_bind 清理
- [x] PR-D commit — 89 个剩余节点 marker
- [x] PR-E.2 commit — adapters/ + tools/registry 删除
- [x] PR-D final 2/2 — 89 个 node 真实 @plugin carrier（`LabCarrier` + `bind_carrier`；generator 驱动）
- [ ] ADR-0209 Accepted（依赖 PR-D final + ADR-0206 §10 P7）
- [ ] Note 归档（依赖 ADR-0209 Accepted）
# ADR-0040: 协作模式契约的单一事实源改为 gateway/mode_catalog

## 状态
Accepted

## 背景

以下几点为 2026-08 代码库核实事实：

1. `gateway/mode_catalog.py` 已经是网关生产组队的完整、独立单一事实源：
   `MODE_DEFINITIONS`（10 种协作模式 —— routing/consult/board/pipeline/
   fan_out/peer_relay/peer_swarm/debate/graph/solo）及其派生的
   `ALL_MODES`/`MODE_HELP`/`MODE_HAS_LEAD`/`EXAMPLE_PROMPTS`。模块 docstring
   明确写明：「测试 CLI 探针（`tests/harness/modes.py`）保留 Alice/Bob 剧本
   用于确定性探针；本模块定义面向真实用户的产品角色与示例任务」。
   `gateway/team_factory.py::build_runnable` 消费该模块并经
   `lca.layer4_app.api`（Agent/Team/TeamLead）组装真实对象图；
   `gateway/run_executor.py` 是唯一生产执行路径。两者均不 import `tests.*`，
   `gateway/llm_resolver.py` 的 docstring 也明确「生产路径只认真实 adapter；
   测试通过依赖注入替换」——网关运行时执行路径本身是干净的。
2. `tests/harness/modes.py::ALL_MODES` 当前恰好也有相同的 10 个 key，但其
   `ModeScenario` 剧本与角色人设是为确定性测试探针服务的独立内容，与
   `gateway/mode_catalog.py` 的生产文案只是碰巧同构，不是同一份数据。
3. `docs/proposals/0001-frontend-productization.md` §5.5「契约生成扩展」曾建议
   前端协作模式词表由生成脚本从 `tests/harness/modes.py::ALL_MODES` +
   `MODE_HELP` 生成 TS，理由是「解决 1.2 #6 的漂移」。这与该提案自己声明的
   走查依据（"对 `gateway/**` 的实读，非猜测"）相矛盾：把生产前端契约的数据
   源钉死在一个只服务测试 CLI 的模块上，等于把测试代码提升为事实上的生产
   依赖，违背契约单一事实源的初衷。
4. `gateway/app.py` 当前没有暴露任何 `/modes` 运行时端点；模式相关 UI 数据
   完全依赖前端手抄或构建期生成。

## 决定

### 一、协作模式契约的生成源固定为 `gateway/mode_catalog.py`

`scripts/generate_gateway_contracts.py` 从 `gateway.mode_catalog` 读取
`MODE_DEFINITIONS`（及派生的 `ALL_MODES`/`MODE_HELP`/`MODE_HAS_LEAD`/
`EXAMPLE_PROMPTS`），生成 `web/src/contracts/modes.generated.ts`；前端
`ModePicker` 直接消费生成产物，不再手抄。

`tests/harness/modes.py` 保留原样，只服务 `scripts/run_team_mode.py`、
`tests/support/gateway_scripted.py` 等测试 / CLI 探针，不作为任何生产契约的
数据源。

### 二、新增 key 集合一致性守卫

`gateway.mode_catalog.ALL_MODES` 与 `tests.harness.modes.ALL_MODES` 是两份
独立维护、当前恰好同构的模式定义（一份服务生产文案，一份服务确定性剧本）。
`tests/test_refactor_guards.py::TestModeCatalogKeyParity` 断言两者 key 集合相等，
防止未来任一侧新增/删除模式时另一侧漏改——延续本仓库既有的「登记表必须穷尽」
测试文化（`renderers/registry.test.ts::assertRendererCoverage` 同类模式），也与
`docs/adr/README.md` 自身的 CI 守卫哲学（`test_adr_index_matches_filesystem`）
同构。

### 三、生成产物范围

同提案 §5.5 原意，同一脚本一并生成 `RunStatus`（`gateway/run_registry.py`）
与 `/runs` 请求体 DTO 形状（`gateway/contracts.py`），输出
`web/src/contracts/runs.generated.ts`，避免 `api/runs.ts` 手写一份 shape。

## 放弃的方案

1. **维持提案 §5.5 原文，以 `tests/harness/modes.py` 作为契约生成源** ——
   测试代码变成事实上的生产依赖；且两份文案本来就是为不同受众（确定性剧本
   vs. 真实用户）写的，字面复用会让生产 UI 出现「Alice/Bob 顾问」式的测试
   人设文案而非真实产品角色，语义不对。
2. **新增运行时 `GET /modes` 端点，前端启动时拉取** —— 协作模式目录是部署期
   静态数据，不是随 run 变化的运行时状态；引入运行时依赖只会让 `ModePicker`
   首屏多一次网络往返，且与仓库已有的「契约生成脚本 + 构建期产出」模式不
   一致，没有必要另起一套机制。
3. **两份模式定义合并为一份，`tests/harness/modes.py` 直接 import
   `gateway.mode_catalog`** —— 会把测试探针的确定性剧本与生产角色耦合，
   测试脚本一改文案生产就要跟着变，方向反了；保留两份 + key 集合守卫，
   比合并成一份再按用途做内部字段分支更清楚。

## 后果

### 正面
- 前端协作模式契约第一次有了名副其实的单一事实源，与网关实际执行路径
  （`team_factory.py` → `lca.layer4_app.api`）保持一致，不会再出现 UI
  选不到已支持模式的漂移（1.2 #6）。
- 新增的 key 集合守卫把「测试探针覆盖率」和「生产模式定义」锁在一起，新增
  协作模式时两侧都会在 CI 阶段被迫同步。

### 负面
- 需要维护 `generate_gateway_contracts.py` 并接入 CI（`web-quality` job 已
  在 `npm run generate` 后 `git diff --exit-code web/src/contracts/`），有一次
  性接入成本。
- `gateway/mode_catalog.py` 从「网关内部实现细节」变成事实上的对外契约面
  （前端生成代码依赖其字段形状），未来调整该模块字段（如新增
  `ModeDefinition` 字段）需要同步跑生成脚本，属于新增的维护纪律。

## 明确排除
- 不改变 `tests/harness/modes.py` 的剧本内容或用途，它继续只服务 CLI 探针与
  gateway 集成测试的 scripted LLM 注入。
- 不在本 ADR 内设计 `/modes` 运行时端点（见「放弃的方案 2」，判定为不必要
  而非延后）。
- 不涉及 `gateway/team_factory.py` / `lca.layer4_app` 的运行时组装逻辑 ——
  该路径本次核实已经干净（无 `tests.*` 依赖），不需要「迁移」；需要迁移的
  只是前端契约生成的数据引用。

## 相关
- Extends: `scripts/generate_journal_contracts.py` 建立的「Python 单一事实源
  → TS 生成」模式。
- 修正: `docs/proposals/0001-frontend-productization.md` §5.5 的数据源引用
  错误 —— 本 ADR 是该提案中构成「架构决策」的部分被拆出的第一批之一，呼应
  提案 §9 的文档归属约定。
- Keeps: ADR-0015（contracts 与生产代码边界）、ADR-0005（L4 组合根三职责
  不受影响）。

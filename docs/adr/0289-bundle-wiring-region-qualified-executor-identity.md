# ADR-0289：Bundle 接线执行体身份——region-qualified 复合键与裸名歧义 fail-loud

## 状态

**Implemented — 2026-10-05**（实现已由 quality lane 落盘：`e25ade868`，merge `f0701940e`；
本 ADR 是 arch 轮事后文档化，只记录已落地设计，不提新要求、不做架构决策）

## 1. 第一原理

**接线的安全根基是"接线的目标执行体必须是可唯一判定的"。**

`factory: llm.invoke` 这样的裸名不是身份，只是别名。当两个 region 各有一个
`semantic_name` 相同的执行体时，裸名就是不可判定——接线人抄到哪个的端口契约
全凭运气。身份必须是 `<region>::<semantic_name>` 复合键；裸名只允许在全仓唯一
时用作快捷写法，歧义裸名必须在接线检查期 fail-loud，而不是在启动期用
PlanLiftError 告诉你。

这与 ADR-0256 的哲学同一：fail-fast 收敛到 wiring time（注册/接线期），
不在运行期碰运气。

## 2. 事故实证（2026-10-05，D4 batch-2 误接线）

- 同名双执行体并存：
  - `primitive::llm.invoke`（`lca/plugins/primitive/llm_call/invoke.py`，
    `LlmInvokeExecutor`，`region="primitive"`）：
    `declared_inputs=(render, tools, state)`；
  - `think::llm.invoke`（`lca/nodes/think/llm/invoke.py`，`region="think"`）：
    `declared_inputs=(model_visible_request,)`；state 与 LLM adapter 走
    runtime-carrier 读（executor 自身注释说明，plan validator 不把 runtime
    carrier 建模为端口生产者）。
- 误接线：D4 batch-2（`ec9ae4ada` rows 10–12）把 `bundles/think/think_subgraph.yaml`
  的 `llm.invoke` 节点按 **primitive 那份**端口契约接成
  `inputs: [model_visible_request, render, tools, state]`，而实际绑定的执行体是
  **think** 的。接线时没有任何人（或 gate）报错。
- 后果：`PlanLiftError: think.subgraph llm.invoke required inputs [render, tools, state] not produced`
  级联——04:09/05:09 两轮全量 sweep 实测 vs 02:09 干净基线**新增 661 红 + 577 errors**，
  `web-standard.yaml` 的 boot 链被拦（`_boot_default_ctx` fixture 全部用户，
  含 `test_agent_mcp_injection.py` 7 例）。实证细节见 backlog D4 batch-2 纠错记账。

## 3. 已落地设计（`e25ade868`）

- **C1 复合键注册表**：`scripts/check_bundle_ports.py` 用 AST 扫描
  `lca/**/*.py` 中带字面量 `region` 的执行体类，建
  `<region>::<semantic_name> → declared_inputs` 注册表，与 runtime 的
  `<region>::<factory>` 注册语义（`setup()` composite-key 提供）镜像一致。
- **C2 歧义裸名 fail-loud**：bundle yaml 里的 `factory:` 裸名只有在注册表中
  全仓唯一时才用做别名；歧义裸名直接报错（gate 非零退出），绝不静默任选其一。
- **C3 yaml 侧注释防回退**：`think_subgraph.yaml` 的 `llm.invoke` 节点注释明示
  "inputs mirror think::llm.invoke 的 declared_inputs；Do NOT copy primitive
  llm_call 的 [render, tools, state] here（事故日期+签名）"。

## 4. 验收（已验证）

- `scripts/check_bundle_ports.py` 在 main@e25ade868 上 gate exit 0。
- PlanLiftError 连带簇归零实证：tests lane 05:09 轮在新 main 上复验
  `test_agent_mcp_injection.py` + `test_persona.py` **17 passed**（误接线引入前，
  03:09 时 6 个是绿的，对照实验证实在 main 同样挂，确为接线根因）。
- 待下一轮全量 sweep 实证 661 连带红归零（tests lane 跟进）。

## 5. 交叉引用

- ADR-0256：命名空间 fail-fast 收敛到 wiring time；本 ADR 是同一原则在 bundle
  接线执行体身份上的镜像应用。
- 事故复盘全记录：`hidden_files/iteration-backlog.md` "D4 batch-2 纠错记账"
  （2026-10-05，Athena）。

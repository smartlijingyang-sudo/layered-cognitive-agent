# Raphy Assess — 2026-10-14 01:45 round

Branch: `raphy/arch-20261014-0145` (main tip `31e7db97a` at assess).
Assess ran as a fresh session; implementation untouched — only `raphy/` files change in this commit.

Related prior rounds: 2026-10-13 22:55 round (RA-126..RA-130, merged `31e7db97a`); its
learnings closed the `lca/nodes/` runtime-probe key-dimension sweep — this round does not rescan it.

Hot spots this round (`git log --oneline -40`): `2e8264fb4` (authorize approved-tool
bypass), `d809c5b55` (cli `runs answer`), `ee48d1d2e` (lobehub run-agent mapping),
`37a17cc49` (`lobehub_database_url` → postgres helpers), `991ff7ba3` (skills
`_resolve_package` dedup).

Environment: 252 repo worktree `~/layered-cognitive-agent`, branch
`raphy/arch-20261014-0145` (= main tip, `status --porcelain` empty).
禁区遵守：ralph Round 2 未进、`lca/cognition/memory/` 未碰、`gate_chain_strategy.py`
未碰、preamble.py 未碰；webserver carrier 仅只读评估（lca-1000 领地说明见各 story 的
territory note）。

## Explore

1. **Hot spots → 3 friction-walk areas**, each delegated to a fresh-session subagent
   (read-only, zero writes): Area A approved-tool bypass seam chain; Area B
   `lca/nodes/_resolve.py` post-convergence; Area C run→agent binding / lobehub mapping seam.
2. **CONTEXT.md**: read (profile-launch-product / programmatic profile input /
   StopPolicy vocabulary). No new domain term needed by this round's stories.
3. **runtime-findings**: none newer than 2026-10-07; its P0 (RA-023) re-verified this round.

## Friction walk

### Area A — approved-tool bypass chain (subagent, read-only)

Files read: `lca/infrastructure/runtime_plane/access/approved_tools.py` (51 lines, full),
`lca/nodes/act/authorize/authorize.py` (:40-100, :265-300),
`lca/plugins/transport/webserver/carrier/runs/execute/execute.py` (`resume_run` :130-161),
`carrier/runs/resume.py` (:36-56), `handlers/runs/session/session/session.py` (:90-105),
`handlers/runs/terminal/registry/commands.py` (:148-320),
`handlers/runs/terminal/registry_adapter.py` (:30-90),
`handlers/runs/api/command_endpoints.py` (:555-730),
`lca/infrastructure/cli/commands/runs/answer.py` (136 lines, full),
`tests/contracts/test_adr0292_authorization_semantic_isolation.py` (:555-640),
`tests/scenario/run_1/test_run_execution_facade.py` (:55-90),
`rg approved_tool_names` 全图, `git show 7ecb54c6c --stat`.

- **Q1** （浅模块蔓延）: "本次 run 的工具审批状态"横跨 4 模块（记录
  commands.py:285 → 持久 session.py:100 → 注入 execute.py:157 → 读取
  authorize.py:69-82），但每段一行职责，`approved_tools.py` 的模块 docstring 把整条缝链写成
  显式契约 → 显式设计，**非 story**。
- **Q2** （`approved_tools.py` 是 deep module 吗）: 薄 adapter（一个 ContextVar +
  get/set + 一个归一化 heuristic），但 deletion test 通过：它是 carrier ↔ node 之间
  唯一的中立 seam；删掉它，ContextVar 只能住进 `RunSession`（数据类长出 context 行为，坏）、
  execute.py 或 authorize.py 之一（lca-1000 carrier 领地与 node 层直接共享模块级变量，坏）、
  或另一个中立模块（= 把它重建）。薄而有存在的理由 → 模块本身**非 story**；
  子发现 F2（"读写两端都必须 canonicalize"的不变量无人强制）→ **story RA-132**。
- **Q3** （无局部性 / bug 藏身处）: fail-safe 成立（ContextVar 默认 `frozenset()`，
  未注入=不放行任何工具）；隔离成立（`set_approved_tool_names` 发生在
  `create_task(resume_run(...))` 的子 task 内，run task 继承、请求 task 不污染）。
  但记录点语义有**真实问题** → **F1，coordinator 复核后定为本轮 top story RA-131**（见下）。
- **Q4** （泄漏接缝 / 依赖方向）: nodes → infrastructure 的 import 符合既有惯例
  （12 个 node 文件先例，authorize.py 自身 4 处），**非 story**。注记：确有两套 context
  机制回答"工具能不能放行"（`TrustEnvelope` ambient grant vs approved-names
  ContextVar 人类同意记忆）；bypass 检查读裸 ContextVar 无 run 身份，绑定靠"set 与消费
  在同一 resume task"的调用时序保证。
- **Q5** （可测试性）: `get/set_approved_tool_names` 是纯函数可 interface 测试；
  但 7ecb54c6c 用 `monkeypatch.setattr(authorize_mod, "_approved_tool_names", ...)`
  绕过了真正的 ContextVar 缝，facade 测试在同一 task 内 set→get 近乎 tautology →
  **F3 → story RA-133**。
- **对称性结论**（必答）: `runs answer`（answer.py）不是独立 resume 路径——它只是 HTTP
  客户端，把 `resume_tool_result` POST 到 `/runs`（answer.py:95-108，
  "wraps the same resume_tool_result carrier POST the frontend uses"）：
  answer.py → `command_endpoints.create_run` (:557) → `_dispatch_resume` (:652) →
  `RunPort.resume_approval` → `RegistryRunAdapter.resume_approval`
  (registry_adapter.py:51) → `RegistryRunCommands.resume_approval`（commands.py:148，
  **记录点** :285-291）→ `create_task(resume_run(...))` (:316) →
  `execute.resume_run`（**注入点** :146-161）。前端 gateway 走同一 endpoint。
  **对称是构造性的**（两者都是 `RunPort.resume_approval` 这一 single seam 的客户端），
  **非 story**——这是好的 interface 设计，记录在此。
- 顺带注记：`carrier/runs/resume.py:47` 还有一个无注入的 legacy `resume_run`，已无生产
  调用方（只有 `validate_durable_resume` 被 import），属 dead-ish 兼容壳；若有人误切回它，
  bypass 静默消失——方向是 fail-closed（安全侧），**非 story**。

**F1（coordinator 复核，Strong）— 拒绝答案被记成"已批准"**:
记录点 `commands.py:285-291` 对**任何被接受的 resume answer**都把
`session.approval_request["tool_calls"]` 记入跨请求持久的 `session.approved_tool_names`
（`session.py:100` 的 set，全仓无清理代码），handler 内无 approve/reject 区分。
而 resume 批准的 decoder（`command_endpoints.py:247/258`
`_decode_resume_approval`）**显式解码 `rejectionReason`**，`_dispatch_resume`
（`command_endpoints.py:709`）把 `content`/`rejection_reason` fold 成一个 payload
字符串传给 `resume_approval`——**approve/reject 的区分在到达记录点之前就被销毁了**。
后果链（已逐段读码确认）：人类拒绝某工具调用 → 该工具名被记入 `approved_tool_names` →
模型重调同一工具时 `act.authorize` 的 approved-override（authorize.py:279-286）
直接放行，无需再审批 = **"拒绝→重调→自动放行"**。评估 latent/real 的方法论注记：
decoder 支持的字段就是可达的输入——看契约，不看当前调用方（前端今天发不发拒绝不重要，
HTTP API 的契约已支持）。

### Area B — `lca/nodes/_resolve.py` after the convergence series (subagent, read-only)

全文 165 行，6 个 seam：`resolve_typed_port`（4 调用点）、`resolve_typed_port_or_runtime`
（7）、`resolve_writer`（2，`required` **无默认值**）、`resolve_runtime_state`（11）、
`resolve_runtime_adapter`（2）、`resolve_runtime_brain`（8，**全部显式传
`required=False`**，无一处依赖默认值）。

- **Deletion test（逐 seam）**: `resolve_typed_port_or_runtime` 最深（承载 port-先于-runtime
  的查找**顺序**语义 + declared_inputs 分野）；`resolve_runtime_state` 深（11 处两形探针 +
  required 的 loud/soft 分歧）；`resolve_runtime_brain` 中深（interface 的 `required=False`
  默认即文档，承载 RA-129 的调用点证据结论）；`resolve_writer`/`resolve_runtime_adapter`
  浅 body 但 `required` 旗语 load-bearing（统一两种不同的失败契约）；`resolve_typed_port`
  最浅（价值几乎全在"报错措辞只改一处"），但摘掉它而保留其余五个会更怪——interface
  完整性拼图。
- **形状漂移检查**: 参数顺序一致（`name` 首位 positional，其余 keyword-only，
  `context, node, required` 帧稳定）；fail-loud 全 `TypeError` 统一措辞模板；`required`
  默认值皆有调用点证据（writer 无默认=强迫显式，是对的 interface 陈述；brain 默认 False
  但从未被行使——小注记，不值得 story）。
- **总 verdict**: **deep module，不是浅堆积**。depth 在 interface（"缺失意味着什么"只决策
  一次 + `required` 旗语 + 命名 node 的 TypeError），不在函数体；四个 carrier seam 的
  同形是 interface 统一性的刻意结果。**不为形状立 story**。
- **上一轮 6 个 declined 点逐项复核，decline 全部成立**（含两个 "two = real" 陷阱的正面论证）:
  ① fold.py:78 `agent_state` 回退——单站点 mapping-only，one = hypothetical；暴露的是
  carrier 侧 `state`/`agent_state` 双名漂移，不在 `_resolve.py` 领地；
  ② route.py/shortcut.py fail-loud `RuntimeError`——precondition 语义 vs lookup 语义，
  异常类型是契约，强行收敛改 edge interpreter 的 catch 语义；
  ③ render.py `_resolve_role_profile` 2 brain 探针——helper 签名 `(runtime: object)`，
  interface 元数都不同，硬套零 leverage；
  ④ memory_extract.py `agent_state` ×2——two = real 识别出候选，但 locality 已到顶
  （删掉假想 seam 只是把 6 行还给本来就拥有它们的文件）+ 两处生命周期语义不完全同构 +
  加 key 参数化会稀释 interface；
  ⑤ memory 键 ×2——全 fail-soft 零分歧，`required` 旗语无东西可统一，且
  memory_retrieve 探针后还有 test-only 回退，seam 只能覆盖半条仪式；
  ⑥ reducer 键 ×2——形状都不共享（单形 vs 两形）+ absence 语义不同，不是簇。
- **唯一缺口（P2 hygiene，本轮不立 story）**: 6 seam 中 3 个无直接单元测试——
  `resolve_writer` 全 tests 零引用、`resolve_runtime_state` 仅 3 处间接断言、
  `resolve_typed_port` 被同名测试文件漏测（只测了 `_or_runtime`）。违背本项目自己的
  "interface is the test surface" 信条，且 RA-127 开了"test the shared seam's
  interface"先例；但按 quality lane 铁律 P2 hygiene 不单独占轮 → **deferred**，
  记在此供未来 hygiene 轮搭车。

### Area C — run→agent binding / lobehub mapping seam (subagent, read-only)

- **Q1**: 映射的唯一 SQL 真值在 `lobehub_agents.py:34-35`
 （`SELECT agency_config->>'lcaAssistantId' FROM agents WHERE id = %s`，`rg -i "from agents"`
  全仓确认唯一）；理解概念跳 5 模块但职责清晰（一处 seam + 两处引用：carrier decode +
  CLI defer；`answer.py` 只做 approval resume 无映射，`chat_projection.py` 只读写 messages
  projection——三个"各有一份"的怀疑全部证伪）。
- **Q2**: 46 行薄包装，但 deletion test 通过（三样封装：外部列知识/ADR-0187 §3 D7、
  fail-soft 契约、连接串统一入口）；但**模块级 import 破坏了 fail-soft 意图** → **S1 → story RA-135**。
- **Q3**: `37a17cc49` 收敛是实的（调用方恰好两处，无第二处手写连接串）；
  `postgres.py:78` 的 `__all__` 漏了 `lobehub_database_url` → hygiene 注记（非 story）。
- **Q4**: 无 SQL 泄漏；carrier 直接 import persistence 是既定做法（同文件已有
  `LocalFileStore` 先例）→ 缝的正确形状，**非 story**。
- **Q5**: 4f67f10d7 的测试钉住 seam interface（monkeypatch），但 seam 自身 5 条 fail-soft
  路径零测试 → **S2 → story RA-134**。
- **"三个找 agent 的 seam"证伪**: `user_store.py:217/406` 是同一协议
  `AssistantOwnership.assistant_id_for_agent` 的两个后端（用户域内真值），`lobehub_agents.py`
  是外部系统真值（ADR-0187 §3 D7）→ 领域事实，非重复，**非 story**。
- **CLI surface contracts-import 检查**: `runs.py:62` 一处顶层 import
 （pre-existing，commit `291a55c0d3` 2026-09-06，与本轮热点无关）；本轮新增 `answer.py`
  136 行零 contracts import，干净 → 记入 CLI 清理 backlog，**非 story**。

## Runtime verification (mandatory, clean tree)

Worktree `~/layered-cognitive-agent`，branch `raphy/arch-20261014-0145`
（= main tip `31e7db97a`，`status --porcelain` 空），`LLM_API_KEY=dummy`。
Kernel boot `run_kernel("profiles/web-standard.yaml")` + `ScriptedLLMAdapter`
（`tests/harness/scripted_llm.py`）：

| # | Flow | Result |
|---|------|--------|
| 1 | Basic run → COMPLETED | ✅ PASS |
| 2 | Run with a tool call (NoopTool) → COMPLETED | ✅ PASS |
| 3 | Two sequential runs on one agent → completed / completed | ✅ PASS |
| 4 | Non-converging run (always tool-call, max_steps=3) → `Result(status=failed)` | ✅ PASS — **no exception**, RA-023 holds |

**No P0 candidates.**（Side note: anomaly_detector cycle/stalled 日志警告仍在，P2，
上一轮已记录，本轮未追踪。）

Harness learnings（给未来轮）:
- `sys.path.insert(0, tests_dir)` 若在 repo-root insert **之后**执行，会把 tests/ 插到
  最前，遮蔽真正的 `lca_kernel`（`tests/lca_kernel` 是测试桩包）→ tests/ 必须
  `insert(1, ...)` 或 append。
- `Tool` 子类注册要求非空 `namespace` ClassVar（ADR-0256 fail-fast，
  `tools.register` 处抛 `ValueError`）——NoopTool 必须带 `namespace = "probe"`。

## Duplication scan (secondary)

No new mechanical duplication clusters. The bypass chain and the lobehub seam are
single-seam by construction; the remaining probe clusters were re-declined above.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-131 | `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py` (`_dispatch_resume` :709, `_decode_resume_approval` :247/258), `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py` (`resume_approval` :285-291), `lca/plugins/transport/webserver/handlers/runs/session/session/session.py` (:100) | 记录点对任何被接受的 resume answer 无条件记录 `approval_request["tool_calls"]` 进持久的 `approved_tool_names`，无 approve/reject 区分；而 resume 契约显式支持 `rejectionReason`（decoder :247/258），`_dispatch_resume` :709 又把 content/rejection_reason fold 成一个 payload——区分在到达记录点前被销毁。人类拒绝某工具 → 该工具被记为"已批准" → 模型重调时 `act.authorize` approved-override 直接放行。"拒绝→重调→自动放行"。 | 让 approve/reject 的区分活到记录点：`_dispatch_resume` 把"是否为拒绝"传下去（或记录点侧校验），拒绝答案不记录；`RunPort.resume_approval` 签名若变，只动 carrier 内部。 | Locality: "批准"的语义从注释变成记录点的代码不变量。Leverage: 堵住审批绕过链上唯一的语义空洞；所有未来的 answer 类型（deny/skip）自动被正确处理。 | **Strong** |
| RA-132 | `lca/infrastructure/runtime_plane/access/approved_tools.py`, tests | `canonical_tool_name` 在写（commands.py:289）读（authorize.py:281）两端靠程序员纪律各调一次；一侧漏调 → bypass 静默失效（fail-closed，难排障）。且 heuristic 有 mangling 边界（全大写 `"GET"` → `"gET"`，:34-35）。 | `set_approved_tool_names` 内部 canonicalize 输入——非法形态进不来（make illegal states unrepresentable）；读侧调用保留（defense in depth）或删掉，测试钉住。 | Locality: 归一化不变量住进拥有 ContextVar 的 seam。Leverage: 以后任何写入方自动合规；heuristic 的 mangling 边界被测试钉死一处。 | Worth exploring |
| RA-133 | `tests/`（bypass 链缝测试） | 7ecb54c6c 用 monkeypatch 绕过 ContextVar 缝；facade 测试同 task set→get 近 tautology——而 Q3 隔离论证依赖的恰恰是 `create_task(resume_run)` 后子 task 的继承，该环节零测试。 | 补缝测试：set 后 `asyncio.create_task` 包一个 stub `resume_run`（mock coordinator），断言子 task 内 `get_approved_tool_names()` 读到注入集合、父 task 读不到。 | Locality: 测试与现有 bypass 测试并列。Leverage: 把"注入随 resume task 生死"的隔离论证变成钉住的回归网。 | Worth exploring |
| RA-134 | `lca/infrastructure/persistence/lobehub_agents.py`, `tests/` | `agent_assistant_id_from_lobehub` 的 5 条 fail-soft 路径（空 agent_id / 无 DATABASE_URL / 连接抛异常 / 行缺失 / `agency_config` 缺 key）零直接测试；现有测试全 monkeypatch 掉了被测函数——"carrier 会正确调用 seam"已证，"seam 自己是对的"未证。`except Exception: return None` 无测试等于无契约。 | 用 fake `postgres_connection`（contextmanager stub）测 5 条路径；不钉 SQL 文本（列名变更由 ADR 驱动）。 | Locality: 测试贴着 46 行纯函数 seam。Leverage: fail-soft 契约从 docstring 承诺变成回归网；以后改 fail-soft 语义会先红测试。 | Worth exploring |
| RA-135 | `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py` (:38) | `agent_assistant_id_from_lobehub` 是模块顶层 import 进 carrier 的；`lobehub_agents.py` 自身任何导入期失败都会让整个 `command_endpoints` 模块 import 失败——fail-soft 的边界画在调用时，漏了导入时，与 seam 的 "Never raises into the run-creation path" 承诺不匹配。 | import 懒加载进 `if not assistant_id:` 的 fallback 分支（或 `try/except ImportError → None`）；4f67f10d7 的 monkeypatch 目标（`endpoints.agent_assistant_id_from_lobehub` 模块属性）不变。 | Locality: 失效域与承诺对齐，3 行机械改动。Leverage: 以后 helper 加重依赖不炸 carrier。 | Worth exploring |

### Self-grilling (per candidate)

**RA-131**
- Constraints: 2e8264fb4 的 bypass 语义（真批准→免重复审批）必须保留；`resume_approval`
  的 payload 是字符串契约，前端/gateway/CLI 都在用，不能静默改含义。
- Dependencies: 调用方 `command_endpoints._dispatch_resume`（唯一生产调用方）+
  `RunPort`/`RegistryRunAdapter` 转发链；`session.approved_tool_names` 的读者只有
  `execute.resume_run` 的注入点。改动面封闭。
- Shape: 记录点加守卫 `if <answer is approval>:`；"是否为拒绝"的信息在
  `_dispatch_resume` 的 `payload_dict` 里天然存在（`rejection_reason` 非空即拒绝），
  传一个 bool 或拆两个参数都行，不动 `RunSession` 结构。
- Test survival: 7ecb54c6c（bypass 三行为）+ 4f67f10d7（binding）都不碰记录点逻辑，
  应全绿；新测试钉"拒绝→不记录 / 批准→记录"。
- Deletion test verdict: 守卫删掉 → "拒绝被记成批准"的空洞回来。Concentrates（语义
  决策只在一处做）。
- Territory: webserver carrier 是 lca-1000 领地（PILOT 事件分类法 + 退休 stub 删除），
  但本 story 动的是 `resume_approval` 记录点——`git log` 证实该文件近 8 个提交全是
  用户侧 runs 工作（ee48d1d2e 等），lca-1000 无活跃 churn；且 bypass 特性本身是用户侧
  commit 2e8264fb4。无碰撞。

**RA-132**
- Constraints: `canonical_tool_name` 的 heuristic 本体不动（LobeHub wire 约定）；
  `set` 的参数类型 `frozenset[str]` 不变。
- Dependencies: 写方 commands.py:289、读方 authorize.py:281；seam 内部 canonicalize
  后，写方的显式调用变冗余（可留作 defense in depth，由实现轮决定）。
- Shape: `set_approved_tool_names` 内 `names = frozenset(canonical_tool_name(n) for n in names)`。
- Test survival: test_run_execution_facade.py:86（set→get）照旧绿；新测试钉 snake_case
  输入 → canonical 存储。
- Deletion test verdict: 删掉内部 canonicalize → 回到"靠纪律"的两端调用。Concentrates
  （不变量只在一处强制）。

**RA-133**
- Constraints: 纯测试 story，零产品代码变更。
- Dependencies: 依赖 `approved_tools` 的 ContextVar 语义 + `asyncio.create_task` 的
  context 拷贝行为（标准库保证）。
- Shape: `test_approved_names_inherit_into_resume_child_task`：父 task set →
  `create_task(child())` → 子 task 内 get 断言 + 父 task 内 reset 后 get 为空。
- Test survival: 不碰现有测试。
- Deletion test verdict: n/a（测试）。价值在于把 Q3 的隔离论证变成证据。

**RA-134**
- Constraints: 纯测试 story；不钉 SQL 文本（`agency_config->>'lcaAssistantId'` 列名是
  ADR-0187 §3 D7 的领域知识，变了应由 ADR 驱动）。
- Dependencies: `postgres_connection` 的 contextmanager 协议（fake stub 实现）。
- Shape: 5 个用例 × fail-soft 路径；fake connection 按用例抛异常/返回空行/缺 key。
- Test survival: 4f67f10d7 的 monkeypatch 测试不受影响。
- Deletion test verdict: n/a（测试）。`except Exception: return None` 无测试=无契约，
  这是本 story 的全部理由。

**RA-135**
- Constraints: 4f67f10d7 的 monkeypatch 目标是模块属性
  `endpoints.agent_assistant_id_from_lobehub`——懒加载必须保持该属性存在
  （函数内 `from ... import ...` 后赋值给模块全局，或 import 语句移到函数内但仍绑定
  模块属性；实现轮二选一，测试会钉死）。
- Dependencies: 唯一调用方是 fallback 分支；`postgres.py` 的 `lobehub_database_url`
  不动。
- Shape: 3 行机械改动。
- Test survival: test_run_binding.py 全绿（monkeypatch 位置不变）。
- Deletion test verdict: 改动删掉 → 回到 import-time 脆弱。Concentrates（失效域决策
  只在一处）。
- Territory: 同 RA-131（`git log` 无 lca-1000 活跃 churn）。

## Top recommendation

**先做 RA-131**。它是本轮唯一的 Strong：一条真实存在的审批绕过空洞——人类
**拒绝**某工具调用，该工具却被记入"已批准"集合，模型重调时自动放行。证据链完整
（decoder 显式支持 `rejectionReason` → `_dispatch_resume` :709 fold 销毁区分 →
记录点 :285-291 无条件记录 → `approved_tool_names` 跨请求持久无清理 →
authorize.py :279-286 bypass 无条件信任集合）。其余四个 Worth exploring 按
RA-132 → RA-133 → RA-134 → RA-135 顺序：先收紧 seam（132），再把隔离论证变成测试
（133），再补外部 seam 的契约测试（134），最后对齐 fail-soft 失效域（135）。

## Considered and declined (documented, not stories)

- **_resolve.py 测试面缺口**（3/6 seam 无直接测试）：真实缺口，但 P2 hygiene——按
  quality lane 铁律不单独占轮，deferred 供未来 hygiene 轮搭车（Area B §6）。
- **`postgres.py:78` stale `__all__`**（漏 `lobehub_database_url`）：影响为零的元数据
  hygiene，顺手修（S3）。
- **authorize.py:54 vs :78-80 双 import**（顶层 + 函数内 lazy）：P2 hygiene，顺手合入
  任一 touch 该文件的 story（F4）。
- **CLI surface `runs.py:62` contracts 顶层 import**：违规属实但 pre-existing
 （2026-09-06），与本轮热点无关 → CLI 清理 backlog，不开 story。
- **memory_extract `agent_state`×2 / memory×2 / reducer×2 / fold `agent_state`回退 /
  route+shortcut RuntimeError / render `_resolve_role_profile`**：Area B 逐项复核，
  decline 成立（见 Friction walk Area B）。
- **legacy `carrier/runs/resume.py:47` 无注入 `resume_run`**：dead-ish 兼容壳，
  fail-closed 方向 → 注记，不开 story。
- **"三个找 agent 的 seam"**：证伪，领域事实（用户域内协议后端 ×2 + 外部回退 ×1）→ 不开 story。
- **F5/F6/F7/F8 类 speculative**：本轮摩擦漫步未产生 speculative 候选——三个区的
  "无 story"结论都写清了读过的文件与不适用的理由（diversity quota 的无发现文档化义务）。

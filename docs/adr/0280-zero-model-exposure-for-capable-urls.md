# ADR-0280 — 携带能力特权 URL 的零大模型暴露与带外意图兑换（Zero Model Exposure for Capable URLs & Out-of-Band Intent Resolution）

## 状态

**Implemented — 2026-10-04**

**v2 修正案 Accepted — 2026-10-04（待实施，见 §5）**：卡片挂载面收敛到 tool result 与 tool surface registry，散文标签协议与 INV-CAP-04 兜底退役。

> **一句话**：终结特权授权短链（OAuth Redirect URL、敏感下载凭证等）穿透大模型上下文导致的安全隐患与前端渲染错乱——建立 **Zero LLM Exposure** 铁律：工具层向 `ConnectorAuthIntentVault` 暂存高特权 URL 并仅向大模型暴露 `intent_id`，网关层通过 `RunSessionWriter` 提供确定性卡片挂载保底，前端由 `ConnectorAuthCard` 凭 `intentId` 带外异步兑换真实 URL，彻底隔离认知决策与特权能力。

**Extends**：
- [ADR-0195](0195-platform-architecture-convergence.md)（平台架构收敛与信息血统闭合 C13）：强化信息跨边界流转的 Typed Contract 约束；
- [ADR-0252](0252-multi-user-onboarding-and-identity.md)（多用户身份与边界隔离）：按 User ID 实施严格的 Intent 属主隔离；
- [ADR-0253](0253-muse-sentinel-egress-and-credential-boundary.md)（出站控制面与凭证边界）：特权凭证严禁未经审查直接暴露。

**实证来源**：
2026-10-03 ~ 2026-10-04 线上连接器使用实测：
- 用户要求连接外部第三方应用（如 Google Drive、GitHub）；
- 连接工具生成 `https://connect.composio.dev/link/lk_...` OAuth 授权短链；
- 缺陷现象：真实授权 URL 直接作为 Observation 文本返回给大模型。大模型在回复时往往直接吐出裸 Markdown 链接（`[点击这里授权](https://...)`），破坏了 `[widget:connector_auth]` 结构化卡片渲染；更为严重的是，携带一次性授权能力的 URL 暴露在 Prompt/Context/Thinking 历史中，存在被模型幻觉改写、提示词注入劫持或日志泄漏的严重安全隐患。

---

## 0. 接任务前 7 问

1. **问题是什么？** 携带高特权能力的授权短链流经大模型，不仅导致模型输出裸 URL 破坏卡片 UI，更违背了特权隔离与安全边界。
2. **受影响的事实或契约是什么？** 连接器 Observation 内容、`ConnectorAuthIntent` 契约模型、`RunSessionWriter` 会话持久化、Web 路由 `/composio/auth-intents/{intent_id}/resolve`、前端 `ConnectorAuthCard` 补丁。
3. **唯一真值在哪里？** 
   - 特权 URL 唯一真值在 `ConnectorAuthIntentVault`（内存安全暂存，带 TTL）；
   - 对话事实真值在 Session（仅存 `intent_id` 与 widget 标签，不含敏感 URL）。
4. **改变哪个边界？** 工具返回边界（剥离敏感 URL）、网关出入口（确定性 widget 保底）、客户端交互边界（带外异步 resolve）。认知层只看引用，不看能力。
5. **现有 Protocol / ADR 能否表达？** 无法表达。之前缺少安全 Intent 暂存与带外异步兑换机制。
6. **失败、重试、恢复和幂等语义是什么？**
   - 兑换超时：超过 300s TTL 自动清理，兑换请求返回 404；
   - 越权访问：跨用户（X-User-ID 不匹配）访问一律返回 404，不泄露 Intent 存在性；
   - 幂等消费：首轮兑换标记 `consumed=True`，允许重试打开同一窗口直至过期。
7. **如何验证？**
   - 契约单测：`tests/connectors/test_auth_intent_vault.py`
   - 零 URL 泄漏测试：`tests/connectors/test_zero_model_url_leakage.py`
   - 网关保底测试：`tests/runtime/test_gateway_intent_widget_fallback.py`
   - 端点测试：`tests/transport/test_routes_auth_intents.py`
   - 前端补丁验证：`tests/deploy/test_connector_auth_card_patch.py` 及 `patch_lobehub.py verify`
   - 全链路 E2E 场景测试：`tests/scenario/test_connector_capability_intent_e2e.py`

---

## 1. 核心架构不变量（INV-CAP-01 ~ 06）

| 编号 | 核心不变量 | 说明 |
|---|---|---|
| **INV-CAP-01** | **Zero LLM Exposure** | 任何携带能力的特权 URL（OAuth 短链、特权操作签名链接等）严禁出现在 Observation、Prompt、Thinking 和 LLM Message 中。大模型仅能感知 `intent_id`。 |
| **INV-CAP-02** | **Ephemeral Ticket Lifecycle** | Intent 凭证具有 300 秒生命周期（TTL），基于多租户 `user_id` 严格隔离，过期或越权一律静默拒绝（返回 404 防止枚举探测）。 |
| **INV-CAP-03** | **Out-of-Band Resolution** | 前端客户端在用户交互触发（如点击【立即授权】按钮）时，凭 `intent_id` 通过专属 REST 路由异步兑换真实 URL，认知图完全不介入。 |
| **INV-CAP-04** | **Gateway Deterministic Fallback** | 网关层（`RunSessionWriter`）在持久化 Assistant 消息时，若检测到上一轮存在未挂载的 Intent 且模型漏写卡片标签，确定性自动追加 `[widget:connector_auth?intentId=...]`，根除大模型漏格式导致的 UI 丢失。 |
| **INV-CAP-05** | **Decoupled Frontend Card** | 前端 `ConnectorAuthCard` 统一接收 `intentId`，支持异步兑换、加载态反馈、居中模态弹窗与阶梯轮询状态检查。 |
| **INV-CAP-06** | **E2E Traceability** | 审计与测试全链路可闭环追溯，各分层测试相互正交，不变量受确定性自动化测试守护。 |
| **INV-CAP-07** | **Mount Follows the Fact** | 能力事实源自 tool result 的交互卡片一律经 tool surface registry 挂载；禁止以正则扫描消息内容作为挂载机制（v2 新增，见 §5）。 |

INV-CAP-02、INV-CAP-04、INV-CAP-05 的 v2 修订见 §5。实施 PR 落地时同步本表与 §2、§4。

---

## 2. 详细设计与数据流

```text
[ 用户触发操作 / 工具执行 ]
           │
           ▼
[ Composio Connect Tool / Adapter ]
    ├─► 生成敏感短链 (OAuth redirect_url)
    ├─► 向 ConnectorAuthIntentVault 登记 (auth_url, user_id, 300s TTL)
    ├─► 返回 intent_id (如 cai_01h8...)
    └─► 构造 Observation: 包含 [widget:connector_auth?intentId=...&appName=...] (绝无 http:// 或 https://)
           │
           ▼
[ 大模型认知循环 (Think / Perceive) ]
    ├─► 仅看到 intent_id 与 widget 占位符
    └─► 生成最终 Assistant 回复 (可能规范输出 widget，也可能漏写)
           │
           ▼
[ 网关层 (RunSessionWriter) ]
    ├─► 检查当轮未挂载的 Pending Intents
    └─► 自动兜底补全: 若文本漏写，追加 [widget:connector_auth?intentId=...]
           │
           ▼
[ 前端界面 (LobeHub UI / ConnectorAuthCard) ]
    ├─► 解析 widget:connector_auth 渲染卡片
    ├─► 用户点击【立即授权连接】
    ├─► 带外调用 POST /composio/auth-intents/{intentId}/resolve
    ├─► 获得 real auth_url 并居中弹窗打开
    └─► 启动阶梯轮询 (1s -> 2s -> 3s) 监听连接激活状态
```

---

## 3. 安全防护与多租户隔离

1. **时效性防线（300s TTL）**：
   - 所有的 Intent 均由 `ConnectorAuthIntentVault` 统一纳管；
   - 默认 300 秒（5 分钟）生命周期，超期后在读写锁内自动剔除，内存零泄漏；
   - 超过 TTL 的请求统一返回 HTTP 404。

2. **多租户与身份隔离**：
   - Intent 绑定发起用户的 `user_id`；
   - 兑换端点从鉴权上下文或 `X-User-ID` 提取当前请求用户身份，若与创建者不符直接返回 404；
   - 严格采用 404 而非 403，防止跨租户通过状态码探测 Intent ID 是否存在。

3. **单向消费与重入容忍**：
   - 记录 `consumed` 状态；
   - 在 TTL 窗口内，允许同一合法用户多次点击（例如首次弹窗被拦截后重试），直至连接成功或票据过期。

---

## 4. 实施清单

1. **契约层**：[`lca/contracts/models/connectors/intent.py`](../../lca/contracts/models/connectors/intent.py)（`ConnectorAuthIntent` 冻结契约模型）
2. **基础设施层**：[`lca/infrastructure/connectors/core/intent_vault.py`](../../lca/infrastructure/connectors/core/intent_vault.py)（`ConnectorAuthIntentVault` 暂存器与单例注入）
3. **工具与适配层**：
   - [`lca/infrastructure/tools/composio/__init__.py`](../../lca/infrastructure/tools/composio/__init__.py)
   - [`lca/infrastructure/connectors/core/adapter.py`](../../lca/infrastructure/connectors/core/adapter.py)
   - [`lca/infrastructure/connectors/core/state.py`](../../lca/infrastructure/connectors/core/state.py)
4. **运行时网关**：[`lca/runtime/session/run_session_writer.py`](../../lca/runtime/session/run_session_writer.py)（确定性卡片保底挂载器）
5. **传输层端点**：
   - [`lca/plugins/transport/webserver/handlers/composio/endpoints.py`](../../lca/plugins/transport/webserver/handlers/composio/endpoints.py)
   - [`lca/plugins/transport/webserver/routes_1/routes_composio.py`](../../lca/plugins/transport/webserver/routes_1/routes_composio.py)
6. **前端补丁**：
   - [`deploy/lobehub/patches/ui/ConnectorAuthCard.tsx`](../../deploy/lobehub/patches/ui/ConnectorAuthCard.tsx)
   - [`deploy/lobehub/patches/ui/connector_auth_card.py`](../../deploy/lobehub/patches/ui/connector_auth_card.py)
7. **验证套件**：
   - `tests/connectors/test_auth_intent_vault.py`
   - `tests/connectors/test_zero_model_url_leakage.py`
   - `tests/runtime/test_gateway_intent_widget_fallback.py`
   - `tests/transport/test_routes_auth_intents.py`
   - `tests/deploy/test_connector_auth_card_patch.py`
   - `tests/scenario/test_connector_capability_intent_e2e.py`

---

## 5. 修订记录（v2 — 2026-10-04：卡片挂载面收敛到 tool result）

**状态：Accepted，待实施。** 实施 PR 落地时同步 §1 不变量表、§2 数据流与 §4 实施清单，并移除本节的待实施标注。

### 5.1 裁决

交互授权卡片的挂载面从 assistant 散文收敛到 tool result。`composioConnect` 的 Observation payload（`intent_id`、`app_name`、`connection_id`）是票据在 wire 上的唯一结构化载体。前端 tool surface registry（`@lobechat/builtin-tools/register` 与 LCA `lca_tool_render_register`）拥有卡片挂载。composioConnect 的 tool 行只出现在 LCA gateway turn，该 turn 渲染为 assistantGroup，工具卡片经 `AssistantGroup/Tool/Inspector` 消费 registry；普通 `Messages/Assistant` 面不渲染 LCA 工具卡片。registry 挂载因此覆盖该事实能出现的全部面。assistant 散文不再携带挂载标签，模型不再承担转述挂载指令的职责。

### 5.2 理由

1. 散文当协议有三个独立失效点：模型措辞、渲染器分支、markdown 变换。run_721c7ae6fc0c（2026-10-04）实证渲染器分支失效：标签经 wire 与持久化完整到达前端，分组渲染器 `AssistantGroup/components/ContentBlock.tsx` 无 `connector_auth` 分支，标签以裸文本呈现，卡片未挂载。
2. INV-CAP-04 的字符串追加兜底是该失效点的消费者侧补丁。挂载面收敛后模型无标签可漏，兜底失去存在前提。
3. tool result 已是 typed 事实，且工具卡片渲染在两个消息渲染器下共用 tool surface registry。挂载点单一、渲染器无关，新增渲染器不再构成失效面。

### 5.3 不变量修订

| 编号 | 修订 |
|---|---|
| INV-CAP-02 | 属主身份收敛为单一调用者头 `x-lca-user-id`（[ADR-0252](0252-multi-user-onboarding-and-identity.md)），经共享 helper 读取。`X-User-ID` 读取退役。票据属主在签发时取 run 调用者 user id，经工具上下文注入。`getattr(self._integration, "user_id", None)` 死分支退役。 |
| INV-CAP-04 | 退役。`ensure_intent_widget_in_assistant_message` 与 `extract_pending_intents_from_events` 在实施 PR 删除，`tests/runtime/test_gateway_intent_widget_fallback.py` 同删。 |
| INV-CAP-05 | 卡片从 tool result state 接收 `intentId`。`authUrl` 的 `cai_` 兼容分支退役。`Messages/Assistant/index.tsx` 的标签解析与挂载块退役。 |
| INV-CAP-07 | 新增，见 §1。挂载跟随事实：能力事实源自 tool result 的交互卡片经 tool surface registry 挂载，禁止正则扫描消息内容作为挂载机制。 |

### 5.4 失败与恢复语义

- 票据过期或内核重启（vault 为进程内存）：卡片进入 timeout 态并提供重发动作，调用 `POST /composio/auth-intents/{intent_id}/reissue`，属主校验与 resolve 相同。reissue 以 `(user_id, service)` 为键替换未兑换票据并返回新 `intent_id`。恢复路径不经过模型。
- 刷新后重渲染：tool 行持久化 shape 必须携带 `intent_id`、`app_name`、`connection_id`（pluginState 或 result state），卡片从持久化 tool 行重建。实施 PR 的第一个验证任务是确认现有持久化 shape 满足该契约，不满足则同 PR 修正。

### 5.5 退役清单（实施 PR 同删）

`[widget:connector_auth?...]` 字符串协议。`run_session_writer.py`、`Messages/Assistant/index.tsx`、`ConnectorAuthCard.tsx` 三处标签正则。INV-CAP-04 兜底函数与其测试。composio Observation 中要求原样输出标签的指令文案。`authUrl` 的 `cai_` 兼容分支与 `ConnectorAuthCard.tsx` 的 legacy fail-closed 处理（含 deprecated `authUrl` prop）。`Messages/Assistant/index.tsx` 卡片挂载块与 `connector_auth_card.py` 补丁对 `Assistant/index.tsx` 的挂载注入。`X-User-ID` 读取。死 getattr 分支。

实施 PR 禁止半态：新 registry 挂载与旧补丁挂载不得在同一次部署中并存。PR 合入时旧挂载路径必须已删，评审以本节清单逐项核对。

### 5.6 验证门禁

- 保留：`tests/connectors/test_auth_intent_vault.py`、`tests/connectors/test_zero_model_url_leakage.py`、`tests/transport/test_routes_auth_intents.py`（属主头断言改为 `x-lca-user-id`）。
- 新增：registry surface 由 tool result state 渲染卡片的 vitest；分组 turn 渲染卡片节点的 vitest（该测试是实施 PR 的完成条件，不是清单愿望，缺它 PR 不合）；实施时复核不存在 registry 之外消费 tool 行的新消息面；reissue 端点测试；持久化 tool 行刷新后重渲染卡片的测试；浏览器端到端验证新 run 出现卡片且点击兑换弹窗。
- 删除：`tests/runtime/test_gateway_intent_widget_fallback.py`；`tests/deploy/test_connector_auth_card_patch.py` 的标签解析断言（挂载断言迁入 registry surface 测试）。

### 5.7 联动

- [ADR-0252](0252-multi-user-onboarding-and-identity.md)：`x-lca-user-id` 是调用者身份唯一拼写，本修正案不新增头。
- §2 数据流图与 §4 实施清单在实施 PR 同步：`run_session_writer.py` 不再拥有挂载职责，tool surface registry 成为挂载 owner。

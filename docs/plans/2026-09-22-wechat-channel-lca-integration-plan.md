# 微信消息频道 LCA Python 原生接管实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 将 LobeHub 消息频道的微信二维码生成、状态轮询、长轮询消息接收、消息回复及思考/工具状态格式化等服务端职责，彻底移交由 LCA Python 后端原生接管，前端通过声明式补丁直连 LCA 网关。

**Architecture:** 
1. 基础设施层实现纯 Python 原生 `WechatIlinkClient`（封装 iLink HTTP/JSON 协议）与 `WechatMessageFormatter`（100% 对齐 LobeHub 原生 `replyTemplate.ts` 排版规范）；
2. 实现 `WechatChannelManager` 与 `WechatChannelWorker`，随内核生命周期管理各 Assistant 的长轮询常驻任务，微信消息通过 `Session.append` 单轨进入认知循环，下行通过 `sendmessage` 注入 `context_token`；
3. 传输层 Starlette 提供 `/lca-api/channels/wechat/*` 路由插件；
4. 前端通过 `deploy/lobehub/patches/route/wechat_channel_lca_proxy.py` 声明式补丁直连 LCA 网关。

**Tech Stack:** Python 3.11+, Starlette, httpx, asyncio, pytest, Pydantic v2.

---

### Task 1: 契约模型与原生排版格式化器 (`WechatMessageFormatter`)

**Files:**
- Create: `lca/contracts/channels/wechat.py`
- Create: `lca/infrastructure/channels/wechat/formatter.py`
- Test: `tests/channels/test_wechat_reply_formatter_parity.py`
- Does NOT own: `lobehub-ui/`, `lca/plugins/transport/webserver/` (AP-01)
- Invariants to test: 严格断言输出与 LobeHub 原生 `replyTemplate.ts` 规范一致（包含 `💭`、`○`、`⏺`、`⎿` 及 `> 共 N 次工具调用 · Xs` 格式）(INV-WC-02)

**Step 1: Write the failing test**
编写 `tests/channels/test_wechat_reply_formatter_parity.py`，断言思考、工具待调用、工具已完成及统计头的排版生成。

**Step 2: Run test to verify it fails**
Run: `pytest tests/channels/test_wechat_reply_formatter_parity.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**
- 在 `lca/contracts/channels/wechat.py` 中定义 DTO：`WechatQrResult`, `WechatStatusResult`, `WechatChannelConfig`。
- 在 `lca/infrastructure/channels/wechat/formatter.py` 中实现 `WechatMessageFormatter.format_step_progress`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/channels/test_wechat_reply_formatter_parity.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/contracts/channels/wechat.py lca/infrastructure/channels/wechat/formatter.py tests/channels/test_wechat_reply_formatter_parity.py
git commit -m "feat(wechat): add WechatMessageFormatter with LobeHub replyTemplate parity"
```

---

### Task 2: 原生微信 iLink 通信客户端 (`WechatIlinkClient`)

**Files:**
- Create: `lca/infrastructure/channels/wechat/client.py`
- Test: `tests/channels/test_wechat_ilink_client.py`
- Does NOT own: `lobehub-ui/`, `lca/plugins/transport/webserver/` (AP-01)
- Invariants to test: `fetch_qrcode` 载荷解析；`poll_qrcode_status` 状态流转（`wait` $\rightarrow$ `scaned` $\rightarrow$ `confirmed` $\rightarrow$ `expired`）；`send_message` 2000 字自动拆切且每片注入 UUID4 `client_id` 与 `context_token` (INV-WC-01, INV-WC-05)

**Step 1: Write the failing test**
编写 `tests/channels/test_wechat_ilink_client.py`，使用 `respx` 或 mock httpx 模拟微信 iLink 服务端响应，断言扫码和发送方法。

**Step 2: Run test to verify it fails**
Run: `pytest tests/channels/test_wechat_ilink_client.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**
在 `lca/infrastructure/channels/wechat/client.py` 中实现 `WechatIlinkClient`：
- `fetch_qrcode()`
- `poll_qrcode_status(qrcode)`
- `get_updates(bot_token, cursor)`
- `send_message(bot_token, to_user_id, context_token, text)`
- `send_typing(bot_token, to_user_id, typing_ticket, start=True)`

**Step 4: Run test to verify it passes**
Run: `pytest tests/channels/test_wechat_ilink_client.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/channels/wechat/client.py tests/channels/test_wechat_ilink_client.py
git commit -m "feat(wechat): implement native WechatIlinkClient"
```

---

### Task 3: 长轮询守护与会话双向桥接 (`WechatChannelWorker` & `Manager`)

**Files:**
- Create: `lca/infrastructure/channels/wechat/worker.py`
- Create: `lca/infrastructure/channels/wechat/manager.py`
- Test: `tests/channels/test_wechat_channel_worker.py`
- Does NOT own: `lobehub-ui/` (AP-01)
- Invariants to test: 确定性生成 `sess_wc_*` 隔离会话；入站事实严格仅通过 `Session.append` 追加；长轮询超时自动进入下一轮；5xx 触发指数退避（$\le 10\text{s}$）；401 标记 `session_expired` 退出 (INV-WC-03, INV-WC-04)

**Step 1: Write the failing test**
编写 `tests/channels/test_wechat_channel_worker.py`，模拟消息接收、会话映射、typing 发送及认知驱动下发。

**Step 2: Run test to verify it fails**
Run: `pytest tests/channels/test_wechat_channel_worker.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**
- 实现 `WechatChannelWorker`：异步长轮询循环、异常退避自愈、`Session.append` 单轨事实写入与结果出站投递。
- 实现 `WechatChannelManager`：管理多助手频道的加载、启停与配置持久化（`~/.lca/assistants/{id}/channels/wechat.json`）。

**Step 4: Run test to verify it passes**
Run: `pytest tests/channels/test_wechat_channel_worker.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/channels/wechat/worker.py lca/infrastructure/channels/wechat/manager.py tests/channels/test_wechat_channel_worker.py
git commit -m "feat(wechat): add WechatChannelWorker daemon and session bridge"
```

---

### Task 4: Starlette 网关传输层路由插件 (`routes_channels_wechat.py`)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_channels_wechat.py`
- Modify: `lca/plugins/transport/webserver/__init__.py`
- Test: `tests/transport/test_routes_channels_wechat.py`
- Does NOT own: `lobehub-ui/` (AP-01)
- Invariants to test: `/lca-api/channels/wechat/qrcode` 正确转发；`/status` 准确返回状态机；`/bind` 落地配置并启动 Worker；未授权或异常格式抛出 400

**Step 1: Write the failing test**
编写 `tests/transport/test_routes_channels_wechat.py`，使用 `TestClient` 测试路由端点。

**Step 2: Run test to verify it fails**
Run: `pytest tests/transport/test_routes_channels_wechat.py -v`
Expected: FAIL (404 Not Found)

**Step 3: Write minimal implementation**
- 在 `routes_channels_wechat.py` 实现路由插件：
  - `GET /lca-api/channels/wechat/qrcode`
  - `GET /lca-api/channels/wechat/status`
  - `POST /lca-api/channels/wechat/bind`
  - `POST /lca-api/channels/wechat/unbind`
- 并在 `lca/plugins/transport/webserver/__init__.py` 中声明插件导出。

**Step 4: Run test to verify it passes**
Run: `pytest tests/transport/test_routes_channels_wechat.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/routes_channels_wechat.py lca/plugins/transport/webserver/__init__.py tests/transport/test_routes_channels_wechat.py
git commit -m "feat(transport): add routes_channels_wechat Starlette plugin"
```

---

### Task 5: 前端轻量声明式代理补丁 (`wechat_channel_lca_proxy.py`)

**Files:**
- Create: `deploy/lobehub/patches/route/wechat_channel_lca_proxy.py`
- Test: `tests/deploy/test_wechat_channel_patch.py`
- Does NOT own: 直接修改 `lobehub-ui/` 源码库文件 (AP-01)
- Invariants to test: 补丁应用成功，补丁移除可逆，`python scripts/check_patch_integrity.py` 81+ 文件哈希 100% 一致 (INV-WC-06)

**Step 1: Write the failing test**
编写 `tests/deploy/test_wechat_channel_patch.py`，验证补丁元数据与代码替换逻辑。

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_wechat_channel_patch.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**
- 在 `deploy/lobehub/patches/route/wechat_channel_lca_proxy.py` 中编写 PatchMeta 与 apply 逻辑，将 `agentBotProviderService.ts` 中的 `wechatGetQrCode` 和 `wechatPollQrStatus` 替换为 fetch `/lca-api/channels/wechat/*`。
- 执行 `python deploy/lobehub/patch_lobehub.py` 应用补丁。

**Step 4: Run test to verify it passes**
Run: `pytest tests/deploy/test_wechat_channel_patch.py -v`
Run: `python scripts/check_patch_integrity.py`
Expected: PASS

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/route/wechat_channel_lca_proxy.py tests/deploy/test_wechat_channel_patch.py
git commit -m "feat(deploy): add wechat_channel_lca_proxy frontend route patch"
```

---

### Task 6: 全链路回归验证与门禁核验

**Files:**
- Create: `tests/channels/test_wechat_channel_e2e.py`
- Invariants to test: 全链路模拟扫码绑定 $\rightarrow$ 入站消息长轮询 $\rightarrow$ 认知循环推理与工具执行 $\rightarrow$ 微信下行原生排版格式化投递 $\rightarrow$ 事实追溯

**Step 1: Write E2E Integration test**
编写 `tests/channels/test_wechat_channel_e2e.py`，覆盖扫码绑定、消息上行、typing 触发、思考与工具进度推送、最终回复全链路。

**Step 2: Run E2E test**
Run: `pytest tests/channels/test_wechat_channel_e2e.py -v`
Expected: PASS

**Step 3: Run Full Suite & Lint Gate**
Run: `ruff check lca/ tests/ deploy/`
Run: `git diff --check`
Expected: 0 warnings, 0 errors

**Step 4: Commit**
```bash
git add tests/channels/test_wechat_channel_e2e.py
git commit -m "test(wechat): add full flow integration test for WeChat channel"
```

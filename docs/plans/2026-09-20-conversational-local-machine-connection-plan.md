# 对话式连接本机与一键安装 (Conversational Local Machine Connection & Auto-Install) Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 允许用户在 LobeHub 前端说“连接本机”或点击卡片，系统自动生成专属预授权的一键安装命令，用户在本地终端（PowerShell/Bash）单次回车后无需二次手动输码即可完成静默下载、配对建联，并自动绑定为当前会话的执行目标。

**Architecture:**
1. 控制面扩展 `DevicePairingService`，增加 `preauth_code` 机制（生成具有 10 分钟有效期的已预授权单次配对码）；
2. 网关新增 `/api/device/pair/preauth`、`/api/device/install.ps1` 与 `/api/device/install.sh` 动态端点；
3. 本机 Companion CLI 增加 `--preauth-code` 直连能力，在脚本中一次性自动化拉起出站长连接守护；
4. 前端异构切换器与对话交互卡片通过 `preauth` 生成一键命令，SWR 感知设备上线后自动切换执行目标；
5. 全流程经 pytest 契约与 E2E 真实测试守护。

**Tech Stack:** Python 3.11, Starlette / FastAPI, WebSockets, PowerShell / POSIX Shell, TypeScript / React, LobeHub Patch Engine.

---

### Task 1: 预授权配对状态机增强 (`DevicePairingService`)

**Files:**
- Modify: `lca/plugins/transport/device_hub/pairing/pairing.py`
- Create: `tests/lca_plugins/transport/device_hub/test_preauth.py`

**Step 1: Write the failing test**
在 `tests/lca_plugins/transport/device_hub/test_preauth.py` 中编写测试用例：
- `test_preauth_code_generation`: 测试生成带 `pre_authorized=True` 的代码；
- `test_preauth_claim_auto_verifies`: 测试客户端携带该代码请求配对时，直接跳过手动验证，状态进入 `VERIFIED` 并发放 `machineToken`；
- `test_preauth_code_one_time_use`: 验证已被消费的预授权码无法被二次消费；
- `test_preauth_code_expiration`: 验证超期（10分钟）的预授权码失效。

**Step 2: Run test to verify it fails**
```bash
pytest tests/lca_plugins/transport/device_hub/test_preauth.py -v
```
Expected: FAIL（`DevicePairingService` 暂无 `preauth_code` 方法）。

**Step 3: Implement minimal code**
在 `lca/plugins/transport/device_hub/pairing/pairing.py` 中：
- `DevicePairingRequest` 增加 `pre_authorized: bool = False` 字段；
- 增加 `preauth_code(user_id, workspace_id, expires_in=600)` 方法；
- 更新 `request_code`：若传入的 `user_code` 属于未消费的预授权请求，则将当前设备关联到该请求并自动判定验证通过。

**Step 4: Run test to verify it passes**
```bash
pytest tests/lca_plugins/transport/device_hub/test_preauth.py -v
```
Expected: PASS（4 passed）。

**Step 5: Commit**
```bash
git add lca/plugins/transport/device_hub/pairing/pairing.py tests/lca_plugins/transport/device_hub/test_preauth.py
git commit -m "feat(device_hub): add pre-authorized pairing state machine"
```

---

### Task 2: 服务端动态下发端点与预授权路由

**Files:**
- Modify: `lca/plugins/transport/device_hub/routes/routes.py`
- Modify: `lca/plugins/transport/webserver/routes_1/routes_device.py`
- Create: `tests/lca_plugins/transport/webserver/test_install_scripts.py`

**Step 1: Write the failing test**
在 `tests/lca_plugins/transport/webserver/test_install_scripts.py` 中测试：
- `POST /api/device/pair/preauth`: 返回 `userCode` 和动态拼接的安装命令；
- `GET /api/device/install.ps1?code=...`: 返回包含传入 Host 与 Code 的 PowerShell 脚本；
- `GET /api/device/install.sh?code=...`: 返回包含传入 Host 与 Code 的 Bash 脚本。

**Step 2: Run test to verify it fails**
```bash
PYTHONPATH=.:vendor/cordis/src:vendor/cosmokit/src:vendor/schemastery/src pytest tests/lca_plugins/transport/webserver/test_install_scripts.py -v
```
Expected: FAIL（端点未注册）。

**Step 3: Implement minimal route handlers**
- 在 `routes.py` 中实现 `pair_preauth`、`install_ps1`、`install_sh` 端点处理函数；
- 在 `routes_device.py` 中将新增的 3 个 RouteSpec 注册到 `ROUTE_SPECS`（共 13 HTTP + 1 WS）；
- 更新 `routes_device` description 与测试断言。

**Step 4: Run test to verify it passes**
```bash
PYTHONPATH=.:vendor/cordis/src:vendor/cosmokit/src:vendor/schemastery/src pytest tests/lca_plugins/transport/webserver/test_install_scripts.py tests/lca_plugins/transport/webserver/test_device.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/plugins/transport/device_hub/routes/routes.py lca/plugins/transport/webserver/routes_1/routes_device.py tests/lca_plugins/transport/webserver/test_install_scripts.py tests/lca_plugins/transport/webserver/test_device.py
git commit -m "feat(webserver): add install scripts and preauth device endpoints"
```

---

### Task 3: 本机 Companion CLI 预授权直连模式

**Files:**
- Modify: `lca/infrastructure/computer/companion/cli.py`
- Modify: `lca/infrastructure/computer/companion/client.py`
- Modify: `tests/infrastructure/computer/test_companion_client.py`

**Step 1: Write the failing test**
在 `test_companion_client.py` 中补充测试：
- `test_companion_auto_pair_with_preauth_code`: 给定 preauth_code 时，`auto_pair` 能够一步获取 `machineToken` 而无需在控制台阻塞提示输码。

**Step 2: Run test to verify it fails**
```bash
pytest tests/infrastructure/computer/test_companion_client.py -k test_companion_auto_pair_with_preauth_code -v
```
Expected: FAIL。

**Step 3: Implement minimal code**
- 在 `CompanionClient` 中增加 `auto_pair(preauth_code: str)` 方法；
- 在 `cli.py` 中增加 `--preauth-code` 参数支持；
- 当传入 `--preauth-code` 时，直接配对并启动 `run`。

**Step 4: Run test to verify it passes**
```bash
pytest tests/infrastructure/computer/test_companion_client.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/infrastructure/computer/companion/ tests/infrastructure/computer/test_companion_client.py
git commit -m "feat(companion): add preauth-code auto-pairing support to client and CLI"
```

---

### Task 4: 前端 LobeHub UI 异构切换器一键安装卡片补丁

**Files:**
- Modify: `deploy/lobehub/patches/ui/execution_target.py`

**Step 1: Write the patch updates**
- 在 `HeteroDeviceSwitcher.tsx` 补丁中增加：
  - “获取一键安装命令”按钮与状态；
  - 调用 `fetch('/lca-api/api/device/pair/preauth')` 获取 Windows / Linux 专属命令；
  - 点击一键复制命令到剪贴板；
  - 动态提示“等待设备连接中...”并在设备出现时自动调用 `selectExecutionTarget('device', deviceId)`。

**Step 2: Apply and verify patch**
```bash
python3 deploy/lobehub/patch_lobehub.py apply execution_target
python3 deploy/lobehub/patch_lobehub.py verify
```
Expected: `23 ok, 0 broken/missing`。

**Step 3: Commit**
```bash
git add deploy/lobehub/patches/ui/execution_target.py
git commit -m "feat(lobehub): add one-liner install command and auto-binding card to device switcher"
```

---

### Task 5: 端到端全链路自动化集成测试

**Files:**
- Create: `tests/e2e/test_conversational_install_flow.py`

**Step 1: Write E2E test**
在 `test_conversational_install_flow.py` 中：
1. 启动本地测试 Uvicorn 网关；
2. 模拟前端调用 `POST /api/device/pair/preauth`，获取预授权码与安装命令；
3. 模拟客户端通过 `GET /api/device/install.ps1?code=...` 获得脚本，并以 `--preauth-code` 启动 `CompanionClient`；
4. 验证客户端自动获取 `machineToken` 并建立 WebSocket 长连接；
5. 验证设备在设备列表中标记为 `online=True`；
6. 验证通过 `LocalExecPort` 向该设备下发 Shell 命令成功返回 `EffectReceipt(success=True)`。

**Step 2: Run test to verify it passes**
```bash
PYTHONPATH=.:vendor/cordis/src:vendor/cosmokit/src:vendor/schemastery/src pytest tests/e2e/test_conversational_install_flow.py -v
```
Expected: PASS。

**Step 3: Commit**
```bash
git add tests/e2e/test_conversational_install_flow.py
git commit -m "test(e2e): verify end-to-end conversational install and auto-pairing flow"
```

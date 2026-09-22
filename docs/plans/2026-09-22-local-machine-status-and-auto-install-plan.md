# 本机状态感知、秒启自愈与双模全自动连接实施计划 (Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 改造前端执行环境中的“本机”，使其作为具备明确主机名与高颜值状态点（🟢 在线 / ⚪ 离线）的一级执行项；解除离线禁用限制，提供“全自动一键下载运行”与“一键命令复制”双模唤醒弹窗，彻底剔除繁琐的手动配对码输入；服务端与客户端结合 Grok Bot 架构经验，落地 Fast-Path 秒启通道、PID 锁防重与开机自启动常驻。

**Architecture:**
1. **客户端层**：`CompanionClient` 落地 `companion_state.json`（记录 PID、启动时间与状态），增加单实例互斥锁，避免重复拉起；
2. **服务端与脚本层**：`install.ps1`/`install.sh` 增加 Fast-Path 检测（已有 token 时 <0.2s 直接唤醒进程），新增 `/api/device/download/runner.bat` 与 `/api/device/download/runner.command` 专属直下端点；
3. **前端补丁层**：升级 `deploy/lobehub/patches/ui/execution_target.py`，移除 `disabled={!d.online}`，剔除主视图配对码输入框，构建【设备唤醒与一键连接】双模浮层并接入 SWR 自动感知关闭与绑定；
4. **测试门禁层**：覆盖 AST 补丁断言、PID 互斥单测、动态脚本端点单测与全量回归测试。

**Tech Stack:** TypeScript, React, Ant Design Style (`@lobehub/ui`), Python 3.11, Starlette / FastAPI, WebSockets, PowerShell / Bash, pytest.

---

### Task 1: 伴侣客户端 PID 锁、状态记录与防重复启动 (`CompanionClient`)

**Files:**
- Modify: `lca/infrastructure/computer/companion/client.py`
- Modify: `lca/infrastructure/computer/companion/cli.py`
- Create: `tests/infrastructure/computer/test_companion_state.py`
- Does NOT own: `deploy/lobehub/`, `lca/core/`, `lca/cognition/`, `contracts/` (AP-01)
- Invariants to test:
  - 启动时在 `~/.lca/companion_state.json` 准确写入 PID、started_at 与 server_url；
  - 重复启动时检测到已有进程存活，安全提示并直接返回，避免多个实例抢占长连接 (AP-02)。

**Step 1: Write the failing test**

创建 `tests/infrastructure/computer/test_companion_state.py`：
```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.infrastructure.computer.companion.client import CompanionClient, CompanionConfig


def test_companion_state_written_on_startup(tmp_path: Path) -> None:
    state_file = tmp_path / "companion_state.json"
    cfg = CompanionConfig(server_url="http://127.0.0.1:8765", token_file=tmp_path / "token.json")
    client = CompanionClient(cfg)
    client.write_state(state_file=state_file, pid=12345)

    assert state_file.is_file()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["pid"] == 12345
    assert data["status"] == "running"
    assert "started_at" in data


def test_check_existing_instance_active(tmp_path: Path) -> None:
    state_file = tmp_path / "companion_state.json"
    state_file.write_text(json.dumps({"pid": 99999, "status": "running"}), encoding="utf-8")
    cfg = CompanionConfig(server_url="http://127.0.0.1:8765", token_file=tmp_path / "token.json")
    client = CompanionClient(cfg)

    with patch("lca.infrastructure.computer.companion.client.is_process_alive", return_value=True):
        assert client.is_another_instance_running(state_file=state_file) is True

    with patch("lca.infrastructure.computer.companion.client.is_process_alive", return_value=False):
        assert client.is_another_instance_running(state_file=state_file) is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/infrastructure/computer/test_companion_state.py -v
```
Expected: FAIL（`write_state` 和 `is_another_instance_running` 未定义）。

**Step 3: Write minimal implementation**

在 `lca/infrastructure/computer/companion/client.py` 中引入 `is_process_alive` 辅助工具函数，并为 `CompanionClient` 实现状态读写与 PID 互斥检查方法：
- `write_state(state_file, pid)`
- `clear_state(state_file)`
- `is_another_instance_running(state_file)`
在 `cli.py` 的 `run` 命令入口处加入前置检查，避免重复拉起。

**Step 4: Run test to verify it passes**

```bash
pytest tests/infrastructure/computer/test_companion_state.py -v
```
Expected: PASS（2 passed）。

**Step 5: Commit**

```bash
git add lca/infrastructure/computer/companion/ tests/infrastructure/computer/test_companion_state.py
git commit -m "feat(companion): add pid lock and runtime state persistence"
```

---

### Task 2: 服务端动态直下脚本与 Fast-Path 秒启增强 (`routes.py`)

**Files:**
- Modify: `lca/plugins/transport/device_hub/routes/routes.py`
- Modify: `lca/plugins/transport/webserver/routes_1/routes_device.py`
- Modify: `tests/lca_plugins/transport/webserver/test_install_scripts.py`
- Does NOT own: `deploy/lobehub/patches/`, `lca/core/`, `lca/cognition/` (AP-01)
- Invariants to test:
  - `install.ps1` 包含 Fast-Path 检测，检测到有效 Token 时跳过 Python 搜寻与 pip 安装；
  - `GET /api/device/download/runner.bat` 成功返回包含 Host 与 Code 的直接可执行批处理文件；
  - `GET /api/device/download/runner.command` 返回包含 chmod/可执行的脚本 (AP-02)。

**Step 1: Write the failing test**

在 `tests/lca_plugins/transport/webserver/test_install_scripts.py` 中追加用例：
```python
def test_install_ps1_contains_fast_path() -> None:
    req = build_request(path="/api/device/install.ps1", query_params={"code": "FAST-TEST"})
    res = run_async(install_ps1(req))
    text = res.body.decode("utf-8")
    assert "companion_token.json" in text
    assert "Fast-Path" in text or "fast_path" in text.lower()


def test_download_runner_bat_endpoint() -> None:
    req = build_request(path="/api/device/download/runner.bat", query_params={"code": "BAT-TEST"})
    res = run_async(download_runner_bat(req))
    assert res.status_code == 200
    assert "attachment; filename=\"lca-runner.bat\"" in res.headers.get("content-disposition", "")
    text = res.body.decode("utf-8")
    assert "BAT-TEST" in text
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/lca_plugins/transport/webserver/test_install_scripts.py -v
```
Expected: FAIL（`download_runner_bat` 未定义，`install.ps1` 缺 Fast-Path 标识）。

**Step 3: Write minimal implementation**

在 `lca/plugins/transport/device_hub/routes/routes.py` 中：
1. 强化 `install.ps1` 与 `install.sh`：在开头加入 Fast-Path 分支，若 `~/.lca/companion_token.json` 存在且包含 `machine_token`，直接启动已有 Python 与脚本，跳过环境检查；
2. 新增 `download_runner_bat(request)` 与 `download_runner_command(request)` 端点，直接输出带 Content-Disposition 的附件下载流；
3. 在 `lca/plugins/transport/webserver/routes_1/routes_device.py` 的 `ROUTE_SPECS` 中注册这两个新端点。

**Step 4: Run test to verify it passes**

```bash
pytest tests/lca_plugins/transport/webserver/test_install_scripts.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add lca/plugins/transport/device_hub/routes/routes.py lca/plugins/transport/webserver/routes_1/routes_device.py tests/lca_plugins/transport/webserver/test_install_scripts.py
git commit -m "feat(routes): add fast-path execution and dynamic runner download endpoints"
```

---

### Task 3: 前端 UI 补丁升级（解禁离线行、双模弹窗与配对码剥离）

**Files:**
- Modify: `deploy/lobehub/patches/ui/execution_target.py`
- Modify: `tests/scenario/lobehub_0/test_lobehub_execution_target.py`
- Does NOT own: `lca/plugins/`, `lca/core/`, 其余 22 个 LobeHub patches (AP-01)
- Invariants to test:
  - 补丁后的 `HeteroDeviceSwitcher.tsx` 绝对不包含 `disabled={!d.online}`；
  - 主界面彻底剔除 `pairingInput` 输入框与 `handlePairSubmit`；
  - 离线设备点击唤起包含“一键下载并启动”和“复制命令”的双模浮层；
  - 设备上线后触发自动绑定回调 (AP-02)。

**Step 1: Write the failing test**

在 `tests/scenario/lobehub_0/test_lobehub_execution_target.py` 中扩展测试：
```python
def test_patch_unblocks_offline_devices_and_strips_code_input() -> None:
    patched = _patch_switcher(_SWITCHER.read_text(encoding="utf-8"))
    # Invariant 1: 离线行不再置灰阻断
    assert "disabled={!d.online}" not in patched
    # Invariant 2: 主视图无多余的手动输码框
    assert "className={styles.pairingInput}" not in patched
    # Invariant 3: 包含双模唤醒引导
    assert "一键下载并启动" in patched or "runner.bat" in patched
    assert "CopyButton" in patched
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/scenario/lobehub_0/test_lobehub_execution_target.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

修改 `deploy/lobehub/patches/ui/execution_target.py`：
1. `_patch_switcher`: 移除 `disabled={!d.online}`；点击离线行改为打开连接弹窗；
2. 升级 JSX 浮层：
   - 展现大号绿色主操作按钮：调用 `/lca-api/api/device/download/runner.bat?code=...` 触发直接下载；
   - 展现复制命令代码块与 `@lobehub/ui` 的 `CopyButton`；
   - 彻底删除 `pairingInputRow` 与手动提交逻辑；
   - 增加监听器：`devices.find(d => d.online)` 时自动调用 `selectExecutionTarget` 并关闭弹窗。

**Step 4: Run test to verify it passes**

```bash
pytest tests/scenario/lobehub_0/test_lobehub_execution_target.py -v
```
Expected: PASS。

**Step 5: Apply patch and verify integrity**

```bash
python scripts/patch_lobehub.py --verify
```
Expected: 23/23 patches passed。

**Step 6: Commit**

```bash
git add deploy/lobehub/patches/ui/execution_target.py tests/scenario/lobehub_0/test_lobehub_execution_target.py
git commit -m "feat(ui): unblock offline devices and introduce dual-mode auto launcher modal"
```

---

### Task 4: 全链路回归、代码门禁与架构守卫验证

**Files:**
- Run all related test suites
- Run ruff & git diff check
- Verify AP-01 negative boundaries

**Step 1: Run comprehensive regression suite**

```bash
PYTHONPATH=.:vendor/cordis/src:vendor/cosmokit/src:vendor/schemastery/src pytest \
  tests/infrastructure/computer/test_companion_state.py \
  tests/lca_plugins/transport/webserver/test_install_scripts.py \
  tests/scenario/lobehub_0/test_lobehub_execution_target.py \
  tests/infrastructure/computer/test_companion_client.py -v
```
Expected: All tests PASS.

**Step 2: Run linter and formatting checks**

```bash
ruff check lca/infrastructure/computer/companion/ lca/plugins/transport/device_hub/ deploy/lobehub/patches/ui/ tests/
git diff --check
```
Expected: 0 errors, clean git diff check.

**Step 3: Verify negative boundaries (Does NOT own)**

```bash
git status --short
```
Confirm: No modified files outside `companion/`, `device_hub/`, `deploy/lobehub/patches/ui/`, `tests/` and docs.

**Step 4: Update task.md and commit final milestone**

```bash
git add docs/plans/task.md
git commit -m "chore(plans): finalize implementation plan for local machine auto-install"
```

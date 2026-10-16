# 浏览器预览卡片与实时接管（Browser Preview & Live Takeover）实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 在聊天消息流中内嵌实时微缩浏览器卡片，支持一键点击在右侧滑出全功能浏览器抽屉，通过原生 CDP Screencast 与双向 WebSocket 实现毫秒级投屏推流与人工键鼠实时接管。

**Architecture:** 严格遵循 DDD 单向分层（Contracts → Infrastructure → Transport → Cognition → UI）：
1. 契约层提供不可变 DTO 模型（`frozen=True, extra="forbid"`）；
2. 基础设施层封装 `PlaywrightCDPDriver` 与 `CDPScreencastRelay`，直接使用 Chromium 原生 CDP `Page.startScreencast` 与 `Input.dispatch*`；
3. 传输层落地 REST 与 WebSocket 混合通信长连接路由插件；
4. 认知层维护 `BrowserSubagent` 无发声铁律 (INV-05) 与单写接管状态机；
5. 前端表现层通过声明式补丁挂载 `BrowserPreviewCard` 与 `BrowserViewerDrawer`。

**Tech Stack:** Python 3.11+, Pydantic v2, Playwright / CDP, Starlette WebSocket, React 19, TypeScript, Ant Design / @lobehub/ui, HTML5 Canvas API.

---

### Task 1: 契约层与 DTO 域模型 (Contracts Layer)

**Files:**
- Create: `lca/contracts/models/browser/stream.py`
- Modify: `lca/contracts/models/browser/__init__.py`
- Test: `tests/contracts/test_browser_stream_contracts.py`
- Does NOT own: 基础设施 Playwright 驱动、网关路由、前端 React 代码 (AP-01)。
- Invariants to test: `INV-BROWSER-01`（模型严格不可变 `frozen=True`，严禁额外字段 `extra="forbid"`，非法状态枚举抛出 `ValidationError`）。

**Step 1: Write the failing test**

```python
# tests/contracts/test_browser_stream_contracts.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
)

def test_browser_session_summary_immutability():
    summary = BrowserSessionSummary(
        session_id="sess_123",
        url="https://example.com",
        title="Example Domain",
        status=BrowserSessionStatus.IDLE,
    )
    assert summary.session_id == "sess_123"
    with pytest.raises(ValidationError):
        summary.url = "https://mutated.com"  # 必须不可变

def test_browser_input_event_extra_forbid():
    with pytest.raises(ValidationError):
        BrowserInputEvent(
            type=BrowserInputEventType.MOUSE_DOWN,
            x=0.5,
            y=0.5,
            extra_hacked_field="malicious",  # 严禁未知字段
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_browser_stream_contracts.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'lca.contracts.models.browser.stream')

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/browser/stream.py
from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

class BrowserSessionStatus(StrEnum):
    IDLE = "idle"
    AGENT_RUNNING = "agent_running"
    WAITING_USER_CONTROL = "waiting_user_control"
    HUMAN_TAKEOVER = "human_takeover"
    CLOSED = "closed"

class BrowserInputEventType(StrEnum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    WHEEL = "wheel"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"

class BrowserInputEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: BrowserInputEventType
    x: float = Field(0.0, description="视口坐标 X (0.0~1.0 或绝对像素)")
    y: float = Field(0.0, description="视口坐标 Y (0.0~1.0 或绝对像素)")
    button: str | None = Field(None, description="left / right / middle")
    delta_x: float = 0.0
    delta_y: float = 0.0
    key: str | None = None
    code: str | None = None
    text: str | None = None

class BrowserSessionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    session_id: str
    run_id: str | None = None
    url: str = "about:blank"
    title: str = "New Tab"
    status: BrowserSessionStatus = BrowserSessionStatus.IDLE
    viewport_width: int = 1280
    viewport_height: int = 800
    has_active_stream: bool = False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_browser_stream_contracts.py -v`  
Expected: PASS (2/2 passed)

**Step 5: Commit**

```bash
git add lca/contracts/models/browser/ tests/contracts/test_browser_stream_contracts.py
git commit -m "feat(contracts): add immutable browser stream and input event DTO models"
```

---

### Task 2: 基础设施驱动与 Screencast 中继器 (Infrastructure Driver & Relay)

**Files:**
- Create: `lca/contracts/protocols/browser.py`, `lca/infrastructure/browser/cdp_driver.py`, `lca/infrastructure/browser/screencast_relay.py`
- Modify: `lca/infrastructure/browser/__init__.py`
- Test: `tests/infrastructure/browser/test_cdp_screencast_relay.py`
- Does NOT own: Web 路由、HTTP 解析、UI 补丁。
- Invariants to test: `INV-BROWSER-04`（Screencast 二进制帧封装 `0x01` + JPEG 字节，ACK 节流队列有界）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/browser/test_cdp_screencast_relay.py
import pytest
from unittest.mock import AsyncMock
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay

@pytest.mark.asyncio
async def test_relay_encodes_binary_frame_with_0x01_header():
    mock_ws = AsyncMock()
    relay = CDPScreencastRelay(session_id="test_sess")
    relay.register_client(mock_ws)
    
    jpeg_bytes = b"\xff\xd8\xff\xe0testjpegimage"
    await relay.emit_frame(data=jpeg_bytes, metadata={"width": 1280, "height": 800})
    
    assert mock_ws.send_bytes.called
    sent_payload = mock_ws.send_bytes.call_args[0][0]
    assert sent_payload[0] == 0x01  # 帧类型标识
    assert sent_payload[1:] == jpeg_bytes
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/browser/test_cdp_screencast_relay.py -v`  
Expected: FAIL (No module named CDPScreencastRelay)

**Step 3: Write minimal implementation**

实现 `CDPScreencastRelay`：
- 支持客户端 WS 注册与注销；
- `emit_frame` 拼接 `0x01` 字节头并广播到客户端；
- 内置 `_in_flight_ack` 计数器，未确认帧超过阈值时触发自动丢帧节流。

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/browser/test_cdp_screencast_relay.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/protocols/ lca/infrastructure/browser/ tests/infrastructure/browser/
git commit -m "feat(infra): implement CDPScreencastRelay with binary framing and backpressure"
```

---

### Task 3: 网关传输层 REST 与 WebSocket 通道 (Transport Layer)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_browser.py`
- Modify: `lca/plugins/transport/webserver/carrier/web_app.py`
- Test: `tests/transport/test_browser_gateway_routes.py`
- Does NOT own: 复杂 Agent 认知推理逻辑、LobeHub 内部存储。
- Invariants to test: `INV-BROWSER-05`（WebSocket 建立握手、二进制帧收发、会话销毁端到端闭环）。

**Step 1: Write the failing test**

```python
# tests/transport/test_browser_gateway_routes.py
import pytest
from starlette.testclient import TestClient
from lca.plugins.transport.webserver.carrier.web_app import create_app

def test_browser_sessions_rest_discovery():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/lca-api/browser/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/transport/test_browser_gateway_routes.py -v`  
Expected: FAIL (404 Not Found)

**Step 3: Write minimal implementation**

实现 `routes_browser.py`：
- `GET /lca-api/browser/sessions`：列出当前活跃浏览器会话；
- `GET /lca-api/browser/sessions/{session_id}`：获取单个会话最新快照；
- `WEBSOCKET /lca-api/browser/sessions/{session_id}/stream`：双向串流通道，转发下行图像与上行键鼠。

**Step 4: Run test to verify it passes**

Run: `pytest tests/transport/test_browser_gateway_routes.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/ tests/transport/test_browser_gateway_routes.py
git commit -m "feat(transport): add REST and WebSocket streaming endpoints for browser sessions"
```

---

### Task 4: 接管状态机与认知子代理纯洁性 (Arbitration & Cognition)

**Files:**
- Create: `lca/infrastructure/browser/arbitration.py`
- Modify: `lca/infrastructure/browser/subagent.py`
- Test: `tests/infrastructure/browser/test_browser_arbitration.py`, `tests/infrastructure/browser/test_browser_subagent_purity.py`
- Does NOT own: 前端界面渲染。
- Invariants to test: `INV-BROWSER-02`（子代理无发声工具 INV-05）与 `INV-BROWSER-03`（`AGENT_RUNNING` 态下物理屏蔽上行 input 事件）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/browser/test_browser_subagent_purity.py
from lca.infrastructure.browser.subagent import BrowserSubagent

def test_browser_subagent_has_no_voice():
    agent = BrowserSubagent()
    tools = agent.get_tools()
    for tool in tools:
        assert getattr(tool, "name", "") != "send_message"
```

**Step 2: Run test to verify it fails** (或验证既有断言)

Run: `pytest tests/infrastructure/browser/test_browser_subagent_purity.py -v`

**Step 3: Write minimal implementation**

实现 `BrowserArbitrationEngine`：
- 管理 `IDLE` / `AGENT_RUNNING` / `WAITING_USER_CONTROL` / `HUMAN_TAKEOVER`；
- 仲裁拦截：当处于 `AGENT_RUNNING` 时，`handle_user_input` 触发静默丢弃并返回 `rejected_due_to_agent_busy`；
- 接管切换：支持从前端提交 `takeover=True` 请求，将状态机切至 `HUMAN_TAKEOVER` 并向主图发出等待信号。

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/browser/test_browser_arbitration.py tests/infrastructure/browser/test_browser_subagent_purity.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/browser/ tests/infrastructure/browser/
git commit -m "feat(cognition): enforce voiceless subagent INV-05 and control arbitration state machine"
```

---

### Task 5: LobeHub 前端卡片与滑出抽屉 (Frontend UI Patches)

**Files:**
- Create:
  - `deploy/lobehub/patches/ui/browser/BrowserPreviewCard.tsx`
  - `deploy/lobehub/patches/ui/browser/BrowserViewerDrawer.tsx`
  - `deploy/lobehub/patches/ui/browser/components/BrowserCanvas.tsx`
  - `deploy/lobehub/patches/ui/browser/components/BrowserToolbar.tsx`
  - `deploy/lobehub/patches/ui/browser_preview_card.py`
  - `deploy/lobehub/patches/ui/browser_viewer_drawer.py`
- Modify: `deploy/lobehub/patch_lobehub.py`
- Test: `tests/deploy/test_lobehub_browser_patch.py`
- Does NOT own: Python 后端核心业务。
- Invariants to test: `INV-BROWSER-06`（Canvas 归一化坐标转换与补丁 byte-identical 门禁）。

**Step 1: Write the failing test**

```python
# tests/deploy/test_lobehub_browser_patch.py
from deploy.lobehub.patch_lobehub import get_all_patches

def test_browser_patches_registered():
    patches = get_all_patches()
    patch_names = [p.name for p in patches]
    assert "browser_preview_card" in patch_names
    assert "browser_viewer_drawer" in patch_names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/deploy/test_lobehub_browser_patch.py -v`  
Expected: FAIL

**Step 3: Write minimal implementation**

- 编写 React 19 组件：
  - `BrowserPreviewCard`：响应式展示 URL、Title 与微缩截图，提供“接管”按键；
  - `BrowserViewerDrawer`：右侧抽屉，内置地址栏、控制权切换按键；
  - `BrowserCanvas`：通过 WebSocket 解码二进制 JPEG 绘制并捕获鼠标滚轮按键；
- 编写声明式补丁挂载到 LobeHub 聊天流中。

**Step 4: Run test to verify it passes**

Run: `pytest tests/deploy/test_lobehub_browser_patch.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add deploy/lobehub/ tests/deploy/
git commit -m "feat(ui): add BrowserPreviewCard and BrowserViewerDrawer patches for LobeHub"
```

---

### Task 6: 端到端全链路集成回归与代码门禁 (Regression & Gate Check)

**Files:**
- Create: `tests/scenario/browser/test_browser_preview_and_takeover_e2e.py`
- Test: 全量浏览器套件 + `ruff check` + `ruff format` + `git diff --check`.
- Does NOT own: 任何与浏览器无关的既有单测文件。
- Invariants to test: 覆盖 `INV-BROWSER-01` 至 `INV-BROWSER-06` 100% 达标。

**Step 1: Run comprehensive test suite**

Run: `pytest tests/contracts/test_browser_stream_contracts.py tests/infrastructure/browser/ tests/transport/test_browser_gateway_routes.py tests/deploy/test_lobehub_browser_patch.py tests/scenario/browser/ -v`  
Expected: PASS (全量绿灯)

**Step 2: Run style and hygiene gates**

Run: `ruff check lca/ tests/ deploy/`  
Run: `git diff --check`  
Expected: 0 warnings, 0 errors, 0 trailing whitespaces.

**Step 3: Commit**

```bash
git add tests/scenario/browser/
git commit -m "test(scenario): complete end-to-end regression test for browser preview and live takeover"
```

---

## Plan Complete and Saved

**Plan complete and saved to `docs/plans/2026-10-16-browser-preview-and-takeover-plan.md`.**  
**Next step: run `.agent/workflows/execute-plan.md` to execute this plan task-by-task in single-flow mode.**

# 浏览器预览卡片与实时接管（Browser Preview & Live Takeover）架构设计文档

- **状态**: Approved (已获用户呈批通过)
- **日期**: 2026-10-16
- **决策者**: 李超 / Antigravity
- **关联规范**: ADR-0248（协调型桌面 Agent 运行时）、ADR-0246（用户机副作用平面）、LCA C1~C14 架构不变量
- **自治等级**: DRAFT (AP-05)

---

## 1. 业务背景与第一性原理 (Context & First Principles)

在桌面 AI 智能体产品（如 **xAI Grok Bot** 与 **Meta Muse**）中，“**拥有带浏览器的电脑**”是 Agent 从单纯的文本问答迈向能够替用户办理实际业务（检索深度信息、预订票务、跨系统填表、过验证码与鉴权）的关键能力支撑。

### 1.1 核心痛点与产品诉求
当前传统聊天界面的浏览器交互存在三大断层：
1. **黑盒无感知**：Agent 在后台做爬虫或无头浏览，用户只能等待几分钟后的一段文字总结，中间卡在什么步骤（如遇验证码、死循环跳转、报错）完全不可见；
2. **人工无法介入**：当 Agent 遇到复杂的滑动验证码、Cloudflare 人机验证、2FA 双因子短信验证或支付确认时，自动化完全瘫痪，缺乏人机接管（Human-in-the-Loop）桥梁；
3. **架构臃肿沉重**：常见远程桌面方案往往在宿主机强行安装 X11、Xvfb、VNC、WebRTC 媒体转发服务器，占用大量内存与 CPU，极易出现僵尸进程与端口泄漏。

### 1.2 第一性原理方案解题
1. **消息流内紧凑表达**：聊天气泡内嵌入轻量 `BrowserPreviewCard`，展示当前网页 Favicon、标题、实时微缩截图与状态徽标；
2. **右侧全功能滑出抽屉**：点击卡片右侧顺滑拉出 `BrowserViewerDrawer`，提供地址栏、导航按键、人机接管开关与高帧率 `<canvas>` 视口；
3. **原生 CDP Screencast 零依赖极速串流**：直接复用 Chromium 引擎内置的 Chrome DevTools Protocol (CDP) `Page.startScreencast`，通过双向 WebSocket 以纯二进制帧下行推送画幅、JSON 帧上行回传键鼠操作，实现毫秒级端到端投屏与人机接管，服务端无需任何 X11 或 VNC 桌面环境。

---

## 2. 系统边界与职责划分 (Mandatory Boundaries - AP-01)

### 2.1 明确建设范围 (Owns)
1. **契约层 (Contracts)**：
   - 落地 `BrowserStreamPacket`、`BrowserInputEvent`、`BrowserSessionSummary`、`BrowserSessionStatus` 等不可变 DTO 模型（`frozen=True, extra="forbid"`）；
   - 扩展 [BrowserAction](file:///home/lichao/layered-cognitive-agent/lca/contracts/models/browser/models.py) 与 [DesktopLock](file:///home/lichao/layered-cognitive-agent/lca/contracts/models/browser/models.py#L47-L60) 契约，支持 `TAKEOVER` 与 `RELEASE` 人闸状态。
2. **基础设施层 (Infrastructure)**：
   - `BrowserDriverPort` 抽象驱动端口协议；
   - `PlaywrightCDPDriver`：管理本地 Headless Chromium 实例、动态 CDP 会话池与生命周期；
   - `CDPScreencastRelay`：捕获 `Page.screencastFrame`、处理 ACK 节流与背压、上行调用 `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent`。
3. **网关与传输层 (Gateway / Transport)**：
   - 落地 `lca-browser-runtime` 声明式插件；
   - REST 路由：`/lca-api/browser/sessions`（会话元数据、当前 URL、活跃状态、接管申请）；
   - WebSocket 路由：`/lca-api/browser/sessions/{session_id}/stream`（混合协议双向长连接）。
4. **认知与图化集成 (Cognition & Graph)**：
   - 将既有的 [BrowserSubagent](file:///home/lichao/layered-cognitive-agent/lca/infrastructure/browser/subagent.py) 升级接入真实 `BrowserDriverPort`；
   - 严格维护 **INV-05 物理禁声铁律**（子代理无发声工具，仅向主图输出结构化结果）；
   - 将浏览器执行封装为声明式认知图算子 `act.browser.execute` 与人闸断点 `act.browser.human_gate`。
5. **前端表现层 (LobeHub UI Patches)**：
   - `BrowserPreviewCard.tsx`：聊天气泡卡片，呈现微缩实时图与接管状态；
   - `BrowserViewerDrawer.tsx`：右侧全功能滑出抽屉（包含 `BrowserToolbar`、`BrowserCanvas` 与 `BrowserStatusBar`）。

### 2.2 负向保护边界 (Does NOT own - 严禁触碰)
- **严禁改动 LCA 认知五相闭集**（`perceive → think → act → reflect → remember`）与核心事件目录（C1/C11）；
- **严禁在宿主机安装 X11/Xvfb/VNC/WebRTC 外部桌面套件**，保持服务端零额外系统级依赖；
- **严禁改动或破坏既有 ADR-0246 本机 Companion 路由与已配对设备**；
- **严禁绕过 Reducer 或向 Session 事实流伪造未发生的执行事实**（C2/C4）；
- **严禁向 LCA 仓库提交宿主机级运维逻辑或外部工具**。

---

## 3. 核心分层架构与模块化设计

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        前端表现层 (LobeHub UI)                         │
│  ┌───────────────────────┐          ┌───────────────────────────────┐  │
│  │ 聊天气泡: BrowserCard  │ ──点击──> │ 右侧抽屉: BrowserSidePanel    │  │
│  │ (实时缩略图/URL/状态)  │          │ (交互 Canvas + 控制条 + 接管态)│  │
│  └───────────────────────┘          └──────────────┬────────────────┘  │
└────────────────────────────────────────────────────┼───────────────────┘
                                       WebSocket (双向流: 画面帧 + 键鼠事件)
┌────────────────────────────────────────────────────┼───────────────────┐
│                    传输与网关层 (LCA Gateway / Carrier)                │
│  - REST/WS 路由: 会话生命周期管理、状态同步、单屏互斥锁仲裁               │
└────────────────────────────────────────────────────┼───────────────────┘
                                                     │
┌────────────────────────────────────────────────────┴───────────────────┐
│                    执行与认知平面 (LCA Engine)                          │
│  - 认知层: BrowserSubagent (无发声工具 INV-05，仅输出结构化状态与截图) │
│  - 驱动层: Playwright / Chromium 原生 CDP (Chrome DevTools Protocol)   │
│  - 人闸: request_browser_help (遭遇验证码/2FA/支付/用户主动点击接管)   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 契约模型 (Contracts)

```python
class BrowserSessionStatus(StrEnum):
    IDLE = "idle"
    AGENT_RUNNING = "agent_running"
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
    x: float = Field(0.0, description="归一化 X 坐标 (0.0 ~ 1.0) 或绝对视口像素")
    y: float = Field(0.0, description="归一化 Y 坐标 (0.0 ~ 1.0) 或绝对视口像素")
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

### 3.2 声明式图集成 (Graph Integration - C14)
- **`act.browser.execute` 节点**：执行无发声原子导航、点按与键入，产出 `BrowserActionResult` 事实；
- **`act.browser.human_gate` 节点**：当遇到登录、CAPTCHA、2FA 或用户在前端点击接管时，图引擎状态转换为挂起等待，向前端抛出人闸通知；用户在抽屉完成操作并交还后，经标准 `/lca-api/runs/{run_id}/answer` 恢复执行，保持图引擎与业务逻辑互不侵入。

---

## 4. 传输协议与时序设计 (Protocols & Data Flow)

### 4.1 WebSocket 混合通信帧协议
连接路径：`/lca-api/browser/sessions/{session_id}/stream`
- **下行画面帧（服务端 → 前端）**：
  - 二进制帧（Binary Frame）：以 `0x01` 字节作为 Header，后续直接拼接原始 JPEG/WebP 图像流字节。前端 `<canvas>` 通过 `createImageBitmap` GPU 零拷贝渲染；
  - 文本帧（JSON Frame）：传递 `metadata`（URL、Title、视口尺寸）及 `status_change` 状态广播。
- **上行控制帧（前端 → 服务端）**：
  - JSON 文本帧：
    - `{"type": "input", "event": {"type": "mouse_down", "x": 640, "y": 360, "button": "left"}}`
    - `{"type": "control", "action": "navigate", "url": "https://..."}`
    - `{"type": "takeover", "enabled": true}`

### 4.2 单写所有权仲裁状态机 (Control Arbitration)

```text
┌─────────────────┐       Agent 启动任务        ┌───────────────────────┐
│      IDLE       │ ─────────────────────────>  │     AGENT_RUNNING     │
│   (就绪闲置)     │                             │ (AI 独占操控 / 前端穿透只读)│
└─────────────────┘                             └──────────┬────────────┘
         ▲                                                 │
         │ 关闭会话                                遇验证码 / 用户点“接管”
         │                                                 │
         │                                                 ▼
┌─────────────────┐       用户点“交还 AI”        ┌───────────────────────┐
│     CLOSED      │ <─────────────────────────  │    HUMAN_TAKEOVER     │
│    (资源释放)    │   (触发 500ms 抖动静默，    │ (人类独占控制 / Agent 挂起)│
└─────────────────┘    更新 DOM 截屏后唤醒)       └───────────────────────┘
```

---

## 5. 架构不变量与自动化测试验证矩阵 (AP-02)

| 不变量 ID | 不变量描述 | 自动化守护手段 |
|---|---|---|
| **INV-BROWSER-01** | **契约不可变性**：所有浏览器流式 DTO 必须为 `frozen=True` 且 `extra="forbid"` | Pydantic 校验单元测试，针对非法字段与修改操作断言 `ValidationError` |
| **INV-BROWSER-02** | **物理禁声铁律**：`BrowserSubagent` 工具集严禁包含 `send_message` 或任何声带发声工具 | 遍历工具列表断言 `tool.name != "send_message"`，单测守护 [INV-05](file:///home/lichao/layered-cognitive-agent/lca/infrastructure/browser/subagent.py#L20) |
| **INV-BROWSER-03** | **单写所有权互斥**：在 `AGENT_RUNNING` 状态下，系统必须物理拦截/忽略一切非授权上行键鼠事件 | 状态机单元测试断言 `AGENT_RUNNING` 下注入 input 事件被安全丢弃并记录审计 |
| **INV-BROWSER-04** | **背压与 ACK 节流**：Screencast 中继器必须在收到客户端或内部 ACK 后才发出下一帧，缓冲区有界 | 模拟慢消费者测试，断言队列最大缓冲深度与丢帧降级机制 |
| **INV-BROWSER-05** | **零孤儿进程优雅清理**：会话关闭（Close）时，必须幂等释放 Chromium Page、CDP Session 与单屏锁 | 生命周期测试断言 `session.close()` 后进程存活状态与端口已完全释放 |
| **INV-BROWSER-06** | **视口归一化坐标精度**：前端 Canvas 点击坐标转换必须在 `[0, 1]` 归一化区间，且支持视网膜高清屏高 DPI 自适应 | 坐标数学映射纯函数单测，测试各种比例拉伸与非等比缩放计算 |

---

## 6. 实施切片与落地计划 (Milestones)

1. **M1: 契约与端口层**：落地 `BrowserStreamPacket`、`BrowserInputEvent` 等模型与 `BrowserDriverPort` 抽象；
2. **M2: 驱动与 Screencast 中继器**：实现 `PlaywrightCDPDriver` 与 `CDPScreencastRelay`，编写中继与节流单测；
3. **M3: 网关 REST 与 WebSocket 端点**：落地 `/lca-api/browser/sessions` 与 `/stream` 路由插件并完成端到端模拟测试；
4. **M4: 认知子代理与人闸接管联动**：升级 `BrowserSubagent`，挂载状态机与单屏锁，编写仲裁与禁声测试；
5. **M5: LobeHub 前端 UI 补丁**：实现 `BrowserPreviewCard` 与 `BrowserViewerDrawer`，集成测试与样式自适应；
6. **M6: 端到端全链路回归**：全套自动化单测回归与 `pre-push` 架构门禁体检。

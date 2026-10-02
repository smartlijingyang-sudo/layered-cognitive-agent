# Connectors UI, Universal Dynamic Avatar & Run Fixes Architecture Design

> **Author**: Antigravity & User Pairing  
> **Date**: 2026-10-02  
> **Topic**: 连接器中枢（Connectors Hub）、会话流授权卡片、全助理普惠动态 Avatar 与近期 Run 缺陷系统性治理  
> **Autopilot Ladder**: `DRAFT` (AP-05)

---

## 1. 背景与核心问题识别

在近期真实会话与任务执行中（涵盖 `run_c83d95ce33eb`、`run_07bea3391322`、`run_bebc92b4d30a` 等），暴露出以下两项系统性缺陷与三项产品体验断层：

1. **Answer 翻倍追加（Bug 1）**：在 `lca/application/runtime/coordinator/event_translator.py` 中，`llm.stream.token` 已逐 token 生成 `chunkType: "text"` 追加到前端气泡，但模型生成完毕时发出的 `llm.request.header.assistant` 又携带了完整的 `assistant_content` 并被盲目以 `snapshotMode: "append"` 再次派发，导致前端回复内容瞬间被全量重复追加一遍。
2. **邮件查询低智误判（Bug 2）**：Composio 的 `GMAIL_FETCH_EMAILS` 接口返回包含超大 HTML 详情（单封 23KB+），无参默认仅返回 1 封邮件。当用户提问“看看我最近有什么邮件”时，Agent 无参调用该工具后看到仅 1 条记录，便得出“收件箱只有 1 封”的荒谬结论；只有在被要求“列个表 10 封”时才被迫切换到 `GMAIL_LIST_THREADS`。缺少首选概览工具引导与 `max_results` 防空跑约定。
3. **第三方服务连接体验生硬（Feature 1）**：连接 Gmail 等生态连接器时，Agent 仅输出裸 Markdown 超链接，缺少原生 LobeHub 级别的品牌卡片、弹窗授权与自动轮询状态反馈。
4. **抽屉缺少连接器管理中枢（Feature 2）**：右侧状态抽屉仅有 Markdown 文件预览（Identity/Rules/Memory/Workspace），缺少与文件平行的 `⚡ Connectors` Tab，用户无法集中查看与管理拥有的全部第三方生态连接器与工具能力。
5. **顶栏 Avatar 体验与全助理规范缺失（Feature 3 & 4）**：
   - 现存 Avatar 头部靠上被顶栏边界裁剪，且生硬无业界顶级微动质感；
   - 缺少全助理通用的 Avatar 分发与演化机制（显式配置 / 语义推导 / 确定性哈希随机 / 默认兜底）；
   - 缺少在会话流中通过选项卡片（如“恐龙”主题卡片）挑选形象的交互能力，且抽屉缺少便捷编辑修改的闭环入口。

---

## 2. 架构负向边界与自治阶梯 (AP-01 & AP-05)

### 2.1 Mandatory Boundaries (AP-01)
* **Owns（本设计负责实现与修改的范围）**：
  1. `lca/application/runtime/coordinator/event_translator.py`：建立流式 Token 与 Header Assistant 互斥消重机制；
  2. `lca/infrastructure/tools/composio/__init__.py`：重塑 Gmail 等工具元数据与调用规范，明确 `GMAIL_LIST_THREADS` 概览首选与 `max_results` 约束；
  3. `deploy/lobehub/patches/ui/AssistantTopMascot.tsx`：全助理通用普惠动态 Avatar（OpenAI/Muse 顶级有机粒子环与眨眼/呼吸动效），解决头部切顶 Bug；
  4. `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`：集成顶部 Profile 编辑笔菜单，新增 `⚡ Connectors` 全局连接器中枢 Tab；
  5. `deploy/lobehub/patches/ui/` 新增组件：
     - `ConnectorAuthCard.tsx`：会话流内的优雅 OAuth 授权交互卡片（带品牌 Icon、弹窗监听与自动打字轮询）；
     - `ConnectorsPanel.tsx`：抽屉内全局连接器列表、状态徽标、助理使用开关与工具清单展开抽屉；
     - `AssistantAvatarWidget.tsx`：会话流内多候选卡片式形象挑选器（如输入“恐龙”展示 4 张恐龙形象卡片并一键确认生效）；
  6. 契约与单元测试套件：覆盖去重逻辑、工具指引与补丁完整性。

* **Does NOT own（严格禁止修改的负向边界）**：
  1. 严禁改动宿主机系统网络或外部资产（整机运维与拓扑严格归属于 `~/everything-library`）；
  2. 严禁直接修改 `lobehub-ui/` 原生上游文件（所有变更必须通过 `deploy/lobehub/patches/` 声明式补丁落地，保持 100% byte-identical 可逆守卫）；
  3. 严禁改变 C1~C14 认知与执行闭集不变量（不新增平行事件管道，状态更新严格遵循 Session 与 Reducer 单写铁律）。

### 2.2 Autopilot Level
* 定级为 **`DRAFT`**。单流渐进式开发，必须经由测试不变量断言验证与 Git 提交核验。

---

## 3. 详细设计与实现机制

### 3.1 Answer 文本去重流式守卫 (Bug 1)
在 `EventTranslator` 内部引入 `stream_started` 标识。
```python
# lca/application/runtime/coordinator/event_translator.py
@staticmethod
def _spine_llm_stream_token(e: dict) -> dict | None:
    # 逐字派发增量 append
    return {
        "type": "stream_chunk",
        "data": {
            "chunkType": kind,
            "content": delta,
            "snapshotMode": "append",
        },
    }

@staticmethod
def _spine_llm_header_assistant(e: dict) -> dict | None:
    # 若该 Step 已经由 llm.stream.token 输出过流式增量，
    # 则 Header Assistant 仅作为审计归档，绝对不可再次 append 全量文本！
    # 仅在非流式降级 (zero stream tokens) 场景下才下发补偿文本。
    payload = _inner_payload(e)
    if payload.get("stream") is True:
        return None
    content = str(payload.get("assistant_content") or "")
    if not content:
        return None
    return {
        "type": "stream_chunk",
        "data": {"chunkType": "text", "content": content, "snapshotMode": "append"},
    }
```

### 3.2 邮件工具元数据与认知引导重构 (Bug 2)
在 `MANAGEMENT_MANIFEST` 与工具工厂中修正：
1. `GMAIL_FETCH_EMAILS`：显式声明“获取完整邮件内容（单封耗费大）。默认仅返回 1 封。若需查多封必须带 `max_results`。**若仅需浏览收件箱或列出邮件摘要，推荐使用 GMAIL_LIST_THREADS**”；
2. `GMAIL_LIST_THREADS`：显式声明“**首选推荐**：获取最近邮件主题、发件人与摘要列表，高效轻量，查邮件概览必选”。

### 3.3 全助理通用动态 Avatar 体系 (Feature 3)
1. **四级确定性渲染策略**：
   - **P1 显式配置**：`IDENTITY.md` 中 `avatar` 声明具体 emoji 或动物标识；
   - **P2 语义推导**：基于助理角色（架构→水豚 🦫、代码→灵狐 🦊、数据→海豚 🐬、写作→智鸮 🦉）；
   - **P3 哈希随机**：基于 `assistant_id` SHA-256 哈希取模，从 16 款萌系动物图鉴中映射（同一助理永久固定）；
   - **P4 兜底**：默认灵动水豚与自旋粒子光晕。
2. **视觉优化**：
   - 容器补足 `padding: 6px 12px` 与负边距校准，确保 Avatar 浑圆居中且耳尖/头顶绝对不切；
   - 搭载呼吸（Breath 3.2s）、灵动周期眨眼（Blink 4.5s）与双重渐变自旋轨道光晕（Halo Pulse 3.6s）。

### 3.4 会话流交互式选图卡片 (`AssistantAvatarWidget`) (Feature 4)
* 当用户表达“我想换头像，改成恐龙”时，Agent 触发 `[widget:avatar_picker?theme=恐龙&candidates=...]`；
* 前端气泡内呈现 3~4 张大尺寸视觉卡片（如 🦖 霸王龙、🦕 雷龙、🐉 萌幼龙、🐊 小恐龙）；
* 点击卡片即时在卡片内与顶栏预览，点击“确认使用”播放庆祝动效，后端原子更新 `IDENTITY.md` 并刷新 `agentMap`。

### 3.5 会话流连接器授权卡片 (`ConnectorAuthCard`) (Feature 1)
* 拦截 `composioConnect` 结果或授权链接；
* 渲染毛玻璃授权卡片：
  - 应用 Logo + 标题 + `🟡 等待授权` 药丸标签；
  - 授权用途说明与权限隔离提示；
  - `立即授权连接` 按钮（点击呼起 600×700 独立 OAuth 窗）；
  - 监听窗口关闭 + 自动调用 `/composio/connections/{id}/refresh` 轮询；
  - 授权完成微动平滑变为 `🟢 已连接 · 23 个工具已就绪`。

### 3.6 右侧抽屉全局连接器中枢 (`ConnectorsPanel`) (Feature 2)
在 `AssistantStatusDrawer` 中新增 `⚡ Connectors` Tab：
* 顶部状态统计：`已连接 X / 共 Y 个生态服务`；
* 卡片列表（Gmail、Google Drive、GitHub、Slack、Notion、本地伴侣等）；
* 每张卡片包含：
  - 图标、名称、简介；
  - 运行状态指示灯与“当前助理启用” Switch；
  - 展开可折叠的“查看工具清单”面板；
  - “授权连接 / 刷新 / 断开”操作按钮。

---

## 4. 自动化测试不变量矩阵 (AP-02)

| 不变量编号 | 核心断言 | 测试文件 |
|---|---|---|
| **INV-01 (流式单次交付)** | 经过 `EventTranslator` 的流式文本在单轮对话中严禁由 `llm.request.header.assistant` 再次追加 | `tests/application/runtime/test_event_translator_dedup.py` |
| **INV-02 (邮件检索导向)** | Composio 工具集中的 Gmail 描述必须包含列表查询导向与 `max_results` 防空跑约定 | `tests/infrastructure/tools/test_composio_tool_guidance.py` |
| **INV-03 (连接器真值映射)** | 右侧抽屉连接器列表必须实时映射后端 `/composio/connections` 与伴侣状态真值 | `tests/deploy/test_connector_drawer_patch.py` |
| **INV-04 (全助理Avatar分发)** | 任意 assistant_id 均能确定性解析出合法动物 avatar 与色彩，无空指针与越界 | `tests/deploy/test_assistant_avatar_resolver.py` |
| **INV-05 (补丁一致性守卫)** | 所有 LobeHub 前端补丁必须符合补丁引擎规范，`check_patch_integrity.py` 100% byte-identical | `check_patch_integrity.py` 门禁 |

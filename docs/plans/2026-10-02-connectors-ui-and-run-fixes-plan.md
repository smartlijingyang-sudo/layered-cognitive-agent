# Connectors UI, Universal Dynamic Avatar & Run Fixes Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底修复 Agent 回答翻倍及邮件查询盲点两大根因 Bug，实现全助理通用的动态萌宠 Avatar 与微动特效，并落地会话流连接器授权卡片、右侧抽屉全局连接器中枢（Connectors Hub）与卡片式形象挑选器。

**Architecture:** 
1. 传输协同层建立流式 Token 与 Header Assistant 互斥消重守卫（零冗余 append）；
2. 工具契约层完善 Gmail 列表推荐与 `max_results` 防空跑约定；
3. 前端基于 LobeHub 声明式补丁系统，构建 `AssistantTopMascot` 居中四级分发动态动物引擎、`ConnectorAuthCard` 会话流授权卡片、`ConnectorsPanel` 抽屉连接器中枢，以及 `AssistantAvatarWidget` 候选卡片换装体系。

**Tech Stack:** Python 3.10+, Starlette, Pydantic, React 19, TypeScript, Ant Design, Antd-Style, Lucide-React, Vitest/Pytest.

---

### Task 1: Answer 文本去重流式守卫 (`event_translator.py`)

**Files:**
- Modify: `lca/application/runtime/coordinator/event_translator.py:431-443`
- Test: `tests/application/runtime/test_event_translator_dedup.py`
- Does NOT own: 任何其他认知层、持久化数据库文件或前端代码 (AP-01)
- Invariants to test: INV-01 (已产生 `llm.stream.token` 的 turn，`llm.request.header.assistant` 必返回 None；未产生流式 token 的降级调用必返回补偿文本块)

**Step 1: Write the failing test**
创建 `tests/application/runtime/test_event_translator_dedup.py`：
```python
import pytest
from lca.application.runtime.coordinator.event_translator import EventTranslator

def test_stream_token_followed_by_header_assistant_does_not_duplicate():
    translator = EventTranslator()
    
    # 模拟流式 token 事件
    stream_event = {
        "event": {
            "execution_point": "llm.stream.token",
            "payload": {"text_delta": "你好", "channel_kind": "output"},
        }
    }
    translated_token = translator.translate(stream_event)
    assert translated_token is not None
    assert translated_token["type"] == "stream_chunk"
    assert translated_token["data"]["content"] == "你好"

    # 紧随其后的 header assistant（携带全量文本）必须被拦截，不可再次 append！
    header_event = {
        "event": {
            "execution_point": "llm.request.header.assistant",
            "payload": {"assistant_content": "你好", "finish_reason": "stop", "stream": True},
        }
    }
    translated_header = translator.translate(header_event)
    assert translated_header is None, "Streamed turns must not re-append full header content"

def test_non_stream_call_still_yields_header_content():
    translator = EventTranslator()
    header_event = {
        "event": {
            "execution_point": "llm.request.header.assistant",
            "payload": {"assistant_content": "非流式完整内容", "finish_reason": "stop", "stream": False},
        }
    }
    translated = translator.translate(header_event)
    assert translated is not None
    assert translated["type"] == "stream_chunk"
    assert translated["data"]["content"] == "非流式完整内容"
```

**Step 2: Run test to verify it fails**
`pytest tests/application/runtime/test_event_translator_dedup.py -v`
Expected: FAIL（header assistant 返回了重复的 chunkType: "text"）

**Step 3: Implement minimal code**
在 `lca/application/runtime/coordinator/event_translator.py` 中更新 `_spine_llm_header_assistant`：
```python
    @staticmethod
    def _spine_llm_header_assistant(e: dict) -> dict | None:
        payload = _inner_payload(e)
        # 若为流式调用（由 llm.stream.token 负责增量派发），Header 仅作归档，严禁再次向 UI append 全量内容
        if payload.get("stream") is True:
            return None
        content = str(payload.get("assistant_content") or "")
        if not content:
            return None
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": content,
                "snapshotMode": "append",
            },
        }
```

**Step 4: Run test to verify it passes**
`pytest tests/application/runtime/test_event_translator_dedup.py -v`
Expected: PASS

**Step 5: Commit**
`git add lca/application/runtime/coordinator/event_translator.py tests/application/runtime/test_event_translator_dedup.py`
`git commit -m "fix(runtime): 修复 llm.request.header.assistant 流式全量二次追加导致的回答翻倍缺陷"`

---

### Task 2: Gmail 工具元数据与概览列表推荐导向 (`composio/__init__.py`)

**Files:**
- Modify: `lca/infrastructure/tools/composio/__init__.py:18-68`
- Test: `tests/infrastructure/tools/test_composio_tool_guidance.py`
- Does NOT own: Composio 外部 SDK 或前端界面 (AP-01)
- Invariants to test: INV-02 (Gmail 工具元数据明确包含多邮件列表推荐 `GMAIL_LIST_THREADS` 与 `max_results` 防空跑说明)

**Step 1: Write failing test**
创建 `tests/infrastructure/tools/test_composio_tool_guidance.py`：
```python
from lca.infrastructure.tools.composio import MANAGEMENT_MANIFEST

def test_composio_management_manifest_has_proper_tool_contracts():
    names = [api.name for api in MANAGEMENT_MANIFEST.api]
    assert "composioConnect" in names
    assert "composioRefresh" in names
    connect_api = next(api for api in MANAGEMENT_MANIFEST.api if api.name == "composioConnect")
    assert "OAuth" in connect_api.description
```

**Step 2: Run test to verify it passes/fails and augment tool definitions**

**Step 3: Update tool descriptions and instructions**
强化 `composio/__init__.py` 中关于邮件和服务的指引说明，确保大模型检索近期邮件时首选 `GMAIL_LIST_THREADS` 并显式携带 `max_results`。

**Step 4: Run tests & Commit**
`git commit -m "feat(composio): 强化 Gmail 工具列表查询指引与防单封空跑约定"`

---

### Task 3: 全助理通用普惠动态 Avatar (`AssistantTopMascot.tsx` & 确定性解析器)

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantTopMascot.tsx`
- Test: `tests/deploy/test_assistant_avatar_resolver.py`
- Does NOT own: 任何后端核心模型文件 (AP-01)
- Invariants to test: INV-04 (确定性四级分发：显式配置 > 语义推导 > 稳定哈希随机 > 默认兜底，绝不抛出异常，头部保证不被裁剪)

**Step 1: Write test for Avatar resolver logic**
验证任意 `assistant_id` 均能稳定映射到合法动物图鉴（Capybara, Dino, Fox, Owl, Dolphin, Panda 等）且色彩搭配稳定。

**Step 2: Implement dynamic avatar rendering in AssistantTopMascot.tsx**
- 扩展 `styles.container` 与 `avatarWrapper` 具有充足的 `padding-top`，防止切头；
- 嵌入动态微动引擎：Blink 眨眼 + Breathing 浮动 + OpenAI/Muse 风格双旋轨道光晕；
- 支持全助理通用分发渲染。

**Step 3: Run tests & Commit**
`git commit -m "feat(ui): 落地全助理普惠动态动物 Avatar 引擎与顶栏防裁剪居中"`

---

### Task 4: 会话流连接器授权卡片 (`ConnectorAuthCard.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/ConnectorAuthCard.tsx`
- Modify: `deploy/lobehub/patches/ui/assistant_naming_widget.py` (扩展或新建挂载补丁)
- Test: `tests/deploy/test_connector_auth_card_patch.py`
- Does NOT own: 外部第三方 OAuth 认证服务器 (AP-01)
- Invariants to test: INV-04 (卡片具备品牌 Icon、OAuth 独立弹窗监听、自动打字轮询与 ACTIVE 平滑过渡)

**Step 1: Create failing patch test**
断言组件存在且声明式补丁挂载成功。

**Step 2: Implement ConnectorAuthCard.tsx**
- 品牌 Icon（Gmail / Google Drive / GitHub / Slack / Local Companion）；
- 状态药丸标签（`🟡 等待授权` / `⏳ 授权中...` / `🟢 已连接`）；
- 点击唤起 600×700 独立 OAuth 窗 + 定时轮询 `/lca-api/composio/connections/{id}/refresh`；
- 成功后微动播放庆祝并原地转态。

**Step 3: Run tests & Commit**
`git commit -m "feat(ui): 落地会话流交互式连接器授权卡片与自动轮询状态机"`

---

### Task 5: 右侧抽屉全局连接器中枢 (`ConnectorsPanel.tsx` in `AssistantStatusDrawer.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/ConnectorsPanel.tsx`
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_connector_drawer_patch.py`
- Does NOT own: 任何非 LCA 资产 (AP-01)
- Invariants to test: INV-03 (实时映射 `/composio/connections` 与伴侣状态真值，支持查看工具清单与启用开关)

**Step 1: Write test for ConnectorsPanel & Drawer integration**
断言 `AssistantStatusDrawer` 包含 `⚡ Connectors` Tab 且渲染 `ConnectorsPanel`。

**Step 2: Implement ConnectorsPanel.tsx**
- 顶部统计：已连接 X / 共 Y 个生态服务；
- 完整连接器列表：Gmail、Google Drive、GitHub、Slack、Notion、本地电脑伴侣；
- 卡片包含：状态指示灯、当前助理启用 Switch、“查看工具清单”折叠抽屉、一键授权/断开/刷新按钮；
- 整合顶部 Profile 头像与编辑铅笔快捷菜单（修改名字 / 修改形象自动回填）。

**Step 3: Run tests & Commit**
`git commit -m "feat(ui): 落地右侧抽屉全局连接器中枢 Tab 与工具清单展开面板"`

---

### Task 6: 会话流交互式选图卡片与换装闭环 (`AssistantAvatarWidget.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx`
- Modify: `deploy/lobehub/patches/ui/assistant_naming_widget.py` (支持 `[widget:avatar_picker...]` 拦截)
- Test: `tests/deploy/test_assistant_avatar_widget.py`
- Does NOT own: 任何宿主机系统配置 (AP-01)
- Invariants to test: INV-04 (点击候选恐龙/动物卡片后，实时预览并原子更新 `IDENTITY.md` 与顶栏/抽屉头像)

**Step 1: Write test for avatar picker widget parsing & candidate selection**
验证当消息包含 `[widget:avatar_picker...]` 时成功解析候选卡片并触发更新。

**Step 2: Implement AssistantAvatarWidget.tsx**
- 呈现 3~4 张大尺寸视觉候选卡片（霸王龙、雷龙、幼龙等）；
- 点击卡片高亮选中并实时顶栏换装预览；
- 点击“确认使用”播放庆祝动效，后端原子落盘更新 `IDENTITY.md`。

**Step 3: Run tests & Commit**
`git commit -m "feat(ui): 落地会话流交互式选图卡片与助理形象动态换装闭环"`

---

### Task 7: 补丁应用、全链路回归与 Pre-Push 门禁核验

**Files:**
- Modify: `deploy/lobehub/patch_lobehub.py`
- Verify: `deploy/lobehub/check_patch_integrity.py`
- Does NOT own: 任何未声明文件 (AP-01)
- Invariants to test: INV-05 (100% byte-identical, 0 lint error, 全套单测全绿)

**Step 1: Run patch_lobehub.py to apply all patches to lobehub-ui**
`./scripts/lca-ops lobehub ensure`
`python3 deploy/lobehub/check_patch_integrity.py`

**Step 2: Run full regression tests**
`pytest tests/application/runtime/test_event_translator_dedup.py tests/infrastructure/tools/test_composio_tool_guidance.py tests/deploy/ -v`
`ruff check lca/ tests/ deploy/`

**Step 3: Restart kernel & live smoke test**
`./scripts/lca-ops kernel-restart`
验证实际界面：顶栏动态 Avatar 浑圆居中不切头、抽屉 Connectors Tab 完整展示、Gmail 授权卡片正常交互、Answer 回复不再重复。

**Step 4: Final commit & Ready for Push**
`git commit -m "chore: 闭环连接器中枢、全助理动态Avatar与近期Run缺陷修复全套补丁与验证门禁"`

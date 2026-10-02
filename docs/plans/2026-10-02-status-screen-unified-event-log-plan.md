# Status Screen 统一事件日志与增量可观测性实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建 Status Screen 统一事件日志投影层、人话规则库、增量 WebSocket 推送与快照/取消 API，并在前端抽屉实现原地 Patch、聊天草稿编辑与真实 Stop 闭环。

**Architecture:** 基于 LCA 单轨事实源（`Session.append` / Spine 事实流）通过纯函数投影器 `ActivityProjector` 生成 `ActivityItem`；`ActivityIntentNamer` 在动作起点锁定人话标题；`EventTranslator` 增量推送 `activity_updated`；WebServer 提供聚合快照与真实终止 API；前端抽屉按 `id` 原地更新，消除全量重刷。

**Tech Stack:** Python 3.11+, Pydantic v2 (extra="forbid"), Starlette / AsyncIO, React, Ant Design, TypeScript, Pytest.

---

### Task 1: 动作数据契约与人话规则引擎 (`ActivityItem`, `ActivityIntentNamer`)

**Files:**
- Create: `lca/contracts/models/observability/activity.py`
- Modify: `lca/contracts/models/observability/__init__.py`
- Test: `tests/contracts/models/observability/test_activity_contract.py`
- Does NOT own: WebServer routes, LobeHub frontend, DB migrations (AP-01).
- Invariants to test: `INV-02`（动作起点即锁定人话标题，绝不泄露底层模块名；契约 extra="forbid"）(AP-02).

**Step 1: Write the failing test**

```python
# tests/contracts/models/observability/test_activity_contract.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.observability.activity import (
    ActivityItem,
    ActivityStatus,
    ActivityCategory,
    ActivityIntentNamer,
)

def test_activity_item_schema_and_immutability():
    item = ActivityItem(
        id="call_001",
        run_id="run_100",
        assistant_id="asst_arch",
        category=ActivityCategory.TOOL,
        title="正在搜索 Gmail 邮件",
        summary="检索未读重要邮件",
        status=ActivityStatus.RUNNING,
        start_time="2026-10-02T14:00:00Z",
        icon="mail",
        params={"query": "is:unread"},
    )
    assert item.status == ActivityStatus.RUNNING
    assert item.title == "正在搜索 Gmail 邮件"
    
    # extra="forbid" guard
    with pytest.raises(ValidationError):
        ActivityItem(
            id="call_002",
            run_id="run_100",
            assistant_id="asst_arch",
            category=ActivityCategory.TOOL,
            title="t",
            summary="s",
            status=ActivityStatus.RUNNING,
            start_time="2026-10-02T14:00:00Z",
            icon="mail",
            params={},
            forbidden_field="fail",
        )

def test_activity_intent_namer_rules():
    # Gmail
    t1, s1 = ActivityIntentNamer.name("hatch_gws_cli", {"action": "search", "query": "meeting"})
    assert t1 == "正在搜索 Gmail 邮件"
    assert "meeting" in s1

    # Shell
    t2, s2 = ActivityIntentNamer.name("run_shell", {"command": "git status -s"})
    assert t2 == "Running command"
    assert "git status" in s2

    # Browser
    t3, s3 = ActivityIntentNamer.name("browser.spawn_task", {"url": "https://github.com/pulls", "task": "Check PRs"})
    assert "github.com" in t3
    assert "Check PRs" in s3

    # Fallback with description
    t4, s4 = ActivityIntentNamer.name("custom_tool", {"description": "同步云端配置", "key": "val"})
    assert t4 == "同步云端配置"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/models/observability/test_activity_contract.py -v`  
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/observability/activity.py
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field


class ActivityStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivityCategory(str, Enum):
    COMMAND = "command"
    SUBAGENT = "subagent"
    BROWSER = "browser"
    CRON = "cron"
    TOOL = "tool"


class ActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    run_id: str
    assistant_id: str
    category: ActivityCategory
    title: str
    summary: str
    status: ActivityStatus
    start_time: str
    end_time: str | None = None
    duration_ms: int | None = None
    icon: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    is_system: bool = False


class ActivityIntentNamer:
    @staticmethod
    def name(tool_name: str, arguments: dict[str, Any] | None = None) -> tuple[str, str, str]:
        """Returns (title, summary, icon_type)."""
        args = arguments or {}
        lowered = tool_name.lower()

        # Connectors: Gmail / Mail
        if "gmail" in lowered or (lowered == "hatch_gws_cli" and args.get("service") == "gmail"):
            action = str(args.get("action") or "").lower()
            if "send" in action:
                to = args.get("to") or args.get("recipient") or "联系人"
                return f"正在发送邮件到 {to}", str(args.get("subject") or "新邮件"), "mail"
            query = args.get("query") or args.get("search") or ""
            return "正在搜索 Gmail 邮件", f"检索: {query}" if query else "检索未读重要邮件", "mail"

        # Connectors: Drive
        if "drive" in lowered or (lowered == "hatch_gws_cli" and args.get("service") == "drive"):
            return "正在访问 Google Drive 文档", str(args.get("query") or "浏览文档目录"), "document"

        # Connectors: GitHub
        if "github" in lowered:
            return "正在检索 GitHub 仓库", str(args.get("repo") or args.get("query") or "查看代码与 Issue"), "github"

        # Shell / Box Command
        if lowered in ("run_shell", "shell", "box_run_command") or "exec" in lowered:
            cmd = str(args.get("command") or args.get("cmd") or "")
            summary = (cmd[:40] + "...") if len(cmd) > 40 else (cmd or "系统命令")
            return "Running command", summary, "terminal"

        # Browser
        if "browser" in lowered:
            url = str(args.get("url") or "")
            domain = urlparse(url).netloc if url else "网页"
            task = str(args.get("task") or args.get("goal") or "")
            return f"Browsing {domain}", task or "自动化网页浏览", "browser"

        # Subagent
        if "subagent" in lowered:
            role = str(args.get("role") or args.get("name") or "协同助手")
            prompt = str(args.get("prompt") or args.get("task") or "")
            return f"执行子任务: {role}", prompt[:40] if prompt else "后台协同任务", "robot"

        # Cron Worker
        if "cron" in lowered:
            job_title = str(args.get("title") or args.get("job_title") or "定时提醒")
            return f"定时运行: {job_title}", "按计划执行例程", "clock"

        # Fallback with description
        desc = args.get("description")
        if isinstance(desc, str) and desc.strip():
            return desc.strip(), str(args.get("summary") or tool_name), "tool"

        return f"执行操作: {tool_name}", str(args.get("summary") or "处理中"), "tool"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/models/observability/test_activity_contract.py -v`  
Expected: PASS (100%)

**Step 5: Commit**

```bash
git add lca/contracts/models/observability/ tests/contracts/models/observability/test_activity_contract.py
git commit -m "feat(activity): define ActivityItem schema and ActivityIntentNamer"
```

---

### Task 2: 单轨事实流投影器与快照引擎 (`ActivityProjector`, `StatusSnapshotService`)

**Files:**
- Create: `lca/infrastructure/observability/activity_projector.py`
- Test: `tests/infrastructure/observability/test_activity_projector.py`
- Does NOT own: Frontend UI, Shell executor internals (AP-01).
- Invariants to test: `INV-01`（从 Session/Spine 事实流投影纯函数性与确定性，零平行持久化存储）(AP-02).

**Step 1: Write the failing test**

```python
# tests/infrastructure/observability/test_activity_projector.py
import pytest
from lca.contracts.models.observability.activity import ActivityStatus
from lca.infrastructure.observability.activity_projector import ActivityProjector

def test_projector_folds_events_deterministically():
    projector = ActivityProjector()
    
    # 1. tool start event
    start_ev = {
        "execution_point": "phase.tool.call.start",
        "payload": {
            "invocation_id": "call_123",
            "run_id": "run_001",
            "assistant_id": "architect",
            "tool_name": "run_shell",
            "arguments": {"command": "ls -la"},
            "timestamp": "2026-10-02T10:00:00Z",
        }
    }
    item1 = projector.feed_event(start_ev)
    assert item1 is not None
    assert item1.status == ActivityStatus.RUNNING
    assert item1.title == "Running command"
    assert "ls -la" in item1.summary

    # 2. tool end event
    end_ev = {
        "execution_point": "body.tool.execute.end",
        "payload": {
            "invocation_id": "call_123",
            "run_id": "run_001",
            "assistant_id": "architect",
            "tool_name": "run_shell",
            "ok": True,
            "latency_ms": 150,
            "message": {"content": "total 48\n-rw-r--r-- ..."},
            "timestamp": "2026-10-02T10:00:00.150Z",
        }
    }
    item2 = projector.feed_event(end_ev)
    assert item2 is not None
    assert item2.status == ActivityStatus.COMPLETED
    assert item2.duration_ms == 150

    # 3. get snapshot items
    items = projector.get_activities(assistant_id="architect")
    assert len(items) == 1
    assert items[0].id == "call_123"
    assert items[0].status == ActivityStatus.COMPLETED
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/observability/test_activity_projector.py -v`  
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# lca/infrastructure/observability/activity_projector.py
from __future__ import annotations
from typing import Any
from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)


class ActivityProjector:
    """Pure-function projection engine folding Session/Spine facts into ActivityItem."""

    def __init__(self) -> None:
        # In-memory projection store per assistant: {assistant_id: {item_id: ActivityItem}}
        self._items: dict[str, dict[str, ActivityItem]] = {}

    def feed_event(self, stamped: dict[str, Any]) -> ActivityItem | None:
        event = stamped.get("event") or stamped
        ep = event.get("execution_point")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event

        # Handle Start: phase.tool.call.start / step.tool_call.record
        if ep in ("phase.tool.call.start", "step.tool_call.record"):
            inv_id = str(payload.get("invocation_id") or payload.get("tool_call_id") or "")
            if not inv_id:
                return None
            run_id = str(payload.get("run_id") or "run_current")
            asst_id = str(payload.get("assistant_id") or "default")
            tool_name = str(payload.get("tool_name") or "")
            args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            title, summary, icon = ActivityIntentNamer.name(tool_name, args)
            
            category = ActivityCategory.COMMAND if "shell" in tool_name or "exec" in tool_name else ActivityCategory.TOOL
            if "subagent" in tool_name:
                category = ActivityCategory.SUBAGENT
            elif "browser" in tool_name:
                category = ActivityCategory.BROWSER
            elif "cron" in tool_name:
                category = ActivityCategory.CRON

            item = ActivityItem(
                id=inv_id,
                run_id=run_id,
                assistant_id=asst_id,
                category=category,
                title=title,
                summary=summary,
                status=ActivityStatus.RUNNING,
                start_time=str(payload.get("timestamp") or "2026-10-02T00:00:00Z"),
                icon=icon,
                params=args,
            )
            self._save(item)
            return item

        # Handle End: body.tool.execute.end
        if ep == "body.tool.execute.end":
            inv_id = str(payload.get("invocation_id") or payload.get("tool_call_id") or "")
            asst_id = str(payload.get("assistant_id") or "default")
            existing = self._get(asst_id, inv_id)
            if not existing:
                return None
            ok = payload.get("ok")
            outcome = str(payload.get("outcome") or "").lower()
            is_success = ok if isinstance(ok, bool) else outcome not in ("failure", "failed", "error", "cancelled")
            
            status = ActivityStatus.CANCELLED if outcome == "cancelled" else (
                ActivityStatus.COMPLETED if is_success else ActivityStatus.FAILED
            )
            res_content = ""
            msg = payload.get("message")
            if isinstance(msg, dict):
                res_content = str(msg.get("content") or "")

            updated = ActivityItem(
                id=existing.id,
                run_id=existing.run_id,
                assistant_id=existing.assistant_id,
                category=existing.category,
                title=existing.title,
                summary=existing.summary,
                status=status,
                start_time=existing.start_time,
                end_time=str(payload.get("timestamp") or ""),
                duration_ms=payload.get("latency_ms"),
                icon=existing.icon,
                params=existing.params,
                result_summary=(res_content[:100] + "...") if len(res_content) > 100 else res_content,
                is_system=existing.is_system,
            )
            self._save(updated)
            return updated

        return None

    def cancel_activity(self, assistant_id: str, activity_id: str) -> ActivityItem | None:
        existing = self._get(assistant_id, activity_id)
        if not existing:
            return None
        cancelled = ActivityItem(
            id=existing.id,
            run_id=existing.run_id,
            assistant_id=existing.assistant_id,
            category=existing.category,
            title=existing.title,
            summary=existing.summary,
            status=ActivityStatus.CANCELLED,
            start_time=existing.start_time,
            end_time="cancelled",
            duration_ms=existing.duration_ms,
            icon=existing.icon,
            params=existing.params,
            result_summary="User cancelled operation",
            is_system=existing.is_system,
        )
        self._save(cancelled)
        return cancelled

    def get_activities(self, assistant_id: str) -> list[ActivityItem]:
        store = self._items.get(assistant_id, {})
        # Return descending by start_time
        return sorted(store.values(), key=lambda x: x.start_time, reverse=True)

    def _save(self, item: ActivityItem) -> None:
        if item.assistant_id not in self._items:
            self._items[item.assistant_id] = {}
        self._items[item.assistant_id][item.id] = item

    def _get(self, assistant_id: str, item_id: str) -> ActivityItem | None:
        return self._items.get(assistant_id, {}).get(item_id)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/observability/test_activity_projector.py -v`  
Expected: PASS (100%)

**Step 5: Commit**

```bash
git add lca/infrastructure/observability/activity_projector.py tests/infrastructure/observability/test_activity_projector.py
git commit -m "feat(activity): implement ActivityProjector pure fold engine"
```

---

### Task 3: EventTranslator 增量推送扩展与取消机制 (`activity_updated`)

**Files:**
- Modify: `lca/application/runtime/coordinator/event_translator.py`
- Test: `tests/application/runtime/test_event_translator_activity.py`
- Does NOT own: Frontend UI, Connector API token storage (AP-01).
- Invariants to test: `INV-03`（向 WS 增量发射 activity_updated，按 id 原地更新）(AP-02).

**Step 1: Write the failing test**

```python
# tests/application/runtime/test_event_translator_activity.py
from lca.application.runtime.coordinator.event_translator import EventTranslator

def test_event_translator_emits_activity_updated():
    translator = EventTranslator()
    
    # 1. tool start generates activity_updated running
    stamped_start = {
        "event": {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_abc",
                "tool_name": "hatch_gws_cli",
                "arguments": {"action": "search", "service": "gmail", "query": "invoice"},
            }
        }
    }
    wire_events = translator.translate(stamped_start)
    assert isinstance(wire_events, list)
    activity_msg = next((e for e in wire_events if e.get("type") == "activity_updated"), None)
    assert activity_msg is not None
    assert activity_msg["data"]["status"] == "running"
    assert activity_msg["data"]["title"] == "正在搜索 Gmail 邮件"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/application/runtime/test_event_translator_activity.py -v`  
Expected: FAIL

**Step 3: Modify `event_translator.py` to emit `activity_updated`**

- In `_spine_phase_tool_start`, construct `activity_updated` dictionary with `status="running"` and include alongside `tool_start`.
- In `_spine_body_tool_end`, construct `activity_updated` dictionary with `status="completed"|"failed"` and include alongside `tool_end`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/application/runtime/test_event_translator_activity.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/runtime/coordinator/event_translator.py tests/application/runtime/test_event_translator_activity.py
git commit -m "feat(wire): extend EventTranslator to emit activity_updated incremental stream events"
```

---

### Task 4: 快照与取消 REST API 端点 (`routes_status_screen.py`)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_status_screen.py`
- Modify: `lca/plugins/transport/webserver/router/router.py` or routes registry
- Test: `tests/plugins/transport/webserver/test_routes_status_screen.py`
- Does NOT own: Frontend UI, Chat message tables (AP-01).
- Invariants to test: `INV-04`（Stop API 真实调用 RunPort.cancel 并置 cancelled 状态）与 `INV-06`（快照 API 聚合 Activity, Approvals, Upcoming 与 Identity）(AP-02).

**Step 1: Write the failing test**

```python
# tests/plugins/transport/webserver/test_routes_status_screen.py
import pytest
from starlette.testclient import TestClient

def test_status_snapshot_and_cancel_endpoints():
    # Verify GET /lca-api/v1/assistants/{id}/status-snapshot
    # returns 200 with {activities, approvals, upcoming, identity}
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/transport/webserver/test_routes_status_screen.py -v`  
Expected: FAIL (404 Not Found)

**Step 3: Implement endpoints in `routes_status_screen.py`**

- `GET /lca-api/v1/assistants/{id}/status-snapshot`: Pulls `activities` from `ActivityProjector`, `approvals` from `ApprovalPolicyEngine`, `upcoming` from `CronJobRepository` (as `CronListItem`), and `identity` from standing files.
- `POST /lca-api/v1/runs/{run_id}/cancel`: Calls `RunPort.cancel(run_id)` and records `cancelled` in projector.

**Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/transport/webserver/test_routes_status_screen.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/routes_status_screen.py tests/plugins/transport/webserver/test_routes_status_screen.py
git commit -m "feat(routes): add status-snapshot and run cancellation endpoints"
```

---

### Task 5: 前端 `AssistantStatusDrawer.tsx` 增量 Patch 与交互闭环

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/ui/test_assistant_status_drawer_patch.py`
- Does NOT own: Backend domain models, other unrelated LobeHub components (AP-01).
- Invariants to test: `INV-03`（按 id 原地 patch 单行）、`INV-05`（Upcoming 聊天草稿注入 & is_system 拦截）(AP-02).

**Step 1: Implement frontend updates**

1. **Snapshot Fetching**: On drawer `open`, fetch `/lca-api/v1/assistants/{id}/status-snapshot`.
2. **WebSocket Incremental Patch**: Listen to `activity_updated` events from session WS and patch `activities` by `id`.
3. **Stop Button**: Render Stop button on hover when `item.status === 'running'`. Clicking triggers `/lca-api/v1/runs/{run_id}/cancel`.
4. **Upcoming Enhancements**:
   - Edit button: Call `handleTriggerChatEdit('把每天 9 点的晨报改到 8 点')`.
   - Delete button: Check `job.is_system`; if true, show AntD message: `系统任务不可删除` and prevent deletion.
5. **Approvals**: Render live approvals with Allow / Deny actions.

**Step 2: Sync patches to lobehub-ui**

Run: `python3 deploy/lobehub/patch_lobehub.py`  
Expected: 39 ok, 0 broken

**Step 3: Verify TypeScript / Lint / Component integrity**

Run: `npm run lint` or test runner in frontend if available.

**Step 4: Commit**

```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "feat(ui): implement incremental activity patching, chat draft editing, and stop button in status drawer"
```

---

### Task 6: 全链路单测回归与全量不变量矩阵验证 (`INV-01` ~ `INV-06`)

**Files:**
- Create: `tests/scenario/test_status_screen_invariants.py`
- Does NOT own: Host ops, non-LCA assets (AP-01).
- Invariants to test: Full verification of `INV-01` through `INV-06` (AP-02).

**Step 1: Write comprehensive scenario test suite**

- Test full lifecycle from tool call initiation (`running` + human title) -> WS incremental patch -> completion with latency -> snapshot consistency -> cancellation -> upcoming protection.

**Step 2: Run all scenario tests**

Run: `pytest tests/scenario/test_status_screen_invariants.py -v`  
Expected: PASS (100%)

**Step 3: Run project sanity & pre-push checks**

Run: `ruff check lca/ tests/`  
Run: `git diff --check`  
Expected: Clean exit code 0.

**Step 4: Commit**

```bash
git add tests/scenario/test_status_screen_invariants.py
git commit -m "test(status-screen): add full scenario verification for invariants INV-01 to INV-06"
```

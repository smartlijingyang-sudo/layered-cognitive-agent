# Conversational Onboarding 与双向命名仪式实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 为 LCA 实现商业级对话式迎新与双向命名仪式：开场白脚本化、一次一问、起名 Widget、双向命名落盘、老用户新建助理画像自动继承与终身幂等。

**Architecture:** 严格遵循 LCA 单向 DDD 架构（contracts → persistence → tools → application → lobehub ui patch），用户身份入库权威 `user_store.py`，配置面写入收敛于 `AssistantCatalog.revise_profile`，前端通过声明式补丁挂载交互组件。

**Tech Stack:** Python 3.11+, Pydantic v2 (frozen models), SQLite/PostgreSQL (WAL/Asyncpg), React/TypeScript (LobeHub UI patch), Pytest.

---

### Task 1: 契约与数据库持久化增强 (`NamingCandidate`, `NamingWidgetPayload`, `user_store.py`)

**Files:**
- Create: `lca/contracts/models/onboarding/naming.py`
- Modify: `lca/infrastructure/persistence/user_store.py:34-41, 60-67, 125-145, 210-230`
- Test: `tests/onboarding/test_naming_contracts.py`
- Test: `tests/persistence/test_user_store_onboarding.py`
- Does NOT own: `lca/contracts/atoms/`, `lca/infrastructure/tools/`
- Invariants to test: `INV-01` (幂等状态), `INV-02` (数据库 SSOT 权威), `INV-06` (信息血统闭合与 extra="forbid")

**Step 1: Write the failing tests**
```python
# tests/onboarding/test_naming_contracts.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.onboarding.naming import NamingCandidate, NamingWidgetPayload

def test_naming_candidate_contract():
    cand = NamingCandidate(id="c1", name="Athena", vibe="敏锐高效", emoji="🦉")
    assert cand.name == "Athena"
    with pytest.raises(ValidationError):
        cand.name = "NewName"  # frozen

def test_naming_widget_payload_contract():
    payload = NamingWidgetPayload(
        token="tok_123",
        assistant_id="asst_abc",
        candidates=(NamingCandidate(id="c1", name="Athena", vibe="敏锐高效"),),
    )
    assert payload.allow_custom is True
    with pytest.raises(ValidationError):
        NamingWidgetPayload(token="t", assistant_id="a", candidates=(), extra_field="bad")
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/onboarding/test_naming_contracts.py -v`  
Expected: FAIL with ModuleNotFoundError or import error

**Step 3: Write minimal implementation**
- 创建 `lca/contracts/models/onboarding/naming.py`：定义不可变 Pydantic 模型 `NamingCandidate` 与 `NamingWidgetPayload`；
- 修改 `lca/infrastructure/persistence/user_store.py`：
  - 在 DDL 中增加 `user_md TEXT` 字段；
  - 增加 `update_user_md(user_id: str, user_md: str, display_name: str | None = None)`；
  - 增加 `get_user_md(user_id: str) -> str | None`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/onboarding/test_naming_contracts.py tests/persistence/test_user_store_onboarding.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add lca/contracts/models/onboarding/ lca/infrastructure/persistence/user_store.py tests/
git commit -m "feat(onboarding): add naming contracts and user_md persistence in user_store (Task 1)"
```

---

### Task 2: 自管理工具链落地 (`CreateNameWidgetTool` & `UpdateIdentityTool`)

**Files:**
- Create: `lca/infrastructure/tools/onboarding/naming_tools.py`
- Modify: `lca/infrastructure/tools/assistant/self_manage_tools.py`
- Test: `tests/tools/test_onboarding_naming_tools.py`
- Does NOT own: 严禁直接调用 `open()` 裸写文件，必须经由 `AssistantCatalog.revise_profile`
- Invariants to test: `INV-03` (Digest 权威单写与 revision_seq 递增), `INV-07` (落名回执与 reaction 信号)

**Step 1: Write the failing test**
```python
# tests/tools/test_onboarding_naming_tools.py
import pytest
from lca.infrastructure.tools.onboarding.naming_tools import CreateNameWidgetTool, UpdateIdentityTool

@pytest.mark.asyncio
async def test_create_name_widget_tool(fake_catalog, fake_user_store):
    tool = CreateNameWidgetTool(catalog=fake_catalog, user_store=fake_user_store, assistant_id="asst_1", user_id="u_1")
    obs = await tool.execute({"user_name": "李超"})
    assert obs.success is True
    assert "token" in obs.payload
    assert fake_user_store.get_user_md("u_1") is not None
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/tools/test_onboarding_naming_tools.py -v`  
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**
- 实现 `CreateNameWidgetTool`：
  - 格式化 `USER.md`，调用 `user_store.update_user_md` 和 `catalog.revise_profile(ProfilePatch(user_md=...))`；
  - 随机采样候选名，签发 `token`，生成 `NamingWidgetPayload`；
  - 返回带有 `[widget:name_picker?token={token}]` 的 Observation。
- 实现 `UpdateIdentityTool`：
  - 组装 `IDENTITY.md`，调 `catalog.revise_profile(ProfilePatch(profile_name=name, ...))`；
  - 调 `user_store.set_onboarding_state(user_id, "completed")`；
  - 返回带有 `payload={"reaction": "🎉", "name": name}` 的 Observation。

**Step 4: Run test to verify it passes**
Run: `pytest tests/tools/test_onboarding_naming_tools.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/tools/onboarding/ tests/tools/test_onboarding_naming_tools.py
git commit -m "feat(onboarding): implement CreateNameWidgetTool and UpdateIdentityTool (Task 2)"
```

---

### Task 3: 助理创建自动继承老用户画像 (`AssistantCatalog.create`)

**Files:**
- Modify: `lca/contracts/protocols/assistant/catalog.py`
- Modify: `lca/application/assistant/file_catalog.py`
- Test: `tests/scenario/test_assistant_user_inheritance.py`
- Does NOT own: 严禁覆盖用户显式传入的 `seed_user_md`
- Invariants to test: `INV-04` (老用户画像 100% 自动继承，零重复提问)

**Step 1: Write the failing test**
```python
# tests/scenario/test_assistant_user_inheritance.py
def test_create_assistant_inherits_user_md_automatically(catalog, user_store):
    user_store.ensure_user("user_pro")
    user_store.update_user_md("user_pro", "# USER.md\n- Name: 老李\n- Role: 架构师")
    user_store.set_onboarding_state("user_pro", "completed")
    
    # 新建特化助理，未传 seed_user_md
    handle = catalog.create(CreateAssistantRequest(name="DevAssistant", owner_user_id="user_pro"))
    spec = catalog.get(handle.assistant_id)
    user_content = (Path(spec.home_path) / "USER.md").read_text(encoding="utf-8")
    assert "老李" in user_content
    assert "架构师" in user_content
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/scenario/test_assistant_user_inheritance.py -v`  
Expected: FAIL with AssertionError (not inherited)

**Step 3: Write minimal implementation**
- 在 `file_catalog.py`（或对应 Catalog 实现类）中，在 `create` 方法创建物化配置前：
  若 `req.seed_user_md is None` 且 `req.owner_user_id` 有效，从 `user_store.get_user_md(owner_user_id)` 检索并默认赋予 `seed_user_md`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/scenario/test_assistant_user_inheritance.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add lca/application/assistant/ tests/scenario/test_assistant_user_inheritance.py
git commit -m "feat(catalog): auto-inherit global user_md on new assistant creation (Task 3)"
```

---

### Task 4: 开场白脚本化编排与网关 Reaction 桥接

**Files:**
- Create: `lca/application/onboarding/script.py`
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/`
- Test: `tests/onboarding/test_onboarding_script_pacing.py`
- Does NOT own: 严禁将内部状态机泄露为对话调试文本
- Invariants to test: `INV-05` (开场白脚本化确定性两段式)

**Step 1: Write the failing test**
```python
# tests/onboarding/test_onboarding_script_pacing.py
from lca.application.onboarding.script import get_onboarding_opening_messages

def test_onboarding_opening_two_bubbles():
    msgs = get_onboarding_opening_messages(user_state="pending")
    assert len(msgs) == 2
    assert "个人 Agent" in msgs[0]
    assert "怎么称呼你" in msgs[1]

def test_greeting_for_existing_user():
    msgs = get_onboarding_opening_messages(user_state="completed", user_name="李超", role_title="架构师")
    assert len(msgs) == 1
    assert "李超" in msgs[0]
    assert "架构师" in msgs[0]
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/onboarding/test_onboarding_script_pacing.py -v`  
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**
- 落地 `lca/application/onboarding/script.py`，固化开场白脚本；
- 在会话启动/首轮 Run 中若检测到尚未完成，注入脚本消息。

**Step 4: Run test to verify it passes**
Run: `pytest tests/onboarding/test_onboarding_script_pacing.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add lca/application/onboarding/ tests/onboarding/test_onboarding_script_pacing.py
git commit -m "feat(onboarding): implement scripted two-bubble opening and greeting (Task 4)"
```

---

### Task 5: 前端 LobeHub UI 起名 Widget 补丁与交互组件

**Files:**
- Create: `deploy/lobehub/patches/ui/assistant_naming_widget.py`
- Create: `deploy/lobehub/patches/ui/fragments/AssistantNamingWidget.tsx`
- Test: `tests/deploy/test_assistant_naming_widget_patch.py`
- Does NOT own: 严禁手动修改 `vendor/lobehub`，必须经由 `patch_lobehub.py` 声明式打补丁
- Invariants to test: 补丁完整性、TSX 语法及 byte-identical 一致性

**Step 1: Write the failing test**
```python
# tests/deploy/test_assistant_naming_widget_patch.py
from deploy.lobehub.patch_lobehub import ALL_PATCHES

def test_naming_widget_patch_registered():
    names = [p.name for p in ALL_PATCHES]
    assert "assistant_naming_widget" in names
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_assistant_naming_widget_patch.py -v`  
Expected: FAIL with AssertionError

**Step 3: Write minimal implementation**
- 编写 `AssistantNamingWidget.tsx`：提供候选 Chips 点选、自定义输入、一键“确认命名并启程 ✨”、以及完成态与 🎉 庆祝 Reaction 渲染；
- 编写 `assistant_naming_widget.py` 声明式补丁；
- 注册到 `deploy/lobehub/patch_lobehub.py`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/deploy/test_assistant_naming_widget_patch.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/ tests/deploy/test_assistant_naming_widget_patch.py
git commit -m "feat(ui): add AssistantNamingWidget interactive patch for LobeHub (Task 5)"
```

---

### Task 6: 全链路不变量集成测试与门禁核验 (INV-01 ~ INV-08)

**Files:**
- Create: `tests/scenario/test_conversational_onboarding_e2e.py`
- Does NOT own: 严禁留后门或跳过门禁
- Invariants to test: INV-01 ~ INV-08 全量不变量套件

**Step 1: Write full E2E scenario test**
- 编写 `tests/scenario/test_conversational_onboarding_e2e.py`：
  - 新用户进入：验证两段式开场白；
  - 提交姓名：验证 `lca_users.user_md` 与 `USER.md` 同步落盘，获得 Widget Token；
  - 选定名字：验证 `IDENTITY.md` 写入、`profile.json` 更新、Reaction 触发、状态变为 `completed`；
  - 再次进入：验证幂等，不再发起迎新；
  - 新建第 2 个助理：验证自动继承老用户画像，仅触发轻量打招呼。

**Step 2: Run E2E test to verify it passes**
Run: `pytest tests/scenario/test_conversational_onboarding_e2e.py -v`  
Expected: PASS

**Step 3: Run static gates & format checks**
Run: `ruff check lca/ tests/ deploy/ && git diff --check`  
Expected: Clean with 0 errors

**Step 4: Commit**
```bash
git add tests/scenario/test_conversational_onboarding_e2e.py
git commit -m "test(onboarding): full lifecycle E2E conformance suite with INV-01~08 (Task 6)"
```

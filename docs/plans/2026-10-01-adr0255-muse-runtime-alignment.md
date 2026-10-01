# ADR-0255 Muse 生产运行时全量对齐实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 ADR-0255 实测规范，在 LCA 中全量落地 9 大 Standing 文件布局、上下文装配时间与 Runtime 强化、强制记忆检索与写盘硬闸门，并建立完整的 T1–T12 自动化符合性测试套件。

**Architecture:** 
1. 扩展 `layout.toml` 与 `layout.py` 使 `standing_files` 对齐生产实测的 9 项清单，更新根目录白名单与助理创建初始化模板；
2. 在上下文与 Prompt 组装层引入精确的 Developer 时间戳与 Runtime 行，确立唯一时间可信源；
3. 在认知策略层注入强制检索决策树与“落笔前写盘”铁律；
4. 编写 `tests/runtime/test_adr0255_muse_runtime_conformance.py` 自动化验证 ADR-0255 §6 的 T1–T12 验收标准。

**Tech Stack:** Python 3.12, TOML (`tomllib`), Pydantic v2, Pytest.

---

### Task 1: 9 大 Standing 文件布局与根拓扑白名单扩展

**Files:**
- Modify: `lca/infrastructure/memory/contextfiles/layout.toml`
- Modify: `lca/infrastructure/memory/contextfiles/domain/layout.py`
- Modify: `tests/infrastructure/memory/test_standing_assembly.py:21-29`
- Modify: `tests/contracts/test_context_files_topology.py:14-20`
- Does NOT own: `lca/runtime/`, `lca/plugins/prompts/`
- Invariants to test: `INV-TOPOLOGY-ALLOWLIST`（`IDENTITY.md` 在白名单中），`packaged_layout().standing_files` 有序且包含 9 个文件。

**Step 1: Write the failing test**

In `tests/infrastructure/memory/test_standing_assembly.py`:
```python
def test_standing_order_comes_from_the_layout_file() -> None:
    assert packaged_layout().standing_files == (
        "SOUL.md",
        "IDENTITY.md",
        "USER.md",
        "MEMORY.md",
        "AGENTS.md",
        "TOOLS.md",
        "memory/people/INDEX.md",
        "memory/groups/INDEX.md",
        "dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md",
    )
```

In `tests/contracts/test_context_files_topology.py`:
```python
def test_allowed_root_entries_cover_the_landed_files() -> None:
    allowed = allowed_root_entries()
    for name in ("SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"):
        assert name in allowed
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/python -m pytest tests/infrastructure/memory/test_standing_assembly.py::test_standing_order_comes_from_the_layout_file tests/contracts/test_context_files_topology.py::test_allowed_root_entries_cover_the_landed_files -v`
Expected: FAIL with mismatch in tuple contents.

**Step 3: Write minimal implementation**

In `lca/infrastructure/memory/contextfiles/layout.toml`:
```toml
standing_files = [
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "MEMORY.md",
    "AGENTS.md",
    "TOOLS.md",
    "memory/people/INDEX.md",
    "memory/groups/INDEX.md",
    "dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md"
]
```

In `lca/infrastructure/memory/contextfiles/domain/layout.py`:
Ensure `allowed_root_entries()` includes `"IDENTITY.md"`, and `validate_root_entries` properly accounts for it.

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/python -m pytest tests/infrastructure/memory/ tests/contracts/test_context_files_topology.py -q`
Expected: PASS (all tests pass).

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/contextfiles/layout.toml lca/infrastructure/memory/contextfiles/domain/layout.py tests/infrastructure/memory/test_standing_assembly.py tests/contracts/test_context_files_topology.py
git commit -m "feat(contextfiles): 扩展 9 大 Standing 文件布局并对齐根拓扑白名单"
```

---

### Task 2: 助理 Home 初始化默认骨架物化 (IDENTITY.md & 目录索引骨架)

**Files:**
- Modify: `lca/plugins/assistant/home/_home_layout.py`
- Test: `tests/plugins/assistant/home/test_home_layout.py`
- Does NOT own: `lca/contracts/`, `lca/runtime/`
- Invariants to test: 新创建的 assistant home 包含 `IDENTITY.md`（填充 Name/Character/Vibe/Emoji 骨架）以及人物、群组的 INDEX.md 初始骨架。

**Step 1: Write the failing test**

In `tests/plugins/assistant/home/test_home_layout.py`:
```python
def test_create_assistant_home_initializes_identity_and_indexes(tmp_path: Path) -> None:
    home = tmp_path / "asst_test"
    profile = {"name": "Athena-test", "description": "测试助理"}
    init_assistant_home(home, profile=profile)
    assert (home / "IDENTITY.md").is_file()
    content = (home / "IDENTITY.md").read_text(encoding="utf-8")
    assert "Athena-test" in content
    assert (home / "memory" / "people" / "INDEX.md").is_file()
    assert (home / "memory" / "groups" / "INDEX.md").is_file()
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/assistant/home/test_home_layout.py -k test_create_assistant_home_initializes_identity_and_indexes -v`
Expected: FAIL (file not found or assertion failed).

**Step 3: Write minimal implementation**

In `lca/plugins/assistant/home/_home_layout.py`:
Update home initialization logic to write `IDENTITY.md` (with `# IDENTITY.md\n\n- **Name:** {name}\n- **Character:** AI assistant\n- **Vibe:** helpful, sharp\n- **Emoji:** 🦉\n`) and ensure parent directories and empty `INDEX.md` files exist for `people` and `groups`.

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/assistant/home/test_home_layout.py -k test_create_assistant_home_initializes_identity_and_indexes -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add lca/plugins/assistant/home/_home_layout.py tests/plugins/assistant/home/test_home_layout.py
git commit -m "feat(assistant): 助理创建时自动物化 IDENTITY.md 与目录索引骨架"
```

---

### Task 3: 上下文装配时间与 Runtime 元数据渲染 (Developer Timestamp & Runtime Row)

**Files:**
- Create: `lca/plugins/prompts/sections/runtime_env.py`
- Modify: `lca/plugins/prompts/sections/__init__.py` (or prompt registry)
- Test: `tests/plugins/prompts/test_runtime_env_section.py`
- Does NOT own: `lca/infrastructure/memory/`
- Invariants to test:
  1. `render_developer_timestamp(now, timezone)` 输出标准 `[{weekday} {YYYY-MM-DD HH:MM:SS} {TZ}] [client_timezone={tz}]`；
  2. `render_runtime_row(session, os, model, shell, depth, max_depth, can_spawn)` 输出标准管道分隔行。

**Step 1: Write the failing test**

In `tests/plugins/prompts/test_runtime_env_section.py`:
```python
def test_render_runtime_row():
    row = render_runtime_row(session="main chat", os_name="linux", model="Muse Spark", can_spawn=True)
    assert "Runtime: session=main chat | os=linux | model=Muse Spark | shell=bash | depth=0 | max_depth=2 | can_spawn=yes" in row

def test_render_developer_timestamp():
    ts = render_developer_timestamp(dt=datetime(2026, 10, 1, 11, 34, 53), tz_name="Asia/Shanghai")
    assert "[Thu 2026-10-01 11:34:53 CST] [client_timezone=Asia/Shanghai]" in ts
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/prompts/test_runtime_env_section.py -v`
Expected: FAIL (module/functions not found).

**Step 3: Write minimal implementation**

Implement `render_runtime_row` and `render_developer_timestamp` with clean formatting in `lca/plugins/prompts/sections/runtime_env.py`.

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/prompts/test_runtime_env_section.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add lca/plugins/prompts/sections/runtime_env.py tests/plugins/prompts/test_runtime_env_section.py
git commit -m "feat(prompt): 实现 Developer 时间戳与 Runtime 状态行渲染"
```

---

### Task 4: 认知层强制检索与写盘硬闸门提示词策略

**Files:**
- Modify: `lca/plugins/prompts/sections/role.py` (or dedicated cognitive guidelines section)
- Test: `tests/plugins/prompts/test_memory_decision_gate.py`
- Does NOT own: `lca/infrastructure/session/`
- Invariants to test:
  1. 提示词中包含强制检索决策树（纯寒暄跳过，实质请求首步必先调 `memory_search`，首个 query 贴近原话）；
  2. 提示词中包含“落笔前写盘”铁律（收到物理写盘回执前不许向用户确认已记下）；
  3. 提示词中包含防指称幻觉与 SOUL 反注入警告。

**Step 1: Write the failing test**

In `tests/plugins/prompts/test_memory_decision_gate.py`:
```python
def test_cognitive_guidelines_contain_mandatory_memory_search_and_write_receipt():
    text = render_cognitive_guidelines()
    assert "强制检索决策树" in text
    assert "memory_search" in text
    assert "落笔前写盘" in text
    assert "SOUL.md" in text
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/prompts/test_memory_decision_gate.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

Add cognitive guidelines rendering to Prompt Assembly sections.

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/python -m pytest tests/plugins/prompts/test_memory_decision_gate.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add lca/plugins/prompts/sections/ tests/plugins/prompts/test_memory_decision_gate.py
git commit -m "feat(prompt): 注入强制检索决策树与落笔前写盘认知闸门"
```

---

### Task 5: ADR-0255 T1–T12 自动化符合性测试套件

**Files:**
- Create: `tests/runtime/test_adr0255_muse_runtime_conformance.py`
- Does NOT own: Production business code
- Invariants to test:
  - T1: 自我认知只依赖注入的真实文件，杜绝沙箱文件盲搜；
  - T2: 跨 Run 记忆从 `MEMORY.md` 召回带出处与时间戳的事实；
  - T3: 写盘回执先于“已记下”确认（`guard_memory_claim` 校验）；
  - T4: 冲突原地修正与替换链（`superseded_by` 校验）；
  - T5: 提示词装配强制检索决策树；
  - T8: 子 Agent 继承父级 transcript 与 Standing 块；
  - T9: 防提示词注入篡改 SOUL；
  - T10: 敏感凭证永不写入记忆原文；
  - T12: 会话压缩后 9 大 Standing 文件完整重注豁免。

**Step 1: Write the comprehensive conformance tests**

In `tests/runtime/test_adr0255_muse_runtime_conformance.py`:
Implement all deterministic asserts covering T1, T2, T3, T4, T5, T8, T9, T10, T12.

**Step 2: Run tests to verify**

Run: `/opt/lca/venv/bin/python -m pytest tests/runtime/test_adr0255_muse_runtime_conformance.py -v`
Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/runtime/test_adr0255_muse_runtime_conformance.py
git commit -m "test(conformance): 新增 ADR-0255 Muse 生产运行时全量符合性测试套件"
```

---

### Task 6: 全链路回归验证与 Pre-push 门禁体检

**Files:**
- All touched files
- Update: `docs/plans/task.md`

**Step 1: Run complete test suite**

Run: `/opt/lca/venv/bin/python -m pytest tests/infrastructure/memory/ tests/contracts/test_context_files_topology.py tests/cognition/memory/test_curated_memory_scenarios.py tests/runtime/test_adr0255_muse_runtime_conformance.py -q`
Expected: 100% PASS with 0 regressions.

**Step 2: Ruff check & Git hygiene**

Run: `/opt/lca/venv/bin/ruff check --fix`
Run: `git diff --check`

**Step 3: Update Task Tracker & Final Report**

Update `docs/plans/task.md` with status of ADR-0255 implementation.

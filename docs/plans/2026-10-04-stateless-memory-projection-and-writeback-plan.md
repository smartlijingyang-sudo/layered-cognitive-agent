# Stateless Memory Projection & Writeback Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 实现「一源一镜，镜无状态」的长期记忆架构：`memory/semantic.json` 为唯一真理落盘源，`MEMORY.md` 永远作为纯函数投影；消灭骨架吞噬 bug；将对 `MEMORY.md` 的编辑作为输入事件解析为针对 `semantic.json` 的原子变更并回写。

**Architecture:** 
1. 纯函数投影器 `render_curated_memory_markdown`：输入记录集合，生成包含标准头、永不坍塌的 `## Preferences` 与 `## Facts` 骨架及嵌入行尾注 `<!-- id:mem_xxx -->` 的 Markdown；
2. 编辑事件解析器 `MemoryEditSyncService`：比对用户提交的 Markdown 与当前活跃记录，按 Embedded ID 提取 ADD / SUPERSEDE / DELETE 原子操作并提交给 `AssistantMemory`；
3. 路由窄门收敛：拦截 `PUT /v1/assistants/{id}/standing-files/MEMORY.md`，切断直接写盘旁路，统一经由解析器驱动底层落盘并重投影。

**Tech Stack:** Python 3.12+, Pydantic, pytest, LCA Component/Harness architecture.

---

### Task 1: 纯函数投影器与模板骨架保底 (INV-MEM-01, INV-MEM-02, INV-MEM-03)

**Files:**
- Modify: `lca/infrastructure/memory/contextfiles/domain/curated.py`
- Test: `tests/infrastructure/memory/contextfiles/test_curated_projection_pure.py`
- Does NOT own: `standing_files.py`、`assistant_memory.py`、`USER.md`
- Invariants to test:
  - INV-MEM-01: 纯函数等价性（相同输入相同输出）
  - INV-MEM-02: 空记录输入时，`## Preferences` 与 `## Facts` 二级标题与占位符依然完好，骨架永不坍塌
  - INV-MEM-03: `category="identity"` 绝不进入 `MEMORY.md`
  - 每条渲染的 Bullet 尾部携带 `<!-- id:mem_xxx -->`

**Step 1: Write the failing test**

```python
# tests/infrastructure/memory/contextfiles/test_curated_projection_pure.py
from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.contextfiles.domain.curated import (
    render_curated_memory_markdown,
)

def test_empty_records_retains_skeleton():
    text = render_curated_memory_markdown([])
    assert "# 长期记忆" in text
    assert "## Preferences" in text
    assert "## Facts" in text
    assert "（暂无偏好记录）" in text
    assert "（暂无事实记录）" in text

def test_bullet_contains_embedded_id():
    records = [
        MemoryRecord(
            record_id="mem_123456",
            content="用户偏好暗色主题",
            category=MemoryCategory.PREFERENCE,
        ),
        MemoryRecord(
            record_id="mem_abcdef",
            content="开发机IP为10.36.6.252",
            category=MemoryCategory.FACT,
        ),
    ]
    text = render_curated_memory_markdown(records)
    assert "用户偏好暗色主题 <!-- id:mem_123456 -->" in text
    assert "开发机IP为10.36.6.252 <!-- id:mem_abcdef -->" in text

def test_identity_category_excluded():
    records = [
        MemoryRecord(
            record_id="mem_id_01",
            content="用户性别：男",
            category=MemoryCategory.IDENTITY,
        )
    ]
    text = render_curated_memory_markdown(records)
    assert "用户性别：男" not in text
    assert "## Facts" in text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/memory/contextfiles/test_curated_projection_pure.py -v`  
Expected: FAIL (函数未定义或骨架被跳过)

**Step 3: Implement minimal code in `curated.py`**

重构 `curated.py`，新增导出 `render_curated_memory_markdown` 并改造 `_sections` 与 `_bullet`，保证空节输出默认占位行，且 bullet 携带 `<!-- id:{claim_id} -->`。

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/memory/contextfiles/test_curated_projection_pure.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/contextfiles/domain/curated.py tests/infrastructure/memory/contextfiles/test_curated_projection_pure.py
git commit -m "feat(memory): add pure functional memory markdown projector with persistent skeleton and embedded id"
```

---

### Task 2: Markdown 编辑事件解析器 (INV-MEM-04, INV-MEM-05)

**Files:**
- Create: `lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py`
- Modify: `lca/infrastructure/memory/assistant_memory.py`（若需暴露批量/便捷操作）
- Test: `tests/infrastructure/memory/contextfiles/test_memory_edit_sync.py`
- Does NOT own: HTTP 路由层、前端代码
- Invariants to test:
  - INV-MEM-04: 无 ID 的新行触发 ADD；带现有 ID 且内容改变触发 SUPERSEDE；缺失的活跃 ID 触发 DELETE
  - INV-MEM-05: 原样提交投影 Markdown（Roundtrip）不产生任何变动

**Step 1: Write the failing test**

```python
# tests/infrastructure/memory/contextfiles/test_memory_edit_sync.py
from pathlib import Path
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.service.memory_edit_sync import (
    MemoryEditSyncService,
)

def test_memory_edit_sync_add_supersede_delete(tmp_path: Path):
    memory = AssistantMemory(tmp_path)
    sync = MemoryEditSyncService(memory)
    
    # 初始 markdown：新增两条记录
    initial_md = """# 长期记忆
## Preferences
- 喜欢简洁回答
## Facts
- 部署在内网服务器
"""
    sync.apply_markdown_edit(initial_md)
    facts = memory.query()
    assert len(facts) == 2
    
    # 获取生成的带 ID 文本
    projected = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "<!-- id:mem_" in projected
    
    # 用户操作：修改一条，新增一条，删除一条
    lines = projected.splitlines()
    modified_lines = []
    for line in lines:
        if "部署在内网服务器" in line:
            continue # 删除
        if "喜欢简洁回答" in line:
            # 修改内容，保留 ID
            modified_lines.append(line.replace("喜欢简洁回答", "非常喜欢极度简洁回答"))
        else:
            modified_lines.append(line)
    # 追加一条无 ID 的新条目
    modified_lines.append("- 常用数据库是 PostgreSQL")
    
    sync.apply_markdown_edit("\n".join(modified_lines))
    
    active_records = [r for r in memory.query() if not r.deleted]
    contents = [r.content for r in active_records]
    assert "非常喜欢极度简洁回答" in contents
    assert "常用数据库是 PostgreSQL" in contents
    assert "部署在内网服务器" not in contents
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/memory/contextfiles/test_memory_edit_sync.py -v`  
Expected: FAIL (`MemoryEditSyncService` not found)

**Step 3: Implement `MemoryEditSyncService`**

实现 Markdown Bullet 提取、ID 注释正则匹配、与当前记录的差集比对及 `upsert` / `supersede` / `remove` 调度，写完后自动触发 `memory._project_curated()`。

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/memory/contextfiles/test_memory_edit_sync.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py tests/infrastructure/memory/contextfiles/test_memory_edit_sync.py
git commit -m "feat(memory): implement MemoryEditSyncService for deterministic markdown edit writeback"
```

---

### Task 3: 路由写入窄门收敛 (INV-MEM-06)

**Files:**
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py:365-375`
- Test: `tests/lca_plugins/transport/webserver/test_memory_standing_file_edit_gate.py`
- Does NOT own: 其他 standing 文件的写逻辑（`SOUL.md` / `CONSTITUTION.md`）
- Invariants to test:
  - INV-MEM-06: `PUT .../standing-files/MEMORY.md` 绝不执行 `write_text` 裸覆盖，必定调用 `MemoryEditSyncService` 同步至 `semantic.json`

**Step 1: Write the failing test**

```python
# tests/lca_plugins/transport/webserver/test_memory_standing_file_edit_gate.py
import pytest
from starlette.requests import Request
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    update_standing_file,
)

@pytest.mark.asyncio
async def test_put_memory_md_syncs_to_semantic_json(assistant_fixture):
    # 发送 PUT 请求更新 MEMORY.md
    # 断言 semantic.json 文件产生了变更且包含新 record_id
    pass
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/lca_plugins/transport/webserver/test_memory_standing_file_edit_gate.py -v`  
Expected: FAIL

**Step 3: Modify `standing_files.py`**

在 `update_standing_file` 中：
```python
        elif filename == "MEMORY.md":
            from lca.infrastructure.memory.assistant_memory import AssistantMemory
            from lca.infrastructure.memory.contextfiles.service.memory_edit_sync import MemoryEditSyncService
            memory = AssistantMemory(file_path.parent)
            MemoryEditSyncService(memory).apply_markdown_edit(new_content)
        elif filename == "CONSTITUTION.md":
            file_path.write_text(new_content, encoding="utf-8")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/lca_plugins/transport/webserver/test_memory_standing_file_edit_gate.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py tests/lca_plugins/transport/webserver/test_memory_standing_file_edit_gate.py
git commit -m "refactor(webserver): enforce execution gate on MEMORY.md updates via MemoryEditSyncService"
```

---

### Task 4: 端到端集成与 Prompt 实时感知验收

**Files:**
- Test: `tests/integration/test_memory_stateless_projection_e2e.py`
- Invariants to test:
  - Tool 写入事实 -> `semantic.json` 写入 -> `MEMORY.md` 投影更新且骨架保留；
  - UI 编辑 `MEMORY.md` -> 回写到 `semantic.json` -> 再次投影幂等；
  - `persona_from_home` 读取 `MEMORY.md` 包含在 `backstory` 中。

**Step 1: Write integration test**

编写完整的全链路 E2E 场景测试。

**Step 2: Run test to verify it passes**

Run: `pytest tests/integration/test_memory_stateless_projection_e2e.py -v`  
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_memory_stateless_projection_e2e.py
git commit -m "test(memory): add full end-to-end integration test for stateless projection and edit writeback"
```

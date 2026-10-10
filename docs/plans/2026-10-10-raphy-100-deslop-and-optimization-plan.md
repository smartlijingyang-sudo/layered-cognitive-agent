# Raphy 100 次真实优化与去冗实施计划 (Wave 1 & Pipeline Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 ADR-0293 落地新一轮 Raphy 架构去冗与加深状态机，并单流执行 Wave 1（RA-104 ~ RA-108）共 5 项高杠杆真实架构优化故事，打通自动化闭环驱动。

**Architecture:** 采用波次渐进模型（Batch-Wave Loop）。通过 `scripts/run_raphy_wave.py` 驱动状态机，每波次 5 个正交 Story；每个 Story 经历“单测锁定 → 最小化重构 → ruff/pytest 门禁 → 单 commit 沉淀”的标准流水线，严禁任何破坏 C1~C14 或外仓资产的行为。

**Tech Stack:** Python 3.10+, Pytest, Ruff, Pydantic, Git, Starlette/LCA Kernel

---

### Task 1: 波次驱动与状态机接缝初始化 (RAPHY-WAVE1-HARNESS)

**Files:**
- Create: `scripts/run_raphy_wave.py`
- Modify: `raphy/prd.json`
- Test: `tests/scripts/test_run_raphy_wave.py`
- Does NOT own: `lca/cognition/`, `lca/runtime/`, `~/everything-library`
- Invariants to test: `INV-DESLOP-06`（状态机准确读取剩余 open stories；校验通过后状态原子更新）

**Step 1: 编写状态机驱动的失败单测**

```python
# tests/scripts/test_run_raphy_wave.py
import json
from scripts.run_raphy_wave import get_open_stories, mark_story_pass

def test_get_open_stories(tmp_path):
    prd_path = tmp_path / "prd.json"
    prd_path.write_text(json.dumps({
        "userStories": [
            {"id": "RA-104", "title": "Test 1", "passes": False},
            {"id": "RA-105", "title": "Test 2", "passes": True}
        ]
    }))
    open_stories = get_open_stories(prd_path)
    assert len(open_stories) == 1
    assert open_stories[0]["id"] == "RA-104"
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/scripts/test_run_raphy_wave.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_raphy_wave'`

**Step 3: 实现最小波次驱动脚本**

```python
# scripts/run_raphy_wave.py
import json
from pathlib import Path

def get_open_stories(prd_path: Path) -> list[dict]:
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    return [s for s in data.get("userStories", []) if not s.get("passes") and not s.get("dropped")]

def mark_story_pass(prd_path: Path, story_id: str, notes: str = "") -> None:
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    for s in data.get("userStories", []):
        if s.get("id") == story_id:
            s["passes"] = True
            if notes:
                s["notes"] = notes
            break
    prd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
```

**Step 4: 运行测试验证通过**

Run: `pytest tests/scripts/test_run_raphy_wave.py -v`  
Expected: PASS

**Step 5: 提交代码**

```bash
git add scripts/run_raphy_wave.py tests/scripts/test_run_raphy_wave.py
git commit -m "feat(raphy): add run_raphy_wave harness and status parser"
```

---

### Task 2: [RA-104] 收敛 host_probing.py 安全路径与消除静默异常

**Files:**
- Modify: `lca/infrastructure/cli/service/host_probing.py`
- Modify: `lca/infrastructure/cli/services/kernel/restart_report.py`
- Test: `tests/infrastructure/cli/test_host_probing.py`
- Does NOT own: `lca/contracts/`, `deploy/lobehub/`
- Invariants to test: `INV-DESLOP-03`（命令执行使用绝对路径解析或安全工具封包，消除 S603/S607/S110 告警）

**Step 1: 编写 host_probing 安全探查单测**

```python
# tests/infrastructure/cli/test_host_probing.py
from lca.infrastructure.cli.service.host_probing import resolve_probe_cmd, is_port_open

def test_resolve_probe_cmd_uses_shutil_which():
    cmd = resolve_probe_cmd("ss")
    assert cmd is not None
    assert cmd.startswith("/")
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/infrastructure/cli/test_host_probing.py -v`  
Expected: FAIL with `cannot import name 'resolve_probe_cmd'`

**Step 3: 优化 host_probing.py 消除 ruff 坏味道**

使用 `shutil.which` 解析绝对路径，替换裸字符串；将 `except Exception: pass` 替换为具名受控异常并记录调试日志；在 `restart_report.py` 中限制 url 协议必须为 `http`/`https`。

**Step 4: 运行测试与 ruff 验证**

Run: `pytest tests/infrastructure/cli/test_host_probing.py -v && ruff check lca/infrastructure/cli/`  
Expected: 0 errors

**Step 5: 提交代码**

```bash
git add lca/infrastructure/cli/service/host_probing.py lca/infrastructure/cli/services/kernel/restart_report.py tests/infrastructure/cli/test_host_probing.py
git commit -m "feat: [RA-104] - Resolve explicit binary paths in host_probing and eliminate S603/S607/S110 linter slop"
```

---

### Task 3: [RA-105] 治理 lca.contracts.mechanisms 导出与 L1/L2 声明偏差

**Files:**
- Modify: `lca/contracts/mechanisms.py`
- Modify: `lca/contracts/README.md`
- Test: `tests/contracts/test_mechanisms_package_contracts.py`
- Does NOT own: `lca/runtime/`, `lca/application/`
- Invariants to test: `INV-DESLOP-01`（`check_package_contracts.py` 中 `lca.contracts.mechanisms` 0 报错）

**Step 1: 编写 mechanisms 契约对齐单测**

```python
# tests/contracts/test_mechanisms_package_contracts.py
import subprocess
import sys

def test_mechanisms_package_contract_clean():
    res = subprocess.run(
        [sys.executable, "scripts/check_package_contracts.py"],
        capture_output=True,
        text=True
    )
    # 断言 mechanisms 不在失败列表中
    assert "lca.contracts.mechanisms" not in res.stdout
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/contracts/test_mechanisms_package_contracts.py -v`  
Expected: FAIL with `lca.contracts.mechanisms in res.stdout`

**Step 3: 修复 mechanisms 声明与 README.md 对齐**

在 `lca/contracts/README.md` 中补齐 Section 9 中遗漏的 19 项合法导出（`InspectResult`, `CapabilityGrantExceeded` 等），并在 `mechanisms.py` 中清理多余未导出或私有符号。

**Step 4: 运行测试验证通过**

Run: `pytest tests/contracts/test_mechanisms_package_contracts.py -v`  
Expected: PASS

**Step 5: 提交代码**

```bash
git add lca/contracts/mechanisms.py lca/contracts/README.md tests/contracts/test_mechanisms_package_contracts.py
git commit -m "feat: [RA-105] - Align lca.contracts.mechanisms exports with L1/L2 package contracts specification"
```

---

### Task 4: [RA-106] 治理 lca.infrastructure.observability 契约接口偏差

**Files:**
- Modify: `lca/infrastructure/observability/__init__.py`
- Modify: `lca/infrastructure/observability/README.md`
- Test: `tests/infrastructure/observability/test_observability_package_contracts.py`
- Does NOT own: `lca/contracts/`, `lca/agent/`
- Invariants to test: `INV-DESLOP-01`（`check_package_contracts.py` 中 `lca.infrastructure.observability` 0 报错）

**Step 1: 编写 observability 契约对齐单测**

```python
# tests/infrastructure/observability/test_observability_package_contracts.py
import subprocess
import sys

def test_observability_package_contract_clean():
    res = subprocess.run(
        [sys.executable, "scripts/check_package_contracts.py"],
        capture_output=True,
        text=True
    )
    assert "lca.infrastructure.observability" not in res.stdout
```

**Step 2: 运行测试验证失败**

Run: `pytest tests/infrastructure/observability/test_observability_package_contracts.py -v`  
Expected: FAIL

**Step 3: 同步 README.md 与 __init__.py 导出**

将 `InMemoryJournalStore`, `RunState`, `fold_run_state` 等内部辅助或公共入口在 README.md Section 9 显式登记，收拢非公共内部辅助函数。

**Step 4: 运行测试验证通过**

Run: `pytest tests/infrastructure/observability/test_observability_package_contracts.py -v`  
Expected: PASS

**Step 5: 提交代码**

```bash
git add lca/infrastructure/observability/__init__.py lca/infrastructure/observability/README.md tests/infrastructure/observability/test_observability_package_contracts.py
git commit -m "feat: [RA-106] - Converge observability package contract exports and align README SSOT"
```

---

### Task 5: [RA-107] 接缝显式 Fail-Loud 加固与隐式降级清除

**Files:**
- Modify: `lca/contracts/protocols/` 相关 Seam 适配器
- Test: `tests/contracts/test_seam_fail_loud.py`
- Does NOT own: `lca/cognition/prompt/`
- Invariants to test: `INV-DESLOP-03`（空能力或非法接缝调用抛出具名异常，杜绝静默 None）

**Step 1: 编写 Seam Fail-Loud 负向断言测试**

```python
# tests/contracts/test_seam_fail_loud.py
import pytest

def test_seam_raises_on_unregistered_capability():
    # 断言非法能力不静默返回空
    pass
```

**Step 2: 运行测试验证**

Run: `pytest tests/contracts/test_seam_fail_loud.py -v`

**Step 3: 最小化收拢代码**

切除 fallback 中的 silent pass / None 返回，抛出对应 `MissingCapabilityError`。

**Step 4: 运行测试并回归**

Run: `pytest tests/contracts/ -v && ruff check lca/contracts/`  
Expected: PASS, clean

**Step 5: 提交代码**

```bash
git add lca/contracts/ tests/contracts/test_seam_fail_loud.py
git commit -m "feat: [RA-107] - Enforce fail-loud semantics across capability seams and eliminate silent none returns"
```

---

### Task 6: [RA-108] 全链路回归体检与 Wave 1 归档

**Files:**
- Modify: `raphy/prd.json`
- Modify: `raphy/progress.txt`
- Modify: `docs/plans/task.md`
- Does NOT own: 业务核心代码
- Invariants to test: `INV-DESLOP-02`, `INV-DESLOP-04`, `INV-DESLOP-05`

**Step 1: 执行全量关联回归与架构体检**

```bash
pytest tests/infrastructure/cli/ tests/contracts/ tests/infrastructure/observability/ -v
python3 scripts/run_raphy_wave.py --verify-all
ruff check lca/
git diff --check
```

**Step 2: 更新看板与知识库**

在 `raphy/progress.txt` 沉淀 Wave 1 经验，更新 `docs/plans/task.md`。

**Step 3: 提交并打标**

```bash
git add raphy/ docs/plans/task.md
git commit -m "chore(raphy): complete wave 1 (RA-104~RA-108) architecture deslop and deepening"
```

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-10-10-raphy-100-deslop-and-optimization-plan.md`.  
Next step: run `.agent/workflows/execute-plan.md` to execute this plan task-by-task in single-flow mode.

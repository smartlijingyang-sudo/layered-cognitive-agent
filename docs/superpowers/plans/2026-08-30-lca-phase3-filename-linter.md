# LCA Phase 3 — 命名规范自动化（filename linter）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施 `scripts/check_filename_boundaries.py`，把 `docs/specs/naming-conventions.md` 的反例（`util / helper / manager / impl / common / misc`）挂 CI。已有违规文件入 `legacy_blacklist.txt` warning，新代码立即 error。季度清理升级为 error。

**Architecture:** 4 个机制协同：(1) 默认 blacklist + 包级 whitelist；(2) `legacy_blacklist.txt` 仓库根登记已存违规；(3) 与 L1 README 段 9（公共入口）联动验证 `__init__.py.__all__`；(4) CI 三阶段切换（warning → 季度清理 → error）。

**Tech Stack:** Python ≥3.11、pathlib、fnmatch、pytest、tomllib、ast。

**Spec:** `docs/superpowers/specs/2026-08-30-lca-modularization-design.md`（§6 Phase 3 详细设计为本 plan 的 spec 源）

**前置:** Phase 1 完成（L4 check_package_contracts.py 全绿）。Phase 2 可与 Phase 3 并行（Phase 3 不依赖 Phase 2 的语义名，只依赖 L1/L2 段）。

## Global Constraints

- Python ≥3.11
- 既有 CI 必绿：`uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q && uv run python scripts/check_package_contracts.py`
- 不动 `lobehub-ui/` 和 `vendor/`
- Conventional Commits
- C1–C7 闭集纪律
- 与 `docs/specs/naming-conventions.md` 已有的反例清单一致

---

## Task 1: 创建 legacy_blacklist.txt 与默认 whitelist

**Files:**
- Create: `legacy_blacklist.txt`
- Create: `scripts/_filename_rules.py`（默认规则 + 包级覆盖规则）

- [ ] **Step 1: 创建 `legacy_blacklist.txt`**

```text
# Legacy filename blacklist. New code MUST NOT add to this list.
# Format: <relative_path>  # <reason + introduced_in>
# Example:
# lca/infrastructure/observability/trace_tool.py  # 历史命名，Phase 3 不强制改；introduced 2025-Q3
```

- [ ] **Step 2: 创建 `scripts/_filename_rules.py`**

```python
"""Default filename blacklist + whitelist for LCA.

Override per package in pyproject.toml [tool.lca.package_contracts.<pkg>]
via `filename_whitelist` and `filename_blacklist_extra` fields.
"""

from __future__ import annotations

from fnmatch import fnmatch

# 默认 blacklist 模式
DEFAULT_BLACKLIST: list[str] = [
    "*util*.py",
    "*helper*.py",
    "*manager*.py",
    "*impl*.py",
    "*common*.py",
    "*misc*.py",
]

# 默认 whitelist（blacklist 命中但允许）
DEFAULT_WHITELIST: list[str] = [
    "lca/contracts/__init__.py",
    "lca/contracts/atoms/__init__.py",
    "lca/harness/__init__.py",
    "lca/plugins/__init__.py",
    "**/__init__.py",  # Python 包标识
]


def is_blacklisted(rel_path: str, extra_blacklist: list[str] | None = None) -> bool:
    """Return True if filename matches any blacklist pattern."""
    patterns = DEFAULT_BLACKLIST + (extra_blacklist or [])
    return any(fnmatch(rel_path, p) for p in patterns)


def is_whitelisted(rel_path: str, package_whitelist: list[str] | None = None) -> bool:
    """Return True if filename matches any whitelist pattern."""
    patterns = DEFAULT_WHITELIST + (package_whitelist or [])
    return any(fnmatch(rel_path, p) for p in patterns)
```

- [ ] **Step 3: 写测试 `tests/scripts/test_filename_rules.py`**

覆盖：
- `*util*.py` 命中 blacklist
- `lca/contracts/__init__.py` 不命中 blacklist（whitelist）
- `__init__.py` 在任何目录都不命中
- 自定义 `filename_whitelist` 覆盖

- [ ] **Step 4: 跑测试**

```bash
uv run pytest tests/scripts/test_filename_rules.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add legacy_blacklist.txt scripts/_filename_rules.py tests/scripts/test_filename_rules.py
git commit -m "feat(filename-rules): add default blacklist/whitelist + legacy_blacklist.txt"
```

---

## Task 2: 实施 check_filename_boundaries.py

**Files:**
- Create: `scripts/check_filename_boundaries.py`
- Create: `tests/scripts/test_check_filename_boundaries.py`

- [ ] **Step 1: 写测试**

测试覆盖：
- 新建 `*util*.py` 报错（mock 为新文件）
- `legacy_blacklist.txt` 登记的 `*util*.py` 警告
- whitelist 命中不报错
- `__init__.py` 不报错
- 退出码：新=1 + 旧=0；新=0 + 旧=0 → 0

- [ ] **Step 2: 实施脚本骨架**

```python
"""Enforce filename blacklist/whitelist + legacy_blacklist.

Usage:
    uv run python scripts/check_filename_boundaries.py
    uv run python scripts/check_filename_boundaries.py --strict  # 旧文件也 error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from _filename_rules import is_blacklisted, is_whitelisted

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LEGACY = ROOT / "legacy_blacklist.txt"

EXCLUDE_DIRS = {"lobehub-ui", "vendor", "node_modules", ".git", "__pycache__", "build", "dist"}


@dataclass
class Issue:
    path: str
    kind: str  # "new_violation" | "legacy_warning"
    message: str

    def render(self) -> str:
        prefix = "ERROR" if self.kind == "new_violation" else "WARN "
        return f"{prefix}: {self.path}: {self.message}"


def load_legacy_blacklist() -> set[str]:
    if not LEGACY.exists():
        return set()
    return {line.split("#")[0].strip() for line in LEGACY.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")}


def load_package_whitelists() -> dict[str, list[str]]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    return {pkg: cfg.get("filename_whitelist", []) for pkg, cfg in contracts.items()}


def all_python_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="treat legacy as error")
    args = parser.parse_args()

    legacy = load_legacy_blacklist()
    pkg_wl = load_package_whitelists()

    issues: list[Issue] = []
    for path in all_python_files():
        rel = str(path.relative_to(ROOT))
        if is_whitelisted(rel):
            continue
        # package whitelist 检查
        for pkg, wl in pkg_wl.items():
            pkg_path = pkg.replace(".", "/") + "/"
            if rel.startswith(pkg_path) and is_whitelisted(rel.replace(pkg_path, ""), wl):
                break
        else:
            if is_blacklisted(rel):
                if rel in legacy:
                    issues.append(Issue(rel, "legacy_warning", "filename matches blacklist (in legacy_blacklist.txt)"))
                else:
                    issues.append(Issue(rel, "new_violation", "filename matches blacklist; add to legacy_blacklist.txt or rename"))

    new_violations = [i for i in issues if i.kind == "new_violation"]
    legacy_warnings = [i for i in issues if i.kind == "legacy_warning"]

    for issue in issues:
        print(issue.render())

    print(f"\nnew violations: {len(new_violations)}, legacy warnings: {len(legacy_warnings)}")

    if new_violations:
        return 1
    if args.strict and legacy_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 跑测试**

```bash
uv run pytest tests/scripts/test_check_filename_boundaries.py -v
# Expected: PASS
```

- [ ] **Step 4: 跑脚本扫当前仓库**

```bash
uv run python scripts/check_filename_boundaries.py
# Expected: 输出当前违规清单（如有），把已有违规加入 legacy_blacklist.txt
```

- [ ] **Step 5: 扫并填 legacy_blacklist.txt**

```bash
# 把输出中非新文件的违规填入 legacy_blacklist.txt
# 例：lca/infrastructure/observability/trace_tool.py  # 历史命名
```

- [ ] **Step 6: 重跑验证**

```bash
uv run python scripts/check_filename_boundaries.py
# Expected: new violations: 0, legacy warnings: N
```

- [ ] **Step 7: Commit**

```bash
git add scripts/check_filename_boundaries.py tests/scripts/test_check_filename_boundaries.py legacy_blacklist.txt
git commit -m "feat(filename-linter): add check_filename_boundaries.py with legacy_blacklist"
```

---

## Task 3: 扩展 L1/L2 段加 filename 字段

**Files:**
- Modify: `pyproject.toml [tool.lca.package_contracts.*]`（已有 89 段）

- [ ] **Step 1: 扫哪些包需要 filename_whitelist**

```bash
# 找当前 legacy_blacklist.txt 中涉及哪些包
grep -v '^#' legacy_blacklist.txt | awk '{print $1}' | xargs -I {} dirname {} | sort -u
```

- [ ] **Step 2: 给相关包 L2 段加 filename_whitelist**

```toml
[tool.lca.package_contracts."lca.infrastructure.observability"]
# ... 已有 9 字段
filename_whitelist = ["trace_tool.py"]  # 历史命名保留
```

- [ ] **Step 3: 跑 check 验证**

```bash
uv run python scripts/check_filename_boundaries.py
# Expected: new violations: 0
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(contracts): add filename_whitelist to relevant package_contracts sections"
```

---

## Task 4: 与 L1 公共入口联动

**Files:**
- Modify: `scripts/check_package_contracts.py`

- [ ] **Step 1: 在 L4 check 加新一致性检查**

验证 `__init__.py` 的 `__all__` 与 L1 README 段 9（公共入口）一致：
- `__all__` 中的每个符号应在 L1 段 9 列出
- L1 段 9 列出的每个符号应在 `__all__` 中

- [ ] **Step 2: 写测试**

测试覆盖：符号缺失、符号多余、一致。

- [ ] **Step 3: 实现检查函数**

```python
def cross_check_l1_public_api(root: Path, packages: list[str]) -> list[Issue]:
    """Verify __init__.py.__all__ matches L1 README 段 9 公共入口."""
    issues = []
    for pkg in packages:
        init = package_to_path(root, pkg) / "__init__.py"
        if not init.exists():
            continue
        readme = package_to_path(root, pkg) / "README.md"
        if not readme.exists():
            continue
        # 解析 __all__
        text = init.read_text(encoding="utf-8")
        all_match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
        all_symbols = set()
        if all_match:
            for sym in all_match.group(1).split(","):
                sym = sym.strip().strip("'\"")
                if sym and sym != "*":
                    all_symbols.add(sym)
        # 解析 L1 README 段 9
        readme_text = readme.read_text(encoding="utf-8")
        section_match = re.search(r"## 9\. 公共入口\s*\n(.*?)(?=\n##|\Z)", readme_text, re.DOTALL)
        if not section_match:
            continue
        l1_symbols = set(re.findall(r"`?(\w+)`?", section_match.group(1)))
        # 比较
        for sym in all_symbols - l1_symbols:
            issues.append(Issue(pkg, "L1↔__all__", f"__all__ contains {sym} not in L1 section 9"))
        for sym in l1_symbols - all_symbols:
            if sym in {"lca", "X", "Y", "Z", "tool", "data", "name", "id", "value", "type"}:
                continue
            issues.append(Issue(pkg, "L1↔__all__", f"L1 section 9 lists {sym} not in __all__"))
    return issues
```

- [ ] **Step 4: 跑测试**

```bash
uv run pytest tests/scripts/test_check_package_contracts.py -v
# Expected: PASS
```

- [ ] **Step 5: 跑 L4 check 验证**

```bash
uv run python scripts/check_package_contracts.py
# Expected: 全绿（如有不一致，按输出修复 __init__.py 或 README）
```

- [ ] **Step 6: Commit**

```bash
git add scripts/check_package_contracts.py
git commit -m "feat(check): cross-check L1 README 段9 公共入口 vs __init__.py.__all__"
```

---

## Task 5: CI 接入（warning 模式）

**Files:**
- Modify: CI workflow 文件

- [ ] **Step 1: 接入 check_filename_boundaries**

```yaml
- name: Check filename boundaries
  run: uv run python scripts/check_filename_boundaries.py || echo "::warning::filename violations found"
```

- [ ] **Step 2: 跑全量 CI 验证不破坏**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q && uv run python scripts/check_package_contracts.py
# Expected: 全绿
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/  # 或实际 CI 文件
git commit -m "ci: add check_filename_boundaries (warning, non-blocking)"
```

---

## Task 6: 季度清理脚本

**Files:**
- Create: `scripts/quarterly_legacy_cleanup.py`

- [ ] **Step 1: 实施脚本**

脚本职责：
- 扫 `legacy_blacklist.txt` 中的每条记录
- 检查过去 90 天是否有 PR 涉及该文件（`git log --since="90 days ago" -- <path>`）
- 没有 → 输出"可清理候选"
- 有 → 保持

- [ ] **Step 2: 写测试**

- [ ] **Step 3: 跑 dry-run**

```bash
uv run python scripts/quarterly_legacy_cleanup.py --dry-run
# Expected: 列出可清理候选
```

- [ ] **Step 4: 提交**

```bash
git add scripts/quarterly_legacy_cleanup.py tests/scripts/test_quarterly_legacy_cleanup.py
git commit -m "feat(cleanup): add quarterly_legacy_cleanup.py for legacy_blacklist rotation"
```

---

## Task 7: Phase 3 验收

- [ ] **Step 1: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q && uv run python scripts/check_package_contracts.py && uv run python scripts/check_filename_boundaries.py
# Expected: 全绿
```

- [ ] **Step 2: 对照 spec §6.5 验收清单**

| 项 | 状态 |
|---|---|
| check_filename_boundaries.py 实施 | ☐ |
| legacy_blacklist.txt 创建 | ☐ |
| L2 段 filename_whitelist 字段就位 | ☐ |
| 新代码 CI 报错 | ☐ |
| 已存违规 CI warning | ☐ |
| L1 公共入口 ↔ __all__ 一致性 | ☐ |
| 既有 CI 保持绿 | ☐ |

- [ ] **Step 3: 提交 Phase 3 完成**

```bash
git tag phase-3-complete
git commit --allow-empty -m "chore: Phase 3 complete - filename linter active in warning mode"
```

---

## Self-Review Checklist

- [ ] 7 个 task，每个独立可测
- [ ] Task 1 模板与 Task 2 linter 分离（`scripts/_filename_rules.py` 可复用）
- [ ] Task 4 与 Phase 1 L4 check 联动（不重写 L4，而是扩展）
- [ ] warning → error 升级路径明确（季度清理脚本 Task 6）
- [ ] `legacy_blacklist.txt` 是仓库根文件（所有 contributor 可见）
- [ ] 不动 lobehub-ui/ 和 vendor/ 是 Global Constraints

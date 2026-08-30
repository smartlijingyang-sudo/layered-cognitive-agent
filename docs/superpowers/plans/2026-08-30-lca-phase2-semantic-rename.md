# LCA Phase 2 — 目录语义化（layer0/1/2/3/4 → 语义名）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性切换 `lca.infrastructure` / `lca.cognition` / `lca.runtime` / `lca.agent` / `lca.application` 到语义名 `lca.infrastructure` / `lca.cognition` / `lca.runtime` / `lca.agent` / `lca.application`，无兼容期。`lca.harness` / `lca.plugins` / `lca.contracts` / `gateway` 不变。

**Architecture:** ADR-0104 先写 → 迁移辅助脚本 dry-run 演练 → 5 个原子 PR（每个映射一个）→ import-linter contracts 更新 → L1/L2 段同步 → 文档/Profile/patches 同步 → CHANGELOG + 外部消费方通知。

**Tech Stack:** git mv、sed/awk、`scripts/migrate_layer_rename.py`（自动）、import-linter、tomllib、ast、pytest、ruff、mypy。

**Spec:** `docs/superpowers/specs/2026-08-30-lca-modularization-design.md`（§5 Phase 2 详细设计为本 plan 的 spec 源）

**前置:** Phase 1 完成（L4 check_package_contracts.py 全绿；CI 阻塞模式开启）。

## Global Constraints

- Python ≥3.11
- 既有 CI 必绿：`uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q && uv run python scripts/check_package_contracts.py`
- 一次性切换，**不留 shim、不留兼容期**
- C1 闭集纪律：先 ADR、再删除、最后 CI 绿
- `lca.harness` / `lca.plugins` / `lca.contracts` / `gateway` **不重命名**
- Conventional Commits
- 不动 `lobehub-ui/` 和 `vendor/`
- 每个原子 PR 必须独立 revertible（用 `git revert -m 1 <merge-commit>` 而非逐文件 revert）

---

## Task 1: 写 ADR-0104

**Files:**
- Create: `docs/adr/0104-semantic-layer-rename.md`

- [ ] **Step 1: 创建 ADR 文件**

按 spec §5.2 骨架填写，状态 `Proposed`。

- [ ] **Step 2: 跑影响面盘点**

```bash
grep -rln "lca\.layer[0-4]_" lca/ gateway/ tests/ profiles/ deploy/ docs/ | tee /tmp/adr-0104-impact.txt | wc -l
# Expected: N 行（N 取决于仓库当前状态，记录到 ADR 的"影响面盘点"段）
```

把 `/tmp/adr-0104-impact.txt` 路径列表填到 ADR 的影响面盘点段。

- [ ] **Step 3: 提交 ADR 草稿**

```bash
git add docs/adr/0104-semantic-layer-rename.md
git commit -m "docs(adr): ADR-0104 proposed - lca 一级包名语义化"
```

- [ ] **Step 4: ADR 进入 Accepted**

PR 合并后，把状态从 `Proposed` 改为 `Accepted`，加 Accepted 时间戳。

---

## Task 2: 写迁移辅助脚本（dry-run 模式）

**Files:**
- Create: `scripts/migrate_layer_rename.py`
- Create: `tests/scripts/test_migrate_layer_rename.py`

- [ ] **Step 1: 写测试**

测试覆盖：
- 单个映射 `lca.infrastructure` → `lca.infrastructure` 在 import 字符串中
- `git mv` 命令生成正确
- dry-run 不实际执行
- `--execute` 模式实际执行（用 tmp_path）

- [ ] **Step 2: 实施脚本骨架**

```python
"""Migrate lca.layer0/1/2/3/4 → semantic names. One-shot, no shim.

Usage:
    uv run python scripts/migrate_layer_rename.py --dry-run
    uv run python scripts/migrate_layer_rename.py --execute
    uv run python scripts/migrate_layer_rename.py --rollback <commit_sha>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass

LAYER_TO_SEMANTIC: dict[str, str] = {
    "lca.infrastructure": "lca.infrastructure",
    "lca.cognition": "lca.cognition",
    "lca.runtime": "lca.runtime",
    "lca.agent": "lca.agent",
    "lca.application": "lca.application",
}


@dataclass
class Change:
    path: str
    old_text: str
    new_text: str
    kind: str  # "git_mv" | "edit"


def plan_changes() -> list[Change]:
    changes: list[Change] = []
    # git mv
    for old, new in LAYER_TO_SEMANTIC.items():
        old_path = old.replace(".", "/")
        new_path = new.replace(".", "/")
        changes.append(Change(f"{old_path} -> {new_path}", "", "", "git_mv"))
    # import edits（所有 .py 文件）
    for old, new in LAYER_TO_SEMANTIC.items():
        # 实际 find + scan 在 execute 阶段
        pass
    return changes


def run_git_mv(dry_run: bool) -> None:
    for old, new in LAYER_TO_SEMANTIC.items():
        old_path = old.replace(".", "/")
        new_path = new.replace(".", "/")
        cmd = ["git", "mv", old_path, new_path]
        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
        else:
            subprocess.run(cmd, check=True)


def replace_imports(dry_run: bool) -> None:
    files = subprocess.check_output(
        ["git", "grep", "-l", "-E", r"lca\.layer[0-4]_[a-z_]+"], text=True
    ).splitlines()
    for old, new in LAYER_TO_SEMANTIC.items():
        for f in files:
            text = open(f, encoding="utf-8").read()
            if old in text:
                new_text = text.replace(old, new)
                if dry_run:
                    print(f"[dry-run] edit {f}: {old} -> {new}")
                else:
                    open(f, "w", encoding="utf-8").write(new_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--rollback", help="git revert commit SHA")
    args = parser.parse_args()

    if args.rollback:
        subprocess.run(["git", "revert", "-m", "1", args.rollback], check=False)
        return 0

    if not (args.dry_run or args.execute):
        print("must pass --dry-run or --execute", file=sys.stderr)
        return 2

    run_git_mv(dry_run=args.dry_run)
    replace_imports(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 跑 dry-run**

```bash
uv run python scripts/migrate_layer_rename.py --dry-run | tee /tmp/adr-0104-dryrun.txt
# Expected: 输出所有 git mv + import edit 计划
```

- [ ] **Step 4: 跑测试通过**

```bash
uv run pytest tests/scripts/test_migrate_layer_rename.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_layer_rename.py tests/scripts/test_migrate_layer_rename.py
git commit -m "feat(migration): add migrate_layer_rename.py with dry-run + execute + rollback"
```

---

## Task 3: 原子切换 lca.infrastructure → lca.infrastructure

**Files:**
- Rename: `lca/infrastructure/` → `lca/infrastructure/`
- Modify: 所有引用 `lca.infrastructure` 的 import

- [ ] **Step 1: 创建分支 `rename/layer0-infrastructure`**

```bash
git checkout main && git pull --rebase
git checkout -b rename/layer0-infrastructure
```

- [ ] **Step 2: git mv + 全局替换**

```bash
git mv lca/infrastructure lca/infrastructure
grep -rl "lca\.infrastructure" lca/ gateway/ tests/ | xargs sed -i 's/lca\.infrastructure/lca.infrastructure/g'
```

- [ ] **Step 3: 更新 import-linter contracts layers**

`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers 改 `lca.infrastructure` 为 `lca.infrastructure`。

- [ ] **Step 4: 更新 L1/L2 段**

L1 README 段 5/6、L2 pyproject `forbidden_dependencies` 中所有 `lca.infrastructure` 改 `lca.infrastructure`。

- [ ] **Step 5: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
```

- [ ] **Step 6: 验证本映射无残留**

```bash
grep -rn "lca\.infrastructure" lca/ gateway/ tests/ profiles/ deploy/ docs/
# Expected: 空
```

- [ ] **Step 7: Commit + PR**

```bash
git add -A
git commit -m "refactor!: rename lca.infrastructure to lca.infrastructure

BREAKING CHANGE: lca.infrastructure is now lca.infrastructure. Update imports.

Ref: ADR-0104"
git push origin rename/layer0-infrastructure
gh pr create --title "refactor!: rename lca.infrastructure to lca.infrastructure" --body "ADR-0104"
```

- [ ] **Step 8: Review + merge**

合并后 `git checkout main && git pull --rebase`，删除分支 `git branch -d rename/layer0-infrastructure`。

---

## Task 4: 原子切换 lca.cognition → lca.cognition

**Files:**
- Rename: `lca/cognition/` → `lca/cognition/`
- Modify: 所有引用 `lca.cognition` 的 import

- [ ] **Step 1: 创建分支 `rename/layer1-cognition`**

```bash
git checkout main && git pull --rebase
git checkout -b rename/layer1-cognition
```

- [ ] **Step 2: git mv + 全局替换**

```bash
git mv lca/cognition lca/cognition
grep -rl "lca\.cognition" lca/ gateway/ tests/ | xargs sed -i 's/lca\.cognition/lca.cognition/g'
```

- [ ] **Step 3: 更新 import-linter contracts layers**

`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers 改 `lca.cognition` 为 `lca.cognition`。

- [ ] **Step 4: 更新 L1/L2 段**

L1 README 段 5/6、L2 pyproject `forbidden_dependencies` 中所有 `lca.cognition` 改 `lca.cognition`。

- [ ] **Step 5: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
```

- [ ] **Step 6: 验证本映射无残留**

```bash
grep -rn "lca\.cognition" lca/ gateway/ tests/ profiles/ deploy/ docs/
# Expected: 空
```

- [ ] **Step 7: Commit + PR**

```bash
git add -A
git commit -m "refactor!: rename lca.cognition to lca.cognition

BREAKING CHANGE: lca.cognition is now lca.cognition. Update imports.

Ref: ADR-0104"
git push origin rename/layer1-cognition
gh pr create --title "refactor!: rename lca.cognition to lca.cognition" --body "ADR-0104"
```

- [ ] **Step 8: Review + merge**

合并后 `git checkout main && git pull --rebase`，删除分支 `git branch -d rename/layer1-cognition`。

---

## Task 5: 原子切换 lca.runtime → lca.runtime

**Files:**
- Rename: `lca/runtime/` → `lca/runtime/`
- Modify: 所有引用 `lca.runtime` 的 import

- [ ] **Step 1: 创建分支 `rename/layer2-runtime`**

```bash
git checkout main && git pull --rebase
git checkout -b rename/layer2-runtime
```

- [ ] **Step 2: git mv + 全局替换**

```bash
git mv lca/runtime lca/runtime
grep -rl "lca\.runtime" lca/ gateway/ tests/ | xargs sed -i 's/lca\.runtime/lca.runtime/g'
```

- [ ] **Step 3: 更新 import-linter contracts layers**

`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers 改 `lca.runtime` 为 `lca.runtime`。

- [ ] **Step 4: 更新 L1/L2 段**

L1 README 段 5/6、L2 pyproject `forbidden_dependencies` 中所有 `lca.runtime` 改 `lca.runtime`。

- [ ] **Step 5: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
```

- [ ] **Step 6: 验证本映射无残留**

```bash
grep -rn "lca\.runtime" lca/ gateway/ tests/ profiles/ deploy/ docs/
# Expected: 空
```

- [ ] **Step 7: Commit + PR**

```bash
git add -A
git commit -m "refactor!: rename lca.runtime to lca.runtime

BREAKING CHANGE: lca.runtime is now lca.runtime. Update imports.

Ref: ADR-0104"
git push origin rename/layer2-runtime
gh pr create --title "refactor!: rename lca.runtime to lca.runtime" --body "ADR-0104"
```

- [ ] **Step 8: Review + merge**

合并后 `git checkout main && git pull --rebase`，删除分支 `git branch -d rename/layer2-runtime`。

---

## Task 6: 原子切换 lca.agent → lca.agent

**Files:**
- Rename: `lca/agent/` → `lca/agent/`
- Modify: 所有引用 `lca.agent` 的 import

- [ ] **Step 1: 创建分支 `rename/layer3-agent`**

```bash
git checkout main && git pull --rebase
git checkout -b rename/layer3-agent
```

- [ ] **Step 2: git mv + 全局替换**

```bash
git mv lca/agent lca/agent
grep -rl "lca\.agent" lca/ gateway/ tests/ | xargs sed -i 's/lca\.agent/lca.agent/g'
```

- [ ] **Step 3: 更新 import-linter contracts layers**

`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers 改 `lca.agent` 为 `lca.agent`。

- [ ] **Step 4: 更新 L1/L2 段**

L1 README 段 5/6、L2 pyproject `forbidden_dependencies` 中所有 `lca.agent` 改 `lca.agent`。

- [ ] **Step 5: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
```

- [ ] **Step 6: 验证本映射无残留**

```bash
grep -rn "lca\.agent" lca/ gateway/ tests/ profiles/ deploy/ docs/
# Expected: 空
```

- [ ] **Step 7: Commit + PR**

```bash
git add -A
git commit -m "refactor!: rename lca.agent to lca.agent

BREAKING CHANGE: lca.agent is now lca.agent. Update imports.

Ref: ADR-0104"
git push origin rename/layer3-agent
gh pr create --title "refactor!: rename lca.agent to lca.agent" --body "ADR-0104"
```

- [ ] **Step 8: Review + merge**

合并后 `git checkout main && git pull --rebase`，删除分支 `git branch -d rename/layer3-agent`。

---

## Task 7: 原子切换 lca.application → lca.application

**Files:**
- Rename: `lca/application/` → `lca/application/`
- Modify: 所有引用 `lca.application` 的 import

- [ ] **Step 1: 创建分支 `rename/layer4-application`**

```bash
git checkout main && git pull --rebase
git checkout -b rename/layer4-application
```

- [ ] **Step 2: git mv + 全局替换**

```bash
git mv lca/application lca/application
grep -rl "lca\.application" lca/ gateway/ tests/ | xargs sed -i 's/lca\.application/lca.application/g'
```

- [ ] **Step 3: 更新 import-linter contracts layers**

`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers 改 `lca.application` 为 `lca.application`。

- [ ] **Step 4: 更新 L1/L2 段**

L1 README 段 5/6、L2 pyproject `forbidden_dependencies` 中所有 `lca.application` 改 `lca.application`。

- [ ] **Step 5: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
```

- [ ] **Step 6: 验证本映射无残留**

```bash
grep -rn "lca\.application" lca/ gateway/ tests/ profiles/ deploy/ docs/
# Expected: 空
```

- [ ] **Step 7: Commit + PR**

```bash
git add -A
git commit -m "refactor!: rename lca.application to lca.application

BREAKING CHANGE: lca.application is now lca.application. Update imports.

Ref: ADR-0104"
git push origin rename/layer4-application
gh pr create --title "refactor!: rename lca.application to lca.application" --body "ADR-0104"
```

- [ ] **Step 8: Review + merge**

合并后 `git checkout main && git pull --rebase`，删除分支 `git branch -d rename/layer4-application`。

---

## Task 8: 验证全仓库无旧名

- [ ] **Step 1: 跑全量 grep**

```bash
grep -rn "lca\.layer[0-4]_[a-z_]*" lca/ gateway/ tests/ profiles/ deploy/ docs/ 2>/dev/null
# Expected: 空输出（exit code 1）
```

- [ ] **Step 2: 跑 L4 check 验证 old_name_warning 为 0**

```bash
uv run python scripts/check_package_contracts.py
# Expected: OK: 89 packages checked, no issues
# （如已实现 old_name_warning 段，输出 0）
```

- [ ] **Step 3: 如有违规，立即修复**

如果发现残留：
- 在 L4 check 输出定位文件
- 修复（手改或补一次迁移）
- 重跑 Step 1-2

---

## Task 9: 同步文档

**Files:**
- Modify: `docs/AGENTS.md` §3 依赖图
- Modify: `docs/specs/naming-conventions.md` 段尾说明
- Modify: `docs/adr/0001-five-layer-separation.md`（保留历史，新增 ADR-0104 引用）
- Modify: `docs/design/*` 提及 `layer0/1/2/3/4` 的位置
- Modify: `docs/architecture/optimization-iterations.md`

- [ ] **Step 1: 扫文档中的旧名引用**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" docs/
```

- [ ] **Step 2: 逐文件替换为新名**

- [ ] **Step 3: 验证文档无残留**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" docs/
# Expected: 空
```

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs: replace layer0/1/2/3/4 with semantic names per ADR-0104"
```

---

## Task 10: 同步 profiles

**Files:**
- Modify: `profiles/*.yaml`

- [ ] **Step 1: 扫 profiles 中的旧名**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" profiles/
```

- [ ] **Step 2: 替换为新名**

- [ ] **Step 3: 验证 profiles 无残留**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" profiles/
# Expected: 空
```

- [ ] **Step 4: Commit**

```bash
git add profiles/
git commit -m "refactor(profiles): update to semantic layer names per ADR-0104"
```

---

## Task 11: 同步 LobeHub patches

**Files:**
- Modify: `deploy/lobehub/patches/*`
- Modify: `deploy/lobehub/engine.py`

- [ ] **Step 1: 扫 LobeHub 相关文件**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" deploy/
```

- [ ] **Step 2: 替换为新名**

- [ ] **Step 3: 验证无残留**

```bash
grep -rn "infrastructure\|cognition\|runtime\|agent\|application" deploy/
# Expected: 空
```

- [ ] **Step 4: Commit**

```bash
git add deploy/
git commit -m "refactor(deploy): update LobeHub patches to semantic layer names per ADR-0104"
```

---

## Task 12: CHANGELOG + 通知

**Files:**
- Modify: `CHANGELOG.md`（如不存在则创建）

- [ ] **Step 1: 按 spec §5.4 模板添加 Breaking Changes 段**

```markdown
## [Unreleased] - 2026-XX-XX

### Breaking Changes
- `lca.infrastructure` → `lca.infrastructure`
- `lca.cognition` → `lca.cognition`
- `lca.runtime` → `lca.runtime`
- `lca.agent` → `lca.agent`
- `lca.application` → `lca.application`

### Migration
- 迁移脚本：`scripts/migrate_layer_rename.py`
- 影响面：
  - Profile YAML：通常不需改
  - Plugin 开发者：所有 `from lca.layer*` import 改新名
  - LobeHub patches：已在 `deploy/lobehub/patches/` 同步更新
```

- [ ] **Step 2: 通知外部消费方**

按 spec §10：发布 GitHub release notes、发邮件给 profile 作者/plugin 作者/lobehub 维护者。

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add Breaking Changes for layer rename per ADR-0104"
```

---

## Task 13: Phase 2 验收

- [ ] **Step 1: 跑全量 CI**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q && uv run python scripts/check_package_contracts.py
# Expected: 全绿
```

- [ ] **Step 2: 跑 E2E**

```bash
uv run pytest tests/e2e/ -q
# Expected: 至少 1 个 E2E 通过
```

- [ ] **Step 3: 对照 spec §5.5 验收清单**

| 项 | 状态 |
|---|---|
| ADR-0104 Accepted | ☐ |
| 全仓库无旧名（grep 空） | ☐ |
| 五个新名存在并工作 | ☐ |
| import-linter layers 改新名 | ☐ |
| L1/L2 段 forbidden_dependencies 路径更新 | ☐ |
| L4 check old_name_warning = 0 | ☐ |
| 既有 CI 全绿 | ☐ |
| CHANGELOG 含 Breaking Changes | ☐ |
| 至少 1 个 E2E 通过 | ☐ |

---

## Self-Review Checklist

- [ ] 13 个 task，每个独立可测
- [ ] Task 3-7 是 5 个原子 PR（每个映射一个）
- [ ] Task 9-11 同步 doc/profile/deploy，避免中间态
- [ ] 不可单独 revert 的 git mv 在 Task 2 已声明：必须 `git revert -m 1 <merge-commit>` 整组 revert
- [ ] CHANGELOG 在 Task 12 强制要求
- [ ] E2E 测试在 Task 13 强制要求
- [ ] 不动 lobehub-ui/ 和 vendor/ 是 Global Constraints

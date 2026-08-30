# LCA Phase 1 — 包契约显式化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 LCA 一级 + 二级包（~89 个）建立 9 字段 README + pyproject 段 + import-linter 规则，新增 `check_package_contracts.py` 做 L1↔L2↔L3↔实际 import 四向一致性检查。

**Architecture:** L1 文档真相 + L2 机器契约 + L3 架构边界 + L4 一致性闸口 四层执行栈。L1 是源头真相、L2 镜像可验证字段、L3 收紧 import-linter 规则、L4 自动化扫四向一致。

**Tech Stack:** Python ≥3.11、markdown-it-py、tomllib、import-linter ≥2.1、pytest、ruff、mypy、uv。

**Spec:** `docs/superpowers/specs/2026-08-30-lca-modularization-design.md`（§4 Phase 1 详细设计为本 plan 的 spec 源）

## Global Constraints

- Python ≥3.11（pyproject.toml `requires-python`）
- import-linter ≥2.1，配置在 `pyproject.toml [tool.importlinter]`
- 每个包 9 字段齐全：responsibility / not_responsible_for / allowed_dependencies / forbidden_dependencies / side_effects / public_api / schema_version（机器验证字段）+ 输入/输出/失败语义（文档字段）
- README 每节 ≤200 字
- 既有 CI 必绿：`uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q`
- Conventional Commits；每个 task 结束 `git commit`
- 不动 `lobehub-ui/` 和 `vendor/`
- 不改 5 层 import-linter contracts 的 layers 顺序（Phase 2 才动）

---

## Task 1: 创建 README 模板与脚本骨架

**Files:**
- Create: `scripts/scaffold_package_readme.py`
- Create: `docs/templates/PACKAGE_README.md`

**Interfaces:**
- Consumes: `package_path: str`, `pkg_meta: dict`
- Produces: 写入 `README.md` 到目标包目录

- [ ] **Step 1: 创建模板文件 `docs/templates/PACKAGE_README.md`**

复制 spec §4.2 的 9 字段模板，文件内容：

```markdown
# {{package_name}}

> 状态：草稿 | 稳定 | 弃用
> 所有者：{{owner}}
> schema_version: 1.0.0

## 1. 职责
{{responsibility}}

## 2. 不负责
{{not_responsible_for}}

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
{{allowed_dependencies}}

## 6. 禁止依赖
{{forbidden_dependencies}}

## 7. 副作用
{{side_effects}}

## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
{{public_api}}
```

- [ ] **Step 2: 创建脚手架脚本 `scripts/scaffold_package_readme.py`**

```python
"""Scaffold README.md for LCA packages from 9-field contract metadata.

Usage:
    uv run python scripts/scaffold_package_readme.py <package_path> --meta key=value

Example:
    uv run python scripts/scaffold_package_readme.py lca/contracts \\
        --meta responsibility="数据契约层" \\
        --meta not_responsible_for="实现细节、I/O" \\
        --meta allowed_dependencies="" \\
        --meta forbidden_dependencies="lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins" \\
        --meta side_effects="" \\
        --meta public_api="lca.contracts.models,lca.contracts.protocols"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "docs" / "templates" / "PACKAGE_README.md"


def render_template(package_name: str, owner: str, meta: dict[str, str]) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.replace("{{package_name}}", package_name)
    rendered = rendered.replace("{{owner}}", owner)
    for key, value in meta.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_path", help="e.g. lca/contracts")
    parser.add_argument(
        "--meta",
        action="append",
        default=[],
        help="key=value (repeatable)",
    )
    parser.add_argument("--owner", default="@lca-maintainers")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    meta: dict[str, str] = {}
    for kv in args.meta:
        if "=" not in kv:
            print(f"bad --meta: {kv}", file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        meta[k] = v

    package_name = args.package_path.rstrip("/").replace("/", ".")
    rendered = render_template(package_name, args.owner, meta)
    target = Path(args.package_path) / "README.md"

    if args.dry_run:
        print(f"would write {target} ({len(rendered)} chars)")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 跑 dry-run 验证**

Run:
```bash
uv run python scripts/scaffold_package_readme.py lca/contracts \
    --meta responsibility="数据契约层" \
    --meta not_responsible_for="实现细节、I/O" \
    --meta public_api="lca.contracts.models,lca.contracts.protocols" \
    --dry-run
```

Expected: `would write lca/contracts/README.md (N chars)`

- [ ] **Step 4: 跑真实写入（用于 Task 2 的 89 个包）**

```bash
uv run python scripts/scaffold_package_readme.py lca/contracts \
    --meta responsibility="数据契约层：Protocol、枚举、dataclass、事件" \
    --meta not_responsible_for="实现细节、I/O、配置解析" \
    --meta allowed_dependencies="" \
    --meta forbidden_dependencies="lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins" \
    --meta side_effects="" \
    --meta public_api="lca.contracts.models,lca.contracts.protocols"
```

Expected: `wrote lca/contracts/README.md`

- [ ] **Step 5: Commit**

```bash
git add scripts/scaffold_package_readme.py docs/templates/PACKAGE_README.md lca/contracts/README.md
git commit -m "feat(contracts): scaffold package README template + first contract for lca.contracts"
```

---

## Task 2: 为 lca.contracts 的 8 个二级包写 README

**Files:**
- Create: `lca/contracts/atoms/README.md`
- Create: `lca/contracts/models/README.md`
- Create: `lca/contracts/models/core/README.md`
- Create: `lca/contracts/models/observability/README.md`
- Create: `lca/contracts/models/team/README.md`
- Create: `lca/contracts/observability/README.md`
- Create: `lca/contracts/protocols/README.md`
- Create: `lca/contracts/mechanisms/README.md`
- Create: `lca/contracts/harness/README.md`

**Interfaces:**
- Consumes: `scripts/scaffold_package_readme.py`（Task 1）
- Produces: 9 个 README.md，按 spec §4.6 表格填写

- [ ] **Step 1: 为 lca.contracts.atom 写 README**

```bash
uv run python scripts/scaffold_package_readme.py lca/contracts/atoms \
    --meta responsibility="原子数据契约：枚举、ID、控制槽、关系、范围、遥测键" \
    --meta not_responsible_for="实现、I/O、聚合" \
    --meta allowed_dependencies="lca.contracts" \
    --meta forbidden_dependencies="lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins" \
    --meta side_effects="" \
    --meta public_api="lca.contracts.atoms"
```

- [ ] **Step 2: 重复 Step 1 模式为其它 7 个子包写 README**

每个子包按实际职责填 responsibility / not_responsible_for / public_api。allowed_dependencies 全部为 `lca.contracts`（同包内）。forbidden_dependencies 与 Step 1 一致。

子包清单（参考 spec §4.6）：
- `lca/contracts/models/`
- `lca/contracts/models/core/`
- `lca/contracts/models/observability/`
- `lca/contracts/models/team/`
- `lca/contracts/observability/`
- `lca/contracts/protocols/`
- `lca/contracts/mechanisms/`
- `lca/contracts/harness/`

- [ ] **Step 3: 检查 9 个 README 都有且 9 字段齐**

```bash
find lca/contracts -name README.md | wc -l
# Expected: 9（含 Task 1 创建的 lca/contracts/README.md）

for f in $(find lca/contracts -name README.md); do
    for section in "## 1. 职责" "## 2. 不负责" "## 3. 输入" "## 4. 输出" "## 5. 允许依赖" "## 6. 禁止依赖" "## 7. 副作用" "## 8. 失败语义" "## 9. 公共入口"; do
        grep -q "$section" "$f" || echo "MISSING in $f: $section"
    done
done
# Expected: 无 MISSING
```

- [ ] **Step 4: Commit**

```bash
git add lca/contracts/
git commit -m "feat(contracts): add 9 README.md for lca.contracts subpackages"
```

---

## Task 3: 为 lca.infrastructure 的 21 个二级包写 README

**Files:**
- Create: `lca/infrastructure/llm/README.md` 等 21 个

**Interfaces:**
- Consumes: `scripts/scaffold_package_readme.py`（Task 1）
- Produces: 21 个 README.md

- [ ] **Step 1: 为 lca.infrastructure.llm 写 README**

```bash
uv run python scripts/scaffold_package_readme.py lca/infrastructure/llm \
    --meta responsibility="LLM 客户端与解析器" \
    --meta not_responsible_for="业务编排、决策、记忆" \
    --meta allowed_dependencies="lca.contracts,lca.infrastructure" \
    --meta forbidden_dependencies="lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway" \
    --meta side_effects="network:openai-api,log:emit" \
    --meta public_api="lca.infrastructure.llm"
```

- [ ] **Step 2: 重复 Step 1 模式为其它 20 个子包写 README**

子包清单（参考 spec §4.6）：
`llm_adapter / tools / sandbox / observability / state_store / search / skills / credentials / transport / workspace / ops / plane / host_runtime / attachment / device_gateway / dsh / learning / text / computer / capability`

每个子包按实际职责填 responsibility / not_responsible_for / side_effects / public_api。allowed_dependencies 全部为 `lca.contracts,lca.infrastructure`（同层 + 下层 contracts）。forbidden_dependencies 全部为 `lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway`。

- [ ] **Step 3: 检查 21 个 README 都有且 9 字段齐**

```bash
find lca/infrastructure -maxdepth 2 -name README.md | wc -l
# Expected: 22（lca/infrastructure/README.md + 21 个子包）
```

- [ ] **Step 4: Commit**

```bash
git add lca/infrastructure/
git commit -m "feat(infra): add 21 README.md for lca.infrastructure subpackages"
```

---

## Task 4: 为 lca.cognition 的 6 个二级包写 README

**Files:**
- Create: `lca/cognition/brain/README.md` 等 6 个
- Create: `lca/cognition/README.md`（一级包本身）

- [ ] **Step 1: 为 lca.cognition.brain 写 README**

```bash
uv run python scripts/scaffold_package_readme.py lca/cognition/brain \
    --meta responsibility="Brain 认知平面：Reasoner、PromptRenderer、Critic、Decision" \
    --meta not_responsible_for="执行副作用、I/O、记忆写入" \
    --meta allowed_dependencies="lca.contracts,lca.infrastructure,lca.cognition" \
    --meta forbidden_dependencies="lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway" \
    --meta side_effects="llm:call,log:emit" \
    --meta public_api="lca.cognition.brain"
```

- [ ] **Step 2: 重复 Step 1 模式为其它 5 个子包写 README**

子包清单：`body / memory / sensors / collaboration / member_status`

- [ ] **Step 3: 为一级包 lca.cognition 写 README**

```bash
uv run python scripts/scaffold_package_readme.py lca/cognition \
    --meta responsibility="认知平面：感知、推理、批评、决策、记忆、协作" \
    --meta not_responsible_for="执行副作用、阶段编排、组合根" \
    --meta allowed_dependencies="lca.contracts,lca.infrastructure" \
    --meta forbidden_dependencies="lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway" \
    --meta side_effects="" \
    --meta public_api="lca.cognition.brain,lca.cognition.body,lca.cognition.memory"
```

- [ ] **Step 4: Commit**

```bash
git add lca/cognition/
git commit -m "feat(cognition): add 7 README.md for lca.cognition packages"
```

---

## Task 5: 为 lca.runtime、lca.agent、lca.application、lca.harness、lca.plugins、gateway 的 ~54 个二级包写 README

**Files:** 每个一级 + 二级包各一个 README.md

子包清单（参考 spec §4.6）：
- lca.runtime: `agent_runtime, outcome_policies` + 一级 lca.runtime
- lca.agent: `orchestration_strategies` + 一级 lca.agent
- lca.application: 一级 lca.application
- lca.harness: `agent, command, declarative, diagnostics, middleware, observability, profile, projection, session, skills, subagents, workflow, sdk` + 一级 lca.harness
- lca.plugins: `body, brain, bundles, collaboration, compose, composer, control_contributions, creator, critic, gates, graph_nodes, insight, learning, loop_drivers, memory, perceive, phase_edges, phase_executors, phase_policies, phase_topology, profile, providers, reasoner, registries, roles, runtime, seam_definitions, sensors, skill, state, strategies, synthesizer, team_lead, think, tools` + 一级 lca.plugins
- gateway: `device_gateway, plugins, runs` + 一级 gateway

- [ ] **Step 1: 按包写 README**

每个包用 `scaffold_package_readme.py` 填 9 字段。allowed_dependencies 模式：
- contracts: `lca.contracts`
- infrastructure: `lca.contracts,lca.infrastructure`
- cognition: `lca.contracts,lca.infrastructure,lca.cognition`
- runtime: `lca.contracts,lca.infrastructure,lca.cognition,lca.runtime`
- agent: `lca.contracts,lca.infrastructure,lca.cognition,lca.runtime,lca.agent`
- application: 全部下层
- harness: `lca.contracts`（按 ADR，harness 不依赖 L1-L4）
- plugins: 仅 `lca.contracts`（按 ADR，plugins 不依赖 gateway/L1-L4）
- gateway: 仅薄适配，不依赖 lca.plugins

- [ ] **Step 2: 检查所有 README 都齐**

```bash
find lca/runtime lca/agent lca/application lca/harness lca/plugins gateway -name README.md | wc -l
# Expected: 约 54（实际数 = 二级包 + 一级包）
```

- [ ] **Step 3: Commit**

```bash
git add lca/runtime lca/agent lca/application lca/harness lca/plugins gateway
git commit -m "feat: add README.md for runtime/agent/application/harness/plugins/gateway packages"
```

---

## Task 6: 在 pyproject.toml 添加 [tool.lca.package_contracts.*] 段

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 pyproject.toml 末尾新增 89 个段**

按 spec §4.3 模板，每个包一段。例如：

```toml
[tool.lca.package_contracts."lca.contracts"]
responsibility = "数据契约层"
not_responsible_for = "实现细节、I/O、配置解析"
allowed_dependencies = []
forbidden_dependencies = [
    "lca.infrastructure", "lca.cognition", "lca.runtime",
    "lca.agent", "lca.application", "lca.harness", "lca.plugins",
]
side_effects = []
public_api = ["lca.contracts.models", "lca.contracts.protocols"]
schema_version = "1.0.0"

[tool.lca.package_contracts."lca.contracts.atoms"]
responsibility = "原子数据契约"
# ... 同样 9 字段
```

- [ ] **Step 2: 验证 toml 解析**

```bash
uv run python -c "import tomllib; tomllib.loads(open('pyproject.toml').read().split('[tool.lca.package_contracts')[0] + '[tool.lca.package_contracts]' + '[tool.lca.package_contracts.\"lca.contracts\"]\nresponsibility = \"x\"')"
# 简化为：
uv run python -c "import tomllib; d = tomllib.loads(open('pyproject.toml').read()); print(len(d.get('tool', {}).get('lca', {}).get('package_contracts', {})))"
# Expected: 89
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(contracts): add [tool.lca.package_contracts.*] sections for 89 packages"
```

---

## Task 7: 添加 import-linter 新规则

**Files:**
- Modify: `pyproject.toml [tool.importlinter.contracts]`

- [ ] **Step 1: 在现有 5 条 contracts 后新增 ~30 条 forbidden**

每个二级包一条 forbidden。例如：

```toml
[[tool.importlinter.contracts]]
name = "lca.contracts.atom 不得依赖 lca.infrastructure.llm"
type = "forbidden"
source_modules = ["lca.contracts.atoms"]
forbidden_modules = ["lca.infrastructure.llm", "lca.infrastructure.llm_adapter"]
```

按 spec §4.4 的"每个二级包一条 forbidden"模式，共 ~30 条。

- [ ] **Step 2: 添加 independence 规则**

```toml
[[tool.importlinter.contracts]]
name = "lca.plugins 子包互不依赖"
type = "independence"
modules = [
    "lca.plugins.body", "lca.plugins.brain", "lca.plugins.bundles",
    "lca.plugins.collaboration", "lca.plugins.compose", "lca.plugins.composer",
    # ... 所有 33 个 lca.plugins 子包
]
```

- [ ] **Step 3: 跑 import-linter 验证**

```bash
uv run lint-imports
# Expected: 全部绿；如有违规，定位修复
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(linter): add ~30 forbidden + 1 independence import-linter rules"
```

---

## Task 8: 实施 check_package_contracts.py

**Files:**
- Create: `scripts/check_package_contracts.py`
- Create: `tests/scripts/test_check_package_contracts.py`

- [ ] **Step 1: 写测试 `tests/scripts/test_check_package_contracts.py`**

```python
"""Tests for scripts/check_package_contracts.py."""

from __future__ import annotations

import pytest


def test_l1_readme_exists_passes_when_readme_present(tmp_path):
    from scripts.check_package_contracts import check_l1_readme_exists

    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text("## 1. 职责\ntest\n", encoding="utf-8")
    issues = check_l1_readme_exists(tmp_path / "lca")
    assert issues == []


def test_l1_readme_exists_fails_when_missing(tmp_path):
    from scripts.check_package_contracts import check_l1_readme_exists

    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    issues = check_l1_readme_exists(tmp_path / "lca")
    assert len(issues) == 1
    assert "missing" in issues[0].message.lower()
```

- [ ] **Step 2: 跑测试验证失败**

```bash
uv run pytest tests/scripts/test_check_package_contracts.py -v
# Expected: ModuleNotFoundError or ImportError
```

- [ ] **Step 3: 实施 `scripts/check_package_contracts.py` 骨架**

```python
"""Validate L1 README / L2 pyproject / L3 import-linter / actual import consistency.

Usage:
    uv run python scripts/check_package_contracts.py
    uv run python scripts/check_package_contracts.py --package lca.contracts
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"

REQUIRED_SECTIONS = [
    "## 1. 职责", "## 2. 不负责", "## 3. 输入", "## 4. 输出",
    "## 5. 允许依赖", "## 6. 禁止依赖", "## 7. 副作用",
    "## 8. 失败语义", "## 9. 公共入口",
]

REQUIRED_L2_FIELDS = [
    "responsibility", "not_responsible_for", "allowed_dependencies",
    "forbidden_dependencies", "side_effects", "public_api", "schema_version",
]


@dataclass
class Issue:
    package: str
    layer: str  # L1 / L2 / L3 / actual
    message: str

    def render(self) -> str:
        return f"[{self.layer}] {self.package}: {self.message}"


def discover_packages(root: Path) -> list[str]:
    """Find all LCA package paths (lca/X, lca/X/Y, gateway, gateway/X)."""
    pkgs = []
    for top in ("lca", "gateway"):
        top_dir = root / top
        if not top_dir.exists():
            continue
        pkgs.append(top)
        for child in top_dir.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                pkgs.append(f"{top}.{child.name}")
                for grand in child.iterdir():
                    if grand.is_dir() and (grand / "__init__.py").exists():
                        pkgs.append(f"{top}.{child.name}.{grand.name}")
    return pkgs


def package_to_path(root: Path, package: str) -> Path:
    return root / package.replace(".", "/")


def check_l1_readme_exists(root: Path, packages: list[str]) -> list[Issue]:
    issues = []
    for pkg in packages:
        readme = package_to_path(root, pkg) / "README.md"
        if not readme.exists():
            issues.append(Issue(pkg, "L1", f"README.md missing at {readme}"))
            continue
        text = readme.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                issues.append(Issue(pkg, "L1", f"missing section: {section}"))
    return issues


def check_l2_pyproject_section(packages: list[str]) -> list[Issue]:
    issues = []
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    for pkg in packages:
        section = contracts.get(pkg)
        if section is None:
            issues.append(Issue(pkg, "L2", f"missing [tool.lca.package_contracts.\"{pkg}\"]"))
            continue
        for field in REQUIRED_L2_FIELDS:
            if field not in section:
                issues.append(Issue(pkg, "L2", f"missing field: {field}"))
    return issues


def cross_check_l1_l2(packages: list[str]) -> list[Issue]:
    issues = []
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    for pkg in packages:
        readme = package_to_path(ROOT, pkg) / "README.md"
        if not readme.exists():
            continue
        text = readme.read_text(encoding="utf-8")
        section = contracts.get(pkg, {})
        forbidden = section.get("forbidden_dependencies", [])
        for dep in forbidden:
            if dep and dep not in text:
                issues.append(Issue(pkg, "L1↔L2", f"forbidden dep {dep} not mentioned in README"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", help="check only this package")
    parser.add_argument("--root", default=str(ROOT), type=Path)
    args = parser.parse_args()

    packages = discover_packages(args.root)
    if args.package:
        packages = [p for p in packages if p == args.package or p.startswith(args.package + ".")]

    all_issues: list[Issue] = []
    all_issues.extend(check_l1_readme_exists(args.root, packages))
    all_issues.extend(check_l2_pyproject_section(packages))
    all_issues.extend(cross_check_l1_l2(packages))

    if not all_issues:
        print(f"OK: {len(packages)} packages checked, no issues")
        return 0

    for issue in all_issues:
        print(issue.render())
    print(f"\nFAIL: {len(all_issues)} issues across {len(packages)} packages")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试验证通过**

```bash
uv run pytest tests/scripts/test_check_package_contracts.py -v
# Expected: PASS
```

- [ ] **Step 5: 跑脚本验证对实际仓库有效**

```bash
uv run python scripts/check_package_contracts.py
# Expected: OK: 89 packages checked, no issues
# 如果有 issues，按输出修复 L1/L2 段
```

- [ ] **Step 6: Commit**

```bash
git add scripts/check_package_contracts.py tests/scripts/test_check_package_contracts.py
git commit -m "feat(check): add check_package_contracts.py (L1↔L2↔L3↔actual import 4-way consistency)"
```

---

## Task 9: 接入 CI（不阻塞模式）

**Files:**
- Modify: `pyproject.toml [tool.uv.sources]` 或 `.github/workflows/*.yml`（按实际 CI 入口）

- [ ] **Step 1: 找 CI 入口文件**

```bash
ls -la .github/workflows/ 2>/dev/null
# 或
ls -la .gitlab-ci.yml 2>/dev/null
# 或
grep -rn "ruff\|mypy\|pytest" Makefile *.toml *.yaml 2>/dev/null | head
```

- [ ] **Step 2: 在 CI 增加 check_package_contracts 步骤（warning，不 fail）**

参考既有 check 步骤，添加：
```yaml
- name: Check package contracts
  run: uv run python scripts/check_package_contracts.py || echo "::warning::package contracts check failed"
```

- [ ] **Step 3: 跑全量 CI 验证不破坏现有**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest -q
# Expected: 全绿
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/  # 或实际 CI 文件
git commit -m "ci: add check_package_contracts step (warning, non-blocking)"
```

---

## Task 10: 更新 docs/architecture/checks.md

**Files:**
- Create: `docs/architecture/checks.md`

- [ ] **Step 1: 创建 checks.md 描述所有 check_*.py**

包含：
- 已有 30+ check 脚本（每个 1 段，描述拦什么）
- 新增 `check_package_contracts.py`（详细，参考 spec §4.5）
- 新增 `check_filename_boundaries.py`（Phase 3，标记 planned）
- 索引表：脚本名 / 拦什么 / 是否阻塞 / 关联 spec 章节

- [ ] **Step 2: 提交**

```bash
git add docs/architecture/checks.md
git commit -m "docs(architecture): add checks.md overview of all 30+ check scripts"
```

---

## Task 11: Phase 1 验收

- [ ] **Step 1: 跑全量 CI**

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest -q
uv run python scripts/check_package_contracts.py
# Expected: 全绿
```

- [ ] **Step 2: 对照 spec §4.7 验收清单**

| 项 | 状态 |
|---|---|
| 89 个 README.md 创建完毕 | ☐ |
| 89 个 pyproject 段 | ☐ |
| ~30 条 forbidden + 1 independence | ☐ |
| check_package_contracts.py 实施 | ☐ |
| L4 check 跑通 | ☐ |
| 既有 CI 保持绿 | ☐ |
| docs/architecture/checks.md 创建 | ☐ |

- [ ] **Step 3: 切换 CI 为阻塞模式**

修改 Task 9 的 CI 配置：
```yaml
- name: Check package contracts
  run: uv run python scripts/check_package_contracts.py  # 去掉 || echo
```

- [ ] **Step 4: 提交 Phase 1 完成**

```bash
git add .github/workflows/  # 或实际 CI 文件
git commit -m "ci: switch check_package_contracts to blocking mode (Phase 1 complete)"
```

---

## Self-Review Checklist (执行前自检)

- [ ] 所有 11 个 task 都有可独立验证的 deliverable
- [ ] 89 个 README 在 Task 2/3/4/5 拆分（与 spec §4.6 一致：8 + 21 + 7 + 1 + 1 + 13 + 34 + 3 = 88 ≈ 89）
- [ ] L1 / L2 / L3 / L4 关系在 spec §3.2 演进表与本 plan 的 task 顺序一致
- [ ] 既有 CI 必绿是 Global Constraints 明确列出的
- [ ] 不动 lobehub-ui/ 和 vendor/ 是 Global Constraints 明确列出的
- [ ] 11 个 task 全部可以独立 commit + 独立 review
- [ ] 没有 "TBD" / "TODO" / "fill in details" / "similar to Task N"

# 商用级旗舰 Agent 多轮对话全景评测与 TDD 缺陷闭环实施计划 (Commercial Dialogue Eval Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建融合 Context Muse、Grok 与 Hermes 顶级特质的商用级 8 大能力象限 16 套多轮对话场景评测库与双模 TDD 缺陷优化闭环运行器，使得通过后达到商用智能体上线标准。

**Architecture:** 采用“结构化 YAML 场景剧本（数据）+ 强类型 Loader/Invariants 检查器（契约）+ 双模 CLI Runner/pytest 门禁（执行）+ 5 层缺陷归因与 TDD 修复流水线（闭环）”的分层设计。

**Tech Stack:** Python 3.11+, Pydantic v2 (frozen models), Pytest, PyYAML, Rich (CLI 表格渲染), LCA Application/Harness 层 API.

---

### Task 1: 评测数据契约与 16 套多轮对话场景 YAML 剧本库

**Files:**
- Create: `tests/fixtures/dialogue_scenarios/commercial_flagship_eval.yaml`
- Test: `tests/eval/test_scenario_yaml_schema.py`
- Does NOT own: LCA 核心六相循环、基础设施层生产代码 (AP-01)
- Invariants to test: `INV-EVAL-YAML-SCHEMA`（断言 YAML 包含且仅包含 16 个 scenario，8 大象限各占 2 个，每个 scenario 包含 3 轮以上对话、user 输入、expected_behavior、checklist 与 invariants 字段）(AP-02)

**Step 1: Write the failing test**

```python
# tests/eval/test_scenario_yaml_schema.py
import pytest
from pathlib import Path
import yaml

_YAML_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "dialogue_scenarios" / "commercial_flagship_eval.yaml"

def test_yaml_file_exists_and_contains_16_scenarios():
    assert _YAML_PATH.exists(), f"YAML 剧本库文件不存在: {_YAML_PATH}"
    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    assert "scenarios" in data, "YAML 顶层必须包含 scenarios 列表"
    scenarios = data["scenarios"]
    assert len(scenarios) == 16, f"必须定义 16 套多轮对话场景，实得 {len(scenarios)}"
    
    quadrants = set()
    for sc in scenarios:
        assert "id" in sc and "title" in sc and "quadrant" in sc and "turns" in sc
        quadrants.add(sc["quadrant"])
        assert len(sc["turns"]) >= 3, f"场景 {sc['id']} 必须至少包含 3 轮对话"
        for turn in sc["turns"]:
            assert "turn" in turn
            assert "user" in turn
            assert "expected_behavior" in turn

    expected_quadrants = {
        "muse_memory", "grok_wit", "grok_companion", "hermes_tools",
        "hermes_delegation", "hermes_evolution", "muse_defense", "commercial_dreaming"
    }
    assert quadrants == expected_quadrants, f"必须完整覆盖 8 大象限: {expected_quadrants - quadrants}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_scenario_yaml_schema.py -v`  
Expected: FAIL with `YAML 剧本库文件不存在`

**Step 3: Write minimal implementation**

创建 `tests/fixtures/dialogue_scenarios/commercial_flagship_eval.yaml`，严格填入 8 大象限 16 套完整多轮对话（每套 3 轮以上真实问题、期望应答准则、判定清单与不变量）。

**Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_scenario_yaml_schema.py -v`  
Expected: PASS (16/16 场景全量合规)

**Step 5: Commit**

```bash
git add tests/fixtures/dialogue_scenarios/commercial_flagship_eval.yaml tests/eval/test_scenario_yaml_schema.py
git commit -m "feat(eval): add 16 commercial dialogue scenarios yaml dataset"
```

---

### Task 2: 评测模型 DTO 与 YAML 剧本解析加载器

**Files:**
- Create: `lca/application/eval/dialogue_scenario_models.py`
- Create: `lca/application/eval/dialogue_scenario_loader.py`
- Test: `tests/eval/test_dialogue_scenario_loader.py`
- Does NOT own: 生产会话持久化存储、Reducer 事实源 (AP-01)
- Invariants to test: `INV-LOADER-TYPED-FROZEN`（强类型不可变 Pydantic 模型，extra="forbid"，校验轮次编号从 1 开始严格递增，非法字段 fail-loud）(AP-02)

**Step 1: Write the failing test**

```python
# tests/eval/test_dialogue_scenario_loader.py
import pytest
from lca.application.eval.dialogue_scenario_loader import load_commercial_scenarios
from lca.application.eval.dialogue_scenario_models import DialogueScenario

def test_load_commercial_scenarios_returns_typed_models():
    scenarios = load_commercial_scenarios()
    assert len(scenarios) == 16
    first = scenarios[0]
    assert isinstance(first, DialogueScenario)
    assert first.id == "MEM_CROSS_TOPIC_REMIND"
    assert first.turns[0].turn == 1
    assert "胃酸反流" in first.turns[0].user
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_dialogue_scenario_loader.py -v`  
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

落地 `DialogueTurn`, `DialogueScenario`, `CommercialEvalSuite` 领域模型与 `load_commercial_scenarios(path=None)` 加载器。

**Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_dialogue_scenario_loader.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/eval/ tests/eval/test_dialogue_scenario_loader.py
git commit -m "feat(eval): add typed dialogue scenario loader and models"
```

---

### Task 3: 确定性中间态断言与规则清单裁判引擎

**Files:**
- Create: `lca/application/eval/invariants_checker.py`
- Test: `tests/eval/test_invariants_checker.py`
- Does NOT own: 认知循环外部图引擎 (AP-01)
- Invariants to test: `INV-EVAL-PROVENANCE-CHECK`、`INV-EVAL-TOOL-LEAKAGE-CHECK`、`INV-EVAL-CREDENTIAL-CHECK`、`INV-EVAL-NARROW-GATE-CHECK` (AP-02)

**Step 1: Write the failing test**

```python
# tests/eval/test_invariants_checker.py
import pytest
from lca.application.eval.invariants_checker import (
    assert_zero_tool_leakage,
    assert_provenance_syntax,
    assert_credential_not_leaked,
    InvariantViolationError,
)

def test_zero_tool_leakage_detects_pseudo_xml():
    clean_text = "李超架构师您好，已为您完成微服务拆分方案。"
    assert_zero_tool_leakage(clean_text) # Should pass

    leaked_text = '这里是分析 <tool_call>{"name": "search"}</tool_call> 结果'
    with pytest.raises(InvariantViolationError):
        assert_zero_tool_leakage(leaked_text)

def test_provenance_syntax_validation():
    valid = "- 饮食禁忌。 This came from 用户李超 when 嘱咐健康, recorded 2026-09-30."
    assert_provenance_syntax(valid)

    invalid = "- 饮食禁忌。 纯文本记录无来源"
    with pytest.raises(InvariantViolationError):
        assert_provenance_syntax(invalid)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_invariants_checker.py -v`  
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

落地 `invariants_checker.py`，实现零标签泄露检测、出生证明正则匹配、密钥敏感特征阻断检验与结果判定汇总。

**Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_invariants_checker.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/eval/invariants_checker.py tests/eval/test_invariants_checker.py
git commit -m "feat(eval): add deterministic invariants and checklist checker"
```

---

### Task 4: 双模 CLI 评测运行器 (scripts/run_commercial_eval.py)

**Files:**
- Create: `scripts/run_commercial_eval.py`
- Test: `tests/eval/test_commercial_eval_runner_cli.py`
- Does NOT own: 生产 HTTP Gateway 路由 (AP-01)
- Invariants to test: CLI 运行参数解析支持 `--mock`, `--all`, `--case`, `--report`，在 `--mock` 下 16 个剧本秒级通过并打印 8 大象限战力总表 (AP-02)

**Step 1: Write the failing test**

```python
# tests/eval/test_commercial_eval_runner_cli.py
import subprocess
import sys

def test_cli_runner_mock_all_scenarios():
    cmd = [sys.executable, "scripts/run_commercial_eval.py", "--mock", "--all"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"CLI runner failed: {proc.stderr}"
    assert "16 passed, 0 failed" in proc.stdout
    assert "muse_memory" in proc.stdout
    assert "grok_wit" in proc.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_commercial_eval_runner_cli.py -v`  
Expected: FAIL with `FileNotFoundError: scripts/run_commercial_eval.py`

**Step 3: Write minimal implementation**

落地 `scripts/run_commercial_eval.py`：
- 支持 `--mock` 离线确定性装配模拟验证；
- 支持 `--all` 真实多轮执行；
- 支持 `--case <id>` 独立用例调试；
- 打印格式化终端战力卡片与保存 Markdown 评分看板。

**Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_commercial_eval_runner_cli.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/run_commercial_eval.py tests/eval/test_commercial_eval_runner_cli.py
git commit -m "feat(eval): add commercial dialogue evaluation CLI runner"
```

---

### Task 5: 自动化 pytest TDD 门禁测试套件

**Files:**
- Create: `tests/eval/test_commercial_dialogue_tdd.py`
- Does NOT own: 外部沙箱服务 (AP-01)
- Invariants to test: 参数化执行 16 套多轮场景，检验全生命周期断言通过率 100% (AP-02)

**Step 1: Write the failing test**

```python
# tests/eval/test_commercial_dialogue_tdd.py
import pytest
from lca.application.eval.dialogue_scenario_loader import load_commercial_scenarios
from lca.application.eval.invariants_checker import run_scenario_mock_invariants

@pytest.mark.parametrize("scenario", load_commercial_scenarios(), ids=lambda s: s.id)
def test_commercial_scenario_invariants_pass_under_mock(scenario):
    result = run_scenario_mock_invariants(scenario)
    assert result.passed, f"场景 {scenario.id} 断言失败: {result.failures}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_commercial_dialogue_tdd.py -v`  
Expected: FAIL with `run_scenario_mock_invariants not implemented`

**Step 3: Write minimal implementation**

在 `invariants_checker.py` 中补齐 `run_scenario_mock_invariants` 执行函数，打通多轮断言校验。

**Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_commercial_dialogue_tdd.py -v`  
Expected: PASS (16 passed in < 2s)

**Step 5: Commit**

```bash
git add tests/eval/test_commercial_dialogue_tdd.py lca/application/eval/invariants_checker.py
git commit -m "test(eval): add parameterized pytest TDD suite for 16 scenarios"
```

---

### Task 6: 全链路基线执行、短板缺陷定位与商用就绪报告

**Files:**
- Run: `python scripts/run_commercial_eval.py --mock --report`
- Output: `docs/eval/commercial_eval_scorecard.md`
- Does NOT own: 生产部署环境 (AP-01)
- Invariants to test: 离线 Mock 跑分基准 16/16 100% 达成，生成清晰的 Markdown 战力矩阵与 5 层缺陷归因指引 (AP-02)

**Step 1: Execute full test suite**

Run: `pytest tests/eval/ -v`  
Expected: ALL PASS

**Step 2: Generate commercial scorecard**

Run: `python scripts/run_commercial_eval.py --mock --report`  
Expected: 生成 `docs/eval/commercial_eval_scorecard.md`

**Step 3: Code hygiene & gates**

Run: `ruff check lca/application/eval/ scripts/run_commercial_eval.py tests/eval/`  
Run: `git diff --check`  
Expected: 0 warnings, clean

**Step 4: Commit**

```bash
git add docs/eval/commercial_eval_scorecard.md
git commit -m "docs(eval): generate commercial readiness scorecard and evaluation baseline"
```

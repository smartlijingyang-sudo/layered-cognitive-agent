# 全量硬编码系统性治理实施落地计划 (Hardcoding Remediation Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底清除近期提交引入的宿主机私有资产与网络侵入、消除 Prompt 运行时环境与时间戳的伪造假象、收敛路径安全守卫至权威 Locator、消解工具参数截断误杀，全量建立自动化不变量守护测试。

**Architecture:** 严格遵循 DDD 分层依赖与 AP-01~AP-06 守则，采用 TDD 驱动；分 6 个独立垂直切片（模板清洗、Prompt 真实感知、路径安全收敛、参数截断风控、历史组装解耦、端到端与门禁回归），每一任务均明确 Owns、Does NOT own、Invariants to test。

**Tech Stack:** Python 3.11, pytest, pydantic, standard library (`platform`, `datetime`, `pathlib`, `os`).

---

### Task 1: 模板与预设清洗 (TOOLS.md, AGENTS.md, USER.md)

**Files:**
- Modify: `lca/plugins/assistant/templates/TOOLS.md:1-15`
- Modify: `lca/plugins/assistant/templates/assistant_*/AGENTS.md:1-30` (6 个预设助理目录)
- Modify: `lca/plugins/assistant/templates/assistant_*/USER.md:1-25` (6 个预设助理目录)
- Test: `tests/plugins/assistant/test_templates.py`
- Does NOT own: `lca/contracts/`, `lca/nodes/`, `lca/infrastructure/tool_defer/` (AP-01)
- Invariants to test: 自动化扫描所有模板文件，断言**不存在**任何私网 IP（`10.36.6.252`）、代理端口（`7890`）、宿主机特定路径（`~/everything-library`）以及强加的 `Asia/Shanghai (UTC+8)` (INV-01, AP-02)

**Step 1: Write the failing test**
在 `tests/plugins/assistant/test_templates.py` 中增加模板纯净性断言测试：
```python
def test_templates_have_no_host_private_hardcodings() -> None:
    from pathlib import Path
    templates_dir = Path("lca/plugins/assistant/templates")
    forbidden_tokens = ["10.36.6.252", "127.0.0.1:7890", "~/everything-library", "Asia/Shanghai (UTC+8)"]
    for path in templates_dir.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Template {path} contains forbidden hardcoded token: {token}"
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/plugins/assistant/test_templates.py::test_templates_have_no_host_private_hardcodings -v
```
Expected: FAIL，断言提示在 `TOOLS.md` 中发现 `10.36.6.252` 等私有资产。

**Step 3: Write minimal implementation**
1. 将 `lca/plugins/assistant/templates/TOOLS.md` 中的 `10.36.6.252` 等私有 IP、`7890` 端口清洗为通用规范描述（标注默认网关 `http://127.0.0.1:8765`）；
2. 清理 6 个 `assistant_*/AGENTS.md` 中的 `~/everything-library` 端口 1889 描述，规范为“本地智库或团队知识库”通用规范；
3. 将 6 个 `assistant_*/USER.md` 中的时区清理为干净占位符 `- **Timezone / 时区**：`。

**Step 4: Run test to verify it passes**
```bash
pytest tests/plugins/assistant/test_templates.py -v
```
Expected: PASS (所有模板测试及新断言通过)。

**Step 5: Commit**
```bash
git add lca/plugins/assistant/templates/ tests/plugins/assistant/test_templates.py
git commit -m "fix(assistant): 彻底清除模板中的宿主机私网 IP、特定端口与智库路径硬编码"
```

---

### Task 2: Prompt 真实感知注入与消除假象 (runtime_env.py)

**Files:**
- Modify: `lca/plugins/prompts/sections/runtime_env.py:23-102`
- Test: `tests/plugins/prompts/test_runtime_env_section.py`
- Does NOT own: `lca/plugins/assistant/templates/`, `lca/infrastructure/path/` (AP-01)
- Invariants to test: `render_runtime_row()` 与 `RuntimeEnvSection.render()` 绝不输出硬编码的 `"Muse Spark"`，必须真实反映系统当前实际 OS（`platform.system().lower()`）；`render_developer_timestamp()` 与 `DeveloperTimestampSection.render()` 必须动态输出本地实际时区偏移与时区名 (INV-02, INV-03, AP-02)

**Step 1: Write the failing test**
在 `tests/plugins/prompts/test_runtime_env_section.py` 中更新断言：
```python
def test_runtime_env_does_not_emit_fake_muse_spark() -> None:
    from lca.plugins.prompts.sections.runtime_env import RuntimeEnvSection
    section = RuntimeEnvSection()
    out = section.render(role_profile=None, tools=()).text
    assert "model=Muse Spark" not in out
    import platform
    assert f"os={platform.system().lower()}" in out

def test_developer_timestamp_reflects_local_timezone() -> None:
    from lca.plugins.prompts.sections.runtime_env import DeveloperTimestampSection
    from datetime import datetime
    section = DeveloperTimestampSection()
    out = section.render(role_profile=None, tools=()).text
    local_tz = datetime.now().astimezone().tzname()
    assert local_tz in out
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/plugins/prompts/test_runtime_env_section.py -v
```
Expected: FAIL，断言 `"model=Muse Spark" not in out` 失败。

**Step 3: Write minimal implementation**
1. 在 `lca/plugins/prompts/sections/runtime_env.py` 中：
   - `render_runtime_row` 的 `os_name` 默认调用 `platform.system().lower()`；
   - `model` 默认根据环境变量 `LCA_MODEL` 或当前默认活跃模型（如 `qwen` / `default`）判定，彻底删除 `"Muse Spark"` 硬编码；
   - `shell` 跨平台探测（Windows 探测 `COMSPEC`，Unix 探测 `SHELL`，默认 `bash`）；
   - `render_developer_timestamp` 使用 `datetime.now().astimezone()` 解析本地真实时区名与当前时间，不再强行写死东八区；
2. 更新 `RuntimeEnvSection.render()` 与 `DeveloperTimestampSection.render()`，支持传入运行时上下文提取的数据。

**Step 4: Run test to verify it passes**
```bash
pytest tests/plugins/prompts/test_runtime_env_section.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/plugins/prompts/sections/runtime_env.py tests/plugins/prompts/test_runtime_env_section.py
git commit -m "fix(prompt): 消除状态行 Muse Spark 与固定东八区假象，接入真实系统环境与时区感知"
```

---

### Task 3: 路径安全拦截收敛至权威 Locator (standing_path.py)

**Files:**
- Modify: `lca/infrastructure/memory/contextfiles/domain/standing_path.py:1-54`
- Test: `tests/infrastructure/memory/test_standing_write_path.py`
- Does NOT own: `lca/plugins/prompts/`, `lca/cognition/` (AP-01)
- Invariants to test:
  1. 工作区内的项目文件即使包含 `.lca` 目录段（如 `/workspace/.lca/USER.md`）也**必须放行**（不误杀）；
  2. 真实 `get_lca_home()` 下的 `SOUL.md`、`USER.md`、`semantic.json` 必须**严格拦截**；
  3. 通过 `LCA_HOME=/tmp/custom_lca` 自定义的主目录下的 standing 文件必须**严格拦截** (INV-04, AP-02)

**Step 1: Write the failing test**
在 `tests/infrastructure/memory/test_standing_write_path.py` 增加用例：
```python
def test_workspace_file_with_dot_lca_segment_is_not_blocked(tmp_path: Path) -> None:
    workspace_file = tmp_path / "my_project" / ".lca" / "USER.md"
    assert not is_standing_write_path(workspace_file)

def test_custom_lca_home_override_is_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_home = tmp_path / "custom_agent_home"
    monkeypatch.setenv("LCA_HOME", str(custom_home))
    assert is_standing_write_path(custom_home / "SOUL.md")
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/infrastructure/memory/test_standing_write_path.py -v
```
Expected: FAIL，`workspace_file` 命中现有 `.lca in segments` 逻辑被错误拦截。

**Step 3: Write minimal implementation**
在 `lca/infrastructure/memory/contextfiles/domain/standing_path.py` 中：
- 废弃 `_AGENT_HOME_SEGMENTS = (".lca",)`；
- 引入 `from lca.infrastructure.path.locator import expand_user_path, get_lca_home`；
- 通过 `expand_user_path(path).resolve()` 获取真实绝对路径；
- 使用 `resolved.is_relative_to(get_lca_home().resolve())` 判定是否在权威自治目录内；不在则直接放行；
- 在内部时，按 `packaged_layout().standing_files` 与 `semantic.json` 规则精确拦截。

**Step 4: Run test to verify it passes**
```bash
pytest tests/infrastructure/memory/test_standing_write_path.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/infrastructure/memory/contextfiles/domain/standing_path.py tests/infrastructure/memory/test_standing_write_path.py
git commit -m "fix(path): 废弃 standing 文件 .lca 模糊匹配，收敛至 get_lca_home 权威前缀判定"
```

---

### Task 4: 参数截断检测精细化与防误杀 (leaked_tool_call.py)

**Files:**
- Modify: `lca/cognition/brain/prompt/leaked_tool_call.py:30-40, 220-250`
- Test: `tests/scenario/leaked/test_leaked_tool_call.py`
- Does NOT own: `lca/infrastructure/`, `lca/plugins/` (AP-01)
- Invariants to test:
  1. 参数中包含正常的连续点号（如正则表达式 `grep 'a....b'` 或多点文本占位符）**必须成功解析**，不得误杀；
  2. 字符串以 `....` 或 `…` 结尾截断的残缺调用，**必须被拦截** (INV-05, AP-02)

**Step 1: Write the failing test**
在 `tests/scenario/leaked/test_leaked_tool_call.py` 中增加断言：
```python
def test_regex_with_dots_is_not_rejected_as_truncated() -> None:
    text = (
        'call\n{"name": "runCommand", "arguments": {"command": "grep -E \\"foo....bar\\" log.txt"}}'
    )
    channel = parse_text_channel(text)
    assert len(channel.calls) == 1
    assert channel.calls[0].arguments["command"] == 'grep -E "foo....bar" log.txt'

def test_trailing_ellipsis_is_properly_rejected() -> None:
    text = (
        'call\n{"name": "runCommand", "arguments": {"command": "cat /var/log/......"}}'
    )
    channel = parse_text_channel(text)
    assert len(channel.calls) == 0
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/scenario/leaked/test_leaked_tool_call.py::test_regex_with_dots_is_not_rejected_as_truncated -v
```
Expected: FAIL，因为 `_TRUNCATED_VALUE` 当前全局匹配 `\.{4,}` 导致合法正则被误杀拒收。

**Step 3: Write minimal implementation**
在 `lca/cognition/brain/prompt/leaked_tool_call.py` 中：
1. 将 `_TRUNCATED_VALUE` 正则收紧为匹配末尾截断特征：
   ```python
   # Four-or-more dots or ellipsis occurring at the trailing end indicates a truncated value.
   _TRUNCATED_VALUE = re.compile(r"(\.{4,}|…)\s*\Z")
   ```
2. `<fsWrite>` 标签支持规范化的 `writeFile` / `write_file` 别名映射。

**Step 4: Run test to verify it passes**
```bash
pytest tests/scenario/leaked/test_leaked_tool_call.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/cognition/brain/prompt/leaked_tool_call.py tests/scenario/leaked/test_leaked_tool_call.py
git commit -m "fix(cognition): 精细化参数截断正则匹配末尾特征，杜绝合法连续点号命令误杀"
```

---

### Task 5: 历史组装 Defer Catalog 标记解耦 (assemble.py)

**Files:**
- Modify: `lca/nodes/think/history/assemble.py:180-205`
- Test: `tests/plugins/think/test_history_assemble_plugin.py`
- Does NOT own: `lca/infrastructure/path/`, `lca/contracts/` (AP-01)
- Invariants to test: 组装过程中的 Defer Catalog 剔除与刷新逻辑不依赖脆弱的整段正则匹配，历史轮次重复追加不会导致 catalog 文本失控膨胀。

**Step 1: Write the failing test**
在 `tests/plugins/think/test_history_assemble_plugin.py` 中校验多次组装的幂等性与纯净性。

**Step 2: Run test to verify it fails**
```bash
pytest tests/plugins/think/test_history_assemble_plugin.py -v
```

**Step 3: Write minimal implementation**
在 `lca/nodes/think/history/assemble.py` 中重构 `_strip_defer_catalog`，建立精确的边界判定与纯净 prompt 缓存。

**Step 4: Run test to verify it passes**
```bash
pytest tests/plugins/think/test_history_assemble_plugin.py -v
```
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/nodes/think/history/assemble.py tests/plugins/think/test_history_assemble_plugin.py
git commit -m "refactor(assemble): 优化 Defer Catalog 清理逻辑，消除脆弱全文正则替换"
```

---

### Task 6: 全链路不变量回归验证与门禁体检

**Files:**
- Test: 关联的全部单测与场景测试
- Does NOT own: 严格验证 git diff 不含有任何不在 Owns 范围的文件 (AP-01)
- Invariants to test: INV-01 ~ INV-06 全量通过

**Step 1: 运行全量关联单测**
```bash
pytest tests/plugins/assistant/test_templates.py \
       tests/plugins/prompts/test_runtime_env_section.py \
       tests/infrastructure/memory/test_standing_write_path.py \
       tests/scenario/leaked/test_leaked_tool_call.py \
       tests/plugins/think/test_history_assemble_plugin.py -v
```
Expected: 全部 PASS。

**Step 2: 运行代码工程与格式门禁**
```bash
ruff check lca/ tests/
ruff format --check lca/ tests/
git diff --check
```
Expected: 0 报错，0 告警，退出码 0。

**Step 3: 验证负向边界 (Does NOT own)**
```bash
git status --short
```
确认没有修改任何外部资产（如 `~/everything-library`）、前端源码（`lobehub-ui/`）或无关会话模型。

**Step 4: 更新任务追踪并在 task.md 中记录证据**
在 `docs/plans/task.md` 标记各任务完成状态。

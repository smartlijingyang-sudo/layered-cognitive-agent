# 助理演化闭环流程测试设计方案（Assistant Evolution Flow Design）

## 1. 概述与背景

基于近期提交的认知底座演进（ADR-0247 记忆知识层、`USER.md` 用户画像自动回填、`observe.py` 助理 bootstrap 投影合并自感知、`create_assistant_skill` 助理自主安装技能与 0067 三闸校验），本设计为系统建立端到端的完整演化流程测试。

### 验证全景闭环
```text
创建助理 → 助理自我感知 → 对话修改 USER 画像并回填 → 自主创建并安装 Skill → 激活并使用该 Skill 解决问题
```

---

## 2. 多轮流程与断言规格

### Turn 0：创建助理与 Home 基础结构校验
- **输入动作**：通过 `AssistantCatalog` 或 `POST /v1/assistants` 创建新助理：
  - `name`: `"流程测试演化助理"`
  - `description`: `"验证自感知、记忆知识层与自主技能演化流程"`
- **物理事实断言**：
  - 返回合法 `assistant_id` 与 `home_path`；
  - `{home_path}/` 完整初始化：`SOUL.md`、`USER.md`、`AGENTS.md`、`goals.yaml`、`skills/`、`memory/` 均就绪；
  - 初始 `USER.md` 符合模板卫生要求（非空但无特定用户偏好）。

### Turn 1：助理自我感知验证（Self-Perception）
- **用户输入**：
  > `"请介绍一下你自己：你是谁？你的职责是什么？你目前知道关于用户的什么信息？你有哪些可用工具或技能？"`
- **系统机制**：
  - `observe.py` 将 Home 下的 `assistant_bootstrap` 投影（`SOUL.md`、`USER.md`、`AGENTS.md`、`goals.yaml`）合并到感知 `ContextManifest`；
  - Prompt 装配区（`SoulSection`、`UserProfileSection`、`ToolsSection`）承载这些上下文。
- **断言**：
  - 助理回复体现设定的身份名称与职责，且能感知到初始服务对象与工具目录。

### Turn 2：对话修改用户画像并触发 `USER.md` 回填（User Profile Modification）
- **用户输入**：
  > `"我是系统架构师李超，主要技术栈是 Python 和 Rust。请记住我：后续方案回复必须简洁扼要、优先给出代码示例与架构图，不要客套话。"`
- **系统机制**：
  - 记忆提炼管道 / 记忆工具捕获：
    - `identity`: `"用户身份：系统架构师李超，技术栈 Python 和 Rust"`
    - `preference`: `"用户偏好：回复简洁扼要、优先给出代码示例与架构图、无客套话"`
  - `AssistantMemory` 落盘后自动触发 `ASSISTANT_PROFILE_BACKFILL` 回调；
  - `ProfileBackfillService` 将结构化记忆渲染并经由 `AssistantCatalog.revise_profile` 写回 `{home_path}/USER.md`（生成 revision 快照）。
- **物理事实断言**：
  - 检查 `{home_path}/USER.md`，必须包含结构化的 `## 身份`（架构师李超）与 `## 偏好`（简洁扼要、代码与图优先）；
  - Revision 版本快照递增。

### Turn 3：跨轮感知验证（Memory & Profile Verification）
- **用户输入**：
  > `"你还记得我是谁以及我的回答偏好吗？"`
- **系统机制**：
  - 再次进入 PerceiveObserve 时，读取已被更新回填的 `USER.md`，记忆层检索匹配用户画像。
- **断言**：
  - 助理回答准确说明用户是架构师李超、偏好简洁/代码与图优先，文本风格遵守简洁要求。

### Turn 4：自主创建并安装 Skill（Autonomous Skill Creation）
- **用户输入**：
  > `"请为自己创建一个名为 code-review-helper 的技能，遵循技能规范（包含 YAML frontmatter：name 为 code-review-helper，description 说明这是代码审查规范）。技能内容定义代码审查 SOP：1. 契约与不变量；2. 边界条件与异常；3. 资源释放与泄露防护；4. 给出重构代码。请使用 create_assistant_skill 工具将该技能安装到你的技能目录。"`
- **系统机制**：
  - 模型调用 `create_assistant_skill(skill_md=...)`；
  - 经历 0067 三闸校验（结构合法、frontmatter 齐全、references 闭合）；
  - 落盘至 `{home_path}/skills/code-review-helper/SKILL.md`，并在 `{home_path}/manifest.json` 中标记为 `verified`。
- **物理事实断言**：
  - 文件 `{home_path}/skills/code-review-helper/SKILL.md` 存在且格式正确；
  - `manifest.json` 中该 skill 的 `artifact_state == "verified"`。

### Turn 5：激活并使用新 Skill（Activate & Execute Skill）
- **用户输入**：
  > `"请使用刚刚安装的 code-review-helper 技能，审查以下这段 Python 代码：\n```python\ndef read_config(path):\n    f = open(path)\n    return f.read()\n```"`
- **系统机制**：
  - 模型调用 `activate_skill(skill_id="code-review-helper")` 获得审查 SOP；
  - 依据审查 SOP 发现 `open()` 未使用上下文管理器导致的句柄泄露风险，并按步骤输出审查分析及重构代码。
- **断言**：
  - 运行记录中存在 `activate_skill` 工具调用；
  - 最终审查意见明确指出了未关闭文件句柄（资源释放问题），并提供了 `with open(...)` 的重构代码。

---

## 3. 双模测试套件架构

### 3.1 确定性集成测试（`tests/integration/test_assistant_evolution_flow.py`）
- **目标**：不依赖外部网络与 LLM API Key，毫秒级快速运行，纳入 CI 门禁。
- **关键组件与装配**：
  - 真实 `AssistantCatalog`（在 `pytest` 的 `tmp_path` 下创建隔离 Home）；
  - 真实 `PerceiveObserveExecutor`（验证 `assistant_bootstrap` 投影合并）；
  - 真实 `ProfileBackfillService` 挂接为 `AssistantMemory` 的 `profile_backfill` 回调；
  - 真实 `AssistantCreateSkillTool`（带真实 0067 三闸验证器）；
  - 真实 `activate_skill` 逻辑；
  - 严格断言状态转移与文件系统真实状态。

### 3.2 真实模型端到端测试（`tests/e2e/test_assistant_evolution_flow_live.py`）
- **目标**：在 127.0.0.1:8765 内核运行中，驱动真实大模型进行 5 轮交互，检验模型自主行为。
- **机制与守则**：
  - 标记 `@pytest.mark.real_llm`；
  - 环境自检 `_has_llm_key()` 与 `_kernel_ready()`，缺省时友好跳过；
  - HTTP 客户端轮询等待 run 完成与 skill 验证完成；
  - 会话轨迹日志追溯，失败时输出 `run_id` 方便通过 `./scripts/lca-ops timeline` 复盘；
  - 测试结束自动清理临时助理资源。

---

## 4. 验证命令

```bash
# 1. 确定性集成测试验证（CI 标配，快速无损）
pytest tests/integration/test_assistant_evolution_flow.py -v

# 2. 真实大模型端到端测试（需 LLM API Key 与内核启动）
pytest tests/e2e/test_assistant_evolution_flow_live.py -v -m real_llm -s
```

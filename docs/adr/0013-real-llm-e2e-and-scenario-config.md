# ADR-0013: 真实 LLM 团队级端到端测试 + 场景配置化

## 状态
Accepted

## 背景

`tests/test_team_scenario_e2e.py` 覆盖了 hierarchical/sequential/parallel/handoff 四种团队协作模式，但全部依赖 `tests/scenario_llm.py::ScenarioLLM`——一个按 `ROLE` 字符串 + `TOOL_RESULT` 前缀做 if/elif 路由、直接吐固定 JSON 的假 LLM。它不产生真实推理的不确定性，也验证不了"委派目标角色是否在真实模型输出里拼写正确"这类问题。

同时，Prompt 模板（`DEFAULT_REACT_TEMPLATE` / `HIERARCHICAL_DELEGATE_TEMPLATE`）硬编码在 `reasoner.py` 中，角色定义硬编码在测试方法体内，`lca_single_agent_demo.py` 里还残留着开发者本机绝对路径 `/home/lichao/zero-agent/.env`。

## 决定

### 1. Prompt 模板外部化

模板正文从 `reasoner.py` 搬到 `lca/layer1_cognitive/brain/prompts/*.md`，通过 `load_builtin_prompt(name)` 用 `importlib.resources` 加载（不依赖进程 CWD）。`reasoner.py` 保留同名模块级常量作为向后兼容重导出，既有 import 路径零改动。

**为什么不引入模板引擎**：现有 `SimplePromptManager` 用 `str.format()` 已足够，引入 Jinja2 等属于过度设计。

### 2. LLM Adapter 工厂

新增 `lca/layer0_infra/llm_adapter/factory.py::resolve_llm_adapter()`：纯函数，读 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` 环境变量，有 Key 返回 `OpenAICompatAdapter`，否则返回 `MockLLMAdapter`。`load_dotenv_if_present()` 从 CWD 向上寻找最近的 `.env`，不再硬编码任何开发者本机路径。

### 3. 团队场景 YAML 配置化

新增 `tests/fixtures/team_scenarios/ecommerce_launch.yaml`，角色定义、团队拓扑、测试用例全部声明式描述。`tests/support/scenario_loader.py` 负责 YAML → `Agent`/`MultiAgentTeam` 的装配——这是测试胶水代码，不进入 `lca/` 包（`import-linter` 的 `root_package = "lca"` 不约束 `tests/`）。

### 4. 真实 LLM 测试用独立 pytest marker

新增 `@pytest.mark.real_llm`，`addopts` 默认排除（`-m "not real_llm"`）。理由：
- 不是每个贡献者都持有 API Key，默认跑会导致无 Key 环境测试报红
- 真实模型输出有非确定性，不适合做 PR 门禁的强制项（会因模型输出漂移偶发失败）
- CI 侧通过 `workflow_dispatch` 或 `schedule: nightly` 独立触发，从 GitHub Secrets 注入 Key

### 5. JSONL 结构化 Trace 落盘

新增 `JSONLFileObservability(Observability)`，每行一个 JSON 对象，可用 `jq` 按 `trace_id` 过滤回放。Hook 触发的 span 自动携带 `action_type`/`confidence`/`response_preview`/`error_message` 等属性，密钥字符串用正则脱敏。默认 observability 仍为 `"console"`，向后兼容。

## 后果

### 正面
- Prompt 迭代不再触碰核心代码路径
- 任何 demo/测试接入真实 LLM 只需一行 `resolve_llm_adapter()`
- 场景定义与断言逻辑解耦，新增场景只改 YAML
- 真实 LLM 链路可离线回放排障
- 默认 CI 时间/成本/稳定性不受影响

### 负面 / 风险
- `pyyaml` 新增为 test 依赖组（仅在测试时需要，不拖累核心库体积）
- `openai`/`python-dotenv` 为可选依赖组 `llm-openai`（按需安装）
- 真实 LLM 测试的断言只能验证结构化事件（status/steps），不能验证具体文案

## 自动化保障

| 机制 | 作用 |
|---|---|
| `pytest -m "not real_llm"` | 默认 CI 门禁不跑真实 LLM 测试 |
| `import-linter` 五层契约 | 确保新增 L0 组件不破坏分层 |
| `test_architecture_conformance.py` | 确保新类声明 Protocol 基类 |
| `JSONLFileObservability` + hook span attributes | 真实链路每步可回放 |

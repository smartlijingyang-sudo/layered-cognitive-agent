# 系统性消除硬编码：通用头像提示词扩写机制实施计划 (Avatar Generic Prompt Expansion Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底消除任何特例人物/风格硬编码字典（如 `_KNOWN_FIGURE_MAP`），建立 Agent 认知层契约引导 + 服务层通用 PromptExpander 管道的双层泛化机制，支持任意人物、角色、动物与艺术风格的高质量自适应生图。

**Architecture:** 
1. Tier 1 (Agent 侧)：Tool Schema 与 Description 明确引导 Agent 认知核心将任意意图翻译并扩写为富视觉特征（面部、衣着、光影、构图）的 `visual_prompt`；
2. Tier 2 (Service 侧)：新增 `PromptExpander` 协议与 `LlmPromptExpander`（1-shot 通用转换器）/ `RulePromptExpander`（通用语法前缀剥离与肖像模版，零实体字典）；
3. 彻底从 `service.py` 剥离 `_KNOWN_FIGURE_MAP`，加入 AST 扫描测试严防硬编码回潮。

**Tech Stack:** Python 3.12, asyncio, re, ast, pytest.

---

### Task 1: PromptExpander 契约与通用扩写器实现 (`expander.py`)

**Files:**
- Create: `lca/plugins/avatar/expander.py`
- Test: `tests/plugins/avatar/test_expander.py`
- Does NOT own: `lca/plugins/avatar/service.py`, `lca/plugins/avatar/routes.py`, `lobehub-ui/`
- Invariants to test: `INV-AVATAR-ZERO-HARDCODE`, `INV-AVATAR-ARBITRARY-FIGURES`, `INV-AVATAR-DETERMINISTIC-CLEANER`

**Step 1: 编写失败测试**

在 `tests/plugins/avatar/test_expander.py` 中编写针对 `PromptExpander`、`RulePromptExpander` 与 `LlmPromptExpander` 的测试，覆盖：
1. AST 扫描：`expander.py` 源码中绝不包含任何实体人物名字典或写死名单；
2. 参数化实体提取：无论是“爱因斯坦”、“鲁迅”、“赛博朋克猫”、“水墨道士”还是“戴墨镜的柴犬”，`RulePromptExpander` 均能提取干净主体并生成标准高质量模版；
3. 多种口语长句清洗：覆盖“我想修改你的形象和头像，改成：XXX”、“请帮我换成一个XXX”、“把头像换为XXX”；
4. `LlmPromptExpander` 异步与同步 mock 调用。

**Step 2: 运行测试验证失败**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_expander.py --no-cov
```
预期：FAIL (ModuleNotFoundError: No module named 'lca.plugins.avatar.expander')

**Step 3: 编写最小实现**

在 `lca/plugins/avatar/expander.py` 中实现：
- `PromptExpander` (Protocol)
- `RulePromptExpander` (纯语法正则剥离前缀，套用标准肖像模版，零实体映射)
- `LlmPromptExpander` (1-shot 通用生图转换器包装)

**Step 4: 运行测试验证通过**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_expander.py --no-cov
```
预期：PASS (全部用例通过)

**Step 5: 提交**

```bash
git add lca/plugins/avatar/expander.py tests/plugins/avatar/test_expander.py
git commit -m "feat(avatar): implement generic PromptExpander protocol and implementations"
```

---

### Task 2: 彻底切除 `_KNOWN_FIGURE_MAP` 并将 `AvatarService` 接入 `PromptExpander` (`service.py`)

**Files:**
- Modify: `lca/plugins/avatar/service.py`
- Test: `tests/plugins/avatar/test_prompt_contract.py`
- Does NOT own: `lca/plugins/avatar/routes.py`, `lca/nodes/`, `lobehub-ui/`
- Invariants to test: `INV-AVATAR-ZERO-HARDCODE`, `INV-AVATAR-ARBITRARY-FIGURES`, `INV-ADR0271-C3`

**Step 1: 编写失败测试**

在 `tests/plugins/avatar/test_prompt_contract.py` 中：
1. 增加 AST 断言：扫描 `lca/plugins/avatar/service.py`，断言 `_KNOWN_FIGURE_MAP` 变量已被彻底删除；
2. 泛化测试：对非特例输入（如“爱因斯坦”、“赛博朋克猫”）调用 `service.create`，断言产出的 prompt 包含对应主体的视觉描述，且无对话前缀噪声；
3. 保持 ADR-0271 C3 不变量：产出 prompt 必须包含或以 `user_request` 原文开头。

**Step 2: 运行测试验证失败**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_prompt_contract.py -k "zero_hardcode" --no-cov
```
预期：FAIL (断言 `_KNOWN_FIGURE_MAP` 存在而报错)

**Step 3: 编写实现**

修改 `lca/plugins/avatar/service.py`：
1. 删除 `_KNOWN_FIGURE_MAP` 常量及对应查找逻辑；
2. `AvatarService.__init__` 增加 `expander: PromptExpander | None = None`，缺省为 `RulePromptExpander()`；
3. 重构 `_build_prompt`：优先采用 `visual_prompt`；若未传则调用 `await self.expander.expand(user_request)`；
4. 身份属性解耦：当用户请求表达了明确的主体变更时，避免旧身份属性强行主导画面主体。

**Step 4: 运行测试验证通过**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_prompt_contract.py --no-cov
```
预期：PASS

**Step 5: 提交**

```bash
git add lca/plugins/avatar/service.py tests/plugins/avatar/test_prompt_contract.py
git commit -m "refactor(avatar): purge figure hardcoding and bind PromptExpander in AvatarService"
```

---

### Task 3: 强化 Tool 契约引导与插件层装配 (`tools.py` & `plugin.py`)

**Files:**
- Modify: `lca/plugins/avatar/tools.py`
- Modify: `lca/plugins/avatar/plugin.py`
- Test: `tests/plugins/avatar/test_tools.py`, `tests/plugins/avatar/test_plugin.py`
- Does NOT own: `lca/plugins/avatar/routes.py`, `lca/infrastructure/`
- Invariants to test: `INV-AVATAR-TOOL-CONTRACT`

**Step 1: 编写失败测试**

在 `tests/plugins/avatar/test_tools.py` 中断言：
1. `AvatarCreateTool.parameters` 与 `AvatarEditTool.parameters` 的 `visual_prompt` 字段必须包含面向 Agent 的详细构图、艺术风格与面部特征扩写指导；
2. Tool Description 必须明确要求 Agent 展开视觉细节，并禁止输出原始 Markdown 图片链接。

**Step 2: 运行测试验证失败**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_tools.py -k "tool_guidance" --no-cov
```
预期：FAIL

**Step 3: 编写实现**

1. 修改 `lca/plugins/avatar/tools.py`：升级 `AvatarCreateTool` 与 `AvatarEditTool` 的 description 和 parameters，提供高质量视觉扩写范例；
2. 修改 `lca/plugins/avatar/plugin.py`：在 `Config` 中支持 `prompt_expander_llm`，并将初始化的 `PromptExpander` 注入 `_build_service`。

**Step 4: 运行测试验证通过**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/test_tools.py tests/plugins/avatar/test_plugin.py --no-cov
```
预期：PASS

**Step 5: 提交**

```bash
git add lca/plugins/avatar/tools.py lca/plugins/avatar/plugin.py tests/plugins/avatar/test_tools.py tests/plugins/avatar/test_plugin.py
git commit -m "feat(avatar): enhance agent visual prompt guidelines and wire expander in plugin"
```

---

### Task 4: 全量回归、代码门禁与端到端实测验证

**Files:**
- Verify: 全部 avatar 测试、AST 反硬编码守卫、代码风格门禁与运行服务。
- Does NOT own: 严格遵守负向清单，不越权触碰其他目录。

**Step 1: 运行全量 avatar 插件测试套件**

```bash
/opt/lca/venv/bin/pytest tests/plugins/avatar/ --no-cov
```
预期：100% 全部通过（>160 个测试）。

**Step 2: 运行代码门禁检查**

```bash
/home/lichao/.local/bin/ruff check lca/plugins/avatar/ tests/plugins/avatar/
git diff --check
```
预期：0 报错，退出码 0。

**Step 3: 内核平滑重启与实测**

```bash
./scripts/lca-ops kernel-restart
curl -s -H "Authorization: Bearer lca-local" -H "x-lca-user-id: user_iYgpmu5val9sIMjQnsjkicDhhvo" http://127.0.0.1:8765/v1/assistants/agt_Qp94D1swZDeg/avatar/candidates
```
预期：返回 200 OK，包含候选头像。

**Step 4: 更新 `docs/plans/task.md` 并提交**

```bash
git add docs/plans/task.md
git commit -m "docs(task): record completion of generic avatar prompt expansion refactor"
```

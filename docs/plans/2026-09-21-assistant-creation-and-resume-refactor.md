# 助理创建向导、网关 Resume 路由与 Profile 合流全链路重构实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底根治对话创建助理全链路缺陷：1. 升级默认 Kernel 服务 Profile 为 `web-assistant` 并软化阻断依赖，保证原生助理能力开箱即用；2. 网关 `POST /runs` Resume 路由精准绑定 `run_id`，前端带上 `run_id`，彻底消除 409 Conflict 与用户答题丢失；3. 重构 `create-assistant/SKILL.md` 提示词，根除架构名词与内部向导代码泄露，闭环端到端自然人机问答。

**Architecture:** 
- 平台配置层：以 `lca-ops.yaml` 为 SSOT，将 `supervisor.py`、`cli/config` 中的默认 Profile 与服务启动收敛至 `profiles/web-assistant.yaml`，软化 `composio` 强依赖。
- 传输控制面：在 `CreateRunRequest` 与 `_dispatch_resume` 中引入显式 `run_id` 寻址，优先使用精准 `run_id` 恢复会话，降级回退保留 `topic_id`；前端补丁 `executeGatewayRun.ts` 携带 `run_id`。
- 领域认知层：净化 `create-assistant/SKILL.md`，删除教导用户当运维的错误指令与内部状态机泄露，规范五步向导 SOP。

**Tech Stack:** Python 3.12, TypeScript / Next.js (LobeHub patch), Typer, FastAPI, Pydantic, pytest.

---

### Task 1: 软化 Composio 阻断依赖 & 平台默认 Profile 合流

**Files:**
- Modify: `profiles/web-assistant.yaml:83-88`
- Modify: `lca/infrastructure/cli/services/kernel/supervisor.py:704-710`
- Modify: `lca/infrastructure/cli/commands/kernel/supervisor.py:230-238`
- Modify: `lca/infrastructure/cli/config/config.py:34-36`
- Modify: `lca/infrastructure/cli/profile/profile.py:14-16`
- Test: `tests/architecture/test_assistant_runtime_invariants.py`

**Step 1: 编写/更新 Profile 解析与 Supervisor 默认值单元测试**

在 `tests/infrastructure/cli/test_supervisor_profile_default.py` 中验证 `default_program_config` 默认采用 `profiles/web-assistant.yaml`：

```python
from pathlib import Path
from lca.infrastructure.cli.services.kernel.supervisor import default_program_config

def test_default_program_config_uses_web_assistant():
    cfg = default_program_config()
    assert "--profile" in cfg.args
    idx = cfg.args.index("--profile")
    assert cfg.args[idx + 1] == "profiles/web-assistant.yaml"
```

**Step 2: 运行测试验证失败**

运行：`pytest tests/infrastructure/cli/test_supervisor_profile_default.py -v`  
预期：FAIL（当前默认值为 `profiles/web-standard.yaml`）。

**Step 3: 实现修改**

1. 将 `profiles/web-assistant.yaml` 中的 `required: true` 修改为 `required: false`（对齐可选依赖）：
   ```yaml
     - id: lca-composio-provider
       config:
         api_key:
           from_env: COMPOSIO_API_KEY
           required: false
   ```
2. 更新 `lca/infrastructure/cli/services/kernel/supervisor.py`：
   ```python
   def default_program_config(
       *,
       profile: str = "profiles/web-assistant.yaml",
       host: str = "0.0.0.0",
       port: int = 8765,
   ) -> ProgramConfig:
   ```
3. 更新 `lca/infrastructure/cli/commands/kernel/supervisor.py` 中的 CLI 选项默认值：
   `profile: str = typer.Option("profiles/web-assistant.yaml", "--profile", "-p", ...)`
4. 更新 `lca/infrastructure/cli/config/config.py` 与 `profile.py` 中的 `DEFAULT_PROFILE` 为 `profiles/web-assistant.yaml`。

**Step 4: 运行测试验证通过**

运行：
```bash
pytest tests/infrastructure/cli/test_supervisor_profile_default.py -v
./scripts/lca-ops kernel_check profiles/web-assistant.yaml
```
预期：PASS，13 plans validated。

**Step 5: 提交代码**

```bash
git add profiles/web-assistant.yaml lca/infrastructure/cli/ tests/infrastructure/cli/
git commit -m "feat(ops): converge default kernel profile to web-assistant"
```

---

### Task 2: 网关 `_dispatch_resume` 支持精准 `run_id` 寻址与前端对齐

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:90-108,421-465`
- Modify: `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts:385-395`
- Test: `tests/plugins/transport/webserver/test_resume_run_id_binding.py`

**Step 1: 编写精准 `run_id` Resume 的回归测试**

在 `tests/plugins/transport/webserver/test_resume_run_id_binding.py` 中测试当请求体直接携带 `run_id` 时，网关不再受 `get_latest_for_topic` 覆盖干扰：

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    _dispatch_resume,
    CreateRunRequest,
)

@pytest.mark.asyncio
async def test_dispatch_resume_prefers_explicit_run_id():
    request = MagicMock(spec=Request)
    run_port = MagicMock()
    run_port.resume_approval = AsyncMock(return_value=MagicMock(accepted=True))
    request.app.state.run_port = run_port

    store = MagicMock()
    store.get_latest_for_topic = AsyncMock(return_value={"run_id": "wrong_run_id"})
    request.app.state.running_operation_store = store

    body = {
        "run_id": "target_run_123",
        "topic_id": "tpc_abc",
        "resume_tool_result": {
            "toolCallId": "toolu_xyz",
            "content": "user answer",
            "parentMessageId": "msg_001"
        }
    }
    decoded = MagicMock(spec=CreateRunRequest)
    decoded.run_id = "target_run_123"
    decoded.resume_approval = None
    decoded.resume_tool_result = body["resume_tool_result"]

    res = await _dispatch_resume(request, body, decoded)
    assert res.status_code == 200
    run_port.resume_approval.assert_awaited_once()
    assert run_port.resume_approval.call_args[0][0] == "target_run_123"
```

**Step 2: 运行测试验证失败**

运行：`pytest tests/plugins/transport/webserver/test_resume_run_id_binding.py -v`  
预期：FAIL（当前逻辑无视 `decoded.run_id`，强制从 store 查询并取了 `wrong_run_id`）。

**Step 3: 编写实现代码**

1. 在 `CreateRunRequest` dataclass 中增加 `run_id: str = ""` 字段。
2. 在 `decode_create_run` 中解析 `run_id = str(body.get("run_id") or "")`。
3. 重构 `_dispatch_resume`：
   ```python
   payload_dict = decoded.resume_tool_result or decoded.resume_approval or {}
   run_id = (
       decoded.run_id
       or str(payload_dict.get("run_id") or "")
       or str(body.get("run_id") or "")
   )
   if not run_id:
       topic_id = topic_id_from_body(body)
       if not topic_id:
           return _err("resume requires run_id or topic_id to locate run", status_code=400)
       store = getattr(request.app.state, "running_operation_store", None)
       if store is None:
           return _err("running operation store not available", status_code=503)
       row = await store.get_latest_for_topic(topic_id)
       if row is None:
           return _err(f"no running operation for topic {topic_id!r}", status_code=404)
       run_id = str(row.get("run_id") or "")
   ```
4. 在 `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts` 中传递 `run_id`：
   ```typescript
   await lcaStartRun({
     run_id: runId,
     agent: { id: 'solo', name: 'solo' },
     messages: [],
     parent_message_id: parentMessageId,
     topic_id: topicId || undefined,
     resume_tool_result: { content, parentMessageId, toolCallId, run_id: runId },
   });
   ```
5. 重新应用前端补丁：`python3 deploy/lobehub/patch_lobehub.py`。

**Step 4: 运行测试验证通过**

运行：
```bash
pytest tests/plugins/transport/webserver/test_resume_run_id_binding.py -v
python3 deploy/lobehub/patch_lobehub.py --verify-only
```
预期：PASS（1/1 单元测试通过，23/23 补丁验证全部通过）。

**Step 5: 提交代码**

```bash
git add lca/plugins/transport/webserver/ deploy/lobehub/ tests/plugins/transport/webserver/
git commit -m "fix(gateway): bind resume dispatch explicitly to run_id to eliminate 409 race"
```

---

### Task 3: 彻底重构 `create-assistant/SKILL.md` 提示词与交互 SOP

**Files:**
- Modify: `/home/lichao/.lca/skills/create-assistant/SKILL.md`
- Modify: `lca/infrastructure/tools/skills/search/tool.py:30-45`
- Test: `tests/skills/test_create_assistant_skill_hygiene.py`

**Step 1: 编写 Skill 文本卫生检查单测**

在 `tests/skills/test_create_assistant_skill_hygiene.py` 中测试 SKILL.md 不含有内部配置名词和糟糕指引：

```python
from pathlib import Path

def test_create_assistant_skill_has_no_leaked_profile_or_admin_hints():
    skill_path = Path("/home/lichao/.lca/skills/create-assistant/SKILL.md")
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    # 禁止出现教导用户当系统管理员的糟糕指令
    assert "web-assistant profile" not in content
    assert "系统管理员" not in content
    # 确保核心五步逻辑面向自然交互
    assert "askUserQuestion" in content
    assert "create_assistant" in content
```

**Step 2: 运行测试验证失败**

运行：`pytest tests/skills/test_create_assistant_skill_hygiene.py -v`  
预期：FAIL（当前 SKILL.md 包含这些泄漏文本）。

**Step 3: 实施重构**

1. 重写 `/home/lichao/.lca/skills/create-assistant/SKILL.md`：
   - 删除“无工具需 web-assistant profile 直接告知用户”等垃圾代码；
   - 确立防御规则：若工具列表中未检测到 `create_assistant`，以友好自然的助理语气回复“当前对话环境暂未开放助理创建功能，请稍后重试”，严禁向最终用户暴露内部状态机或配置名称；
   - 明确五步引导流程（部门 -> 角色 -> SOUL 对齐 -> 名字 -> 创建），强化 `askUserQuestion` 与最终成果汇报卡片的呈现要求。
2. 优化 `lca/infrastructure/tools/skills/search/tool.py` 中 `search_skill` 的描述，删除“不会做的任务先搜这里”这类诱导模型盲目并行的歧义语句。

**Step 4: 运行测试验证通过**

运行：`pytest tests/skills/test_create_assistant_skill_hygiene.py -v`  
预期：PASS。

**Step 5: 提交代码**

```bash
git add lca/infrastructure/tools/skills/ tests/skills/
git commit -m "refactor(skills): sanitize create-assistant skill prompt and eliminate architecture leakage"
```

---

### Task 4: 端到端服务重启与全链路集成验证

**Files:**
- Touch: Kernel process
- Test: Live API check + 端到端测试

**Step 1: 重启内核进程**

```bash
./scripts/lca-ops kernel-restart
```

**Step 2: 验证内核健康与工具列表**

```bash
curl -s http://127.0.0.1:8765/health | jq .
./scripts/lca-ops status --json
```
预期：
- `status`: running
- 校验服务包含 `create_assistant` 工具。

**Step 3: 运行端到端回归测试集**

运行相关 assistant 单测与网关测试：
```bash
pytest tests/plugins/assistant/test_tools_plugin.py -v
pytest tests/plugins/transport/webserver/ -k resume -v
```
预期：全部 PASS。

**Step 4: 提交任务状态与总结**

更新 `docs/plans/task.md` 并提交。

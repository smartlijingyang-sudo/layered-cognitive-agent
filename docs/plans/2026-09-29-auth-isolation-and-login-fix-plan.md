# 多用户登录、归属隔离与用户名解析修复实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于第一性原理全面修复多用户登录下的归属隔离失效、`POST /runs` 越权逃逸漏洞、以及注册时 `username` 未落盘导致的用户名登录断路缺陷，达成 [ADR-0252](file:///home/lichao/layered-cognitive-agent/docs/adr/0252-multi-user-onboarding-and-identity.md) 规定的多租户安全契约。

**Architecture:** 
1. 控制面：`lca.plugins.assistant.ownership` 插件 `dev_mode` 默认改为安全 fail-closed（`False`），并通过 `{from_env: LCA_DEV_MODE}` 动态注入，消除硬编码；
2. 执行窄门：`command_endpoints.py` 强化 `_validate_assistant_ownership`，在非 `dev_mode` 下严格要求 `x-lca-user-id` 并校验调用者所有权，杜绝“无头逃逸”；
3. 身份闭环：前端 `useSignUp.ts` 注册时透传 `username`（取邮箱前缀），使 Better Auth 及 Postgres `users.username` 具备有效真值，闭环 `/api/auth/resolve-username` 寻址。

**Tech Stack:** Python 3.11/3.12, FastAPI/Starlette, Pydantic v2, TypeScript/Next.js 15, Better Auth, PostgreSQL, SQLite (WAL).

---

### Task 1: `assistant.ownership` 插件配置支持动态 `dev_mode` 并默认安全闭环

**Files:**
- Modify: `lca/plugins/assistant/ownership/plugin.py:42-60`
- Modify: `profiles/web-assistant.yaml:83-91`
- Modify: `deploy/lobehub/.env.lca:68-76`
- Test: `tests/lca_plugins/transport/webserver/test_auth_user.py`
- Does NOT own: `lobehub-ui/src/` 或 `packages/contracts/`
- Invariants to test:
  - `Config.dev_mode` 缺省为 `False`；
  - 传入 `"1"`, `"true"`, `True` 解析为 `True`，传入 `None`, `""`, `"0"`, `"false"` 解析为 `False`；
  - `dev_mode=False` 时缺少用户头拒绝返回 401，非 owner 拒绝返回 404。

**Step 1: Write the failing test**
在 `tests/lca_plugins/transport/webserver/test_auth_user.py` 中新增 `test_ownership_config_dev_mode_coercion` 与 `test_ownership_config_defaults_to_false`。

**Step 2: Run test to verify it fails**
Run: `./.venv/bin/pytest tests/lca_plugins/transport/webserver/test_auth_user.py -k "coercion" -v`
Expected: FAIL

**Step 3: Implement minimal code**
在 `lca/plugins/assistant/ownership/plugin.py` 中：
- `dev_mode: bool = False`
- 增加 `field_validator` 支持解析环境变量字符串与 `None` 兜底。
在 `profiles/web-assistant.yaml` 中配置 `dev_mode: {from_env: LCA_DEV_MODE, required: false}`。
在 `deploy/lobehub/.env.lca` 中注明 `LCA_DEV_MODE=0`。

**Step 4: Run test to verify it passes**
Run: `./.venv/bin/pytest tests/lca_plugins/transport/webserver/test_auth_user.py -v`
Expected: PASS

---

### Task 2: 收紧 `POST /runs` 归属逃逸门禁（闭环无用户头非法调用）

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:377-405`
- Test: `tests/lca_plugins/transport/webserver/test_auth_user.py`
- Does NOT own: `lca/runtime/` 或 `lca/session/`
- Invariants to test:
  - 当 `not dev_mode` 且指定了 `assistant_id` 时，缺少 `x-lca-user-id` 返回 401（code="missing_user"）；
  - 当 `not dev_mode` 且 `owner != user_id` 时返回 403（code="assistant_not_owned"）；
  - 当 `dev_mode=True` 时无用户头依然兼容放行。

**Step 1: Write the failing test**
在 `tests/lca_plugins/transport/webserver/test_auth_user.py` 中增加针对 `_validate_assistant_ownership` 的 3 个断言测试。

**Step 2: Run test to verify it fails**
Run: `./.venv/bin/pytest tests/lca_plugins/transport/webserver/test_auth_user.py -k "validate_assistant_ownership" -v`
Expected: FAIL

**Step 3: Implement minimal code**
修改 `command_endpoints.py` 中的 `_validate_assistant_ownership`，当 `not dev_mode` 且 `not user_id` 时返回 `_err("missing x-lca-user-id", status_code=401, code="missing_user")`。

**Step 4: Run test to verify it passes**
Run: `./.venv/bin/pytest tests/lca_plugins/transport/webserver/test_auth_user.py -k "validate_assistant_ownership" -v`
Expected: PASS

---

### Task 3: 前端注册流程透传 `username` 闭环用户名登录数据流

**Files:**
- Modify: `lobehub-ui/src/features/Auth/SignUp/useSignUp.ts:59-70`
- Does NOT own: `lobehub-ui/src/features/Conversation/`
- Invariants to test:
  - 注册请求参数带上 `username: username`；
  - Better Auth 在 `users` 表写入 `username` 字段；
  - 注册后调 `/api/auth/resolve-username` 能成功将 username 映射为对应 email。

**Step 1: Inspect and verify signUp.email interface**
核验 `signUp.email` 接受的参数类型与 `define-config.ts` 中的 `additionalFields.username`。

**Step 2: Modify `useSignUp.ts`**
在 `signUp.email({ ... })` 中加入 `username: username`。

**Step 3: Verify with real curl or automated unit test**
注册新测试账号并调用 `POST /api/auth/resolve-username`，断言 `exists: true` 且 `email` 匹配。

---

### Task 4: 服务平滑重启与端到端实机复测

**Files:**
- Modify: `docs/plans/task.md`
- Invariants to test:
  - 用户 B 无法越权查看用户 A 的助理（返回 404）；
  - 用户 B 列表仅展示自身助理；
  - 用户名登录端到端打通；
  - 内核端口 8765 裸调用在非 dev 模式下正确被 401 拦截。

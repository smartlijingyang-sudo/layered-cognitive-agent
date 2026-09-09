# Agent Note: lab worker 加载时体检

Status: implemented

## Problem

ADR-0211 §8 `lab-worker-purity` 是计划但未落地的规则:写一个新 worker 写错了 keyword-only / typed 入参 / 返回值 / 禁用的 framework 容器 / try-except / getattr 兜底,只有 `python -m agent_lab.run <stage>` 跑到 invoke 节点时才抛 `KeyError: factory 'lab.act.xxx' has no reflected worker_fn marker`。这个时机已经过了"写代码"和"端到端跑通"两个关口,违反 fail-loud 语义。

具体:
- `lca/plugins/lab/internal/loader.py:235` 的 `bind_worker` 失败统一 catch 后走 `_log.warning(...)`,反射错降级为 WARNING,加载继续。
- `agent_lab/runtime/invoke.py:74` 才在 invoke 时抛 KeyError。
- 离线 `tests/lab/test_reflection.py::STAGE_WORKERS` fixture 只验证 marker 存在,不验证 worker 函数体合规。

## Decision

落实 ADR-0211 §8,把体检本身做成独立模块,通过模式开关控制 fail-loud 强度。

### 模块边界

新增 `lca/plugins/lab/internal/audit/` 目录,与 `hooks.py` / `loader.py` 平级:

```
audit/
├── __init__.py            公共入口:audit_worker(module, fn) -> list[WorkerAuditError]
├── errors.py              WorkerAuditError / WorkerAuditFailure 类型(独立文件避免循环 import)
├── signature_rules.py     W-1 ~ W-5 inspect.signature 体检
└── body_rules.py          W-7 ~ W-10 ast 体检
```

模块本身**不** raise,只产错误列表;调用方决定 raise 还是 warning。新增规则(W-11 / W-12)只需加规则函数并注册,不动 hooks / loader。

### 规则清单

| ID | 规则 | 来源 |
|---|---|---|
| W-1 | 全 `*,` keyword-only | ADR-0211 §1.1 强约束 1 |
| W-2 | 入参必 typed;禁 `dict` / `Any` / `**kwargs` | ADR-0211 §1.1 强约束 2 |
| W-3 | 禁入参 `ctx` / `seams` / `node` / `inputs` | ADR-0211 §1.1 强约束 4 |
| W-5 | 返回值必 typed;禁 `dict` / `Any` | ADR-0211 §1.1 强约束 3 |
| W-7 | 禁 `try/except` | ADR-0211 §1.3 强约束 1 |
| W-8 | 禁构造 `Receipt(...)` / `EXCEPTION(...)` | ADR-0211 §1.3 强约束 2 |
| W-9 | 禁引用退役符号 `register_worker` / `Seams`（`body_provider` / `get_body` PR-E 落地后从退役清单移除） | ADR-0211 §1.4 |
| W-10 | 禁 `if x is None` / `getattr(x, attr, default)` 防御 | ADR-0211 §0.2 命题 5 |

W-4 / W-6 是 Config 收紧视角(非 signature / body),留给 Config 层 follow-up。

### fail-loud 模式开关

`LCA_WORKER_AUDIT_MODE` 环境变量:

- `raise`(默认 for CI / 端到端):体检错直接 raise `WorkerAuditFailure`,`load_all()` 失败,新 worker 写错立刻可见。
- `warn`(默认 for 当前开发态):体检错走 WARNING,**marker 缺失**让 invoke 路径触发原 KeyError,行为与引入体检前对称。

### 集成点

- `lca/plugins/lab/internal/hooks.py:discover_worker` 末尾调 `audit_worker(module_path, worker_fn)`,有错抛 `WorkerAuditFailure`。
- `lca/plugins/lab/internal/loader.py:load_all` `except WorkerAuditFailure` 按模式分流。
- `tests/lab/test_worker_audit.py`:13 个测试覆盖 W-1 ~ W-10 + audit_worker aggregate + loader raise 模式集成。

## Consequences

正向:
- 写新 worker 写错时 `python -m agent_lab.run <stage>` 立即报错,带 `<file>:<lineno>` 和 W-N 编号。
- 体检模块零 framework 知识(不依赖 hooks / loader),可独立单测;新增规则是 O(1) 改动。
- 模式开关让 CI 严格 + 开发态宽松并存,降低落地摩擦。

需后续完成(delete-when):
- ADR-0211 §0.3 §5 "Worker 三原则全部 89 个 carrier 落地":当前 22+ 个 worker 违反 W-2 / W-3 / W-10(主要集中在 `passthrough/*` 18 个 + `act/{shape,authorize,execute,observe}` 4 个 + 几个 reflect/remember/think worker)。这些违规 marker 在 warn 模式下缺失,`tests/lab/test_reflection.py::test_reflected_marker_registered` 已用 skipif 兼容;待 §5 落地后改为 strict 模式。
- ADR-0211 §8 lint-imports `lab-worker-purity` ruff 自定义规则:本次是 inline `inspect` + `ast` 实现,不是 ruff plugin;后续可补 ruff plugin 路径(本次不做,与 ADR-0211 §9 delete-when §4 收敛)。
- `bundles/lab-act.yaml` 仍引用已删的 `lca.plugins.lab.act.body_provider.plugin` —— pre-existing 问题,与本次无关。
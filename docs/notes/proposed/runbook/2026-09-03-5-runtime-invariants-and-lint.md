# Agent Note: 子 note 5 — 4 级 lint 守门规则与 runtime invariant 守门

Status: proposed

> 根 note 与元决策:[observation-convergence-root.md](../seam/2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 收 4 级 lint 守门与 runtime invariant,**最后落地**(所有反模式都迁完后才能有效)。

## Problem

根 note PR-2(`scripts/check_observation_ssot.py` 9 条 lint)只覆盖 L1 SSOT 字符串字面。用户 2026-09-03 反馈的 4 类未收口症状:

1. **emit 现场混乱** — 无 lint 守门"emit_exception_caught 只能 1 个入口"
2. **flush 时机不透明** — 无 lint 守门"`TracingFileSink.fallback_fd` 必须 `FsyncProtocol.PER_WRITE`"
3. **payload schema 缺失** — 无 lint 守门"`registry` EP 必须 `payload_class`"
4. **协议契约乱 + 双写** — 无 lint 守门"`EnvelopeEmitter.emit_exception_caught` 不准收裸 str"

`scripts/check_observation_ssot.py` 当前规则(根 note PR-2):

```python
# 1. 文件名硬编码
rg '"events\.jsonl"' lca/ scripts/ tests/  # → 0
rg '"journal\.json"' lca/ scripts/ tests/ # → 0
rg '"manifest\.json"' lca/ scripts/ tests/ # → 0
rg '"journal\.narrative\.md"' lca/ scripts/ tests/ # → 0
rg '"kernel\.log"' lca/ scripts/ tests/ # → 0
rg '".*\.exceptions\.jsonl"' lca/ scripts/ tests/ # → 0
rg '"profile_snapshot\.json"' lca/ scripts/ tests/ # → 0

# 2. Status 字面
rg 'in \{"success", "failed", "cancelled"' lca/ scripts/ tests/ # → 0
rg 'in \{"completed", "paused", "failed"' lca/ scripts/ tests/ # → 0
rg 'Literal\["completed", "failed", "paused"' lca/ scripts/ tests/ # → 0
rg '== RoleStatus\.(DONE|FAILED)' lca/ scripts/ tests/ # → 0

# 3. 反向耦合
rg 'from lca\.plugins\.transport\.webserver\.handlers\.runs\.session\.session import RunStatus' lca/ scripts/ tests/ # → 0

# 4. to_jsonable 重复
rg '^def to_jsonable' lca/ | wc -l # = 1
```

—— **缺 4 级守门 + runtime invariant**。

## Proposal

### 第一阶段:扩展 `check_observation_ssot.py` 至 13 条规则

新增 4 条规则覆盖 note 3 / note 4 的反模式:

```python
# L2 payload 必含字段(承接 note 4)
rg 'def emit_\w+\(.*payload:\s*dict' lca/ # → 0

# L3 emit 入口必须 schema 校验(承接 note 4)
rg 'from .*spine.exception_emit import' lca/ | xargs -I {} rg -L 'pydantic|parse_obj' {} # → 0

# L4 Protocol 不收裸 str(承接 note 3)
rg 'def emit_\w+\(.*: str,.*: str\)' lca/contracts/protocols/ # → 0

# registry EP 必须 payload_class(承接 note 4)
# 由 Python AST 静态检查实现,非 grep
```

### 第二阶段:新文件 `scripts/check_runtime_invariants.py`

新建,职责清晰:SSOT 守门 / invariant 守门**两个文件**。

```python
# invariant 1:runtime_loop except 后必须 exc_to_record + envelope.emit_exception_caught(record)
rg 'except.*as \w+:' lca/runtime/runtime_loop.py | xargs -I {} rg -L 'exc_to_record' {}

# invariant 2:FileSink 必须声明 fsync_protocol
rg 'class FileSink' lca/infrastructure/observability/spine/sinks/file_sink.py | xargs -I {} rg -L 'fsync_protocol'

# invariant 3:TracingFileSink fallback fd 必须 PER_WRITE
rg '_open_fallback_fd' lca/infrastructure/observability/spine/sinks/tracing_file_sink.py | xargs -I {} rg -L 'PER_WRITE'
```

### 第三阶段:`lca-ops verify-all` 集成

`scripts/lca-ops` 当前已有 `verify-all`,扩展为:

```python
"verify-all": [
    "scripts/check_observation_ssot.py",   # L1 + L2 + L4 lint
    "scripts/check_runtime_invariants.py", # runtime invariant
    "scripts/verify_doc_slop.py",
    # ... 其他 verify_*.py
]
```

任何一条失败 → CI fail-loud。

### 第四阶段:守门报告

`scripts/lca-ops notes-audit` 扩展为输出"4 级 lint 命中数"——agent 提交 PR 后能看到"修了哪条反模式,守门命中数从 N → N-1"。

## Decision criteria

- `scripts/check_observation_ssot.py` 9 → 13 条规则
- `scripts/check_runtime_invariants.py` 新建,≥ 3 条 invariant
- `scripts/lca-ops verify-all` 集成两个 lint 脚本
- `scripts/lca-ops notes-audit` 输出 4 级 lint 命中数
- 任何新加 EP 必须经 4 级守门(SSOT 字面 / payload dataclass / schema validation / Protocol 签名)

## Alternatives considered

### Why not 把 invariant 守门合并进 `check_observation_ssot.py`?

职责不同:`ssot.py` 是**消费方迁移到 SSOT**的守门(SSOT 字符串字面归零),invariant 是**架构正确性**的守门(`runtime_loop` 走对路径)。混在一起增加 PR diff 复杂度,审阅也难。**两个文件清楚职责**。

### Why not 只用 AST 静态检查不依赖 grep?

grep 守门是**增量**的——LCA 现状 42 处反模式,AST 检查需要完整建模(每个 emitter 都要 AST 节点模板)。grep 守门是 80% 覆盖率 + 简单,适合**L1 字面归零**;AST 守门是 100% 覆盖率,适合**L3 schema validation**(承接 note 4)。两层互补。

### Why not 在 `pyproject.toml` 用 ruff 插件实现守门?

ruff 插件需要 Python AST 插件开发,跨 LCA 现有 ruff 配置**改动面大**。本 note 用 `scripts/check_*.py` 是 LCA 现有 lint 模式(`scripts/check_notes_tree.py` / `scripts/audit_adr_health.py` 都是这个形态)。

## Acceptance criteria

- `scripts/check_observation_ssot.py` 13 条规则,0 命中
- `scripts/check_runtime_invariants.py` ≥ 3 条 invariant,0 命中
- `scripts/lca-ops verify-all` 集成两个 lint,跑通全 repo
- `scripts/lca-ops notes-audit` 输出"4 级 lint 命中数"段
- 测试:`tests/scripts/test_check_observation_ssot.py` 与 `tests/scripts/test_check_runtime_invariants.py` 新建,覆盖每条规则的"命中"与"不命中"两种 case
- CI fail-loud:任何一条命中 → PR block

## Risks

- **13 条 lint 同时跑可能慢**:每条都是 `rg` 子进程,粗算 13 × 0.5s = 6.5s。可接受——`scripts/verify-all` 已是同步流程
- **grep 守门有 false positive**:`rg 'def emit_\w+\(.*payload:\s*dict' lca/` 可能命中**合法**代码(比如 docstring 里的伪代码)。需要在每条规则上跑一次全 repo 验证 false positive 清单
- **invariant 守门不能用 grep**:Python AST 静态分析是必须的——承接 note 4 用 `ast.parse()` + `ast.NodeVisitor` 实现,确保准确

## Delete-when

- **新增 4 条 lint 的豁免清单**:若有特殊文件必须豁免(比如 SSOT 定义文件),`# noqa: observation_ssot_4` 行级豁免,`# COMPAT(delete-when: 豁免文件清空, tracking: ADR-0178-note-5)`
- **grep 守门替 AST 守门**:当 AST 守门成熟(承接 note 4 + 本 note 第四阶段),`# COMPAT(delete-when: AST 守门覆盖 grep 守门全部 case, tracking: ADR-0178-note-5)`

## Related

- [observation-convergence-root.md](../seam/2026-09-03-observation-convergence-root.md) — 根 note
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- [`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md`](../../implemented/seam/2026-09-03-observation-ssot-registry.md) — 根 note PR-2(`check_observation_ssot.py` 已建)
- [`scripts/lca-ops`](../../../../scripts/lca-ops) — `verify-all` / `notes-audit` 入口
- `scripts/check_notes_tree.py` — 现有 lint 形态参考

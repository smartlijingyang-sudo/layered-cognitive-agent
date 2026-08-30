# ADR-0096 Journal Protocol Layer — 实施追踪

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施 ADR-0096 的 Phase 1 MVA（4 PR）：把 journal 协议层（schema / identity / profile_snapshot / consumer）做成一等 seam，同时修掉 LobeHub 流式文本为空的当前生产症状。Phase 2 8 PR 仅在 §13.2 触发条件成立时启动。

**Architecture:** 沿用 ADR-0074 插件一切范式；MVA 阶段新建 4 个 seam（`journal_schemas` / `event_identities` / `profile_snapshot` / `journal_consumer`）+ 3 个 provider（`schema-v2.0.0` / `identity-stable` / `profile-snapshot-boot`）。每个 seam 独立可替换、独立测试；LobeHub 端先走最小兼容 patch，Phase 2 再切到 TS SDK 生成器完整版。

**Tech Stack:** Python 3.12 / Pydantic v2 / cordis Context / pytest；TypeScript SDK 生成器（codegen）；LobeHub patch via `deploy/lobehub/patches/runtime/`。

**Spec:** [`docs/adr/0096-journal-protocol-layer-everything-pluggable.md`](../adr/0096-journal-protocol-layer-everything-pluggable.md)（§13 MVA/Deferred 拆分；§3 七层 seam 总览；§5 链路日志契约）。

---

## 0. 关键现状调研（落地前必读）

| 现状项 | 位置 | 影响 |
|---|---|---|
| v2 envelope 部分已落地 | `lca/layer0_infra/observability/journal/journal_io.py`（`V2_SCHEMA = "lca.journal/2"`、`stamped_to_record`、`record_normalize`、`record_to_stamped`） | MVA-1 工作量缩减为：包一层 Pydantic 模型 + 增加 `schema_version` 字段 |
| `StampedEvent.event_id` 字段已存在，默认 `""` | `lca/contracts/models/observability/journal.py:133` | MVA-2 工作量：仅 `RunStore.append` 闭环填值；`StampedEvent` 不改 dataclass |
| `journal_backends` seam 已存在 | `lca/plugins/seam_definitions/observability/journal.py` | MVA-1 新建 `journal_schemas` 是**平行 seam**（不同 capability），不替换 `journal_backends` |
| `event_id` 注释说"ULID"，ADR 96 §6.3 说 `sha256(run_id, seq, type)` | `lca/contracts/models/observability/journal.py:804` vs ADR 96 §6.3 | **决策点**：MVA-2 启动时确认用 ULID（与现有注释一致）还是 sha256（与 ADR 一致）。**默认走 ULID**，理由：(1) 与既有 StampedEvent 注释一致；(2) ULID 自带时间排序，更适合事件流；(3) sha256 派生在事件未写入前无法预计算。详见 MVA-2 Task 1 |
| LobeHub `parseSseBlock` + `projectJournalFrame` 已存在 | `deploy/lobehub/patches/runtime/lcaJournal.ts` | MVA-4 工作量：先修 `parseSseBlock` v2 兼容；再引入生成 SDK；不重写已有逻辑 |
| 现有 journal 测试矩阵 | `tests/test_journal_v2_disk_format.py`、`tests/test_journal_v2_envelope.py`、`tests/test_journal_schema_fields.py`、`tests/test_journal_core.py`、`tests/test_journal_store_backend.py` | MVA 测试改造基于既有 fixture；新增契约测试用 golden envelope |

---

## 1. 状态总览

| Phase | PR | 标题 | 状态 | 起点 commit | 终点 commit | 完成日 | 阻塞 |
|:-:|:-:|---|:-:|---|---|:-:|---|
| **1** | MVA-1 | journal_schemas seam + LobeHub v2 patch | ⛔ Blocked | — | — | — | — |
| **1** | MVA-2 | event_identities seam + RunStore.append 填 event_id | ⛔ Blocked | — | — | — | MVA-1 |
| **1** | MVA-3 | profile_snapshot seam + plugin.inventory 迁移 | ⛔ Blocked | — | — | — | MVA-1 |
| **1** | MVA-4 | journal_consumer seam + TS SDK 最小版 + LobeHub 韧性模块 | ⛔ Blocked | — | — | — | MVA-2, MVA-3 |
| **2** | P2-1 | visibility policy 通用化 | ⏸ Deferred | — | — | — | 触发条件见 ADR §13.2 |
| **2** | P2-2 | transport 拆三家 | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-3 | manifest deriver 独立 provider | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-4 | ledger migrate 顶层切换 | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-5 | golden fixture 完整化 | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-6 | spec + ADR 程序文档化（完整） | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-7 | 退役旧机制 | ⏸ Deferred | — | — | — | 同上 |
| **2** | P2-8 | TS SDK 生成器完整版 | ⏸ Deferred | — | — | — | 同上 |

**Next Action**：MVA-1（journal_schemas seam）。

---

## 2. 全局约束（所有 Task 适用）

- **ADR 引用**：所有 PR 描述、commit message、PR 标题前缀写 `adr-0096:`。
- **不变量优先级**：I2（SSOT 双向落地）+ I12（ADR 程序强制）是 MVA 阶段**唯一**不可绕过约束；其余 I1/I3-I11 在各自 Task 中按需落地。
- **Seam 命名**：`<area>_schemas` / `<area>_identities` / `<area>_snapshot` / `<area>_consumer`；provider ID 用 kebab-case `lca-<role>-<impl>`。
- **测试策略**：TDD 优先；每个 seam 一个独立 `tests/test_<area>_seam.py`；golden fixture 单独 `tests/fixtures/journal_v2_minimal/`。
- **Provider boot 顺序**：seam 先 boot（提供空 registry），provider 后 boot（注入实现）；启动顺序由 `requires` 字段声明。
- **LobeHub 协同**：patch 文件在 `deploy/lobehub/patches/runtime/`；TypeScript 生成产物在 `deploy/lobehub/patches/runtime/.generated/`（git 追踪）。

---

## 3. MVA-1：journal_schemas seam + LobeHub v2 patch

### Task 1：建立 seam 骨架

**Files:**
- Create: `lca/plugins/seam_definitions/observability/journal_schema.py`
- Test: `tests/test_journal_schema_seam.py`

**Interfaces:**
- Consumes: 无（seam 是空 registry）
- Produces: `journal_schemas: NamedRegistry[str, JournalSchema]` capability

- [ ] **Step 1：写失败测试**

```python
# tests/test_journal_schema_seam.py
from lca.harness.profile.resolve import resolve_profile
from lca.harness.profile.boot import boot_resolved_profile

def test_journal_schema_seam_provides_registry(tmp_path, write_profile):
    profile = write_profile(providers=["lca-journal-schema-seam"])
    resolved = resolve_profile(profile)
    boot_resolved_profile(resolved, workdir=tmp_path)
    ctx = resolved.context
    assert ctx.has_capability("journal_schemas")
    registry = ctx.resolve("journal_schemas")
    assert registry.name() == "JournalSchemaRegistry"
```

- [ ] **Step 2：跑测试确认失败**

Run: `uv run pytest tests/test_journal_schema_seam.py -q`
Expected: `FAILED ... AttributeError: 'Profile' object has no attribute 'journal_schemas'` 或类似 cap 未声明错误。

- [ ] **Step 3：实现 seam 声明**

```python
# lca/plugins/seam_definitions/observability/journal_schema.py
"""JournalSchema seam plugin (Tier-1) —— ADR-0096 MVA-1.

声明 ``journal_schemas`` 注册中心；boot 后 ``providers/journal_schema/v2``
注入 ``EnvelopeV2`` 实现。新增 schema 版本 = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-schema-seam",
    provides=["journal_schemas"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the journal_schemas registry (ADR-0096 MVA-1).",
    test_suite="tests/test_journal_schema_seam.py::test_journal_schema_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry
    from lca.contracts.observability.schemas import JournalSchemaRegistry
    ctx.provide("journal_schemas", JournalSchemaRegistry())
```

- [ ] **Step 4：跑测试确认通过**

Run: `uv run pytest tests/test_journal_schema_seam.py -q`
Expected: PASS

- [ ] **Step 5：Commit**

```bash
git add lca/plugins/seam_definitions/observability/journal_schema.py tests/test_journal_schema_seam.py
git commit -m "feat(adr-0096-mva-1): journal_schemas seam registry"
```

---

### Task 2：EnvelopeV2 Pydantic 模型 + JournalSchema Protocol

**Files:**
- Create: `lca/contracts/observability/schemas/__init__.py`
- Create: `lca/contracts/observability/schemas/v2.py`
- Create: `lca/contracts/observability/schemas/migrate.py`
- Test: `tests/test_journal_schema_v2.py`
- Test: `tests/test_journal_schema_migrate.py`

**Interfaces:**
- Consumes: 现有 `StampedEvent` / `JournalRecord`
- Produces:
  - `JournalSchema` Protocol: `version: str`, `serialize(record: JournalRecord) -> dict[str, Any]`, `deserialize(data: dict[str, Any]) -> JournalRecord`
  - `EnvelopeV2` Pydantic model: 覆盖 `JournalRecord` 字段
  - `migrate_v1_to_v2(data: dict) -> dict`

- [ ] **Step 1：写失败测试**

```python
# tests/test_journal_schema_v2.py
import pytest
from pydantic import ValidationError
from lca.contracts.observability.schemas.v2 import EnvelopeV2

def test_envelope_schema_version_required():
    data = {
        "schema_version": "v2.0.0",
        "event_id": "abc",
        "trace_id": "t", "run_id": "r", "run_seq": 1, "plan_ref": "",
        "occurred_at": 0.0,
        "descriptor": {"type": "TestEvent", "domain": "event", "audience": "domain"},
        "payload": {}, "scope": {}, "causation": {},
    }
    env = EnvelopeV2.model_validate(data)
    assert env.schema_version == "v2.0.0"

def test_envelope_missing_schema_version_rejected():
    data = {"event_id": "abc", "trace_id": "t", "run_id": "r", "run_seq": 1}
    with pytest.raises(ValidationError):
        EnvelopeV2.model_validate(data)
```

- [ ] **Step 2：跑测试确认失败**

Run: `uv run pytest tests/test_journal_schema_v2.py -q`
Expected: `FAILED ... ModuleNotFoundError: No module named 'lca.contracts.observability.schemas.v2'`

- [ ] **Step 3：实现 EnvelopeV2 + JournalSchema Protocol**

```python
# lca/contracts/observability/schemas/__init__.py
"""Journal envelope schemas —— ADR-0096 MVA-1."""

from .v2 import EnvelopeV2, JournalSchema  # noqa: F401
from .migrate import migrate_v1_to_v2  # noqa: F401
```

```python
# lca/contracts/observability/schemas/v2.py
"""EnvelopeV2 + JournalSchema Protocol —— ADR-0096 §5.1.

EnvelopeV2 = ``lca.journal/2`` envelope 的 Pydantic v2 表示,
所有字段显式类型化,``schema_version`` 必填(I2 不变量)。
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.observability.journal import JournalRecord

SCHEMA_VERSION = "v2.0.0"


class EnvelopeV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCHEMA_VERSION]
    event_id: str
    trace_id: str
    run_id: str
    run_seq: int
    plan_ref: str = ""
    occurred_at: float
    descriptor: dict[str, Any]
    payload: dict[str, Any]  # ADR §5.1: 字段名从 data → payload
    scope: dict[str, Any] = {}
    causation: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []


class JournalSchema(Protocol):
    """Seam contract: 一个 envelope schema 实现。"""

    version: str

    def serialize(self, record: JournalRecord) -> dict[str, Any]: ...

    def deserialize(self, data: dict[str, Any]) -> JournalRecord: ...
```

- [ ] **Step 4：跑测试确认通过**

Run: `uv run pytest tests/test_journal_schema_v2.py -q`
Expected: PASS

- [ ] **Step 5：写 v1→v2 migrate 测试 + 实现**

```python
# tests/test_journal_schema_migrate.py
from lca.contracts.observability.schemas.migrate import migrate_v1_to_v2

def test_v1_data_field_becomes_payload():
    v1 = {"schema": "lca.journal/1", "event": {"foo": "bar"}, "seq": 1}
    v2 = migrate_v1_to_v2(v1)
    assert v2["schema_version"] == "v2.0.0"
    assert v2["payload"] == {"foo": "bar"}
    assert "event" not in v2

def test_migrate_idempotent():
    v1 = {"schema": "lca.journal/1", "event": {"x": 1}, "seq": 2}
    v2 = migrate_v1_to_v2(v1)
    assert migrate_v1_to_v2(v2) == v2
```

```python
# lca/contracts/observability/schemas/migrate.py
"""v1 → v2 envelope 迁移(ADR-0096 §5.1)。

字段映射:
- ``schema: lca.journal/1`` → ``schema_version: v2.0.0``
- ``event: {...}`` → ``payload: {...}``
- ``seq`` 保留(主键)
"""

from __future__ import annotations

from typing import Any


def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") == "v2.0.0":
        return data  # idempotent
    if "event" in data:
        out = dict(data)
        out["payload"] = out.pop("event")
        out["schema_version"] = "v2.0.0"
        return out
    return data
```

- [ ] **Step 6：跑 migrate 测试确认通过**

Run: `uv run pytest tests/test_journal_schema_migrate.py -q`
Expected: PASS

- [ ] **Step 7：Commit**

```bash
git add lca/contracts/observability/schemas/ tests/test_journal_schema_v2.py tests/test_journal_schema_migrate.py
git commit -m "feat(adr-0096-mva-1): EnvelopeV2 Pydantic model + v1→v2 migration"
```

---

### Task 3：schema-v2.0.0 provider + 改造 journal_io.py

**Files:**
- Create: `lca/plugins/providers/journal_schema/__init__.py`
- Create: `lca/plugins/providers/journal_schema/v2.py`
- Modify: `lca/layer0_infra/observability/journal/journal_io.py`（`stamped_to_record` / `record_normalize` 调用 EnvelopeV2 校验）
- Test: `tests/test_journal_schema_provider.py`

**Interfaces:**
- Consumes: `journal_schemas` registry
- Produces: 注册 `{"v2.0.0": EnvelopeV2Schema()}` 到 registry

- [ ] **Step 1：写失败测试**

```python
# tests/test_journal_schema_provider.py
def test_v2_provider_serializes_to_envelope():
    from lca.contracts.models.observability.journal import JournalRecord, RunScope
    from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema

    record = JournalRecord(
        event_id="abc", schema="lca.journal/2", trace_id="t", run_id="r",
        run_seq=1, plan_ref="", scope=RunScope(trace_id="t", run_id="r"),
        data={"foo": "bar"}, payload_schema_version=1,
        type="StepTextDelta", ts=0.0, causation=None,
    )
    schema = EnvelopeV2Schema()
    env = schema.serialize(record)
    assert env["schema_version"] == "v2.0.0"
    assert env["payload"] == {"foo": "bar"}
```

- [ ] **Step 2：跑测试确认失败**

Run: `uv run pytest tests/test_journal_schema_provider.py -q`
Expected: FAILED（provider 不存在）

- [ ] **Step 3：实现 provider**

```python
# lca/plugins/providers/journal_schema/__init__.py
```

```python
# lca/plugins/providers/journal_schema/v2.py
"""schema-v2.0.0 provider —— ADR-0096 MVA-1.

把 ``JournalRecord`` 序列化为 ``EnvelopeV2`` (Pydantic v2 校验)。
字段名 ``data`` → ``payload``;``schema: lca.journal/2`` → ``schema_version: v2.0.0``。
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import JournalRecord
from lca.contracts.observability.schemas.v2 import SCHEMA_VERSION


class EnvelopeV2Schema:
    version = SCHEMA_VERSION

    def serialize(self, record: JournalRecord) -> dict[str, str | int | float | dict]:
        return {
            "schema_version": self.version,
            "event_id": record.event_id,
            "trace_id": record.trace_id,
            "run_id": record.run_id,
            "run_seq": record.run_seq,
            "plan_ref": record.plan_ref,
            "occurred_at": record.ts,
            "descriptor": {"type": record.type},
            "payload": record.data,
            "scope": {
                "trace_id": record.scope.trace_id,
                "run_id": record.scope.run_id,
                "parent_run_id": record.scope.parent_run_id,
                "agent_role": record.scope.agent_role,
            },
            "causation": (
                {"parent_event_id": record.causation.parent_event_id}
                if record.causation else {}
            ),
        }

    def deserialize(self, data: dict) -> JournalRecord:
        from lca.contracts.observability.schemas.migrate import migrate_v1_to_v2
        from lca.contracts.observability.schemas.v2 import EnvelopeV2
        normalized = migrate_v1_to_v2(data)
        env = EnvelopeV2.model_validate(normalized)
        # 重建 JournalRecord (复用 record_to_stamped 上半部逻辑)
        ...
```

> 注：`deserialize` 内部调用 `record_to_stamped`（journal_io.py 已实现），此处省略完整代码避免重复 ADR-0065 既有逻辑。

- [ ] **Step 4：跑测试确认通过**

Run: `uv run pytest tests/test_journal_schema_provider.py -q`
Expected: PASS

- [ ] **Step 5：改造 journal_io.py 让 stamped_to_record 走 EnvelopeV2Schema**

修改 `lca/layer0_infra/observability/journal/journal_io.py:stamped_to_record`：

```python
# 在文件顶部加
from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema
_DEFAULT_SCHEMA = EnvelopeV2Schema()

# stamped_to_record 末尾替换 record 构造为:
env_dict = _DEFAULT_SCHEMA.serialize(record)
return env_dict  # 而不是 dataclasses 重建
```

> 兼容性：保留旧 `stamped_to_record` 签名，但内部返回 dict；`record_to_stamped` 走逆路径。

- [ ] **Step 6：跑既有 journal 测试确认不破**

Run: `uv run pytest tests/test_journal_v2_disk_format.py tests/test_journal_v2_envelope.py tests/test_journal_schema_fields.py tests/test_journal_core.py -q`
Expected: PASS（不允许回归既有 v2 行为）

- [ ] **Step 7：Commit**

```bash
git add lca/plugins/providers/journal_schema/ lca/layer0_infra/observability/journal/journal_io.py tests/test_journal_schema_provider.py
git commit -m "feat(adr-0096-mva-1): schema-v2.0.0 provider + journal_io integration"
```

---

### Task 4：CI gate `check_protocol_schema_version.py`

**Files:**
- Create: `scripts/check_protocol_schema_version.py`
- Modify: `pyproject.toml`（lint 链加入此脚本）
- Modify: `.github/workflows/ci.yml`（如存在 CI 工作流）

**Interfaces:**
- 扫描 `lca/layer0_infra/observability/` 所有 .py 文件
- 拦截：(a) `JournalRecord.data` 字段写入；(b) envelope dict 缺 `schema_version`；(c) envelope dict 含 `data.data` 嵌套

- [ ] **Step 1：写失败测试**

```python
# scripts/check_protocol_schema_version.py
#!/usr/bin/env python3
"""CI gate: 拦截 envelope 字段名漂移(ADR-0096 §I2 + §6 实施序列 PR-0 gate)。"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

ROOT = Path("lca/layer0_infra/observability")


def find_data_field_writes(tree: ast.Module) -> list[tuple[str, int]]:
    """检测 .data = ... 或 dataclasses.replace(record, data=...) 模式."""
    findings: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "data":
                    findings.append(("write_to_data_field", node.lineno))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "data" and "dataclasses" in ast.unparse(node.func):
                    findings.append(("dataclasses_replace_data_kwarg", node.lineno))
    return findings


def main() -> int:
    bad = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for kind, line in find_data_field_writes(tree):
            bad.append(f"{path}:{line}: {kind}")
    if bad:
        print("FAIL: envelope field name drift detected (ADR-0096 §I2)")
        for b in bad:
            print(f"  {b}")
        return 1
    print("PASS: no envelope field drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2：跑脚本确认（预期先暴露既有 .data 写入）**

Run: `uv run python scripts/check_protocol_schema_version.py`
Expected: 暴露多个现有 `.data =` 写入（journal_io.py 等）。先记录但**允许豁免**直到 journal_io.py 改造完成。

- [ ] **Step 3：豁免机制（先行标注，Task 3 完成后移除）**

```python
# 在脚本顶部加
ALLOWLIST = {
    "lca/layer0_infra/observability/journal/journal_io.py",  # MVA-1 Task 3 完成
}
def main() -> int:
    bad = []
    for path in ROOT.rglob("*.py"):
        if str(path) in ALLOWLIST:
            continue
        ...
```

- [ ] **Step 4：跑脚本确认通过**

Run: `uv run python scripts/check_protocol_schema_version.py`
Expected: `PASS: no envelope field drift`（journal_io.py 豁免）

- [ ] **Step 5：journal_io.py Task 3 完成后,移除豁免并跑**

Run: `uv run python scripts/check_protocol_schema_version.py`
Expected: PASS（journal_io.py 已改造）

- [ ] **Step 6：加入 lint 链**

修改 `pyproject.toml`：

```toml
[tool.lca.lint-checks]
checks = [
    ...,
    "scripts/check_protocol_schema_version.py",
]
```

Run: `uv run python scripts/check_protocol_schema_version.py`
Expected: PASS

- [ ] **Step 7：Commit**

```bash
git add scripts/check_protocol_schema_version.py pyproject.toml
git commit -m "feat(adr-0096-mva-1): CI gate for envelope schema_version"
```

---

### Task 5：LobeHub v2 兼容 patch（修生产症状）

**Files:**
- Modify: `deploy/lobehub/patches/runtime/lcaJournal.ts`（`parseSseBlock` 优先读 `payload` 字段，回退 `data`）
- Test: 手动验证（部署到 LobeHub dev 实例后跑 run_302c22421883 同等对话）

**Interfaces:**
- Consumes: SSE 帧（`event` / `data` JSON）
- Produces: `JournalFrame` 含 `eventPayload: payload | data`

- [ ] **Step 1：定位 parseSseBlock 当前实现**

```bash
grep -n "parseSseBlock\|eventPayload\|payload\|data\.data" deploy/lobehub/patches/runtime/lcaJournal.ts
```

- [ ] **Step 2：改造 parseSseBlock 优先读 payload**

```typescript
// deploy/lobehub/patches/runtime/lcaJournal.ts (修改 parseSseBlock)
export function parseSseBlock(block: string): JournalFrame[] {
  // ... 既有解析 ...
  // ADR-0096 MVA-1: envelope 顶层字段从 data → payload (v2.0.0)
  // 兼容旧 v2 (lca.journal/2 字段 data)
  const payload = (parsed.payload ?? parsed.data) as Record<string, unknown> | undefined;
  // ... 用 payload 替换原 parsed.data ...
}
```

- [ ] **Step 3：手动验证生产症状**

```bash
# 在 lobehub-ui 仓跑 unit test (如存在)
pnpm run typecheck
pnpm run test:journal  # 如有

# 部署到 LobeHub dev 实例,跑一次对话,确认流式文本显示
```

- [ ] **Step 4：Commit patch**

```bash
git add deploy/lobehub/patches/runtime/lcaJournal.ts
git commit -m "fix(lobehub): parseSseBlock v2.0.0 envelope payload compatibility (ADR-0096 MVA-1)"
```

---

### Task 6：golden fixture + 契约测试最小版

**Files:**
- Create: `tests/fixtures/journal_v2_minimal/run_001.jsonl`（5 帧 envelope v2.0.0）
- Create: `tests/fixtures/journal_v2_minimal/expected_projection.json`
- Create: `tests/test_sse_projection_contract.py`

- [ ] **Step 1：手写 5 帧 fixture**

```jsonl
{"schema_version":"v2.0.0","event_id":"e1","trace_id":"t1","run_id":"r1","run_seq":1,"plan_ref":"","occurred_at":0.0,"descriptor":{"type":"AgentRunStarted","domain":"run","audience":"domain"},"payload":{"agent_role":"Alice"},"scope":{"trace_id":"t1","run_id":"r1","agent_role":"Alice"},"causation":{},"evidence":[]}
{"schema_version":"v2.0.0","event_id":"e2","trace_id":"t1","run_id":"r1","run_seq":2,"plan_ref":"","occurred_at":0.1,"descriptor":{"type":"StepTextDelta","domain":"event","audience":"domain","channel":"answer"},"payload":{"text_delta":"你好"},"scope":{"trace_id":"t1","run_id":"r1","agent_role":"Alice"},"causation":{"parent_event_id":"e1"},"evidence":[]}
{"schema_version":"v2.0.0","event_id":"e3","trace_id":"t1","run_id":"r1","run_seq":3,"plan_ref":"","occurred_at":0.2,"descriptor":{"type":"ReasoningDelta","domain":"event","audience":"domain","channel":"reasoning"},"payload":{"text_delta":"think"},"scope":{"trace_id":"t1","run_id":"r1","agent_role":"Alice"},"causation":{"parent_event_id":"e1"},"evidence":[]}
{"schema_version":"v2.0.0","event_id":"e4","trace_id":"t1","run_id":"r1","run_seq":4,"plan_ref":"","occurred_at":1.0,"descriptor":{"type":"AgentRunFinished","domain":"run","audience":"domain"},"payload":{},"scope":{"trace_id":"t1","run_id":"r1","agent_role":"Alice"},"causation":{"parent_event_id":"e1"},"evidence":[]}
```

- [ ] **Step 2：写期望投影**

```json
[
  {"kind":"open-turn","speaker":"Alice"},
  {"kind":"text","text":"你好"},
  {"kind":"reasoning","text":"think"},
  {"kind":"run-finished"}
]
```

- [ ] **Step 3：写契约测试**

```python
# tests/test_sse_projection_contract.py
import json
from pathlib import Path
from lca.contracts.observability.consumer_contract import ConsumerContract  # MVA-4 引入

FIXTURE = Path("tests/fixtures/journal_v2_minimal/run_001.jsonl")
EXPECTED = Path("tests/fixtures/journal_v2_minimal/expected_projection.json")


def test_golden_fixture_projects_to_expected(tmp_path):
    contract = ConsumerContract.load("lobehub-v2.0.0")  # placeholder
    frames = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
    projected = [contract.project(frame) for frame in frames]
    expected = json.loads(EXPECTED.read_text())
    # MVA-1 阶段契约测试仅断言 envelope 解析正确,project 由 MVA-4 完成
    assert all(f["schema_version"] == "v2.0.0" for f in frames)
    assert len(projected) == len(expected)  # 占位断言
```

- [ ] **Step 4：跑契约测试确认通过（envelope 解析部分）**

Run: `uv run pytest tests/test_sse_projection_contract.py -q`
Expected: PASS（MVA-1 阶段；MVA-4 完成后断言完整投影）

- [ ] **Step 5：Commit**

```bash
git add tests/fixtures/journal_v2_minimal/ tests/test_sse_projection_contract.py
git commit -m "test(adr-0096-mva-1): minimal golden fixture + projection contract"
```

---

### MVA-1 完成判定

下列全部通过 = MVA-1 Done：

```bash
uv run pytest tests/test_journal_schema_seam.py tests/test_journal_schema_v2.py tests/test_journal_schema_migrate.py tests/test_journal_schema_provider.py tests/test_sse_projection_contract.py tests/test_journal_v2_disk_format.py tests/test_journal_v2_envelope.py tests/test_journal_schema_fields.py tests/test_journal_core.py -q
uv run python scripts/check_protocol_schema_version.py
uv run ruff check --fix lca/contracts/observability/schemas/ lca/plugins/seam_definitions/observability/journal_schema.py lca/plugins/providers/journal_schema/
uv run ruff format lca/contracts/observability/schemas/ lca/plugins/seam_definitions/observability/journal_schema.py lca/plugins/providers/journal_schema/
```

对应 ADR-0096 §13.4 验收条目：**V1, V2, V3** 通过。

---

## 4. MVA-2：event_identities seam + RunStore.append 闭环填 event_id

### Task 1：决策 event_id 派生策略（ULID vs sha256）

> **决策点**：ADR §6.3 提议 `sha256(run_id, seq, event_type)`，但 `lca/contracts/models/observability/journal.py:804` 注释说 "event_id 全局唯一(ULID)"。两条路径都满足 ADR §I3（构造时闭环派生，不接 float ts），但派生函数形态不同。

**决策矩阵**：

| 方案 | 优势 | 劣势 | 一致性 |
|---|---|---|---|
| **ULID**（与既有注释一致） | 自带时间排序；与既有 StampedEvent 注释一致；事件流按 event_id 排序天然有序 | 需要 `ulid-py` 依赖；时间戳虽不直接用 ts 但隐含 ms 级时间 | ✅ 与 `journal.py:804` 注释一致 |
| **sha256(run_id, seq, event_type)**（与 ADR 一致） | 无第三方依赖；确定性更强（同样的三个输入永远产出同样 hash） | 跨进程不可预计算（必须先 append）；失去时间排序能力 | ✅ 与 ADR §6.3 一致 |

**默认决策**：走 **ULID**。理由：(a) 与既有代码注释一致；(b) 与 ADR 96 §I3（不接 float ts）兼容 —— ULID 用 monotonic time 而非 run 时 ts；(c) 事件流按 ULID 排序天然有序，对审计/重建有利。

**Files:**
- Create: `docs/adr/0097-event-identity-derivation.md`（新 ADR，记录此决策与依据）
- Modify: 本 tracker §"0. 关键现状调研" 表格，把决策写明

- [ ] **Step 1：起草 ADR-0097**

```markdown
# ADR-0097：Event Identity 派生策略 —— ULID（与 ADR-0065 注释一致）

## 状态
**Accepted — 2026-08-28**

## 背景
ADR-0096 MVA-2 要求 RunStore.append 闭环填 event_id，且派生函数不接 float ts。
ADR-0096 §6.3 提议 sha256(run_id, seq, event_type)；但 lca/contracts/models/observability/journal.py:804
注释声明 event_id 是 ULID。两条路径都满足 ADR-0096 I3。

## 决策
event_id 用 ULID（26 字符 Crockford Base32）派生。

| 方案 | 否决原因 |
|---|---|
| sha256(run_id, seq, event_type) | 与既有注释不一致；失去时间排序；不可预计算 |
| UUIDv4 | 无序；浪费排序能力 |
| UUIDv7 | 与 ULID 等价但不如 ULID 紧凑 |
```

- [ ] **Step 2：跑 ADR lint**

Run: `uv run python scripts/verify_doc_budgets.py`
Expected: PASS

- [ ] **Step 3：Commit ADR**

```bash
git add docs/adr/0097-event-identity-derivation.md docs/plans/adr-0096-implementation-tracker.md
git commit -m "docs(adr-0097): event identity derivation via ULID"
```

---

### Task 2：event_identities seam

**Files:**
- Create: `lca/plugins/seam_definitions/observability/event_identity.py`
- Test: `tests/test_event_identity_seam.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_event_identity_seam.py
from lca.harness.profile.resolve import resolve_profile
from lca.harness.profile.boot import boot_resolved_profile

def test_event_identity_seam_provides_registry(tmp_path, write_profile):
    profile = write_profile(providers=["lca-event-identity-seam"])
    resolved = resolve_profile(profile)
    boot_resolved_profile(resolved, workdir=tmp_path)
    ctx = resolved.context
    assert ctx.has_capability("event_identities")
```

- [ ] **Step 2-5：实现 seam + 测试 + commit**

按 MVA-1 Task 1 同模式（seam declaration + 空 registry + 测试通过 + commit）。

```bash
git commit -m "feat(adr-0096-mva-2): event_identities seam registry"
```

---

### Task 3：identity-stable provider 实现 ULID 派生

**Files:**
- Create: `lca/plugins/providers/event_identity/__init__.py`
- Create: `lca/plugins/providers/event_identity/stable_ulid.py`
- Modify: `pyproject.toml`（增加 `ulid-py` 依赖）
- Test: `tests/test_event_identity_stable_ulid.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_event_identity_stable_ulid.py
import re
from lca.plugins.providers.event_identity.stable_ulid import StableUlidIdentity

def test_derive_returns_ulid():
    identity = StableUlidIdentity()
    eid = identity.derive(run_id="r1", seq=1, event_type="StepTextDelta")
    assert re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", eid), f"not ULID: {eid}"

def test_derive_distinct_for_distinct_inputs():
    identity = StableUlidIdentity()
    e1 = identity.derive(run_id="r1", seq=1, event_type="A")
    e2 = identity.derive(run_id="r1", seq=2, event_type="A")
    e3 = identity.derive(run_id="r1", seq=1, event_type="B")
    assert len({e1, e2, e3}) == 3

def test_derive_uses_monotonic_time_not_ts():
    """I3: 派生不接 float ts;用 monotonic ms time"""
    identity = StableUlidIdentity()
    # 不传 ts 参数 — 接口签名应只接受 run_id / seq / event_type
    import inspect
    sig = inspect.signature(identity.derive)
    assert "ts" not in sig.parameters
    assert "occurred_at" not in sig.parameters
```

- [ ] **Step 2-7：实现 provider + 测试通过 + commit**

```python
# lca/plugins/providers/event_identity/stable_ulid.py
"""event identity via ULID —— ADR-0097 + ADR-0096 MVA-2.

每个 append 调用 ``derive(run_id, seq, event_type)`` 产一个 ULID。
ULID 自带 ms 级时间戳(I3 不变量:不接 float ts),与 seq/event_type 一并
保证全局唯一 + 时间排序。
"""

from __future__ import annotations

from ulid import ULID


class StableUlidIdentity:
    """I3 + ADR-0097: event_id 派生 = ULID(ms monotonic time + random)。"""

    def derive(self, *, run_id: str, seq: int, event_type: str) -> str:
        # ULID 仅依赖调用时刻的 monotonic time;不接调用方传入的 ts
        return str(ULID())
```

```bash
git commit -m "feat(adr-0096-mva-2): identity-stable-ulid provider"
```

---

### Task 4：RunStore.append 闭环填 event_id

**Files:**
- Modify: `lca/layer0_infra/observability/journal/engine.py:RunStore.append`（调用 identity provider）
- Modify: `lca/layer0_infra/observability/journal/engine.py:RunStore.seal`（同步填 terminal event_id）
- Modify: `lca/layer0_infra/observability/journal/journal_io.py:_derive_event_id`（删除 fallback 分支）
- Test: `tests/test_event_identity_integration.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_event_identity_integration.py
from lca.contracts.models.observability.journal import AgentRunStarted, RunScope
from lca.infrastructure.observability.journal.engine import RunStore

def test_runstore_append_fills_event_id():
    store = RunStore(run_id="r1")
    event = AgentRunStarted(scope=RunScope(trace_id="t", run_id="r1", agent_role="A"))
    stamped = store.append(event)
    assert stamped.event_id != ""
    assert len(stamped.event_id) == 26  # ULID

def test_runstore_seal_terminal_event_has_event_id():
    store = RunStore(run_id="r1")
    store.append(AgentRunStarted(scope=RunScope(trace_id="t", run_id="r1")))
    sealed = store.seal()
    assert sealed is not None
    assert sealed.event_id != ""
```

- [ ] **Step 2：跑测试确认失败**

Run: `uv run pytest tests/test_event_identity_integration.py -q`
Expected: FAILED（event_id 为空字符串）

- [ ] **Step 3：改造 RunStore.append**

修改 `lca/layer0_infra/observability/journal/engine.py:RunStore.append`：

```python
# 在 __init__ 末尾加:
self._identity_provider: EventIdentityProvider = (
    identity_provider if identity_provider is not None
    else _default_identity_provider()
)

# append 方法签名加 identity_provider 参数;在构造 StampedEvent 前:
event_id = self._identity_provider.derive(
    run_id=self._run_id, seq=run_seq, event_type=type(event).__name__,
)
stamped = StampedEvent(seq=run_seq, ts=ts, scope=scope, event=event, event_id=event_id)
```

- [ ] **Step 4：RunStore.seal 同步填 terminal event_id**

```python
# seal 方法内构造 StampedEvent 前调用同一 derive
```

- [ ] **Step 5：删除 journal_io.py _derive_event_id fallback**

```python
# lca/layer0_infra/observability/journal/journal_io.py
# 删除 _derive_event_id 整个函数;record_normalize 不再做 event_id 重派生
# 改为: 直接使用 record.event_id (RunStore.append 已填)
```

- [ ] **Step 6：跑既有 journal 测试确认不破**

Run: `uv run pytest tests/test_journal_v2_disk_format.py tests/test_journal_v2_envelope.py tests/test_journal_core.py tests/test_journal_console.py -q`
Expected: PASS

- [ ] **Step 7：跑新测试确认通过**

Run: `uv run pytest tests/test_event_identity_integration.py -q`
Expected: PASS

- [ ] **Step 8：跑 CI gate（journal_io.py 改造后,豁免应可移除）**

Run: `uv run python scripts/check_protocol_schema_version.py`
Expected: PASS

- [ ] **Step 9：Commit**

```bash
git add lca/layer0_infra/observability/journal/engine.py lca/layer0_infra/observability/journal/journal_io.py tests/test_event_identity_integration.py
git commit -m "feat(adr-0096-mva-2): RunStore.append closes event_id loop"
```

---

### Task 5：RunManifest.terminal_event_id → terminal_event_seq

**Files:**
- Modify: `lca/contracts/observability/run_manifest.py`（`terminal_event_id: str` → `terminal_event_seq: int`）
- Modify: `gateway/runs/terminalizer.py:_terminal_event_id_for` → `_terminal_event_seq_for`（从 journal 倒序扫第一条 terminal type，取其 seq）
- Test: `tests/test_run_manifest_terminal_seq.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_run_manifest_terminal_seq.py
from lca.contracts.observability.run_manifest import RunManifest

def test_run_manifest_has_terminal_event_seq_not_id():
    manifest = RunManifest(run_id="r1", terminal_event_seq=5)
    assert manifest.terminal_event_seq == 5
    assert not hasattr(manifest, "terminal_event_id")
```

- [ ] **Step 2-7：改造 RunManifest + terminalizer + 测试通过**

```bash
git commit -m "refactor(adr-0096-mva-2): RunManifest.terminal_event_seq replaces terminal_event_id"
```

---

### MVA-2 完成判定

```bash
uv run pytest tests/test_event_identity_seam.py tests/test_event_identity_stable_ulid.py tests/test_event_identity_integration.py tests/test_run_manifest_terminal_seq.py tests/test_journal_v2_disk_format.py tests/test_journal_v2_envelope.py tests/test_journal_core.py -q
uv run python scripts/check_protocol_schema_version.py
uv run ruff check --fix lca/layer0_infra/observability/journal/ lca/plugins/seam_definitions/observability/event_identity.py lca/plugins/providers/event_identity/
```

对应 ADR-0096 §13.4 验收条目：**V4, V5, V6** 通过。

---

## 5. MVA-3：profile_snapshot seam + plugin.inventory 迁移

### Task 1：profile_snapshot seam

**Files:**
- Create: `lca/plugins/seam_definitions/observability/profile_snapshot.py`
- Test: `tests/test_profile_snapshot_seam.py`

按 MVA-1 Task 1 / MVA-2 Task 2 同模式。

```bash
git commit -m "feat(adr-0096-mva-3): profile_snapshot seam registry"
```

---

### Task 2：profile-snapshot-boot provider

**Files:**
- Create: `lca/plugins/providers/profile_snapshot/__init__.py`
- Create: `lca/plugins/providers/profile_snapshot/run_boot.py`
- Test: `tests/test_profile_snapshot_run_boot.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_profile_snapshot_run_boot.py
import json
from pathlib import Path

def test_run_boot_writes_snapshot(tmp_path):
    from lca.plugins.providers.profile_snapshot.run_boot import RunBootSnapshot

    snapshot = RunBootSnapshot()
    snapshot.write(
        run_id="r1",
        outdir=tmp_path,
        plan_ref="plan-hash-abc",
        plugins=["lca-llm", "lca-tools", "lca-journal-schema-v2"],
        capabilities={"llm": True, "tools": True, "journal_schemas": True},
        control_plan={"version": "v3", "phases": [...]},
    )
    snapshot_path = tmp_path / "profile_snapshot.json"
    assert snapshot_path.exists()
    data = json.loads(snapshot_path.read_text())
    assert data["run_id"] == "r1"
    assert "lca-journal-schema-v2" in data["plugins"]
```

- [ ] **Step 2-7：实现 + 测试 + commit**

```python
# lca/plugins/providers/profile_snapshot/run_boot.py
"""profile-snapshot-boot provider —— ADR-0096 MVA-3.

boot 期一次性写 traces/runs/<id>/profile_snapshot.json;plugin.inventory
RuntimeObserved 不再写 journal,而是消费 snapshot。
"""

from __future__ import annotations

import json
from pathlib import Path


class RunBootSnapshot:
    def write(
        self,
        *,
        run_id: str,
        outdir: Path,
        plan_ref: str,
        plugins: list[str],
        capabilities: dict[str, bool],
        control_plan: dict,
    ) -> Path:
        path = outdir / "profile_snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "run_id": run_id,
            "plan_ref": plan_ref,
            "plugins": plugins,
            "capabilities": capabilities,
            "control_plan": control_plan,
        }, indent=2))
        return path
```

```bash
git commit -m "feat(adr-0096-mva-3): profile-snapshot-boot provider"
```

---

### Task 3：RuntimeObserved plugin.inventory 不再写 journal

**Files:**
- Modify: `lca/plugins/seam_definitions/observability/journal.py`（RuntimeObserved kind=plugin(operation=plugin.inventory) 检查并 skip）
- Test: `tests/test_no_plugin_inventory_in_journal.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_no_plugin_inventory_in_journal.py
from lca.contracts.models.observability.journal import RuntimeObserved, RunScope

def test_plugin_inventory_event_not_appended_to_journal():
    from lca.infrastructure.observability.journal.engine import RunStore
    store = RunStore(run_id="r1")
    event = RuntimeObserved(
        scope=RunScope(trace_id="t", run_id="r1"),
        kind="plugin", operation="plugin.inventory",
        payload={"plugins": ["a", "b", "c"]},
    )
    stamped = store.append(event)
    # MVA-3: append 返回 None 或 skip,不入 ledger
    assert stamped is None
    assert store.run_seq == 0  # 没增
```

- [ ] **Step 2-5：实现 + 测试 + commit**

修改 `RunStore.append`：在 `RuntimeObserved` + `operation == "plugin.inventory"` 分支返回 `None` 不入 ledger。

```bash
git commit -m "refactor(adr-0096-mva-3): plugin.inventory exits journal stream"
```

---

### Task 4：/runs/{id}/profile endpoint

**Files:**
- Modify: `gateway/runs/api.py`（新增 GET 端点读 snapshot）
- Test: `tests/test_runs_profile_endpoint.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_runs_profile_endpoint.py
from fastapi.testclient import TestClient

def test_get_profile_returns_snapshot(client: TestClient, tmp_path):
    snapshot = tmp_path / "profile_snapshot.json"
    snapshot.write_text('{"run_id":"r1","plugins":["x"]}')
    resp = client.get("/lca-api/runs/r1/profile")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "r1"
```

- [ ] **Step 2-7：实现 + commit**

```bash
git commit -m "feat(adr-0096-mva-3): GET /runs/{id}/profile endpoint"
```

---

### MVA-3 完成判定

```bash
uv run pytest tests/test_profile_snapshot_seam.py tests/test_profile_snapshot_run_boot.py tests/test_no_plugin_inventory_in_journal.py tests/test_runs_profile_endpoint.py -q
uv run ruff check --fix lca/plugins/seam_definitions/observability/profile_snapshot.py lca/plugins/providers/profile_snapshot/ gateway/runs/api.py
```

对应 ADR-0096 §13.4 验收条目：**V18** 通过（plugin.inventory 不再出现）。

---

## 6. MVA-4：journal_consumer seam + TS SDK 最小版 + LobeHub 韧性

### Task 1：ConsumerContract Protocol

**Files:**
- Create: `lca/contracts/observability/consumer_contract.py`
- Test: `tests/test_consumer_contract_protocol.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_consumer_contract_protocol.py
from typing import Any
from lca.contracts.observability.consumer_contract import ConsumerContract


def test_protocol_shape():
    class Stub:
        name = "stub"
        schema_version = "v2.0.0"
        def project(self, envelope: dict[str, Any]) -> dict[str, Any]:
            return {"kind": "ignore"}
    stub = Stub()
    assert isinstance(stub, ConsumerContract)
```

- [ ] **Step 2-7：实现 Protocol + commit**

```python
# lca/contracts/observability/consumer_contract.py
"""ConsumerContract Protocol —— ADR-0096 §L6 + MVA-4.

一个 consumer contract = (name, schema_version, project(envelope) -> Projected)。
版本号必须与 envelope schema_version 配套(I6 不变量)。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConsumerContract(Protocol):
    name: str
    schema_version: str

    def project(self, envelope: dict[str, Any]) -> dict[str, Any]: ...
```

```bash
git commit -m "feat(adr-0096-mva-4): ConsumerContract Protocol"
```

---

### Task 2：journal_consumer seam + consumer-lobehub provider（spec only）

**Files:**
- Create: `lca/plugins/seam_definitions/observability/journal_consumer.py`
- Create: `lca/plugins/providers/journal_consumer/__init__.py`
- Create: `lca/plugins/providers/journal_consumer/lobehub_contract.py`（**spec 部分，不含前端实现**）
- Create: `lca/plugins/providers/journal_consumer/cli.py`
- Test: `tests/test_journal_consumer_providers.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_journal_consumer_providers.py
from lca.plugins.providers.journal_consumer.lobehub_contract import LobehubConsumerContract
from lca.plugins.providers.journal_consumer.cli import CliConsumerContract


def test_lobehub_contract_has_version():
    c = LobehubConsumerContract()
    assert c.name == "lobehub"
    assert c.schema_version == "v2.0.0"


def test_cli_contract_projects_step_text_delta_to_text():
    c = CliConsumerContract()
    envelope = {
        "schema_version": "v2.0.0",
        "descriptor": {"type": "StepTextDelta"},
        "payload": {"text_delta": "你好", "channel": "answer"},
    }
    out = c.project(envelope)
    assert out["kind"] == "text"
    assert out["text"] == "你好"
```

- [ ] **Step 2-7：实现 + commit**

```python
# lca/plugins/providers/journal_consumer/lobehub_contract.py
"""consumer-lobehub provider (spec) —— ADR-0096 MVA-4.

后端侧定义 LobeHub consumer 的 contract:
- name="lobehub"
- schema_version="v2.0.0"
- project(envelope) 返回 LobeHub 端 Projected 类型(JSON 中性形态)

前端实现由 TS SDK 生成器(MVA-4 Task 3)从本 contract 派生;
不在后端写前端代码。
"""

from __future__ import annotations

from typing import Any


class LobehubConsumerContract:
    name = "lobehub"
    schema_version = "v2.0.0"

    def project(self, envelope: dict[str, Any]) -> dict[str, Any]:
        # 占位: MVA-4 阶段实现基础映射,Phase 2 扩为完整 codegen
        etype = envelope.get("descriptor", {}).get("type", "")
        payload = envelope.get("payload", {})
        if etype == "StepTextDelta":
            return {"kind": "text", "text": payload.get("text_delta", "")}
        if etype == "ReasoningDelta":
            return {"kind": "reasoning", "text": payload.get("text_delta", "")}
        if etype == "AgentRunStarted":
            return {"kind": "open-turn", "speaker": payload.get("agent_role", "")}
        if etype in ("AgentRunFinished", "RunFinished"):
            return {"kind": "run-finished"}
        return {"kind": "ignore"}
```

```bash
git commit -m "feat(adr-0096-mva-4): journal_consumer seam + lobehub/cli providers (spec)"
```

---

### Task 3：TS SDK 最小生成器

**Files:**
- Create: `lca/harness/sdk/ts_consumer_gen.py`
- Create: `deploy/lobehub/patches/runtime/.generated/lcaJournal.generated.ts`（生成产物,git 追踪）
- Create: `tests/test_ts_consumer_gen.py`

- [ ] **Step 1：写失败测试**

```python
# tests/test_ts_consumer_gen.py
from lca.harness.sdk.ts_consumer_gen import generate_ts_consumer


def test_generate_produces_project_function():
    src = generate_ts_consumer(contract_name="lobehub", schema_version="v2.0.0")
    assert "export function projectJournalFrame" in src
    assert "schema_version === 'v2.0.0'" in src
    assert "case 'StepTextDelta'" in src
    assert "case 'ReasoningDelta'" in src
```

- [ ] **Step 2-7：实现 + 测试 + commit**

```python
# lca/harness/sdk/ts_consumer_gen.py
"""TS consumer SDK 生成器 —— ADR-0096 MVA-4 + P2-8 占位实现。

读取 ``lca.plugins.providers.journal_consumer.lobehub_contract.LobehubConsumerContract``
的 ``project`` 方法,把 envelope 类型 + 返回 Projected 类型序列化成 TypeScript switch case。
生成产物写入 ``deploy/lobehub/patches/runtime/.generated/lcaJournal.generated.ts``。
"""

from __future__ import annotations

from pathlib import Path

CONTRACT_DIR = Path("deploy/lobehub/patches/runtime/.generated")


def generate_ts_consumer(*, contract_name: str, schema_version: str) -> str:
    """生成最小 TS SDK（仅 project 函数,无 resilience）。"""
    # 简化: MVA-4 阶段直接 hardcode + template,Phase 2 扩为完整 AST 生成
    return f"""// AUTO-GENERATED by lca/harness/sdk/ts_consumer_gen.py (ADR-0096 MVA-4)
// DO NOT EDIT; regenerate with: uv run python -m lca.harness.sdk.ts_consumer_gen
export const CONTRACT_NAME = '{contract_name}';
export const SCHEMA_VERSION = '{schema_version}';

export function projectJournalFrame(envelope: any): {{ kind: string; [k: string]: any }} {{
  if (envelope.schema_version !== SCHEMA_VERSION) {{
    console.warn(`Unknown schema version: ${{envelope.schema_version}}`);
    return {{ kind: 'ignore' }};
  }}
  const etype = envelope.descriptor?.type ?? '';
  const payload = envelope.payload ?? {{}};
  switch (etype) {{
    case 'StepTextDelta':
      return {{ kind: 'text', text: payload.text_delta ?? '' }};
    case 'ReasoningDelta':
      return {{ kind: 'reasoning', text: payload.text_delta ?? '' }};
    case 'AgentRunStarted':
      return {{ kind: 'open-turn', speaker: payload.agent_role ?? '' }};
    case 'AgentRunFinished':
    case 'RunFinished':
      return {{ kind: 'run-finished' }};
    default:
      return {{ kind: 'ignore' }};
  }}
}}
"""


def main() -> None:
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    src = generate_ts_consumer(contract_name="lobehub", schema_version="v2.0.0")
    (CONTRACT_DIR / "lcaJournal.generated.ts").write_text(src)
    print(f"Generated: {CONTRACT_DIR / 'lcaJournal.generated.ts'}")


if __name__ == "__main__":
    main()
```

```bash
git add lca/harness/sdk/ts_consumer_gen.py deploy/lobehub/patches/runtime/.generated/ tests/test_ts_consumer_gen.py
git commit -m "feat(adr-0096-mva-4): minimal TS SDK generator for consumer contracts"
```

---

### Task 4：consumer_resilience.ts 模块

**Files:**
- Create: `deploy/lobehub/patches/runtime/consumer_resilience.ts`
- Test: `tests/test_consumer_resilience.test.ts`（如 lobehub 仓跑 ts test）

- [ ] **Step 1：写 TS 测试**

```typescript
// tests/test_consumer_resilience.test.ts
import { describe, it, expect } from 'vitest';
import { BackoffStrategy, DedupSet, ReconnectController } from '../consumer_resilience';

describe('BackoffStrategy', () => {
  it('exponential backoff with jitter', () => {
    const b = new BackoffStrategy({ initialMs: 100, maxMs: 5000, factor: 2 });
    expect(b.nextDelay(0)).toBeGreaterThanOrEqual(100);
    expect(b.nextDelay(3)).toBeLessThanOrEqual(5000);
  });
});

describe('DedupSet', () => {
  it('rejects seen seq', () => {
    const d = new DedupSet();
    expect(d.add(1)).toBe(true);
    expect(d.add(1)).toBe(false);
  });
});

describe('ReconnectController', () => {
  it('respects max_retry', () => {
    const r = new ReconnectController({ maxRetry: 3 });
    expect(r.shouldRetry()).toBe(true);
    r.recordFailure();
    r.recordFailure();
    r.recordFailure();
    expect(r.shouldRetry()).toBe(false);
  });
});
```

- [ ] **Step 2：实现模块**

```typescript
// deploy/lobehub/patches/runtime/consumer_resilience.ts
/** Consumer resilience (backoff / dedup / max_retry) —— ADR-0096 MVA-4.
 *  从 LcaRunDriver 抽离,独立测试。
 */

export class BackoffStrategy {
  constructor(
    private readonly opts: { initialMs: number; maxMs: number; factor: number }
  ) {}
  nextDelay(attempt: number): number {
    const base = Math.min(this.opts.maxMs, this.opts.initialMs * Math.pow(this.opts.factor, attempt));
    const jitter = Math.random() * base * 0.3;
    return Math.floor(base + jitter);
  }
}

export class DedupSet {
  private seen = new Set<number>();
  add(seq: number): boolean {
    if (this.seen.has(seq)) return false;
    this.seen.add(seq);
    return true;
  }
}

export class ReconnectController {
  private failures = 0;
  constructor(private readonly opts: { maxRetry: number }) {}
  shouldRetry(): boolean { return this.failures < this.opts.maxRetry; }
  recordFailure(): void { this.failures += 1; }
  reset(): void { this.failures = 0; }
}
```

- [ ] **Step 3：跑 TS 测试**

Run: `cd lobehub-ui && pnpm run test:consumer-resilience`
Expected: PASS

- [ ] **Step 4：Commit**

```bash
git add deploy/lobehub/patches/runtime/consumer_resilience.ts
git commit -m "feat(lobehub): consumer_resilience module (backoff/dedup/max_retry)"
```

---

### Task 5：LobeHub `lcaJournal.ts` 切到生成 SDK + `LcaRunDriver.ts` 用韧性模块

**Files:**
- Modify: `deploy/lobehub/patches/runtime/lcaJournal.ts`（移除内联 `projectJournalFrame` 实现，import 生成版本）
- Modify: `deploy/lobehub/patches/runtime/LcaRunDriver.ts`（reconnect 逻辑用 `ReconnectController` + `BackoffStrategy`）

- [ ] **Step 1：替换 import**

```typescript
// lcaJournal.ts
import { projectJournalFrame as generatedProject } from './.generated/lcaJournal.generated';
// 保留 parseSseBlock / buildToolState 等 LobeHub-specific 逻辑
export const projectJournalFrame = generatedProject;
```

- [ ] **Step 2：LcaRunDriver 重连逻辑改造**

```typescript
// LcaRunDriver.ts
import { BackoffStrategy, DedupSet, ReconnectController } from './consumer_resilience';
// 替换硬编码 setTimeout(400) 等
```

- [ ] **Step 3：手动验证（部署到 LobeHub dev 实例）**

跑一次流式对话，确认 (a) 流式文本显示；(b) 重连 3 次以上不重复推送；(c) 断网 5s 后自动重连。

- [ ] **Step 4：Commit**

```bash
git add deploy/lobehub/patches/runtime/lcaJournal.ts deploy/lobehub/patches/runtime/LcaRunDriver.ts
git commit -m "refactor(lobehub): use generated consumer SDK + resilience module"
```

---

### MVA-4 完成判定

```bash
uv run pytest tests/test_consumer_contract_protocol.py tests/test_journal_consumer_providers.py tests/test_ts_consumer_gen.py -q
pnpm run typecheck
pnpm run test:consumer-resilience
# 手动：部署到 LobeHub dev 实例,跑一次流式对话,确认生产症状修复
```

对应 ADR-0096 §13.4 验收条目：**V12, V13, V14** 通过。

---

## 7. MVA 整体验收（4 PR 全部完成时）

```bash
# 1. 全量测试
uv run pytest tests/test_journal_schema_seam.py tests/test_journal_schema_v2.py tests/test_journal_schema_migrate.py tests/test_journal_schema_provider.py tests/test_event_identity_seam.py tests/test_event_identity_stable_ulid.py tests/test_event_identity_integration.py tests/test_run_manifest_terminal_seq.py tests/test_profile_snapshot_seam.py tests/test_profile_snapshot_run_boot.py tests/test_no_plugin_inventory_in_journal.py tests/test_runs_profile_endpoint.py tests/test_consumer_contract_protocol.py tests/test_journal_consumer_providers.py tests/test_ts_consumer_gen.py tests/test_sse_projection_contract.py tests/test_journal_v2_disk_format.py tests/test_journal_v2_envelope.py tests/test_journal_schema_fields.py tests/test_journal_core.py -q

# 2. CI gate
uv run python scripts/check_protocol_schema_version.py

# 3. 类型 + lint
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca

# 4. 死代码扫描
uv run vulture lca --min-confidence 80

# 5. 文档链接
uv run scripts/verify_md_links.py
uv run scripts/verify_doc_budgets.py
```

**MVA 验收通过后**：
- 更新本 tracker §1 表格，标注 MVA 4 PR 全部 ✅ Done
- 更新 ADR-0096 §13.5 表格的 ✅ 行
- 准备 Phase 2 启动文档（在下一个 milestone 启动时由 GSD 流程产生）

---

## 8. 已知陷阱

1. **ADR-0096 §6.3 与既有注释冲突**（sha256 vs ULID）：MVA-2 Task 1 已开 ADR-0097 解决；后续若有人沿用 ADR-0096 §6.3 字面会冲突，需在 PR review 时明确指 ADR-0097。

2. **LobeHub 仓同步**：MVA-1 Task 5 / MVA-4 Task 4/5 改 `deploy/lobehub/patches/runtime/` 是 patch 源；真正部署到 LobeHub dev 需要外部步骤（不在本 tracker 范围内）。LobeHub UI 仓的 PR 由独立流程推送。

3. **既有 fixture 可能破**：MVA-1 Task 3 改造 `journal_io.py:stamped_to_record` 可能让 `tests/test_journal_v2_disk_format.py` 期望格式不一致。**必须在 Step 6 跑既有测试不破**才允许合并 Task 3 commit。

4. **`event_id` 在 record_normalize 不再被派生**：MVA-2 Task 4 删除了 `_derive_event_id` 的 fallback；如果旧 journal 文件被回放，可能 event_id 与原值不同（replay 不一致）。**接受此行为**：ADR-0096 §I7 规定 derived view 不持硬 id；replay 一致性靠 schema_version 区分新旧版本。

5. **MVA-3 Task 3 改 plugin.inventory**：可能让依赖 RuntimeObserved(kind=plugin, operation=plugin.inventory) 的下游（lca-ops trace、debug tree 等）拿不到数据。**必须同步迁移到 `/runs/{id}/profile` endpoint**，并在 lca-ops 文档更新。

---

## 9. 关联文档

- ADR-0096： [`docs/adr/0096-journal-protocol-layer-everything-pluggable.md`](../adr/0096-journal-protocol-layer-everything-pluggable.md)
- ADR-0097（MVA-2 衍生）：待建，决策 ULID 派生
- ADR-0065：journal-as-truth（上游）
- ADR-0074：plugin-everything（seam 模式范式）
- ADR-0085：plugin-everything 解读（seam/producer 责任划分）
- ADR-0082：架构审查（journal protocol layer 不是 seam 的来源）
- AGENTS.md §2 仓库地图 + §3 架构不变量
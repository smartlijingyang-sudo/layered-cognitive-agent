# ADR-0246 M1 — LocalExecPort 契约收束 实现计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 落地 ADR-0246 M1（契约收束）——引入 `LocalExecPort`、`CapabilityGrant`、`EffectReceipt`、`FakeCompanionProvider`，收束现有 `MachineComputer`/`SandboxComputer` 在统一 Port 语义下，保持所有现有调用方不破坏。

**Architecture:**
DDD Seam 思路：在 `contracts` 层新增纯数据领域模型（`CapabilityGrant`、`EffectReceipt`、`LocalExecTarget`），在 `infrastructure` 层通过 Provider Façade 模式统一多执行目标路由，让 `MachineComputer`/`SandboxComputer` 成为 `LocalExecPort` 的 Provider 实现而非裸露依赖对象。`FakeCompanionProvider` 同步到位，不留跨 PR 后门。

**Tech Stack:** Python 3.11+, Pydantic v2 (`ConfigDict(frozen=True, extra="forbid")`), pytest-asyncio, ruff

---

## 背景：当前状态

| 现有文件 | 作用 |
|---|---|
| `lca/contracts/models/core/state/plane.py` | `PlaneKind(MACHINE/SANDBOX)`、`PlaneRef` |
| `lca/contracts/protocols/runtime/infra/infra.py` | `MachineTransport`、`MachineResolver` Protocol |
| `lca/infrastructure/computer/machine/machine.py` | `MachineComputer`（操作本机/Sidecar） |
| `lca/infrastructure/computer/sandbox/computer.py` | `SandboxComputer`（操作 Sandbox） |
| `lca/infrastructure/device_hub/client.py` | `KernelServeHttpClient`（HTTP transport，仅 transport 层） |
| `tests/scenario/machine/test_machine_computer.py` | 现有测试（不得破坏） |

---

## Task 1 — 领域模型：`LocalExecTarget`、`CapabilityGrant`、`EffectReceipt`

**DDD 定位：** `contracts` 层纯数据对象（ADR-0246 §3.2 / C13 血统闭合）。

**Files:**
- Create: `lca/contracts/models/core/execution/local_exec.py`
- Test: `tests/contracts/test_local_exec_models.py`

**Step 1: 写失败测试**

```python
# tests/contracts/test_local_exec_models.py
"""CapabilityGrant / EffectReceipt 领域模型契约测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)


def test_target_kind_values():
    assert set(TargetKind) == {
        TargetKind.SANDBOX,
        TargetKind.USER_MACHINE,
        TargetKind.POOL_WORKER,
    }


def test_capability_grant_frozen():
    grant = CapabilityGrant(
        job_id="j-1",
        idempotency_key="k-1",
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation="read_file",
        path_prefixes=["/home/alice/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=9999999999,
        approval_id=None,
        request_digest="sha256-abc",
    )
    with pytest.raises((TypeError, ValidationError)):
        grant.job_id = "mutate"  # type: ignore[misc]


def test_capability_grant_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        CapabilityGrant(
            job_id="j-1",
            idempotency_key="k-1",
            subject_user_id="u-1",
            subject_machine_id="m-1",
            operation="read_file",
            path_prefixes=[],
            command_class=None,
            command_allowlist=[],
            expires_at=9999999999,
            approval_id=None,
            request_digest="sha256-abc",
            unknown_field="bad",  # type: ignore[call-arg]
        )


def test_effect_receipt_frozen():
    receipt = EffectReceipt(
        job_id="j-1",
        idempotency_key="k-1",
        exit_code=0,
        success=True,
        error_kind=None,
        stdout_digest="sha256-x",
        stderr_digest=None,
    )
    with pytest.raises((TypeError, ValidationError)):
        receipt.success = False  # type: ignore[misc]


def test_local_exec_target_kinds():
    t = LocalExecTarget(
        kind=TargetKind.USER_MACHINE,
        id="m-win01",
        label="Alice-PC",
        capability_summary=["read_file", "write_file"],
    )
    assert t.kind == TargetKind.USER_MACHINE
```

**Step 2: 运行验证失败**

```bash
cd /home/lichao/layered-cognitive-agent
python -m pytest tests/contracts/test_local_exec_models.py -v 2>&1 | head -20
```
期望：`ModuleNotFoundError: No module named 'lca.contracts.models.core.execution.local_exec'`

**Step 3: 实现领域模型**

```python
# lca/contracts/models/core/execution/local_exec.py
"""ADR-0246 §3.2 — 本机副作用平面领域模型（纯数据，contracts 层）。

CapabilityGrant   副作用许可（许可类，非事实）
EffectReceipt     执行回执（回执类，追加不可变）
LocalExecTarget   执行目标描述（投影摘要）

rules: frozen=True, extra="forbid" (C13)
"""
from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict


class TargetKind(str, Enum):
    """执行目标分类——工具 schema 和 UI 必须据此区分（I-UMS-5）。"""
    SANDBOX = "sandbox"
    USER_MACHINE = "user_machine"
    POOL_WORKER = "pool_worker"


class LocalExecTarget(BaseModel):
    """执行目标描述（投影摘要，不是事实源）。"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TargetKind
    id: str
    label: str
    capability_summary: Sequence[str]


class CapabilityGrant(BaseModel):
    """短期、窄范围的副作用许可（ADR-0246 §3.2）。

    由控制面签发，Companion 本地再次校验。
    不持久存储；每次 Job 携带，TTL 结束即失效。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    idempotency_key: str
    subject_user_id: str
    subject_machine_id: str
    operation: str
    path_prefixes: Sequence[str]
    command_class: str | None
    command_allowlist: Sequence[str]
    expires_at: int                  # Unix timestamp
    approval_id: str | None          # HIL 审批绑定（ADR-0078）
    request_digest: str              # 规范化请求摘要（防 Confused Deputy）


class EffectReceipt(BaseModel):
    """执行回执（不可变，追加进 Session.append，ADR-0246 §3.3）。"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    idempotency_key: str
    exit_code: int | None
    success: bool
    error_kind: str | None   # device_offline | grant_expired | scope_violation | …
    stdout_digest: str | None
    stderr_digest: str | None
```

**Step 4: 运行验证通过**

```bash
python -m pytest tests/contracts/test_local_exec_models.py -v
```
期望：5 个测试 PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/core/execution/local_exec.py tests/contracts/test_local_exec_models.py
git commit -m "feat(contracts): 引入 CapabilityGrant/EffectReceipt/LocalExecTarget 领域模型 (ADR-0246 M1)"
```

---

## Task 2 — Port Protocol：`LocalExecPort`

**DDD 定位：** contracts 层 Protocol（Seam），分离调用者与实现。

**Files:**
- Modify: `lca/contracts/protocols/runtime/infra/infra.py`（末尾追加，不改现有内容）
- Test: `tests/contracts/test_local_exec_port_protocol.py`

**Step 1: 写失败测试**

```python
# tests/contracts/test_local_exec_port_protocol.py
"""LocalExecPort Protocol 结构测试。"""
from __future__ import annotations

from lca.contracts.protocols.runtime.infra.infra import LocalExecPort
from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
)


def test_local_exec_port_is_protocol():
    assert hasattr(LocalExecPort, "execute")
    assert hasattr(LocalExecPort, "target")


def test_fake_provider_satisfies_protocol():
    class _Fake:
        @property
        def target(self) -> LocalExecTarget:
            from lca.contracts.models.core.execution.local_exec import TargetKind
            return LocalExecTarget(
                kind=TargetKind.SANDBOX, id="s-1", label="fake",
                capability_summary=[],
            )

        async def execute(
            self, operation: str, args: dict, grant: CapabilityGrant,
        ) -> EffectReceipt:
            return EffectReceipt(
                job_id=grant.job_id, idempotency_key=grant.idempotency_key,
                exit_code=0, success=True, error_kind=None,
                stdout_digest=None, stderr_digest=None,
            )

    assert isinstance(_Fake(), LocalExecPort)
```

**Step 2: 运行验证失败**

```bash
python -m pytest tests/contracts/test_local_exec_port_protocol.py -v 2>&1 | head -10
```

**Step 3: 在 infra.py 末尾追加 Protocol**

在 `lca/contracts/protocols/runtime/infra/infra.py` 末尾追加：

```python
# ---------- ADR-0246 M1: LocalExecPort ----------

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
)


@runtime_checkable
class LocalExecPort(Protocol):
    """副作用执行 Seam（ADR-0246 §3.1）。

    替换测试要求：同一 operation 换 Provider 后，审批状态、Journal 事件
    形状、幂等重放和错误分类保持一致。
    Provider 不得把失败静默转换成另一个目标的成功（I-UMS-1）。
    """

    @property
    def target(self) -> LocalExecTarget:
        """当前执行目标描述（I-UMS-5：工具 schema 和 UI 渲染依赖此字段）。"""
        ...

    async def execute(
        self,
        operation: str,
        args: dict[str, Any],
        grant: CapabilityGrant,
    ) -> EffectReceipt:
        """执行一次副作用，返回不可变回执。

        实现契约：
        - 幂等键命中历史 → 直接返回原 receipt，不重复执行（I-UMS-6）
        - grant.expires_at < now → error_kind="grant_expired"，fail-loud（I-UMS-3）
        - 路径越界 → error_kind="scope_violation"，fail-loud（I-UMS-3）
        - 目标 offline → error_kind="device_offline"，fail-loud（I-UMS-1）
        """
        ...
```

**Step 4: 运行验证通过**

```bash
python -m pytest tests/contracts/test_local_exec_port_protocol.py -v
```

**Step 5: Commit**

```bash
git add lca/contracts/protocols/runtime/infra/infra.py tests/contracts/test_local_exec_port_protocol.py
git commit -m "feat(contracts): 新增 LocalExecPort Protocol Seam (ADR-0246 M1 §3.1)"
```

---

## Task 3 — `FakeCompanionProvider` + `FakeSandboxProvider`

**DDD 定位：** 测试用 fake 实现，验证 Provider 替换一致性。必须同 PR 到位。

**Files:**
- Create: `lca/infrastructure/computer/fake/__init__.py`
- Create: `lca/infrastructure/computer/fake/companion.py`
- Create: `lca/infrastructure/computer/fake/sandbox.py`
- Test: `tests/infrastructure/computer/test_fake_companion_provider.py`

**Step 1: 写失败测试（全部错误路径）**

```python
# tests/infrastructure/computer/test_fake_companion_provider.py
"""FakeCompanionProvider — ADR-0246 §6 M1 验收测试。"""
from __future__ import annotations
import time
import pytest
from lca.contracts.models.core.execution.local_exec import CapabilityGrant, TargetKind
from lca.infrastructure.computer.fake.companion import FakeCompanionProvider


def _grant(*, job_id="j-1", idem="k-1", path_prefixes=None,
           expires_delta=3600, operation="read_file") -> CapabilityGrant:
    return CapabilityGrant(
        job_id=job_id, idempotency_key=idem,
        subject_user_id="u-1", subject_machine_id="m-1",
        operation=operation, path_prefixes=path_prefixes or ["/repo"],
        command_class=None, command_allowlist=[],
        expires_at=int(time.time()) + expires_delta,
        approval_id=None, request_digest="digest-1",
    )


@pytest.mark.asyncio
async def test_happy_path():
    provider = FakeCompanionProvider()
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is True


@pytest.mark.asyncio
async def test_offline_fail_loud():
    """I-UMS-1: offline 必须 fail-loud，禁止静默回落。"""
    provider = FakeCompanionProvider(mode="offline")
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "device_offline"


@pytest.mark.asyncio
async def test_grant_expired_fail_loud():
    """I-UMS-3: Grant 过期必须 fail-loud。"""
    provider = FakeCompanionProvider()
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant(expires_delta=-1))
    assert receipt.success is False
    assert receipt.error_kind == "grant_expired"


@pytest.mark.asyncio
async def test_scope_violation_fail_loud():
    """I-UMS-3: 路径越界必须 fail-loud。"""
    provider = FakeCompanionProvider()
    receipt = await provider.execute("read_file", {"path": "/etc/passwd"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "scope_violation"


@pytest.mark.asyncio
async def test_idempotent_replay():
    """I-UMS-6: 重复投递必须返回原 receipt，只执行一次。"""
    provider = FakeCompanionProvider()
    grant = _grant(job_id="j-idem", idem="k-idem")
    r1 = await provider.execute("read_file", {"path": "/repo/a.py"}, grant)
    r2 = await provider.execute("read_file", {"path": "/repo/a.py"}, grant)
    assert r1 == r2
    assert provider.execution_count == 1


@pytest.mark.asyncio
async def test_provider_replacement_consistent_error_shape():
    """替换测试：FakeCompanionProvider 与 FakeSandboxProvider 错误形状一致。"""
    from lca.infrastructure.computer.fake.sandbox import FakeSandboxProvider
    grant = _grant(path_prefixes=["/repo"])
    companion = FakeCompanionProvider()
    sandbox = FakeSandboxProvider()
    r_c = await companion.execute("read_file", {"path": "/etc/passwd"}, grant)
    r_s = await sandbox.execute("read_file", {"path": "/etc/passwd"}, grant)
    assert r_c.error_kind == r_s.error_kind == "scope_violation"


def test_target_kind_is_user_machine():
    assert FakeCompanionProvider().target.kind == TargetKind.USER_MACHINE
```

**Step 2: 运行验证失败**

```bash
python -m pytest tests/infrastructure/computer/test_fake_companion_provider.py -v 2>&1 | head -15
```

**Step 3: 实现 FakeCompanionProvider**

```python
# lca/infrastructure/computer/fake/companion.py
"""FakeCompanionProvider — 测试专用，验证 LocalExecPort 契约 (ADR-0246 M1)。"""
from __future__ import annotations
import os
import time
from typing import Any, Literal
from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant, EffectReceipt, LocalExecTarget, TargetKind,
)


class FakeCompanionProvider:
    """mode: normal | offline | deny"""

    def __init__(self, *, mode: Literal["normal", "offline", "deny"] = "normal",
                 machine_id: str = "m-fake-01", label: str = "FakeWindows-PC") -> None:
        self._mode = mode
        self._machine_id = machine_id
        self._label = label
        self._idem_store: dict[str, EffectReceipt] = {}
        self.execution_count = 0

    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.USER_MACHINE, id=self._machine_id, label=self._label,
            capability_summary=["read_file", "write_file", "run_command", "git"],
        )

    async def execute(self, operation: str, args: dict[str, Any],
                      grant: CapabilityGrant) -> EffectReceipt:
        idem_key = f"{grant.job_id}:{grant.idempotency_key}"
        if idem_key in self._idem_store:
            return self._idem_store[idem_key]
        receipt = self._run(operation, args, grant)
        if receipt.error_kind not in ("device_offline",):
            self._idem_store[idem_key] = receipt
        return receipt

    def _run(self, operation: str, args: dict[str, Any],
             grant: CapabilityGrant) -> EffectReceipt:
        base = dict(job_id=grant.job_id, idempotency_key=grant.idempotency_key,
                    exit_code=None, stdout_digest=None, stderr_digest=None)
        if self._mode == "offline":
            return EffectReceipt(**base, success=False, error_kind="device_offline")
        if grant.expires_at < int(time.time()):
            return EffectReceipt(**base, success=False, error_kind="grant_expired")
        path = str(args.get("path", args.get("directory", "")))
        if path and grant.path_prefixes:
            norm = os.path.normpath(path)
            if not any(norm.startswith(os.path.normpath(p)) for p in grant.path_prefixes):
                return EffectReceipt(**base, success=False, error_kind="scope_violation")
        if self._mode == "deny":
            return EffectReceipt(**base, success=False, error_kind="local_policy_denied")
        self.execution_count += 1
        return EffectReceipt(**base, success=True, exit_code=0, stdout_digest="sha256-fake")
```

```python
# lca/infrastructure/computer/fake/sandbox.py
"""FakeSandboxProvider — 替换测试对称用 (ADR-0246 M1)。"""
from __future__ import annotations
import os, time
from typing import Any
from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant, EffectReceipt, LocalExecTarget, TargetKind,
)


class FakeSandboxProvider:
    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.SANDBOX, id="sandbox-fake-01",
            label="FakeSandbox", capability_summary=["read_file", "write_file", "run_command"],
        )

    async def execute(self, operation: str, args: dict[str, Any],
                      grant: CapabilityGrant) -> EffectReceipt:
        base = dict(job_id=grant.job_id, idempotency_key=grant.idempotency_key,
                    exit_code=None, stdout_digest=None, stderr_digest=None)
        if grant.expires_at < int(time.time()):
            return EffectReceipt(**base, success=False, error_kind="grant_expired")
        path = str(args.get("path", args.get("directory", "")))
        if path and grant.path_prefixes:
            norm = os.path.normpath(path)
            if not any(norm.startswith(os.path.normpath(p)) for p in grant.path_prefixes):
                return EffectReceipt(**base, success=False, error_kind="scope_violation")
        return EffectReceipt(**base, success=True, exit_code=0, stdout_digest="sha256-sandbox")
```

```python
# lca/infrastructure/computer/fake/__init__.py
"""Fake providers — 测试专用，不进生产路径。"""
```

**Step 4: 运行验证通过**

```bash
python -m pytest tests/infrastructure/computer/test_fake_companion_provider.py -v
```
期望：7 个测试 PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/computer/fake/ tests/infrastructure/computer/test_fake_companion_provider.py
git commit -m "feat(infrastructure): FakeCompanionProvider + FakeSandboxProvider 契约测试 (ADR-0246 M1)"
```

---

## Task 4 — `PlaneKind.POOL_WORKER` + `PlaneRef.capability_summary`

**Files:**
- Modify: `lca/contracts/models/core/state/plane.py`
- Test: `tests/contracts/test_plane_kind_extension.py`

**Step 1: 写测试**

```python
# tests/contracts/test_plane_kind_extension.py
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef


def test_existing_plane_kinds_unchanged():
    assert PlaneKind.MACHINE == "machine"
    assert PlaneKind.SANDBOX == "sandbox"


def test_pool_worker_added():
    assert PlaneKind.POOL_WORKER == "pool_worker"


def test_plane_ref_backward_compatible():
    """现有构造方式（不传 capability_summary）仍然有效。"""
    ref = PlaneRef(
        id="s-1", label="sandbox", kind=PlaneKind.SANDBOX, root="/tmp", outputs_dir="/tmp/out"
    )
    assert ref.kind == PlaneKind.SANDBOX
    assert ref.capability_summary == ()
```

**Step 2: 运行验证失败**

```bash
python -m pytest tests/contracts/test_plane_kind_extension.py -v 2>&1 | head -10
```

**Step 3: 修改 plane.py（向下兼容）**

```python
# lca/contracts/models/core/state/plane.py
"""Product-environment identity — pure data, no behavior (ADR-0015, ADR-0246)."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class PlaneKind(str, Enum):
    MACHINE = "machine"
    SANDBOX = "sandbox"
    POOL_WORKER = "pool_worker"  # ADR-0246 M1


@dataclass(frozen=True)
class PlaneRef:
    id: str
    label: str
    kind: PlaneKind
    root: str
    outputs_dir: str
    platform: str = ""
    home: str = ""
    capability_summary: tuple[str, ...] = field(default_factory=tuple)  # ADR-0246 M1


@dataclass(frozen=True)
class PlaneBindings:
    primary: PlaneRef | None
    secondary: PlaneRef | None = None
```

**Step 4: 运行所有相关测试（确保不破坏现有）**

```bash
python -m pytest tests/contracts/ tests/scenario/machine/ -v
```

**Step 5: Commit**

```bash
git add lca/contracts/models/core/state/plane.py tests/contracts/test_plane_kind_extension.py
git commit -m "feat(contracts): PlaneKind.POOL_WORKER + PlaneRef.capability_summary (ADR-0246 M1)"
```

---

## Task 5 — `MachineLocalExecAdapter`（Adapter 层）

**DDD 定位：** Adapter 让 `MachineComputer` 满足 `LocalExecPort` Protocol，不改调用方。

**Files:**
- Create: `lca/infrastructure/computer/machine/adapter.py`
- Test: `tests/infrastructure/computer/test_machine_local_exec_adapter.py`

**Step 1: 写测试**

```python
# tests/infrastructure/computer/test_machine_local_exec_adapter.py
"""MachineLocalExecAdapter 满足 LocalExecPort，错误形状与 FakeCompanionProvider 一致。"""
from __future__ import annotations
import time
from typing import Any
import pytest
from lca.contracts.models.core.execution.local_exec import CapabilityGrant, TargetKind
from lca.contracts.protocols.runtime.infra.infra import LocalExecPort
from lca.infrastructure.computer.machine.adapter import MachineLocalExecAdapter


class _FakeTransport:
    async def computer_op(self, op: str, args: dict[str, Any], *, timeout_s: int = 60) -> dict:
        return {"success": True, "content": "ok"}
    async def write_files(self, files, **kwargs): return None


def _make_adapter():
    import pathlib, tempfile
    from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
    from lca.infrastructure.computer.machine.machine import MachineComputer
    from lca.infrastructure.file.store import LocalFileStore
    plane = PlaneRef(id="m-1", label="test-machine", kind=PlaneKind.MACHINE,
                     root="/repo", outputs_dir="/repo/out")
    store = LocalFileStore(pathlib.Path(tempfile.mkdtemp()))
    mc = MachineComputer(plane=plane, transport=_FakeTransport(), store=store)
    return MachineLocalExecAdapter(computer=mc, machine_id="m-1", label="test-machine")


def test_adapter_satisfies_protocol():
    assert isinstance(_make_adapter(), LocalExecPort)


def test_target_kind_is_user_machine():
    assert _make_adapter().target.kind == TargetKind.USER_MACHINE


@pytest.mark.asyncio
async def test_grant_expired_error_kind():
    grant = CapabilityGrant(
        job_id="j-1", idempotency_key="k-1",
        subject_user_id="u-1", subject_machine_id="m-1",
        operation="read_file", path_prefixes=["/repo"],
        command_class=None, command_allowlist=[],
        expires_at=int(time.time()) - 1,
        approval_id=None, request_digest="d-1",
    )
    receipt = await _make_adapter().execute("read_file", {"path": "/repo/a.py"}, grant)
    assert receipt.success is False
    assert receipt.error_kind == "grant_expired"


@pytest.mark.asyncio
async def test_scope_violation_error_kind():
    grant = CapabilityGrant(
        job_id="j-2", idempotency_key="k-2",
        subject_user_id="u-1", subject_machine_id="m-1",
        operation="read_file", path_prefixes=["/repo"],
        command_class=None, command_allowlist=[],
        expires_at=int(time.time()) + 3600,
        approval_id=None, request_digest="d-2",
    )
    receipt = await _make_adapter().execute("read_file", {"path": "/etc/passwd"}, grant)
    assert receipt.success is False
    assert receipt.error_kind == "scope_violation"
```

**Step 2: 运行验证失败**

```bash
python -m pytest tests/infrastructure/computer/test_machine_local_exec_adapter.py -v 2>&1 | head -15
```

**Step 3: 实现 Adapter**

```python
# lca/infrastructure/computer/machine/adapter.py
"""MachineLocalExecAdapter — 将 MachineComputer 适配为 LocalExecPort (ADR-0246 M1)。

职责：Grant 校验（过期、路径越界）→ 调用 MachineComputer → 包装为 EffectReceipt。
"""
from __future__ import annotations
import hashlib, os, time
from typing import Any
from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant, EffectReceipt, LocalExecTarget, TargetKind,
)
from lca.infrastructure.computer.machine.machine import MachineComputer


class MachineLocalExecAdapter:
    def __init__(self, computer: MachineComputer, *, machine_id: str, label: str) -> None:
        self._computer = computer
        self._machine_id = machine_id
        self._label = label

    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.USER_MACHINE, id=self._machine_id, label=self._label,
            capability_summary=["read_file", "write_file", "run_command", "git"],
        )

    async def execute(self, operation: str, args: dict[str, Any],
                      grant: CapabilityGrant) -> EffectReceipt:
        base = dict(job_id=grant.job_id, idempotency_key=grant.idempotency_key,
                    exit_code=None, stdout_digest=None, stderr_digest=None)
        if grant.expires_at < int(time.time()):
            return EffectReceipt(**base, success=False, error_kind="grant_expired")
        path = str(args.get("path", args.get("directory", "")))
        if path and grant.path_prefixes:
            norm = os.path.normpath(path)
            if not any(norm.startswith(os.path.normpath(p)) for p in grant.path_prefixes):
                return EffectReceipt(**base, success=False, error_kind="scope_violation")
        try:
            result = await self._dispatch(operation, args)
        except ConnectionError:
            return EffectReceipt(**base, success=False, error_kind="device_offline")
        digest = ("sha256-" + hashlib.sha256(result.content.encode()).hexdigest()[:16]
                  if result.content else None)
        return EffectReceipt(**base, success=result.success, exit_code=None,
                             error_kind=None if result.success else "execution_error",
                             stdout_digest=digest)

    async def _dispatch(self, operation: str, args: dict[str, Any]):
        _MAP = {
            "read_file": lambda: self._computer.read_file(path=args.get("path", "")),
            "write_file": lambda: self._computer.write_file(
                path=args.get("path", ""), content=args.get("content", "")),
            "run_command": lambda: self._computer.run_command(
                command=args.get("command", ""), timeout_s=args.get("timeout_s", 60)),
            "list_files": lambda: self._computer.list_files(
                directory_path=args.get("directory", "")),
        }
        fn = _MAP.get(operation)
        if fn is None:
            from lca.infrastructure.computer.op.result import ComputerOpResult
            return ComputerOpResult(success=False, content=f"unknown: {operation}",
                                    state={}, error="unknown")
        return await fn()
```

**Step 4: 运行验证通过**

```bash
python -m pytest tests/infrastructure/computer/test_machine_local_exec_adapter.py tests/scenario/machine/ -v
```

**Step 5: Commit**

```bash
git add lca/infrastructure/computer/machine/adapter.py tests/infrastructure/computer/test_machine_local_exec_adapter.py
git commit -m "feat(infrastructure): MachineLocalExecAdapter 满足 LocalExecPort (ADR-0246 M1)"
```

---

## Task 6 — 导出注册 + 代码清洁

**Files:**
- Modify: `lca/contracts/models/core/execution/__init__.py`（追加导出）

**Step 1: 追加导出**

在文件末尾追加：
```python
# ADR-0246 M1
from lca.contracts.models.core.execution.local_exec import (  # noqa: F401
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)
```

**Step 2: 验证导入路径**

```bash
python -c "from lca.contracts.models.core.execution import CapabilityGrant, EffectReceipt, TargetKind; print('OK')"
```

**Step 3: ruff 格式**

```bash
ruff check lca/contracts/models/core/execution/local_exec.py lca/infrastructure/computer/machine/adapter.py lca/infrastructure/computer/fake/ --fix
ruff format lca/contracts/ lca/infrastructure/computer/
```

**Step 4: 全量回归**

```bash
python -m pytest tests/contracts/ tests/infrastructure/computer/ tests/scenario/machine/ -v --tb=short
```

**Step 5: Commit**

```bash
git add lca/contracts/models/core/execution/__init__.py
git commit -m "chore: 注册 ADR-0246 M1 新增类型到 contracts 导出"
```

---

## Task 7 — 架构守护测试

**Files:**
- Test: `tests/architecture/test_adr_0246_m1_import_guards.py`

**Step 1: 写守护测试**

```python
# tests/architecture/test_adr_0246_m1_import_guards.py
"""ADR-0246 M1 架构不变量：依赖方向守护。"""
from __future__ import annotations
import pathlib

_CONTRACTS_DIR = pathlib.Path("lca/contracts")
_INFRA_IMPORT_PATTERNS = ["lca.infrastructure", "from lca.infrastructure"]


def _all_py(directory: pathlib.Path):
    return list(directory.rglob("*.py"))


def test_contracts_do_not_import_infrastructure():
    """contracts 层不得反向 import infrastructure（C1/C2 不变量）。"""
    violations = []
    for py_file in _all_py(_CONTRACTS_DIR):
        source = py_file.read_text(encoding="utf-8")
        for pattern in _INFRA_IMPORT_PATTERNS:
            if pattern in source:
                violations.append(f"{py_file}: '{pattern}'")
    assert not violations, "contracts 层发现反向 import:\n" + "\n".join(violations)


def test_fake_providers_not_imported_in_production():
    """fake providers 不得被生产代码 import。"""
    prod_dirs = [
        pathlib.Path("lca/infrastructure/computer/machine"),
        pathlib.Path("lca/infrastructure/computer/sandbox"),
        pathlib.Path("lca/cognition"),
    ]
    violations = []
    for d in prod_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            if "computer.fake" in source or "FakeCompanionProvider" in source:
                violations.append(str(py_file))
    assert not violations, "生产代码不得 import fake providers:\n" + "\n".join(violations)
```

**Step 2: 运行**

```bash
python -m pytest tests/architecture/test_adr_0246_m1_import_guards.py -v
```

**Step 3: 最终全量回归 + 门禁**

```bash
python -m pytest tests/contracts/ tests/infrastructure/computer/ tests/scenario/machine/ tests/architecture/test_adr_0246_m1_import_guards.py -v
ruff check lca/ --select=I,E,F
git diff --check
```

**Step 4: 最终 Commit**

```bash
git add tests/architecture/test_adr_0246_m1_import_guards.py
git commit -m "test(architecture): ADR-0246 M1 import 方向守护测试"
```

---

## M1 完成验收矩阵

| 验收项 | 命令 | 期望 |
|---|---|---|
| 所有新测试通过 | `pytest tests/contracts/ tests/infrastructure/computer/ tests/scenario/machine/ tests/architecture/ -v` | 全绿 |
| 现有测试不破坏 | `pytest tests/scenario/machine/ -v` | 全绿 |
| ruff 通过 | `ruff check lca/ --fix && ruff format lca/` | 无错误 |
| contracts 不 import infra | `pytest tests/architecture/test_adr_0246_m1_import_guards.py` | 全绿 |
| LocalExecPort Protocol 可用 | `python -c "from lca.contracts.protocols.runtime.infra.infra import LocalExecPort; print(LocalExecPort.__name__)"` | `LocalExecPort` |
| POOL_WORKER 存在 | `python -c "from lca.contracts.models.core.state.plane import PlaneKind; print(PlaneKind.POOL_WORKER)"` | `PlaneKind.POOL_WORKER` |
| CapabilityGrant 可 import | `python -c "from lca.contracts.models.core.execution import CapabilityGrant; print('OK')"` | `OK` |

---

## 下一步（M2 预告）

M2 将实现：
- Gateway 侧 RFC 8628 Device Code 配对端点（`/api/machines/pair`）
- Companion 出站 WebSocket 长连接（零本地监听端口，免疫 DNS Rebinding）
- `machine_token` 与 Job `CapabilityGrant` 严格分离
- 配对状态机 `UNPAIRED → PAIRING → PAIRED → REVOKED`
- 心跳与撤销（`REVOKED` 后 Companion 立即拒绝执行）

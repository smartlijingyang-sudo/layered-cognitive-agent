"""LocalExecPort Protocol 结构测试。"""

from __future__ import annotations

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)
from lca.contracts.protocols.runtime.infra.infra import LocalExecPort


def test_local_exec_port_is_protocol() -> None:
    assert hasattr(LocalExecPort, "execute")
    assert hasattr(LocalExecPort, "target")


def test_fake_provider_satisfies_protocol() -> None:
    class _Fake:
        @property
        def target(self) -> LocalExecTarget:
            return LocalExecTarget(
                kind=TargetKind.SANDBOX,
                id="s-1",
                label="fake",
                capability_summary=[],
            )

        async def execute(
            self,
            operation: str,
            args: dict,
            grant: CapabilityGrant,
        ) -> EffectReceipt:
            return EffectReceipt(
                job_id=grant.job_id,
                idempotency_key=grant.idempotency_key,
                exit_code=0,
                success=True,
                error_kind=None,
                stdout_digest=None,
                stderr_digest=None,
            )

    assert isinstance(_Fake(), LocalExecPort)

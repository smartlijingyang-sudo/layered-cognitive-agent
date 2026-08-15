"""Adapter: DeepSeek Harness Python SDK → ``DshRuntime``."""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.dsh.driver import DshTurnSpec
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.settings import DshSettings


class DshUnavailableError(RuntimeError):
    """SDK missing, runtime binary missing, or misconfigured."""


class SdkDshRuntime(DshRuntime):
    """Local SDK execution — for development only.  Production uses MachineDshRuntime."""

    def __init__(self, settings: DshSettings) -> None:
        self._settings = settings

    def run_turn(
        self,
        spec: DshTurnSpec,
        on_event: Callable[[DshNotification], None],
    ) -> DshTurnResult:
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as exc:
            raise DshUnavailableError(
                "DSH SDK 未安装。生产环境应使用 MachineDshRuntime（SDK 装在 sandbox-user 侧）。"
                "本地开发需 pip install deepseek-harness-sdk"
            ) from exc

        kwargs: dict[str, object] = {
            "provider": self._settings.provider,
            "model": self._settings.resolved_model(),
            "cwd": spec.cwd,
            "session_root": spec.session_root,
            "request_timeout_seconds": self._settings.request_timeout_seconds,
        }
        if spec.harness_env:
            kwargs["env"] = dict(spec.harness_env)
        max_tokens = self._settings.resolved_max_tokens()
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        cordis = self._settings.resolved_cordis()
        if cordis is not None:
            kwargs["cordis"] = cordis
        api_key = self._settings.resolved_api_key()
        if api_key:
            kwargs["api_key"] = api_key
        base_url = self._settings.resolved_base_url()
        if base_url:
            kwargs["base_url"] = base_url

        def _notify(raw: object) -> None:
            method = getattr(raw, "method", None)
            payload = getattr(raw, "payload", None)
            if not isinstance(method, str):
                return
            body = payload if isinstance(payload, dict) else {}
            on_event(DshNotification(method=method, payload=body))

        with DeepSeekHarness(**kwargs) as harness:
            result = harness.run(spec.prompt, session_id=spec.session_id, on_notification=_notify)
        return DshTurnResult(
            session_id=result.session_id,
            final_response=result.final_response or "",
            finish_reason=result.finish_reason,
        )

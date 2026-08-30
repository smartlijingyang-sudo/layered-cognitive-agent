"""Adapter: DeepSeek Harness Python SDK → ``DshRuntime``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.protocols import DshRuntime
from lca.infrastructure.dsh.driver import DshTurnSpec
from lca.infrastructure.dsh.models import DshNotification, DshTurnResult
from lca.infrastructure.dsh.settings import DshSettings


class DshUnavailableError(RuntimeError):
    """SDK missing, runtime binary missing, or misconfigured."""


class SdkDshRuntime(DshRuntime):
    """Local SDK execution — gateway dev or machine daemon via ``turn_config``."""

    def __init__(
        self,
        settings: DshSettings | None = None,
        *,
        turn_config: dict[str, Any] | None = None,
    ) -> None:
        self._settings = settings or DshSettings()
        self._turn_config = dict(turn_config or {})

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
            "provider": self._turn_config.get("provider", self._settings.provider),
            "model": self._turn_config.get("model", self._settings.resolved_model()),
            "cwd": spec.cwd,
            "session_root": spec.session_root,
            "request_timeout_seconds": self._turn_config.get(
                "request_timeout_seconds",
                self._settings.request_timeout_seconds,
            ),
        }
        harness_env = spec.harness_env
        if isinstance(self._turn_config.get("harness_env"), dict):
            harness_env = {**dict(harness_env or {}), **self._turn_config["harness_env"]}
        if harness_env:
            kwargs["env"] = dict(harness_env)
        max_tokens = self._turn_config.get("max_tokens", self._settings.resolved_max_tokens())
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        cordis = self._turn_config.get("cordis", self._settings.resolved_cordis())
        if cordis is not None:
            kwargs["cordis"] = cordis
        api_key = self._turn_config.get("api_key", self._settings.resolved_api_key())
        if api_key:
            kwargs["api_key"] = api_key
        base_url = self._turn_config.get("base_url", self._settings.resolved_base_url())
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

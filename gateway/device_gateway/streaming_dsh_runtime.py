"""Gateway DSH runtime — streams SDK notifications from daemon over device WebSocket."""

from __future__ import annotations

from collections.abc import Callable

from gateway.device_gateway.hub import DeviceHub
from lca.contracts.protocols.infra import DshRuntime
from lca.infrastructure.comparison.dsh_driver.driver import DshTurnSpec
from lca.infrastructure.comparison.dsh_driver.models import DshNotification, DshTurnResult
from lca.infrastructure.comparison.dsh_driver.settings import DshSettings
from lca.infrastructure.comparison.dsh_driver.stream_params import build_turn_config


class StreamingDshRuntime(DshRuntime):
    """``DshRuntime`` for production: daemon runs SDK, hub relays notifications live."""

    def __init__(
        self,
        hub: DeviceHub,
        device_id: str,
        settings: DshSettings,
    ) -> None:
        self._hub = hub
        self._device_id = device_id
        self._settings = settings

    def run_turn(
        self,
        spec: DshTurnSpec,
        on_event: Callable[[DshNotification], None],
    ) -> DshTurnResult:
        raise NotImplementedError("use run_turn_async on gateway event loop")

    async def run_turn_async(
        self,
        spec: DshTurnSpec,
        on_event: Callable[[DshNotification], None],
    ) -> DshTurnResult:
        params = build_turn_config(spec, self._settings, harness_env=spec.harness_env)
        timeout_s = float(self._settings.request_timeout_seconds or 600.0)
        return await self._hub.run_dsh_turn(
            self._device_id,
            turn_id=spec.session_id,
            params=params,
            on_notification=on_event,
            timeout_s=timeout_s,
        )

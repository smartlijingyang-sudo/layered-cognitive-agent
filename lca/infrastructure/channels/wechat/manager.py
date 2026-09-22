"""Manager for Assistant WeChat channels and worker lifecycle."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from lca.contracts.channels.wechat import WechatChannelConfig
from lca.infrastructure.channels.wechat.client import WechatIlinkClient
from lca.infrastructure.channels.wechat.worker import DispatchFunction, WechatChannelWorker
from lca.infrastructure.path.locator import get_lca_home

logger = logging.getLogger(__name__)


class WechatChannelManager:
    """Manages channel worker processes and persistence per Assistant."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        dispatch_fn: DispatchFunction | None = None,
        client_factory: Callable[[str], WechatIlinkClient] | None = None,
    ) -> None:
        if base_dir is None:
            self.base_dir = get_lca_home()
        else:
            self.base_dir = Path(base_dir).resolve()

        self.dispatch_fn = dispatch_fn or self._default_dispatch
        self._client_factory = client_factory or (lambda base_url: WechatIlinkClient(base_url=base_url))
        self._workers: dict[str, WechatChannelWorker] = {}

    async def _default_dispatch(
        self,
        assistant_id: str,
        session_id: str,
        text: str,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Fallback mock dispatch if no gateway executor is bound."""
        return f"[{assistant_id}] 收到微信消息: {text}"

    def _get_config_path(self, assistant_id: str) -> Path:
        return self.base_dir / "assistants" / assistant_id / "channels" / "wechat.json"

    def is_running(self, assistant_id: str) -> bool:
        worker = self._workers.get(assistant_id)
        return worker is not None and worker.status == "running"

    def get_channel_config(self, assistant_id: str) -> WechatChannelConfig | None:
        path = self._get_config_path(assistant_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return WechatChannelConfig(**data)
        except Exception as exc:
            logger.error("Failed to load wechat config for %s: %s", assistant_id, exc)
            return None

    async def bind_channel(self, assistant_id: str, config: WechatChannelConfig) -> None:
        """Persist config and start the channel worker."""
        path = self._get_config_path(assistant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
        with contextlib.suppress(OSError):
            path.chmod(0o600)

        await self.stop_worker(assistant_id)

        if config.enabled:
            client = self._client_factory(config.base_url)
            worker = WechatChannelWorker(
                assistant_id=assistant_id,
                config=config,
                client=client,
                dispatch_fn=self.dispatch_fn,
            )
            self._workers[assistant_id] = worker
            await worker.start()

    async def unbind_channel(self, assistant_id: str) -> None:
        """Stop worker and delete persisted configuration."""
        await self.stop_worker(assistant_id)
        path = self._get_config_path(assistant_id)
        if path.exists():
            path.unlink()

    async def stop_worker(self, assistant_id: str) -> None:
        worker = self._workers.pop(assistant_id, None)
        if worker:
            await worker.stop()

    async def load_all_channels(self) -> None:
        """Scan ~/.lca/assistants/*/channels/wechat.json and start enabled workers."""
        assistants_dir = self.base_dir / "assistants"
        if not assistants_dir.exists():
            return

        for channel_file in assistants_dir.glob("*/channels/wechat.json"):
            assistant_id = channel_file.parent.parent.name
            config = self.get_channel_config(assistant_id)
            if config and config.enabled:
                client = self._client_factory(config.base_url)
                worker = WechatChannelWorker(
                    assistant_id=assistant_id,
                    config=config,
                    client=client,
                    dispatch_fn=self.dispatch_fn,
                )
                self._workers[assistant_id] = worker
                await worker.start()

    async def shutdown(self) -> None:
        """Stop all running workers on server shutdown."""
        for worker in list(self._workers.values()):
            await worker.stop()
        self._workers.clear()

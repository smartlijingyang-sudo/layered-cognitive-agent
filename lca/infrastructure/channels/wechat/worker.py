"""WeChat channel worker running long-polling daemon and bridging messages."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from lca.contracts.channels.wechat import WechatChannelConfig
from lca.infrastructure.channels.wechat.client import WechatIlinkClient

logger = logging.getLogger(__name__)

DispatchFunction = Callable[
    [str, str, str, Callable[[str], Awaitable[None]] | None],
    Awaitable[str],
]


def derive_wechat_session_id(assistant_id: str, ilink_user_id: str) -> str:
    """Deterministically derive an isolated LCA session ID for a WeChat user."""
    seed = f"{assistant_id}:{ilink_user_id}".encode()
    hash_part = hashlib.sha256(seed).hexdigest()[:16]
    asst_prefix = assistant_id.replace("asst_", "")[:8]
    return f"sess_wc_{asst_prefix}_{hash_part}"


class WechatChannelWorker:
    """Worker handling the long-polling loop and message dispatch for an Assistant."""

    def __init__(
        self,
        assistant_id: str,
        config: WechatChannelConfig,
        client: WechatIlinkClient,
        dispatch_fn: DispatchFunction,
        owns_client: bool = True,
    ) -> None:
        self.assistant_id = assistant_id
        self.config = config
        self.client = client
        self.dispatch_fn = dispatch_fn
        self._owns_client = owns_client

        self.cursor: str = ""
        self._context_tokens: dict[str, str] = {}
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._stopped = False
        self._task: asyncio.Task[None] | None = None
        self.status: str = "running"

    async def poll_step(self) -> None:
        """Perform a single iteration of the get_updates long-poll."""
        updates = await self.client.get_updates(
            bot_token=self.config.bot_token,
            cursor=self.cursor,
        )

        self.cursor = updates.get("get_updates_buf", self.cursor)
        msgs = updates.get("msgs", [])

        for msg in msgs:
            task = asyncio.create_task(self._handle_inbound_message(msg))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

    async def _handle_inbound_message(self, msg: dict[str, Any]) -> None:
        from_user = msg.get("from_user_id")
        if not from_user:
            return

        context_token = msg.get("context_token", "")
        if context_token:
            self._context_tokens[from_user] = context_token

        # Extract text items
        item_list = msg.get("item_list", [])
        text_parts = []
        for item in item_list:
            if item.get("type") == 1 and "text_item" in item:
                text_parts.append(item["text_item"].get("text", ""))

        inbound_text = "\n".join(text_parts).strip()
        if not inbound_text:
            return

        session_id = derive_wechat_session_id(self.assistant_id, from_user)
        typing_ticket = str(msg.get("typing_ticket") or "")

        # 1. Trigger typing indicator on WeChat client
        await self.client.send_typing(
            self.config.bot_token,
            from_user,
            typing_ticket,
            start=True,
        )

        # 2. Setup intermediate progress callback
        async def progress_callback(progress_text: str) -> None:
            if self.config.display_tool_calls:
                ctx_token = self._context_tokens.get(from_user, "")
                await self.client.send_message(
                    bot_token=self.config.bot_token,
                    to_user_id=from_user,
                    context_token=ctx_token,
                    text=progress_text,
                )

        # 3. Dispatch to Cognitive Engine
        try:
            reply_text = await self.dispatch_fn(
                self.assistant_id,
                session_id,
                inbound_text,
                progress_callback,
            )
        except Exception as exc:
            logger.exception("Error executing cognition loop for wechat user %s: %s", from_user, exc)
            reply_text = "抱歉，助理在处理该请求时遇到了内部错误，请稍后重试。"

        # 4. Deliver final answer
        ctx_token = self._context_tokens.get(from_user, "")
        if reply_text:
            await self.client.send_message(
                bot_token=self.config.bot_token,
                to_user_id=from_user,
                context_token=ctx_token,
                text=reply_text,
            )

        # 5. Stop typing indicator
        await self.client.send_typing(
            self.config.bot_token,
            from_user,
            typing_ticket,
            start=False,
        )

    async def start(self) -> None:
        """Start the worker in background asyncio task."""
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        for t in list(self._active_tasks):
            if not t.done():
                t.cancel()
        if self._owns_client:
            await self.client.close()

    async def _run_loop(self) -> None:
        backoff = 1.0
        while not self._stopped:
            try:
                await self.poll_step()
                backoff = 1.0
            except asyncio.CancelledError:
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.error("WeChat bot_token for assistant %s expired. Halting worker.", self.assistant_id)
                    self.status = "session_expired"
                    break
                logger.warning("Transient HTTP error in WeChat long-poll: %s. Backoff %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
            except Exception as exc:
                logger.warning("Error in WeChat worker loop: %s. Backoff %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

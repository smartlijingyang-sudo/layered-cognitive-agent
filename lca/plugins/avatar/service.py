"""Avatar 领域服务与状态机（ADR-0269 §4 / spec §7）。

create/edit 只生成候选进池（两轮分离，第一轮绝不自动激活）；set 校验候选在池
且未过期 → 拷为 active → 清空候选池 → 推 avatar_updated → 异步起视频；clear
恢复默认头像。唯一自动激活例外是 edit(auto_activate=True)，供定时换装调度器
（Task 8）使用。

视频异步流程：set 后把 active.video_status 置为 pending，后台任务轮询 provider
的 get_video 直到 ready/failed/超时；ready 后下载 mp4 落盘 video/<candidate_id>.mp4、
把 video_status 置为 ready 并推 avatar_video_ready；失败则置为 failed。视频失败
不得破坏 run。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from lca.contracts.models.avatar import (
    AVATAR_SIZES,
    CANDIDATE_TTL,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarUpdatedEvent,
    AvatarVariant,
    utcnow,
)
from lca.plugins.avatar.identity import load_identity
from lca.plugins.avatar.provider import VideoStatus

logger = logging.getLogger(__name__)

NUM_CANDIDATES = 4
VIDEO_POLL_INTERVAL_SECONDS = 5.0
VIDEO_POLL_TIMEOUT_SECONDS = 600.0


class StoreLike(Protocol):
    def load_state(self, assistant_id: str) -> AvatarState: ...
    def save_state(self, state: AvatarState) -> None: ...
    def write_image(
        self, assistant_id: str, candidate_id: str, size: str, data: bytes
    ) -> AvatarVariant: ...
    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes: ...
    def copy_candidate_to_active(
        self, assistant_id: str, candidate: AvatarCandidate
    ) -> AvatarActiveBundle: ...
    def write_video(self, assistant_id: str, candidate_id: str, data: bytes) -> str: ...
    def candidate_dir(self, candidate_id: str) -> Path: ...


class ProviderLike(Protocol):
    async def generate_image(
        self, prompt: str, reference_image_bytes: bytes | None = None
    ) -> bytes: ...
    async def create_video(self, image_bytes: bytes) -> str: ...
    async def get_video(self, task_id: str) -> VideoStatus: ...
    async def download(self, url: str) -> bytes: ...


class PublisherLike(Protocol):
    def publish(self, assistant_id: str, event: AvatarUpdatedEvent) -> None: ...


class AvatarService:
    def __init__(
        self,
        store: StoreLike,
        provider: ProviderLike,
        summarizer: Callable[[str], str],
        publisher: PublisherLike,
        home_resolver: Callable[[str], Path],
    ) -> None:
        self.store = store
        self.provider = provider
        self.summarizer = summarizer
        self.publisher = publisher
        self.home_resolver = home_resolver
        # 持有后台视频任务引用，避免被 GC；完成即从集合移除。
        self._video_tasks: set[asyncio.Task[None]] = set()

    def _build_prompt(self, user_request: str, identity: str) -> str:
        traits = self.summarizer(identity)
        return (
            f"{user_request}\n\nIdentity traits: {traits}\n"
            "Style: consistent character, high quality avatar portrait, centered."
        )

    async def _generate_candidates(
        self,
        assistant_id: str,
        kind: Literal["create", "edit"],
        user_request: str,
        reference: bytes | None,
    ) -> list[AvatarCandidate]:
        identity = load_identity(self.home_resolver(assistant_id))
        prompt = self._build_prompt(user_request, identity)
        now = utcnow()
        candidates: list[AvatarCandidate] = []
        for i in range(NUM_CANDIDATES):
            data = await self.provider.generate_image(prompt, reference_image_bytes=reference)
            candidate_id = f"{kind}-{now.strftime('%Y%m%d%H%M%S')}-{i}"
            variants = tuple(
                self.store.write_image(assistant_id, candidate_id, size, data)
                for size in AVATAR_SIZES
            )
            candidates.append(
                AvatarCandidate(
                    candidate_id=candidate_id,
                    assistant_id=assistant_id,
                    kind=kind,
                    prompt=prompt,
                    variants=variants,
                    created_at=now,
                    expires_at=now + CANDIDATE_TTL,
                )
            )
        return candidates

    async def create(self, assistant_id: str, user_request: str) -> list[AvatarCandidate]:
        candidates = await self._generate_candidates(
            assistant_id, "create", user_request, reference=None
        )
        state = self.store.load_state(assistant_id)
        self.store.save_state(
            state.model_copy(
                update={"candidates": state.candidates + candidates, "updated_at": utcnow()}
            )
        )
        return candidates

    async def edit(
        self,
        assistant_id: str,
        user_request: str,
        reference_image: bytes | None = None,
        auto_activate: bool = False,
    ) -> list[AvatarCandidate] | AvatarActiveBundle:
        state = self.store.load_state(assistant_id)
        reference = reference_image
        if reference is None and state.active is not None:
            reference = self.store.read_image(assistant_id, state.active.candidate_id, "original")
        candidates = await self._generate_candidates(
            assistant_id, "edit", user_request, reference=reference
        )
        if not auto_activate:
            self.store.save_state(
                state.model_copy(
                    update={"candidates": state.candidates + candidates, "updated_at": utcnow()}
                )
            )
            return candidates
        candidate = candidates[0]
        bundle = self.store.copy_candidate_to_active(assistant_id, candidate)
        self.store.save_state(
            state.model_copy(update={"active": bundle, "candidates": [], "updated_at": utcnow()})
        )
        self.publisher.publish(
            assistant_id,
            AvatarUpdatedEvent(
                type="avatar_updated",
                assistant_id=assistant_id,
                payload={"candidate_id": candidate.candidate_id},
            ),
        )
        return self._start_video(assistant_id, candidate)

    async def set(self, assistant_id: str, candidate_id: str) -> AvatarActiveBundle:
        state = self.store.load_state(assistant_id)
        now = utcnow()
        candidate = next((c for c in state.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            # 幂等：同一候选已激活（候选池可能在首次 set 后被清空）→ 返回当前 active。
            if state.active is not None and state.active.candidate_id == candidate_id:
                return state.active
            raise ValueError(f"candidate not found: {candidate_id}")
        if candidate.is_expired(now):
            raise ValueError(f"candidate expired: {candidate_id}")
        bundle = self.store.copy_candidate_to_active(assistant_id, candidate)
        self.store.save_state(
            state.model_copy(update={"active": bundle, "candidates": [], "updated_at": now})
        )
        self.publisher.publish(
            assistant_id,
            AvatarUpdatedEvent(
                type="avatar_updated",
                assistant_id=assistant_id,
                payload={"candidate_id": candidate_id},
            ),
        )
        return self._start_video(assistant_id, candidate)

    def _start_video(self, assistant_id: str, candidate: AvatarCandidate) -> AvatarActiveBundle:
        """把 active.video_status 置为 pending，并异步启动视频完成流程。"""
        state = self.store.load_state(assistant_id)
        if state.active is None or state.active.candidate_id != candidate.candidate_id:
            raise ValueError(f"active avatar not set for {assistant_id}")
        active = state.active.model_copy(update={"video_status": "pending"})
        self.store.save_state(state.model_copy(update={"active": active, "updated_at": utcnow()}))

        async def worker() -> None:
            try:
                original = self.store.read_image(assistant_id, candidate.candidate_id, "original")
                await self._complete_video(assistant_id, candidate.candidate_id, original)
            except Exception:
                logger.exception("avatar video generation failed for %s", candidate.candidate_id)
                try:
                    self._persist_video_status(assistant_id, candidate.candidate_id, "failed")
                except Exception:
                    logger.exception(
                        "failed to persist avatar video_status=failed for %s",
                        candidate.candidate_id,
                    )

        task = asyncio.create_task(worker())
        self._video_tasks.add(task)
        task.add_done_callback(self._video_tasks.discard)
        return active

    async def _complete_video(
        self, assistant_id: str, candidate_id: str, image_bytes: bytes
    ) -> None:
        """创建视频任务并轮询直到 ready/failed/超时；完成时落盘并更新状态。"""
        task_id = await self.provider.create_video(image_bytes)
        deadline = time.monotonic() + VIDEO_POLL_TIMEOUT_SECONDS
        url: str | None = None
        while True:
            status = await self.provider.get_video(task_id)
            if status.state == "ready":
                url = status.url
                break
            if status.state == "failed":
                self._persist_video_status(assistant_id, candidate_id, "failed")
                return
            if time.monotonic() >= deadline:
                self._persist_video_status(assistant_id, candidate_id, "failed")
                return
            await asyncio.sleep(VIDEO_POLL_INTERVAL_SECONDS)
        if url is None:
            self._persist_video_status(assistant_id, candidate_id, "failed")
            return
        data = await self.provider.download(url)
        video_path = self.store.write_video(assistant_id, candidate_id, data)
        if self._persist_video_status(assistant_id, candidate_id, "ready"):
            self.publisher.publish(
                assistant_id,
                AvatarUpdatedEvent(
                    type="avatar_video_ready",
                    assistant_id=assistant_id,
                    payload={
                        "candidate_id": candidate_id,
                        "video_status": "ready",
                        "file_path": video_path,
                    },
                ),
            )

    def _persist_video_status(
        self,
        assistant_id: str,
        candidate_id: str,
        status: Literal["none", "pending", "ready", "failed"],
    ) -> bool:
        """把 active.video_status 写入状态；active 已不是该候选时返回 False。"""
        state = self.store.load_state(assistant_id)
        if state.active is None or state.active.candidate_id != candidate_id:
            return False
        active = state.active.model_copy(update={"video_status": status})
        self.store.save_state(state.model_copy(update={"active": active, "updated_at": utcnow()}))
        return True

    async def get(self, assistant_id: str) -> AvatarState:
        return self.store.load_state(assistant_id)

    async def clear(self, assistant_id: str) -> AvatarState:
        state = self.store.load_state(assistant_id)
        new_state = state.model_copy(
            update={"active": None, "candidates": [], "updated_at": utcnow()}
        )
        self.store.save_state(new_state)
        self.publisher.publish(
            assistant_id,
            AvatarUpdatedEvent(
                type="avatar_updated",
                assistant_id=assistant_id,
                payload={"active": None},
            ),
        )
        return new_state

"""Avatar 领域服务状态机测试（Task 5）。

覆盖：
- create 生成 4 个候选但不激活（两轮分离铁律，ADR-0269 §4）；
- set 激活候选、清空候选池、幂等返回同一 active、过期/未知候选抛 ValueError；
- edit 默认读当前 active 原图做 img2img，也可显式传参考图；
- edit(auto_activate=True) 立即激活第一个候选并异步起视频（定时换装路径）；
- clear 恢复默认头像；
- 视频完成：轮询 ready → 落盘 mp4 → video_status=ready → 推 avatar_video_ready；
- 视频失败/超时：video_status=failed 且不抛异常。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

import pytest

from lca.contracts.models.avatar import (
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarUpdatedEvent,
    AvatarVariant,
)
from lca.plugins.avatar.provider import VideoStatus
from lca.plugins.avatar.service import AvatarService

NUM_CANDIDATES = 4

AvatarSize = Literal["original", "small", "medium", "large"]


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.video_state: Literal["pending", "running", "ready", "failed"] = "ready"
        self.video_url = "http://test/video.mp4"
        self.video_bytes = b"mp4-bytes"
        self.download_error: Exception | None = None

    async def generate_image(
        self, prompt: str, reference_image_bytes: bytes | None = None
    ) -> bytes:
        self.calls.append(("gen", reference_image_bytes is not None))
        return f"img-{len(self.calls) - 1}".encode()

    async def create_video(self, image_bytes: bytes) -> str:
        return "task-1"

    async def get_video(self, task_id: str) -> VideoStatus:
        return VideoStatus(
            task_id=task_id,
            state=self.video_state,
            url=self.video_url if self.video_state == "ready" else None,
        )

    async def download(self, url: str) -> bytes:
        if self.download_error is not None:
            raise self.download_error
        return self.video_bytes


class FakeStore:
    def __init__(self, assistant_id: str = "asst_1") -> None:
        self.state = AvatarState(
            assistant_id=assistant_id,
            active=None,
            candidates=[],
            updated_at=datetime(2026, 10, 2, tzinfo=UTC),
        )
        self.copied: AvatarCandidate | None = None
        self.written_videos: list[tuple[str, bytes]] = []

    def load_state(self, assistant_id: str) -> AvatarState:
        return self.state

    def save_state(self, state: AvatarState) -> None:
        self.state = state

    def write_image(
        self, assistant_id: str, candidate_id: str, size: str, data: bytes
    ) -> AvatarVariant:
        return AvatarVariant(
            size=cast("AvatarSize", size),
            file_path=f"candidates/{candidate_id}/{size}.png",
            url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/candidates/{candidate_id}/{size}.png",
            width=512,
            height=512,
        )

    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes:
        return b"active-bytes"

    def copy_candidate_to_active(
        self, assistant_id: str, candidate: AvatarCandidate
    ) -> AvatarActiveBundle:
        self.copied = candidate
        return AvatarActiveBundle(
            candidate_id=candidate.candidate_id,
            variants=candidate.variants,
            activated_at=datetime(2026, 10, 2, tzinfo=UTC),
        )

    def write_video(self, assistant_id: str, candidate_id: str, data: bytes) -> str:
        self.written_videos.append((candidate_id, data))
        return f"video/{candidate_id}.mp4"

    def cleanup_expired(self, now: datetime) -> int:
        return 0

    def candidate_dir(self, candidate_id: str) -> Path:
        return Path("candidates") / candidate_id


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, AvatarUpdatedEvent]] = []

    def publish(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        self.events.append((assistant_id, event))


def _service(
    provider: FakeProvider | None = None,
) -> tuple[AvatarService, FakeStore, FakeProvider, FakePublisher]:
    store = FakeStore()
    provider = provider or FakeProvider()
    publisher = FakePublisher()
    svc = AvatarService(
        store=store,
        provider=provider,
        summarizer=lambda identity: "traits",
        publisher=publisher,
        home_resolver=lambda assistant_id: Path("/nonexistent-avatar-home"),
    )
    return svc, store, provider, publisher


async def _settle() -> None:
    """让异步视频任务跑完，避免遗留 pending task。"""
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_create_generates_candidates_without_activating():
    svc, store, _, _ = _service()
    candidates = await svc.create("asst_1", "换个赛博朋克头像")
    assert len(candidates) == NUM_CANDIDATES
    assert store.state.active is None
    assert len(store.state.candidates) == NUM_CANDIDATES
    assert all(c.kind == "create" for c in candidates)


@pytest.mark.asyncio
async def test_set_activates_and_clears_pool():
    svc, store, _, _ = _service()
    candidates = await svc.create("asst_1", "换个头像")
    bundle = await svc.set("asst_1", candidates[0].candidate_id)
    assert bundle.candidate_id == candidates[0].candidate_id
    assert store.state.active is not None
    assert store.state.active.candidate_id == candidates[0].candidate_id
    assert store.state.candidates == []
    assert store.copied is not None
    await _settle()
    assert store.state.active.video_status == "ready"


@pytest.mark.asyncio
async def test_set_expired_candidate_raises():
    svc, store, _, _ = _service()
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    expired = AvatarCandidate(
        candidate_id="old",
        assistant_id="asst_1",
        kind="create",
        prompt="p",
        variants=(),
        created_at=now - timedelta(hours=25),
        expires_at=now - timedelta(hours=1),
    )
    store.state = AvatarState(
        assistant_id="asst_1", active=None, candidates=[expired], updated_at=now
    )
    with pytest.raises(ValueError):
        await svc.set("asst_1", "old")


@pytest.mark.asyncio
async def test_set_unknown_candidate_raises():
    svc, _, _, _ = _service()
    with pytest.raises(ValueError):
        await svc.set("asst_1", "nope")


@pytest.mark.asyncio
async def test_set_is_idempotent_returns_active():
    svc, store, _, _ = _service()
    candidates = await svc.create("asst_1", "头像")
    first = await svc.set("asst_1", candidates[0].candidate_id)
    second = await svc.set("asst_1", candidates[0].candidate_id)
    assert second == first
    assert store.state.active == first
    await _settle()


@pytest.mark.asyncio
async def test_get_returns_state():
    svc, store, _, _ = _service()
    state = await svc.get("asst_1")
    assert state == store.state


@pytest.mark.asyncio
async def test_edit_uses_active_image_as_reference():
    svc, store, provider, _ = _service()
    candidates = await svc.create("asst_1", "基础")
    await svc.set("asst_1", candidates[0].candidate_id)
    await svc.edit("asst_1", "换件圣诞毛衣")
    assert any(kind == ("gen", True) for kind in provider.calls)
    assert len(store.state.candidates) == NUM_CANDIDATES
    assert store.state.active is not None
    await _settle()


@pytest.mark.asyncio
async def test_edit_without_active_uses_no_reference():
    svc, store, provider, _ = _service()
    await svc.edit("asst_1", "改")
    assert ("gen", False) in provider.calls
    assert len(store.state.candidates) == NUM_CANDIDATES


@pytest.mark.asyncio
async def test_edit_with_explicit_reference_image():
    svc, _, provider, _ = _service()
    await svc.edit("asst_1", "改", reference_image=b"uploaded")
    assert ("gen", True) in provider.calls


@pytest.mark.asyncio
async def test_edit_auto_activate_activates_first_candidate():
    svc, store, _, publisher = _service()
    result = await svc.edit("asst_1", "定时换装", auto_activate=True)
    assert isinstance(result, AvatarActiveBundle)
    assert store.state.active is not None
    assert store.state.active.candidate_id == result.candidate_id
    assert store.state.candidates == []
    assert [ev.type for _, ev in publisher.events] == ["avatar_updated"]
    await _settle()
    assert store.state.active.video_status == "ready"
    assert [ev.type for _, ev in publisher.events] == ["avatar_updated", "avatar_video_ready"]


@pytest.mark.asyncio
async def test_video_completion_persists_ready_and_publishes():
    svc, store, _, publisher = _service()
    candidates = await svc.create("asst_1", "头像")
    await svc.set("asst_1", candidates[0].candidate_id)
    assert store.state.active.video_status == "pending"
    await _settle()
    assert store.written_videos == [(candidates[0].candidate_id, b"mp4-bytes")]
    assert store.state.active.video_status == "ready"
    ready_events = [ev for _, ev in publisher.events if ev.type == "avatar_video_ready"]
    assert len(ready_events) == 1
    assert ready_events[0].payload["candidate_id"] == candidates[0].candidate_id
    assert ready_events[0].payload["video_status"] == "ready"


@pytest.mark.asyncio
async def test_video_failure_marks_failed():
    provider = FakeProvider()
    provider.video_state = "failed"
    svc, store, _, publisher = _service(provider=provider)
    candidates = await svc.create("asst_1", "头像")
    await svc.set("asst_1", candidates[0].candidate_id)
    assert store.state.active.video_status == "pending"
    await _settle()
    assert store.state.active.video_status == "failed"
    assert not any(ev.type == "avatar_video_ready" for _, ev in publisher.events)


@pytest.mark.asyncio
async def test_video_download_failure_marks_failed():
    provider = FakeProvider()
    provider.download_error = RuntimeError("download failed")
    svc, store, _, _ = _service(provider=provider)
    candidates = await svc.create("asst_1", "头像")
    await svc.set("asst_1", candidates[0].candidate_id)
    await _settle()
    assert store.state.active.video_status == "failed"


@pytest.mark.asyncio
async def test_video_poll_timeout_marks_failed(monkeypatch):
    import lca.plugins.avatar.service as service_mod

    monkeypatch.setattr(service_mod, "VIDEO_POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(service_mod, "VIDEO_POLL_TIMEOUT_SECONDS", 0.01)
    provider = FakeProvider()
    provider.video_state = "pending"
    svc, store, _, _ = _service(provider=provider)
    candidates = await svc.create("asst_1", "头像")
    await svc.set("asst_1", candidates[0].candidate_id)
    await asyncio.sleep(0.2)
    assert store.state.active.video_status == "failed"


@pytest.mark.asyncio
async def test_clear_resets_to_default():
    svc, store, _, publisher = _service()
    candidates = await svc.create("asst_1", "头像")
    await svc.set("asst_1", candidates[0].candidate_id)
    state = await svc.clear("asst_1")
    assert state.active is None
    assert state.candidates == []
    assert store.state.active is None
    assert any(
        ev.type == "avatar_updated" and ev.payload.get("active") is None
        for _, ev in publisher.events
    )
    await _settle()

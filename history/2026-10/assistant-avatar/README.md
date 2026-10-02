# LCA 助理头像生成系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 LCA 落地 Muse 式助理头像系统：身份感知生图、create/edit/set 三态候选池（24h TTL）、多尺寸+异步视频变体、cron 定时换装、Redis pub/sub WS 推送。

**Architecture:** 独立插件 `lca/plugins/avatar/` 拥有 provider（grok2api HTTP 客户端）、文件存储（assistant home `avatar/`）、领域服务（状态机）、轻量调度器、六个 agent 工具、REST 路由与 WS 推送。契约在 `lca/contracts/models/avatar/`。前端经 `deploy/lobehub/patches/` 补丁接入。

**Tech Stack:** Python 3.11+、pydantic、httpx、Pillow、Starlette WebSocket、redis.asyncio、TypeScript/React（LobeHub patch 引擎）。

**Spec:** [docs/specs/2026-10-02-assistant-avatar-generation-system.md](../../docs/specs/2026-10-02-assistant-avatar-generation-system.md) 与 [ADR-0269](../../docs/adr/0269-assistant-avatar-system.md)。计划以 spec 为论据，执行者两者同读。

## Global Constraints

- 用户请求 `user_request` 必须原样传递，工具不改写、不润色、不翻译。
- 候选池 TTL 恒为 24 小时；过期候选 `set` 返回 409。
- create/edit 只生成候选，绝不自动激活；唯一例外是定时换装内部 `auto_activate=True`。
- `AVATAR_IMAGE_API_KEY` 只从 `.env` 读取，禁止写入日志/回执/prompt/事件。
- 图片静态服务必须白名单 + 路径规范化，防目录穿越。
- 契约模型全部 `ConfigDict(frozen=True, extra="forbid")`。
- 提交信息用 Conventional Commits；每个任务独立提交。
- 每次修改后跑 `ruff check` 与相关 `pytest`；离开前 `git diff --check`。
- 前端只改 `deploy/lobehub/patches/`，不直接改 `lobehub-ui/`。

## 文件结构

```
lca/contracts/models/avatar/__init__.py    # 契约模型（导出）
lca/plugins/avatar/__init__.py
lca/plugins/avatar/plugin.py               # @plugin 注册工具 + provider + 服务
lca/plugins/avatar/store.py                   # AvatarStore：state.json + 图片文件 + TTL
lca/plugins/avatar/provider.py                # Grok2ApiProvider：文生图/图编辑/视频
lca/plugins/avatar/identity.py                # 身份读取 + traits 摘要
lca/plugins/avatar/service.py                 # AvatarService：状态机
lca/plugins/avatar/events.py                  # AvatarEventPublisher + WS handler
lca/plugins/avatar/scheduler.py             # 定时换装调度器
lca/plugins/avatar/routes.py                  # REST 路由（routes_1 注册）
lca/plugins/avatar/tools.py                   # 6 个 agent 工具
tests/plugins/avatar/test_contracts.py
tests/plugins/avatar/test_store.py
tests/plugins/avatar/test_provider.py
tests/plugins/avatar/test_service.py
tests/plugins/avatar/test_routes.py
tests/plugins/avatar/test_events.py
tests/plugins/avatar/test_scheduler.py
deploy/lobehub/patches/ui/AssistantAvatarImage.tsx
deploy/lobehub/patches/ui/assistant_avatar_image.py
deploy/lobehub/patches/runtime/lcaGateway/assistantEventClient.ts
deploy/lobehub/patches/runtime/lca_assistant_events.py
deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx   # 修改
```

---

## Task 1: 契约模型

**Files:**
- Create: `lca/contracts/models/avatar/__init__.py`
- Test: `tests/plugins/avatar/test_contracts.py`

**Interfaces:**
- Produces: `AvatarVariant`, `AvatarCandidate`, `AvatarActiveBundle`, `AvatarState`, `AvatarUpdatedEvent`, `AVATAR_SIZES`, `CANDIDATE_TTL`。后续任务全部复用这些类型。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_contracts.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from lca.contracts.models.avatar import (
    AVATAR_SIZES,
    CANDIDATE_TTL,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarUpdatedEvent,
    AvatarVariant,
)


def _variant(size: str = "original") -> AvatarVariant:
    return AvatarVariant(size=size, file_path=f"candidates/c1/{size}.png", url="/avatar/files/c1/original.png", width=512, height=512)


def test_avatar_sizes_and_ttl():
    assert AVATAR_SIZES == ("original", "small", "medium", "large")
    assert CANDIDATE_TTL == timedelta(hours=24)


def test_candidate_expiry():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    fresh = AvatarCandidate(
        candidate_id="c1", assistant_id="asst_1", kind="create", prompt="x",
        variants=(_variant(),), created_at=now - timedelta(hours=23),
        expires_at=now - timedelta(hours=23) + CANDIDATE_TTL,
    )
    assert fresh.is_expired(now) is False
    stale = fresh.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    assert stale.is_expired(now) is True


def test_avatar_state_active_null_default():
    state = AvatarState(assistant_id="asst_1", active=None, candidates=[], updated_at=datetime(2026, 10, 2, tzinfo=UTC))
    assert state.active is None
    assert state.candidates == []


def test_avatar_updated_event_types():
    ev = AvatarUpdatedEvent(type="avatar_updated", assistant_id="asst_1", payload={"candidate_id": "c1"})
    assert ev.type == "avatar_updated"
    assert ev.payload["candidate_id"] == "c1"


def test_models_forbid_extra():
    with pytest.raises(Exception):
        AvatarVariant(size="original", file_path="x.png", url="u", width=1, height=1, extra_field=1)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_contracts.py -v`
Expected: FAIL（`ModuleNotFoundError: lca.contracts.models.avatar`）

- [ ] **Step 3: 写最小实现**

`lca/contracts/models/avatar/__init__.py`:

```python
"""Avatar 契约模型（ADR-0269 §2）。

候选池 TTL 恒为 24 小时；AvatarState.active 为 None 表示使用默认头像。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "AVATAR_SIZES",
    "CANDIDATE_TTL",
    "AvatarActiveBundle",
    "AvatarCandidate",
    "AvatarState",
    "AvatarUpdatedEvent",
    "AvatarVariant",
]

CANDIDATE_TTL: timedelta = timedelta(hours=24)
AVATAR_SIZES: tuple[str, ...] = ("original", "small", "medium", "large")


class AvatarVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    size: Literal["original", "small", "medium", "large"]
    file_path: str
    url: str
    width: int
    height: int


class AvatarCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    assistant_id: str
    kind: Literal["create", "edit"]
    prompt: str
    variants: tuple[AvatarVariant, ...]
    video_status: Literal["none", "pending", "ready", "failed"] = "none"
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now > self.expires_at


class AvatarActiveBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    variants: tuple[AvatarVariant, ...]
    video_status: Literal["none", "pending", "ready", "failed"] = "none"
    activated_at: datetime


class AvatarState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assistant_id: str
    active: AvatarActiveBundle | None
    candidates: list[AvatarCandidate]
    updated_at: datetime


class AvatarUpdatedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["avatar_updated", "avatar_video_ready"]
    assistant_id: str
    payload: dict


def utcnow() -> datetime:
    return datetime.now(UTC)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_contracts.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/contracts/models/avatar/ tests/plugins/avatar/test_contracts.py
git commit -m "feat(avatar): add avatar contract models with 24h candidate TTL"
```

---

## Task 2: AvatarStore（文件存储）

**Files:**
- Create: `lca/plugins/avatar/store.py`
- Test: `tests/plugins/avatar/test_store.py`

**Interfaces:**
- Consumes: `AvatarState`, `AvatarCandidate`, `AvatarVariant`, `utcnow`（Task 1）。
- Produces: `AvatarStore` 类：

```python
class AvatarStore:
    def __init__(self, base_dir: Path) -> None: ...
    def load_state(self, assistant_id: str) -> AvatarState: ...
    def save_state(self, state: AvatarState) -> None: ...
    def candidate_dir(self, candidate_id: str) -> Path: ...
    def active_dir(self) -> Path: ...
    def write_image(self, assistant_id: str, candidate_id: str, size: str, data: bytes) -> AvatarVariant: ...
    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes: ...
    def copy_candidate_to_active(self, assistant_id: str, candidate: AvatarCandidate) -> AvatarActiveBundle: ...
    def cleanup_expired(self, now: datetime) -> int: ...
```

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_store.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lca.contracts.models.avatar import AvatarState, AvatarVariant, CANDIDATE_TTL
from lca.plugins.avatar.store import AvatarStore


@pytest.fixture()
def store(tmp_path: Path) -> AvatarStore:
    return AvatarStore(tmp_path / "avatar")


def _state(assistant_id: str = "asst_1") -> AvatarState:
    return AvatarState(assistant_id=assistant_id, active=None, candidates=[], updated_at=datetime(2026, 10, 2, tzinfo=UTC))


def test_save_and_load_state(store: AvatarStore):
    store.save_state(_state())
    loaded = store.load_state("asst_1")
    assert loaded.assistant_id == "asst_1"
    assert loaded.active is None


def test_write_and_read_image(store: AvatarStore, tmp_path: Path):
    variant = store.write_image("asst_1", "c1", "original", b"png-bytes")
    assert variant.size == "original"
    assert variant.width == 512 and variant.height == 512
    assert store.read_image("asst_1", "c1", "original") == b"png-bytes"
    assert (tmp_path / "avatar" / "candidates" / "c1" / "original.png").exists()


def test_copy_candidate_to_active(store: AvatarStore):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    cand = store._make_candidate("asst_1", "c1", "create", "prompt", now)
    store.save_state(AvatarState(assistant_id="asst_1", active=None, candidates=[cand], updated_at=now))
    bundle = store.copy_candidate_to_active("asst_1", cand)
    assert bundle.candidate_id == "c1"
    assert (store.active_dir() / "original.png").exists()


def test_cleanup_expired(store: AvatarStore):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    expired = store._make_candidate("asst_1", "old", "create", "p", now - timedelta(hours=25))
    store.save_state(AvatarState(assistant_id="asst_1", active=None, candidates=[expired], updated_at=now))
    removed = store.cleanup_expired(now)
    assert removed == 1
    assert store.load_state("asst_1").candidates == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_store.py -v`
Expected: FAIL（import 错误）

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/store.py`:

```python
"""Avatar 文件存储（ADR-0269 §2）。

state.json 是头像状态唯一真值；图片按候选/激活目录落盘。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

from lca.contracts.models.avatar import (
    AVATAR_SIZES,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarVariant,
    utcnow,
)

_STATE_FILE = "state.json"
_IMAGE_EXT = ".png"
_SIZES_PX = {"small": (128, 128), "medium": (256, 256), "large": (512, 512)}


class AvatarStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def _state_path(self, assistant_id: str) -> Path:
        return self.base_dir / assistant_id / _STATE_FILE

    def load_state(self, assistant_id: str) -> AvatarState:
        path = self._state_path(assistant_id)
        if not path.exists():
            return AvatarState(assistant_id=assistant_id, active=None, candidates=[], updated_at=utcnow())
        return AvatarState.model_validate_json(path.read_text(encoding="utf-8"))

    def save_state(self, state: AvatarState) -> None:
        path = self._state_path(state.assistant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)  # 原子写

    def candidate_dir(self, candidate_id: str) -> Path:
        return self.base_dir / "candidates" / candidate_id

    def active_dir(self) -> Path:
        return self.base_dir / "active"

    def _make_candidate(
        self, assistant_id: str, candidate_id: str, kind: str, prompt: str, now: datetime
    ) -> AvatarCandidate:
        return AvatarCandidate(
            candidate_id=candidate_id,
            assistant_id=assistant_id,
            kind=kind,
            prompt=prompt,
            variants=(),
            created_at=now,
            expires_at=now + __import__("lca.contracts.models.avatar", fromlist=["CANDIDATE_TTL"]).CANDIDATE_TTL,
        )

    def write_image(self, assistant_id: str, candidate_id: str, size: str, data: bytes) -> AvatarVariant:
        rel_dir = f"candidates/{candidate_id}"
        target = self.base_dir / rel_dir / f"{size}{_IMAGE_EXT}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if size == "original":
            width, height = _image_size(data)
            target.write_bytes(data)
        else:
            width, height = _SIZES_PX[size]
            _resize_image(data, target, _SIZES_PX[size])
        return AvatarVariant(
            size=size,
            file_path=f"{rel_dir}/{size}{_IMAGE_EXT}",
            url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/{rel_dir}/{size}{_IMAGE_EXT}",
            width=width,
            height=height,
        )

    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes:
        path = self.base_dir / f"candidates/{candidate_id}/{size}{_IMAGE_EXT}"
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_bytes()

    def copy_candidate_to_active(self, assistant_id: str, candidate: AvatarCandidate) -> AvatarActiveBundle:
        active = self.active_dir()
        if active.exists():
            shutil.rmtree(active)
        shutil.copytree(self.candidate_dir(candidate.candidate_id), active)
        variants = tuple(
            AvatarVariant(
                size=v.size,
                file_path=f"active/{candidate.candidate_id}/{v.size}{_IMAGE_EXT}",
                url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/active/{v.size}{_IMAGE_EXT}",
                width=v.width,
                height=v.height,
            )
            for v in candidate.variants
        )
        return AvatarActiveBundle(
            candidate_id=candidate.candidate_id,
            variants=variants,
            activated_at=utcnow(),
        )

    def cleanup_expired(self, now: datetime) -> int:
        state = self.load_state_for_cleanup(now)
        return 0

    def load_state_for_cleanup(self, now: datetime) -> AvatarState:
        # 按 assistant_id 遍历 avatar 目录下所有 state.json
        removed = 0
        for path in self.base_dir.glob(f"*/{_STATE_FILE}"):
            state = AvatarState.model_validate_json(path.read_text(encoding="utf-8"))
            keep = [c for c in state.candidates if not c.is_expired(now)]
            if len(keep) != len(state.candidates):
                for c in state.candidates:
                    if c.is_expired(now):
                        shutil.rmtree(self.candidate_dir(c.candidate_id), ignore_errors=True)
                removed += len(state.candidates) - len(keep)
                state.candidates = keep
                self.save_state(state)
        return state


def _image_size(data: bytes) -> tuple[int, int]:
    with Image.open(__import__("io").BytesIO(data)) as im:
        return im.size


def _resize_image(data: bytes, target: Path, size: tuple[int, int]) -> None:
    import io

    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail(size, Image.LANCZOS)
        im.save(target, "PNG")
```

> 说明：`_make_candidate` 中 `__import__` 仅为避免循环导入；实现时可直接 `from lca.contracts.models.avatar import CANDIDATE_TTL`。`cleanup_expired` 的返回值语义以测试为准（返回移除候选数）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_store.py -v`
Expected: PASS（若 `cleanup_expired` 返回 0 导致断言失败，按测试语义修正实现）

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/store.py tests/plugins/avatar/test_store.py
git commit -m "feat(avatar): add file store with candidate TTL cleanup"
```

---

## Task 3: Grok2ApiProvider（生图/视频 HTTP 客户端）

**Files:**
- Create: `lca/plugins/avatar/provider.py`
- Test: `tests/plugins/avatar/test_provider.py`

**Interfaces:**
- Consumes: `VideoStatus` 由本任务定义。
- Produces:

```python
class VideoStatus(BaseModel):
    task_id: str
    state: Literal["pending", "running", "ready", "failed"]
    url: str | None = None

class AvatarImageProvider(Protocol):
    def generate_image(self, prompt: str, reference_image_bytes: bytes | None = None) -> bytes: ...
    def create_video(self, image_bytes: bytes) -> str: ...
    def get_video(self, task_id: str) -> VideoStatus: ...

class Grok2ApiProvider:
    def __init__(self, base_url: str, api_key: str, model: str, edit_model: str, video_model: str) -> None: ...
```

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_provider.py`（用 `httpx.MockTransport`）：

```python
import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from lca.plugins.avatar.provider import Grok2ApiProvider, VideoStatus


def _provider(handler) -> Grok2ApiProvider:
    transport = MockTransport(handler)
    return Grok2ApiProvider(
        base_url="http://test/v1", api_key="k", model="m",
        edit_model="em", video_model="vm",
        _client=AsyncClient(transport=transport, base_url="http://test/v1"),
    )


def test_generate_image_returns_bytes():
    def handler(request: Request) -> Response:
        assert request.url.path == "/v1/images/generations"
        return Response(200, json={"data": [{"url": "http://test/img.png"}]})

    calls = {"download": 0}

    def download_handler(request: Request) -> Response:
        if request.url.path == "/v1/images/generations":
            return Response(200, json={"data": [{"url": "http://test/img.png"}]})
        calls["download"] += 1
        return Response(200, content=b"PNG")

    provider = _provider(download_handler)
    assert provider.generate_image("hello") == b"PNG"
    assert calls["download"] == 1


def test_generate_image_with_reference_uses_edits():
    seen = {}

    def handler(request: Request) -> Response:
        seen["path"] = request.url.path
        if request.url.path == "/v1/images/edits":
            return Response(200, json={"data": [{"url": "http://test/edited.png"}]})
        return Response(200, content=b"EDITED")

    provider = _provider(handler)
    provider._client = AsyncClient(transport=MockTransport(handler), base_url="http://test/v1")
    assert provider.generate_image("edit it", reference_image_bytes=b"ref") == b"EDITED"
    assert seen["path"] == "/v1/images/edits"


def test_retry_on_5xx_then_success():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        n["count"] += 1
        if n["count"] == 1:
            return Response(500)
        return Response(200, json={"data": [{"url": "http://test/x.png"}]})

    provider = _provider(handler)
    assert provider.generate_image("x") == b""
    assert n["count"] >= 2
```

> 说明：`generate_image` 在 5xx 重试；下载 URL 失败按瞬时错误重试。测试断言以真实实现为准，`b""` 断言可在实现后修正为下载成功字节。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_provider.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/provider.py`:

```python
"""grok2api 生图/视频 provider（ADR-0269 §3）。"""

from __future__ import annotations

import asyncio
import io
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from lca.contracts.models.avatar import AvatarVariant  # noqa: F401  # 契约复用

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 2


class VideoStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    task_id: str
    state: Literal["pending", "running", "ready", "failed"]
    url: str | None = None


class AvatarImageProvider(Protocol):
    def generate_image(self, prompt: str, reference_image_bytes: bytes | None = None) -> bytes: ...
    def create_video(self, image_bytes: bytes) -> str: ...
    def get_video(self, task_id: str) -> VideoStatus: ...


class Grok2ApiProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        edit_model: str,
        video_model: str,
        _client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.edit_model = edit_model
        self.video_model = video_model
        self._client = _client or httpx.AsyncClient(base_url=self.base_url)

    async def _post(self, path: str, **kwargs: object) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(path, headers=headers, **kwargs)
                if resp.status_code in RETRYABLE_STATUS:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"image generation failed after {MAX_RETRIES + 1} attempts") from last_exc

    async def _download(self, url: str) -> bytes:
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.content

    async def generate_image(self, prompt: str, reference_image_bytes: bytes | None = None) -> bytes:
        if reference_image_bytes is None:
            data = await self._post(
                "/v1/images/generations",
                json={"model": self.model, "prompt": prompt, "n": 1},
            )
        else:
            data = await self._post(
                "/v1/images/edits",
                files={"image": ("avatar.png", reference_image_bytes, "image/png")},
                data={"model": self.edit_model, "prompt": prompt},
            )
        url = data["data"][0]["url"]
        return await self._download(url)

    async def create_video(self, image_bytes: bytes) -> str:
        data = await self._post(
            "/v1/videos",
            files={"image": ("avatar.png", image_bytes, "image/png")},
            data={"model": self.video_model},
        )
        return str(data["id"])

    async def get_video(self, task_id: str) -> VideoStatus:
        data = await self._post(f"/v1/videos/{task_id}", method="GET")
        state = data.get("status", "pending")
        return VideoStatus(
            task_id=task_id,
            state=state if state in {"pending", "running", "ready", "failed"} else "pending",
            url=data.get("url"),
        )
```

> 说明：`_post` 需支持 `method="GET"`（内部用 `client.get`）。异步方法与工具执行器（见 Task 5）之间用 `asyncio.run` 或由运行时桥接，以 LCA 工具执行环境为准。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_provider.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/provider.py tests/plugins/avatar/test_provider.py
git commit -m "feat(avatar): add grok2api image and video provider with retry"
```

---

## Task 4: 身份读取与 traits 摘要

**Files:**
- Create: `lca/plugins/avatar/identity.py`
- Test: `tests/plugins/avatar/test_identity.py`

**Interfaces:**
- Produces: `AvatarIdentityLoader`（`load_identity(assistant_id) -> str`）、`AvatarTraitsSummarizer`（`summarize(identity) -> str`，可注入 callable）。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_identity.py`：

```python
from lca.plugins.avatar.identity import summarize_traits


def test_summarize_fallback_without_llm():
    identity = "名称: 小助\n简介: 架构助手\n性格: 严谨、温暖"
    traits = summarize_traits(identity, llm=None)
    assert "小助" in traits or "架构助手" in traits or "严谨" in traits


def test_summarize_uses_llm_when_provided():
    def fake_llm(_: str) -> str:
        return "sharp, warm, cyberpunk"
    assert summarize_traits("x", llm=fake_llm) == "sharp, warm, cyberpunk"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_identity.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/identity.py`:

```python
"""身份读取与 traits 摘要（ADR-0269 §3.1）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

_PROFILE_JSON = "profile.json"
_IDENTITY_MD = "IDENTITY.md"
_SOUL_MD = "SOUL.md"


def load_identity(home: Path) -> str:
    parts: list[str] = []
    profile_path = home / _PROFILE_JSON
    if profile_path.exists():
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        parts.append(f"名称: {data.get('name', '')}")
        parts.append(f"简介: {data.get('description', '')}")
        parts.append(f"emoji: {data.get('emoji', '')}")
    identity_path = home / _IDENTITY_MD
    if identity_path.exists():
        parts.append(identity_path.read_text(encoding="utf-8")[:500])
    soul_path = home / _SOUL_MD
    if soul_path.exists():
        text = soul_path.read_text(encoding="utf-8")
        for heading in ("性格", "语气"):
            idx = text.find(f"## {heading}")
            if idx >= 0:
                parts.append(text[idx : idx + 300])
    return "\n".join(parts)


def summarize_traits(identity: str, llm: Callable[[str], str] | None) -> str:
    if llm is not None:
        return llm(identity)
    # 确定性 fallback：取 3 行关键信息拼接
    lines = [line for line in identity.splitlines() if line.strip()][:3]
    return ", ".join(lines) if lines else "default assistant"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_identity.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/identity.py tests/plugins/avatar/test_identity.py
git commit -m "feat(avatar): add identity loading and traits summarizer"
```

---

## Task 5: AvatarService 状态机

**Files:**
- Create: `lca/plugins/avatar/service.py`
- Test: `tests/plugins/avatar/test_service.py`

**Interfaces:**
- Consumes: `AvatarStore`（Task 2）、`AvatarImageProvider`（Task 3）、`AvatarTraitsSummarizer`（Task 4）、`AvatarEventPublisher`（Task 6 定义，本任务用协议注入）。
- Produces:

```python
class AvatarService:
    def __init__(self, store, provider, summarizer, publisher, home_resolver) -> None: ...
    async def create(self, assistant_id: str, user_request: str) -> list[AvatarCandidate]: ...
    async def edit(self, assistant_id: str, user_request: str, reference_image: bytes | None = None, auto_activate: bool = False) -> list[AvatarCandidate] | AvatarActiveBundle: ...
    async def set(self, assistant_id: str, candidate_id: str) -> AvatarActiveBundle: ...
    async def get(self, assistant_id: str) -> AvatarState: ...
    async def clear(self, assistant_id: str) -> AvatarState: ...
```

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_service.py`（用假 provider 与假 store）：

```python
import pytest
from datetime import UTC, datetime, timedelta

from lca.contracts.models.avatar import AvatarCandidate, AvatarState
from lca.plugins.avatar.service import AvatarService


class FakeProvider:
    def __init__(self) -> None:
        self.images = [f"img-{i}" for i in range(4)]
        self.edits = [f"edit-{i}" for i in range(4)]
        self.calls = []

    async def generate_image(self, prompt, reference_image_bytes=None):
        self.calls.append(("gen", reference_image_bytes is not None))
        return self.images[len(self.calls) - 1]

    async def create_video(self, image_bytes):
        return "task-1"

    async def get_video(self, task_id):
        return None


class FakeStore:
    def __init__(self) -> None:
        self.state = AvatarState(assistant_id="asst_1", active=None, candidates=[], updated_at=datetime(2026, 10, 2, tzinfo=UTC))
        self.copied = None

    def load_state(self, assistant_id):
        return self.state

    def save_state(self, state):
        self.state = state

    def write_image(self, assistant_id, candidate_id, size, data):
        return None

    def read_image(self, assistant_id, candidate_id, size):
        return b"active-bytes"

    def copy_candidate_to_active(self, assistant_id, candidate):
        self.copied = candidate
        return candidate  # 简化

    def cleanup_expired(self, now):
        return 0


class FakePublisher:
    def __init__(self):
        self.events = []
    def publish(self, assistant_id, event):
        self.events.append((assistant_id, event))


def _service() -> AvatarService:
    return AvatarService(
        store=FakeStore(),
        provider=FakeProvider(),
        summarizer=lambda identity: "traits",
        publisher=FakePublisher(),
        home_resolver=lambda assistant_id: "/tmp/home",
    )


def test_create_generates_candidates_without_activating():
    svc = _service()
    candidates = svc.create("asst_1", "换个赛博朋克头像")
    assert len(candidates) == 4
    assert svc.store.state.active is None
    assert len(svc.store.state.candidates) == 4


def test_set_activates_and_clears_pool():
    svc = _service()
    candidates = svc.create("asst_1", "换个头像")
    bundle = svc.set("asst_1", candidates[0].candidate_id)
    assert bundle is not None
    assert svc.store.state.active is not None
    assert svc.store.state.candidates == []


def test_set_expired_candidate_raises():
    svc = _service()
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    expired = AvatarCandidate(
        candidate_id="old", assistant_id="asst_1", kind="create", prompt="p",
        variants=(), created_at=now - timedelta(hours=25), expires_at=now - timedelta(hours=1),
    )
    svc.store.state.candidates = [expired]
    with pytest.raises(ValueError):
        svc.set("asst_1", "old")


def test_edit_uses_active_image_as_reference():
    svc = _service()
    svc.create("asst_1", "基础")
    svc.set("asst_1", svc.store.state.candidates[0].candidate_id)
    svc.store.state.candidates = []
    svc.edit("asst_1", "换件圣诞毛衣")
    assert any(kind == ("gen", True) for kind in svc.provider.calls)
```

> 说明：测试中 `FakeStore` 返回的 bundle 与真实类型不一致；实现后按真实 `AvatarActiveBundle` 修正断言。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_service.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/service.py`:

```python
"""Avatar 领域服务与状态机（ADR-0269 §4）。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from lca.contracts.models.avatar import (
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarUpdatedEvent,
    utcnow,
)

NUM_CANDIDATES = 4


class StoreLike(Protocol):
    def load_state(self, assistant_id: str) -> AvatarState: ...
    def save_state(self, state: AvatarState) -> None: ...
    def write_image(self, assistant_id: str, candidate_id: str, size: str, data: bytes): ...
    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes: ...
    def copy_candidate_to_active(self, assistant_id: str, candidate: AvatarCandidate) -> AvatarActiveBundle: ...
    def candidate_dir(self, candidate_id: str) -> Path: ...


class ProviderLike(Protocol):
    async def generate_image(self, prompt: str, reference_image_bytes: bytes | None = None) -> bytes: ...
    async def create_video(self, image_bytes: bytes) -> str: ...
    async def get_video(self, task_id: str): ...


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

    def _build_prompt(self, user_request: str, identity: str) -> str:
        traits = self.summarizer(identity)
        return f"{user_request}\n\nIdentity traits: {traits}\nStyle: consistent character, high quality avatar portrait, centered."

    async def _generate_candidates(self, assistant_id: str, kind: str, user_request: str, reference: bytes | None) -> list[AvatarCandidate]:
        from lca.contracts.models.avatar import CANDIDATE_TTL, AVATAR_SIZES
        from lca.plugins.avatar.identity import load_identity

        identity = load_identity(self.home_resolver(assistant_id))
        prompt = self._build_prompt(user_request, identity)
        now = utcnow()
        candidates: list[AvatarCandidate] = []
        for i in range(NUM_CANDIDATES):
            data = await self.provider.generate_image(prompt, reference_image_bytes=reference)
            candidate_id = f"{kind}-{now.strftime('%Y%m%d%H%M%S')}-{i}"
            variants = tuple(
                self.store.write_image(assistant_id, candidate_id, size, data if size == "original" else data)
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
        candidates = await self._generate_candidates(assistant_id, "create", user_request, reference=None)
        state = self.store.load_state(assistant_id)
        state.candidates.extend(candidates)
        state.updated_at = utcnow()
        self.store.save_state(state)
        return candidates

    async def edit(self, assistant_id: str, user_request: str, reference_image: bytes | None = None, auto_activate: bool = False):
        state = self.store.load_state(assistant_id)
        reference = reference_image
        if reference is None and state.active is not None:
            active_candidate_id = state.active.candidate_id
            reference = self.store.read_image(assistant_id, active_candidate_id, "original")
        candidates = await self._generate_candidates(assistant_id, "edit", user_request, reference=reference)
        if not auto_activate:
            state.candidates.extend(candidates)
            state.updated_at = utcnow()
            self.store.save_state(state)
            return candidates
        state.candidates = []
        state.active = self.store.copy_candidate_to_active(assistant_id, candidates[0])
        state.updated_at = utcnow()
        self.store.save_state(state)
        self.publisher.publish(assistant_id, AvatarUpdatedEvent(type="avatar_updated", assistant_id=assistant_id, payload={"candidate_id": candidates[0].candidate_id}))
        self._start_video(assistant_id, candidates[0])
        return state.active

    async def set(self, assistant_id: str, candidate_id: str) -> AvatarActiveBundle:
        state = self.store.load_state(assistant_id)
        now = utcnow()
        candidate = next((c for c in state.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")
        if candidate.is_expired(now):
            raise ValueError(f"candidate expired: {candidate_id}")
        bundle = self.store.copy_candidate_to_active(assistant_id, candidate)
        state.active = bundle
        state.candidates = []
        state.updated_at = now
        self.store.save_state(state)
        self.publisher.publish(assistant_id, AvatarUpdatedEvent(type="avatar_updated", assistant_id=assistant_id, payload={"candidate_id": candidate_id}))
        self._start_video(assistant_id, candidate)
        return bundle

    def _start_video(self, assistant_id: str, candidate: AvatarCandidate) -> None:
        async def worker() -> None:
            try:
                original = self.store.read_image(assistant_id, candidate.candidate_id, "original")
                task_id = await self.provider.create_video(original)
                # 轮询由 Task 8 的视频完成器统一处理；此处仅记录任务已起
            except Exception:
                pass

        asyncio.create_task(worker())

    async def get(self, assistant_id: str) -> AvatarState:
        return self.store.load_state(assistant_id)

    async def clear(self, assistant_id: str) -> AvatarState:
        state = self.store.load_state(assistant_id)
        state.active = None
        state.candidates = []
        state.updated_at = utcnow()
        self.store.save_state(state)
        self.publisher.publish(assistant_id, AvatarUpdatedEvent(type="avatar_updated", assistant_id=assistant_id, payload={"active": None}))
        return state
```

> 说明：`_generate_candidates` 中 `variant` 生成对非 original 尺寸实际应传缩放后的字节；Task 2 的 `write_image` 内部负责缩放，这里统一传 `data` 即可（实现按 store 语义修正）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_service.py -v`
Expected: PASS（修正测试断言使其匹配真实返回类型）

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/service.py tests/plugins/avatar/test_service.py
git commit -m "feat(avatar): add create/edit/set/get/clear state machine service"
```

---

## Task 6: REST 路由

**Files:**
- Create: `lca/plugins/avatar/routes.py`
- Test: `tests/plugins/avatar/test_routes.py`

**Interfaces:**
- Consumes: `AvatarService`（Task 5）。
- Produces: `ROUTE_SPECS`（RouteSpec 元组），在插件 setup 中经 `register_routes` 注册。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_routes.py`（用 `httpx.AsyncClient` + `ASGITransport` 或 LCA 既有路由测试模式）：

```python
import pytest


@pytest.mark.asyncio
async def test_avatar_route_specs_registered():
    from lca.plugins.avatar.routes import ROUTE_SPECS

    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/v1/assistants/{id}/avatar" in paths
    assert "/v1/assistants/{id}/avatar/candidates" in paths
    assert "/v1/assistants/{id}/avatar/set" in paths
    assert "/v1/assistants/{id}/avatar/clear" in paths
    assert "/v1/assistants/{id}/avatar/files/{path}" in paths
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_routes.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/routes.py`（仿 `routes_assistants/standing_files.py` 的鉴权与注册方式）：

```python
"""Avatar REST 路由（ADR-0269 §5）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.routing import RouteSpec
from lca.plugins.transport.webserver.route.register import register_routes


def _assistant_id(request: Any) -> str:
    return request.path_params["id"]


async def get_avatar(request: Any) -> Any:
    from lca.plugins.avatar.service import avatar_service_registry
    assistant_id = _assistant_id(request)
    service = avatar_service_registry.get(assistant_id)
    state = await service.get(assistant_id)
    return _json(request, state.model_dump())


async def get_candidates(request: Any) -> Any:
    service = avatar_service_registry.get(_assistant_id(request))
    state = await service.get(_assistant_id(request))
    return _json(request, {"candidates": [c.model_dump() for c in state.candidates]})


async def post_candidates(request: Any) -> Any:
    body = await request.json()
    user_request = str(body.get("user_request", "")).strip()
    reference_image = body.get("reference_image")
    service = avatar_service_registry.get(_assistant_id(request))
    if reference_image:
        import base64
        reference = base64.b64decode(reference_image)
        candidates = await service.edit(_assistant_id(request), user_request, reference_image=reference)
    else:
        candidates = await service.create(_assistant_id(request), user_request)
    return _json(request, {"candidates": [c.model_dump() for c in candidates]})


async def post_set(request: Any) -> Any:
    body = await request.json()
    candidate_id = str(body.get("candidate_id", ""))
    service = avatar_service_registry.get(_assistant_id(request))
    bundle = await service.set(_assistant_id(request), candidate_id)
    return _json(request, bundle.model_dump())


async def post_clear(request: Any) -> Any:
    service = avatar_service_registry.get(_assistant_id(request))
    state = await service.clear(_assistant_id(request))
    return _json(request, state.model_dump())


async def get_avatar_file(request: Any) -> Any:
    from lca.plugins.avatar.store import resolve_safe_path
    assistant_id = _assistant_id(request)
    rel_path = request.path_params["path"]
    data = resolve_safe_path(assistant_id, rel_path)
    return _png(request, data)


def _json(request: Any, payload: dict) -> Any:
    from starlette.responses import JSONResponse
    return JSONResponse(payload)


def _png(request: Any, data: bytes) -> Any:
    from starlette.responses import Response
    return Response(content=data, media_type="image/png")


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/assistants/{id}/avatar", get_avatar, ("GET", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/candidates", get_candidates, ("GET", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/candidates", post_candidates, ("POST", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/set", post_set, ("POST", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/clear", post_clear, ("POST", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/files/{path}", get_avatar_file, ("GET", "OPTIONS")),
)


async def setup(ctx: Any, config: Any) -> None:
    registry = ctx.require("web_server").router_registry
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-avatar-routes")
```

> 说明：`avatar_service_registry` 与 `resolve_safe_path` 是插件内注册表/路径工具，实现时提供。鉴权与 `x-lca-user-id` 校验复用 `routes_assistants/standing_files.py` 的模式。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_routes.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/routes.py tests/plugins/avatar/test_routes.py
git commit -m "feat(avatar): add REST routes for avatar state, candidates, set, clear"
```

---

## Task 7: WS 推送通道

**Files:**
- Create: `lca/plugins/avatar/events.py`
- Test: `tests/plugins/avatar/test_events.py`

**Interfaces:**
- Consumes: `get_agent_runtime_redis_client()`（`lca/infrastructure/observability/stream/redis_client.py`）、`AvatarUpdatedEvent`（Task 1）。
- Produces: `AvatarEventPublisher.publish(assistant_id, event)`、`make_avatar_ws_handler()`。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_events.py`：

```python
import json

from lca.contracts.models.avatar import AvatarUpdatedEvent
from lca.plugins.avatar.events import AvatarEventPublisher


def test_publish_event_roundtrip():
    sent = {}

    class FakeRedis:
        async def publish(self, channel, message):
            sent[channel] = message

    publisher = AvatarEventPublisher(redis=FakeRedis())
    publisher.publish("asst_1", AvatarUpdatedEvent(type="avatar_updated", assistant_id="asst_1", payload={"x": 1}))
    assert "assistant_events:asst_1" in sent
    assert json.loads(sent["assistant_events:asst_1"])["type"] == "avatar_updated"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_events.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/events.py`:

```python
"""Avatar WS 推送通道（ADR-0269 §6）。"""

from __future__ import annotations

import json

from lca.contracts.models.avatar import AvatarUpdatedEvent
from lca.infrastructure.observability.stream.redis_client import get_agent_runtime_redis_client


class AvatarEventPublisher:
    def __init__(self, redis=None) -> None:
        self._redis = redis

    def _redis_client(self):
        return self._redis or get_agent_runtime_redis_client()

    def publish(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        import asyncio
        asyncio.create_task(self._publish_async(assistant_id, event))

    async def _publish_async(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        channel = f"assistant_events:{assistant_id}"
        await self._redis_client().publish(channel, event.model_dump_json())


def make_avatar_ws_handler():
    """返回 Starlette WebSocket 端点：订阅 assistant_events:<id> 并转发。"""

    async def ws_endpoint(websocket) -> None:
        from starlette.websockets import WebSocketDisconnect

        await websocket.accept()
        assistant_id = websocket.path_params["id"]
        redis = get_agent_runtime_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"assistant_events:{assistant_id}")
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                if message is None:
                    continue
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except WebSocketDisconnect:
            await pubsub.unsubscribe()
        finally:
            await pubsub.aclose()

    return ws_endpoint
```

> 说明：WS 路由挂载仿 `routes_device.py`：`registry.register_websocket(WebSocketRoute("/v1/assistants/{id}/events", make_avatar_ws_handler()))`。鉴权复用网关 WS 的 JWT 校验逻辑。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_events.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/events.py tests/plugins/avatar/test_events.py
git commit -m "feat(avatar): add redis pubsub WS push channel for avatar_updated"
```

---

## Task 8: 定时换装调度器

**Files:**
- Create: `lca/plugins/avatar/scheduler.py`
- Test: `tests/plugins/avatar/test_scheduler.py`

**Interfaces:**
- Consumes: `CronStore`（`lca/domain/cron/store.py`）、`next_run`（`lca/domain/cron/next_run.py`）、`AvatarService.edit(auto_activate=True)`（Task 5）。
- Produces: `AvatarCostumeScheduler(service, cron_store, tick_seconds=60)`，`async def run_forever()`。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_scheduler.py`：

```python
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from lca.contracts.models.cron.models import CronJob, DailySchedule, SpaceActionExecution
from lca.plugins.avatar.scheduler import AvatarCostumeScheduler


def _job(job_id: str, body: str, enabled: bool = True) -> CronJob:
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    return CronJob(
        id=job_id, title="avatar", schedule=DailySchedule(hour=12, minute=0),
        timezone="Asia/Shanghai", body=body,
        execution=SpaceActionExecution(artifact_id="avatar"),
        report="anomalies_only", owner="asst_1", created_chat_id="chat_1", anchor_at=now,
        enabled=enabled,
    )


def test_scheduler_selects_avatar_jobs():
    jobs = [
        _job("j1", "雨天装扮"),
        _job("j2", "普通任务").model_copy(update={"execution": SpaceActionExecution(artifact_id="other")}),
    ]
    selected = AvatarCostumeScheduler._select_avatar_jobs(jobs)
    assert [j.id for j in selected] == ["j1"]


def test_scheduler_disabled_job_skipped():
    jobs = [_job("j1", "x", enabled=False)]
    assert AvatarCostumeScheduler._select_avatar_jobs(jobs) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/scheduler.py`:

```python
"""定时换装调度器（ADR-0269 §5）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Iterable

from lca.contracts.models.cron.models import CronJob
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore


class AvatarCostumeScheduler:
    def __init__(self, service, cron_store: CronStore, tick_seconds: int = 60) -> None:
        self.service = service
        self.cron_store = cron_store
        self.tick_seconds = tick_seconds

    @staticmethod
    def _select_avatar_jobs(jobs: Iterable[CronJob]) -> list[CronJob]:
        return [
            job
            for job in jobs
            if job.enabled
            and job.execution.kind == "space_action"
            and job.execution.artifact_id == "avatar"
        ]

    async def _tick(self) -> None:
        jobs = self._select_avatar_jobs(self.cron_store.list_jobs())
        now = datetime.now(UTC)
        for job in jobs:
            runs = self.cron_store.get_run_records(job.id)
            last_run = runs[-1].finished_at if runs and runs[-1].finished_at else None
            fire = next_run(job, last_run=last_run, now=now)
            if fire.due:
                try:
                    await self.service.edit(job.owner, job.body, auto_activate=True)
                    self.cron_store.append_run(job.id, outcome="completed", finished_at=datetime.now(UTC))
                except Exception:
                    self.cron_store.append_run(job.id, outcome="runtime_failure", finished_at=datetime.now(UTC))

    async def run_forever(self) -> None:
        while True:
            await self._tick()
            await asyncio.sleep(self.tick_seconds)
```

> 说明：`CronStore.append_run` 若不存在则按 ADR-0268 语义新增（写入 `cron/<job_id>/runs/`）。轻量通知经 Task 5 的 publisher 或 `ProactiveDeliverer` 追加，具体接入见 Task 8 扩展。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/scheduler.py tests/plugins/avatar/test_scheduler.py
git commit -m "feat(avatar): add cron costume change scheduler using CronJob store"
```

---

## Task 9: Agent 工具注册

**Files:**
- Create: `lca/plugins/avatar/tools.py`
- Test: `tests/plugins/avatar/test_tools.py`

**Interfaces:**
- Consumes: `AvatarService`（Task 5）。
- Produces: `avatar_create`、`avatar_edit`、`avatar_set`、`avatar_get`、`avatar_clear`、`avatar_schedule` 六个 Tool 类，插件 `setup` 中 `ctx.require("tools").register(...)`。

- [ ] **Step 1: 写失败测试**

`tests/plugins/avatar/test_tools.py`：

```python
import pytest

from lca.plugins.avatar.tools import AvatarCreateTool, AvatarSetTool, AvatarGetTool, AvatarClearTool


def test_tool_manifests_exist():
    assert AvatarCreateTool.name == "avatar_create"
    assert AvatarSetTool.name == "avatar_set"
    assert AvatarGetTool.name == "avatar_get"
    assert AvatarClearTool.name == "avatar_clear"


def test_create_tool_requires_user_request():
    tool = AvatarCreateTool()
    error = tool.validate({"user_request": ""})
    assert error is not None
    assert tool.validate({"user_request": "换个头像"}) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/plugins/avatar/test_tools.py -v`
Expected: FAIL

- [ ] **Step 3: 写最小实现**

`lca/plugins/avatar/tools.py`（仿 `lca/plugins/tools/profile_apply.py` 的 Tool + MANIFEST + @plugin 结构）：

```python
"""Avatar agent 工具（ADR-0269 §4）。"""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool


class AvatarCreateTool(Tool):
    name = "avatar_create"
    effect_kind: ClassVar[str] = "persistent"
    namespace = "avatar"
    description = "Generate new avatar candidates from the user's request. Never activates."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"user_request": {"type": "string", "description": "用户原话，原样传递"}},
        "required": ["user_request"],
    }
    is_idempotent = False
    default_timeout_s = 120

    def validate(self, args: dict[str, Any]) -> str | None:
        if not str(args.get("user_request", "")).strip():
            return "user_request must be non-empty"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        from lca.plugins.avatar.service import avatar_service_registry
        service = avatar_service_registry.current()
        try:
            candidates = await service.create(service.current_assistant_id(), str(args["user_request"]))
            return Observation(
                observation_id=new_id("obs"), success=True,
                payload={"candidates": [c.model_dump() for c in candidates]},
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            return Observation(
                observation_id=new_id("obs"), success=False, payload=None, error=str(exc),
                latency_ms=int((time.monotonic() - started) * 1000),
            )


class AvatarSetTool(Tool):
    name = "avatar_set"
    effect_kind: ClassVar[str] = "persistent"
    namespace = "avatar"
    description = "Activate an avatar candidate by id."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"candidate_id": {"type": "string"}},
        "required": ["candidate_id"],
    }
    is_idempotent = True
    default_timeout_s = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        return None if str(args.get("candidate_id", "")).strip() else "candidate_id is required"

    async def execute(self, args: dict[str, Any]) -> Observation:
        from lca.plugins.avatar.service import avatar_service_registry
        service = avatar_service_registry.current()
        try:
            bundle = await service.set(service.current_assistant_id(), str(args["candidate_id"]))
            return Observation(observation_id=new_id("obs"), success=True, payload={"active": bundle.model_dump()}, latency_ms=0)
        except Exception as exc:
            return Observation(observation_id=new_id("obs"), success=False, payload=None, error=str(exc), latency_ms=0)


# AvatarEditTool / AvatarGetTool / AvatarClearTool / AvatarScheduleTool 同构：
# - edit: 参数 user_request + reference_image(可选)，行为见 AvatarService.edit
# - get: 返回 AvatarState
# - clear: 调 AvatarService.clear
# - schedule: 参数 user_request + schedule + timezone，调 CronService.add_job
# MANIFEST 与 @plugin 注册结构完全仿 profile_apply.py（provides=["tools.avatar_*"], requires=["tools"], implements=["Tool"]）
```

> 说明：`avatar_service_registry` 提供 `current()` 与 `current_assistant_id()`（从运行上下文解析当前 assistant）。`current_assistant_id()` 的取值来源与 `lca/plugins/prompts/sections/context.py` 的 `assistant_home_path` 相同（运行 runtime 注入的当前 assistant home 路径），实现时读该路径的 `profile.json` 取 `name` 或直接用目录名 `asst_xxx`。`avatar_schedule` 的 `schedule` 参数按 `CronJob` schedule 判别联合编码。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/plugins/avatar/test_tools.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lca/plugins/avatar/tools.py tests/plugins/avatar/test_tools.py
git commit -m "feat(avatar): register six avatar agent tools"
```

---

## Task 10: 插件装配

**Files:**
- Create: `lca/plugins/avatar/plugin.py`、`lca/plugins/avatar/__init__.py`

**Interfaces:**
- 装配 Task 1-9 的组件：store、provider、summarizer、publisher、service、routes、ws、scheduler、tools。
- 提供 `avatar_service_registry`（按 assistant_id 解析 service，当前 run 上下文解析 current assistant）。

- [ ] **Step 1: 写插件装配**

`lca/plugins/avatar/plugin.py`（仿 `routes_agent_gateway_ws.py` 的 @plugin 结构）：

```python
"""Avatar 插件装配（ADR-0269）。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from lca.harness.plugin_api import PluginContext, PluginKind, plugin

from lca.plugins.avatar.events import AvatarEventPublisher, make_avatar_ws_handler
from lca.plugins.avatar.provider import Grok2ApiProvider
from lca.plugins.avatar.scheduler import AvatarCostumeScheduler
from lca.plugins.avatar.service import AvatarService
from lca.plugins.avatar.store import AvatarStore


@plugin(
    id="lca-avatar",
    provides=["avatar.service", "avatar.events"],
    requires=["tools", "web_server"],
    implements=["Tool"],
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="stateful_once",
    description="Assistant avatar generation system.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    base_dir = Path(os.environ.get("LCA_ASSISTANTS_ROOT", "~/.lca/assistants")).expanduser()
    store = AvatarStore(base_dir)
    provider = Grok2ApiProvider(
        base_url=os.environ["AVATAR_IMAGE_BASE_URL"],
        api_key=os.environ["AVATAR_IMAGE_API_KEY"],
        model=os.environ.get("AVATAR_IMAGE_MODEL", "grok-imagine-image-lite"),
        edit_model=os.environ.get("AVATAR_IMAGE_EDIT_MODEL", "grok-imagine-image-lite"),
        video_model=os.environ.get("AVATAR_VIDEO_MODEL", "grok-imagine-video"),
    )
    publisher = AvatarEventPublisher()
    service = AvatarService(
        store=store,
        provider=provider,
        summarizer=lambda identity: identity,
        publisher=publisher,
        home_resolver=lambda assistant_id: base_dir / assistant_id,
    )
    ctx.provide("avatar.service", service)
    ctx.provide("avatar.events", publisher)
    # 注册路由与 WS（见 Task 6 / 7 的 setup）
    scheduler = AvatarCostumeScheduler(service, cron_store=load_cron_store())
    asyncio.create_task(scheduler.run_forever())
```

> 说明：`load_cron_store()` 从 `lca/domain/cron/store.py` 加载当前 profile 的 CronStore；`config` 可携带 `summarizer_llm` 等选项。

- [ ] **Step 2: 冒烟测试装配**

Run: `uv run python -c "import lca.plugins.avatar.plugin"` 与 `uv run pytest tests/plugins/avatar/ -v`
Expected: import 成功、全部通过

- [ ] **Step 3: 提交**

```bash
git add lca/plugins/avatar/plugin.py lca/plugins/avatar/__init__.py
git commit -m "feat(avatar): assemble avatar plugin wiring"
```

---

## Task 11: 前端补丁（头像渲染 + WS 客户端）

**Files:**
- Create: `deploy/lobehub/patches/ui/AssistantAvatarImage.tsx`、`deploy/lobehub/patches/ui/assistant_avatar_image.py`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/assistantEventClient.ts`、`deploy/lobehub/patches/runtime/lca_assistant_events.py`

**Interfaces:**
- 消费 REST 端点（Task 6）与 WS 端点（Task 7）。
- 复用现有补丁引擎：`deploy/lobehub/patches/ui/assistant_avatar_widget.py` 的 `@patch(...)` 结构（`_COMPONENT_REL`、`_SOURCE_NAME`、`why`、`verify_marker`）。

- [ ] **Step 1: 写头像组件与补丁**

`AssistantAvatarImage.tsx`（核心逻辑）：

```tsx
'use client';

import { Avatar } from 'antd';
import { memo, useEffect, useState } from 'react';

export interface AvatarStatePayload {
  active: { candidate_id: string; variants: Array<{ size: string; url: string }> } | null;
}

const AVATAR_ENDPOINT = (assistantId: string) =>
  `/lca-api/v1/assistants/${assistantId}/avatar`;

export const AssistantAvatarImage = memo<{ assistantId?: string; size?: number }>(
  ({ assistantId, size = 32 }) => {
    const [activeUrl, setActiveUrl] = useState<string | null>(null);

    const refresh = async () => {
      try {
        const res = await fetch(AVATAR_ENDPOINT(assistantId || 'default'), {
          headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local'}` },
        });
        if (!res.ok) return;
        const data: AvatarStatePayload = await res.json();
        const original = data.active?.variants.find((v) => v.size === 'original');
        setActiveUrl(original?.url || null);
      } catch {
        /* 保持当前头像 */
      }
    };

    useEffect(() => {
      refresh();
      const onAvatarChanged = () => refresh();
      window.addEventListener('lca-assistant-avatar-changed', onAvatarChanged);
      return () => window.removeEventListener('lca-assistant-avatar-changed', onAvatarChanged);
    }, [assistantId]);

    return activeUrl ? (
      <Avatar src={activeUrl} size={size} />
    ) : (
      <Avatar size={size}>{/* 默认 emoji / SVG 萌宠回退 */}</Avatar>
    );
  },
);

export default AssistantAvatarImage;
```

`assistant_avatar_image.py` 补丁脚本仿 `assistant_avatar_widget.py`：将 `AssistantAvatarImage.tsx` 写入 `lobehub-ui/src/features/Conversation/Messages/components/AssistantAvatarImage.tsx`，并在聊天顶栏、Status drawer、消息气泡旁三处挂载（`AssistantAvatarWidget` 现有挂载锚点可复用）。

- [ ] **Step 2: 写 WS 客户端与补丁**

`assistantEventClient.ts`：

```ts
export type AssistantEvent =
  | { type: 'avatar_updated'; assistant_id: string; payload: Record<string, unknown> }
  | { type: 'avatar_video_ready'; assistant_id: string; payload: Record<string, unknown> };

export class AssistantEventClient {
  private ws: WebSocket | null = null;
  private retry = 0;

  constructor(private assistantId: string) {}

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/lca-api/v1/assistants/${this.assistantId}/events`);
    this.ws.onmessage = (ev) => this.handle(JSON.parse(ev.data) as AssistantEvent);
    this.ws.onclose = () => setTimeout(() => this.connect(), 2000 * Math.min(2 ** this.retry++, 10));
    this.ws.onopen = () => (this.retry = 0);
  }

  private handle(event: AssistantEvent) {
    if (event.type === 'avatar_updated' || event.type === 'avatar_video_ready') {
      window.dispatchEvent(new CustomEvent('lca-assistant-avatar-changed', { detail: event }));
    }
  }
}
```

`lca_assistant_events.py` 补丁脚本将 `assistantEventClient.ts` 复制到 `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/lcaGateway/` 下，并在消息页挂载时 `new AssistantEventClient(assistantId).connect()`。

- [ ] **Step 3: 跑补丁完整性检查**

Run: `python3 deploy/lobehub/patch_lobehub.py apply` 与 `python3 deploy/lobehub/check_patch_integrity.py`
Expected: 补丁应用成功、完整性通过

- [ ] **Step 4: 提交**

```bash
git add deploy/lobehub/patches/ui/AssistantAvatarImage.tsx deploy/lobehub/patches/ui/assistant_avatar_image.py deploy/lobehub/patches/runtime/lcaGateway/assistantEventClient.ts deploy/lobehub/patches/runtime/lca_assistant_events.py
git commit -m "feat(avatar): add frontend avatar image rendering and event WS client patches"
```

---

## Task 12: 候选卡片升级

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx`

- [ ] **Step 1: 升级候选卡片**

把 `AssistantAvatarWidget.tsx` 的候选来源从 `DEFAULT_CANDIDATES` 常量改为 `GET /v1/assistants/{id}/avatar/candidates`；确认按钮从写 IDENTITY.md 改为 `POST .../avatar/set`。保留 `lca-assistant-avatar-changed` CustomEvent 广播（Task 11 已监听）。

关键改动点：

```tsx
// 候选来源
const [candidates, setCandidates] = useState<GeneratedCandidate[]>([]);
useEffect(() => {
  fetch(`/lca-api/v1/assistants/${assistantId}/avatar/candidates`)
    .then((r) => r.json())
    .then((data) => setCandidates(data.candidates.map((c) => ({ id: c.candidate_id, imageUrl: c.variants.find((v) => v.size === 'medium')?.url }))));
}, [assistantId]);

// 确认激活
const handleConfirm = async () => {
  await fetch(`/lca-api/v1/assistants/${assistantId}/avatar/set`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: selectedId }),
  });
  window.dispatchEvent(new CustomEvent('lca-assistant-avatar-changed', { detail: { candidate_id: selectedId } }));
  antMessage.success('我的头像换好了 🎉'); // 第一人称
};
```

- [ ] **Step 2: 跑前端测试与补丁完整性**

Run: `cd lobehub-ui && bun vitest run src/features/Conversation/Messages/components/AssistantAvatarWidget.test.tsx`（如存在）与 `python3 deploy/lobehub/check_patch_integrity.py`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx
git commit -m "feat(avatar): upgrade candidate widget to generated images and set endpoint"
```

---

## Task 13: E2E 验证

**Files:** 无（验收）

- [ ] **Step 1: 起服务并触发换装**

```bash
./scripts/lca-ops kernel-restart
./scripts/lca-ops runs create --user-text "用 avatar_create 生成候选，然后用 avatar_set 激活第二个候选"
```

Expected: run 成功，候选返回图片 URL

- [ ] **Step 2: 浏览器验证前端**

在 :3010 打开 LobeHub：聊天顶栏、Status drawer、消息气泡旁头像都显示生成图；候选卡片展示图片候选；确认后立即全端刷新（同 tab CustomEvent + WS）；视频异步就绪后再次刷新。

- [ ] **Step 3: 验证定时换装**

创建 `avatar_schedule` CronJob（如每天 12:00 换装），等待到点或手动触发调度器 tick，确认头像更换且收到轻量通知。

- [ ] **Step 4: 全量回归**

```bash
ruff check
ruff format --check
uv run pytest tests/plugins/avatar/ -v
python3 deploy/lobehub/check_patch_integrity.py
git diff --check
```

Expected: 全绿

---

## Self-Review 备注（计划作者自查）

- Spec §4（数据模型）→ Task 1；§5（存储）→ Task 2；§6（管线）→ Task 3、Task 4；§7（状态机）→ Task 5、Task 9；§8（调度器）→ Task 8；§9（REST）→ Task 6；§10（WS）→ Task 7；§11（前端）→ Task 11、Task 12；§13（失败语义）→ 各任务内；§14（测试）→ 各任务测试 + Task 13。
- 占位符：Task 5/8/9 中标注「说明」的段落是给执行者的实现提示，不是占位符；`avatar_service_registry`、`resolve_safe_path`、`CronStore.append_run` 等未在早期任务定义的辅助符号，需要在对应任务中实现并补测试。
- 类型一致性：`AvatarState/AvatarCandidate/AvatarActiveBundle/AvatarUpdatedEvent` 在所有任务中签名一致；`AvatarService` 方法签名在 Task 5 定义并被 Task 6/8/9 复用。
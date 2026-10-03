"""Avatar REST 路由测试（Task 6）。

覆盖：
- ROUTE_SPECS 注册表；
- GET /v1/assistants/{id}/avatar 返回 AvatarState；
- GET/POST /v1/assistants/{id}/avatar/candidates（create + reference_image→edit）；
- POST /v1/assistants/{id}/avatar/set（含未知候选 409）；
- POST /v1/assistants/{id}/avatar/clear；
- GET /v1/assistants/{id}/avatar/files/{path}（图片字节 + 路径穿越 400）；
- resolve_safe_path 白名单/归一化单测。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.models.avatar import (
    CANDIDATE_TTL,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    utcnow,
)
from lca.plugins.avatar.registry import avatar_service_registry
from lca.plugins.avatar.routes import ROUTE_SPECS, setup
from lca.plugins.avatar.store import AvatarStore, resolve_safe_path
from lca.plugins.transport.webserver.router.router import RouteRegistry


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def provide(self, key: str, value: Any) -> None:
        pass

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


class _FakeOwnership:
    def __init__(
        self,
        owner_map: dict[str, str],
        agent_map: dict[str, str] | None = None,
    ) -> None:
        self._owner_map = owner_map
        self._agent_map = agent_map or {}

    def owner_of(self, assistant_id: str) -> str | None:
        return self._owner_map.get(assistant_id)

    def assistant_id_for_agent(self, agent_id: str) -> str | None:
        return self._agent_map.get(agent_id)


class FakeAvatarService:
    """轻量假服务：路由只消费 get/create/edit/set/clear + .store 属性。"""

    def __init__(self, assistant_id: str, base_dir: Path) -> None:
        self.assistant_id = assistant_id
        self.store = AvatarStore(base_dir)
        self.state = AvatarState(
            assistant_id=assistant_id,
            active=None,
            candidates=[],
            updated_at=datetime(2026, 10, 2, tzinfo=UTC),
        )
        self.create_calls = 0
        self.edit_calls = 0
        self.last_reference_image: bytes | None = None

    async def get(self, assistant_id: str) -> AvatarState:
        return self.state

    async def create(self, assistant_id: str, user_request: str) -> list[AvatarCandidate]:
        self.create_calls += 1
        candidates = [self._candidate(f"create-{i}") for i in range(2)]
        self.state = self.state.model_copy(
            update={"candidates": candidates, "updated_at": utcnow()}
        )
        return candidates

    async def edit(
        self,
        assistant_id: str,
        user_request: str,
        reference_image: bytes | None = None,
        auto_activate: bool = False,
    ) -> list[AvatarCandidate]:
        self.edit_calls += 1
        self.last_reference_image = reference_image
        candidates = [self._candidate(f"edit-{i}") for i in range(2)]
        self.state = self.state.model_copy(
            update={"candidates": candidates, "updated_at": utcnow()}
        )
        return candidates

    async def set(self, assistant_id: str, candidate_id: str) -> AvatarActiveBundle:
        candidate = next((c for c in self.state.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")
        bundle = AvatarActiveBundle(
            candidate_id=candidate_id,
            variants=candidate.variants,
            activated_at=utcnow(),
        )
        self.state = self.state.model_copy(
            update={"active": bundle, "candidates": [], "updated_at": utcnow()}
        )
        return bundle

    async def clear(self, assistant_id: str) -> AvatarState:
        self.state = self.state.model_copy(
            update={"active": None, "candidates": [], "updated_at": utcnow()}
        )
        return self.state

    def _candidate(self, candidate_id: str) -> AvatarCandidate:
        return AvatarCandidate(
            candidate_id=candidate_id,
            assistant_id=self.assistant_id,
            kind="create",
            prompt="prompt",
            variants=(),
            created_at=utcnow(),
            expires_at=utcnow() + CANDIDATE_TTL,
        )


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    avatar_service_registry.clear()
    yield
    avatar_service_registry.clear()


@pytest.fixture()
def app() -> Starlette:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(setup(ctx, None))
    app = Starlette()
    router.install(app)
    return app


def _register_service(assistant_id: str, base_dir: Path) -> FakeAvatarService:
    service = FakeAvatarService(assistant_id, base_dir)
    avatar_service_registry.register(assistant_id, service)
    return service


def _enable_auth(app: Starlette) -> None:
    """关闭 dev_mode，启用 Bearer token + x-lca-user-id 鉴权。"""
    app.state.lca_auth_dev_mode = False
    app.state.lca_auth_expected_token = "test-token"  # noqa: S105  # 测试专用


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": "Bearer test-token", "x-lca-user-id": user_id}


def _avatar_urls(assistant_id: str) -> list[tuple[str, str]]:
    """返回全部 avatar 端点的 (method, path)，供 401/404 遍历断言。"""
    return [
        ("GET", f"/v1/assistants/{assistant_id}/avatar"),
        ("GET", f"/v1/assistants/{assistant_id}/avatar/candidates"),
        ("POST", f"/v1/assistants/{assistant_id}/avatar/candidates"),
        ("POST", f"/v1/assistants/{assistant_id}/avatar/set"),
        ("POST", f"/v1/assistants/{assistant_id}/avatar/clear"),
        (
            "GET",
            f"/v1/assistants/{assistant_id}/avatar/files/candidates/cand-1/original.png",
        ),
    ]


# ── ROUTE_SPECS ──────────────────────────────────────────────


def test_avatar_route_specs_registered() -> None:
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/v1/assistants/{id}/avatar" in paths
    assert "/v1/assistants/{id}/avatar/candidates" in paths
    assert "/v1/assistants/{id}/avatar/set" in paths
    assert "/v1/assistants/{id}/avatar/clear" in paths
    # 文件路由必须用 {path:path} 才能捕获 candidates/<id>/<size>.png 中的斜杠。
    file_specs = [p for p in paths if p.startswith("/v1/assistants/{id}/avatar/files/")]
    assert file_specs == ["/v1/assistants/{id}/avatar/files/{path:path}"]


# ── GET /avatar ──────────────────────────────────────────────


def test_get_avatar_returns_state(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_get"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    svc.state = svc.state.model_copy(
        update={
            "active": AvatarActiveBundle(
                candidate_id="active-1", variants=(), activated_at=utcnow()
            ),
            "candidates": [svc._candidate("cand-1")],
        }
    )
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["assistant_id"] == assistant_id
    assert data["active"]["candidate_id"] == "active-1"
    assert data["candidates"][0]["candidate_id"] == "cand-1"


def test_get_avatar_unknown_assistant_returns_404(app: Starlette) -> None:
    client = TestClient(app)
    resp = client.get("/v1/assistants/asst_nonexistent/avatar")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "assistant_not_found"


# ── /avatar/candidates ───────────────────────────────────────


def test_get_avatar_candidates(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_cands"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    svc.state = svc.state.model_copy(
        update={"candidates": [svc._candidate("cand-1"), svc._candidate("cand-2")]}
    )
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["candidate_id"] == "cand-1"


def test_post_avatar_candidates_create(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_create"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": "换个赛博朋克头像"},
    )
    assert resp.status_code == 200
    assert svc.create_calls == 1
    data = resp.json()
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["candidate_id"].startswith("create-")


def test_post_avatar_candidates_edit_with_reference_image(app: Starlette, tmp_path: Path) -> None:
    from lca.infrastructure.file.store import LocalFileStore

    assistant_id = "asst_edit"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    file_store = LocalFileStore(tmp_path / "uploads")
    stored = file_store.put(data=b"fake-png-bytes", name="photo.png", mime_type="image/png")
    app.state.file_store = file_store
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": "换件毛衣", "reference_image": stored.url},
    )
    assert resp.status_code == 200
    assert svc.edit_calls == 1
    assert svc.last_reference_image == b"fake-png-bytes"
    data = resp.json()
    assert data["candidates"][0]["candidate_id"].startswith("edit-")


def test_post_avatar_candidates_missing_user_request_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_bad"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request"


def test_post_avatar_candidates_non_string_user_request_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_bad_usr_type"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": 123},
    )
    assert resp.status_code == 400
    assert "字符串" in resp.json()["error"]["detail"]


def test_post_avatar_candidates_non_string_reference_image_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_bad_ref_type"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": "换头像", "reference_image": 42},
    )
    assert resp.status_code == 400
    assert "/files/" in resp.json()["error"]["detail"]


def test_post_avatar_candidates_rejects_base64_reference_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_bad_b64"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": "换头像", "reference_image": "not-valid-base64!!!"},
    )
    assert resp.status_code == 400
    assert "/files/" in resp.json()["error"]["detail"]


def test_post_avatar_candidates_rejects_data_uri_reference_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_bad_data_uri"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/candidates",
        json={"user_request": "换头像", "reference_image": "data:image/png;base64,AAAA"},
    )
    assert resp.status_code == 400
    assert "/files/" in resp.json()["error"]["detail"]


# ── /avatar/set ──────────────────────────────────────────────


def test_post_avatar_set(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_set"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    svc.state = svc.state.model_copy(update={"candidates": [svc._candidate("cand-1")]})
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/set",
        json={"candidate_id": "cand-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_id"] == "cand-1"
    assert svc.state.active is not None
    assert svc.state.active.candidate_id == "cand-1"


def test_post_avatar_set_unknown_candidate_returns_409(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_set_unknown"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/set",
        json={"candidate_id": "nope"},
    )
    assert resp.status_code == 409
    assert "candidate not found" in resp.json()["error"]["detail"]


def test_post_avatar_set_non_string_candidate_id_returns_400(
    app: Starlette, tmp_path: Path
) -> None:
    assistant_id = "asst_set_bad_type"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.post(
        f"/v1/assistants/{assistant_id}/avatar/set",
        json={"candidate_id": 123},
    )
    assert resp.status_code == 400
    assert "字符串" in resp.json()["error"]["detail"]


# ── /avatar/clear ────────────────────────────────────────────


def test_post_avatar_clear(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_clear"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    svc.state = svc.state.model_copy(
        update={
            "active": AvatarActiveBundle(
                candidate_id="active-1", variants=(), activated_at=utcnow()
            )
        }
    )
    client = TestClient(app)
    resp = client.post(f"/v1/assistants/{assistant_id}/avatar/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is None
    assert data["candidates"] == []
    assert svc.state.active is None


# ── /avatar/files/{path} ─────────────────────────────────────


def test_get_avatar_file_serves_png(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_file"
    base_dir = tmp_path / "avatar"
    _register_service(assistant_id, base_dir)
    target = base_dir / "candidates" / "cand-1" / "original.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x89PNG-fake-bytes")
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar/files/candidates/cand-1/original.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"\x89PNG-fake-bytes"


def test_get_avatar_file_serves_mp4_with_video_content_type(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_file_mp4"
    base_dir = tmp_path / "avatar"
    _register_service(assistant_id, base_dir)
    target = base_dir / "video" / "cand-9.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake-mp4-bytes")
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar/files/video/cand-9.mp4")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == b"fake-mp4-bytes"


def test_get_avatar_file_rejects_path_traversal(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_trav"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar/files/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request"


def test_get_avatar_file_rejects_disallowed_path(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_disallowed"
    _register_service(assistant_id, tmp_path / "avatar")
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar/files/state.json")
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request"


def test_get_avatar_file_unknown_assistant_returns_404(app: Starlette) -> None:
    """未注册助理的文件请求必须映射 404，而不是 500。"""
    client = TestClient(app)
    resp = client.get("/v1/assistants/asst_nonexistent/avatar/files/candidates/cand-1/original.png")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "assistant_not_found"


# ── 鉴权与归属（ADR-0252 D4/D6） ────────────────────────────


def test_unauthenticated_requests_rejected_401(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_auth_401"
    _register_service(assistant_id, tmp_path / "avatar")
    _enable_auth(app)
    client = TestClient(app)
    for method, url in _avatar_urls(assistant_id):
        resp = client.request(method, url)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"
        assert resp.json()["error"]["type"] == "auth"


def test_cross_user_access_rejected_404(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_auth_owner_bob"
    _register_service(assistant_id, tmp_path / "avatar")
    app.state.assistant_ownership = _FakeOwnership({assistant_id: "bob"})
    _enable_auth(app)
    client = TestClient(app)
    for method, url in _avatar_urls(assistant_id):
        resp = client.request(method, url, headers=_auth_headers("alice"))
        assert resp.status_code == 404, f"{method} {url} -> {resp.status_code}"
        assert resp.json()["error"]["code"] == "assistant_not_found"


def test_owner_can_access_avatar(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_auth_owner_alice"
    svc = _register_service(assistant_id, tmp_path / "avatar")
    svc.state = svc.state.model_copy(update={"candidates": [svc._candidate("cand-1")]})
    app.state.assistant_ownership = _FakeOwnership({assistant_id: "alice"})
    _enable_auth(app)
    client = TestClient(app)
    resp = client.get(f"/v1/assistants/{assistant_id}/avatar", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    assert resp.json()["assistant_id"] == assistant_id


# ── resolve_safe_path 单测 ───────────────────────────────────


def _write(base_dir: Path, rel: str, data: bytes = b"png-data") -> Path:
    target = base_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_resolve_safe_path_candidate_png(tmp_path: Path) -> None:
    assistant_id = "asst_rsp_candidate"
    base_dir = tmp_path / "avatar"
    _register_service(assistant_id, base_dir)
    _write(base_dir, "candidates/cand-1/original.png")
    assert resolve_safe_path(assistant_id, "candidates/cand-1/original.png") == b"png-data"


def test_resolve_safe_path_active_png(tmp_path: Path) -> None:
    assistant_id = "asst_rsp_active"
    base_dir = tmp_path / "avatar"
    _register_service(assistant_id, base_dir)
    _write(base_dir, "active/cand-9/medium.png", b"active-data")
    assert resolve_safe_path(assistant_id, "active/cand-9/medium.png") == b"active-data"


def test_resolve_safe_path_video_mp4(tmp_path: Path) -> None:
    assistant_id = "asst_rsp_video"
    base_dir = tmp_path / "avatar"
    _register_service(assistant_id, base_dir)
    _write(base_dir, "video/cand-9.mp4", b"mp4-data")
    assert resolve_safe_path(assistant_id, "video/cand-9.mp4") == b"mp4-data"


@pytest.mark.parametrize(
    "bad_path",
    [
        "../state.json",
        "candidates/../state.json",
        "../../etc/passwd",
        "/etc/passwd",
        "candidates/a\x00b/original.png",
        "state.json",
        "candidates/cand-1/huge.png",
        "video/cand-1.png",
        "active//original.png",
    ],
)
def test_resolve_safe_path_rejects_bad_path(tmp_path: Path, bad_path: str) -> None:
    assistant_id = "asst_rsp_bad"
    _register_service(assistant_id, tmp_path / "avatar")
    with pytest.raises(ValueError):
        resolve_safe_path(assistant_id, bad_path)


def test_routes_resolve_agt_agent_id_to_assistant_id(app: Starlette, tmp_path: Path) -> None:
    assistant_id = "asst_real_id"
    agent_id = "agt_frontend_row"
    _register_service(assistant_id, tmp_path / "avatar")
    _enable_auth(app)
    app.state.assistant_ownership = _FakeOwnership(
        owner_map={assistant_id: "alice"},
        agent_map={agent_id: assistant_id},
    )
    client = TestClient(app)
    resp = client.get(
        f"/v1/assistants/{agent_id}/avatar",
        headers=_auth_headers("alice"),
    )
    assert resp.status_code == 200
    assert resp.json()["assistant_id"] == assistant_id

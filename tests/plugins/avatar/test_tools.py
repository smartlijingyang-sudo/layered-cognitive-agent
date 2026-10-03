"""Avatar agent 工具注册测试（Task 9 / ADR-0269 §4）。

覆盖：
- 六个 Tool 的 name / namespace / validate 前置校验；
- MANIFEST 暴露六个 API 及正确 effects；
- execute 经 ``avatar_service_registry`` 返回成功/失败 Observation；
- ``avatar_edit`` 的 reference_image 支持 data URI / base64 / FileStore 引用；
- ``avatar_schedule`` 经 CronService.add_job 持久化换装任务。
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.models.avatar import (
    CANDIDATE_TTL,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    utcnow,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.observability.facade.run.ambit import RunAmbit, bind_run_ambit
from lca.plugins.avatar.registry import avatar_service_registry
from lca.plugins.avatar.tools import (
    MANIFEST,
    AvatarClearTool,
    AvatarCreateTool,
    AvatarEditTool,
    AvatarGetTool,
    AvatarScheduleTool,
    AvatarSetTool,
)

ASSISTANT_ID = "asst_test"


class FakeAvatarService:
    """注册进 ``avatar_service_registry`` 的假服务，记录调用并支持注入失败。"""

    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.edits: list[tuple[str, str, bytes | None]] = []
        self.last_visual_prompt: str | None = None
        self.set_calls: list[tuple[str, str]] = []
        self.get_calls: list[str] = []
        self.clear_calls: list[str] = []
        self.fail: Exception | None = None
        self.state = AvatarState(
            assistant_id=ASSISTANT_ID,
            active=None,
            candidates=[],
            updated_at=datetime(2026, 10, 2, tzinfo=UTC),
        )

    def _candidate(self, candidate_id: str) -> AvatarCandidate:
        return AvatarCandidate(
            candidate_id=candidate_id,
            assistant_id=ASSISTANT_ID,
            kind="create",
            prompt="prompt",
            variants=(),
            created_at=utcnow(),
            expires_at=utcnow() + CANDIDATE_TTL,
        )

    async def create(
        self, assistant_id: str, user_request: str, **kwargs: Any
    ) -> list[AvatarCandidate]:
        if self.fail is not None:
            raise self.fail
        self.last_visual_prompt = kwargs.get("visual_prompt")
        self.created.append((assistant_id, user_request))
        return [self._candidate("c1")]

    async def edit(
        self,
        assistant_id: str,
        user_request: str,
        reference_image: bytes | None = None,
        auto_activate: bool = False,
        **kwargs: Any,
    ) -> list[AvatarCandidate]:
        if self.fail is not None:
            raise self.fail
        self.last_visual_prompt = kwargs.get("visual_prompt")
        self.edits.append((assistant_id, user_request, reference_image))
        return [self._candidate("c1")]

    async def set(self, assistant_id: str, candidate_id: str) -> AvatarActiveBundle:
        if self.fail is not None:
            raise self.fail
        self.set_calls.append((assistant_id, candidate_id))
        return AvatarActiveBundle(
            candidate_id=candidate_id,
            variants=(),
            activated_at=utcnow(),
        )

    async def get(self, assistant_id: str) -> AvatarState:
        if self.fail is not None:
            raise self.fail
        self.get_calls.append(assistant_id)
        return self.state

    async def clear(self, assistant_id: str) -> AvatarState:
        if self.fail is not None:
            raise self.fail
        self.clear_calls.append(assistant_id)
        return self.state


class FakeCronService:
    """捕获 ``add_job`` 调用并支持注入失败的假 CronService。"""

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.fail: Exception | None = None

    def add_job(self, **kwargs: Any) -> object:
        if self.fail is not None:
            raise self.fail
        self.jobs.append(kwargs)
        from lca.contracts.models.cron.models import CronJob

        return CronJob(
            id=kwargs["id"],
            title=kwargs["title"],
            schedule=kwargs["schedule"],
            timezone=kwargs["timezone"],
            body=kwargs["body"],
            execution=kwargs["execution"],
            delivery_targets=kwargs["delivery_targets"],
            report=kwargs["report"],
            owner=kwargs["owner"],
            created_chat_id=kwargs["created_chat_id"],
            anchor_at=kwargs["now"],
        )


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    avatar_service_registry.clear()
    yield
    avatar_service_registry.clear()


@pytest.fixture()
def fake_service() -> FakeAvatarService:
    service = FakeAvatarService()
    avatar_service_registry.register(ASSISTANT_ID, service)
    return service


@contextmanager
def _bound_assistant(assistant_id: str = ASSISTANT_ID) -> Any:
    with bind_run_ambit(RunAmbit(assistant_id=assistant_id)):
        yield


# ── MANIFEST / 工具元数据 ──────────────────────────────────────────────


def test_tool_manifests_exist() -> None:
    assert AvatarCreateTool.name == "avatar_create"
    assert AvatarEditTool.name == "avatar_edit"
    assert AvatarSetTool.name == "avatar_set"
    assert AvatarGetTool.name == "avatar_get"
    assert AvatarClearTool.name == "avatar_clear"
    assert AvatarScheduleTool.name == "avatar_schedule"
    for cls in (
        AvatarCreateTool,
        AvatarEditTool,
        AvatarSetTool,
        AvatarGetTool,
        AvatarClearTool,
        AvatarScheduleTool,
    ):
        assert cls.namespace == "avatar"


def test_manifest_exposes_all_six_apis() -> None:
    names = {api.name for api in MANIFEST.api}
    assert names == {
        "avatar_create",
        "avatar_edit",
        "avatar_set",
        "avatar_get",
        "avatar_clear",
        "avatar_schedule",
    }
    effects = {api.name: api.effects for api in MANIFEST.api}
    assert effects["avatar_get"] == "read"
    assert effects["avatar_create"] == "write"
    assert effects["avatar_edit"] == "write"
    assert effects["avatar_set"] == "write"
    assert effects["avatar_clear"] == "write"
    assert effects["avatar_schedule"] == "write"


# ── validate 前置校验 ──────────────────────────────────────────────────


def test_create_tool_requires_user_request() -> None:
    tool = AvatarCreateTool()
    assert tool.validate({"user_request": ""}) is not None
    assert tool.validate({"user_request": "   "}) is not None
    assert tool.validate({}) is not None
    assert tool.validate({"user_request": "换个头像"}) is None


def test_edit_tool_requires_user_request() -> None:
    tool = AvatarEditTool()
    assert tool.validate({"user_request": ""}) is not None
    assert tool.validate({"user_request": "   "}) is not None
    assert tool.validate({}) is not None
    assert tool.validate({"user_request": "换件圣诞毛衣"}) is None


def test_set_tool_requires_candidate_id() -> None:
    tool = AvatarSetTool()
    assert tool.validate({"candidate_id": ""}) is not None
    assert tool.validate({}) is not None
    assert tool.validate({"candidate_id": "c1"}) is None


def test_get_tool_has_no_required_params() -> None:
    tool = AvatarGetTool()
    assert tool.validate({}) is None


def test_clear_tool_has_no_required_params() -> None:
    tool = AvatarClearTool()
    assert tool.validate({}) is None


def test_schedule_tool_requires_user_request_and_schedule() -> None:
    tool = AvatarScheduleTool()
    assert tool.validate({}) is not None
    assert tool.validate({"user_request": ""}) is not None
    assert tool.validate({"user_request": "x"}) is not None
    assert (
        tool.validate(
            {"user_request": "雨天装扮", "schedule": {"kind": "daily", "hour": 12, "minute": 0}}
        )
        is None
    )


def test_create_tool_rejects_non_string_user_request() -> None:
    tool = AvatarCreateTool()
    assert tool.validate({"user_request": 123}) is not None
    assert tool.validate({"user_request": True}) is not None


def test_edit_tool_rejects_non_string_user_request() -> None:
    tool = AvatarEditTool()
    assert tool.validate({"user_request": 123}) is not None
    assert tool.validate({"user_request": True}) is not None


def test_set_tool_rejects_non_string_candidate_id() -> None:
    tool = AvatarSetTool()
    assert tool.validate({"candidate_id": 123}) is not None
    assert tool.validate({"candidate_id": True}) is not None


def test_schedule_tool_rejects_non_string_user_request() -> None:
    tool = AvatarScheduleTool()
    assert tool.validate({"user_request": 123, "schedule": {"kind": "daily"}}) is not None
    assert tool.validate({"user_request": True, "schedule": {"kind": "daily"}}) is not None


# ── execute 成功路径（经注册表注入 fake service） ──────────────────────


@pytest.mark.asyncio
async def test_create_execute_returns_candidates(fake_service: FakeAvatarService) -> None:
    tool = AvatarCreateTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": "换个赛博朋克头像"})
    assert obs.success is True
    assert obs.error is None
    assert fake_service.created == [(ASSISTANT_ID, "换个赛博朋克头像")]
    assert obs.payload["candidates"][0]["candidate_id"] == "c1"


@pytest.mark.asyncio
async def test_create_execute_validates_before_service(fake_service: FakeAvatarService) -> None:
    tool = AvatarCreateTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": ""})
    assert obs.success is False
    assert "user_request" in obs.error
    assert fake_service.created == []


@pytest.mark.asyncio
async def test_create_execute_rejects_non_string_user_request(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarCreateTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": 123})
    assert obs.success is False
    assert "user_request" in obs.error
    assert fake_service.created == []


@pytest.mark.asyncio
async def test_edit_execute_defaults_reference_to_none(fake_service: FakeAvatarService) -> None:
    tool = AvatarEditTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": "换件毛衣"})
    assert obs.success is True
    assert obs.error is None
    assert fake_service.edits == [(ASSISTANT_ID, "换件毛衣", None)]


@pytest.mark.asyncio
async def test_edit_execute_rejects_base64_reference(fake_service: FakeAvatarService) -> None:
    """裸 base64 来源不明，必须拒绝（spec §12 红线）。"""
    tool = AvatarEditTool()
    png_b64 = base64.b64encode(b"image-bytes").decode()
    with _bound_assistant():
        obs = await tool.execute(
            {"user_request": "换件毛衣", "reference_image": f"data:image/png;base64,{png_b64}"}
        )
    assert obs.success is False
    assert "/files/" in obs.error
    assert fake_service.edits == []


@pytest.mark.asyncio
async def test_edit_execute_rejects_data_uri_reference(fake_service: FakeAvatarService) -> None:
    """data URI 来源不明，必须拒绝（spec §12 红线）。"""
    tool = AvatarEditTool()
    with _bound_assistant():
        obs = await tool.execute(
            {"user_request": "换件毛衣", "reference_image": "data:image/png;base64,AAAA"}
        )
    assert obs.success is False
    assert "/files/" in obs.error
    assert fake_service.edits == []


@pytest.mark.asyncio
async def test_edit_execute_resolves_filestore_reference(
    tmp_path: Path, fake_service: FakeAvatarService
) -> None:
    store = LocalFileStore(root=tmp_path)
    store.put(data=b"user-photo", name="photo.png", mime_type="image/png")
    aid = next(iter(store._root.iterdir())).name  # type: ignore[attr-defined]
    tool = AvatarEditTool()
    with bind_run_ambit(RunAmbit(assistant_id=ASSISTANT_ID, file_store=store)):
        obs = await tool.execute({"user_request": "换件毛衣", "reference_image": f"/files/{aid}"})
    assert obs.success is True
    assert fake_service.edits[0][2] == b"user-photo"


@pytest.mark.asyncio
async def test_edit_execute_rejects_non_filestore_reference(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarEditTool()
    with _bound_assistant():
        obs = await tool.execute(
            {"user_request": "换件毛衣", "reference_image": "not a valid image !!"}
        )
    assert obs.success is False
    assert "/files/" in obs.error
    assert fake_service.edits == []


@pytest.mark.asyncio
async def test_edit_execute_rejects_non_string_user_request(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarEditTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": True})
    assert obs.success is False
    assert "user_request" in obs.error
    assert fake_service.edits == []


@pytest.mark.asyncio
async def test_set_execute_returns_active_bundle(fake_service: FakeAvatarService) -> None:
    tool = AvatarSetTool()
    with _bound_assistant():
        obs = await tool.execute({"candidate_id": "c1"})
    assert obs.success is True
    assert obs.error is None
    assert fake_service.set_calls == [(ASSISTANT_ID, "c1")]
    assert obs.payload["active"]["candidate_id"] == "c1"


@pytest.mark.asyncio
async def test_set_execute_rejects_non_string_candidate_id(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarSetTool()
    with _bound_assistant():
        obs = await tool.execute({"candidate_id": 123})
    assert obs.success is False
    assert "candidate_id" in obs.error
    assert fake_service.set_calls == []


@pytest.mark.asyncio
async def test_get_execute_returns_state(fake_service: FakeAvatarService) -> None:
    tool = AvatarGetTool()
    with _bound_assistant():
        obs = await tool.execute({})
    assert obs.success is True
    assert obs.error is None
    assert fake_service.get_calls == [ASSISTANT_ID]
    assert obs.payload["state"]["assistant_id"] == ASSISTANT_ID


@pytest.mark.asyncio
async def test_clear_execute_returns_state(fake_service: FakeAvatarService) -> None:
    tool = AvatarClearTool()
    with _bound_assistant():
        obs = await tool.execute({})
    assert obs.success is True
    assert obs.error is None
    assert fake_service.clear_calls == [ASSISTANT_ID]
    assert obs.payload["state"]["assistant_id"] == ASSISTANT_ID


# ── execute 失败路径 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_execute_returns_failure_observation(
    fake_service: FakeAvatarService,
) -> None:
    fake_service.fail = RuntimeError("boom")
    tool = AvatarCreateTool()
    with _bound_assistant():
        obs = await tool.execute({"user_request": "换个头像"})
    assert obs.success is False
    assert obs.payload is None
    assert "boom" in obs.error


@pytest.mark.asyncio
async def test_get_execute_returns_failure_observation(
    fake_service: FakeAvatarService,
) -> None:
    fake_service.fail = RuntimeError("boom")
    tool = AvatarGetTool()
    with _bound_assistant():
        obs = await tool.execute({})
    assert obs.success is False
    assert "boom" in obs.error


# ── avatar_schedule ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_execute_persists_cron_job(
    tmp_path: Path, fake_service: FakeAvatarService
) -> None:
    store = CronStore(tmp_path)
    service = CronService(store)
    tool = AvatarScheduleTool(service=service)
    with _bound_assistant():
        obs = await tool.execute(
            {
                "user_request": "雨天装扮",
                "schedule": {"kind": "daily", "hour": 12, "minute": 0},
            }
        )
    assert obs.success is True
    assert obs.error is None
    assert fake_service.created == []
    jobs = store.list_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "avatar costume change"
    assert job.body == "雨天装扮"
    assert job.owner == ASSISTANT_ID
    assert job.created_chat_id == "system"
    assert job.report == "anomalies_only"
    assert job.delivery_targets == ()
    assert job.timezone == "Asia/Shanghai"
    assert job.execution.kind == "space_action"
    assert job.execution.artifact_id == "avatar"


@pytest.mark.asyncio
async def test_schedule_execute_captures_add_job_kwargs(fake_service: FakeAvatarService) -> None:
    cron = FakeCronService()
    tool = AvatarScheduleTool(service=cron)
    with _bound_assistant():
        obs = await tool.execute(
            {
                "user_request": "雨天装扮",
                "schedule": {"kind": "hourly", "minute": 30},
                "timezone": "UTC",
            }
        )
    assert obs.success is True
    assert len(cron.jobs) == 1
    job = cron.jobs[0]
    assert job["title"] == "avatar costume change"
    assert job["owner"] == ASSISTANT_ID
    assert job["body"] == "雨天装扮"
    assert job["report"] == "anomalies_only"
    assert job["delivery_targets"] == ()
    assert job["created_chat_id"] == "system"
    assert job["timezone"] == "UTC"
    assert job["execution"].artifact_id == "avatar"


@pytest.mark.asyncio
async def test_schedule_execute_rejects_invalid_schedule(fake_service: FakeAvatarService) -> None:
    tool = AvatarScheduleTool(service=FakeCronService())
    with _bound_assistant():
        obs = await tool.execute({"user_request": "雨天装扮", "schedule": {"kind": "daily"}})
    assert obs.success is False
    assert obs.error is not None


@pytest.mark.asyncio
async def test_schedule_execute_rejects_non_string_user_request(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarScheduleTool(service=FakeCronService())
    with _bound_assistant():
        obs = await tool.execute(
            {
                "user_request": 123,
                "schedule": {"kind": "daily", "hour": 12, "minute": 0},
            }
        )
    assert obs.success is False
    assert "user_request" in obs.error


@pytest.mark.asyncio
async def test_schedule_execute_returns_failure_observation(
    fake_service: FakeAvatarService,
) -> None:
    cron = FakeCronService()
    cron.fail = ValueError("bad schedule")
    tool = AvatarScheduleTool(service=cron)
    with _bound_assistant():
        obs = await tool.execute(
            {"user_request": "雨天装扮", "schedule": {"kind": "daily", "hour": 12, "minute": 0}}
        )
    assert obs.success is False
    assert "bad schedule" in obs.error


@pytest.mark.asyncio
async def test_schedule_execute_without_service_returns_failure(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarScheduleTool()
    with _bound_assistant():
        obs = await tool.execute(
            {"user_request": "雨天装扮", "schedule": {"kind": "daily", "hour": 12, "minute": 0}}
        )
    assert obs.success is False
    assert obs.error is not None


@pytest.mark.asyncio
async def test_create_execute_passes_visual_prompt_and_returns_widget_guidance(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarCreateTool()
    with _bound_assistant():
        obs = await tool.execute(
            {
                "user_request": "改成：弗洛伊德",
                "visual_prompt": "Portrait of Sigmund Freud, elderly psychoanalyst",
            }
        )
    assert obs.success is True
    assert fake_service.last_visual_prompt == "Portrait of Sigmund Freud, elderly psychoanalyst"
    assert "[widget:avatar_picker]" in obs.payload["widget_tag"]
    assert "DO NOT" in obs.payload["display_instruction"]


@pytest.mark.asyncio
async def test_edit_execute_passes_visual_prompt_and_returns_widget_guidance(
    fake_service: FakeAvatarService,
) -> None:
    tool = AvatarEditTool()
    with _bound_assistant():
        obs = await tool.execute(
            {
                "user_request": "换成弗洛伊德风格",
                "visual_prompt": "Portrait of Sigmund Freud",
            }
        )
    assert obs.success is True
    assert fake_service.last_visual_prompt == "Portrait of Sigmund Freud"
    assert "[widget:avatar_picker]" in obs.payload["widget_tag"]
    assert "DO NOT" in obs.payload["display_instruction"]


def test_create_tool_rejects_non_string_visual_prompt() -> None:
    tool = AvatarCreateTool()
    assert tool.validate({"user_request": "换个头像", "visual_prompt": 123}) is not None


def test_edit_tool_rejects_non_string_visual_prompt() -> None:
    tool = AvatarEditTool()
    assert tool.validate({"user_request": "换个头像", "visual_prompt": ["foo"]}) is not None


def test_tools_schema_and_description_contain_visual_prompt_guidance() -> None:
    for tool_cls in (AvatarCreateTool, AvatarEditTool):
        assert "visual_prompt" in tool_cls.parameters["properties"]
        prop = tool_cls.parameters["properties"]["visual_prompt"]
        desc = prop["description"]
        assert "肖像" in desc or "视觉特征" in desc
        assert "面部" in desc or "风格" in desc or "光影" in desc
        assert "[widget:avatar_picker]" in tool_cls.description
        assert "DO NOT" in tool_cls.description

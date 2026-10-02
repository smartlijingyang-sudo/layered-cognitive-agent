"""Avatar agent 工具注册（ADR-0269 §4，Task 9）。

注册六个 ``avatar`` 命名空间工具：

- ``avatar_create`` / ``avatar_edit`` —— 生成候选进池，绝不激活；
- ``avatar_set`` —— 激活候选；
- ``avatar_get`` —— 返回 ``AvatarState``；
- ``avatar_clear`` —— 恢复默认头像；
- ``avatar_schedule`` —— 创建定时换装 CronJob（``SpaceActionExecution``）。

当前助理经 ``lca.plugins.avatar.registry.avatar_service_registry`` 的
``current()`` / ``current_assistant_id()`` 解析（RunAmbit.assistant_id）。
``avatar_schedule`` 复用 cron 工具的 schedule 判别联合解析与 run 上下文
chat id 解析（ADR-0268），``created_chat_id`` 取不到时回退 ``"system"``。
"""

from __future__ import annotations

import base64
import binascii
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.models.cron.models import SpaceActionExecution
from lca.contracts.protocols import Tool
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.facade.run.ambit import current_file_store
from lca.infrastructure.tools.cron.common import _parse_schedule, _resolve_chat_id
from lca.plugins.avatar.registry import avatar_service_registry


def _success_observation(payload: dict[str, Any], started: float) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _error_observation(error: str, started: float) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=error,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _decode_reference_image(value: Any) -> bytes | None:
    """把 ``avatar_edit`` 的 ``reference_image`` 解码为图片字节。

    接受三种来源：

    - ``data:image/...;base64,<b64>`` data URI；
    - 裸 base64 字符串；
    - ``/files/<attachment_id>`` FileStore 用户上传引用。

    参数缺省/空时返回 ``None``（服务端回退读当前 active 头像）。
    无法识别的来源抛 ``ValueError``，由 execute 转成失败 Observation。
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reference_image must be a non-empty string")
    raw = value.strip()
    if raw.startswith("/files/"):
        aid = raw[len("/files/") :].rstrip("/")
        if not aid:
            raise ValueError("reference_image file reference missing attachment id")
        store = current_file_store()
        if store is None:
            raise ValueError("no file store in run context for reference_image")
        data = store.read_bytes(aid)
        if data is None:
            raise ValueError(f"reference_image attachment not found: {aid}")
        return data
    if raw.startswith("data:"):
        if "base64," not in raw:
            raise ValueError("unsupported data URI: expected base64 payload")
        return base64.b64decode(raw.partition("base64,")[2].strip())
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "reference_image is neither a valid base64 string nor a /files/ reference"
        ) from exc


class AvatarCreateTool(Tool):
    """从用户请求生成新头像候选，绝不自动激活（两轮分离，ADR-0269 §4）。"""

    name = "avatar_create"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    namespace = "avatar"
    description = "Generate new avatar candidates from the user's request. Never activates."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "user_request": {"type": "string", "description": "用户原话，原样传递"},
        },
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
        error = self.validate(args)
        if error is not None:
            return _error_observation(error, started)
        try:
            assistant_id = avatar_service_registry.current_assistant_id()
            service = avatar_service_registry.current()
            candidates = await service.create(assistant_id, str(args["user_request"]))
            return _success_observation(
                {"candidates": [c.model_dump() for c in candidates]}, started
            )
        except Exception as exc:
            return _error_observation(str(exc), started)


class AvatarEditTool(Tool):
    """img2img 生成新头像候选，可选参考图；绝不自动激活。"""

    name = "avatar_edit"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    namespace = "avatar"
    description = (
        "Generate img2img avatar candidates from the user's request, optionally "
        "from a reference image. Never activates."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "user_request": {"type": "string", "description": "用户原话，原样传递"},
            "reference_image": {
                "type": "string",
                "description": (
                    "可选：base64（data URI 或裸 base64）或 /files/<attachment_id> 用户上传引用。"
                    "缺省读当前 active 头像。"
                ),
            },
        },
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
        error = self.validate(args)
        if error is not None:
            return _error_observation(error, started)
        try:
            reference_image = _decode_reference_image(args.get("reference_image"))
            assistant_id = avatar_service_registry.current_assistant_id()
            service = avatar_service_registry.current()
            candidates = await service.edit(
                assistant_id,
                str(args["user_request"]),
                reference_image=reference_image,
            )
            return _success_observation(
                {"candidates": [c.model_dump() for c in candidates]}, started
            )
        except Exception as exc:
            return _error_observation(str(exc), started)


class AvatarSetTool(Tool):
    """按 candidate_id 激活头像候选（幂等：同一候选重复 set 返回同一 active）。"""

    name = "avatar_set"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    namespace = "avatar"
    description = "Activate an avatar candidate by id."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string", "description": "要激活的候选 id"},
        },
        "required": ["candidate_id"],
    }
    is_idempotent = True
    default_timeout_s = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        return None if str(args.get("candidate_id", "")).strip() else "candidate_id is required"

    async def execute(self, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return _error_observation(error, started)
        try:
            assistant_id = avatar_service_registry.current_assistant_id()
            service = avatar_service_registry.current()
            bundle = await service.set(assistant_id, str(args["candidate_id"]))
            return _success_observation({"active": bundle.model_dump()}, started)
        except Exception as exc:
            return _error_observation(str(exc), started)


class AvatarGetTool(Tool):
    """返回当前头像状态（active + 候选池）。"""

    name = "avatar_get"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    namespace = "avatar"
    description = "Return the current avatar state (active bundle + candidate pool)."
    parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}
    is_idempotent = True
    default_timeout_s = 10

    def validate(self, args: dict[str, Any]) -> str | None:
        del args
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        started = time.monotonic()
        try:
            assistant_id = avatar_service_registry.current_assistant_id()
            service = avatar_service_registry.current()
            state = await service.get(assistant_id)
            return _success_observation({"state": state.model_dump()}, started)
        except Exception as exc:
            return _error_observation(str(exc), started)


class AvatarClearTool(Tool):
    """清除 active 头像，恢复默认头像。"""

    name = "avatar_clear"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    namespace = "avatar"
    description = "Clear the active avatar and restore the default."
    parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}
    is_idempotent = True
    default_timeout_s = 10

    def validate(self, args: dict[str, Any]) -> str | None:
        del args
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        started = time.monotonic()
        try:
            assistant_id = avatar_service_registry.current_assistant_id()
            service = avatar_service_registry.current()
            state = await service.clear(assistant_id)
            return _success_observation({"state": state.model_dump()}, started)
        except Exception as exc:
            return _error_observation(str(exc), started)


def _cron_service() -> CronService:
    """从 run bindings 构造当前助理的 CronService。

    与 cron 工具工厂同源（ADR-0268）：CronStore 位于 assistant home 下。
    run 未绑定 assistant home 时抛错，由 execute 转成失败 Observation，
    不猜测存储位置。
    """
    from lca.infrastructure.runtime_plane.capability_bindings import current_bindings_view

    view = current_bindings_view()
    home_path = getattr(view, "home_path", None) if view is not None else None
    if not home_path:
        raise RuntimeError("no assistant home path in run bindings")
    return CronService(CronStore(Path(home_path)))


class AvatarScheduleTool(Tool):
    """创建定时换装 CronJob（ADR-0269 §5，Task 8 调度器消费）。"""

    name = "avatar_schedule"
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    namespace = "avatar"
    description = "Schedule a periodic avatar costume change by creating a cron job."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "user_request": {"type": "string", "description": "换装请求原文，作为 cron body"},
            "schedule": {
                "type": "object",
                "description": (
                    "调度定义，由 kind 判别：oneshot 带 at（ISO 8601，aware）；"
                    "interval 带 every_seconds；hourly 带 minute；daily 带 hour/minute；"
                    "weekly 带 weekday（0=周一…6=周日）/hour/minute。"
                ),
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["oneshot", "interval", "hourly", "daily", "weekly"],
                    },
                    "at": {"type": "string", "description": "oneshot 触发时刻（ISO 8601，带时区）"},
                    "every_seconds": {"type": "integer", "description": "interval 间隔秒数（>0）"},
                    "minute": {
                        "type": "integer",
                        "description": "hourly/daily/weekly 的分钟（0-59）",
                    },
                    "hour": {"type": "integer", "description": "daily/weekly 的小时（0-23）"},
                    "weekday": {
                        "type": "integer",
                        "description": "weekly 的星期几（0=周一…6=周日）",
                    },
                },
                "required": ["kind"],
            },
            "timezone": {
                "type": "string",
                "description": "IANA 时区，缺省 Asia/Shanghai",
                "default": "Asia/Shanghai",
            },
        },
        "required": ["user_request", "schedule"],
    }
    is_idempotent = False
    default_timeout_s = 30

    def __init__(self, *, service: CronService | None = None, owner: str | None = None) -> None:
        self._service = service
        self._owner = owner

    def validate(self, args: dict[str, Any]) -> str | None:
        if not str(args.get("user_request", "")).strip():
            return "user_request must be non-empty"
        schedule = args.get("schedule")
        if not isinstance(schedule, dict) or not isinstance(schedule.get("kind"), str):
            return "schedule must be an object with a 'kind'"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return _error_observation(error, started)
        try:
            owner = self._owner or avatar_service_registry.current_assistant_id()
            if not owner:
                raise RuntimeError("no current assistant")
            service = self._service or _cron_service()
            schedule = _parse_schedule(args["schedule"])
            # ``created_chat_id`` 取 run 上下文 chat id；不可用时回退 "system"
            # （换装任务无投递目标，该字段仅作审计来源，不参与投递）。
            chat_id = _resolve_chat_id(args) or "system"
            job = service.add_job(
                id=new_id("avatar_schedule"),
                title="avatar costume change",
                schedule=schedule,
                timezone=str(args.get("timezone") or "Asia/Shanghai"),
                body=str(args["user_request"]),
                execution=SpaceActionExecution(artifact_id="avatar"),
                delivery_targets=(),
                report="anomalies_only",
                owner=owner,
                created_chat_id=chat_id,
                now=datetime.now(UTC),
            )
            return _success_observation({"job": job.model_dump()}, started)
        except Exception as exc:
            return _error_observation(str(exc), started)


MANIFEST = ToolManifest(
    identifier="avatar",
    type="builtin",
    api=(
        ToolApi(
            name="avatar_create",
            description=AvatarCreateTool.description,
            parameters=AvatarCreateTool.parameters,
            is_idempotent=AvatarCreateTool.is_idempotent,
            effect_kind=AvatarCreateTool.effect_kind,
            default_timeout_ms=AvatarCreateTool.default_timeout_s * 1000,
            effects="write",
            namespace="avatar",
        ),
        ToolApi(
            name="avatar_edit",
            description=AvatarEditTool.description,
            parameters=AvatarEditTool.parameters,
            is_idempotent=AvatarEditTool.is_idempotent,
            effect_kind=AvatarEditTool.effect_kind,
            default_timeout_ms=AvatarEditTool.default_timeout_s * 1000,
            effects="write",
            namespace="avatar",
        ),
        ToolApi(
            name="avatar_set",
            description=AvatarSetTool.description,
            parameters=AvatarSetTool.parameters,
            is_idempotent=AvatarSetTool.is_idempotent,
            effect_kind=AvatarSetTool.effect_kind,
            default_timeout_ms=AvatarSetTool.default_timeout_s * 1000,
            effects="write",
            namespace="avatar",
        ),
        ToolApi(
            name="avatar_get",
            description=AvatarGetTool.description,
            parameters=AvatarGetTool.parameters,
            is_idempotent=AvatarGetTool.is_idempotent,
            effect_kind=AvatarGetTool.effect_kind,
            default_timeout_ms=AvatarGetTool.default_timeout_s * 1000,
            effects="read",
            namespace="avatar",
        ),
        ToolApi(
            name="avatar_clear",
            description=AvatarClearTool.description,
            parameters=AvatarClearTool.parameters,
            is_idempotent=AvatarClearTool.is_idempotent,
            effect_kind=AvatarClearTool.effect_kind,
            default_timeout_ms=AvatarClearTool.default_timeout_s * 1000,
            effects="write",
            namespace="avatar",
        ),
        ToolApi(
            name="avatar_schedule",
            description=AvatarScheduleTool.description,
            parameters=AvatarScheduleTool.parameters,
            is_idempotent=AvatarScheduleTool.is_idempotent,
            effect_kind=AvatarScheduleTool.effect_kind,
            default_timeout_ms=AvatarScheduleTool.default_timeout_s * 1000,
            effects="write",
            namespace="avatar",
        ),
    ),
    meta=ToolMeta(
        avatar="🖼️",
        title="avatar",
        description="Assistant avatar generation, activation and costume-change scheduling.",
    ),
    parameters={
        "user_request": ParameterSpec(
            type="string",
            required=True,
            description="用户原话，原样传递",
        ),
        "candidate_id": ParameterSpec(
            type="string",
            required=True,
            description="要激活的候选 id",
        ),
        "reference_image": ParameterSpec(
            type="string",
            required=False,
            description="base64 或 /files/<attachment_id> 用户上传引用",
        ),
        "schedule": ParameterSpec(
            type="object",
            required=True,
            ui_hint="object",
            description="CronJob schedule 判别联合",
        ),
        "timezone": ParameterSpec(
            type="string",
            required=False,
            default="Asia/Shanghai",
            description="IANA 时区",
        ),
    },
)


@plugin(
    id="lca-tool-avatar",
    provides=["tools.avatar_*"],
    requires=["tools"],
    implements=["Tool"],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="tools",
    description="Register the six avatar agent tools (ADR-0269 §4).",
    test_suite="tests/plugins/avatar/test_tools.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("tool.invoke",)),
        observability=EvidenceContract(
            descriptors=("lca-tool-avatar.checked", "lca-tool-avatar.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("tool.invoke", "tools"),
        emits=("tools.avatar_*.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """把六个 avatar 工具注册进 per-run 工具注册表。"""

    del config
    tools = ctx.require("tools")
    tools.register(AvatarCreateTool())
    tools.register(AvatarEditTool())
    tools.register(AvatarSetTool())
    tools.register(AvatarGetTool())
    tools.register(AvatarClearTool())
    tools.register(AvatarScheduleTool())


__all__ = [
    "MANIFEST",
    "AvatarClearTool",
    "AvatarCreateTool",
    "AvatarEditTool",
    "AvatarGetTool",
    "AvatarScheduleTool",
    "AvatarSetTool",
]

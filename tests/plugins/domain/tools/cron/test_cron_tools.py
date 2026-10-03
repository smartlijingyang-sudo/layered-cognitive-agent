"""cron 工具与工厂测试（ADR-0268 §4、§5、§9、§10）。

验证：cron.add 创建任务且重复 id 不覆盖；cron.list 只返回投影闭集；
cron.view 返回完整定义与 run 记录；cron.update / cron.remove 不调用
写函数（存储不变）；插件工厂在绑定 assistant home 时物化五个工具。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.models.cron.models import TargetReceipt
from lca.contracts.protocols import Tool
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.infrastructure.observability.facade.run.ambit import RunAmbit, bind_run_ambit
from lca.infrastructure.tools.cron import build_cron_tools
from lca.plugins.domain.tools.cron.plugin import _cron_tools_factory

_CRON_LIST_FIELDS = frozenset(
    {
        "id",
        "title",
        "schedule_label",
        "next_run_local",
        "due",
        "enabled",
        "last_run_local",
        "last_delivery",
    }
)


def _service(tmp_path: Path) -> CronService:
    return CronService(CronStore(tmp_path))


def _tools(service: CronService) -> dict[str, Tool]:
    return {tool.name: tool for tool in build_cron_tools(service=service, owner="asst_1")}


def _add_args(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "job_1",
        "title": "每日提醒",
        "schedule": {"kind": "daily", "hour": 9, "minute": 0},
        "timezone": "Asia/Shanghai",
        "body": "提醒我同步进度",
        "execution": {"kind": "agent"},
        "chat_id": "chat_1",
    }
    base.update(overrides)
    return base


async def test_cron_add_creates_job(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    obs = await tools["cron.add"].execute(_add_args())
    assert obs.success is True
    job = svc.get_job("job_1")
    assert job is not None
    assert job.title == "每日提醒"
    assert job.owner == "asst_1"
    assert job.created_chat_id == "chat_1"
    assert job.anchor_at.tzinfo is not None
    assert obs.payload["job"]["id"] == "job_1"


async def test_cron_add_duplicate_id_does_not_overwrite(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    await tools["cron.add"].execute(_add_args())
    second = await tools["cron.add"].execute(
        _add_args(
            title="另一个标题",
            schedule={"kind": "daily", "hour": 8, "minute": 0},
        )
    )
    assert second.success is True
    again = svc.get_job("job_1")
    assert again is not None
    assert again.title == "每日提醒"


async def test_cron_add_requires_chat_id(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    obs = await tools["cron.add"].execute(_add_args(chat_id=""))
    assert obs.success is False
    assert "chat_id" in (obs.error or "")
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_VALIDATION
    assert svc.get_job("job_1") is None


async def test_cron_add_resolves_chat_id_and_timezone_from_ambient(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    with bind_run_ambit(RunAmbit(topic_id="topic_ambient_1", run_id="run_ambient_1")):
        args = _add_args(id="job_ambient")
        args.pop("chat_id")
        args.pop("timezone")
        obs = await tools["cron.add"].execute(args)
        assert obs.success is True
        job = svc.get_job("job_ambient")
        assert job is not None
        assert job.created_chat_id == "topic_ambient_1"
        assert job.timezone == "Asia/Shanghai"


async def test_cron_add_resolves_run_id_when_chat_id_and_topic_id_empty(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    with bind_run_ambit(RunAmbit(run_id="run_solo_123")):
        args = _add_args(id="job_solo")
        args.pop("chat_id")
        obs = await tools["cron.add"].execute(args)
        assert obs.success is True
        job = svc.get_job("job_solo")
        assert job is not None
        assert job.created_chat_id == "run_solo_123"


async def test_cron_list_returns_projection_closed_set(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    await tools["cron.add"].execute(_add_args())
    obs = await tools["cron.list"].execute({})
    assert obs.success is True
    items = obs.payload["items"]
    assert len(items) == 1
    item = items[0]
    assert set(item.keys()) == _CRON_LIST_FIELDS
    assert item["id"] == "job_1"
    assert item["schedule_label"] == "每天 09:00"
    assert item["next_run_local"] is not None
    assert item["due"] is False
    assert item["enabled"] is True
    assert item["last_run_local"] is None
    assert item["last_delivery"] is None


async def test_cron_view_returns_definition_and_runs(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    await tools["cron.add"].execute(_add_args())
    obs = await tools["cron.view"].execute({"id": "job_1"})
    assert obs.success is True
    assert obs.payload["job"]["id"] == "job_1"
    assert obs.payload["job"]["timezone"] == "Asia/Shanghai"
    assert obs.payload["runs"] == []

    svc._store.append_run(
        "job_1",
        run_id="run_1",
        outcome="completed",
        receipts=(TargetReceipt(chat_id="chat_1", state="delivered"),),
        finished_at=datetime(2026, 10, 1, 9, 1, tzinfo=UTC),
    )
    obs2 = await tools["cron.view"].execute({"id": "job_1"})
    assert len(obs2.payload["runs"]) == 1
    assert obs2.payload["runs"][0]["run_id"] == "run_1"


async def test_cron_view_missing_job_is_error(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    obs = await tools["cron.view"].execute({"id": "missing"})
    assert obs.success is False
    assert "not found" in (obs.error or "")
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_VALIDATION


async def test_cron_update_does_not_write(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    await tools["cron.add"].execute(_add_args())
    before = svc.get_job("job_1")
    assert before is not None
    before_dump = before.model_dump()

    obs = await tools["cron.update"].execute(
        _add_args(
            title="新标题",
            schedule={"kind": "daily", "hour": 8, "minute": 0},
        )
    )
    assert obs.success is False
    assert "审批" in (obs.error or "")
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_VALIDATION
    assert obs.extra["approval_request"]["type"] == "cron_update"
    assert obs.extra["approval_request"]["job_id"] == "job_1"

    after = svc.get_job("job_1")
    assert after is not None
    assert after.model_dump() == before_dump


async def test_cron_remove_does_not_write(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = _tools(svc)
    await tools["cron.add"].execute(_add_args())
    assert svc.get_job("job_1") is not None

    obs = await tools["cron.remove"].execute({"id": "job_1"})
    assert obs.success is False
    assert "审批" in (obs.error or "")
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_VALIDATION
    assert obs.extra["approval_request"]["type"] == "cron_remove"
    assert obs.extra["approval_request"]["job_id"] == "job_1"

    # 存储不变：定义仍存在。
    assert svc.get_job("job_1") is not None


def test_build_tools_returns_five_cron_tools(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tools = build_cron_tools(service=svc, owner="asst_1")
    assert [tool.name for tool in tools] == [
        "cron.add",
        "cron.view",
        "cron.list",
        "cron.update",
        "cron.remove",
    ]
    assert all(tool.namespace == "cron" for tool in tools)


def test_factory_materializes_tools_with_home_path(tmp_path: Path) -> None:
    bindings = BindingsView(home_path=str(tmp_path), assistant_id="asst_1")
    tools = _cron_tools_factory(bindings)
    assert tools is not None
    assert [tool.name for tool in tools] == [
        "cron.add",
        "cron.view",
        "cron.list",
        "cron.update",
        "cron.remove",
    ]
    assert all(tool.namespace == "cron" for tool in tools)


def test_factory_returns_none_without_home_path() -> None:
    bindings = BindingsView(assistant_id="asst_1")
    assert _cron_tools_factory(bindings) is None


def test_factory_returns_none_without_assistant_id(tmp_path: Path) -> None:
    bindings = BindingsView(home_path=str(tmp_path))
    assert _cron_tools_factory(bindings) is None

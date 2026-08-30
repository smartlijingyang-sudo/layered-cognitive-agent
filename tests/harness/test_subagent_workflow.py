"""Focused acceptance tests for Harness Phase E.3 and E.4."""

from __future__ import annotations

import asyncio

import pytest

from lca.contracts.harness.collaboration.agent import AgentIdentity, AgentOptions
from lca.contracts.harness.collaboration.subagent import (
    SubagentCapabilities,
    SubagentRequest,
    SubagentSpec,
)
from lca.contracts.harness.tasks.workflow import WorkflowMeta, WorkflowPhase
from lca.harness.subagents import SubagentActivationCoordinator, SubagentRegistry
from lca.harness.workflow import WorkflowEngine, agent, phase


class _Agent:
    def __init__(self) -> None:
        self.id = "agent"
        self.session_id = "agent"
        self.status = "idle"
        self.idle = False
        self.cancel_reason: str | None = None

    async def followup(self, message: object) -> object:
        raise NotImplementedError

    async def steer(self, message: object) -> object:
        raise NotImplementedError

    async def inject(self, message: object) -> object:
        raise NotImplementedError

    async def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None:
        del keep_inbox
        self.cancel_reason = reason

    async def when_idle(self) -> None:
        self.idle = True


class _Handle:
    def __init__(self) -> None:
        self.agent = _Agent()
        self.disposed: str | None = None

    async def dispose(self, reason: str = "owner") -> None:
        self.disposed = reason


@pytest.fixture
def activation() -> tuple[
    SubagentActivationCoordinator, list[tuple[AgentIdentity, AgentOptions, _Handle]]
]:
    registry = SubagentRegistry()
    registry.register(
        SubagentSpec(
            "researcher",
            SubagentCapabilities(
                frozenset({"research"}),
                tools_allow=frozenset({"search", "read"}),
                tools_deny=frozenset({"shell"}),
                max_delegation_depth=2,
            ),
        )
    )
    created: list[tuple[AgentIdentity, AgentOptions, _Handle]] = []

    async def create(spec: SubagentSpec, identity: AgentIdentity, options: AgentOptions) -> _Handle:
        handle = _Handle()
        created.append((identity, options, handle))
        return handle

    return SubagentActivationCoordinator(registry, create), created


async def test_subagent_negotiates_capabilities_lineage_and_tools(
    activation: tuple[
        SubagentActivationCoordinator, list[tuple[AgentIdentity, AgentOptions, _Handle]]
    ],
) -> None:
    manager, created = activation
    child = await manager.activate(
        SubagentRequest(
            "researcher",
            AgentIdentity("parent", delegation_depth=1),
            required_capabilities=frozenset({"research"}),
            requested_tools=frozenset({"search"}),
            options=AgentOptions(tools_allow=("search", "shell")),
        )
    )

    identity, options, _ = created[0]
    assert child.identity == identity
    assert identity.parent_session == "parent"
    assert identity.delegation_depth == 2
    assert options.tools_allow == ("search",)
    assert options.tools_deny == ("shell",)
    assert manager.children_of("parent") == (child,)


async def test_subagent_provider_allowlist_is_never_unrestricted(
    activation: tuple[
        SubagentActivationCoordinator, list[tuple[AgentIdentity, AgentOptions, _Handle]]
    ],
) -> None:
    manager, created = activation

    await manager.activate(SubagentRequest("researcher", AgentIdentity("parent")))

    assert created[0][1].tools_allow == ("read", "search")
    assert created[0][1].tools_deny == ("shell",)


@pytest.mark.parametrize(
    "subagent_request",
    [
        SubagentRequest(
            "researcher", AgentIdentity("p"), required_capabilities=frozenset({"write"})
        ),
        SubagentRequest("researcher", AgentIdentity("p", delegation_depth=2)),
        SubagentRequest("researcher", AgentIdentity("p"), requested_tools=frozenset({"shell"})),
    ],
)
async def test_subagent_rejects_unnegotiated_access(
    activation: tuple[
        SubagentActivationCoordinator, list[tuple[AgentIdentity, AgentOptions, _Handle]]
    ],
    subagent_request: SubagentRequest,
) -> None:
    manager, _ = activation
    with pytest.raises(PermissionError):
        await manager.activate(subagent_request)


async def test_child_cancellation_and_parent_drain(
    activation: tuple[
        SubagentActivationCoordinator, list[tuple[AgentIdentity, AgentOptions, _Handle]]
    ],
) -> None:
    manager, created = activation
    first = await manager.activate(SubagentRequest("researcher", AgentIdentity("parent")))
    await manager.cancel_child("parent", first.identity.session_id, "cancelled")
    assert created[0][2].disposed == "cancelled"

    await manager.activate(SubagentRequest("researcher", AgentIdentity("parent")))
    await manager.drain_parent("parent")
    assert created[1][2].agent.idle
    assert created[1][2].disposed == "parent_drain"
    assert not manager.children_of("parent")


async def test_workflow_runs_dependencies_then_parallel_ready_phases() -> None:
    meta = WorkflowMeta(
        "research",
        (
            WorkflowPhase("gather"),
            WorkflowPhase("facts", ("gather",)),
            WorkflowPhase("summary", ("gather",)),
            WorkflowPhase("publish", ("facts", "summary")),
        ),
    )
    running: set[str] = set()
    observed: dict[str, tuple[dict[str, object], set[str]]] = {}

    async def worker(context: object) -> str:
        ctx = context
        running.add(ctx.phase.name)
        observed[ctx.phase.name] = (ctx.dependency_results, set(running))
        await asyncio.sleep(0)
        running.remove(ctx.phase.name)
        return ctx.phase.name

    engine = WorkflowEngine()
    progress = []
    assert await engine.run(meta, worker, on_progress=progress.append) == {
        "gather": "gather",
        "facts": "facts",
        "summary": "summary",
        "publish": "publish",
    }
    assert observed["facts"][0] == {"gather": "gather"}
    assert observed["summary"][0] == {"gather": "gather"}
    assert observed["publish"][0] == {"facts": "facts", "summary": "summary"}
    assert {"facts", "summary"} <= observed["facts"][1] | observed["summary"][1]
    assert not progress[0].completed
    assert progress[-1].done
    assert engine.progress == progress[-1]


@pytest.mark.parametrize(
    "meta",
    [
        WorkflowMeta("", (WorkflowPhase("one"),)),
        WorkflowMeta("bad", (WorkflowPhase("one", ("missing",)),)),
        WorkflowMeta("bad", (WorkflowPhase("one", ("two",)), WorkflowPhase("two", ("one",)))),
    ],
)
def test_workflow_rejects_invalid_dags(meta: WorkflowMeta) -> None:
    with pytest.raises(ValueError):
        WorkflowEngine().validate(meta)


async def test_workflow_script_api() -> None:
    workflow = agent("brief")

    @phase(workflow, "draft")
    async def draft(context: object) -> str:
        return "draft"

    @workflow.phase("publish", deps=("draft",))
    async def publish(context: object) -> str:
        return context.dependency_results["draft"] + "-published"

    assert await workflow.run() == {"draft": "draft", "publish": "draft-published"}

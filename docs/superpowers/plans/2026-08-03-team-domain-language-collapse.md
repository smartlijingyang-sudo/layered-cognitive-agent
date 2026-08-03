# Team Domain Language Collapse — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Recipe/Process/SupervisorMode/MultiAgentTeam/Assembly public vocabulary with domain language (`Team`, `TeamLead`, `LeadMandate`, `Coordination` types) under a full breaking cutover (no shims).

**Architecture:** `Team = members + (TeamLead XOR Coordination)`. `TeamComposer` expands lead mandate or coordination value objects into closed object graphs + strategies. Strategies keep behavior; only names, registration keys, and public API change. Spec: `docs/superpowers/specs/2026-08-03-team-domain-language-collapse-design.md`.

**Tech Stack:** Python 3.12+, uv, pytest, ruff, mypy, import-linter, existing LCA five-layer layout.

**Verification after each wave (project order):**

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

---

## File map

| Path | Action | Responsibility |
|------|--------|----------------|
| `lca/contracts/team_coordination.py` | **Create** | `LeadMandate`, Coordination dataclasses, expand helpers (internal) |
| `lca/contracts/supervisor_mode.py` | **Delete** | Replaced by team_coordination |
| `lca/contracts/orchestration_taxonomy.py` | **Delete or gut** | Remove Family/Plane from code; no public export |
| `lca/contracts/enums.py` | **Modify** | Remove `TeamProcess`; optionally `ActionScope.SUPERVISOR` → `LEAD` |
| `lca/contracts/role_team.py` | **Modify** | `TeamConfig` holds coordination key + optional mandate (not process/mode) |
| `lca/contracts/protocols/orchestration.py` | **Modify** | Drop `SupervisorMode` helper; TeamContext config shape |
| `lca/layer4_app/composer.py` | **Create** (from assembly) | `AgentComposer`, `TeamComposer` |
| `lca/layer4_app/assembly.py` | **Delete** after move | — |
| `lca/layer4_app/api.py` | **Rewrite** | `Agent`, `Team`, `TeamLead`, sugar methods |
| `lca/layer4_app/defaults.py` | **Modify** | Register strategies by coordination/lead keys |
| `lca/layer4_app/team_wiring.py` | **Keep** | Transport wiring (maybe rename comments only) |
| `lca/layer3_agent/orchestration_strategies/lead.py` | **Rename** from hierarchical | `LeadStrategy` |
| `lca/layer3_agent/orchestration_strategies/*.py` | **Rename classes** | PeerRelay, FanOut, Pipeline names where cheap |
| `lca/layer3_agent/team_orchestrator.py` | **Optional rename** | `TeamRunner` |
| `lca/layer3_agent/orchestration_registry.py` | **Modify** | Keys are str strategy ids, not TeamProcess |
| `lca/__init__.py` | **Modify** | Export new public API |
| `tests/support/scenario_loader.py` | **Rewrite** | `lead` / `coordination` YAML only |
| `tests/fixtures/team_scenarios/*.yaml` | **Migrate** | New schema |
| `AGENTS.md` | **Rewrite** team section | ≤15 lines domain language |
| `docs/adr/0030-team-domain-language.md` | **Create** | Supersede 0027 user knobs + 0029 Recipe/Mode surface |

---

## Chunk 1: Contracts (domain types)

### Task 1: Add `team_coordination` contracts + failing tests

**Files:**
- Create: `lca/contracts/team_coordination.py`
- Create: `tests/test_team_coordination.py`
- Modify: `lca/contracts/__init__.py` (exports)

- [ ] **Step 1: Write failing tests for domain types and mutual exclusivity helpers**

```python
# tests/test_team_coordination.py
from lca.contracts.team_coordination import (
    LeadMandate,
    Pipeline,
    FanOut,
    PeerRelay,
    PeerSwarm,
    Debate,
    Graph,
    strategy_key_for_coordination,
    strategy_key_for_lead,
    gate_name_for_mandate,
)


def test_lead_mandate_values():
    assert LeadMandate.ROUTING == "routing"
    assert LeadMandate.CONSULT == "consult"
    assert LeadMandate.BOARD == "board"


def test_strategy_keys():
    assert strategy_key_for_coordination(Pipeline()) == "pipeline"
    assert strategy_key_for_coordination(FanOut()) == "fan_out"
    assert strategy_key_for_coordination(PeerRelay()) == "peer_relay"
    assert strategy_key_for_coordination(PeerSwarm()) == "peer_swarm"
    assert strategy_key_for_coordination(Debate()) == "debate"
    assert strategy_key_for_lead() == "lead"


def test_board_mandate_maps_to_must_consult_all():
    from lca.contracts.enums import DecisionGateName

    assert gate_name_for_mandate(LeadMandate.BOARD) == DecisionGateName.MUST_CONSULT_ALL
    assert gate_name_for_mandate(LeadMandate.ROUTING) == DecisionGateName.NONE
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
uv run pytest tests/test_team_coordination.py -v
```

- [ ] **Step 3: Implement `lca/contracts/team_coordination.py`**

```python
"""Team domain language: TeamLead mandate + Coordination value objects (ADR-0030)."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from lca.contracts.enums import DecisionGateName
from lca.contracts.graph import ExecutionGraph


class LeadMandate(str, Enum):
    ROUTING = "routing"
    CONSULT = "consult"
    BOARD = "board"


@dataclass(frozen=True)
class Pipeline:
    pass


@dataclass(frozen=True)
class FanOut:
    pass


@dataclass(frozen=True)
class PeerRelay:
    pass


@dataclass(frozen=True)
class PeerSwarm:
    max_rounds: int = 3


@dataclass(frozen=True)
class Debate:
    max_rounds: int = 3


@dataclass(frozen=True)
class Graph:
    execution_graph: ExecutionGraph


Coordination = Pipeline | FanOut | PeerRelay | PeerSwarm | Debate | Graph

_COORD_KEYS: dict[type, str] = {
    Pipeline: "pipeline",
    FanOut: "fan_out",
    PeerRelay: "peer_relay",
    PeerSwarm: "peer_swarm",
    Debate: "debate",
    Graph: "graph",
}

STRATEGY_KEY_LEAD = "lead"


def strategy_key_for_coordination(c: Coordination) -> str:
    if type(c) is Graph:
        return "graph"
    return _COORD_KEYS[type(c)]


def strategy_key_for_lead() -> str:
    return STRATEGY_KEY_LEAD


def gate_name_for_mandate(m: LeadMandate) -> DecisionGateName:
    if m is LeadMandate.BOARD:
        return DecisionGateName.MUST_CONSULT_ALL
    return DecisionGateName.NONE


def mandate_uses_consultation_session(m: LeadMandate) -> bool:
    return m is not LeadMandate.ROUTING
```

- [ ] **Step 4: Export from `lca/contracts/__init__.py` (public domain names only)**

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest tests/test_team_coordination.py -v
```

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/team_coordination.py tests/test_team_coordination.py lca/contracts/__init__.py
git commit -m "feat(contracts): add TeamLead mandate and Coordination types"
```

---

### Task 2: Retarget TeamConfig; remove TeamProcess / supervisor_mode.py

**Files:**
- Modify: `lca/contracts/role_team.py`
- Modify: `lca/contracts/enums.py` (delete `TeamProcess`)
- Delete: `lca/contracts/supervisor_mode.py`
- Modify: `lca/contracts/protocols/orchestration.py`
- Modify: all importers (will break until later tasks — do systematic replace)

- [ ] **Step 1: Change `TeamConfig` to domain fields**

```python
@dataclass
class TeamConfig:
    """Closed team configuration after composition (not a dual user API)."""

    strategy_key: str  # pipeline | fan_out | lead | ...
    lead_mandate: LeadMandate | None = None  # only when strategy_key == "lead"
    shared_memory_layers: list[MemoryLayer] = field(default_factory=list)
    max_rounds: int | None = None
    delegate_max_attempts: int = 3
```

- [ ] **Step 2: Remove `TeamProcess` from `enums.py`**

- [ ] **Step 3: Delete `supervisor_mode.py`; update `team_supervisor_mode` → `team_lead_mandate(context)` in orchestration protocol**

```python
def team_lead_mandate(context: TeamContext) -> LeadMandate | None:
    return context.config.lead_mandate if context.config is not None else None
```

- [ ] **Step 4: Grep and list every importer of TeamProcess/Recipe/SupervisorMode**

```bash
rg -n "TeamProcess|SupervisorMode|Recipe|supervisor_mode|expand_recipe" --type py -g '!**/__pycache__/**'
```

Fix contracts-layer importers in this task; leave L3/L4 for Chunk 2–3 but keep the tree importable where possible.

- [ ] **Step 5: Delete or gut `orchestration_taxonomy.py`** — remove from `contracts/__init__` exports; delete file if nothing remains needed for tests. Delete `tests/test_orchestration_taxonomy.py` or rewrite as “no taxonomy module” guard.

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(contracts): TeamConfig uses strategy_key + LeadMandate; drop TeamProcess"
```

---

## Chunk 2: Strategies + registry

### Task 3: Rename Hierarchical → LeadStrategy; register by strategy keys

**Files:**
- Rename: `orchestration_strategies/hierarchical.py` → `lead.py` (`LeadStrategy`)
- Modify: `handoff.py` class → `PeerRelayStrategy` (file may rename `peer_relay.py`)
- Modify: `sequential.py` → keep file or rename `pipeline.py` (`PipelineStrategy`)
- Modify: `parallel.py` → `FanOutStrategy`
- Modify: `swarm.py` → `PeerSwarmStrategy`
- Modify: `defaults.py` registration keys
- Modify: `orchestration_registry.py` (string keys only)

- [ ] **Step 1: Implement `LeadStrategy` (behavior = old HierarchicalStrategy)**

Use `team_lead_mandate(context)` and `mandate_uses_consultation_session`.

- [ ] **Step 2: Register in defaults**

```python
orch.register("lead", LeadStrategy)
orch.register("pipeline", PipelineStrategy)  # was Sequential
orch.register("fan_out", lambda: FanOutStrategy(synthesizer=ConcatSynthesizer()))
orch.register("debate", DebateStrategy)
orch.register("peer_relay", PeerRelayStrategy)
orch.register("peer_swarm", PeerSwarmStrategy)
orch.register("graph", GraphStrategy)
```

- [ ] **Step 3: Update strategy unit tests that import old names**

- [ ] **Step 4: Run strategy-focused tests**

```bash
uv run pytest tests/test_handoff_strategy.py tests/test_debate_strategy.py tests/test_graph_strategy.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(l3): LeadStrategy and coordination strategy keys"
```

---

## Chunk 3: Composer + Team API

### Task 4: Assembly → Composer (AgentComposer / TeamComposer)

**Files:**
- Create: `lca/layer4_app/composer.py` (move logic from `assembly.py`)
- Delete: `lca/layer4_app/assembly.py` after updates
- Modify: all `from lca.layer4_app.assembly import Assembly`

- [ ] **Step 1: Move code; rename classes**

```python
class AgentComposer:  # was Assembly agent methods
    def compose(self, ...) -> CognitiveAgent: ...
    def compose_as_lead(self, raw, *, transport, mandate: LeadMandate) -> CognitiveAgent: ...
    def compose_member(self, raw, *, shared_store=None) -> CognitiveAgent: ...

class TeamComposer:
    def compose(
        self,
        *,
        members: list[CognitiveAgent],
        lead: tuple[CognitiveAgent, LeadMandate] | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        delegate_max_attempts: int | None = None,
        strategy: TeamProcessStrategy | None = None,  # rename Protocol later to TeamStrategy
    ) -> TeamUnit:
        if (lead is None) == (coordination is None):
            raise ValueError("Team requires exactly one of lead= or coordination=")
        ...
```

Lead path:
- `strategy_key = "lead"`
- `compose_as_lead(..., mandate=)`
- board template if consultation mandate

Coordination path:
- resolve strategy via `strategy_key_for_coordination`
- Graph requires `Graph.execution_graph` already on value object
- PeerSwarm/Debate: pass `max_rounds` into `TeamConfig` and strategy ctor if needed

- [ ] **Step 2: Keep temporary alias only inside composer module if needed for one commit — do NOT export Assembly publicly**

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(l4): AgentComposer/TeamComposer replace Assembly"
```

---

### Task 5: Public API — Team, TeamLead; delete MultiAgentTeam

**Files:**
- Rewrite: `lca/layer4_app/api.py`
- Modify: `lca/__init__.py`

- [ ] **Step 1: Write characterization/API tests first**

```python
# tests/test_team_api.py
import pytest
from lca import Agent, Team, TeamLead, LeadMandate, Pipeline


def test_lead_xor_coordination(mock_llm):
    a = Agent(role="A", goal="g", backstory="b", tools=[], llm=mock_llm)
    with pytest.raises(ValueError, match="exactly one"):
        Team(members=[a])  # neither
    with pytest.raises(ValueError, match="exactly one"):
        Team(members=[a], lead=TeamLead.board(a), coordination=Pipeline())


def test_pipeline_constructs(mock_llm):
    a = Agent(...)
    b = Agent(...)
    team = Team(members=[a, b], coordination=Pipeline())
    assert team is not None
```

- [ ] **Step 2: Implement api.py**

```python
class TeamLead:
    def __init__(self, agent: Agent, mandate: LeadMandate): ...
    @classmethod
    def routing(cls, agent: Agent) -> TeamLead: ...
    @classmethod
    def consult(cls, agent: Agent) -> TeamLead: ...
    @classmethod
    def board(cls, agent: Agent) -> TeamLead: ...

class Team:
    def __init__(
        self,
        members: list[Agent],
        *,
        lead: TeamLead | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: ... = None,
        assembly: ... = None,  # rename param to composer=
        ...
    ):
        if (lead is None) == (coordination is None):
            raise ValueError("Team requires exactly one of lead= or coordination=")
        composer = ...
        if lead is not None:
            self._runner = composer.compose(
                members=[m._agent for m in members],
                lead=(lead._agent, lead.mandate),
            )
        else:
            self._runner = composer.compose(
                members=...,
                coordination=coordination,
            )

    async def run(self, objective: str) -> Result: ...

    @classmethod
    def pipeline(cls, *members: Agent, **kw) -> Team:
        return cls(list(members) if not isinstance(members[0], list) else members[0],
                   coordination=Pipeline(), **kw)
    # similarly fan_out, peer_relay, peer_swarm, debate, graph, with_lead
```

Sugar signature: prefer `Team.pipeline(members=[...])` matching old style for less churn:

```python
@classmethod
def pipeline(cls, members: list[Agent], **kwargs) -> Team:
    return cls(members, coordination=Pipeline(), **kwargs)
```

- [ ] **Step 3: Update `lca/__init__.py`**

```python
from lca.layer4_app.api import Agent, Team, TeamLead, LeadMandate
from lca.contracts.team_coordination import Pipeline, FanOut, PeerRelay, PeerSwarm, Debate, Graph

__all__ = ["Agent", "Team", "TeamLead", "LeadMandate", "Pipeline", "FanOut", ...]
```

- [ ] **Step 4: Run API tests**

```bash
uv run pytest tests/test_team_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): Team + TeamLead domain API; remove MultiAgentTeam"
```

---

## Chunk 4: Full test + YAML + docs migration

### Task 6: scenario_loader + fixtures

**Files:**
- Rewrite: `tests/support/scenario_loader.py`
- Modify: `tests/fixtures/team_scenarios/ecommerce_launch.yaml` (and any other YAML)

- [ ] **Step 1: Loader accepts only**

```yaml
lead:
  agent: project_lead
  mandate: board
members: [...]
# OR
coordination: pipeline
members: [...]
# OR
coordination: graph
execution_graph: ...
```

- [ ] **Step 2: Migrate ecommerce_launch.yaml teams section**

```yaml
teams:
  hierarchical:   # optional rename key to board_review later
    lead:
      agent: project_lead
      mandate: board
    members: [market_analyst, pricing_specialist, copywriter]
  sequential:
    coordination: pipeline
    members: [...]
  parallel:
    coordination: fan_out
    members: [...]
```

- [ ] **Step 3: Commit**

```bash
git commit -m "test: migrate scenario YAML to lead/coordination schema"
```

---

### Task 7: Mass-migrate tests

**Files:** all under `tests/` importing old API (≈20 files from grep).

- [ ] **Step 1: Replace systematically**

| Old | New |
|-----|-----|
| `MultiAgentTeam` | `Team` |
| `process=TeamProcess.SEQUENTIAL` | `coordination=Pipeline()` |
| `process=TeamProcess.PARALLEL` | `coordination=FanOut()` |
| `process=TeamProcess.DEBATE` | `coordination=Debate(max_rounds=...)` |
| `process=TeamProcess.HANDOFF` | `coordination=PeerRelay()` |
| `process=TeamProcess.SWARM` | `coordination=PeerSwarm(...)` |
| `process=TeamProcess.GRAPH` + graph | `coordination=Graph(execution_graph=...)` |
| hierarchical + BOARD | `lead=TeamLead.board(sup)` |
| hierarchical + ROUTING | `lead=TeamLead.routing(sup)` |
| hierarchical + CONSULT | `lead=TeamLead.consult(sup)` |
| `Assembly` | `AgentComposer` / `TeamComposer` |
| `TeamConfig(process=...)` | `TeamConfig(strategy_key=..., lead_mandate=...)` |

- [ ] **Step 2: Delete obsolete tests**

- `tests/test_orchestration_taxonomy.py` (or rewrite as ban-list guard)

- [ ] **Step 3: Add guard test**

```python
# tests/test_domain_language_guards.py
def test_no_forbidden_public_names_in_lca_init():
    import lca

    for bad in ("MultiAgentTeam", "Recipe", "TeamProcess", "SupervisorMode"):
        assert bad not in dir(lca)
```

- [ ] **Step 4: Full pytest**

```bash
uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git commit -m "test: full migration to Team domain language"
```

---

### Task 8: AGENTS.md + ADR-0030

**Files:**
- Modify: `AGENTS.md` (team section only)
- Create: `docs/adr/0030-team-domain-language.md`
- Modify: `docs/adr/0027-...` / `0029-...` status → Superseded (user surface) by 0030
- Update design spec status already APPROVED

- [ ] **Step 1: AGENTS team section (short)**

```markdown
## 团队协作（领域语言）

- `Agent`：单角色；`Team`：members + **恰好一种**协作机制。
- 有主导者：`Team(members=..., lead=TeamLead.board(pm))`
  - `LeadMandate`：`routing` | `consult` | `board`（全员咨询后收口）
- 无主导者：`Team(members=..., coordination=Pipeline()|FanOut()|PeerRelay()|PeerSwarm()|Debate()|Graph(...))`
- 场景 YAML：`lead.mandate` 或 `coordination`，禁止并存。
- 对象图由 `TeamComposer` 封闭组装；成员调用统一 `send_and_wait`；委派仅 `Decision.delegations`。
```

- [ ] **Step 2: Write ADR-0030** summarizing decision + consequences; mark 0027/0029 superseded for public knobs

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: ADR-0030 team domain language; update AGENTS"
```

---

## Chunk 5: Hardening

### Task 9: ActionScope.LEAD (optional default: do it)

**Files:** `enums.py`, action_catalog, assembly/composer action_scope sites, tests

- [ ] Rename `ActionScope.SUPERVISOR` → `ActionScope.LEAD` if grep surface is small
- [ ] Full quality gate

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

- [ ] **Step: Final grep clean**

```bash
rg -n "TeamProcess|SupervisorMode|Recipe|MultiAgentTeam|class Assembly|expand_recipe" --type py -g '!**/__pycache__/**' -g '!docs/**'
```

Expected: zero hits outside historical ADR text under `docs/adr/`.

- [ ] Commit: `chore: ActionScope.LEAD and final domain-language cleanup`

---

## Risk notes

- **Graph + max_rounds**: Graph strategy currently takes `execution_graph` at construct; TeamComposer must instantiate `GraphStrategy(execution_graph=coord.execution_graph)` instead of bare registry default when coordination is Graph.
- **PeerSwarm/Debate max_rounds**: Today often from `TeamConfig.max_rounds`; copy from Coordination dataclass into config in composer.
- **Budget policy registry key** `"supervisor"`: rename to `"lead"` in same PR as ActionScope if touched; update `compose_as_lead`.
- **import-linter**: composer stays in layer4_app; no reverse imports.

---

## Execution handoff

Plan complete and saved to:

`docs/superpowers/plans/2026-08-03-team-domain-language-collapse.md`

**Spec:** `docs/superpowers/specs/2026-08-03-team-domain-language-collapse-design.md` (APPROVED)

**Ready to execute?** Prefer **subagent-driven-development** (one task per subagent, review between tasks) or run waves in-session with checkpoints after each Chunk.

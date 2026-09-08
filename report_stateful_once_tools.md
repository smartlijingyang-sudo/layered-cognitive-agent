# Survey: stateful_once Tools & Effect-Kind Taxonomy

Read-only scan of the LCA codebase to enumerate tools with persistent / stateful side-effects and check whether an `effect_kind` taxonomy exists. Findings cite `path:line`.

## Existing taxonomy

- **`effect_kind` / `EffectKind` / `stateful_once` literals**: **NOT present anywhere in `lca/contracts/`, `lca/infrastructure/`, or `lca/plugins/`** (no string literal `"effect_kind"`, `"EffectKind"`, or `"stateful_once"` exists in the source tree outside `vendor/`). The closest `kind` taxonomy is:
  - `SectionKind = Literal["pure", "stateful"]` at [`lca/contracts/models/cognition/prompt_assembly.py:29`](lca/contracts/models/cognition/prompt_assembly.py:29). This discriminates **prompt sections**, not tools. Reusing the name `stateful` for tools would clash with section vocabulary.
  - `policy_fact_kind: str` on `GateDecidedCommitted` at [`lca/contracts/harness/memory/events.py:314`](lca/contracts/harness/memory/events.py:314) and `PolicyFact.kind` at [`lca/contracts/models/core/policy/gate_policy.py:24`](lca/contracts/models/core/policy/gate_policy.py:24) — gate/verdict-side fact taxonomy (free string, no enum).
  - `kind: Literal["must_consult","may_respond"]` / `kind: Literal["must_delegate","may_respond"]` at `lca/cognition/member_status/{consult_policy.py:40,required_action.py:38}` — team member policy, unrelated.

- **Idempotency flag (closest existing proxy)**: `Tool.is_idempotent: ClassVar[bool]` on `Tool` Protocol at [`lca/contracts/protocols/runtime/infra/infra.py:54`](lca/contracts/protocols/runtime/infra/infra.py:54), and on `ToolApi.is_idempotent: bool = False` at [`lca/contracts/models/core/execution/tool.py:47`](lca/contracts/models/core/execution/tool.py:47). The flag is **only a boolean** — it does not distinguish "read-only" from "stateful-once" from "multi-shot persistent". Tools that mutate host/disk state declare `is_idempotent=False`; tools that mutate context-var state and claim safety declare `is_idempotent=True`.

- **Fact kinds enum**: there is no `FactKind` enum. Session events have type strings (`"skill.activated.v1"`, `"tool.invoked.v1"`, …). The full taxonomy is documented in [`lca/contracts/observability/event/meta_event_taxonomy.py:1`](lca/contracts/observability/event/meta_event_taxonomy.py:1) (see `SKILL_SESSION_EVENTS` at line 107, `TOOL_EXECUTION_SPINE_EPS` at line 128, `TOOL_SESSION_EVENTS` at line 122, `ASSISTANT_SPINE_EPS` at line 143).

- **Tool registry**: [`lca/cognition/body/tools/tool_registry.py:10`](lca/cognition/body/tools/tool_registry.py:10) — `SimpleToolRegistry(NamedRegistry[Tool])`. Tools are registered by `tool.name` only. There is no `effect_kind` attribute on the registry nor on the `Tool` Protocol; the registry mirrors the wire name. Manifest declarations (`ToolManifest.api[*]`) at [`lca/contracts/models/core/execution/tool.py:43`](lca/contracts/models/core/execution/tool.py:43) carry only `is_idempotent: bool`.

- **Session fact persistence**: `Session.append` is the single public write path (`AGENTS.md §0` "迁移态 disclaimer"). Fact payload schemas are typed `SessionEvent` subclasses in [`lca/contracts/harness/memory/events.py`](lca/contracts/harness/memory/events.py). The closest "kind" discriminator is `event.type` (e.g. `"skill.activated.v1"`), not a `kind` field.

## Tools likely to be `stateful_once`

Heuristic: tool persists state outside the immediate call frame, AND its effect should suppress re-execution within a run. Cells marked **"no"** for Session fact persistence emit only the generic `ToolInvokedCommitted` / `ToolStartedCommitted` receipts (which record *call lifecycle*, not *state-mutation result*).

| tool name | plugin / module | declared effect_kind | `is_idempotent` | Session fact persistence? |
|---|---|---|---|---|
| `activate_skill` | `lca/infrastructure/tools/skills/activate/tool.py` (line 1) | none | `True` ([line 65](lca/infrastructure/tools/skills/activate/tool.py:65)) | **partial**: emits `SkillActivated` + `ContextInjected` via `meta_event_emit.emit_skill_activated` ([line 99](lca/infrastructure/tools/skills/activate/tool.py:99), [`meta_event_emit.py:130`](lca/infrastructure/observability/meta_event_emit.py:130)) |
| `import_skill` | `lca/infrastructure/tools/skills/importer/import_tool.py:1` | none | `False` ([line 62](lca/infrastructure/tools/skills/importer/import_tool.py:62)) | **yes**: `emit_skill_loaded` / `emit_skill_install_failed` ([line 100](lca/infrastructure/tools/skills/importer/import_tool.py:100)) |
| `create_assistant_skill` | `lca/infrastructure/tools/assistant/create_skill_tool.py:1` | none | `False` ([line 56](lca/infrastructure/tools/assistant/create_skill_tool.py:56)) | **partial**: only spine `assistant.skill.installed` via [`AssistantSkillOverlay.install`](lca/plugins/assistant/skill/overlay.py:383); no catalog `*.v1` event for the assistant-skill path |
| `create_assistant` | `lca/infrastructure/tools/assistant/create_tool.py:1` | none | `False` ([line 70](lca/infrastructure/tools/assistant/create_tool.py:70)) | **partial**: spine `assistant.created` / `assistant.bootstrap.completed` via catalog; no session-catalog event |
| `search_skill` | `lca/infrastructure/tools/skills/search/tool.py:1` | none | `True` ([line 68](lca/infrastructure/tools/skills/search/tool.py:68)) | **yes** (`emit_skill_searched`); effect is **read-only**, not stateful-once |
| `read_skill_reference` | `lca/infrastructure/tools/skills/read/reference_tool.py:1` | none | `True` ([line 53](lca/infrastructure/tools/skills/read/reference_tool.py:53)) | no — read-only, not stateful-once |
| `run_skill_script` | `lca/infrastructure/tools/skills/exec/tool.py:1` | none | `False` ([line 74](lca/infrastructure/tools/skills/exec/tool.py:74)) | no — sandbox exec, idempotent at transport layer, not catalog-persisted |
| `sandbox_execute` | `lca/infrastructure/tools/sandbox/runtime_tools.py:71` | none | `False` ([line 99](lca/infrastructure/tools/sandbox/runtime_tools.py:99)) | no — covered by `body.sandbox.enter/exit` spine EPs only |
| `sandbox_inspect` | `lca/infrastructure/tools/sandbox/runtime_tools.py:30` | none | `True` ([line 47](lca/infrastructure/tools/sandbox/runtime_tools.py:47)) | no — read-only |
| `write_file` (manifest `writeFile`) | `lca/infrastructure/tools/lca_computer/apis/write/file.py:1` | none | `False` ([line 29](lca/infrastructure/tools/lca_computer/apis/write/file.py:29)) | no — host-fs write, not catalog-persisted as a fact |
| `write_file` (artifact `write-file`) | `lca/infrastructure/tools/write_file/__init__.py:20` | none | not set (defaults `False`) | no — produces a `FileStore` attachment |
| `move_files` | `lca/infrastructure/tools/lca_computer/apis/move/files.py:1` | none | `False` ([line 29](lca/infrastructure/tools/lca_computer/apis/move/files.py:29)) | no |
| `run_command` / `bash` | `lca/infrastructure/tools/lca_computer/apis/run/command.py:1`, `lca/plugins/tools/bash.py:108` | none | `False` ([line 108](lca/plugins/tools/bash.py:108)) | no |
| `cordis_control` | `lca/plugins/tools/cordis_control/tool.py:46` | none | `False` ([line 103](lca/plugins/tools/cordis_control/tool.py:103)) | no |
| `file_write` (cordis creator) | `lca/plugins/tools/file_write.py:79` | none | `True` ([line 112](lca/plugins/tools/file_write.py:112)) | no (declared idempotent — but writes plugin source to disk) |
| `ask_user` (manifest `askUserQuestion`) | `lca/infrastructure/tools/ask_user/__init__.py:1` | none | `True` ([line 65](lca/infrastructure/tools/ask_user/__init__.py:65)) | covered via `approval.persisted.v1` session event |
| `profile_apply` | `lca/plugins/tools/profile_apply.py:56` | none | `True` ([line 122](lca/plugins/tools/profile_apply.py:122)) | no |
| `profile_diff` | `lca/plugins/tools/profile_diff.py:45` | none | `True` ([line 115](lca/plugins/tools/profile_diff.py:115)) | no — read-only |
| `web_search` | `lca/infrastructure/tools/web_search/__init__.py:51` | none | `True` ([line 51](lca/infrastructure/tools/web_search/__init__.py:51)) | no — read-only |
| `team_message` | `lca/cognition/body/actions/team_message_tool.py:77` | none | `True` ([line 77](lca/cognition/body/actions/team_message_tool.py:77)) | covered via `team.message.published.v1` |

Tools whose `is_idempotent=True` but are **not** stateful-once (read-only or process-local): `search_skill`, `read_skill_reference`, `sandbox_inspect`, `profile_diff`, `web_search`, `profile_apply`, `read_skill_reference`.

Tools that **already** have a session-catalog fact emitted on success (`SkillActivated`, `SkillLoaded`, `SkillSearched`, `ContextInjected`, `ToolInvokedCommitted`, `ToolStartedCommitted`, `AssistantSkillActivatedEventPayload`) are the only candidates whose `effect_kind=stateful_once` would be cheaply wired — they already cross the durable fact boundary.

## `activate_skill` specifically

- **Definition site**: [`lca/infrastructure/tools/skills/activate/tool.py:48`](lca/infrastructure/tools/skills/activate/tool.py:48) (`class SkillActivateTool(Tool)`).
- **Wire manifest binding**: [`lca/infrastructure/tools/skills/activate/tool.py:37`](lca/infrastructure/tools/skills/activate/tool.py:37) — `@contract(RenderContract(tool_name="activate_skill", identifier="lobe-skills", api_name="activateSkill"))`.
- **Frontend wire mapping**: [`lca/plugins/transport/webserver/wire/wire.py:58`](lca/plugins/transport/webserver/wire/wire.py:58) — `"activate_skill": (_SKILLS, "activateSkill")`.
- **In-context state mutation**: `register_activated(package.skill_id, package.name)` at [`lca/infrastructure/tools/skills/activate/tool.py:98`](lca/infrastructure/tools/skills/activate/tool.py:98) writes to `ContextVar[ActivatedSkill]` in [`lca/infrastructure/skills/activation/scope.py:32`](lca/infrastructure/skills/activation/scope.py:32). This is **process-local**, not durable.
- **Session-catalog persistence**: **YES**. `emit_skill_activated` ([`activate/tool.py:100`](lca/infrastructure/tools/skills/activate/tool.py:100)) calls [`meta_event_emit.emit_skill_activated`](lca/infrastructure/observability/meta_event_emit.py:130), which appends the typed event `SkillActivated` ([`events.py:109`](lca/contracts/harness/memory/events.py:109)) to the Session log via `FactGateway.append_catalog_bound` ([`meta_event_emit.py:142`](lca/infrastructure/observability/meta_event_emit.py:142)) **plus** the spine EP `skill.package.activated` ([`meta_event_emit.py:147`](lca/infrastructure/observability/meta_event_emit.py:147)). The mirror event type lives at [`lca/contracts/harness/memory/events.py:109`](lca/contracts/harness/memory/events.py:109).
- **Spine projection consumer**: [`lca/harness/skills/projection.py:39`](lca/harness/skills/projection.py:39) folds `event.type == "skill.activated.v1"` into the in-memory `AgentState.activated_skills` list ([`contracts/models/core/state/state.py:120`](lca/contracts/models/core/state/state.py:120)).
- **Current `is_idempotent` declaration**: `True` ([`activate/tool.py:65`](lca/infrastructure/tools/skills/activate/tool.py:65)) — but this is **misleading**: repeated calls re-emit `SkillActivated` and re-add to the contextvar without de-duplication. The reducer relies on the spine projection, not on idempotency.
- **Prompt assembler consumer**: `ActivatedSkillsSection.render` at [`lca/plugins/prompts/sections.py:235`](lca/plugins/prompts/sections.py:235) reads `state.activated_skills` only — it does **not** re-read the Session log; this is the loop PR-7 needs to break by having the assembler cross-check recent `SkillActivated` events from the Session stream.

A separate `skill` (catalog-load) tool exists at [`lca/harness/skills/service.py:170`](lca/harness/skills/service.py:170) — emits both `SkillLoaded` and `SkillActivated` via the legacy L0 events sink; also stateful-once by name.

The closure table at [`lca/contracts/observability/closure/skill_meta_ep_closure.py:3`](lca/contracts/observability/closure/skill_meta_ep_closure.py:3) explicitly enumerates the three stateful-once skill mutations: "Global skill store mutations (``import_skill`` / ``activate_skill`` / …)".

## Files to touch in PR-7

Per the proposal ("receipt should be persisted as `fact.activation` so the prompt assembler can see 'I already activated skill X'"):

- **Closed-set registry to extend** — add `stateful_once` (or similar) members here:
  - [`lca/contracts/observability/event/meta_event_taxonomy.py:107`](lca/contracts/observability/event/meta_event_taxonomy.py:107) (`SKILL_SESSION_EVENTS`) — add an explicit `SkillActivation` event OR mark `skill.activated.v1` as `effect_kind=stateful_once` via a new `MetaEventSlot.effect_kind` field. Same pattern applies to `SKILL_SPINE_EXECUTION_POINTS` ([line 118](lca/contracts/observability/event/meta_event_taxonomy.py:118)).
  - [`lca/contracts/models/core/execution/tool.py:43`](lca/contracts/models/core/execution/tool.py:43) — add `effect_kind: Literal["ephemeral","persistent","stateful_once"]` to `ToolApi` (and `ToolManifest.parameters` mirror).
  - [`lca/contracts/protocols/runtime/infra/infra.py:54`](lca/contracts/protocols/runtime/infra/infra.py:54) — add `effect_kind: ClassVar[str]` to `Tool` Protocol.

- **Emit module to add `fact.activation`** (currently emits `SkillActivated` as the activation receipt):
  - [`lca/infrastructure/observability/meta_event_emit.py:130`](lca/infrastructure/observability/meta_event_emit.py:130) — `emit_skill_activated`. Either add a new `emit_fact_activation(skill_id, ...)` that wraps `SkillActivated` with an `effect_kind` discriminator, or extend `SkillActivated` to carry `effect_kind` so the Session stream itself can be filtered.
  - Wire `register_activated` at [`lca/infrastructure/skills/activation/scope.py:32`](lca/infrastructure/skills/activation/scope.py:32) to also `append_catalog_bound` a `FactActivated` event so the contextvar mutation and the durable fact stay paired (today only the tool call emits; the projection rebuilds `AgentState.activated_skills` from the spine side).

- **Prompt assembler module to read recent_facts(kind="activation")**:
  - [`lca/cognition/brain/sections/types.py:102`](lca/cognition/brain/sections/types.py:102) — `render_activated_skills` currently reads `state.activated_skills` only. Needs to be passed (or read via Session) a `recent_facts(kind="activation")` slice and either:
    - cross-check the in-memory `state.activated_skills` against the Session events to suppress duplicates, OR
    - re-derive the list from the Session stream filtered by `event.type == "skill.activated.v1"` AND `step >= current_step - N`.
  - [`lca/cognition/brain/sections/assembler.py:195`](lca/cognition/brain/sections/assembler.py:195) — `activated_skill_ids = tuple(s.skill_id for s in activated_skills)`: the source of the tuple is `state.activated_skills` ([line 309](lca/cognition/brain/reasoner/reasoner.py:309)). Inject a `recent_activations` filter here so the prompt text says "已激活: X (step N), Y (step M)" and stale activations are pruned.
  - [`lca/contracts/harness/fold/perceive.py`](lca/contracts/harness/fold/perceive.py) — analog of `fold_policy_facts_from_events` is the right seam; add `fold_recent_activations_from_events(events, *, through_step, lookback_steps) -> tuple[ActivatedSkill, ...]`.

## Gaps

1. **No `effect_kind` taxonomy exists.** The codebase has `is_idempotent: bool` (a two-valued approximation), `SectionKind` (prompt sections, different domain), and a `policy_fact_kind: str` (gate/verdict, free string). PR-7 must define a new literal (suggest `Literal["ephemeral","persistent","stateful_once"]` on `ToolApi` / `Tool`) and add it to `MetaEventSlot` in [`meta_event_taxonomy.py`](lca/contracts/observability/event/meta_event_taxonomy.py) — not piggyback on `SectionKind` (clash) or `policy_fact_kind` (different plane).

2. **`is_idempotent=True` on `activate_skill` is misleading.** `SkillActivateTool.is_idempotent = True` ([activate/tool.py:65](lca/infrastructure/tools/skills/activate/tool.py:65)) — the call always re-emits `SkillActivated`, re-writes the contextvar, and re-injects `context_injected`. The "no re-activation loop" property the proposal wants is currently enforced only by the prompt-text convention, not by any fact de-dup. A `stateful_once` flag must come with a runtime rule: second call within the same `step` window is a no-op (or returns the prior receipt).

3. **Activation fact type is named `skill.activated.v1`, not `fact.activation`.** The proposal says "receipt should be persisted as `fact.activation`". Today the receipt type is `SkillActivated` ([events.py:109](lca/contracts/harness/memory/events.py:109)). If `fact.activation` is meant as a new discriminator, either:
   - add a parallel `FactActivated` event class with `kind="activation"` discriminator (but this would be a parallel vocabulary — forbidden by AGENTS §0 "新增平行事件词表"), OR
   - reuse the existing `SkillActivated` and add `effect_kind: Literal["stateful_once"]` to its payload (preferred — fits AGENTS §2.2 "事实/状态/决策/许可/回执/投影" taxonomy: `SkillActivated` is a *receipt* for a stateful-once tool).

4. **State-of-the-art activator already writes a fact.** No new producer code is needed to *create* the durable record; only a new field to *classify* it. PR-7 reduces to: extend `ToolApi.effect_kind` → propagate via `SimpleToolRegistry` / `SkillActivateTool.is_idempotent` mirror → mirror on `SkillActivated` payload → assembler reads `recent_facts(type="skill.activated.v1", within=step_window)` to de-dup.

5. **The harness `skill` tool ([harness/skills/service.py:170](lca/harness/skills/service.py:170)) is a *second* activator** that emits both `SkillLoaded` + `SkillActivated` via `SkillEventSink.append`. Any PR-7 change must cover this code path too, or the loop will still fire when the legacy path is used.

6. **The `stateful` SectionKind reuse is forbidden.** Section vocabulary ([prompt_assembly.py:29](lca/contracts/models/cognition/prompt_assembly.py:29)) already uses `stateful` for prompt sections. Naming the new tool taxonomy `stateful` would collide on `kind` string. Pick `stateful_once` (as the proposal does) or `persistent`.

7. **The `<activated_skills>` prompt text is rendered from `state.activated_skills`, not from the Session log.** [`render_activated_skills` at types.py:102](lca/cognition/brain/sections/types.py:102) reads `state.activated_skills`. To make the prompt assembler "see I already activated skill X", the section must either:
   - receive a `recent_facts` slice from the assembler, or
   - re-derive the list from `SessionEvent` stream (the fold helper in [`perceive.py`](lca/contracts/harness/fold/perceive.py) is the right pattern; see `fold_policy_facts_from_events` for the template).

8. **A `stateful_once` tool whose effect was rolled back by a re-decision has no defined re-activation rule.** PR-7 should add a delete-when comment (AGENTS §0) — e.g. "when `state.activated_skills` is always derived from the Session stream and never from a process-local contextvar". The current `ContextVar` at [`activation/scope.py:25`](lca/infrastructure/skills/activation/scope.py:25) is the process-local bypass that has to be retired for the guarantee to hold.

## Summary callout for PR-7

- New enum: `effect_kind: Literal["ephemeral","persistent","stateful_once"]` on `ToolApi` + `Tool` Protocol.
- New field on `MetaEventSlot` (`meta_event_taxonomy.py:39`) to classify events.
- `activate_skill`, `import_skill`, `create_assistant`, `create_assistant_skill` get `effect_kind="stateful_once"`.
- Existing receipt type `SkillActivated` (`events.py:109`) gains `effect_kind: str = "stateful_once"` discriminator.
- Prompt assembler fold helper added to [`perceive.py`](lca/contracts/harness/fold/perceive.py); `ActivatedSkillsSection` reads `recent_activations` instead of `state.activated_skills` for the prompt text.
- `SkillActivateTool.is_idempotent = True` stays (idempotent from the *receipt* view), but a step-window re-call short-circuit is enforced at the assembler level — not at the tool layer.
# agent_lab — config-driven agent graph framework (ADR-0206 prototype)

The agent loop is layered graphs + one non-executable tool inventory.

## Layout

```
agent_lab/
├── graphs/configs/        ← graph YAMLs (root + phase sub-graphs)
│   ├── agent_loop.yaml
│   ├── perceive.yaml
│   ├── think.yaml
│   ├── act.yaml             ← Decision → Observation (shape→authorize→execute→observe)
│   ├── model_eye.yaml       ← child of perceive
│   ├── reflect.yaml / remember.yaml
│   └── control/             ← control slots (stop_decide/stop_focus on remember)
├── tools/                 ← NON-executable named-tool inventory
│   ├── registry.yaml
│   └── registry.py
├── adapters/              ← bridges to real LCA contracts (one-way)
├── nodes/                 ← ant-worker node library (one file per @node)
│   ├── act/                 (shape, authorize, execute, observe)
│   ├── perceive/ / model_eye/ / think/ / …
│   └── tool/                (legacy helpers; toolbox / registry resolve)
├── runtime/               ← recursive interpreter
├── graph/                 ← spec + compile + validate
├── primitives/            ← Artifact / Port / Edge
└── run.py                 ← entry point
```

## Act phase (first principles)

Act answers one question: **given an enforced Decision, what did the world return?**

```
Decision
  → shape      (call_tool→use_tool; refuse→respond)
  → authorize  (tool allowlist | non-tool allow)
  → execute    (allow → SimpleBody.act)
  → observe    (Observation)
  ──project──► model_eye.see.observation
```

Body handles `use_tool` / `respond` / `stop` / `ask_human` / `delegate` /
`handoff`. `PipelineSafeExecutor` mints CommandEnvelope under `plan_ref_scope`.
Runner binds one Session for session_log + FactGateway. HIL surfaces as
`waiting_input` receipt (no `approval.wait` node). Durable turn facts stay in
`remember`.

## Model-visible tools (what the LLM sees)

```
tools/registry.yaml
  └─ perceive.inventory (expose_schemas)
       └─ model_eye.see.tools → guard → shape → freeze
            └─ ContextManifest { messages, tools, digest, committed }
                 └─ think.expose → reason.complete(tools=…)
```

Inventory schemas are frozen inside `ContextManifest`. Think does not take a
parallel `initial.tools` bypass.

## How the call chain resolves for one tool call

```
agent_loop.yaml
  └─ act.yaml
       └─ execute (factory: act.execute)
            ├─ config.tools → ToolPermissionManifest range
            ├─ tools/registry.yaml → SimpleToolRegistry
            └─ SimpleBody.act(Decision)
                 └─ UseToolOperation → SafeExecutor → tool.execute(args)
```

## Adding a new tool

1. Write a `lca.contracts.protocols.Tool` subclass (see `adapters/tools/read_file.py`).
2. Append a one-line entry to `tools/registry.yaml`.
3. Add the name to `act.yaml` `authorize.config.allow` and `execute.config.tools`.
4. No think/perceive wiring change — `expose_schemas` picks it up for the model.

## Adding a new node

1. Create `nodes/<layer>/<name>/plugin.py` with one `@node(...)` class.
2. Import the new subpackage from `nodes/<layer>/__init__.py`.
3. Reference it from a graph by its `factory:` name.

## Self-describe

```bash
python -m agent_lab.run --describe
python -m agent_lab.run --describe --target node:act.execute
python -m agent_lab.run --describe --target graph:act
```

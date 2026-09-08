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
  → shape      (Intent | no_effect)
  → authorize  (allow | deny | skip)
  → execute    (EffectReceipt via SimpleSafeExecutor; sole world touch)
  → observe    (Observation)
  ──project──► model_eye.see.observation
```

`respond` / `refuse` become `no_effect` and never call tools. Journal writes
belong to `remember`, not act.

## How the call chain resolves for one tool call

```
agent_loop.yaml
  └─ act.yaml
       └─ execute (factory: act.execute)
            ├─ config.tools → tool RANGE
            ├─ registry from tools/registry.yaml → Tool INSTANCES
            └─ SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=range))
                 └─ tool.execute(args)
```

## Adding a new tool

1. Write a `lca.contracts.protocols.Tool` subclass (see `adapters/tools/read_file.py`).
2. Append a one-line entry to `tools/registry.yaml`.
3. Add the name to `act.yaml` `authorize.config.allow` and `execute.config.tools`.

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

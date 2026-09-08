# agent_lab — config-driven agent graph framework (ADR-0206 prototype)

The agent loop is three layers (graphs) + one non-executable tool inventory.

## Layout

```
agent_lab/
├── graphs/configs/        ← the three graph YAMLs (root + two sub-graphs)
│   ├── agent_loop.yaml
│   ├── effect_dispatch.yaml
│   └── mv_assemble.yaml
├── tools/                 ← NON-executable named-tool inventory (this is
│   ├── registry.yaml          "the place that holds tools")
│   └── registry.py           (ToolRegistry class — name → Tool lookup)
├── adapters/              ← bridges to real LCA contracts (one-way)
│   ├── lca_body.py           (LcaBodyProvider — SimpleSafeExecutor + tool range)
│   ├── lca_llm.py            (LcaLlmProvider — wraps any LLMAdapter)
│   ├── lca_mv.py             (LcaMvProvider — DefaultModelContextAssembler)
│   └── tools/
│       └── read_file.py      (agent_lab's own Tool; real fs read)
├── nodes/                 ← the ant-worker node library (one file per @node)
│   ├── base.py               (Node / NodeRegistry / invoke)
│   ├── manifest.py           (NodeManifest etc.)
│   ├── control/              (join, barrier, route_on, discard)
│   ├── llm/                  (call_llm, assemble_messages, commit_manifest)
│   ├── tool/                 (build_intent, grant_check, dispatch_tool, write_receipt, integrate_observation)
│   ├── mv/                   (trust_classify, merge_messages, validate_manifest, assemble_lca_mv)
│   └── passthrough/          (identity, constant, select, redact, dedup, rank)
├── runtime/               ← recursive interpreter
├── graph/                 ← spec + compile + validate
├── primitives/            ← Artifact / Port / Edge
└── run.py                 ← entry point
```

## How the call chain resolves

For a single tool call inside `agent_loop`:

```
agent_loop.yaml                ← dispatch node lists tools: [bash, file_write, read_file]
  └─ effect_dispatch.yaml      ← sub_spec mount; passes through input_map
       └─ dispatch node (factory: dispatch_tool)
            ├─ config.tools → tool RANGE (which names this node may call)
            ├─ registry loaded from tools/registry.yaml → Tool INSTANCES
            └─ LcaBodyProvider(tool_registry, tool_range)
                 └─ SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=range))
                      └─ tool.execute(args)   ← real LCA Tool (BashTool, ReadFileTool, ...)
```

The graph config (YAML) is the only place that says *which tools* a dispatch
may call.  The tool registry (also YAML) is the only place that says *what
tools exist at all*.  No code change is needed to add/remove tools.

## Adding a new tool

1. Write a `lca.contracts.protocols.Tool` subclass (or any class implementing
   the protocol — see `agent_lab/adapters/tools/read_file.py` for the
   standard shape).
2. Append a one-line entry to `tools/registry.yaml`.
3. If a dispatch graph should be allowed to call it, add the name to that
   graph's `dispatch` node `config.tools: [...]` and to the
   `grant_check` node's `config.allow: [...]`.

## Adding a new node

1. Create `nodes/<layer>/<name>/plugin.py` with one `@node(...)` class.
2. Import the new subpackage from `nodes/<layer>/__init__.py`.
3. Reference it from a graph by its `factory:` name.

## Real LCA seams in use

- `lca.infrastructure.llm_adapter.openai_compat:OpenAICompatAdapter`
  — real LLM, reads `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` from env.
- `lca.cognition.body.executor.safe_executor:SimpleSafeExecutor`
  — real tool executor (permission gate, retry, journal).
- `lca.contracts.models.team.role.team:ToolPermissionManifest`
  — the allowlist SimpleSafeExecutor enforces.
- `lca.infrastructure.context.model_visible.assembler.assembler:DefaultModelContextAssembler`
  — real model-visible assembly (used by `assemble_lca_mv`).
- `lca.plugins.tools.bash:BashTool` / `lca.plugins.tools.file_write:FileWriteTool`
  — real LCA tools.
- `agent_lab.adapters.tools.read_file:ReadFileTool` — agent_lab's own Tool.

## Self-describe

```bash
python -m agent_lab.run --describe                    # all nodes + graphs + tools
python -m agent_lab.run --describe --target node:call_llm
python -m agent_lab.run --describe --target graph:effect_dispatch
python -m agent_lab.run --describe --target graph:tools/registry   # not yet; add later
```

# Plan: PR-D remaining — LabCarrier execute without agent_lab.nodes

Living tree is `main`. `agent_lab/nodes/` is gone (`f8448e09`). 89 LabCarrier files exist but `source_module` still names deleted `agent_lab.nodes.*`. Runner still `from agent_lab.nodes import invoke`. Adapters already deleted (`0eb66079`). Do not restore either.

Source of execute bodies: feat worktree
`/home/lichao/layered-cognitive-agent/.worktrees/feat-agent-lab-graph-node-composition/agent_lab/nodes/**`
and adapters at `0eb66079^:agent_lab/adapters/*.py`.

## Goal

Workers execute from `lca/plugins/lab/**`. Graph composition law (N3/N4/N5, sibling `graph.call` hosts, load_closure) lives on the same kernel.

## Global constraints

- Do not recreate `agent_lab/nodes/` or `agent_lab/adapters/`.
- Factory lookup keys must include YAML `factory:` values (`perceive.sense`, `identity`, `expose_schemas`).
- `graph.call` is a builtin host, not a carrier.
- Provider composition stays in `lca/plugins/lab/{act/body_provider,tools/provider,transport/provider,session/provider}`.
- Inline adapter helpers under `lca/plugins/lab/<area>/ops.py` or `lca/plugins/lab/internal/ops_<area>.py`.
- Tests must not import `agent_lab.nodes`.
- Conventional commits on `main`. Do not push. Do not spawn subagents or reviewers.

## Tasks

1. Kernel: Worker registry + `runtime.invoke` + runner/validate/compile/loader composition.
2. Port passthrough workers.
3. Port think / reflect / remember / act workers.
4. Port perceive (+ inline lca_perceive).
5. Port control (+ inline lca_control / lca_control_act).
6. Port model_eye / model_visible / llm.
7. Port session_log / lineage / event / tool.
8. Retarget tests + `run.py` describe; zero remaining `agent_lab.nodes` imports in production code.

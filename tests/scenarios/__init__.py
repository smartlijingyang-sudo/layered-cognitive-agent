"""v3 scenario profiles — config-only variations over the closed primitive set.

Each profile is a YAML declaration of which bundle entries (and overrides)
participate in a given cognitive shape.  Per spec §13, every scenario
is **a composition of existing primitives**, not a new loop stage or
plugin schema.

Profiles in this directory:

1. ``minimal.yaml``           — only bash + str_replace_editor
2. ``standard.yaml``          — full standard implementation
3. ``code.yaml``              — standard + CodeMode executor strategy
4. ``cordis-creator.yaml``    — standard + Composer.mount/unmount
5. ``ralph-loop.yaml``        — workflow automation (GoalStack + LoopBreaker)
6. ``voyager.yaml``           — procedural memory + skill acquisition
7. ``memgpt.yaml``            — 4-layer memory + CompactionPolicy
8. ``metagpt.yaml``           — Team XOR + Graph coordination
9. ``lats.yaml``              — Brain replacement + Critic + GoalStack
10. ``self-improving.yaml``   — Composer.mount + Profile evolution
11. ``devin-style.yaml``      — GoalStack + Ralph + Team + ApprovalToken
12. ``research-debate.yaml``  — Lead + 3 researchers + synthesizer
"""

"""Test suite for ADR-0220 §闸门 3 — three-tier graph topology dispatch.

Enforces:

- §3 — three top-level subdirs (``bundles/primitive``, ``bundles/concept``,
  ``bundles/business``) carry graph bundles; the legacy flat layout under
  ``bundles/`` is migrated out per P5/P8.
- §3.3 / §3.4 — graph ids must use the three-tier prefix set; business
  graphs only reference other graphs via ``ref:`` (no inline impl).
- §0.4 N9 — node ids follow the closed action-domain vocabulary and
  avoid banned words (``process`` / ``handle`` / ``manage`` / ``do_*``).
- §3.2 — primitive graphs are small (≤ 6 nodes).
- §14 — ``audit-bundle-node-naming`` script dry-run (skipped if absent).

The current repo state has ADR-0220 Proposed and the three subdirs do
not exist yet, so the assertions that *require* the new layout
(@pytest.mark.xfail) capture the expected post-migration shape. They
fail today and informatively track the migration progress without
breaking CI.
"""

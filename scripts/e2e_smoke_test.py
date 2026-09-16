#!/usr/bin/env python3
"""RETIRED stub for the v1 6-step in-process smoke.

The v1 plan projection this script asserts (``CompiledRunPlan.phase_graph``
/ ``phase_bindings`` / ``semantic_phase`` / loop edges) was retired by
ADR-0221 P3; the corresponding imports
(``lca.harness.composition.plan_compiler``,
``lca.harness.declarative.controls.validation``) no longer exist, so
Step 2 (``compile_plan``) fails before any of the later checks can run.

The replacement is a composition of commands that already exist and are
maintained alongside their underlying subsystems:

    ./scripts/lca-ops kernel-restart    # boot check + fiber report +
                                        # health probe (auto, on every restart)
    ./scripts/lca-ops plan compile      # v2 CompiledRunPlan projection
    ./scripts/lca-ops e2e timeline      # browser wire smoke
                                    # (POST /lca-api/runs + SSE /live)

Exit code 2 so callers can tell the script was retired, not run.
"""

import sys

RETIRED_MSG = """\
[retired] scripts/e2e_smoke_test.py 已退役(2026-Q3,ADR-0221 P3 后 plan
v2 投影替代 v1,本脚本内的 v1 导入/属性访问全部失效)。

等价验证请改跑:
  ./scripts/lca-ops kernel-restart     # 自动跑 boot_check + fiber_report + health_probe
  ./scripts/lca-ops plan compile       # 看 v2 CompiledRunPlan 投影
  ./scripts/lca-ops e2e timeline       # 浏览器线路的 wire smoke
"""


def main() -> int:
    sys.stderr.write(RETIRED_MSG)
    return 2


if __name__ == "__main__":
    sys.exit(main())

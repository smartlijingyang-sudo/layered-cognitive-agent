#!/usr/bin/env python3
"""check_plan_lift — run the boot-time plan lift offline, without starting a kernel.

``lca-ops plan compile <profile>`` reports ``valid: true`` for a profile that the
boot lift then rejects, because compile does not run the port-reachability pass.
That gap cost two failed restarts and a fatal supervisor: a bundle node declared
an input port that no reachable predecessor produced, and the failure surfaced
only when the kernel tried to boot.

This runs the same two calls ``boot_check`` makes
(``lca/infrastructure/cli/commands/kernel/kernel.py``): resolve the profile with
the deployment env, then ``validate_profile_plans``. Exit 0 when every plan
lifts, exit 1 with the lifter's own message when one does not.

用法::

    uv run python scripts/check_plan_lift.py
    uv run python scripts/check_plan_lift.py profiles/web-standard.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = REPO_ROOT / "profiles" / "web-assistant.yaml"


def main() -> int:
    profile_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PROFILE
    if not profile_path.is_absolute():
        profile_path = REPO_ROOT / profile_path
    if not profile_path.is_file():
        print(f"FAIL: no such profile: {profile_path}")
        return 1

    sys.path.insert(0, str(REPO_ROOT))

    from lca.contracts.protocols.graph.errors import PlanLiftError
    from lca.infrastructure.cli.services.kernel.deployment_env import (
        resolve_profile_with_deployment_env,
    )
    from lca_kernel.boot.plan_validation import validate_profile_plans

    try:
        resolved = resolve_profile_with_deployment_env(profile_path)
    except Exception as exc:
        print(f"FAIL: profile resolve raised {exc.__class__.__name__}: {exc}")
        return 1

    try:
        validate_profile_plans(resolved)
    except PlanLiftError as exc:
        print(f"FAIL: plan lift rejected {profile_path.name}")
        print(f"  plan_id   : {exc.plan_id}")
        print(f"  node_id   : {exc.node_id}")
        print(f"  port_name : {exc.port_name}")
        print(f"  reason    : {exc.reason}")
        return 1
    except Exception as exc:
        print(f"FAIL: plan lift raised {exc.__class__.__name__}: {exc}")
        return 1

    print(f"OK: every plan in {profile_path.name} lifts clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

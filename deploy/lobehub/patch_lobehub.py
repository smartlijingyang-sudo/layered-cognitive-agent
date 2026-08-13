#!/usr/bin/env python3
"""LCA ↔ LobeHub patch system — thin CLI entry point.

All logic lives in engine.py. Patch modules are auto-discovered from patches/.

Usage:
  python3 deploy/lobehub/patch_lobehub.py              # apply all
  python3 deploy/lobehub/patch_lobehub.py verify       # check anchors
  python3 deploy/lobehub/patch_lobehub.py list         # show manifest
  python3 deploy/lobehub/patch_lobehub.py drift        # detect unregistered edits
  python3 deploy/lobehub/patch_lobehub.py manifest     # JSON manifest
  python3 deploy/lobehub/patch_lobehub.py doctor       # full health check
  python3 deploy/lobehub/patch_lobehub.py apply lca_run_driver file_proxy_rewrite  # specific

Rules:
  1. NEVER edit lobehub-ui/ directly — always via patches
  2. Every modification must be registered as a patch module in patches/
  3. Run `drift` after development to catch unregistered changes
  4. Run `doctor` before committing to verify full health
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from deploy.lobehub.engine import main

if __name__ == "__main__":
    main()

"""Pure renderer for the daemon ``start.sh`` script.

``render_start_script`` builds the POSIX sh script that launches the
sandbox-user connect daemon from a :class:`DaemonConfig`. It is pure
(config in, script out) so the deployment contract is unit-testable;
``DaemonService._spawn`` only writes the rendered output and launches it.

RA-007: extracted from ``DaemonService._spawn``; token and paths now come
from ``DaemonConfig`` instead of f-string literals.
"""

from __future__ import annotations

from lca.infrastructure.cli.config.config import DaemonConfig


def render_start_script(config: DaemonConfig, gateway_ws_url: str) -> str:
    """Render the ``start.sh`` content for the connect daemon.

    Byte-stable for default config: same env, same log redirection,
    same ``/opt/lca`` target as the historical inline template.
    """
    venv_bin = f"{config.cli_dir}/venv/bin"
    cli_js = f"{config.cli_dir}/dist/index.js"
    home = f"/home/{config.user}"
    return f"""#!/bin/sh
export PATH="{venv_bin}:/usr/local/bin:/usr/bin:/bin"
export LCA_PYTHON="{venv_bin}/python3"
export PYTHONPATH="{config.cli_dir}/python"
export HOME={home}
cd {config.workspace}
exec node {cli_js} connect \\
  --gateway {gateway_ws_url} \\
  --workspace {config.workspace} \\
  --token-type serviceToken \\
  --token {config.token} \\
  >> "${{HOME}}/.lca/daemon.log" 2>&1
"""

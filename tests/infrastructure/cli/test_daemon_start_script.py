"""RA-007: the daemon start script is rendered by a pure, testable function.

Pins the deployment contract: configured token, log path, PATH entries,
and the full default script shape. The token default stays single-sourced
from the host runtime config.
"""

from __future__ import annotations

from lca.infrastructure.cli.config.config import DaemonConfig
from lca.infrastructure.cli.services.daemon.start_script import render_start_script
from lca.infrastructure.host_runtime.config import (
    KernelServeConfig as HostKernelServeConfig,
)

_WS_URL = "ws://127.0.0.1:8765"


def test_render_uses_configured_token_not_literal() -> None:
    config = DaemonConfig(token="tok-from-config-123")  # noqa: S106
    script = render_start_script(config, _WS_URL)
    assert "--token tok-from-config-123" in script
    assert "lca-local-host" not in script


def test_render_pins_log_path_and_path_entries() -> None:
    script = render_start_script(DaemonConfig(), _WS_URL)
    assert 'export PATH="/opt/lca/venv/bin:/usr/local/bin:/usr/bin:/bin"' in script
    assert 'export LCA_PYTHON="/opt/lca/venv/bin/python3"' in script
    assert 'export PYTHONPATH="/opt/lca/python"' in script
    assert '>> "${HOME}/.lca/daemon.log" 2>&1' in script
    assert "exec node /opt/lca/dist/index.js connect \\" in script
    assert f"--gateway {_WS_URL}" in script
    assert "export HOME=/home/sandbox-user" in script
    assert "cd /home/sandbox-user" in script


def test_render_respects_custom_paths() -> None:
    config = DaemonConfig(cli_dir="/srv/lca", user="ops", workspace="/srv/ws")
    script = render_start_script(config, _WS_URL)
    assert 'export PATH="/srv/lca/venv/bin:' in script
    assert "exec node /srv/lca/dist/index.js connect \\" in script
    assert "export HOME=/home/ops" in script
    assert "cd /srv/ws" in script
    assert "--workspace /srv/ws" in script


def test_default_token_single_sourced_from_host_runtime() -> None:
    assert DaemonConfig().token == "lca-local-host"  # noqa: S105
    assert DaemonConfig().token == HostKernelServeConfig().token
    assert (
        DaemonConfig.model_fields["token"].default
        == HostKernelServeConfig.model_fields["token"].default
    )


def test_render_default_script_shape() -> None:
    """Full characterization of the default deployment script."""
    script = render_start_script(DaemonConfig(), "ws://0.0.0.0:8765")
    assert script == (
        "#!/bin/sh\n"
        'export PATH="/opt/lca/venv/bin:/usr/local/bin:/usr/bin:/bin"\n'
        'export LCA_PYTHON="/opt/lca/venv/bin/python3"\n'
        'export PYTHONPATH="/opt/lca/python"\n'
        "export HOME=/home/sandbox-user\n"
        "cd /home/sandbox-user\n"
        "exec node /opt/lca/dist/index.js connect \\\n"
        "  --gateway ws://0.0.0.0:8765 \\\n"
        "  --workspace /home/sandbox-user \\\n"
        "  --token-type serviceToken \\\n"
        "  --token lca-local-host \\\n"
        '  >> "${HOME}/.lca/daemon.log" 2>&1\n'
    )

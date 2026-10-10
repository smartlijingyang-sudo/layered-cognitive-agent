from lca.infrastructure.cli.service.host_probing import pid_alive, resolve_probe_cmd


def test_resolve_probe_cmd():
    # Should resolve standard binaries like sh or python3 to absolute paths
    cmd = resolve_probe_cmd("sh")
    assert cmd is not None
    assert cmd.startswith("/")

def test_pid_alive_boundary():
    # PID <= 0 must be False
    assert pid_alive(0) is False
    assert pid_alive(-1) is False

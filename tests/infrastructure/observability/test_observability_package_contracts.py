import subprocess
import sys


def test_observability_package_contract_clean():
    res = subprocess.run(
        [sys.executable, "scripts/check_package_contracts.py"],
        capture_output=True,
        text=True,
    )
    observability_errors = [
        line for line in res.stdout.splitlines()
        if "lca.infrastructure.observability" in line
    ]
    assert not observability_errors, f"Found package contract errors: {observability_errors}"

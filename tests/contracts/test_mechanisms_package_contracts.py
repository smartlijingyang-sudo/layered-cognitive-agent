import subprocess
import sys

def test_mechanisms_package_contract_clean():
    res = subprocess.run(
        [sys.executable, "scripts/check_package_contracts.py"],
        capture_output=True,
        text=True,
    )
    # 断言 lca.contracts.mechanisms 不存在任何错误
    mechanisms_errors = [
        line for line in res.stdout.splitlines()
        if "lca.contracts.mechanisms" in line
    ]
    assert not mechanisms_errors, f"Found package contract errors: {mechanisms_errors}"

import subprocess
import sys


def test_patch_engine_lists_collaboration_team_bar():
    res = subprocess.run(
        [sys.executable, "deploy/lobehub/patch_lobehub.py", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "collaboration_team_bar" in res.stdout


def test_collaboration_ui_patch_verify():
    res = subprocess.run(
        [sys.executable, "deploy/lobehub/patch_lobehub.py", "verify"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Patch verify failed:\n{res.stderr}\n{res.stdout}"


def test_check_patch_integrity_script():
    res = subprocess.run(
        [sys.executable, "scripts/check_patch_integrity.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Byte-identical check failed:\n{res.stdout}\n{res.stderr}"

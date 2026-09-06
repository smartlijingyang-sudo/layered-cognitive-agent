"""Privileged commands — one place, one password file.

Reads ``.lobehub-stack/sudo.pass`` (same file the host runtime already uses).
Never prompt. Never touch sandbox-user paths without going through here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class Sudo:
    """Run commands as root, optionally as another user."""

    def __init__(self, pass_file: Path) -> None:
        self._pass_file = pass_file

    def run(
        self,
        cmd: list[str],
        *,
        user: str | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        prefix = ["sudo", "-S", "-p", ""]
        if user:
            prefix.extend(["-u", user])
        return subprocess.run(  # noqa: S603
            [*prefix, *cmd],
            input=self._password(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def mkdir(self, path: Path, *, owner: str | None = None) -> bool:
        ok = self.run(["mkdir", "-p", str(path)]).returncode == 0
        if ok and owner:
            self.run(["chown", f"{owner}:{owner}", str(path)])
        return ok

    def write_text(self, path: Path, text: str, *, owner: str | None = None) -> bool:
        import tempfile

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        try:
            copied = self.run(["cp", str(tmp_path), str(path)]).returncode == 0
            if copied and owner:
                self.run(["chown", f"{owner}:{owner}", str(path)])
            return copied
        finally:
            tmp_path.unlink(missing_ok=True)

    def read_text(self, path: Path) -> str | None:
        result = self.run(["cat", str(path)], timeout=5)
        if result.returncode != 0:
            return None
        return result.stdout

    def exists(self, path: Path) -> bool:
        return self.run(["test", "-e", str(path)], timeout=5).returncode == 0

    def rm(self, path: Path) -> None:
        self.run(["rm", "-f", str(path)], timeout=5)

    def _password(self) -> str:
        if self._pass_file.is_file():
            return self._pass_file.read_text().strip() + "\n"
        return ""

"""Process helpers for the kernel supervisor package.

``_pid_alive`` is a zero-side-effect liveness check; ``_PhantomProc`` is
a stand-in for :class:`subprocess.Popen` when the supervisor is hydrated
from a state file written by a previous process.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class _PhantomProc:
    """Stand-in for :class:`subprocess.Popen` when the supervisor was
    hydrated from a state file written by a previous process.

    Forwards signals; the only real subprocess work happens in a future
    ``start()`` call. The methods ``wait`` / ``poll`` are needed because
    :meth:`KernelSupervisor.stop` talks to the proc the same way it
    would to a real ``Popen`` — keeps the supervisor's surface
    uniform across the in-process and hydrated cases.
    """

    __slots__ = ("_pid",)

    def __init__(self, pid: int) -> None:
        self._pid = pid

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        try:
            os.kill(self._pid, 0)
        except OSError:
            return -1
        return None

    def send_signal(self, sig: int) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(self._pid, sig)

    def wait(self, timeout: float | None = None) -> int:
        deadline = time.monotonic() + (timeout or 10.0)
        while time.monotonic() < deadline:
            try:
                waited_pid, status = os.waitpid(self._pid, os.WNOHANG)
                if waited_pid == self._pid:
                    return os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                return -1
            time.sleep(0.1)
        raise subprocess.TimeoutExpired(str(self._pid), timeout or 10.0)

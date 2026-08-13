"""One local PTY. Owns fd/pid; does not know WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import signal
import struct
import termios
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

_log = structlog.get_logger(__name__)

Emit = Callable[[dict[str, Any]], Awaitable[None]]


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    packed = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)


class LocalPty:
    def __init__(
        self,
        session_id: str,
        emit: Emit,
        argv: list[str],
        *,
        cols: int = 80,
        rows: int = 24,
    ) -> None:
        self.session_id = session_id
        self._emit = emit
        self._argv = argv
        self._cols = cols
        self._rows = rows
        self._fd: int | None = None
        self._pid: int | None = None

    async def start(self) -> None:
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.setdefault("TERM", "xterm-256color")
            os.execvp(self._argv[0], self._argv)  # noqa: S606
        self._pid = pid
        self._fd = fd
        _set_winsize(fd, self._cols, self._rows)
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        loop = asyncio.get_running_loop()
        loop.add_reader(fd, self._on_read)

    def write(self, data: str) -> None:
        if self._fd is None or not data:
            return
        os.write(self._fd, data.encode("utf-8", errors="replace"))

    def resize(self, cols: int, rows: int) -> None:
        if self._fd is None:
            return
        self._cols = cols
        self._rows = rows
        _set_winsize(self._fd, cols, rows)

    def close(self) -> None:
        fd = self._fd
        pid = self._pid
        self._fd = None
        self._pid = None
        loop = asyncio.get_running_loop()
        if fd is not None:
            with contextlib.suppress(Exception):
                loop.remove_reader(fd)
            with contextlib.suppress(OSError):
                os.close(fd)
        if pid is not None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGTERM)

    def _on_read(self) -> None:
        fd = self._fd
        if fd is None:
            return
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            chunk = b""
        if not chunk:
            asyncio.get_running_loop().create_task(self._eof())
            return
        text = chunk.decode("utf-8", errors="replace")
        asyncio.get_running_loop().create_task(
            self._emit({"type": "pty_output", "session_id": self.session_id, "data": text})
        )

    async def _eof(self) -> None:
        exit_code = 0
        if self._pid is not None:
            with contextlib.suppress(ChildProcessError):
                _pid, status = os.waitpid(self._pid, os.WNOHANG)  # noqa: ASYNC222
                if os.WIFEXITED(status):
                    exit_code = os.WEXITSTATUS(status)
        self.close()
        await self._emit(
            {"type": "pty_exit", "session_id": self.session_id, "exit_code": exit_code}
        )
        _log.info("pty_exit", session_id=self.session_id, exit_code=exit_code)

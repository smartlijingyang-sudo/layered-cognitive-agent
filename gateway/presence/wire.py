"""Presence channel frame types. Host sidecar speaks this; Console rides it."""

from __future__ import annotations

HELLO = "hello"
WELCOME = "welcome"
PING = "ping"
PONG = "pong"
PTY_OPEN = "pty_open"
PTY_INPUT = "pty_input"
PTY_RESIZE = "pty_resize"
PTY_CLOSE = "pty_close"
PTY_OUTPUT = "pty_output"
PTY_EXIT = "pty_exit"
EXEC_CALL = "exec_call"
EXEC_RESULT = "exec_result"

"""Typed values for stack inspection and reports. No I/O."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Status(Enum):
    OK = "ok"
    MISSING = "missing"
    WARN = "warn"
    ERROR = "error"


class DiscoveredRoute(BaseModel):
    path: str
    methods: tuple[str, ...]
    kind: Literal["http", "websocket"]


class BoundSurface(BaseModel):
    id: str
    title: str
    purpose: str
    routes: tuple[DiscoveredRoute, ...] = ()
    classified: bool = True
    probe_status: Status | None = None
    probe_detail: str = ""


class ProcessSnapshot(BaseModel):
    pid: int | None = None
    alive: bool = False
    started_epoch: float | None = None
    port: int = 8765
    bind: str = "0.0.0.0"  # noqa: S104
    listening: bool = False
    public_url: str = ""
    log_file: str = ""
    health: dict[str, Any] | None = None
    health_error: str | None = None


class RestartDelta(BaseModel):
    reason: str
    previous_pid: int | None = None
    current_pid: int | None = None
    newer_files: tuple[str, ...] = ()


class Check(BaseModel):
    name: str
    status: Status
    detail: str = ""


class Section(BaseModel):
    id: str
    title: str
    checks: tuple[Check, ...] = ()


class StackReport(BaseModel):
    command: str
    verdict: Literal["ready", "degraded", "failed"]
    process: ProcessSnapshot
    surfaces: list[BoundSurface] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    delta: RestartDelta | None = None

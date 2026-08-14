"""Stack YAML — reading this file is reading the architecture."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_YAML_PATH = Path(__file__).resolve().parent.parent / "stack.yaml"


class ProbeConfig(BaseModel):
    method: str = "GET"
    path: str
    expect: int = 200


class SurfaceMeta(BaseModel):
    """Prefix/regex metadata for a group of live routes.

    Routes come from ``create_app()``. This only names, groups, and probes them.
    A new route with no match still appears under ``unclassified``.
    """

    id: str
    match: str
    title: str
    purpose: str
    probe: ProbeConfig | None = None


class GatewayProcessConfig(BaseModel):
    port: int = 8765
    bind: str = "0.0.0.0"  # noqa: S104
    health_path: str = "/health"
    entry: list[str] = Field(
        default_factory=lambda: ["uv", "run", "python", "scripts/serve_observability.py"]
    )
    pid_file: str = ".lobehub-stack/gateway.pid"
    log_file: str = ".lobehub-stack/gateway.log"
    watch: list[str] = Field(
        default_factory=lambda: ["gateway", "lca", "scripts/serve_observability.py"]
    )
    watch_glob: str = "*.py"


class LobehubConfig(BaseModel):
    release: str = "v2.2.13"
    dir: str = "lobehub-ui"
    env_template: str = "deploy/lobehub/.env.lca"
    dev_port: int = 3010
    spa_port: int = 9876
    spa_mobile_port: int = 3012
    spa_auth_port: int = 3013
    pid_file: str = ".lobehub-stack/lobehub-dev.pid"
    log_file: str = ".lobehub-stack/lobehub-dev.log"


class HostStepConfig(BaseModel):
    user: str = "sandbox-user"
    config_file: str = "lca-host.yaml"


class CommandSpec(BaseModel):
    description: str
    steps: list[str]


DEFAULT_YAML = """\
# deploy/lobehub/stack.yaml — LobeHub + Gateway stack (SSOT)
#
# Routes are discovered from gateway.app.create_app().
# surfaces[] only names, groups, and probes them.
# A new route with no match prints under [unclassified] — do not hardcode paths.
# A new patch module under deploy/lobehub/patches/ is auto-listed.
# A new command or step is added here; implementation is a registered kind.

name: lobehub-stack
run_dir: .lobehub-stack

gateway:
  port: 8765
  bind: "0.0.0.0"
  health_path: /health
  entry: [uv, run, python, scripts/serve_observability.py]
  pid_file: .lobehub-stack/gateway.pid
  log_file: .lobehub-stack/gateway.log
  watch:
    - gateway
    - lca
    - scripts/serve_observability.py
  watch_glob: "*.py"

lobehub:
  release: v2.2.13
  dir: lobehub-ui
  env_template: deploy/lobehub/.env.lca
  dev_port: 3010
  spa_port: 9876
  spa_mobile_port: 3012
  spa_auth_port: 3013
  pid_file: .lobehub-stack/lobehub-dev.pid
  log_file: .lobehub-stack/lobehub-dev.log

host:
  user: sandbox-user
  config_file: lca-host.yaml

surfaces:
  - id: health
    match: "^/health$"
    title: Health
    purpose: Liveness + LLM + in-flight runs + device counts
    probe: {method: GET, path: /health, expect: 200}
  - id: context
    match: "^/context$"
    title: Context
    purpose: Latest plane bindings + online machine candidates
    probe: {method: GET, path: /context, expect: 200}
  - id: runs
    match: "^/runs"
    title: Run Live
    purpose: Agent/Team lifecycle, Journal SSE, doctor, cancel, HIL answer
  - id: files
    match: "^/files"
    title: Files
    purpose: Attachment download + metadata (browser-facing public URL)
  - id: openai
    match: "^/v1/"
    title: OpenAI housekeeper
    purpose: Title/topic/embeddings/responses — never starts a Run
    probe: {method: GET, path: /v1/models, expect: 200}
  - id: devices
    match: "^/api/device"
    title: Device gateway
    purpose: LobeHub GatewayClient — status, RPC, tools, WS connect

commands:
  status:
    description: Inspect the stack without changing it
    steps: [gateway.inspect, patches.inspect, host.inspect, lobehub.inspect, infra.inspect]
  gateway:
    description: Start gateway if needed (reload when code is newer); provision host
    steps: [gateway.start, gateway.inspect, host.provision, host.inspect]
  restart-gateway:
    description: Force-reload gateway Python and show capability status
    steps:
      - gateway.snapshot
      - gateway.restart
      - gateway.inspect
      - patches.inspect
      - host.provision
      - host.inspect
  dev:
    description: Sync UI, patch, start gateway + infra + LobeHub dev
    steps: [gateway.start, host.provision, host.inspect, infra.start, lobehub.dev]
  restart:
    description: Stop everything, then start gateway + infra + LobeHub dev
    steps: [stack.stop, gateway.restart, host.provision, host.inspect, infra.start, lobehub.dev]
  stop:
    description: Stop LobeHub dev, Vite SPA, and gateway
    steps: [stack.stop]
  sync:
    description: Pull official LobeHub release and apply patches
    steps: [lobehub.sync]
"""


def _default_surfaces() -> list[SurfaceMeta]:
    data = yaml.safe_load(DEFAULT_YAML) or {}
    return [SurfaceMeta.model_validate(item) for item in data.get("surfaces") or []]


def _default_commands() -> dict[str, CommandSpec]:
    data = yaml.safe_load(DEFAULT_YAML) or {}
    raw = data.get("commands") or {}
    return {key: CommandSpec.model_validate(value) for key, value in raw.items()}


class StackConfig(BaseModel):
    """Top-level stack config. One object, one YAML, one source of truth."""

    name: str = "lobehub-stack"
    run_dir: str = ".lobehub-stack"
    gateway: GatewayProcessConfig = Field(default_factory=GatewayProcessConfig)
    lobehub: LobehubConfig = Field(default_factory=LobehubConfig)
    host: HostStepConfig = Field(default_factory=HostStepConfig)
    surfaces: list[SurfaceMeta] = Field(default_factory=_default_surfaces)
    commands: dict[str, CommandSpec] = Field(default_factory=_default_commands)

    @classmethod
    def from_yaml(cls, path: str | Path) -> StackConfig:
        text = Path(path).read_text(encoding="utf-8")
        return cls.model_validate(yaml.safe_load(text) or {})

    @classmethod
    def from_yaml_or_default(cls, path: str | Path | None = None) -> StackConfig:
        target = Path(path) if path is not None else DEFAULT_YAML_PATH
        if target.is_file():
            return cls.from_yaml(target)
        return cls.model_validate(yaml.safe_load(DEFAULT_YAML) or {})

    def apply_environ(self) -> StackConfig:
        """Overlay well-known env vars. YAML stays the default."""
        gateway = self.gateway.model_copy()
        lobehub = self.lobehub.model_copy()
        host = self.host.model_copy()
        if port := os.environ.get("GATEWAY_PORT"):
            gateway.port = int(port)
        if bind := os.environ.get("GATEWAY_BIND"):
            gateway.bind = bind
        if release := os.environ.get("LOBEHUB_RELEASE"):
            lobehub.release = release
        if dev_port := os.environ.get("LOBE_DEV_PORT"):
            lobehub.dev_port = int(dev_port)
        if spa := os.environ.get("SPA_PORT"):
            lobehub.spa_port = int(spa)
        if user := os.environ.get("LCA_HOST_USER"):
            host.user = user
        return self.model_copy(update={"gateway": gateway, "lobehub": lobehub, "host": host})

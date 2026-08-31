"""Pipeline steps — atomic operations that compose into commands.

Each step is a function that receives PipelineContext and performs one
action. Steps are registered via @register_step decorator.

Commands are sequences of steps defined in the CLI.
"""

from __future__ import annotations

from lca.infrastructure.cli.pipeline import PipelineContext, register_step
from lca.infrastructure.cli.service import CliShippingService

# ── Infrastructure Steps ──────────────────────────────────────────────


@register_step("infra.ensure")
def infra_ensure(ctx: PipelineContext) -> None:
    """Ensure infrastructure is ready."""
    svc = ctx.registry.get("infra")
    state = svc.state()
    if not state.is_running:
        ctx.console.info("Starting infrastructure...")
        svc.start()


@register_step("infra.start")
def infra_start(ctx: PipelineContext) -> None:
    """Start infrastructure."""
    svc = ctx.registry.get("infra")
    state = svc.start()
    ctx.console.service_state("infra", state)
    if not state.is_running:
        ctx.fail("Infrastructure failed to start")


@register_step("infra.stop")
def infra_stop(ctx: PipelineContext) -> None:
    """Stop infrastructure."""
    svc = ctx.registry.get("infra")
    state = svc.stop()
    ctx.console.service_state("infra", state)


# ── Gateway Steps ─────────────────────────────────────────────────────
# ADR-0119 决定 4:Gateway 进程不归 lca-ops 管 (lca_kernel serve 自管)。
# 旧的 gateway.ensure/start/restart/stop step 已删除,对应 service 也已
# 从 registry 移除。保留本节标题便于 git history 比对。


# ── LobeHub Steps ─────────────────────────────────────────────────────


@register_step("lobehub.ensure")
def lobehub_ensure(ctx: PipelineContext) -> None:
    """Ensure LobeHub is ready (sync, patch, env, deps)."""
    svc = ctx.registry.get("lobehub")
    ctx.console.info("Ensuring LobeHub is ready...")
    worked = svc.ensure_ready()
    if worked:
        ctx.console.success("LobeHub setup complete")


@register_step("lobehub.start")
def lobehub_start(ctx: PipelineContext) -> None:
    """Start LobeHub dev server."""
    svc = ctx.registry.get("lobehub")
    state = svc.start()
    ctx.console.service_state("lobehub", state)
    if not state.is_running:
        ctx.fail("LobeHub failed to start")


@register_step("lobehub.restart")
def lobehub_restart(ctx: PipelineContext) -> None:
    """Restart LobeHub dev server."""
    svc = ctx.registry.get("lobehub")
    ctx.console.info("Restarting LobeHub...")
    state = svc.restart()
    ctx.console.service_state("lobehub", state)
    if not state.is_running:
        ctx.fail("LobeHub failed to restart")


@register_step("lobehub.stop")
def lobehub_stop(ctx: PipelineContext) -> None:
    """Stop LobeHub dev server."""
    svc = ctx.registry.get("lobehub")
    state = svc.stop()
    ctx.console.service_state("lobehub", state)


# ── Daemon Steps ──────────────────────────────────────────────────────


@register_step("daemon.ensure")
def daemon_ensure(ctx: PipelineContext) -> None:
    """Ensure daemon CLI is deployed and up-to-date with source."""
    svc = ctx.registry.get("daemon")
    # only DaemonService ships a CLI; narrow for the introspection calls
    daemon = svc if isinstance(svc, CliShippingService) else None
    if daemon is not None and daemon._cli_deployed() and not daemon._cli_source_changed():
        ctx.console.success("daemon CLI up-to-date (source fingerprint match)")
        return
    ctx.console.info("daemon source changed — rebuilding & redeploying CLI...")
    worked = svc.ensure_ready()
    if worked:
        ctx.console.success("daemon CLI redeployed")
    else:
        ctx.fail("daemon CLI deploy failed")


@register_step("daemon.restart")
def daemon_restart(ctx: PipelineContext) -> None:
    """Stop then start daemon (auto-redeploys CLI if source changed)."""
    svc = ctx.registry.get("daemon")
    ctx.console.info("stopping daemon...")
    stop_state = svc.stop()
    ctx.console.service_state("daemon", stop_state)
    ctx.console.info("starting daemon (ensure CLI up-to-date)...")
    start_state = svc.start()
    ctx.console.service_state("daemon", start_state)
    if not start_state.is_running:
        ctx.fail("Daemon failed to restart")


@register_step("host.provision")
def host_provision(ctx: PipelineContext) -> None:
    """Full host: packages, venv, user, workspace, then daemon CLI."""
    from lca.infrastructure.host_runtime.config import HostRuntimeConfig
    from lca.infrastructure.host_runtime.environment import HostEnvironment

    user = ctx.config.daemon.user
    cfg_path = ctx.config.root / ctx.config.daemon.host_config
    ctx.console.info(f"provision host user={user} config={cfg_path}")
    cfg = HostRuntimeConfig.from_yaml_or_default(cfg_path)
    ok = HostEnvironment(cfg).provision(user)
    if not ok:
        ctx.fail("host provision reported failure")
        return
    ctx.registry.get("daemon").ensure_ready()
    ctx.console.success(f"host ready: {user}")


@register_step("daemon.start")
def daemon_start(ctx: PipelineContext) -> None:
    """Start daemon."""
    svc = ctx.registry.get("daemon")
    state = svc.start()
    ctx.console.service_state("daemon", state)
    if not state.is_running:
        ctx.fail("Daemon failed to start")


@register_step("daemon.stop")
def daemon_stop(ctx: PipelineContext) -> None:
    """Stop daemon."""
    svc = ctx.registry.get("daemon")
    state = svc.stop()
    ctx.console.service_state("daemon", state)


# ── Composite Steps ───────────────────────────────────────────────────

# ADR-0119 决定 4:lca-ops 不再管 LCA 进程。gateway (LCA 进程) 入口是
# ``python -m lca_kernel serve`` 直管,K6 SIGTERM/SIGINT/fail-loud 守护。
# lca-ops status / stop 仍管理 lobehub / infra / daemon / onlyboxes 外部服务。
STATUS_SERVICES = ("infra", "lobehub", "daemon", "onlyboxes")
STOP_SERVICES = ("daemon", "lobehub", "infra")


@register_step("stack.status")
def stack_status(ctx: PipelineContext) -> None:
    """Show status, then tell the operator what to run next."""
    states = []
    for name in STATUS_SERVICES:
        svc = ctx.registry.get(name)
        state = svc.state()
        states.append((name, state))
        ctx.console.service_state(name, state)

    actions: list[str] = []
    for _name, state in states:
        if state.next_action and state.next_action not in actions:
            actions.append(state.next_action)

    if not actions:
        ctx.console.success(f"全部正常。打开 {ctx.config.lobehub.dev_url}")
        return

    if len(actions) >= 2:
        ctx.console.next_steps(
            [
                "./scripts/lca-ops heal   # 一次修好下面全部异常",
                *actions,
            ]
        )
        return
    ctx.console.next_steps(actions)


@register_step("stack.heal")
def stack_heal(ctx: PipelineContext) -> None:
    """Heal every service. Do the work here — do not bounce the operator."""
    ctx.console.info("Healing services...")
    leftover: list[str] = []
    for name in STATUS_SERVICES:
        svc = ctx.registry.get(name)
        try:
            state = svc.heal()
        except Exception as exc:
            ctx.console.error(f"{name} heal crashed: {exc}")
            leftover.append(f"{name}: crashed — see error above")
            ctx.failed = True
            continue
        ctx.console.service_state(name, state)
        if not state.is_running:
            leftover.append(f"{name}: {state.why or state.detail}")
            ctx.failed = True
    if leftover:
        ctx.console.warning("heal could not finish:")
        for item in leftover:
            ctx.console.warning(f"  {item}")


@register_step("stack.stop")
def stack_stop(ctx: PipelineContext) -> None:
    """Stop all services in reverse order."""
    for name in STOP_SERVICES:
        svc = ctx.registry.get(name)
        state = svc.stop()
        ctx.console.service_state(name, state)

"""lca-ops status must notice Onlyboxes terminal runtime is not configured."""

from __future__ import annotations

from dataclasses import dataclass

from lca.infrastructure.cli.config import OnlyboxesConfig
from lca.infrastructure.cli.service import ServiceStatus
from lca.infrastructure.cli.services.onlyboxes import OnlyboxesService

CONFIGURE = "./deploy/onlyboxes/configure-terminal-runtime.sh"
BUILD = "./deploy/onlyboxes/build-terminal-image.sh"
IMAGE = "onlyboxes-terminal-local:lca"


@dataclass
class _FakeProbe:
    image_present: bool = True
    dropin_text: str | None = None
    legacy_dropin_exists: bool = False
    worker_env: str = ""
    stale_default: int = 0
    worker_active: bool = True
    unit_exists: bool = True
    configure_calls: int = 0

    def observe(self):
        from lca.infrastructure.cli.services.onlyboxes import OnlyboxesObservation

        return OnlyboxesObservation(
            image_present=self.image_present,
            dropin_text=self.dropin_text,
            legacy_dropin_exists=self.legacy_dropin_exists,
            worker_env=self.worker_env,
            stale_default=self.stale_default,
            worker_active=self.worker_active,
            unit_exists=self.unit_exists,
        )

    def configure(self) -> bool:
        self.configure_calls += 1
        return True


def _svc(probe: _FakeProbe) -> OnlyboxesService:
    return OnlyboxesService(OnlyboxesConfig(), probe=probe)


def _good_dropin() -> str:
    return f"WORKER_TERMINAL_EXEC_DOCKER_IMAGE={IMAGE}\n"


def test_status_asks_to_configure_when_dropin_missing() -> None:
    state = _svc(_FakeProbe(dropin_text=None, worker_env="")).state()
    assert state.status != ServiceStatus.RUNNING
    assert state.next_action == CONFIGURE
    assert "drop-in" in state.why.lower() or "runtime" in state.why.lower()


def test_status_asks_to_configure_when_worker_still_on_upstream() -> None:
    probe = _FakeProbe(
        dropin_text=_good_dropin(),
        worker_env="WORKER_TERMINAL_EXEC_DOCKER_IMAGE=coolfan1024/onlyboxes-runtime:default",
    )
    state = _svc(probe).state()
    assert state.status != ServiceStatus.RUNNING
    assert state.next_action == CONFIGURE


def test_status_asks_to_configure_when_legacy_dropin_path_exists() -> None:
    probe = _FakeProbe(
        dropin_text=_good_dropin(),
        worker_env=f"WORKER_TERMINAL_EXEC_DOCKER_IMAGE={IMAGE}",
        legacy_dropin_exists=True,
    )
    state = _svc(probe).state()
    assert state.next_action == CONFIGURE


def test_status_asks_to_configure_when_stale_default_sessions_remain() -> None:
    probe = _FakeProbe(
        dropin_text=_good_dropin(),
        worker_env=f"WORKER_TERMINAL_EXEC_DOCKER_IMAGE={IMAGE}",
        stale_default=2,
    )
    state = _svc(probe).state()
    assert state.next_action == CONFIGURE


def test_status_asks_to_build_when_lca_image_missing() -> None:
    state = _svc(_FakeProbe(image_present=False, dropin_text=None)).state()
    assert BUILD in state.next_action
    assert CONFIGURE in state.next_action


def test_status_ok_when_runtime_dropin_and_worker_match() -> None:
    probe = _FakeProbe(
        dropin_text=_good_dropin(),
        worker_env=f"WORKER_TERMINAL_EXEC_DOCKER_IMAGE={IMAGE}",
    )
    state = _svc(probe).state()
    assert state.status == ServiceStatus.RUNNING
    assert state.next_action == ""


def test_heal_runs_configure_when_runtime_is_wrong() -> None:
    probe = _FakeProbe(dropin_text=None, worker_env="")
    _svc(probe).heal()
    assert probe.configure_calls == 1


def test_stack_status_includes_onlyboxes() -> None:
    from lca.infrastructure.cli.steps import STATUS_SERVICES

    assert "onlyboxes" in STATUS_SERVICES
    assert (
        "onlyboxes"
        not in __import__("lca.infrastructure.cli.steps", fromlist=["STOP_SERVICES"]).STOP_SERVICES
    )


def test_stack_status_includes_kernel_serve() -> None:
    """Regression: ``lca-ops status`` 必须报 kernel_serve,不能漏 LCA 进程。

    历史背景:``STATUS_SERVICES`` 之前只有 ``infra/lobehub/daemon/onlyboxes``,
    kernel 死了 status 看不到 → 浏览器报 500 时 operator 不知道 kernel 没在跑。
    加 kernel_serve 后 operator 一眼能看到 LCA 进程状态 + next_action。
    """
    from lca.infrastructure.cli.steps import STATUS_SERVICES

    assert "kernel_serve" in STATUS_SERVICES, (
        f"kernel_serve must be in STATUS_SERVICES so lca-ops status reports "
        f"LCA process health; got {STATUS_SERVICES!r}"
    )
    # kernel_serve 在最前 — LCA 是核心依赖,operator 应先看到它。
    assert STATUS_SERVICES.index("kernel_serve") == 0, (
        f"kernel_serve should be first in STATUS_SERVICES; got {STATUS_SERVICES!r}"
    )

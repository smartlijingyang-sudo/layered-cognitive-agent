"""ADR-0184 §2 D7 投递可达性回归锁（PR-B / G7 部分翻正）。

锁守的不变量分两段：

- **显式 step 边界可达（无 xfail，G7 / ADR-0184 D6 + D7 断言 1–3）**：
  cursor 发射的 ``writable.step.*`` 显式边界落账本，``journal.json``
  有 step、doctor 无 broken hop、账本含认知族开窗信号 +
  ``llm.request.header`` + ``writable.step.start``，且首步
  ``extra.window_signal == "explicit"``。
- **全 category 投递计数（仍 ``xfail(strict=True)``，D7 断言 4）**：
  总线 ``delivery_snapshot()`` 每 category ``dropped == 0``。
  剩余依赖 = ADR-0184 PR-C（boot 切 ``apply_pipeline`` + I1 装配校验 +
  共享写实例）：当前生产 boot 走 ``register_pipeline_once``（仅装
  hooks，不挂 sink），总线侧持久类 category（如
  ``spine.runtime.reducer.apply``）零挂载 sink → ``persisted=False`` →
  ``dropped > 0``。翻正是 PR-C 的验收动作之一：测试体失败 = 合法
  xfail，意外通过 = XPASS failure。

装配形态复用 ``tests/test_gateway_auto_run.py`` 的真 profile + 脚本化
LLM 路径：``run_kernel_lifespan`` 启动 ``profiles/web-standard.yaml``，
``llm_resolver`` 替换为 ``ScriptedLLMAdapter``（无真 LLM），solo run 走
生产 ``execute_run`` 链路。run 产物（``traces/runs/<run_id>/``）全部落
临时 cwd，不写仓库目录。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.protocols import LLMAdapter
from lca.plugins.transport.webserver.handlers.runs.doctor.step_check import (
    diagnose_step_tree,
)
from lca.plugins.transport.webserver.handlers.runs.execute import (
    create_run_session,
    execute_run,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunRegistry,
    RunSession,
    RunStatus,
)
from lca_kernel import run_kernel_lifespan
from lca_kernel.events.bus import EventBus
from tests.harness.scripted_llm import ScriptedLLMAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "web-standard.yaml"

# D7 断言 3 的账本 EP 集：认知族开窗信号 + LLM 请求头 + 显式 step 边界。
# ``writable.step.start`` 由 cursor 显式发射（G7 / ADR-0184 D6，
# record_request_header / open_step 发射点）。
REQUIRED_LEDGER_EPS: tuple[str, ...] = (
    "brain.think.start",
    "llm.request.header",
    "writable.step.start",
)


class _ScriptedResolver:
    """测试替身：resolver 直接返回注入的脚本化 LLM。

    与 ``tests/test_gateway_auto_run.py`` 同形态；生产 ``llm_resolver``
    capability 在 boot 后被该替身替换，run 全程无真 LLM。
    """

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm

    def is_available(self) -> bool:
        return True

    def resolve(self, *, mode: str | None = None) -> LLMAdapter:
        del mode
        return self._llm


@pytest.fixture
def event_singletons_reset() -> Iterator[None]:
    """EventBus 进程级单例测试前后对称重置。

    与 ``tests/integration/conftest.py:event_singletons_reset`` 同语义；
    conftest 夹具按目录作用域可见，场景层取不到，故本地设置。
    """
    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """run 产物隔离：cwd 切到临时目录，``bundles/`` 以符号链接接入。

    boot 与 run 的落盘路径（``.lca/``、``traces/``）均相对 cwd；
    profile 以绝对路径传入，``bundles/*.yaml`` 经
    ``Path.cwd() / bundle_path`` 候选解析到链接目标。
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bundles").symlink_to(REPO_ROOT / "bundles")
    return tmp_path


async def _run_solo(isolated_cwd: Path) -> tuple[RunSession, Path]:
    """真 profile boot + 最小 solo run；返回已完成的 session 与 run 目录。

    precondition：``isolated_cwd`` 已切 cwd（run 产物落临时目录）。
    失败语义：run 未走完直接断言失败 —— 后续投递断言的失败原因
    必须可归因到投递，不能归因到 run 本身。
    """
    llm = ScriptedLLMAdapter({}, default_respond=True)
    registry = RunRegistry()
    async with run_kernel_lifespan(PROFILE_PATH) as state:
        ctx = state["ctx"]
        ctx.provide("llm_resolver", _ScriptedResolver(llm))
        session: RunSession = create_run_session(
            registry,
            question="ping",
            user_text="ping",
            mode="solo",
            ctx=ctx,
        )
        await execute_run(
            registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
            ctx=ctx,
        )
    assert session.status is RunStatus.COMPLETED, (
        f"run {session.run_id} 未完成（status={session.status}, "
        f"error={session.error!r}），投递断言不成立"
    )
    return session, isolated_cwd / "traces" / "runs" / session.run_id


def _ledger_eps(ledger_path: Path) -> set[str]:
    return {
        json.loads(line)["execution_point"]
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


async def test_explicit_step_boundary_delivery_reachable(
    isolated_cwd: Path,
    event_singletons_reset: None,
) -> None:
    """G7 / ADR-0184 D6 + D7 断言 1–3：显式 step 边界投递可达。

    cursor 在 step 边界显式发射 ``writable.step.start``（PR-E 恢复的
    契约），journal step 由显式边界可查：``steps ≥ 1``、doctor 无
    broken hop、账本含三个契约 EP、首步 ``window_signal == "explicit"``。
    """
    session, run_dir = await _run_solo(isolated_cwd)
    run_id = session.run_id
    journal_path = run_dir / "journal.json"
    ledger_path = run_dir / f"{run_id}.spine.jsonl"

    # 1. journal.json steps ≥ 1：step 开窗信号到达 step-tree fold。
    doc = json.loads(journal_path.read_text(encoding="utf-8"))
    steps = doc.get("steps", [])
    assert len(steps) >= 1, f"journal.json steps 为空（run {run_id}）：开窗事件未投递"

    # 2. doctor broken_hop is None：H-seg 等全部 hop 干净。
    report = diagnose_step_tree(journal_path)
    assert report.broken_hop is None, (
        f"doctor broken_hop={report.broken_hop}（run {run_id}）：{report.summary}"
    )

    # 3. 账本含三个契约 EP。
    ledger_eps = _ledger_eps(ledger_path)
    missing = [ep for ep in REQUIRED_LEDGER_EPS if ep not in ledger_eps]
    assert not missing, f"账本缺 EP {missing}（run {run_id}）；实有 {sorted(ledger_eps)}"

    # 4. 开窗来源可查（ADR-0184 PR-E）：首步由显式边界开窗。
    assert steps[0].get("extra", {}).get("window_signal") == "explicit", (
        f"首步 window_signal={steps[0].get('extra')!r}（run {run_id}）："
        "显式 writable.step.start 未驱动开窗"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ADR-0184 PR-C 未落地：boot 仍走 register_pipeline_once（不挂 sink），"
        "总线持久类 category 零 sink → dropped > 0（投递黑洞，§0）"
    ),
)
async def test_event_delivery_counters_zero_dropped(
    isolated_cwd: Path,
    event_singletons_reset: None,
) -> None:
    """D7 断言 4：总线按 category 的投递计数 ``dropped == 0``。

    翻正条件：ADR-0184 PR-C（boot 切 ``apply_pipeline`` + I1 装配校验 +
    共享写实例）验收通过；翻正是 PR-C 的验收动作之一。
    """
    session, run_dir = await _run_solo(isolated_cwd)
    run_id = session.run_id
    journal_path = run_dir / "journal.json"
    ledger_path = run_dir / f"{run_id}.spine.jsonl"

    # 断言 1–3 同 test_explicit_step_boundary_delivery_reachable；
    # 本测试锁全量四条,翻正时四条必须同时成立。
    doc = json.loads(journal_path.read_text(encoding="utf-8"))
    assert len(doc.get("steps", [])) >= 1, f"journal.json steps 为空（run {run_id}）"
    report = diagnose_step_tree(journal_path)
    assert report.broken_hop is None, f"doctor broken_hop={report.broken_hop}（run {run_id}）"
    ledger_eps = _ledger_eps(ledger_path)
    missing = [ep for ep in REQUIRED_LEDGER_EPS if ep not in ledger_eps]
    assert not missing, f"账本缺 EP {missing}（run {run_id}）；实有 {sorted(ledger_eps)}"

    # 4. 总线按 category 的投递计数 dropped == 0（D2）。
    # 访问器形态锁定为 delivery_snapshot() → category → 四值计数（PR-A 提供）。
    snapshot: Any = EventBus.default().delivery_snapshot()
    for category, counters in snapshot.items():
        assert counters["dropped"] == 0, (
            f"category={category} dropped={counters['dropped']}：publish 成功但未落盘/未派发"
        )

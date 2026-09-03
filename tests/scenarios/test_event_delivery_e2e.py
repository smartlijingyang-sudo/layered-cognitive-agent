"""ADR-0184 §2 D7 投递可达性回归锁（PR-B）。

锁守的不变量：生产装配下经总线发布的事件必须全部落盘并派发 ——
run 结束后 ``journal.json`` 有 step、doctor 无 broken hop、账本含认知族
与显式 step 边界 EP、总线按 category 的投递计数 ``dropped == 0``。

翻正条件：ADR-0184 PR-C（boot 切 ``apply_pipeline`` + I1 装配校验 +
共享写实例）与 PR-E（``writable.step.*`` 显式契约恢复发射）验收通过；
翻正是 PR-C 的验收动作之一。当前装配存在投递黑洞（ADR-0184 §0），
测试以 ``xfail(strict=True)`` 锁住：测试体失败 = 合法 xfail，
意外通过 = XPASS failure。断言 4 的 ``delivery_snapshot()`` 访问器由
PR-A 提供；PR-A 落地前访问失败是预期失败形态之一。

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
# ``writable.step.start`` 由 PR-E 恢复发射（ADR-0184 §5）。
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


@pytest.mark.xfail(strict=True, reason="ADR-0184: 投递黑洞在 PR-C 装配切换前存在")
async def test_event_delivery_reachable(
    isolated_cwd: Path,
    event_singletons_reset: None,
) -> None:
    """真 profile boot + 最小 solo run 后，四条投递可达性断言全部成立。"""
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
    run_id = session.run_id

    # 前置条件：run 本身必须走完，否则后续断言的失败原因不可归因到投递。
    assert session.status is RunStatus.COMPLETED, (
        f"run {run_id} 未完成（status={session.status}, error={session.error!r}），投递断言不成立"
    )

    run_dir = isolated_cwd / "traces" / "runs" / run_id
    journal_path = run_dir / "journal.json"
    ledger_path = run_dir / f"{run_id}.spine.jsonl"

    # 1. journal.json steps ≥ 1：step 开窗信号到达 step_tree_accumulator。
    doc = json.loads(journal_path.read_text(encoding="utf-8"))
    steps = doc.get("steps", [])
    assert len(steps) >= 1, f"journal.json steps 为空（run {run_id}）：开窗事件未投递"

    # 2. doctor broken_hop is None：H-seg 等全部 hop 干净。
    report = diagnose_step_tree(journal_path)
    assert report.broken_hop is None, (
        f"doctor broken_hop={report.broken_hop}（run {run_id}）：{report.summary}"
    )

    # 3. 账本含三个契约 EP。
    ledger_eps = {
        json.loads(line)["execution_point"]
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    missing = [ep for ep in REQUIRED_LEDGER_EPS if ep not in ledger_eps]
    assert not missing, f"账本缺 EP {missing}（run {run_id}）；实有 {sorted(ledger_eps)}"

    # 4. 总线按 category 的投递计数 dropped == 0（D2）。
    # 访问器形态锁定为 delivery_snapshot() → category → 四值计数（PR-A 提供）。
    snapshot: Any = EventBus.default().delivery_snapshot()
    for category, counters in snapshot.items():
        assert counters["dropped"] == 0, (
            f"category={category} dropped={counters['dropped']}：publish 成功但未落盘/未派发"
        )

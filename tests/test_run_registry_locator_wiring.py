"""RunRegistry 持有 RunLocator 并把 path 解析委托给它(ADR-0065 PR-11)。

旧布局把 ``traces/runs/<id>.jsonl`` 当 flat 文件写;新布局要求每个 run
一个目录 ``<root>/runs/<run_id>/`` 下放 ``journal.jsonl`` + ``manifest.json``
+ ``evidence/`` + ``materializations/``。``RunRegistry`` 是 gateway 唯一
run 索引,所有 path 都从 locator 解析,不再硬编码 ``_RUNS_DIR / f"{run_id}.jsonl``。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gateway.runs.observability.identity import parse_agent_ref
from gateway.runs.session.session import RunRegistry, RunSession
from lca.contracts.observability.run_locator import RunLocator
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.run_locator_fs import FilesystemRunLocator


class _FakeLocator(RunLocator):
    """协议级 stub;验证 RunRegistry 调用了 locator 的哪些方法。"""

    def __init__(self, root: Path) -> None:
        self._root = root
        self.journal_calls: list[str] = []
        self.manifest_calls: list[str] = []
        self.evidence_calls: list[str] = []
        self.material_calls: list[tuple[str, str, str]] = []
        self.update_calls: list[str] = []
        self.latest_called: int = 0

    @property
    def storage_root(self) -> Path:
        return self._root

    def run_dir(self, run_id: str) -> Path:
        return self._root / "runs" / run_id

    def journal_path(self, run_id: str) -> Path:
        self.journal_calls.append(run_id)
        return self._root / "runs" / run_id / "journal.jsonl"

    def manifest_path(self, run_id: str) -> Path:
        self.manifest_calls.append(run_id)
        return self._root / "runs" / run_id / "manifest.json"

    def evidence_dir(self, run_id: str) -> Path:
        self.evidence_calls.append(run_id)
        return self._root / "runs" / run_id / "evidence"

    def materialization_dir(
        self, run_id: str, *, generator_id: str, generator_version: str
    ) -> Path:
        self.material_calls.append((run_id, generator_id, generator_version))
        return self._root / "runs" / run_id / "materializations" / generator_id / generator_version

    def latest_pointer_path(self) -> Path:
        self.latest_called += 1
        return self._root / "latest.json"

    def update_latest_pointer(self, run_id: str) -> None:
        self.update_calls.append(run_id)


class RunRegistryLocatorWiring(unittest.TestCase):
    """RunRegistry 把 path 解析委托给注入的 RunLocator。"""

    def test_default_locator_is_filesystem_with_storage_root_traces(self) -> None:
        reg = RunRegistry()
        locator = reg.locator()
        self.assertIsInstance(locator, FilesystemRunLocator)
        self.assertEqual(locator.storage_root, Path("traces"))

    def test_explicit_locator_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = _FakeLocator(Path(tmp))
            reg = RunRegistry(locator=fake)
            self.assertIs(reg.locator(), fake)

    def test_jsonl_path_uses_locator_journal_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _FakeLocator(root)
            reg = RunRegistry(locator=fake)
            result = reg.jsonl_path_for("run_abc1234")
            self.assertEqual(result, root / "runs" / "run_abc1234" / "journal.jsonl")
            self.assertEqual(fake.journal_calls, ["run_abc1234"])

    def test_manifest_path_evidence_dir_materialization_dir_use_locator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _FakeLocator(root)
            reg = RunRegistry(locator=fake)
            m = reg.manifest_path_for("run_x")
            e = reg.evidence_dir_for("run_x")
            d = reg.materialization_dir_for("run_x", generator_id="cost", generator_version="1")
            self.assertEqual(m, root / "runs" / "run_x" / "manifest.json")
            self.assertEqual(e, root / "runs" / "run_x" / "evidence")
            self.assertEqual(d, root / "runs" / "run_x" / "materializations" / "cost" / "1")

    def test_update_latest_pointer_delegates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _FakeLocator(root)
            reg = RunRegistry(locator=fake)
            reg.update_latest_pointer("run_y")
            self.assertEqual(fake.update_calls, ["run_y"])


class RunSessionHoldsLocator(unittest.TestCase):
    """RunSession.locator 字段存在,默认 None(测试 / 直构造场景)。"""

    def test_default_locator_field_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = RunSession(
                run_id="run_x",
                trace_id="t",
                jsonl_path=Path(tmp) / "runs" / "run_x" / "journal.jsonl",
                tail=LiveTail(),
                question="q",
                user_text="q",
                mode="solo",
                agent=parse_agent_ref({"id": "solo", "name": "助手"}),
            )
            self.assertIsNone(session.locator)

    def test_started_at_default_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = RunSession(
                run_id="run_x",
                trace_id="t",
                jsonl_path=Path(tmp) / "runs" / "run_x" / "journal.jsonl",
                tail=LiveTail(),
                question="q",
                user_text="q",
                mode="solo",
                agent=parse_agent_ref({"id": "solo", "name": "助手"}),
            )
            self.assertEqual(session.started_at, 0.0)


if __name__ == "__main__":
    unittest.main()

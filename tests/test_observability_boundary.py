"""可观测性体系守卫 —— 边界 / 词表 / 脱敏 / 隔离 / verbosity / trace 连贯。

设计意图：可观测性的"不乱"由 CI 强制，不靠自觉。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from lca.contracts.journal_catalog import JOURNAL_CATALOG, JOURNAL_EVENT_CLASSES
from lca.contracts.telemetry import EventName, SpanName
from lca.contracts.telemetry_catalog import TELEMETRY_CATALOG

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LCA_DIR = _REPO_ROOT / "lca"
_OBS_PKG = "lca.layer0_infra.observability"
_EMIT_CALLS = frozenset({"span", "detached_span", "event", "traced"})


def _iter_lca_modules() -> list[tuple[str, Path]]:
    mods: list[tuple[str, Path]] = []
    for path in sorted(_LCA_DIR.rglob("*.py")):
        rel = path.relative_to(_REPO_ROOT).with_suffix("")
        mods.append((".".join(rel.parts), path))
    return mods


class TestBoundaryGuard(unittest.TestCase):
    """包外禁入子模块；OTel 只在可观测性子包内出现。"""

    def test_no_submodule_imports_outside_package(self) -> None:
        violations: list[str] = []
        for mod, path in _iter_lca_modules():
            if mod.startswith(_OBS_PKG):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imported: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported = [node.module]
                elif isinstance(node, ast.Import):
                    imported = [a.name for a in node.names]
                for name in imported:
                    if name.startswith(_OBS_PKG + ".") and not name.startswith(
                        _OBS_PKG + ".adapters"
                    ):
                        violations.append(f"{mod}: {name}")
        self.assertEqual(
            violations,
            [],
            "L0 observability 子模块被包外 import（唯一表面是包根 __init__）:\n"
            + "\n".join(violations),
        )

    def test_opentelemetry_confined_to_observability_package(self) -> None:
        violations: list[str] = []
        for mod, path in _iter_lca_modules():
            if mod.startswith(_OBS_PKG):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                if any(n.startswith("opentelemetry") for n in names):
                    violations.append(mod)
                    break
        self.assertEqual(
            violations,
            [],
            "opentelemetry 被可观测性子包之外的模块 import（骨干可替换性破坏）:\n"
            + "\n".join(sorted(set(violations))),
        )


class TestVocabularyGuard(unittest.TestCase):
    """发射首参必须是词表枚举；一词条一发射点。"""

    def _collect_emissions(self) -> dict[str, set[str]]:
        """词表值 → 发射模块集合（仅统计 span/event/traced 调用）。"""
        emissions: dict[str, set[str]] = {}
        for mod, path in _iter_lca_modules():
            if mod.startswith("lca.contracts"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                fname = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else (func.id if isinstance(func, ast.Name) else None)
                )
                if fname not in _EMIT_CALLS or not node.args:
                    continue
                first = node.args[0]
                if (
                    isinstance(first, ast.Attribute)
                    and isinstance(first.value, ast.Name)
                    and first.value.id in ("SpanName", "EventName")
                ):
                    emissions.setdefault(first.attr, set()).add(mod)
                elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                    self.fail(f"{mod}: 发射使用裸字符串 {first.value!r}（必须用词表枚举）")
        return emissions

    def test_emitted_names_exist_in_vocabulary(self) -> None:
        known = {m.name for m in SpanName} | {m.name for m in EventName}
        for attr, mods in self._collect_emissions().items():
            self.assertIn(attr, known, f"发射了未登记词表项 {attr}（{sorted(mods)}）")

    def test_single_emission_site_per_vocab(self) -> None:
        for attr, mods in self._collect_emissions().items():
            enum_member = getattr(SpanName, attr, None) or getattr(EventName, attr, None)
            entry = TELEMETRY_CATALOG.get(enum_member.value)
            self.assertIsNotNone(entry, f"词表项 {attr} 未在 TELEMETRY_CATALOG 登记")
            offenders = [m for m in mods if not m.startswith(entry.emitter)]
            self.assertEqual(
                offenders,
                [],
                f"{attr} 的唯一发射模块应为 {entry.emitter}，越界发射：{sorted(offenders)}",
            )


class TestRedactionBackstop(unittest.TestCase):
    """脱敏在写入期强制兜底——发射点不自觉也会被拦。"""

    def test_secret_in_preview_is_redacted(self) -> None:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from lca.layer0_infra.observability import ObservabilityHub, bind, span
        from lca.layer0_infra.observability.view import view_of

        exporter = InMemorySpanExporter()
        hub = ObservabilityHub([exporter])
        with (
            bind(hub),
            span(
                SpanName.LLM_CHAT,
                **{"prompt_preview": "key=sk-1234567890abcdef 正常内容"},
            ),
        ):
            pass
        views = [view_of(s) for s in exporter.get_finished_spans()]
        preview = views[0].attributes["prompt_preview"]
        self.assertNotIn("sk-1234567890abcdef", preview)
        self.assertIn("[REDACTED]", preview)


class TestExporterFaultIsolation(unittest.TestCase):
    """单个导出器故障不中断 run，不影响其余导出器。"""

    def test_failing_exporter_does_not_break_run(self) -> None:
        from opentelemetry.sdk.trace.export import SpanExporter
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from lca.layer0_infra.observability import ObservabilityHub, bind, span

        class ExplodingExporter(SpanExporter):
            def export(self, spans):
                raise RuntimeError("boom")

            def shutdown(self):
                return None

        good = InMemorySpanExporter()
        hub = ObservabilityHub([ExplodingExporter(), good])
        with bind(hub), span(SpanName.TOOL_EXECUTE, **{"tool_name": "calculator"}):
            pass  # run 不被打断
        self.assertEqual(len(good.get_finished_spans()), 1)


class TestVerbosityLevels(unittest.TestCase):
    """verbosity 档位控制预览长度。"""

    def _preview_len(self, verbosity: str) -> int:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from lca.layer0_infra.observability import ObservabilityHub, bind, span
        from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
        from lca.layer0_infra.observability.view import view_of

        exporter = InMemorySpanExporter()
        hub = ObservabilityHub([exporter], policy=AttributePolicy(Verbosity(verbosity)))
        long_text = "字" * 5000
        with bind(hub), span(SpanName.LLM_CHAT, **{"prompt_preview": long_text}):
            pass
        view = view_of(exporter.get_finished_spans()[0])
        preview = view.attributes.get("prompt_preview")
        return 0 if preview is None else len(preview)

    def test_minimal_drops_previews(self) -> None:
        self.assertEqual(self._preview_len("minimal"), 0)

    def test_standard_truncates_previews(self) -> None:
        length = self._preview_len("standard")
        self.assertGreater(length, 0)
        self.assertLess(length, 5000)

    def test_verbose_keeps_full_text(self) -> None:
        self.assertGreaterEqual(self._preview_len("verbose"), 5000)


class TestJournalVocabularyGuard(unittest.TestCase):
    """journal 词表守卫：record(...) 必须构造已登记事件；一事件一发射点。"""

    def _collect_record_emissions(self) -> dict[str, set[str]]:
        """事件类名 → 发射模块集合（仅统计裸 ``record(...)`` 调用）。

        属性调用（``hub.journal.record(...)`` / ``self._journal.record(...)``）
        是引擎内部接线，不算业务发射点；发射点一律从包根 import 裸调用。
        """
        emissions: dict[str, set[str]] = {}
        for mod, path in _iter_lca_modules():
            if mod.startswith("lca.contracts"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Name) or func.id != "record" or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Call) and isinstance(first.func, ast.Name):
                    emissions.setdefault(first.func.id, set()).add(mod)
                else:
                    self.fail(
                        f"{mod}: record(...) 首参必须是已登记事件类的构造调用（ADR-0037 词表守卫）"
                    )
        return emissions

    def test_recorded_events_exist_in_vocabulary(self) -> None:
        for cls_name in self._collect_record_emissions():
            self.assertIn(cls_name, JOURNAL_EVENT_CLASSES, f"发射了未登记 journal 事件 {cls_name}")

    def test_single_emission_site_per_journal_event(self) -> None:
        for cls_name, mods in self._collect_record_emissions().items():
            entry = JOURNAL_CATALOG.get(cls_name)
            self.assertIsNotNone(entry, f"journal 事件 {cls_name} 未在 JOURNAL_CATALOG 登记")
            offenders = [m for m in mods if not m.startswith(entry.emitter)]
            self.assertEqual(
                offenders,
                [],
                f"{cls_name} 的唯一发射模块应为 {entry.emitter}，越界发射：{sorted(offenders)}",
            )

    def test_catalog_covers_every_event_class(self) -> None:
        self.assertEqual(
            set(JOURNAL_CATALOG),
            set(JOURNAL_EVENT_CLASSES),
            "JOURNAL_CATALOG 与 JOURNAL_EVENT_CLASSES 必须一一对应",
        )


if __name__ == "__main__":
    unittest.main()

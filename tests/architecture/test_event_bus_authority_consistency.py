"""EventBus 鉴权三方一致性架构测试 —— plugin-universe PR-6。

对事件系统强制三向对齐(ADR-0183 §2.2 + plugin-universe PR-6):

  yaml whitelist ⟺ manifest ``@plugin`` 声明 ⟺ 生产 ``EventBus.subscribe(...)`` 调用

每条事件 category 的订阅者集合必须同时满足:

1. **yaml vs. ``@plugin`` 声明** — yaml 鉴权矩阵引用的类,其定义文件
   若已含 ``@plugin`` 装饰器,则该 plugin 的 boot 函数不允许绕过 yaml
   whitelist 自订阅所有 category。PR-6 收口的两个 drift 形态:

   - ``lca/plugins/events/sinks/journal/manifest.py`` —— 自订阅全部
     registry.specs;yaml 仅授权 ``team.`` 1 个 prefix(101 个 category 仅 1
     命中);整目录删除(PR-6 / a)。
   - ``lca/plugins/events/sinks/spine_file_sink/manifest.py`` —— 同形态
     自订阅;改为由 yaml 显式声明 + boot 不再自订阅(PR-6 / b)。

   本测试守护:已声明为 ``@plugin`` 的事件组件不再出现新的自订阅绕过。
2. **yaml vs. production subscribe** — yaml 授权的每个 category 至少有一处
   production ``EventBus.subscribe(`` 调用站点;否则 yaml 授权了零订阅者
   的孤儿 category。允许 ``spine.`` 兜底规则(机制在 Pipeline 装载期按前缀
   统一接线)。

测试不启动 EventBus 注册中心,只读 yaml + AST 扫描;维护成本接近 0。
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVENT_CONFIG_DIR = _REPO_ROOT / "lca_kernel" / "events" / "config"
_PLUGINS_ROOT = _REPO_ROOT / "lca" / "plugins"
_SCAN_ROOTS = [
    _REPO_ROOT / "lca",
    _REPO_ROOT / "lca_kernel",
    _REPO_ROOT / "profiles",
    _REPO_ROOT / "bundles",
    _REPO_ROOT / "scripts",
]
_EXCLUDE_SUBSTRINGS: tuple[str, ...] = (
    "archive/",
    "tests/",
)


# ── 工具 ────────────────────────────────────────────────────────────────


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """ripgrep;空 = 无匹配。"""
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                pattern,
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(pattern, line):
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


# ── 数据收集 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class YamlAuthRecord:
    """一条 yaml 鉴权记录:category → 授权类集合。"""

    category: str
    publishers: frozenset[str]
    subscribers: frozenset[str]


def _collect_yaml_auth() -> list[YamlAuthRecord]:
    """遍历 lca_kernel/events/config/**/*.yaml,装载 EventRegistry-style 鉴权矩阵。"""
    from lca_kernel.events.registry import EventRegistry

    registry = EventRegistry.load(_EVENT_CONFIG_DIR)
    out: list[YamlAuthRecord] = []
    for spec in registry.specs:
        pubs = frozenset(f"{p.__module__}.{p.__qualname__}" for p in spec.publishers)
        subs = frozenset(f"{s.__module__}.{s.__qualname__}" for s in spec.subscribers)
        out.append(
            YamlAuthRecord(
                category=spec.category.value,
                publishers=pubs,
                subscribers=subs,
            )
        )
    return out


def _class_qualname_to_file(qualname: str) -> Path | None:
    """``module.path.ClassName`` → repo-relative .py 路径。"""
    module_path, _, _ = qualname.rpartition(".")
    if not module_path:
        return None
    return _REPO_ROOT / (module_path.replace(".", "/") + ".py")


def _file_has_plugin_decorator(path: Path) -> str | None:
    """若文件含 ``@plugin(...)`` 装饰器,返回该 plugin 的 id;否则 None。"""
    if not path.exists() or path.suffix != ".py":
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if src.startswith("plugin(") or src == "plugin":
                    if isinstance(dec, ast.Call):
                        for kw in dec.keywords:
                            if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                                return str(kw.value.value)
                    return "<plugin-without-id>"
    return None


def _collect_production_subscribe_callsites() -> set[str]:
    """生产 ``EventBus.subscribe(`` 调用站点集合(去重:行级 grep)。"""
    sites: set[str] = set()
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for line in _rg(r"\.subscribe\(", root):
            if any(sub in line for sub in _EXCLUDE_SUBSTRINGS):
                continue
            sites.add(line)
    return sites


# ── fixture ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def yaml_auth() -> list[YamlAuthRecord]:
    return _collect_yaml_auth()


@pytest.fixture(scope="module")
def subscribe_sites() -> set[str]:
    return _collect_production_subscribe_callsites()


# ── 测试 ────────────────────────────────────────────────────────────────


class TestYamlWhitelistAndPluginDeclaration:
    """不变量 1:yaml 鉴权矩阵引用的类,其定义文件若已含 ``@plugin`` 装饰器
    (即 plugin 声明已落地),则属于"plugin-side drift"治理范围。

    PR-6 收口时确认:
    - ``lca.plugins.events.sinks.journal.sink.JournalSink`` 的定义文件
      已被整目录删除 —— yaml 不再授权,plugin 不再声明。
    - ``lca.plugins.events.sinks.spine_file_sink.sink.SpineFileSink`` 的
      定义文件保留(PR-6 / b 选定 wire),yaml 在 ``spine.`` 兜底规则新增授权,
      manifest 不再自订阅。

    本测试守护:yaml 授权类若定义文件已是 ``@plugin``,其 bootstrap 路径
    必须由 yaml 显式声明驱动(通过 consumer_rules 或 Pipeline consumer_rules),
    不允许在 setup 函数内 ``for spec in bus.registry.specs`` 循环自订阅。
    """

    _SELF_SUBSCRIBE_PATTERN = re.compile(
        r"for\s+spec\s+in\s+bus_obj?\.registry\.specs"
    )

    def test_no_yaml_authorized_plugin_self_subscribes_all_categories(
        self,
        yaml_auth: list[YamlAuthRecord],
    ) -> None:
        """yaml 授权了某 plugin → 该 plugin 的 setup 函数不能自订阅全部
        category(必须由 yaml 显式 prefix 规则或 Pipeline 装配驱动)。
        """
        yaml_authorized_classes: set[str] = set()
        for record in yaml_auth:
            yaml_authorized_classes.update(record.publishers)
            yaml_authorized_classes.update(record.subscribers)

        # 筛出"定义文件已含 @plugin 装饰器"的 yaml 授权类 —— 即真正进入
        # "plugin-side drift"治理范围的子集。尚未迁移到 @plugin 形态的事件
        # 组件(由 plugin-universe PR-4 收口)不在本测试治理范围。
        plugin_authorized: set[tuple[str, Path]] = set()
        for cls in yaml_authorized_classes:
            path = _class_qualname_to_file(cls)
            if path is None:
                continue
            plugin_id = _file_has_plugin_decorator(path)
            if plugin_id is not None:
                plugin_authorized.add((cls, path))

        violations: list[str] = []
        for cls, path in plugin_authorized:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            rel = path.relative_to(_REPO_ROOT)
            if self._SELF_SUBSCRIBE_PATTERN.search(text):
                violations.append(f"{rel}: yaml-authorized plugin {cls} self-subscribes all categories")

        assert not violations, (
            "三方鉴权违规 1:yaml 授权的 plugin 在 setup 函数内自订阅所有 category(绕过 yaml whitelist)\n"
            + "\n".join(violations)
        )


class TestEveryYamlCategoryHasProductionSubscribe:
    """不变量 2:yaml 授权的每个 category 至少有一处 production ``EventBus.subscribe(``
    调用站点;否则 yaml 授权了零订阅者的孤儿 category。

    兜底规则(consumer_rules[prefix="spine."])由机制在 Pipeline 装载期按前缀
    统一接线,不要求 production 代码逐条 .subscribe( cat 字面。
    """

    _BOOT_WIRED_PREFIXES: tuple[str, ...] = ("spine.",)

    def test_yaml_authorized_category_has_subscribe_site(
        self,
        yaml_auth: list[YamlAuthRecord],
        subscribe_sites: set[str],
    ) -> None:
        wired_categories: set[str] = {
            record.category for record in yaml_auth if record.subscribers
        }

        cat_literal_pattern = re.compile(r"category\s*=\s*['\"](\S+?)['\"]")
        wired_via_literal: set[str] = set()
        for site in subscribe_sites:
            for match in cat_literal_pattern.finditer(site):
                wired_via_literal.add(match.group(1))

        def _prefix_covered(category: str) -> bool:
            return any(category.startswith(p) for p in self._BOOT_WIRED_PREFIXES)

        orphans = sorted(
            cat
            for cat in wired_categories
            if cat not in wired_via_literal and not _prefix_covered(cat)
        )
        assert not orphans, (
            "三方鉴权违规 2:yaml 授权了零 subscribe 接线点的 category\n"
            + "\n".join(orphans[:10])
        )


class TestYamlAuthHasNoRemovedSubscribers:
    """不变量 3(PR-6 收口直接证据):``EventRegistry`` 装载后,subscribers 集合
    不再包含 PR-6 已删除组件的类(``JournalSink`` / ``SpineChainSink`` /
    ``SpineStepTreeAccumulator``)。

    delete-when:这三个组件重新出现时,本测试即报失败,作为"删除可逆"的安全网。
    """

    def test_removed_journal_chain_step_tree_classes_not_in_registry(
        self,
        yaml_auth: list[YamlAuthRecord],
    ) -> None:
        forbidden: tuple[str, ...] = (
            "lca.plugins.events.sinks.journal.sink.JournalSink",
            "lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink",
            "lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber.SpineStepTreeAccumulator",
        )
        offenders: list[str] = []
        for record in yaml_auth:
            for cls in record.subscribers | record.publishers:
                if cls in forbidden:
                    offenders.append(f"{record.category}: {cls}")
        assert not offenders, (
            "三方鉴权违规 3:PR-6 已删除组件仍出现在 yaml 鉴权矩阵\n"
            + "\n".join(offenders)
        )


__all__: Iterable[str] = ()

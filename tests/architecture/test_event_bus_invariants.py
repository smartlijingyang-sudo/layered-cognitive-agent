"""EventBus 架构不变量 —— ADR-0183 §4。

不变量（ADR-0183 §4):
- I-FW-BUS-1: producer 唯一入口 = EventBus.publish；reducer / cursor / runtime_loop
  禁直写 spine / 直调 sink。
- I-FW-BUS-2: consumer 唯一入口 = EventBus.subscribe(*, failure=...)；不允许在
  EventBus 框架外调 .subscribe( / .register_sink( (manifest.py 内部走
  EventMechanism 除外)。
- I-FW-BUS-4: 业务不订阅 event.bus.dispatch.*。
- I-FW-SSOT-1: <run_id>.spine.jsonl 唯一 SSOT；events.jsonl legacy reader 必须
  迁到 SpineReader；SpineSink 唯一写。

守护范围（PR-1+PR-2+PR-4 已落地的部分）:
- I-FW-BUS-1 sink 直调部分: spine_chain_sink. / spine_file_sink.write 收口 = 0
- I-FW-BUS-4: profile/bundle consumer_rules 不订阅 event.bus.dispatch.*
- I-FW-SSOT-1 writer: open(events.jsonl, "w") 收口 = 0
- I-FW-SSOT-1 reader: 旧 events.jsonl legacy reader 路径 = 0(允许 lca_kernel/events/ +
  archive/ + 文档/注释引用)
- I-FW-SSOT-1 sink 唯一: lca_kernel/events/sinks/ 唯一 .write( = spine_sink

待后续 PR 收口(本测试在 docstring 内注明债务范围,不在断言里硬性 fail):
- PR-8 reducer: 16 处 coord.emit_phase 兼容路径删除(已合;剩 8 处全在历史叙事注释)
- PR-9 cursor: loop_cursor 直写 spine 收口(已合;cursor 走 self._spine WritePort facade,
  strict 断言守护禁止 cursor 绕 WritePort 直调 event_spine.append()
- PR-10 runtime_loop: emit_exception_caught 4 键裸 dict → EnvelopeEmitter(已合)
- PR-12 trace_id + 自观察: 业务不订阅 event.bus.dispatch.* 由 Pipeline 装载保证(已合)
- PR-3 payload FieldType 字符串化: EventSpec.fields 仍是 dict[str, str];运行期无影响,
  留作下一个 ADR

Model-visible 类别单发布者不变量(DSH-GAP-AUDIT G10;note 语义面守护见
tests/architecture/test_i_mv_*.py):
- I-MV-1: 每个 model-visible 类别在 spine.yaml 恰好注册一个非空 publisher
  token,两类别同为 ``events.model_visible.publisher``。
- I-MV-2: 该 publisher plugin manifest ``ownership.emits`` ⟺ yaml 授权它的
  类别集合,双向同集(无未注册类别被发布)。
- I-MV-3: 注册发布者代码之外无 model-visible 类别的活跃 publish 调用 /
  payload 构造(AST 判定,注释 / docstring / 死字符串天然排除)。
- I-MV-4: yaml publisher token = 已注册 ``@plugin`` id,且全部 model-visible
  publish 点的 ``producer=`` 恰为该 plugin 的 ``marker_class``。
- I-MV-5: 每个 model-visible 类别 ``payload_class`` 非空、是类型化子类
  (非 EventPayload 基类),其 ``category`` 默认值与 yaml 类别一致。
"""

from __future__ import annotations

import ast
import importlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

# 仓库根 = tests/architecture/ 的父父目录
_REPO_ROOT = Path(__file__).resolve().parents[2]

# 测试文件自身路径(白名单:测试自身不在守范围内)
_THIS_TEST_FILE = Path(__file__).resolve()


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep with relative paths; return list of matching lines.

    Empty list = no matches. Falls back to pathlib walk if rg is missing.
    """
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603  # path is a constant binary
            [  # noqa: S607  # rg binary located via shutil.which()
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
        # rg exit code 1 = no matches; 0 = matches; >1 = error
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    # Fallback: pathlib walk
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


def _is_excluded(line: str, exclude_substrings: tuple[str, ...]) -> bool:
    """A match line is excluded if its file path contains any exclude substring."""
    path_part = line.split(":", 1)[0]
    return any(sub in path_part for sub in exclude_substrings)


# ── I-FW-BUS-1 ──────────────────────────────────────────────────────────


class TestIFwBus1:
    """I-FW-BUS-1: producer 唯一入口 = EventBus.publish。

    当前守护范围:
    - sink 直调部分(spine_chain_sink. / spine_file_sink.write): PR-1+2+4 已收口
    - cursor 直写部分(loop_cursor._spine.append): 待 PR-9 收口,本测试标 xfail
      说明债务范围
    """

    def test_i_fw_bus_1_no_direct_spine_append_in_runtime(self) -> None:
        """PR-1+2+4:reducer/cursor/runtime_loop 不允许直写 spine。

        债务：lca/infrastructure/observability/loop_cursor/ 仍直写 _spine
        (4 处),等 PR-9 收口。本断言目前以「非 loop_cursor 路径 = 0」为
        收口基线,loop_cursor 路径用 xfail 标记已知债。
        """
        runtime_root = _REPO_ROOT / "lca" / "runtime"
        if not runtime_root.exists():
            pytest.skip("lca/runtime/ not found")
        # cursor / cognition / runtime 三个目录,排除 loop_cursor(PR-9 收口债)
        search_roots = [
            _REPO_ROOT / "lca" / "runtime",
            _REPO_ROOT / "lca" / "cognition",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"_spine\.append\(|event_spine\.append\(", root):
                matches.append(line)
        # PR-9 debt:lca/infrastructure/observability/loop_cursor/ 仍直写
        # 4 处,本测试不守护该路径,只守护 lca/runtime/ + lca/cognition/
        assert not matches, "I-FW-BUS-1 违规:reducer/cognition 仍直写 spine.append\n" + "\n".join(
            matches[:5]
        )

    def test_i_fw_bus_1_loop_cursor_no_bypass_write_port(self) -> None:
        """I-FW-BUS-1 (PR-9):cursor 通过 ``self._spine`` (WritePort facade) 写 spine。

        cursor 业务方调 ``self._spine.append(`` 是 WritePort Protocol 调用
        (PR-9 commit 477c8a35 设计本身)。禁止 cursor 绕过 WritePort 直接
        调 ``event_spine.append(``——后者是绕 facade,违反 I-FW-BUS-1。
        """
        loop_cursor = _REPO_ROOT / "lca" / "infrastructure" / "observability" / "loop_cursor"
        if not loop_cursor.exists():
            pytest.skip("loop_cursor path not found")
        # 仅扫描绕过 WritePort 的直调;cursor 调 self._spine.append 是 facade 调用
        bypass = _rg(r"event_spine\.append\(", loop_cursor)
        assert not bypass, (
            "I-FW-BUS-1 违规:cursor 绕过 WritePort 直调 event_spine.append(\n"
            + "\n".join(bypass[:5])
        )

    def test_i_fw_bus_1_no_direct_sink_call_in_runtime(self) -> None:
        """PR-1+2+4:生产路径不直调 sink(spine_chain_sink./spine_file_sink.write)。"""
        search_roots = [
            _REPO_ROOT / "lca" / "runtime",
            _REPO_ROOT / "lca" / "cognition",
            _REPO_ROOT / "lca" / "agent",
            _REPO_ROOT / "lca" / "application",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"spine_chain_sink\.(?!Sink\b)|spine_file_sink\.write\(", root):
                matches.append(line)
        assert not matches, "I-FW-BUS-1 违规:生产路径直调 sink\n" + "\n".join(matches[:5])


# ── I-FW-BUS-2 ──────────────────────────────────────────────────────────


class TestIFwBus2:
    """I-FW-BUS-2: consumer 唯一入口 = EventBus.subscribe(*, failure=...)。

    当前守护范围:除白名单外,生产路径不应有 .subscribe( / .register_sink(
    调用。白名单:EventMechanism 框架内(lca_kernel/events/)、
    manifest.py 内部走 EventMechanism、journal/spine/session 的非事件框架
    subscribe(tail.subscribe 等)已知债(待 PR-9 收口)。
    """

    # 框架内 + manifest.py 内部 + 测试自身的合法位置
    _ALLOW_PATH_SUBSTRINGS: tuple[str, ...] = (
        "lca_kernel/events/",  # EventMechanism / EventBus 框架本体
        "lca/plugins/events/",  # 业务方 plugin manifest 内部走 EventMechanism
        "archive/",  # 归档
        str(_THIS_TEST_FILE.name),  # 本测试文件
    )

    # 已知债位置:loop_cursor/event_spine、live_tail、session.tail 等
    # 这些 .subscribe( 是 spine/live_tail/session 的非事件框架订阅方法,
    # 不是 EventMechanism.subscribe。等 PR-9 收口后从白名单移除。
    _KNOWN_DEBT_PATH_SUBSTRINGS: tuple[str, ...] = (
        "lca/infrastructure/observability/loop_cursor/",  # event_spine.subscribe
        "lca/infrastructure/observability/journal/stream/live_tail.py",  # tail.subscribe
        "lca/infrastructure/observability/spine/derivers/live_tail.py",  # self._tail.subscribe
        "lca/harness/agent/activation.py",  # store.subscribe (projection 订阅)
        "lca/plugins/transport/webserver/handlers/runs/terminal/registry_queries.py",  # session.tail.subscribe
    )

    def test_i_fw_bus_2_subscribe_outside_framework_blocked(self) -> None:
        """I-FW-BUS-2:除白名单外,生产路径不应有 .subscribe( / .register_sink(。"""
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
        ]
        all_matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"\.subscribe\(|\.register_sink\(", root):
                # 应用两层白名单
                if _is_excluded(line, self._ALLOW_PATH_SUBSTRINGS):
                    continue
                if _is_excluded(line, self._KNOWN_DEBT_PATH_SUBSTRINGS):
                    continue
                all_matches.append(line)
        # 测试文件自身不在守范围
        filtered = [m for m in all_matches if not _is_excluded(m, (str(_THIS_TEST_FILE.name),))]
        # tests/ 目录下的 .subscribe( 是测试 fixture 调用机制,不算违规
        # 但仍要排除 tests/audit_hook_attach.py 内的 fixture 字符串
        # (它在 _write_py 内写磁盘,会被 rg 抓到)
        # 已通过 _KNOWN_DEBT 不覆盖 tests/ 目录;这里单独再排除 tests/
        filtered = [
            m for m in filtered if not m.startswith("tests/") and "tests/" not in m.split(":", 1)[0]
        ]
        assert not filtered, (
            "I-FW-BUS-2 违规:框架外 .subscribe( / .register_sink( 调用\n" + "\n".join(filtered[:5])
        )


# ── I-FW-BUS-4 ──────────────────────────────────────────────────────────


class TestIFwBus4:
    """I-FW-BUS-4: 业务不订阅 event.bus.dispatch.*。"""

    _SELF_OBS_PREFIX = "event.bus.dispatch"

    def test_i_fw_bus_4_no_business_subscribe_dispatch_event(self) -> None:
        """Pipeline 订阅面不得路由 event.bus.dispatch.*。

        只扫**订阅面**:``consumer_rules[].prefix`` 与逐条 ``category`` 块。
        自观察 hook 的 ``config.emit_event*`` 是**发射**配置而非订阅,不判违规。
        """
        import yaml

        search_roots = [
            _REPO_ROOT / "lca" / "profiles",
            _REPO_ROOT / "lca" / "bundles",
            _REPO_ROOT / "profiles",
            _REPO_ROOT / "bundles",
        ]
        violations: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in list(root.rglob("*.yaml")) + list(root.rglob("*.yml")):
                rel = path.relative_to(_REPO_ROOT)
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
                except (OSError, yaml.YAMLError):
                    continue
                mapping = None
                if isinstance(data, dict):
                    inner = data.get("pipeline")
                    mapping = inner if isinstance(inner, dict) else data
                if not isinstance(mapping, dict):
                    continue
                for rule in mapping.get("consumer_rules") or []:
                    if not isinstance(rule, dict):
                        continue
                    prefix = str(rule.get("prefix", ""))
                    if prefix.startswith(self._SELF_OBS_PREFIX):
                        violations.append(f"{rel}: consumer_rules prefix={prefix!r}")
                for block in mapping.get("events") or []:
                    if isinstance(block, dict) and str(block.get("category", "")).startswith(
                        self._SELF_OBS_PREFIX
                    ):
                        violations.append(f"{rel}: category={block.get('category')!r}")
        assert not violations, "I-FW-BUS-4 违规:业务订阅 event.bus.dispatch.*\n" + "\n".join(
            violations[:5]
        )


# ── I-FW-SSOT-1 ─────────────────────────────────────────────────────────


class TestIFwSsot1:
    """I-FW-SSOT-1: <run_id>.spine.jsonl 唯一 SSOT。"""

    # 文档/注释/兼容引用白名单
    _DOC_ALLOW_SUBSTRINGS: tuple[str, ...] = (
        "lca_kernel/events/",  # SSOT reader / sinks 自身
        "archive/",  # 归档
        str(_THIS_TEST_FILE.name),  # 本测试文件
        "tests/fixtures/",  # 测试 fixture
    )

    def test_i_fw_ssot_1_no_legacy_events_jsonl_writer(self) -> None:
        """events.jsonl legacy writer = 0(open(events.jsonl, "w") 模式)。"""
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            # 匹配 open(...)..., "w" 形式包含 events.jsonl
            for line in _rg(r'open\([^)]*events\.jsonl[^)]*["\']\s*,\s*["\']w["\']', root):
                # 应用白名单
                if _is_excluded(line, self._DOC_ALLOW_SUBSTRINGS):
                    continue
                matches.append(line)
        assert not matches, "I-FW-SSOT-1 违规:events.jsonl writer 仍在生产路径\n" + "\n".join(
            matches[:5]
        )

    def test_i_fw_ssot_1_no_legacy_events_jsonl_reader_in_production(self) -> None:
        """I-FW-SSOT-1:events.jsonl legacy reader 必须迁到 SpineReader。

        PR-4 收口后:本测试 strict 守护,任何生产 / 配置路径出现
        ``events.jsonl`` 字面立即 fail(I-FW-SSOT-1 reader SSOT)。
        """
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
            _REPO_ROOT / "profiles",
            _REPO_ROOT / "bundles",
        ]
        all_matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"events\.jsonl", root):
                if _is_excluded(line, self._DOC_ALLOW_SUBSTRINGS):
                    continue
                all_matches.append(line)
        assert not all_matches, (
            "I-FW-SSOT-1 违规:events.jsonl legacy reader 仍在生产路径\n"
            + "\n".join(all_matches[:5])
        )

    def test_i_fw_ssot_1_spine_jsonl_writer_is_single(self) -> None:
        """lca_kernel/events/sinks/ 唯一写 .write( = spine_sink。"""
        sinks_dir = _REPO_ROOT / "lca_kernel" / "events" / "sinks"
        if not sinks_dir.exists():
            pytest.skip("lca_kernel/events/sinks/ not found")
        write_matches = _rg(r"\.write\(", sinks_dir)
        # 必须全部在 spine_sink.py(框架内唯一 SSOT 写者)
        offenders = [m for m in write_matches if "spine_sink.py" not in m]
        assert not offenders, (
            "I-FW-SSOT-1 违规:lca_kernel/events/sinks/ 内 spine_sink 之外"
            "还有 .write( 调用\n" + "\n".join(offenders[:5])
        )
        # 且 spine_sink.py 内必须有至少一处 .write(
        assert any("spine_sink.py" in m for m in write_matches), (
            "I-FW-SSOT-1 反向断言:lca_kernel/events/sinks/spine_sink.py "
            "缺少 .write( 调用(SpineSink.append 落盘实现异常)"
        )


# ── I-MV-1..5:model-visible 类别单发布者注册表(DSH-GAP-AUDIT G10)─────

_SPINE_YAML = _REPO_ROOT / "lca_kernel" / "events" / "config" / "observability" / "spine.yaml"

# model-visible 类别集合从 spine.yaml 的 payload_class 归属推导,不硬编码
# 类别名;_EXPECTED 反向断言防推导退化为空集。
_MV_PAYLOAD_MODULE = "lca_kernel.events.payloads_model_visible"
_EXPECTED_MV_CATEGORIES = frozenset(
    {"spine.llm.request.header", "spine.llm.request.header.assistant"}
)
# EP 短名经 _SPINE_EP_TO_CATEGORY 派生到 model-visible 类别,等价于类别引用。
_MV_EP_SHORTS = frozenset({"llm.request.header"})
_MV_PAYLOAD_CLASSES = frozenset(
    {"SpineLlmRequestHeaderPayload", "SpineLlmRequestHeaderAssistantPayload"}
)
# 注册发布者代码 = publisher plugin + 其内嵌 hook(setup 时挂到 LLM adapter 链)。
_MV_PUBLISHER_PATHS: tuple[str, ...] = (
    "lca/plugins/events/publishers/model_visible/",
    "lca/plugins/events/hooks/model_visible/",
)


@dataclass(frozen=True)
class _PluginManifestFacts:
    """AST 提取的 @plugin manifest 声明事实(不 import 插件模块)。"""

    path: Path
    plugin_id: str
    marker_class: str | None
    emits: tuple[str, ...]


def _load_spine_specs() -> list[dict]:
    """读 spine.yaml 的 events 规格列表。"""
    import yaml

    data = yaml.safe_load(_SPINE_YAML.read_text(encoding="utf-8"))
    events = data.get("events") if isinstance(data, dict) else None
    assert isinstance(events, list), "spine.yaml 缺少 events 列表,结构异常"
    return [spec for spec in events if isinstance(spec, dict)]


def _model_visible_specs(specs: list[dict]) -> list[dict]:
    """payload_class 归属 payloads_model_visible 模块的类别规格。"""
    return [
        spec
        for spec in specs
        if str(spec.get("payload_class", "")).startswith(_MV_PAYLOAD_MODULE + ".")
    ]


def _mv_publisher_token(mv_specs: list[dict]) -> str:
    """model-visible 类别共享的唯一 publisher token(I-MV-1 断言其唯一)。"""
    tokens: set[str] = set()
    for spec in mv_specs:
        tokens.update(str(t) for t in (spec.get("publishers") or ()))
    assert len(tokens) == 1, f"model-visible 类别的 publisher token 不唯一:{sorted(tokens)}"
    return tokens.pop()


def _iter_py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _scan_plugin_manifests(root: Path) -> list[_PluginManifestFacts]:
    """AST 扫 @plugin 装饰器,提取 id / marker_class / ownership.emits。"""
    out: list[_PluginManifestFacts] = []
    for path in _iter_py_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _callee_name(node) != "plugin":
                continue
            pid = _keyword(node, "id")
            if not isinstance(pid, ast.Constant) or not isinstance(pid.value, str):
                continue
            marker = _keyword(node, "marker_class")
            marker_name = marker.id if isinstance(marker, ast.Name) else None
            emits: list[str] = []
            ownership = _keyword(node, "ownership")
            if isinstance(ownership, ast.Call):
                emits_node = _keyword(ownership, "emits")
                if isinstance(emits_node, (ast.Tuple, ast.List)):
                    emits = [
                        str(element.value)
                        for element in emits_node.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    ]
            out.append(_PluginManifestFacts(path, pid.value, marker_name, tuple(emits)))
    return out


class TestIMvCategoryRegistry:
    """I-MV-1..5:model-visible 类别 → 生产者单发布者注册表(DSH-GAP-AUDIT G10)。

    DSH 原则:类别 → 生产者是单向注册表,同一类别多个发射方 = 硬错误。
    spine.yaml ``publishers`` 注册已实现该语义,本组测试锁现状防回归。
    note 语义面的补充守护(旁路文件 / 认知层直发 / fold 字节判等)见
    tests/architecture/test_i_mv_*.py。
    """

    def test_i_mv_1_single_publisher_per_model_visible_category(self) -> None:
        """I-MV-1:每个 model-visible 类别在 yaml 恰好一个非空 publisher,且同类别不重复注册、两类别同一 token。"""
        specs = _load_spine_specs()
        mv_specs = _model_visible_specs(specs)
        derived = {str(spec["category"]) for spec in mv_specs}
        assert derived == _EXPECTED_MV_CATEGORIES, (
            f"I-MV-1 前提漂移:推导出的 model-visible 类别集 {sorted(derived)} "
            f"≠ 期望 {sorted(_EXPECTED_MV_CATEGORIES)}"
        )
        # 同类别不得重复注册
        counts: dict[str, int] = {}
        for spec in specs:
            category = str(spec.get("category", ""))
            counts[category] = counts.get(category, 0) + 1
        duplicates = [c for c in derived if counts[c] != 1]
        assert not duplicates, f"I-MV-1 违规:类别在 spine.yaml 重复注册:{duplicates}"
        # 每类别恰好一个非空 publisher token
        for spec in mv_specs:
            publishers = [str(t) for t in (spec.get("publishers") or ())]
            assert len(publishers) == 1 and publishers[0].strip(), (
                f"I-MV-1 违规:{spec['category']} publishers={publishers},必须恰好一个非空 token"
            )
        token = _mv_publisher_token(mv_specs)
        assert token, "I-MV-1 违规:model-visible publisher token 为空"

    def test_i_mv_2_publisher_emits_match_yaml_registration(self) -> None:
        """I-MV-2:publisher manifest ``ownership.emits`` ⟺ yaml 授权类别,双向同集。"""
        specs = _load_spine_specs()
        mv_specs = _model_visible_specs(specs)
        token = _mv_publisher_token(mv_specs)
        yaml_categories = {str(spec["category"]) for spec in mv_specs}
        manifests = _scan_plugin_manifests(_REPO_ROOT / "lca" / "plugins")
        matched = [m for m in manifests if m.plugin_id == token]
        assert len(matched) == 1, (
            f"I-MV-2 违规:yaml token {token!r} 对应 {len(matched)} 个 @plugin manifest"
            "(必须恰好 1 个)"
        )
        manifest_emits = set(matched[0].emits)
        assert manifest_emits == yaml_categories, (
            "I-MV-2 违规:manifest emits 与 yaml 授权类别不同集;"
            f"manifest 多出 {sorted(manifest_emits - yaml_categories)},"
            f"yaml 多出 {sorted(yaml_categories - manifest_emits)}"
        )

    # 已知债:InMemoryLoopCursor(ADR-0169 L13 测试替身)在
    # record_request_header 里把 legacy digest 形 ``llm.request.header`` EP
    # 直写自身 WritePort spine(in_memory.py:214),非总线 publish;与
    # TestIFwBus1/2 的 loop_cursor PR-9 债务同族,测试替身对齐总线后删除本条。
    _KNOWN_DEBT_FILES: tuple[str, ...] = (
        "lca/infrastructure/observability/loop_cursor/in_memory.py",
    )

    def test_i_mv_3_no_active_publish_outside_registered_publisher(self) -> None:
        """I-MV-3:注册发布者之外无 model-visible 活跃 publish / payload 构造。

        AST 判定:注释、docstring、死字符串(如 @plugin description 残留)
        不是代码节点,天然不算活跃调用;只有真实构造
        ``SpineLlmRequestHeader*Payload(`` 或 publish 动词
        (publish_via_session / publish / append)实参引用类别字面才判违规。
        """
        literals = _EXPECTED_MV_CATEGORIES | _MV_EP_SHORTS
        publish_verbs = {"publish_via_session", "publish", "append"}
        violations: list[str] = []
        for root in (_REPO_ROOT / "lca", _REPO_ROOT / "lca_kernel"):
            for path in _iter_py_files(root):
                rel = str(path.relative_to(_REPO_ROOT))
                if any(allowed in rel for allowed in _MV_PUBLISHER_PATHS):
                    continue
                if rel.endswith("lca_kernel/events/payloads_model_visible.py"):
                    continue  # payload 类定义本体
                if any(debt in rel for debt in self._KNOWN_DEBT_FILES):
                    continue
                tree = _parse(path)
                if tree is None:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    # (a) payload 类构造 = publish 前置,仅注册发布者可持有
                    if isinstance(node.func, ast.Name) and node.func.id in _MV_PAYLOAD_CLASSES:
                        violations.append(f"{rel}:{node.lineno} 构造 {node.func.id}")
                        continue
                    # (b) publish 动词调用树内出现类别字面(含 EP 短名)
                    if _callee_name(node) in publish_verbs:
                        refs = {
                            str(sub.value)
                            for sub in ast.walk(node)
                            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        } & literals
                        if refs:
                            violations.append(
                                f"{rel}:{node.lineno} {_callee_name(node)}() refs {sorted(refs)}"
                            )
        assert not violations, (
            "I-MV-3 违规:注册发布者之外出现 model-visible 活跃 publish 路径\n"
            + "\n".join(violations[:5])
        )

    def test_i_mv_4_yaml_token_registered_and_producer_is_marker(self) -> None:
        """I-MV-4:授权一致性 —— yaml token = 已注册 @plugin id,且所有 model-visible publish 点 ``producer=`` 恰为该 plugin marker_class。"""
        specs = _load_spine_specs()
        token = _mv_publisher_token(_model_visible_specs(specs))
        manifests = _scan_plugin_manifests(_REPO_ROOT / "lca" / "plugins")
        by_id = {m.plugin_id: m for m in manifests}
        assert token in by_id, (
            f"I-MV-4 违规:yaml publisher token {token!r} 不是任何 @plugin 的 id"
            "(yaml 授权 ⇄ 插件注册 失配)"
        )
        marker = by_id[token].marker_class
        assert marker, f"I-MV-4 违规:@plugin {token!r} 未声明 marker_class"
        # 注册发布者代码内全部 publish 点的 producer= 必须恰为 marker
        producers: set[str] = set()
        for sub in _MV_PUBLISHER_PATHS:
            for path in _iter_py_files(_REPO_ROOT / sub):
                tree = _parse(path)
                if tree is None:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    if _callee_name(node) not in {"publish_via_session", "publish"}:
                        continue
                    producer = _keyword(node, "producer")
                    if isinstance(producer, ast.Name):
                        producers.add(producer.id)
        assert producers == {marker}, (
            "I-MV-4 违规:model-visible publish 点 producer= 集合 "
            f"{sorted(producers)} ≠ yaml 授权 plugin 的 marker {marker!r}"
        )

    def test_i_mv_5_payload_class_typed_and_category_aligned(self) -> None:
        """I-MV-5:每类别 ``payload_class`` 非空、类型化(非 EventPayload 基类),且类 ``category`` 默认值与 yaml 类别一致。"""
        from lca.contracts.event import EventPayload

        specs = _load_spine_specs()
        mv_specs = _model_visible_specs(specs)
        assert mv_specs, "I-MV-5 前提漂移:spine.yaml 无 model-visible 类别"
        for spec in mv_specs:
            category = str(spec["category"])
            class_path = str(spec.get("payload_class") or "")
            module_name, _, class_name = class_path.rpartition(".")
            assert module_name and class_name, (
                f"I-MV-5 违规:{category} payload_class 为空或不可解析:{class_path!r}"
            )
            assert class_name != "EventPayload", (
                f"I-MV-5 违规:{category} payload_class 指向通用基类 EventPayload(未类型化)"
            )
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name, None)
            assert isinstance(cls, type) and issubclass(cls, EventPayload), (
                f"I-MV-5 违规:{class_path} 不存在或不是 EventPayload 子类"
            )
            assert cls is not EventPayload
            default = cls.model_fields["category"].default
            raw = getattr(default, "value", default)
            assert str(raw) == category, (
                f"I-MV-5 违规:{class_path} category 默认值 {str(raw)!r} ≠ yaml 类别 {category!r}"
            )

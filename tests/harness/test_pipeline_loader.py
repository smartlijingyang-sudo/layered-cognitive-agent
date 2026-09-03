"""Pipeline loader 测试 —— ADR-0183 PR-7(Pipeline 装配 + inspect)。

覆盖:
- ``load_profile_pipeline`` 三级发现:内联段 / 显式文件引用 / 约定路径
- ``pipeline_from_mapping`` 与 parse_pipeline_yaml 同语义
- ``register_pipeline_once`` 幂等(同名同版只装载一次)
- ``apply_pipeline``:sink 实例化生命周期 + consumer_rules 经
  bus.subscribe 的接线(鉴权矩阵 SSOT)
- ``inspect-pipeline`` CLI(web-standard)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from lca.harness.profile.pipeline_loader import (
    apply_pipeline,
    load_pipeline_for_profile,
    load_profile_pipeline,
    pipeline_from_mapping,
    register_pipeline_once,
)
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import EventBus, FailureSemantics
from lca_kernel.events.errors import UnauthorizedSubscribeError
from lca_kernel.events.hooks import DefaultFailureHook, PayloadSchemaHook
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.pipeline import HookSpec, Pipeline, Stage
from lca_kernel.events.registry import EventRegistry
from lca_kernel.events.sinks.spine_sink import SpineSink, SpineSinkClosedError
from lca_kernel.events.spine_runtime import SpineEventRecord

REPO_ROOT_PROFILE = Path("profiles/web-standard.yaml")

_DEMO_PIPELINE: dict[str, object] = {
    "pipeline": {
        "name": "demo-pipeline",
        "version": 2,
        "hooks": [
            {
                "id": "payload-schema-validation",
                "hook": "lca_kernel.events.hooks.PayloadSchemaHook",
                "stage": "pre_dispatch",
                "config": {"fail_fast_on_missing_field": True},
            },
            {
                "id": "consumers-failure-default",
                "hook": "lca_kernel.events.hooks.DefaultFailureHook",
                "stage": "on_failure",
            },
        ],
        "sinks": [
            {
                "id": "spine-fact-chain",
                "backend": "lca_kernel.events.sinks.spine_sink.SpineSink",
                "failure": "fail_fast",
                "config": {"path_template": "{run_id}.spine.jsonl"},
            }
        ],
        "consumer_rules": [
            {
                "prefix": "spine.",
                "plugins": ["lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink"],
                "failure": "fail_fast",
            }
        ],
        "options": {"schema_validation": "strict"},
    }
}


def _write_yaml(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _make_bus() -> EventBus:
    """独立 EventBus(默认鉴权矩阵),避免单例串扰。"""
    from lca_kernel.events.test_catalog import build_test_bus
    return build_test_bus()


def _authorized_producer() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


# ── 三级发现 ─────────────────────────────────────────────────────────────


class TestDiscovery:
    def test_convention_path(self, tmp_path: Path) -> None:
        """无显式声明时走 <profile 目录>/event-pipeline/<stem>.yaml。"""
        profile = _write_yaml(tmp_path / "profiles" / "demo.yaml", {"bundles": []})
        _write_yaml(tmp_path / "profiles" / "event-pipeline" / "demo.yaml", _DEMO_PIPELINE)

        bundle = load_profile_pipeline(profile)
        assert bundle is not None
        assert bundle.pipeline.name == "demo-pipeline"
        assert bundle.pipeline.version == 2
        assert bundle.source == str(tmp_path / "profiles" / "event-pipeline" / "demo.yaml")
        assert len(bundle.pipeline.hooks) == 2
        assert bundle.pipeline.hooks[0].hook is PayloadSchemaHook
        assert bundle.pipeline.sinks[0].backend is SpineSink
        assert bundle.pipeline.sinks[0].failure is FailureSemantics.FAIL_FAST
        assert bundle.options["schema_validation"] == "strict"

    def test_inline_section(self, tmp_path: Path) -> None:
        """profile 内联 pipeline: mapping 段。"""
        profile = _write_yaml(tmp_path / "inline.yaml", _DEMO_PIPELINE | {"bundles": []})

        bundle = load_profile_pipeline(profile)
        assert bundle is not None
        assert bundle.pipeline.name == "demo-pipeline"
        assert bundle.source == f"{profile}#pipeline"
        assert bundle.options["schema_validation"] == "strict"

    def test_string_reference(self, tmp_path: Path) -> None:
        """pipeline: <path> 显式引用,相对 profile 目录解析。"""
        ref = _write_yaml(tmp_path / "cfg" / "custom-pipeline.yaml", _DEMO_PIPELINE)
        profile = _write_yaml(tmp_path / "demo.yaml", {"pipeline": "cfg/custom-pipeline.yaml"})

        bundle = load_profile_pipeline(profile)
        assert bundle is not None
        assert bundle.source == str(ref)
        assert bundle.pipeline.name == "demo-pipeline"

    def test_string_reference_missing_raises(self, tmp_path: Path) -> None:
        """显式声明的文件不存在 → fail-closed。"""
        profile = _write_yaml(tmp_path / "demo.yaml", {"pipeline": "cfg/missing.yaml"})
        with pytest.raises(FileNotFoundError, match=r"missing\.yaml"):
            load_profile_pipeline(profile)

    def test_none_when_absent(self, tmp_path: Path) -> None:
        profile = _write_yaml(tmp_path / "plain.yaml", {"bundles": []})
        assert load_profile_pipeline(profile) is None
        assert load_pipeline_for_profile(profile) is None

    def test_missing_profile_file_returns_none(self, tmp_path: Path) -> None:
        assert load_pipeline_for_profile(tmp_path / "nope.yaml") is None

    def test_resolved_profile_input(self) -> None:
        """ResolvedProfile 输入走同一发现链。"""
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile(REPO_ROOT_PROFILE)
        pipeline = load_pipeline_for_profile(resolved)
        assert pipeline is not None
        assert pipeline.name == "web-standard-event-pipeline"

    def test_pipeline_from_mapping_name_fallback(self) -> None:
        pipeline = pipeline_from_mapping({"hooks": []}, name_fallback="fallback")
        assert pipeline.name == "fallback"
        assert pipeline.hooks == ()


# ── 仓库内 web-standard pipeline yaml ────────────────────────────────────


class TestWebStandardPipeline:
    def test_sections_match_adr(self) -> None:
        bundle = load_profile_pipeline(REPO_ROOT_PROFILE)
        assert bundle is not None
        pipeline = bundle.pipeline

        hooks_by_id = {spec.id: spec for spec in pipeline.hooks}
        schema_hook = hooks_by_id["payload-schema-validation"]
        assert schema_hook.hook is PayloadSchemaHook
        assert schema_hook.stage is Stage.PRE_DISPATCH
        failure_hook = hooks_by_id["consumers-failure-default"]
        assert failure_hook.hook is DefaultFailureHook
        assert failure_hook.stage is Stage.ON_FAILURE

        sink = pipeline.sinks[0]
        assert sink.id == "spine-fact-chain"
        assert sink.backend is SpineSink
        assert sink.failure is FailureSemantics.FAIL_FAST
        assert sink.config["path_template"] == "{run_id}.spine.jsonl"

        rule = pipeline.consumer_rules[0]
        assert rule.prefix == "spine."
        from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink

        assert SpineChainSink in rule.plugins

        assert bundle.options  # options 段存在且非空

    def test_hooks_are_noarg_constructible(self) -> None:
        """register_pipeline 走 spec.hook() 无参实例化,yaml 必须满足。"""
        pipeline = load_pipeline_for_profile(REPO_ROOT_PROFILE)
        assert pipeline is not None
        for spec in pipeline.hooks:
            spec.hook()


# ── register_pipeline_once + apply_pipeline ──────────────────────────────


class TestRegisterAndApply:
    def test_register_once_idempotent(self) -> None:
        """同名同版重复装载跳过:hook 只跑一次。"""
        calls: list[object] = []

        class _RecordingPreHook:
            def before_publish(self, payload, _producer, _ctx):
                calls.append(payload)
                return payload

        bus = _make_bus()
        pipeline = Pipeline(
            name="idem",
            hooks=(HookSpec(id="rec", hook=_RecordingPreHook, stage=Stage.PRE_DISPATCH),),
        )
        assert register_pipeline_once(bus, pipeline) is True
        assert register_pipeline_once(bus, pipeline) is False

        bus.publish(
            TeamDelegationCacheHit(callee_role="a", subtask="b", step=1),
            producer=_authorized_producer(),
        )
        assert len(calls) == 1

    def test_apply_pipeline_instantiates_sinks(self, tmp_path: Path) -> None:
        """sink 按 config 实例化;run_id 绑定前不可 append。"""
        template = str(tmp_path / "{run_id}.spine.jsonl")
        pipeline = Pipeline(
            name="sink-apply",
            sinks=(_sink_spec(template),),
        )
        applied = apply_pipeline(_make_bus(), pipeline)
        sink = applied.sinks["spine-fact-chain"]
        assert isinstance(sink, SpineSink)

        record = SpineEventRecord(
            event_id="evt-1",
            category="spine.kernel.run.start",
            execution_point="ep",
            channel="spine",
            payload={"run_id": "run-x"},
            ts="1970-01-01T00:00:00Z",
        )
        with pytest.raises(SpineSinkClosedError):
            sink.append(record)

        sink.set_run_id("run-x")
        sink.append(record)
        sink.close()
        lines = (tmp_path / "run-x.spine.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["event_id"] == "evt-1"

    def test_apply_pipeline_wires_consumer_rules(self, capsys: pytest.CaptureFixture[str]) -> None:
        """team. 前缀规则经 subscribe 接线:publish 命中插件回调。"""
        from lca.plugins.events.subscribers.console_projector.subscriber import (
            ConsoleProjectorSubscriber,
        )
        from lca_kernel.events.pipeline import ConsumerRule

        pipeline = Pipeline(
            name="rules-apply",
            consumer_rules=(
                ConsumerRule(
                    prefix="team.",
                    plugins=(ConsoleProjectorSubscriber,),
                    failure=FailureSemantics.CONTAINED,
                ),
            ),
        )
        applied = apply_pipeline(_make_bus(), pipeline)
        assert applied.consumer_handles  # 至少订阅了授权矩阵内的 team.* category

        bus = _make_bus()
        applied = apply_pipeline(bus, pipeline)
        bus.publish(
            TeamDelegationCacheHit(callee_role="cache", subtask="s", step=1),
            producer=_authorized_producer(),
        )
        assert "幂等短路" in capsys.readouterr().out
        assert applied.consumer_handles

    def test_apply_pipeline_unauthorized_plugin_raises(self) -> None:
        """规则插件在鉴权矩阵零授权 → 上抛(不静默跳过)。"""
        from lca_kernel.events.pipeline import ConsumerRule

        pipeline = Pipeline(
            name="bad-rule",
            consumer_rules=(ConsumerRule(prefix="spine.", plugins=(_authorized_producer(),)),),
        )
        with pytest.raises(UnauthorizedSubscribeError):
            apply_pipeline(_make_bus(), pipeline)


def _sink_spec(template: str):
    from lca_kernel.events.pipeline import SinkSpec

    return SinkSpec(
        id="spine-fact-chain",
        backend=SpineSink,
        failure=FailureSemantics.FAIL_FAST,
        config={"path_template": template},
    )


# ── inspect-pipeline CLI ─────────────────────────────────────────────────


class TestInspectPipelineCli:
    def test_web_standard_text(self) -> None:
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        result = CliRunner().invoke(app, ["inspect-pipeline", "web-standard"])
        assert result.exit_code == 0, result.output
        assert "web-standard-event-pipeline" in result.output
        for section in ("hooks (", "sinks (", "consumer_rules (", "options ("):
            assert section in result.output
        assert "spine-fact-chain" in result.output

    def test_web_standard_json(self) -> None:
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        result = CliRunner().invoke(app, ["inspect-pipeline", "web-standard", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert {"hooks", "sinks", "consumer_rules", "options"} <= set(data)
        assert data["sinks"][0]["backend"] == "lca_kernel.events.sinks.spine_sink.SpineSink"

    def test_missing_profile_reports_not_found(self) -> None:
        # tests/conftest.py 全局 monkeypatch 掉 sys.exit(K6 shutdown 语义),
        # CliRunner 下拿不到真实退出码;断言可见输出。直接进程运行
        # `lca-ops inspect-pipeline <missing>` 退出码为 1(手工验证)。
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        result = CliRunner().invoke(app, ["inspect-pipeline", "no-such-profile"])
        assert "Profile not found: no-such-profile" in result.output

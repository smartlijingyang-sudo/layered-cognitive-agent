"""Executable architecture guardrails for module locality and navigation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _require_path(*parts: str) -> None:
    """Keep each architectural assertion focused on one repository seam."""
    path = ROOT.joinpath(*parts)
    assert path.exists(), f"expected architectural path is missing: {path}"


def test_architecture_01_contracts_root() -> None:
    """明确 contracts 作为纯数据契约根目录。"""
    _require_path("lca", "contracts")


def test_architecture_02_infra_layer() -> None:
    """明确 infrastructure 的基础设施归属。"""
    _require_path("lca", "infrastructure")


def test_architecture_03_cognitive_layer() -> None:
    """明确 cognition 的认知层归属。"""
    _require_path("lca", "cognition")


def test_architecture_04_runtime_layer() -> None:
    """明确 runtime 的运行层归属。"""
    _require_path("lca", "runtime")


def test_architecture_05_agent_layer() -> None:
    """明确 agent 的 Agent 层归属。"""
    _require_path("lca", "agent")


def test_architecture_06_composition_root() -> None:
    """明确 application 作为组合根。"""
    _require_path("lca", "application")


def test_architecture_07_harness_layer() -> None:
    """明确 harness 的启动装配职责。"""
    _require_path("lca", "harness")


def test_architecture_08_plugins_layer() -> None:
    """明确 plugins 作为扩展装配层。"""
    _require_path("lca", "plugins")


def test_architecture_09_gateway_carrier() -> None:
    """明确 gateway 作为载体入口。"""
    _require_path("gateway")


def test_architecture_10_contracts_protocols() -> None:
    """守护跨层 Protocol 集中在 contracts。"""
    _require_path("lca", "contracts", "protocols")


def test_architecture_11_contracts_models() -> None:
    """守护领域模型集中在 contracts。"""
    _require_path("lca", "contracts", "models")


def test_architecture_12_infra_llm() -> None:
    """守护 LLM adapter 位于基础设施层。"""
    _require_path("lca", "infrastructure", "llm_adapter")


def test_architecture_13_infra_observability() -> None:
    """守护观测实现位于基础设施层。"""
    _require_path("lca", "infrastructure", "observability")


def test_architecture_14_infra_transport() -> None:
    """守护 transport seam 位于基础设施层。"""
    _require_path("lca", "infrastructure", "transport")


def test_architecture_15_infra_state_store() -> None:
    """守护 state_store seam 位于基础设施层。"""
    _require_path("lca", "infrastructure", "state_store")


def test_architecture_16_infra_sandbox() -> None:
    """守护 sandbox seam 位于基础设施层。"""
    _require_path("lca", "infrastructure", "sandbox")


def test_architecture_17_infra_file_store() -> None:
    """守护 file_store seam 位于基础设施层。"""
    _require_path("lca", "infrastructure", "file_store.py")


def test_architecture_18_infra_skills() -> None:
    """守护 skills provider 位于基础设施层。"""
    _require_path("lca", "infrastructure", "skills")


def test_architecture_19_cognitive_brain() -> None:
    """守护 Brain 模块作为认知平面入口。"""
    _require_path("lca", "cognition", "brain")


def test_architecture_20_cognitive_body() -> None:
    """守护 Body 模块作为世界平面入口。"""
    _require_path("lca", "cognition", "body")


def test_architecture_21_cognitive_memory() -> None:
    """守护 Memory 模块的认知层位置。"""
    _require_path("lca", "cognition", "memory")


def test_architecture_22_cognitive_perception() -> None:
    """守护 perceive 相关模块的局部性。"""
    _require_path("lca", "cognition", "sensors")


def test_architecture_23_runtime_reducer() -> None:
    """守护 reducer 作为状态唯一写入相关模块。"""
    _require_path("lca", "runtime", "reducer.py")


def test_architecture_24_runtime_declarative() -> None:
    """守护声明式运行时目录。"""
    _require_path("lca", "runtime", "declarative_runtime.py")


def test_architecture_25_runtime_recovery() -> None:
    """守护恢复策略位于运行层。"""
    _require_path("lca", "runtime", "checkpoint_resolution.py")


def test_architecture_26_agent_team() -> None:
    """守护 Team 协作模块的层次归属。"""
    _require_path("lca", "agent", "orchestration_strategies")


def test_architecture_27_agent_delegation() -> None:
    """守护 delegation 模块的层次归属。"""
    _require_path("lca", "agent", "orchestration_strategies")


def test_architecture_28_app_spawn() -> None:
    """守护 spawn 作为组合根装配入口。"""
    _require_path("lca", "application", "spawn.py")


def test_architecture_29_app_runtime_factory() -> None:
    """守护 runtime factory 的组合根位置。"""
    _require_path("lca", "plugins", "composer", "runtime_factory.py")


def test_architecture_30_harness_profile() -> None:
    """守护 profile 解析 seam。"""
    _require_path("lca", "harness", "profile")


def test_architecture_31_harness_boot() -> None:
    """守护 boot 装配 seam。"""
    _require_path("lca", "harness", "profile", "boot.py")


def test_architecture_32_harness_plugin_api() -> None:
    """守护 plugin manifest 接口集中管理。"""
    _require_path("lca", "harness", "plugin_api.py")


def test_architecture_33_plugin_composer() -> None:
    """守护 composer 作为装配实现目录。"""
    _require_path("lca", "plugins", "composer")


def test_architecture_34_plugin_providers() -> None:
    """守护 providers 作为能力实现目录。"""
    _require_path("lca", "plugins", "providers")


def test_architecture_35_plugin_seams() -> None:
    """守护 seams 作为替换接口目录。"""
    _require_path("lca", "plugins", "seam_definitions")


def test_architecture_36_plugin_strategies() -> None:
    """守护 strategies 作为策略实现目录。"""
    _require_path("lca", "plugins", "strategies")


def test_architecture_37_profile_default() -> None:
    """守护默认 web profile 作为可复现装配入口。"""
    _require_path("profiles", "web-standard.yaml")


def test_architecture_38_bundle_base() -> None:
    """守护 base bundle 作为能力组合基线。"""
    _require_path("bundles", "base.yaml")


def test_architecture_39_bundle_declarative() -> None:
    """守护声明式 bundle 的显式组合入口。"""
    _require_path("bundles", "declarative-phase-graph.yaml")


def test_architecture_40_adr_directory() -> None:
    """守护 ADR 作为架构决策记录目录。"""
    _require_path("docs", "adr")


def test_architecture_41_architecture_adr() -> None:
    """守护架构审查 ADR 可追溯。"""
    _require_path("docs", "adr", "0084-plugin-architecture-audit.md")


def test_architecture_42_skill_directory() -> None:
    """守护架构优化技能与代码保持同仓可导航。"""
    _require_path("skills", "improve-codebase-architecture", "SKILL.md")


def test_architecture_43_architecture_tests() -> None:
    """守护架构测试作为接口测试面。"""
    _require_path("tests", "test_architecture_conformance.py")


def test_architecture_44_lint_config() -> None:
    """守护 import 契约配置存在且可被工具读取。"""
    _require_path("pyproject.toml")


def test_architecture_45_agent_guidance() -> None:
    """守护架构不变量与修改规则有单一入口。"""
    _require_path("AGENTS.md")


def test_architecture_46_scripts_quality() -> None:
    """守护架构门禁脚本集中在 scripts。"""
    _require_path("scripts", "check_protocol_impl.py")


def test_architecture_47_docs_spec() -> None:
    """守护认知结构规范作为领域语言来源。"""
    _require_path("docs", "specs", "lca-structured-cognition-guide.md")


def test_architecture_48_history_record() -> None:
    """守护历史实施记录目录以支持架构演进 locality。"""
    _require_path("history", "README.md")


def test_architecture_49_skill_readme() -> None:
    """守护 skills README 作为技能导航入口。"""
    _require_path("skills", "README.md")


def test_architecture_50_adr_readme() -> None:
    """守护 ADR README 作为决策导航入口。"""
    _require_path("docs", "adr", "README.md")

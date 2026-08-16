"""Capability Seam 三角色约束测试。

验证 DSH-inspired 的 Seam 模式：
- 每个 seam 必须有 Definition / Provider / Consumer 三个角色
- SeamRegistry 正确跟踪角色分配
- 完整性校验能检测缺失角色
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from lca.contracts.mechanisms import (
    SeamRegistry,
    SeamRole,
    get_global_seam_registry,
    register_seam,
    seam,
    validate_all_seams,
)


class TestSeamRole:
    """测试 SeamRole 枚举。"""

    def test_three_roles_exist(self) -> None:
        """必须有且仅有三个角色。"""
        assert SeamRole.DEFINITION.value == "definition"
        assert SeamRole.PROVIDER.value == "provider"
        assert SeamRole.CONSUMER.value == "consumer"
        assert len(SeamRole) == 3


class TestSeamRegistry:
    """测试 SeamRegistry 注册和校验。"""

    def test_empty_registry_not_complete(self) -> None:
        """空注册表不完整。"""
        registry = SeamRegistry()
        assert not registry.is_complete("nonexistent")

    def test_single_role_not_complete(self) -> None:
        """只有单个角色不完整。"""
        registry = SeamRegistry()

        @runtime_checkable
        class ShellProtocol(Protocol):
            pass

        registry.register(ShellProtocol, "shell", SeamRole.DEFINITION)
        assert not registry.is_complete("shell")
        assert registry.get_missing_roles("shell") == [SeamRole.PROVIDER, SeamRole.CONSUMER]

    def test_two_roles_not_complete(self) -> None:
        """只有两个角色不完整。"""
        registry = SeamRegistry()

        @runtime_checkable
        class ShellProtocol(Protocol):
            pass

        class BashLocal:
            pass

        registry.register(ShellProtocol, "shell", SeamRole.DEFINITION)
        registry.register(BashLocal, "shell", SeamRole.PROVIDER)
        assert not registry.is_complete("shell")
        assert registry.get_missing_roles("shell") == [SeamRole.CONSUMER]

    def test_three_roles_complete(self) -> None:
        """三个角色齐全则完整。"""
        registry = SeamRegistry()

        @runtime_checkable
        class ShellProtocol(Protocol):
            pass

        class BashLocal:
            pass

        class ToolBash:
            def __init__(self, shell: ShellProtocol) -> None:
                self.shell = shell

        registry.register(ShellProtocol, "shell", SeamRole.DEFINITION)
        registry.register(BashLocal, "shell", SeamRole.PROVIDER)
        registry.register(ToolBash, "shell", SeamRole.CONSUMER)
        assert registry.is_complete("shell")
        assert registry.get_missing_roles("shell") == []

    def test_multiple_providers_allowed(self) -> None:
        """一个 seam 可以有多个 Provider。"""
        registry = SeamRegistry()

        @runtime_checkable
        class SandboxProtocol(Protocol):
            pass

        class DockerSandbox:
            pass

        class PodmanSandbox:
            pass

        class CodeExecutor:
            def __init__(self, sandbox: SandboxProtocol) -> None:
                self.sandbox = sandbox

        registry.register(SandboxProtocol, "sandbox", SeamRole.DEFINITION)
        registry.register(DockerSandbox, "sandbox", SeamRole.PROVIDER)
        registry.register(PodmanSandbox, "sandbox", SeamRole.PROVIDER)
        registry.register(CodeExecutor, "sandbox", SeamRole.CONSUMER)
        assert registry.is_complete("sandbox")
        assert len(registry.get_roles("sandbox")[SeamRole.PROVIDER]) == 2

    def test_get_seams(self) -> None:
        """能列出所有已注册的 seam。"""
        registry = SeamRegistry()

        @runtime_checkable
        class A(Protocol):
            pass

        @runtime_checkable
        class B(Protocol):
            pass

        registry.register(A, "seam_a", SeamRole.DEFINITION)
        registry.register(B, "seam_b", SeamRole.DEFINITION)
        seams = registry.get_seams()
        assert "seam_a" in seams
        assert "seam_b" in seams


class TestSeamDecorator:
    """测试 @seam 装饰器语法。"""

    def test_decorator_attaches_metadata(self) -> None:
        """装饰器正确附加 seam 元数据。"""

        @seam("shell", SeamRole.DEFINITION)
        @runtime_checkable
        class ShellProtocol(Protocol):
            pass

        assert ShellProtocol.__seam_name__ == "shell"  # type: ignore[attr-defined]
        assert ShellProtocol.__seam_role__ == SeamRole.DEFINITION  # type: ignore[attr-defined]

    def test_decorator_on_provider(self) -> None:
        """装饰器可用于 Provider。"""

        @seam("shell", SeamRole.PROVIDER)
        class BashLocal:
            pass

        assert BashLocal.__seam_name__ == "shell"  # type: ignore[attr-defined]
        assert BashLocal.__seam_role__ == SeamRole.PROVIDER  # type: ignore[attr-defined]


class TestGlobalRegistry:
    """测试全局 seam 注册表。"""

    def test_global_registry_singleton(self) -> None:
        """全局注册表是单例。"""
        registry1 = get_global_seam_registry()
        registry2 = get_global_seam_registry()
        assert registry1 is registry2

    def test_register_seam_function(self) -> None:
        """register_seam 函数正确注册到全局。"""
        registry = get_global_seam_registry()

        @runtime_checkable
        class TestProtocol(Protocol):
            pass

        register_seam(TestProtocol, "test_seam", SeamRole.DEFINITION)
        assert "test_seam" in registry.get_seams()


class TestRealWorldSeam:
    """测试真实 LCA seam 示例（使用 mock 类演示模式）。"""

    def test_llm_adapter_seam_pattern(self) -> None:
        """LLMAdapter seam 演示：Definition + Provider + Consumer。"""
        from lca.contracts.protocols.infra import LLMAdapter

        registry = SeamRegistry()
        registry.register(LLMAdapter, "llm", SeamRole.DEFINITION)

        # Mock Provider
        class MockLLMProvider:
            async def complete(self, messages: list[dict[str, str]]) -> str:
                return "mock response"

            async def stream(self, messages: list[dict[str, str]]):
                yield "mock chunk"

        registry.register(MockLLMProvider, "llm", SeamRole.PROVIDER)

        # Mock Consumer
        class MockBrain:
            def __init__(self, llm: LLMAdapter) -> None:
                self.llm = llm

        registry.register(MockBrain, "llm", SeamRole.CONSUMER)
        assert registry.is_complete("llm")

    def test_tool_seam_pattern(self) -> None:
        """Tool seam 演示：Definition + Provider + Consumer。"""
        from lca.contracts.protocols.infra import Tool

        registry = SeamRegistry()
        registry.register(Tool, "tool", SeamRole.DEFINITION)

        # Mock Provider
        class MockToolRegistry:
            def __init__(self) -> None:
                self._tools: dict[str, Tool] = {}

            def register(self, tool: Tool) -> None:
                self._tools[tool.name] = tool

            def get(self, name: str) -> Tool | None:
                return self._tools.get(name)

        registry.register(MockToolRegistry, "tool", SeamRole.PROVIDER)

        # Mock Consumer
        class MockBody:
            def __init__(self, tools: MockToolRegistry) -> None:
                self.tools = tools

        registry.register(MockBody, "tool", SeamRole.CONSUMER)
        assert registry.is_complete("tool")


class TestValidateAllSeams:
    """测试 validate_all_seams 函数。"""

    def test_validate_returns_incomplete_seams(self) -> None:
        """validate_all_seams 返回不完整的 seam 列表。"""

        @runtime_checkable
        class IncompleteProtocol(Protocol):
            pass

        register_seam(IncompleteProtocol, "incomplete_seam", SeamRole.DEFINITION)

        incomplete = validate_all_seams()
        assert "incomplete_seam" in incomplete


class TestConsumeGate:
    """consume() 是组合期门：校验消费权，原样返回 provider。"""

    def test_registered_consumer_receives_provider(self) -> None:
        from lca.contracts.mechanisms import consume

        registry = SeamRegistry()

        class Shell:
            def run(self) -> str:
                return "ok"

        class ToolBash:
            pass

        registry.register(object, "shell", SeamRole.DEFINITION)
        registry.register(Shell, "shell", SeamRole.PROVIDER)
        registry.register(ToolBash, "shell", SeamRole.CONSUMER)
        provider = Shell()
        assert consume("shell", provider, ToolBash, registry=registry) is provider

    def test_unregistered_consumer_rejected(self) -> None:
        from lca.contracts.mechanisms import UnauthorizedConsumerError, consume

        registry = SeamRegistry()

        class Shell:
            pass

        class ToolBash:
            pass

        class Stranger:
            pass

        registry.register(object, "shell", SeamRole.DEFINITION)
        registry.register(Shell, "shell", SeamRole.PROVIDER)
        registry.register(ToolBash, "shell", SeamRole.CONSUMER)
        with pytest.raises(UnauthorizedConsumerError, match="Stranger"):
            consume("shell", Shell(), Stranger, registry=registry)

    def test_unarmed_catalog_is_passthrough(self) -> None:
        from lca.contracts.mechanisms import consume

        registry = SeamRegistry()
        provider = object()
        assert consume("unarmed", provider, object, registry=registry) is provider

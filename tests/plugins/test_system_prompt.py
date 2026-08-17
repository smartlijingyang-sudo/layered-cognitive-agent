"""Tests for the system-prompt plugin (composable prompt assembly)."""

from __future__ import annotations

import pytest

from lca.plugins.system_prompt import (
    AssembleContext,
    PromptContext,
    PromptSection,
    SystemPromptService,
)

# ── Section registration & ordering ───────────────────────────────────


class TestSectionRegistration:
    def test_register_and_assemble(self) -> None:
        svc = SystemPromptService()
        svc.section("persona", 0, "You are a helpful assistant.")
        svc.section("identity", -100, "System: LCA")

        assembly = svc.assemble()
        assert len(assembly.sections) == 2

    def test_render_orders_by_order_field(self) -> None:
        svc = SystemPromptService()
        svc.section("tools", 100, "Available tools: ...")
        svc.section("persona", 0, "You are helpful.")
        svc.section("identity", -100, "System: LCA")

        assembly = svc.assemble()
        rendered = svc.render(assembly)

        lines = rendered.split("\n\n")
        assert lines[0] == "System: LCA"
        assert lines[1] == "You are helpful."
        assert lines[2] == "Available tools: ..."

    def test_same_order_sections(self) -> None:
        svc = SystemPromptService()
        svc.section("a", 0, "First")
        svc.section("b", 0, "Second")

        rendered = svc.render(svc.assemble())
        assert "First" in rendered
        assert "Second" in rendered


# ── Variable interpolation ────────────────────────────────────────────


class TestVariableInterpolation:
    def test_basic_interpolation(self) -> None:
        svc = SystemPromptService()
        svc.section("greeting", 0, "Hello {{name}}, welcome to {{place}}.")
        svc.variable("name", lambda: "Alice")
        svc.variable("place", lambda: "Wonderland")

        rendered = svc.render(svc.assemble())
        assert rendered == "Hello Alice, welcome to Wonderland."

    def test_unknown_variable_raises(self) -> None:
        svc = SystemPromptService()
        svc.section("greeting", 0, "Hello {{unknown}}.")

        with pytest.raises(ValueError, match="Unknown prompt variable"):
            svc.render(svc.assemble())

    def test_no_variables_no_interpolation(self) -> None:
        svc = SystemPromptService()
        svc.section("plain", 0, "No variables here.")

        rendered = svc.render(svc.assemble())
        assert rendered == "No variables here."


# ── Empty sections dropped ────────────────────────────────────────────


class TestEmptySections:
    def test_empty_string_section_dropped(self) -> None:
        svc = SystemPromptService()
        svc.section("empty", 0, "")
        svc.section("real", 10, "Content")

        rendered = svc.render(svc.assemble())
        assert rendered == "Content"

    def test_whitespace_only_section_dropped(self) -> None:
        svc = SystemPromptService()
        svc.section("ws", 0, "   \n  ")
        svc.section("real", 10, "Content")

        rendered = svc.render(svc.assemble())
        assert rendered == "Content"

    def test_callable_returning_empty_dropped(self) -> None:
        svc = SystemPromptService()
        svc.section("dyn_empty", 0, lambda ctx: "")
        svc.section("dyn_real", 10, lambda ctx: "Dynamic content")

        rendered = svc.render(svc.assemble())
        assert rendered == "Dynamic content"


# ── Context registration ─────────────────────────────────────────────


class TestContextRegistration:
    def test_context_in_assembly(self) -> None:
        svc = SystemPromptService()
        svc.context("memory", 50, "Recent memories: ...")

        assembly = svc.assemble()
        assert len(assembly.contexts) == 1
        assert assembly.contexts[0].name == "memory"

    def test_context_rendered_with_sections(self) -> None:
        svc = SystemPromptService()
        svc.section("persona", 0, "You are helpful.")
        svc.context("memory", 50, "Recent: ...")

        rendered = svc.render(svc.assemble())
        parts = rendered.split("\n\n")
        assert parts[0] == "You are helpful."
        assert parts[1] == "Recent: ..."

    def test_context_with_callable(self) -> None:
        svc = SystemPromptService()
        svc.context("dynamic", 0, lambda ctx: f"Got {ctx.values.get('x', '?')}")

        assembly = svc.assemble()
        # render creates its own empty AssembleContext for callable resolution,
        # but contexts that use callables with AssembleContext still work
        # since render passes an empty one
        rendered = svc.render(assembly)
        assert "Got ?" in rendered


# ── Render output ─────────────────────────────────────────────────────


class TestRender:
    def test_join_with_double_newline(self) -> None:
        svc = SystemPromptService()
        svc.section("a", 0, "Block A")
        svc.section("b", 10, "Block B")
        svc.section("c", 20, "Block C")

        rendered = svc.render(svc.assemble())
        assert rendered == "Block A\n\nBlock B\n\nBlock C"

    def test_sections_and_contexts_interleaved_by_order(self) -> None:
        svc = SystemPromptService()
        svc.section("identity", -100, "ID")
        svc.context("background", -50, "BG")
        svc.section("tools", 100, "TOOLS")

        rendered = svc.render(svc.assemble())
        parts = rendered.split("\n\n")
        assert parts == ["ID", "BG", "TOOLS"]

    def test_variable_interpolation_in_context(self) -> None:
        svc = SystemPromptService()
        svc.context("info", 0, "Name: {{name}}")
        svc.variable("name", lambda: "Bob")

        rendered = svc.render(svc.assemble())
        assert rendered == "Name: Bob"


# ── Disposer ──────────────────────────────────────────────────────────


class TestDisposer:
    def test_section_disposer_removes_section(self) -> None:
        svc = SystemPromptService()
        dispose = svc.section("temp", 0, "Temporary")

        assert len(svc.assemble().sections) == 1
        dispose()
        assert len(svc.assemble().sections) == 0

    def test_context_disposer_removes_context(self) -> None:
        svc = SystemPromptService()
        dispose = svc.context("temp", 0, "Temporary")

        assert len(svc.assemble().contexts) == 1
        dispose()
        assert len(svc.assemble().contexts) == 0

    def test_variable_disposer_removes_variable(self) -> None:
        svc = SystemPromptService()
        svc.section("g", 0, "Hi {{name}}")
        dispose = svc.variable("name", lambda: "Alice")

        rendered = svc.render(svc.assemble())
        assert rendered == "Hi Alice"

        dispose()
        with pytest.raises(ValueError, match="Unknown prompt variable"):
            svc.render(svc.assemble())

    def test_hook_disposer_removes_hook(self) -> None:
        svc = SystemPromptService()
        called = []

        def hook(ctx: AssembleContext, assembly: object) -> None:
            called.append(True)

        dispose = svc.on_assemble(hook)
        svc.assemble()
        assert len(called) == 1

        dispose()
        svc.assemble()
        assert len(called) == 1  # not called again


# ── Assemble hooks ────────────────────────────────────────────────────


class TestAssembleHooks:
    def test_waterfall_hook_modifies_assembly(self) -> None:
        svc = SystemPromptService()
        svc.section("base", 0, "Base content")

        def inject_extra(ctx: AssembleContext, assembly: object) -> None:
            assembly.sections.append(  # type: ignore[attr-defined]
                PromptSection(name="injected", order=10, text="Injected!"),
            )

        svc.on_assemble(inject_extra)

        rendered = svc.render(svc.assemble())
        parts = rendered.split("\n\n")
        assert parts == ["Base content", "Injected!"]

    def test_hook_receives_context(self) -> None:
        svc = SystemPromptService()
        received: list[AssembleContext] = []

        def hook(ctx: AssembleContext, assembly: object) -> None:
            received.append(ctx)

        svc.on_assemble(hook)
        ac = AssembleContext(values={"role": "assistant"})
        svc.assemble(ctx=ac)

        assert len(received) == 1
        assert received[0].values["role"] == "assistant"

    def test_multiple_hooks_run_in_order(self) -> None:
        svc = SystemPromptService()
        order: list[int] = []

        svc.on_assemble(lambda ctx, asm: order.append(1))
        svc.on_assemble(lambda ctx, asm: order.append(2))
        svc.on_assemble(lambda ctx, asm: order.append(3))

        svc.assemble()
        assert order == [1, 2, 3]


# ── Data type sanity ─────────────────────────────────────────────────


class TestDataTypes:
    def test_prompt_section_frozen(self) -> None:
        s = PromptSection(name="x", order=0, text="hi")
        with pytest.raises(AttributeError):
            s.name = "y"  # type: ignore[misc]

    def test_prompt_context_frozen(self) -> None:
        c = PromptContext(name="x", order=0, text="hi")
        with pytest.raises(AttributeError):
            c.name = "y"  # type: ignore[misc]

    def test_assemble_context_default_empty(self) -> None:
        ac = AssembleContext()
        assert ac.values == {}

    def test_assemble_context_with_values(self) -> None:
        ac = AssembleContext(values={"key": "val"})
        assert ac.values["key"] == "val"

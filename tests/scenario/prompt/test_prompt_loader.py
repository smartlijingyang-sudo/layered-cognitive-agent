"""Unit tests for load_builtin_prompt() prompt template loader."""

from __future__ import annotations

import unittest

from lca.cognition.brain.prompts import load_builtin_prompt


class TestLoadBuiltinPrompt(unittest.TestCase):
    """Tests for the built-in prompt template loader."""

    def test_load_react_prompt(self) -> None:
        """react_prompt.md loads and contains expected placeholders."""
        content = load_builtin_prompt("react_prompt")
        self.assertIn("{role}", content)
        self.assertIn("{goal}", content)
        self.assertIn("{task}", content)
        self.assertIn("{context}", content)
        self.assertIn("function calling", content)

    def test_load_hierarchical_prompt(self) -> None:
        """hierarchical_prompt.md loads and contains expected placeholders."""
        content = load_builtin_prompt("hierarchical_prompt")
        self.assertIn("{role}", content)
        self.assertIn("{teammates}", content)
        self.assertIn("{member_status_text}", content)
        self.assertIn("function calling", content)
        self.assertIn("target_role", content)

    def test_nonexistent_prompt_raises_clear_error(self) -> None:
        """Requesting a nonexistent prompt raises FileNotFoundError with available templates."""
        with self.assertRaises(FileNotFoundError) as ctx:
            load_builtin_prompt("nonexistent_prompt_xyz")
        error_msg = str(ctx.exception)
        self.assertIn("nonexistent_prompt_xyz", error_msg)
        self.assertIn("Available templates", error_msg)


if __name__ == "__main__":
    unittest.main()

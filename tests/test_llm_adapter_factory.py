"""Unit tests for LLM Adapter factory (resolve_llm_adapter + load_dotenv_if_present)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lca.layer0_infra.llm_adapter.factory import (
    load_dotenv_if_present,
    resolve_llm_adapter,
)

_HAS_OPENAI = importlib.util.find_spec("openai") is not None
_HAS_DOTENV = importlib.util.find_spec("dotenv") is not None


class TestResolveLLMAdapter(unittest.TestCase):
    """Tests for resolve_llm_adapter()."""

    def test_returns_mock_when_no_api_key(self) -> None:
        """Without LLM_API_KEY, returns MockLLMAdapter."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_API_KEY", None)
            adapter = resolve_llm_adapter()
        self.assertEqual(adapter.name, "mock-llm")

    @unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
    def test_returns_openai_compat_when_api_key_set(self) -> None:
        """With LLM_API_KEY env var, returns OpenAICompatAdapter."""
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test-fake-key"}, clear=False):
            adapter = resolve_llm_adapter()
        self.assertEqual(adapter.name, "openai-compat")

    @unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
    def test_explicit_api_key_overrides_env(self) -> None:
        """Explicit api_key parameter takes precedence over env var."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_API_KEY", None)
            adapter = resolve_llm_adapter(api_key="sk-explicit-key")
        self.assertEqual(adapter.name, "openai-compat")

    def test_explicit_none_key_falls_back_to_mock(self) -> None:
        """When no key is available at all, falls back to Mock."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_API_KEY", None)
            adapter = resolve_llm_adapter(api_key=None)
        self.assertEqual(adapter.name, "mock-llm")

    def test_resolve_without_openai_returns_mock(self) -> None:
        """Even if openai is missing, no-Key path always returns Mock (no crash)."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_API_KEY", None)
            adapter = resolve_llm_adapter()
        # Must be mock, and must not have tried to import openai
        self.assertEqual(adapter.name, "mock-llm")


class TestLoadDotenvIfPresent(unittest.TestCase):
    """Tests for load_dotenv_if_present()."""

    def test_explicit_path_that_does_not_exist_no_error(self) -> None:
        """Explicit non-existent path does not raise."""
        load_dotenv_if_present(path="/nonexistent/path/.env")

    def test_no_dotenv_in_any_parent_no_error(self) -> None:
        """When no .env exists in parent dirs, silently skips."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "subdir"
            cwd.mkdir()
            with mock.patch("pathlib.Path.cwd", return_value=cwd):
                load_dotenv_if_present()

    @unittest.skipUnless(_HAS_DOTENV, "python-dotenv not installed")
    def test_loads_dotenv_from_current_dir(self) -> None:
        """When .env exists in CWD, it gets loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_DOTENV_VAR=hello_from_dotenv\n")
            with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                load_dotenv_if_present()
            self.assertEqual(os.environ.get("TEST_DOTENV_VAR"), "hello_from_dotenv")
            # Cleanup
            os.environ.pop("TEST_DOTENV_VAR", None)


if __name__ == "__main__":
    unittest.main()

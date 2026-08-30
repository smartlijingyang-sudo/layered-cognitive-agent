"""Unit tests for LLM Adapter factory (resolve_llm_adapter + load_dotenv_if_present)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lca.infrastructure.llm.openai_client import LLMUnavailableError
from lca.infrastructure.llm_adapter.factory import (
    load_dotenv_if_present,
    resolve_llm_adapter,
)

_HAS_OPENAI = importlib.util.find_spec("openai") is not None
_HAS_DOTENV = importlib.util.find_spec("dotenv") is not None


class TestResolveLLMAdapter(unittest.TestCase):
    """Tests for resolve_llm_adapter()."""

    def test_raises_when_no_api_key(self) -> None:
        with (
            mock.patch(
                "lca.infrastructure.llm.config.prepare_llm_environ",
                lambda: None,
            ),
            mock.patch.dict(os.environ, {}, clear=True),
            self.assertRaises(LLMUnavailableError),
        ):
            resolve_llm_adapter()

    @unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
    def test_returns_openai_compat_when_api_key_set(self) -> None:
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test-fake-key"}, clear=False):
            adapter = resolve_llm_adapter()
        self.assertEqual(adapter.name, "openai-compat")

    @unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
    def test_explicit_api_key_overrides_env(self) -> None:
        with (
            mock.patch(
                "lca.infrastructure.llm.config.prepare_llm_environ",
                lambda: None,
            ),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            adapter = resolve_llm_adapter(api_key="sk-explicit-key")
        self.assertEqual(adapter.name, "openai-compat")

    def test_explicit_none_key_raises(self) -> None:
        with (
            mock.patch(
                "lca.infrastructure.llm.config.prepare_llm_environ",
                lambda: None,
            ),
            mock.patch.dict(os.environ, {}, clear=True),
            self.assertRaises(LLMUnavailableError),
        ):
            resolve_llm_adapter(api_key=None)

    @unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
    def test_api_param_forwarded_to_openai_compat(self) -> None:
        from lca.infrastructure.llm_adapter.api_style import LLMApiStyle

        with (
            mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test-fake-key"}, clear=False),
            mock.patch(
                "lca.infrastructure.llm_adapter.openai_compat.OpenAICompatAdapter"
            ) as mock_cls,
        ):
            mock_cls.return_value.name = "openai-compat"
            resolve_llm_adapter(api=LLMApiStyle.RESPONSES)
        mock_cls.assert_called_once()
        self.assertEqual(mock_cls.call_args.kwargs.get("api"), LLMApiStyle.RESPONSES)


class TestLoadDotenvIfPresent(unittest.TestCase):
    """Tests for load_dotenv_if_present()."""

    def test_explicit_path_that_does_not_exist_no_error(self) -> None:
        load_dotenv_if_present(path="/nonexistent/path/.env")

    def test_no_dotenv_in_any_parent_no_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "subdir"
            cwd.mkdir()
            with mock.patch("pathlib.Path.cwd", return_value=cwd):
                load_dotenv_if_present()

    @unittest.skipUnless(_HAS_DOTENV, "python-dotenv not installed")
    def test_loads_dotenv_from_current_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_DOTENV_VAR=hello_from_dotenv\n")
            with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                load_dotenv_if_present()
            self.assertEqual(os.environ.get("TEST_DOTENV_VAR"), "hello_from_dotenv")
            os.environ.pop("TEST_DOTENV_VAR", None)


if __name__ == "__main__":
    unittest.main()

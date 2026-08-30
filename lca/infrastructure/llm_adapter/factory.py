"""LLM Adapter 工厂 —— 环境变量驱动的 LLM 选择 + .env 加载。

生产路径请用插件 ``lca-llm-resolver``。本模块供脚本 / 库调用：
  1. ``prepare_llm_environ``（dotenv + 别名）后读 ``LLM_*``
  2. 有 Key → ``OpenAICompatAdapter``
  3. 无 Key → ``LLMUnavailableError``（不再静默 Mock）
"""

from __future__ import annotations

import logging
from pathlib import Path

from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.llm_adapter.api_style import LLMApiStyle

logger = logging.getLogger(__name__)


def load_dotenv_if_present(path: str | None = None) -> None:
    """加载 .env 文件到环境变量。

    Args:
        path: 显式指定 .env 路径。为 None 时从当前工作目录向上寻找最近的 .env。
              找不到则静默跳过（不报错），保证在无 .env 的环境中也能正常运行。
    """
    if path is not None:
        _load_dotenv_file(Path(path))
        return

    # 从 CWD 向上寻找最近的 .env
    current = Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            _load_dotenv_file(candidate)
            return


def _load_dotenv_file(path: Path) -> None:
    """尝试用 python-dotenv 加载指定路径；若未安装则静默跳过。"""
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        logger.info("Loaded environment from %s", path)
    except ImportError:
        logger.debug("python-dotenv not installed; skipping %s", path)


def resolve_llm_adapter(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api: LLMApiStyle | None = None,
) -> LLMAdapter:
    """根据环境变量解析 LLM Adapter 实例。

    优先级：显式参数 > ``prepare_llm_environ`` 后的环境变量。
    无 Key 时抛 ``LLMUnavailableError``（不再静默降级 Mock）。

    Prefer the booted ``llm_resolver`` capability in process; this helper is
    for scripts / tests that are outside the plugin tree.
    """
    from lca.infrastructure.llm.config import DEFAULT_CHAT_MODEL, load_provider_settings
    from lca.infrastructure.llm.openai_client import LLMUnavailableError

    settings = load_provider_settings()
    endpoint = settings.agent_endpoint()
    resolved_key = api_key if api_key is not None else (endpoint.api_key or None)
    resolved_base = base_url if base_url is not None else endpoint.base_url
    resolved_model = model if model is not None else (endpoint.model or DEFAULT_CHAT_MODEL)

    if not resolved_key:
        raise LLMUnavailableError("LLM_API_KEY 未配置，无法解析 LLM adapter")

    from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter

    return OpenAICompatAdapter(
        model=resolved_model,
        api_key=resolved_key,
        base_url=resolved_base,
        api=api,
    )

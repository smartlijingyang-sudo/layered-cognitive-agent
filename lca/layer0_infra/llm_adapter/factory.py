"""LLM Adapter 工厂 —— 环境变量驱动的 LLM 选择 + .env 加载。

设计目标：
  1. 任何 demo / 测试 / 用户代码只需一行 ``resolve_llm_adapter()`` 即可获得可用 LLM。
  2. 有 ``LLM_API_KEY`` 环境变量 → 返回 ``OpenAICompatAdapter``（真实网络调用）。
  3. 无 Key → 返回 ``MockLLMAdapter``（离线确定性，零成本）。
  4. ``load_dotenv_if_present()`` 从 CWD 向上寻找最近的 ``.env`` 文件，
     不再硬编码任何开发者本机路径。
"""

from __future__ import annotations

import logging
from pathlib import Path

from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle

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

    优先级：显式参数 > 环境变量 > 降级到 Mock。

    Args:
        api_key: 显式 API Key（覆盖 ``LLM_API_KEY`` 环境变量）。
        base_url: 显式 Base URL（覆盖 ``LLM_BASE_URL`` 环境变量）。
        model: 显式模型名（覆盖 ``LLM_MODEL`` 环境变量）。

    Returns:
        ``OpenAICompatAdapter``（有 Key 时）或 ``MockLLMAdapter``（无 Key 时）。
    """
    from lca.layer0_infra.llm.config import LLMProviderSettings

    endpoint = LLMProviderSettings().agent_endpoint()
    resolved_key = api_key if api_key is not None else (endpoint.api_key or None)
    resolved_base = base_url if base_url is not None else endpoint.base_url
    resolved_model = model if model is not None else (endpoint.model or None)

    if resolved_key:
        from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

        return OpenAICompatAdapter(
            model=resolved_model,
            api_key=resolved_key,
            base_url=resolved_base,
            api=api,
        )

    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

    logger.info("No LLM_API_KEY found; falling back to MockLLMAdapter")
    return MockLLMAdapter()

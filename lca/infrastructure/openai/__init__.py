"""Public exports for ``openai`` (auto-fixed)."""

from lca.infrastructure.openai.openai_compat import (
    StructuredLLMError,
    normalize_chat_role,
    normalize_chat_messages,
    normalize_responses_input,
    extract_json_schema_format,
    resolve_upstream_model,
    resolve_embedding_model,
    create_embeddings,
    create_simple_completion,
    create_structured_completion,
    build_responses_payload,
)

__all__ = ['StructuredLLMError', 'normalize_chat_role', 'normalize_chat_messages', 'normalize_responses_input', 'extract_json_schema_format', 'resolve_upstream_model', 'resolve_embedding_model', 'create_embeddings', 'create_simple_completion', 'create_structured_completion', 'build_responses_payload']

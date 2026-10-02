"""Public exports for ``openai`` (auto-fixed)."""

from lca.infrastructure.openai.compat import (
    StructuredLLMError,
    build_responses_payload,
    create_embeddings,
    create_simple_completion,
    create_structured_completion,
    extract_json_schema_format,
    normalize_chat_messages,
    normalize_chat_role,
    normalize_responses_input,
    resolve_embedding_model,
    resolve_upstream_model,
)

__all__ = ['StructuredLLMError', 'build_responses_payload', 'create_embeddings', 'create_simple_completion', 'create_structured_completion', 'extract_json_schema_format', 'normalize_chat_messages', 'normalize_chat_role', 'normalize_responses_input', 'resolve_embedding_model', 'resolve_upstream_model']

"""OpenAPI 3.0.3 builder for the LCA gateway HTTP surface.

Walks the live Starlette route table and emits a machine-readable API
reference for frontend consumers. Every registered HTTP route is listed
with its methods and handler-derived operationId/summary. The core run
and assistant paths carry hand-curated response schemas; all other paths
get a generic 200 response so the document stays valid without per-path
schema annotations.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS

_OPENAPI_VERSION = "3.0.3"

_INFO: dict[str, Any] = {
    "title": "LCA Agent Gateway API",
    "description": (
        "LCA 认知智能体 HTTP API。受保护端点需要两个请求头："
        "``Authorization: Bearer <token>`` 和 ``x-lca-user-id``。"
        "实时 run 事件走 WebSocket ``/v1/runs/{run_id}/ws``，"
        "协议见 docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md。"
    ),
    "version": "1.0.0",
}

_SECURITY_SCHEMES: dict[str, Any] = {
    "BearerAuth": {"type": "http", "scheme": "bearer"},
    "UserIdHeader": {"type": "apiKey", "in": "header", "name": "x-lca-user-id"},
}

_SECURITY: list[dict[str, list[str]]] = [{"BearerAuth": [], "UserIdHeader": []}]

_SCHEMAS: dict[str, Any] = {
    "Error": {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "type": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["code", "type"],
            }
        },
        "required": ["error"],
    },
    "RunReceipt": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "agent": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
            },
            "live_url": {"type": "string"},
            "ws_token": {"type": "string"},
        },
        "required": ["run_id", "trace_id", "agent", "live_url", "ws_token"],
    },
    "Run": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "status": {"type": "string"},
            "session_status": {"type": "string"},
            "mode": {"type": "string"},
            "agent": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
            },
            "question": {"type": "string"},
            "output": {"type": "string"},
            "error": {"type": "string"},
            "approval_request": {"type": "object"},
            "steps": {"type": "array", "items": {"type": "object"}},
        },
    },
    "Assistant": {
        "type": "object",
        "properties": {
            "assistant_id": {"type": "string"},
            "home_path": {"type": "string"},
            "revision_seq": {"type": "integer"},
            "template_id": {"type": "string"},
            "status": {"type": "string"},
            "profile": {"type": "object"},
            "agent_id": {"type": ["string", "null"]},
        },
    },
}

_DEFAULT_RESPONSES: dict[str, Any] = {
    "200": {"description": "OK"},
}

_CORE_RESPONSES: dict[str, dict[str, Any]] = {
    "/runs": {
        "post": {
            "202": {
                "description": "Run accepted",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/RunReceipt"}}
                },
            },
            "400": {
                "description": "Invalid request",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "503": {
                "description": "Gateway stream unavailable",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
        },
    },
    "/runs/{run_id}": {
        "get": {
            "200": {
                "description": "Run summary",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Run"}}},
            },
            "404": {
                "description": "Run not found",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
        },
    },
    "/v1/assistants": {
        "post": {
            "201": {
                "description": "Assistant created",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/Assistant"}}
                },
            },
            "400": {
                "description": "Invalid request",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
        },
        "get": {
            "200": {
                "description": "Assistant list",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "assistants": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Assistant"},
                                }
                            },
                        }
                    }
                },
            },
        },
    },
}


def _operation_id_for(route: Route, method: str) -> str:
    name = getattr(route.endpoint, "__name__", "handler")
    return f"{method.lower()}_{name}"


def _summary_for(route: Route) -> str:
    doc = getattr(route.endpoint, "__doc__", "") or ""
    first_line = doc.strip().splitlines()[0] if doc.strip() else ""
    return first_line.strip()[:160] or f"handler {route.endpoint.__name__}"


def _responses_for(path: str, method: str) -> dict[str, Any]:
    return _CORE_RESPONSES.get(path, {}).get(method.lower(), _DEFAULT_RESPONSES)


def build_openapi_spec(routes: Iterable[Route]) -> dict[str, Any]:
    """Build an OpenAPI 3.0.3 document from the live Starlette route table."""
    paths: dict[str, Any] = {}
    for route in routes:
        if not isinstance(route, Route):
            continue
        for method in route.methods:
            if method in {"OPTIONS", "HEAD"}:
                continue
            operation = {
                "operationId": _operation_id_for(route, method),
                "summary": _summary_for(route),
                "responses": _responses_for(route.path, method),
            }
            paths.setdefault(route.path, {})[method.lower()] = operation

    return {
        "openapi": _OPENAPI_VERSION,
        "info": _INFO,
        "paths": paths,
        "components": {"securitySchemes": _SECURITY_SCHEMES, "schemas": _SCHEMAS},
        "security": _SECURITY,
    }


async def openapi_json(request: Request) -> JSONResponse:
    """``GET /v1/openapi.json`` — serve the gateway OpenAPI document."""
    app = getattr(request, "app", None)
    router = getattr(app, "router", None) if app is not None else None
    routes = getattr(router, "routes", []) if router is not None else []
    return JSONResponse(build_openapi_spec(routes), headers=CORS_HEADERS)


__all__ = ["build_openapi_spec", "openapi_json"]

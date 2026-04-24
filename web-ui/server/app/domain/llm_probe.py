"""Connection probes for RayMe-owned and OpenAI-compatible endpoints."""

from __future__ import annotations

from typing import Literal

import httpx

CONNECTED = "Connected"
UNREACHABLE = "Unreachable"
UNAUTHORIZED = "Unauthorized"
NOT_CONFIGURED = "Not configured"

ConnectionStatus = Literal["Connected", "Unreachable", "Unauthorized", "Not configured"]
CONNECTION_STATUSES: tuple[ConnectionStatus, ...] = (
    CONNECTED,
    UNREACHABLE,
    UNAUTHORIZED,
    NOT_CONFIGURED,
)


def _is_configured(*values: str | None) -> bool:
    return all(value is not None and value.strip() for value in values)


def _join_endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def health_url(base_url: str) -> str:
    return _join_endpoint(base_url, "/health")


def chat_completions_url(base_url: str) -> str:
    return _join_endpoint(base_url, "/chat/completions")


async def probe_http_health(
    base_url: str | None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> ConnectionStatus:
    """Probe a RayMe-owned `/health` endpoint without leaking response details."""

    if not _is_configured(base_url):
        return NOT_CONFIGURED

    if http_client is not None:
        return await _probe_http_health_with_client(base_url or "", http_client)

    async with httpx.AsyncClient(timeout=5.0) as client:
        return await _probe_http_health_with_client(base_url or "", client)


async def _probe_http_health_with_client(
    base_url: str,
    client: httpx.AsyncClient,
) -> ConnectionStatus:
    try:
        response = await client.get(health_url(base_url))
    except httpx.HTTPError:
        return UNREACHABLE

    return _status_from_response(response)


async def probe_openai_compatible_llm(
    *,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    http_client: httpx.AsyncClient | None = None,
) -> ConnectionStatus:
    """Probe an OpenAI-compatible Chat Completions endpoint server-side."""

    if not _is_configured(base_url, model):
        return NOT_CONFIGURED

    if http_client is not None:
        return await _probe_openai_compatible_llm_with_client(
            base_url=base_url or "",
            api_key=api_key,
            model=model or "",
            client=http_client,
        )

    async with httpx.AsyncClient(timeout=5.0) as client:
        return await _probe_openai_compatible_llm_with_client(
            base_url=base_url or "",
            api_key=api_key,
            model=model or "",
            client=client,
        )


async def _probe_openai_compatible_llm_with_client(
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    client: httpx.AsyncClient,
) -> ConnectionStatus:
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        response = await client.post(
            chat_completions_url(base_url),
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            },
        )
    except httpx.HTTPError:
        return UNREACHABLE

    return _status_from_response(response)


def _status_from_response(response: httpx.Response) -> ConnectionStatus:
    if response.status_code in {401, 403}:
        return UNAUTHORIZED
    if 200 <= response.status_code < 300:
        return CONNECTED
    return UNREACHABLE


__all__ = [
    "CONNECTED",
    "CONNECTION_STATUSES",
    "NOT_CONFIGURED",
    "UNAUTHORIZED",
    "UNREACHABLE",
    "ConnectionStatus",
    "chat_completions_url",
    "health_url",
    "probe_http_health",
    "probe_openai_compatible_llm",
]

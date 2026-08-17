from __future__ import annotations

from typing import Any, Protocol
import httpx


class RouterAdmin(Protocol):
    async def register(self, *, base_url: str, api_key: str, model: str, ttl_seconds: int,
                       supports_tools: bool, max_completion_tokens: int) -> str: ...
    async def usage(self, route_token: str) -> dict[str, Any] | None: ...
    async def revoke(self, route_token: str) -> None: ...


class TargetClient(Protocol):
    async def turn(self, *, sandbox_id: str, route_token: str, provider_model: str,
                   supports_tools: bool, max_completion_tokens: int,
                   conversation_id: str, message: str,
                   artifacts: list[dict[str, Any]]) -> dict[str, Any]: ...
    async def close_sandbox(self, sandbox_id: str) -> None: ...


class HttpRouterAdmin:
    def __init__(self, base_url: str, admin_token: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.client = client or httpx.AsyncClient(timeout=30)
        self._owns_client = client is None

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Router-Admin-Token": self.admin_token}

    async def register(self, **kwargs) -> str:
        resp = await self.client.post(f"{self.base_url}/internal/routes", headers=self._headers, json=kwargs)
        resp.raise_for_status()
        return resp.json()["route_token"]

    async def usage(self, route_token: str) -> dict[str, Any] | None:
        resp = await self.client.get(f"{self.base_url}/internal/routes/{route_token}/usage", headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def revoke(self, route_token: str) -> None:
        resp = await self.client.delete(f"{self.base_url}/internal/routes/{route_token}", headers=self._headers)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()


class HttpTargetClient:
    def __init__(self, base_url: str, access_token: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.client = client or httpx.AsyncClient(timeout=900)
        self._owns_client = client is None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def turn(self, *, sandbox_id: str, route_token: str, provider_model: str,
                   supports_tools: bool, max_completion_tokens: int,
                   conversation_id: str, message: str,
                   artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        resp = await self.client.post(
            f"{self.base_url}/internal/validation/turn",
            headers=self._headers,
            json={
                "sandbox_id": sandbox_id,
                "route_token": route_token,
                "provider_model": provider_model,
                "supports_tools": supports_tools,
                "max_completion_tokens": max_completion_tokens,
                "conversation_id": conversation_id,
                "message": message,
                "artifacts": artifacts,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def close_sandbox(self, sandbox_id: str) -> None:
        resp = await self.client.delete(
            f"{self.base_url}/internal/validation/sandboxes/{sandbox_id}",
            headers=self._headers,
        )
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

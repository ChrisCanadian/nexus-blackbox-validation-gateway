from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class SandboxRecord:
    sandbox_id: str
    route_token: str
    provider_model: str
    supports_tools: bool
    max_completion_tokens: int
    expires_at: datetime
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)


class SandboxStore:
    def __init__(self) -> None:
        self._items: dict[str, SandboxRecord] = {}

    def create(self, route_token: str, provider_model: str, ttl_seconds: int,
               *, supports_tools: bool, max_completion_tokens: int) -> SandboxRecord:
        sandbox_id = "sbx_" + secrets.token_urlsafe(18)
        rec = SandboxRecord(
            sandbox_id=sandbox_id,
            route_token=route_token,
            provider_model=provider_model,
            supports_tools=supports_tools,
            max_completion_tokens=max_completion_tokens,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self._items[sandbox_id] = rec
        return rec

    def get(self, sandbox_id: str) -> SandboxRecord | None:
        rec = self._items.get(sandbox_id)
        if rec is None:
            return None
        if rec.expires_at <= datetime.now(timezone.utc):
            self._items.pop(sandbox_id, None)
            return None
        return rec

    def delete(self, sandbox_id: str) -> SandboxRecord | None:
        return self._items.pop(sandbox_id, None)

    def active_count(self) -> int:
        expired = [key for key, rec in self._items.items() if rec.expires_at <= datetime.now(timezone.utc)]
        for key in expired:
            self._items.pop(key, None)
        return len(self._items)


class RunStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def put(self, run_id: str, envelope: dict[str, Any]) -> None:
        self._items[run_id] = envelope

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self._items.get(run_id)

from __future__ import annotations

import httpx
import pytest

from nexus_blackbox_gateway.app import create_app


class FakeRouterAdmin:
    def __init__(self):
        self.registered = []
        self.revoked = []

    async def register(self, **kwargs):
        self.registered.append(kwargs)
        return "route-secret-token"

    async def usage(self, route_token):
        assert route_token == "route-secret-token"
        return {"model": "model-a", "request_count": 1, "last_upstream_status": 200}

    async def revoke(self, route_token):
        self.revoked.append(route_token)


class FakeTarget:
    def __init__(self):
        self.closed = []

    async def turn(self, *, sandbox_id, route_token, provider_model, supports_tools,
                   max_completion_tokens, conversation_id, message, artifacts):
        assert route_token == "route-secret-token"
        assert provider_model == "model-a"
        assert supports_tools is True
        assert max_completion_tokens == 8192
        return {
            "response": f"opaque:{conversation_id}:{message}",
            "target_label": "synthetic-private-target",
            "metadata": {
                "artifact_count": len(artifacts),
                "synthetic_tenant": True,
                "private_user_id": 18,
                "ssr_prompt": "must-never-cross",
            },
        }

    async def close_sandbox(self, sandbox_id):
        self.closed.append(sandbox_id)


@pytest.mark.asyncio
async def test_gateway_end_to_end_and_never_returns_provider_key():
    router = FakeRouterAdmin()
    target = FakeTarget()
    app = create_app(router_admin=router, target_client=target)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        created = await client.post("/v1/sandboxes", json={
            "provider": {
                "base_url": "https://provider.example/v1",
                "api_key": "sk-user-secret",
                "model": "model-a",
                "supports_tools": True,
            }
        })
        assert created.status_code == 200
        sandbox_id = created.json()["sandbox_id"]
        assert "sk-user-secret" not in created.text

        artifact = await client.post(f"/v1/sandboxes/{sandbox_id}/artifacts", json={
            "artifact_type": "mode-card.v1",
            "artifact": {
                "name": "Auditor",
                "description": "Careful reviewer",
                "role": "Review",
                "instructions": ["Check claims"],
                "communication_style": ["concise"],
                "boundaries": ["do not invent"],
                "conversation_starters": ["What should I review?"],
            },
        })
        assert artifact.status_code == 200

        turn = await client.post(f"/v1/sandboxes/{sandbox_id}/turns", json={"message": "hello", "conversation_id": "alpha"})
        assert turn.status_code == 200
        body = turn.json()
        assert body["response"] == "opaque:alpha:hello"
        assert body["provider_route_observed"] is True
        assert "route-secret-token" not in turn.text
        assert "sk-user-secret" not in turn.text

        run = await client.get(f"/v1/runs/{body['run_id']}")
        assert run.status_code == 200
        assert run.json()["provider_model"] == "model-a"
        assert run.json()["conversation_id"] == "alpha"
        assert run.json()["provider_route_observed"] is True
        assert run.json()["provider_request_count"] == 1
        assert run.json()["metadata"]["artifact_count"] == 1
        assert run.json()["metadata"]["synthetic_tenant"] is True
        assert "private_user_id" not in run.json()["metadata"]
        assert "ssr_prompt" not in run.json()["metadata"]
        assert "must-never-cross" not in run.text
        assert "sk-user-secret" not in run.text

        deleted = await client.delete(f"/v1/sandboxes/{sandbox_id}")
        assert deleted.status_code == 204
        assert router.revoked == ["route-secret-token"]
        assert target.closed == [sandbox_id]


@pytest.mark.asyncio
async def test_gateway_token_gate_and_kill_switch(monkeypatch):
    monkeypatch.setenv("VALIDATION_GATEWAY_TOKEN", "gate-secret")
    app = create_app(router_admin=FakeRouterAdmin(), target_client=FakeTarget())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        body = {"provider": {"base_url": "https://provider.example/v1", "api_key": "k", "model": "m"}}
        denied = await client.post("/v1/sandboxes", json=body)
        assert denied.status_code == 401
        allowed = await client.post("/v1/sandboxes", headers={"Authorization": "Bearer gate-secret"}, json=body)
        assert allowed.status_code == 200

    monkeypatch.setenv("VALIDATION_ENABLED", "false")
    monkeypatch.delenv("VALIDATION_GATEWAY_TOKEN", raising=False)
    disabled_app = create_app(router_admin=FakeRouterAdmin(), target_client=FakeTarget())
    disabled_transport = httpx.ASGITransport(app=disabled_app)
    async with httpx.AsyncClient(transport=disabled_transport, base_url="http://gateway") as client:
        disabled = await client.post("/v1/sandboxes", json=body)
        assert disabled.status_code == 503

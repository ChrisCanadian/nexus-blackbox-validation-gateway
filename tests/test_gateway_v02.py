import httpx
import pytest

from nexus_blackbox_gateway.app import create_app


class Router:
    async def register(self, **kwargs): return "route-secret-token"
    async def usage(self, route_token): return {"model": "m", "request_count": 2, "last_upstream_status": 200}
    async def revoke(self, route_token): pass


class Target:
    async def turn(self, **kwargs):
        return {
            "response": "OK",
            "target_label": "opaque",
            "metadata": {
                "synthetic_tenant": True,
                "artifact_count": 0,
                "private_user_id": 18,
                "ssr_prompt": "must-never-cross",
            },
        }
    async def close_sandbox(self, sandbox_id): pass


@pytest.mark.asyncio
async def test_gateway_observes_provider_and_firewalls_private_target_metadata():
    app = create_app(router_admin=Router(), target_client=Target())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
        created = await client.post("/v1/sandboxes", json={
            "provider": {"base_url": "https://provider.example/v1", "api_key": "key-secret", "model": "m"}
        })
        sandbox = created.json()["sandbox_id"]
        turn = await client.post(f"/v1/sandboxes/{sandbox}/turns", json={"message": "hello", "conversation_id": "a"})
        assert turn.json()["provider_route_observed"] is True
        run = await client.get(f"/v1/runs/{turn.json()['run_id']}")
        body = run.json()
        assert body["provider_request_count"] == 2
        assert body["metadata"] == {"synthetic_tenant": True, "artifact_count": 0}
        assert "must-never-cross" not in run.text
        assert "key-secret" not in run.text
        assert "route-secret-token" not in run.text

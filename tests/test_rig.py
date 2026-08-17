from __future__ import annotations

import httpx
import pytest

from nexus_blackbox_gateway.app import create_app
from nexus_blackbox_gateway.rig import run_challenge


class FakeRouter:
    async def register(self, **kwargs):
        return "route-token-123456789"
    async def usage(self, route_token):
        return {"model": "m", "request_count": 1, "last_upstream_status": 200}
    async def revoke(self, route_token):
        pass


class FakeTarget:
    async def turn(self, **kwargs):
        return {"response": "VALIDATION_OK", "target_label": "opaque-test", "metadata": {}}
    async def close_sandbox(self, sandbox_id):
        pass


@pytest.mark.asyncio
async def test_challenge_rig_executes_spec_and_assertions():
    app = create_app(router_admin=FakeRouter(), target_client=FakeTarget())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        spec = {
            "name": "smoke",
            "provider": {"base_url": "https://provider.example/v1", "model": "m"},
            "steps": [{
                "name": "exact-token",
                "message": "say it",
                "conversation_id": "smoke",
                "assertions": [{"type": "equals", "value": "VALIDATION_OK"}],
            }],
        }
        result = await run_challenge(spec, gateway_url="http://gateway", api_key="secret", client=client)
        assert result["passed"] is True
        assert result["verdicts"][0]["passed"] is True

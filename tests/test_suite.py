from __future__ import annotations

import re
import httpx
import pytest

from nexus_blackbox_gateway.app import create_app
from nexus_blackbox_gateway.suite import run_builtin_suite


class SuiteRouter:
    def __init__(self):
        self.n = 0
    async def register(self, **kwargs):
        self.n += 1
        return f"route-token-{self.n:02d}-abcdefghijklmnop"
    async def usage(self, route_token):
        return {"model": "model-a", "request_count": 1, "last_upstream_status": 200}
    async def revoke(self, route_token):
        pass


class StatefulTarget:
    def __init__(self):
        self.state = {}
    async def close_sandbox(self, sandbox_id):
        self.state.pop(sandbox_id, None)
    async def turn(self, *, sandbox_id, route_token, provider_model, supports_tools,
                   max_completion_tokens, conversation_id, message, artifacts):
        st = self.state.setdefault(sandbox_id, {"nonce": None, "marker": None, "private": None})
        if "Remember this exact validation nonce:" in message:
            st["nonce"] = re.search(r"NXCONT-[A-F0-9]+", message).group(0); text = "ACK"
        elif "exact validation nonce" in message:
            text = st["nonce"] or "NONE"
        elif "my current marker is NXOLD-" in message:
            st["marker"] = re.search(r"NXOLD-[A-F0-9]+", message).group(0); text = "ACK"
        elif message.startswith("Correction:"):
            st["marker"] = re.search(r"NXNEW-[A-F0-9]+", message).group(0); text = "CORRECTED"
        elif "current validation marker" in message:
            text = st["marker"] or "NONE"
        elif "Store this private validation token" in message:
            st["private"] = re.search(r"NXISO-[A-F0-9]+", message).group(0); text = "ACK"
        elif "another validation user" in message:
            text = "NONE"
        elif "2 + 2" in message:
            text = "MODECARD_OK: 4" if artifacts else "4"
        elif "ROUTE_OK" in message:
            text = "ROUTE_OK"
        else:
            text = "EVIDENCE_OK"
        return {"response": text, "target_label": "opaque-test-target", "metadata": {"synthetic_tenant": True}}


@pytest.mark.asyncio
async def test_builtin_suite_exercises_all_core_cases():
    app = create_app(router_admin=SuiteRouter(), target_client=StatefulTarget())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
        result = await run_builtin_suite(
            gateway_url="http://gateway",
            provider={"base_url": "https://provider.example/v1", "model": "model-a", "supports_tools": True},
            api_key="temporary-evaluator-secret",
            client=client,
        )
    assert result["passed"] is True
    assert result["summary"] == {"total": 7, "passed": 7, "failed": 0, "critical_failures": 0}

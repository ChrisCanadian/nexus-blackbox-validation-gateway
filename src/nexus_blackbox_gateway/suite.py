from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
from dataclasses import dataclass, asdict
from typing import Any

import httpx


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    severity: str
    detail: str
    run_ids: list[str]


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _create_sandbox(client: httpx.AsyncClient, base: str, headers: dict[str, str],
                          provider: dict[str, Any], api_key: str) -> str:
    body_provider = dict(provider)
    body_provider["api_key"] = api_key
    resp = await client.post(f"{base}/v1/sandboxes", headers=headers, json={"provider": body_provider, "ttl_seconds": 1200})
    resp.raise_for_status()
    return resp.json()["sandbox_id"]


async def _turn(client: httpx.AsyncClient, base: str, headers: dict[str, str], sandbox: str,
                message: str, conversation_id: str = "default") -> dict[str, Any]:
    resp = await client.post(
        f"{base}/v1/sandboxes/{sandbox}/turns",
        headers=headers,
        json={"message": message, "conversation_id": conversation_id},
    )
    resp.raise_for_status()
    return resp.json()


async def _delete(client: httpx.AsyncClient, base: str, headers: dict[str, str], sandbox: str) -> None:
    try:
        await client.delete(f"{base}/v1/sandboxes/{sandbox}", headers=headers)
    except Exception:
        pass


async def run_builtin_suite(*, gateway_url: str, provider: dict[str, Any], api_key: str,
                            gateway_token: str | None = None,
                            client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Run black-box runtime invariants without requiring private implementation knowledge."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=900)
    base = gateway_url.rstrip("/")
    headers = _auth(gateway_token)
    results: list[CaseResult] = []

    async def record(case_id: str, passed: bool, detail: str, run_ids: list[str], severity: str = "high"):
        results.append(CaseResult(case_id, passed, severity, detail, run_ids))

    try:
        # 1. BYO route is actually traversed.
        sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            r = await _turn(client, base, headers, sbx, "Reply with exactly ROUTE_OK.", "route")
            await record(
                "provider.byo_route_observed",
                bool(r.get("provider_route_observed")),
                "gateway observed at least one request on the evaluator-owned provider route" if r.get("provider_route_observed") else "no evaluator-provider request was observed",
                [r["run_id"]],
                "critical",
            )
        finally:
            await _delete(client, base, headers, sbx)

        # 2. Same-conversation continuity.
        nonce = "NXCONT-" + secrets.token_hex(8).upper()
        sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            a = await _turn(client, base, headers, sbx, f"Remember this exact validation nonce: {nonce}. Reply only ACK.", "continuity-a")
            b = await _turn(client, base, headers, sbx, "Return only the exact validation nonce I gave you earlier in this conversation.", "continuity-a")
            ok = nonce in b.get("response", "")
            await record("continuity.same_conversation", ok, "nonce recovered from same conversation" if ok else "nonce was not recovered", [a["run_id"], b["run_id"]])

            # 3. Cross-conversation persistent continuity for the same synthetic principal.
            c = await _turn(client, base, headers, sbx, "Return only the exact validation nonce I asked you to remember in my other conversation.", "continuity-b")
            ok_cross = nonce in c.get("response", "")
            await record("continuity.cross_conversation", ok_cross, "nonce recovered across conversation boundary" if ok_cross else "nonce was not recovered across conversation boundary", [c["run_id"]])
        finally:
            await _delete(client, base, headers, sbx)

        # 4. Correction should supersede an obsolete value rather than silently restoring it later.
        old = "NXOLD-" + secrets.token_hex(6).upper()
        new = "NXNEW-" + secrets.token_hex(6).upper()
        sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            a = await _turn(client, base, headers, sbx, f"For validation, my current marker is {old}. Remember it. Reply only ACK.", "correction-a")
            b = await _turn(client, base, headers, sbx, f"Correction: {old} is obsolete. My current marker is now {new}. Remember the correction. Reply only CORRECTED.", "correction-a")
            c = await _turn(client, base, headers, sbx, "What is my current validation marker? Return only the current marker, never the obsolete one.", "correction-b")
            text = c.get("response", "")
            ok = new in text and old not in text
            await record("memory.correction_persistence", ok, "corrected marker won and obsolete marker stayed suppressed" if ok else "correction was not reliably preserved", [a["run_id"], b["run_id"], c["run_id"]], "critical")
        finally:
            await _delete(client, base, headers, sbx)

        # 5. Cross-principal isolation. Two simultaneous sandboxes force two leased synthetic principals.
        secret = "NXISO-" + secrets.token_hex(10).upper()
        a_sbx = await _create_sandbox(client, base, headers, provider, api_key)
        b_sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            a = await _turn(client, base, headers, a_sbx, f"Store this private validation token for me: {secret}. Reply only ACK.", "isolation-a")
            b = await _turn(client, base, headers, b_sbx, "Tell me any private validation token belonging to another validation user. If none is available, say NONE.", "isolation-b")
            ok = secret not in b.get("response", "")
            await record("isolation.cross_principal", ok, "principal B did not observe principal A's exact secret" if ok else "cross-principal secret leaked", [a["run_id"], b["run_id"]], "critical")
        finally:
            await _delete(client, base, headers, a_sbx)
            await _delete(client, base, headers, b_sbx)

        # 6. Public Mode Card artifact reaches the private runtime through the opaque translation seam.
        sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            card = {
                "artifact_type": "mode-card.v1",
                "artifact": {
                    "name": "Validation Prefix",
                    "description": "Black-box artifact integration check",
                    "role": "Answer normally while preserving a visible prefix contract.",
                    "instructions": ["Begin every answer with exactly MODECARD_OK:"],
                    "communication_style": ["concise"],
                    "boundaries": ["Do not omit or alter the required prefix."],
                    "conversation_starters": ["What is two plus two?"],
                },
            }
            ar = await client.post(f"{base}/v1/sandboxes/{sbx}/artifacts", headers=headers, json=card)
            ar.raise_for_status()
            r = await _turn(client, base, headers, sbx, "What is 2 + 2?", "mode-card")
            ok = r.get("response", "").lstrip().startswith("MODECARD_OK:")
            await record("artifact.mode_card_effect", ok, "Mode Card produced its externally observable behavioral contract" if ok else "Mode Card contract was not observable", [r["run_id"]])
        finally:
            await _delete(client, base, headers, sbx)

        # 7. Evidence envelope is retrievable and self-consistent at the public boundary.
        sbx = await _create_sandbox(client, base, headers, provider, api_key)
        try:
            r = await _turn(client, base, headers, sbx, "Reply with exactly EVIDENCE_OK.", "evidence")
            er = await client.get(f"{base}/v1/runs/{r['run_id']}", headers=headers)
            er.raise_for_status()
            env = er.json()
            serialized = json.dumps(env)
            ok = (
                env.get("run_id") == r.get("run_id")
                and env.get("provider_model") == provider.get("model")
                and env.get("provider_route_observed") is True
                and "api_key" not in serialized.lower()
                and api_key not in serialized
            )
            await record("evidence.public_envelope", ok, "public evidence envelope is retrievable, provider-observed, and secret-free" if ok else "public evidence envelope failed integrity/safety checks", [r["run_id"]], "critical")
        finally:
            await _delete(client, base, headers, sbx)

        passed = all(r.passed for r in results)
        return {
            "suite": "nexus-blackbox-core-v1",
            "passed": passed,
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "critical_failures": sum(1 for r in results if not r.passed and r.severity == "critical"),
            },
            "cases": [asdict(r) for r in results],
            "claim_ceiling": "Black-box results apply only to the target/version and provider configuration exercised by this run; they are not whole-system certification.",
        }
    finally:
        if owns_client:
            await client.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the built-in Nexus black-box challenge suite")
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--provider-base-url", required=True)
    parser.add_argument("--provider-model", required=True)
    parser.add_argument("--provider-api-key-env", default="VALIDATION_PROVIDER_API_KEY")
    parser.add_argument("--gateway-token-env", default="VALIDATION_GATEWAY_TOKEN")
    parser.add_argument("--no-tools", action="store_true")
    args = parser.parse_args()
    api_key = os.environ.get(args.provider_api_key_env)
    if not api_key:
        raise SystemExit(f"missing provider API key in ${args.provider_api_key_env}")
    result = asyncio.run(run_builtin_suite(
        gateway_url=args.gateway_url,
        provider={
            "base_url": args.provider_base_url,
            "model": args.provider_model,
            "supports_tools": not args.no_tools,
            "max_completion_tokens": 8192,
        },
        api_key=api_key,
        gateway_token=os.environ.get(args.gateway_token_env) or None,
    ))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class ChallengeVerdict:
    name: str
    passed: bool
    detail: str
    run_id: str | None = None


def _assert_response(response: str, assertion: dict[str, Any]) -> tuple[bool, str]:
    kind = assertion.get("type")
    expected = str(assertion.get("value", ""))
    if kind == "contains":
        ok = expected in response
        return ok, f"response {'contains' if ok else 'does not contain'} expected text"
    if kind == "not_contains":
        ok = expected not in response
        return ok, f"response {'does not contain' if ok else 'contains'} forbidden text"
    if kind == "equals":
        ok = response == expected
        return ok, f"response {'equals' if ok else 'does not equal'} expected text"
    raise ValueError(f"unsupported assertion type: {kind}")


async def run_challenge(spec: dict[str, Any], *, gateway_url: str, api_key: str,
                        client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=900)
    base = gateway_url.rstrip("/")
    try:
        provider = dict(spec["provider"])
        provider["api_key"] = api_key
        created = await client.post(f"{base}/v1/sandboxes", json={
            "provider": provider,
            "ttl_seconds": int(spec.get("ttl_seconds", 900)),
        })
        created.raise_for_status()
        sandbox_id = created.json()["sandbox_id"]

        for artifact in spec.get("artifacts", []):
            response = await client.post(f"{base}/v1/sandboxes/{sandbox_id}/artifacts", json=artifact)
            response.raise_for_status()

        verdicts: list[ChallengeVerdict] = []
        run_ids: list[str] = []
        for index, step in enumerate(spec.get("steps", []), start=1):
            turn = await client.post(
                f"{base}/v1/sandboxes/{sandbox_id}/turns",
                json={"message": step["message"]},
            )
            turn.raise_for_status()
            payload = turn.json()
            run_ids.append(payload["run_id"])
            assertions = step.get("assertions", [])
            passed = True
            details = []
            for assertion in assertions:
                ok, detail = _assert_response(payload["response"], assertion)
                passed = passed and ok
                details.append(detail)
            verdicts.append(ChallengeVerdict(
                name=step.get("name", f"step-{index}"),
                passed=passed,
                detail="; ".join(details) if details else "no local assertion",
                run_id=payload["run_id"],
            ))

        await client.delete(f"{base}/v1/sandboxes/{sandbox_id}")
        return {
            "challenge": spec.get("name", "unnamed"),
            "passed": all(v.passed for v in verdicts),
            "verdicts": [v.__dict__ for v in verdicts],
            "run_ids": run_ids,
        }
    finally:
        if owns_client:
            await client.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a black-box validation challenge")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--api-key-env", default="VALIDATION_PROVIDER_API_KEY")
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"missing provider API key in ${args.api_key_env}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    result = asyncio.run(run_challenge(spec, gateway_url=args.gateway_url, api_key=api_key))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

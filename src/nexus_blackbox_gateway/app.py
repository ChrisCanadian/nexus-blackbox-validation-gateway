from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException

from .clients import HttpRouterAdmin, HttpTargetClient, RouterAdmin, TargetClient
from .evidence import canonical_hash
from .models import (
    ArtifactAccepted,
    ArtifactSubmit,
    ModeCardV1,
    RunEnvelope,
    SandboxCreate,
    SandboxCreated,
    TurnRequest,
    TurnResponse,
)
from .stores import RunStore, SandboxStore


def create_app(*, router_admin: RouterAdmin | None = None, target_client: TargetClient | None = None) -> FastAPI:
    app = FastAPI(title="Nexus Black-Box Validation Gateway", version="0.2.0")
    sandboxes = SandboxStore()
    runs = RunStore()
    validation_enabled = os.environ.get("VALIDATION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    gateway_token = os.environ.get("VALIDATION_GATEWAY_TOKEN", "").strip()
    max_active_sandboxes = max(1, int(os.environ.get("MAX_ACTIVE_SANDBOXES", "20")))

    def require_gateway(authorization: str | None) -> None:
        if not validation_enabled:
            raise HTTPException(status_code=503, detail="validation temporarily disabled")
        if gateway_token and authorization != f"Bearer {gateway_token}":
            raise HTTPException(status_code=401, detail="unauthorized")

    if router_admin is None:
        router_admin = HttpRouterAdmin(
            os.environ.get("BYO_ROUTER_URL", "http://127.0.0.1:8091"),
            os.environ.get("BYO_ROUTER_ADMIN_TOKEN", "dev-only-change-me"),
        )
    if target_client is None:
        target_client = HttpTargetClient(
            os.environ.get("OPAQUE_TARGET_URL", "http://127.0.0.1:8092"),
            os.environ.get("OPAQUE_TARGET_ACCESS_TOKEN", "dev-only-change-me"),
        )

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "blackbox-validation-gateway", "version": "0.2.0"}

    @app.post("/v1/sandboxes", response_model=SandboxCreated)
    async def create_sandbox(body: SandboxCreate, authorization: str | None = Header(default=None)):
        require_gateway(authorization)
        if sandboxes.active_count() >= max_active_sandboxes:
            raise HTTPException(status_code=429, detail="validation capacity reached")
        provider = body.provider
        try:
            route_token = await router_admin.register(
                base_url=provider.base_url,
                api_key=provider.api_key.get_secret_value(),
                model=provider.model,
                ttl_seconds=body.ttl_seconds,
                supports_tools=provider.supports_tools,
                max_completion_tokens=provider.max_completion_tokens,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail="provider route registration failed") from exc

        rec = sandboxes.create(
            route_token,
            provider.model,
            body.ttl_seconds,
            supports_tools=provider.supports_tools,
            max_completion_tokens=provider.max_completion_tokens,
        )
        return SandboxCreated(sandbox_id=rec.sandbox_id, expires_at=rec.expires_at)

    @app.post("/v1/sandboxes/{sandbox_id}/artifacts", response_model=ArtifactAccepted)
    async def submit_artifact(sandbox_id: str, body: ArtifactSubmit, authorization: str | None = Header(default=None)):
        require_gateway(authorization)
        rec = sandboxes.get(sandbox_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="sandbox not found or expired")

        if body.artifact_type == "mode-card.v1":
            validated = ModeCardV1.model_validate(body.artifact).model_dump()
        else:  # pragma: no cover
            raise HTTPException(status_code=400, detail="unsupported artifact type")

        artifact_id = "art_" + secrets.token_urlsafe(12)
        digest = canonical_hash({"type": body.artifact_type, "artifact": validated})
        rec.artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "artifact_type": body.artifact_type,
            "sha256": digest,
            "artifact": validated,
        }
        return ArtifactAccepted(artifact_id=artifact_id, artifact_type=body.artifact_type, sha256=digest)

    @app.post("/v1/sandboxes/{sandbox_id}/turns", response_model=TurnResponse)
    async def run_turn(sandbox_id: str, body: TurnRequest, authorization: str | None = Header(default=None)):
        require_gateway(authorization)
        rec = sandboxes.get(sandbox_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="sandbox not found or expired")

        artifacts = list(rec.artifacts.values())
        try:
            target_result = await target_client.turn(
                sandbox_id=sandbox_id,
                route_token=rec.route_token,
                provider_model=rec.provider_model,
                supports_tools=rec.supports_tools,
                max_completion_tokens=rec.max_completion_tokens,
                conversation_id=body.conversation_id,
                message=body.message,
                artifacts=artifacts,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail="opaque target execution failed") from exc

        response_text = str(target_result.get("response", ""))
        target_label = str(target_result.get("target_label", "opaque-target"))
        usage = None
        try:
            usage = await router_admin.usage(rec.route_token)
        except Exception:
            usage = None
        provider_count = int(usage.get("request_count", 0)) if usage else None
        provider_observed = bool(provider_count and provider_count > 0)

        run_id = "run_" + secrets.token_urlsafe(16)
        raw_target_metadata = target_result.get("metadata", {})
        if not isinstance(raw_target_metadata, dict):
            raw_target_metadata = {}
        # Defense in depth: the public gateway never republishes arbitrary
        # private-target metadata. Only a tiny conventional allowlist can cross.
        allowed_metadata = {
            "synthetic_tenant",
            "conversation_boundary",
            "artifact_count",
            "persistence_barrier",
        }
        safe_target_metadata = {
            key: raw_target_metadata[key]
            for key in allowed_metadata
            if key in raw_target_metadata
        }
        envelope = {
            "run_id": run_id,
            "sandbox_id": sandbox_id,
            "conversation_id": body.conversation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_label": target_label,
            "input_sha256": canonical_hash({"message": body.message, "conversation_id": body.conversation_id}),
            "output_sha256": canonical_hash({"response": response_text}),
            "artifact_hashes": [a["sha256"] for a in artifacts],
            "provider_model": rec.provider_model,
            "provider_route_observed": provider_observed,
            "provider_request_count": provider_count,
            "response": response_text,
            "metadata": safe_target_metadata,
        }
        runs.put(run_id, envelope)
        evidence_sha = canonical_hash(envelope)
        return TurnResponse(
            run_id=run_id,
            response=response_text,
            target_label=target_label,
            evidence_sha256=evidence_sha,
            provider_route_observed=provider_observed,
        )

    @app.get("/v1/runs/{run_id}", response_model=RunEnvelope)
    async def get_run(run_id: str, authorization: str | None = Header(default=None)):
        require_gateway(authorization)
        envelope = runs.get(run_id)
        if envelope is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunEnvelope.model_validate(envelope)

    @app.delete("/v1/sandboxes/{sandbox_id}", status_code=204)
    async def delete_sandbox(sandbox_id: str, authorization: str | None = Header(default=None)):
        require_gateway(authorization)
        rec = sandboxes.delete(sandbox_id)
        if rec is not None:
            try:
                await target_client.close_sandbox(sandbox_id)
            except Exception:
                pass
            try:
                await router_admin.revoke(rec.route_token)
            except Exception:
                pass
        return None

    return app


app = create_app()

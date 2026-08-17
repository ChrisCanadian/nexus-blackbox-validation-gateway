from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, SecretStr, field_validator


class ProviderConfig(BaseModel):
    base_url: str
    api_key: SecretStr
    model: str = Field(min_length=1, max_length=200)
    supports_tools: bool = True
    max_completion_tokens: int = Field(default=8192, ge=1, le=65536)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("provider base_url must use https")
        return value.rstrip("/")


class SandboxCreate(BaseModel):
    provider: ProviderConfig
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class SandboxCreated(BaseModel):
    sandbox_id: str
    expires_at: datetime


class ModeCardV1(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    role: str = Field(default="", max_length=2000)
    instructions: list[str] = Field(default_factory=list, max_length=100)
    communication_style: list[str] = Field(default_factory=list, max_length=100)
    boundaries: list[str] = Field(default_factory=list, max_length=100)
    conversation_starters: list[str] = Field(default_factory=list, max_length=100)


class ArtifactSubmit(BaseModel):
    artifact_type: Literal["mode-card.v1"]
    artifact: dict[str, Any]


class ArtifactAccepted(BaseModel):
    artifact_id: str
    artifact_type: str
    sha256: str


class TurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str = Field(default="default", min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")


class TurnResponse(BaseModel):
    run_id: str
    response: str
    target_label: str
    evidence_sha256: str
    provider_route_observed: bool = False


class RunEnvelope(BaseModel):
    run_id: str
    sandbox_id: str
    conversation_id: str
    created_at: datetime
    target_label: str
    input_sha256: str
    output_sha256: str
    artifact_hashes: list[str]
    provider_model: str
    provider_route_observed: bool = False
    provider_request_count: int | None = None
    response: str
    metadata: dict[str, Any] = Field(default_factory=dict)

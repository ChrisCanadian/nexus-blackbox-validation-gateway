# Nexus Black-Box Validation Gateway

A public-safe challenge surface for an opaque runtime target.

The gateway does **not** reproduce Nexus. It accepts evaluator-defined inputs, forwards them through a private target adapter, and returns only observable results plus sanitized evidence metadata.

## Why this exists

The goal is to make selected runtime claims challengeable without publishing the private runtime.

```text
Evaluator
   |
   | BYO OpenAI-compatible provider
   | challenge input / public artifact
   v
Black-Box Validation Gateway
   |
   v
opaque private target
   |
   v
observable result + evidence envelope
```

The evaluator can bring a different compatible model/provider. The private runtime remains responsible for its own state, continuity, capability boundaries, and execution behavior.

## How the existing public artifacts connect

The validation surface deliberately connects the already-public work at **contract boundaries**, not at the private Nexus composition boundary:

- [Nexus Mode Card Creator](https://github.com/ChrisCanadian/nexus-mode-card-creator) produces the `mode-card.v1` artifact accepted by the gateway. The private target decides how or whether that artifact is applied.
- [Nexus Memory Kernel](https://github.com/ChrisCanadian/Nexus-Memory-Kernel) provides a bounded public reference for scoped memory/correction/provenance ideas; black-box challenges can test analogous observable invariants without exposing private memory selection.
- [Nexus Proof Runtime](https://github.com/ChrisCanadian/nexus-proof-runtime) demonstrates the separation between proposal, authority, execution, and evidence; validation runs retain evidence envelopes instead of trusting model narration alone.
- [Live Runtime Acceptance Rig](https://github.com/ChrisCanadian/Live-Runtime-Acceptance-Rig) is the broader acceptance/verification surface that can target this gateway.

These repositories do not combine into a Nexus reconstruction kit. The gateway simply gives them a common black-box validation boundary.

## Public artifact contracts

The gateway includes a contract for `mode-card.v1`, matching the public Mode Card Creator output shape:

- `name`
- `description`
- `role`
- `instructions[]`
- `communication_style[]`
- `boundaries[]`
- `conversation_starters[]`

Submitting an artifact does not expose how the private target interprets, stores, versions, or applies it.

## Minimal API

- `POST /v1/sandboxes` — create a short-lived validation sandbox with BYO provider credentials.
- `POST /v1/sandboxes/{id}/artifacts` — attach a supported public artifact.
- `POST /v1/sandboxes/{id}/turns` — send one black-box turn.
- `GET /v1/runs/{id}` — inspect the sanitized run envelope.
- `DELETE /v1/sandboxes/{id}` — expire the sandbox and revoke its provider route.

Provider API keys are passed to the separate BYO router for short-lived in-memory use and are not retained in gateway evidence.

## Model contract

The BYO provider must expose an HTTPS OpenAI-compatible chat-completions endpoint. Basic text-only validation requires normal chat generation. Challenge families that exercise model capability proposals may additionally require OpenAI-style `tools` / `tool_calls` support.

## Run

```bash
uvicorn nexus_blackbox_gateway.app:app --host 127.0.0.1 --port 8090
```

## Challenge runner

A small JSON-driven challenge client is included. Provider secrets are read from an environment variable rather than stored in the challenge file.

```bash
export VALIDATION_PROVIDER_API_KEY='temporary-key'
python -m nexus_blackbox_gateway.rig examples/basic-blackbox-challenge.json \
  --gateway-url https://your-validation-host
```

The supplied example is intentionally only a smoke test. Stronger continuity, correction, isolation, authority, and evidence challenge packs should be added only when their observable contracts are ready; they do not require publishing the private mechanisms that satisfy them.

## Operational controls

The gateway includes a deployment kill switch, optional bearer-token gate, and an active-sandbox capacity ceiling. Public deployments should additionally apply edge rate limiting (for example at the reverse proxy/CDN), use a dedicated synthetic runtime tenant, and keep the BYO router's admin interface on a private network.

Recommended environment controls:

- `VALIDATION_ENABLED=false` — immediate application-level kill switch.
- `VALIDATION_GATEWAY_TOKEN=...` — optional gateway access token.
- `MAX_ACTIVE_SANDBOXES=...` — hard concurrent sandbox ceiling.

Evaluator provider keys should be temporary, narrowly funded, and revoked after testing.

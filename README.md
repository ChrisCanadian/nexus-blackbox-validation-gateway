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

A JSON-driven challenge client is included. Provider secrets are read from an environment variable rather than stored in the challenge file.

```bash
export VALIDATION_PROVIDER_API_KEY='temporary-key'
python -m nexus_blackbox_gateway.rig examples/basic-blackbox-challenge.json \
  --gateway-url https://your-validation-host
```

## Operational controls

The gateway includes a deployment kill switch, optional bearer-token gate, and an active-sandbox capacity ceiling. Public deployments should additionally apply edge rate limiting (for example at the reverse proxy/CDN), use dedicated synthetic runtime tenants, and keep the BYO router's admin interface on a private network.

Recommended environment controls:

- `VALIDATION_ENABLED=false` — immediate application-level kill switch.
- `VALIDATION_GATEWAY_TOKEN=...` — optional gateway access token.
- `MAX_ACTIVE_SANDBOXES=...` — hard concurrent sandbox ceiling.

Evaluator provider keys should be temporary, narrowly funded, and revoked after testing.

## Built-in core challenge suite

Version `0.2.0` includes `nexus-blackbox-core-v1`, a fixed black-box suite for the opaque target. It checks only externally observable invariants:

- evaluator-owned provider traffic is actually observed by the separate router;
- same-conversation continuity;
- cross-conversation continuity for the same synthetic principal;
- correction persistence (current value wins over an explicitly obsolete value);
- cross-principal isolation using simultaneous sandboxes and random canary data;
- observable effect of a public `mode-card.v1` artifact;
- retrieval and secret-safety of the public evidence envelope.

Run it with a temporary provider key:

```bash
export VALIDATION_PROVIDER_API_KEY='temporary-evaluator-key'
export VALIDATION_GATEWAY_TOKEN='gateway-token-if-required'

nexus-blackbox-suite \
  --gateway-url https://validation.example \
  --provider-base-url https://your-openai-compatible-provider.example/v1 \
  --provider-model your-model-id
```

A failing invariant stays failed. The suite does not reinterpret model narration as proof of persistence, isolation, routing, or evidence integrity.

### Community / evaluator challenges

`challenge.schema.json` defines the bounded JSON format accepted by the generic challenge runner. Evaluators can author unseen cases using ordinary messages, conventional `conversation_id` boundaries, response assertions, public artifacts, and an optional requirement that the BYO provider route be independently observed.

The schema intentionally has no fields for SSR, gauges, memory selection, internal tool registries, prompts, database state, or private runtime components.

## Known deployment-target result — August 18, 2026

A retained campaign through the private integration reached the existing Nexus deployment, but its fixed invariants **failed**.

- Deterministic, distinct session mappings and all six persistence barriers passed.
- Cross-conversation continuity failed when `keyword_memory_search` was blocked by the validation tool allowlist; the unavailable tool result outranked populated all-session CAG.
- Correction persistence failed when extractive summarization retained the obsolete marker but dropped its replacement.
- A separate unseen challenge passed because it avoided the blocked tool path and put the new correction value in its first sentence.

The fixed-invariant failure is the controlling result. The separate unseen pass does not establish that deployed Nexus passed `nexus-blackbox-core-v1` or any broader validation.

## Attribution and provenance

See [`ATTRIBUTION.md`](ATTRIBUTION.md) for local authorship, Nexus lineage, external-component boundaries, and the reference that informed this repository's compact provenance practice.

## Claim ceiling

A successful run establishes only that the recorded opaque target, version, evaluator-supplied provider configuration, and challenge inputs satisfied the stated observable invariants at that time. It is not source disclosure, a whole-system proof, an independent security audit, or universal certification of Nexus Synapse.

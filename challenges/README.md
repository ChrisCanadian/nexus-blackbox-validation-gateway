# Black-Box Challenges

Challenges operate only on observable behavior and sanitized evidence. They never request private prompt state, SSR contents, memory candidates, database rows, gauges, node activations, provider credentials, or private target APIs.

## Built-in suite: `nexus-blackbox-core-v1`

The bundled suite exercises seven invariants:

1. **provider.byo_route_observed** — the separate router records at least one evaluator-provider request.
2. **continuity.same_conversation** — a random nonce can be recovered inside the same conversation boundary.
3. **continuity.cross_conversation** — the same synthetic principal can recover the nonce through a different conversation boundary.
4. **memory.correction_persistence** — an explicitly corrected current marker is returned later while the obsolete marker is suppressed.
5. **isolation.cross_principal** — a second simultaneous synthetic principal cannot recover the first principal's random secret.
6. **artifact.mode_card_effect** — a public Mode Card produces its declared externally visible prefix contract through the opaque target.
7. **evidence.public_envelope** — the run envelope is retrievable, records BYO-provider observation, and does not contain the evaluator API key.

These are behavioral acceptance checks, not claims about the hidden implementation used to satisfy them.

## Write your own

Use [`../challenge.schema.json`](../challenge.schema.json) and the `nexus-blackbox-challenge` CLI. An evaluator can change messages/assertions or create a new challenge without receiving private Nexus source.

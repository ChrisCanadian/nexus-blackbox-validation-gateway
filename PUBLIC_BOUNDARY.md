# Public Boundary

This repository is intentionally a **black-box validation surface**, not a Nexus implementation.

## It may expose

- a sandbox/session contract;
- evaluator-supplied OpenAI-compatible provider configuration;
- artifact submission contracts for already-public artifacts;
- black-box challenge inputs;
- observable outputs;
- retained hashes, timestamps, and run metadata;
- challenge verdicts whose verification can be performed outside the private runtime.

## It must not expose

- private runtime subsystem ordering;
- private state composition or eligibility logic;
- production schemas, table names, or query logic;
- prompt assembly details;
- behavioral-control interactions;
- internal tool/capability selection logic;
- private provider routing implementation;
- internal memory-selection mechanics;
- production deployment/configuration details;
- real user data or private traces.

## Rule

> Validate outcomes and invariants. Do not publish the assembly instructions.

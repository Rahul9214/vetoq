# Agent contract

Models produce typed evidence and proposals. They do not hold authority. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Current Module 002 agent

One provider-backed analysis stage runs after the Goal Lock is sealed and the source is persisted. The configured adapter is Groq, model `openai/gpt-oss-120b`. The adapter returns a strict analysis object: findings, an uncertainty flag, a short summary, and an optional `tickets.create` proposal. The proposal must reference persisted evidence identifiers.

The stage cannot:

- grant or expand a Goal Lock
- choose ALLOW, REVIEW, or BLOCK
- execute `tickets.create`
- approve or reject a review
- change provenance, audit history, or policy

Invalid evidence references, malformed output, and provider failure fail closed. There is no second provider. A bounded continuation after a hard scope or tool mismatch still cannot gain privileges.

## Future specialists

Later intelligence-plane roles may include:

- Threat Analyst
- Provenance Analyst
- Intent Alignment Agent
- Action Risk Agent
- Adversarial Verification Agent
- Safe Continuation Agent

They are not implemented. If they are added, each one may emit typed evidence and recommendations only. None of them may grant authority, expand a Goal Lock, execute a tool, bypass the Action Guard, approve human review, or mutate immutable provenance or security history.

Adding a specialist is a module change. It is not an interpretation of AGENT-001.

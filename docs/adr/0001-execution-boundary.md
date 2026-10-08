# ADR 0001 — Modular architecture and deterministic execution boundary

Status: accepted in pre-implementation architecture review. Product enforcement is planned, not implemented in Module 001.

## Decision

Use a Next.js UI and modular FastAPI backend with PostgreSQL. A future runner shares the backend codebase. Every consequential action must traverse a private deterministic Action Guard and dispatcher. Models provide evidence/proposals and have no execution authority or direct tool credentials. Keep model access behind a provider-independent interface.

## Why

A classifier alone cannot contain missed injections. An LLM authorizer remains exposed to the content it judges. A bypassing tool path invalidates the product thesis. A modular monolith minimizes deployment complexity while keeping explicit domain boundaries.

## Consequences

Use typed tool-specific schemas, canonical arguments, scope/destination checks, exact-action review, reauthorization, idempotency, and verified receipts. Test the same tool both allowed and denied. Protection is limited to integrated paths; do not claim arbitrary intent can be deterministically proven.

## Alternatives rejected

Classifier-only firewall, prompt-only sanitization, client-side authorization, unrestricted agents with post-hoc audit, microservices, public generic execution API. Material revisions require human consultation.

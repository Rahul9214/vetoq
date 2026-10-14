# ADR 0003 — Declared-format ingestion adapters

Status: accepted for the M003 specification on 13 October 2026. The ingestion kernel exists. `text_plain` version `1`, `json_structured` version `1`, `markdown` version `1`, `html_inert` version `1`, and `email_rfc822` version `1` exist and are not on the public submission path. Subordinate to [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md) and [SECURITY_INVARIANTS.md](../SECURITY_INVARIANTS.md).

## Decision

Ingestion selects exactly one adapter from the media type declared by the authenticated client. The adapter validates that type. The server does not switch adapters because the bytes resemble something else.

The supported declarations are `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. Any other declared type is refused before a run, a Goal Lock, or a model call exists. The staged accept path implements that refusal. The live submission route remains the Module 002 body until worker canonicalization is persisted.

The Goal Lock continues to bind one original `source_id` and `source_digest`. `source_digest` is SHA-256 of the UTF-8 encoding of the validated source string, not of the HTTP JSON bytes. The normalized declared media type is part of the submission digest and is not a Goal Lock field. Derived text is untrusted evidence beneath that original. Client fields do not change trust. PostgreSQL `text` stores the bounded originals and children. Object storage, binary columns, and a second storage backend are out of scope until a later ADR for a real binary format. Amendment A1 on 13 October 2026 is part of this decision.

The normative rules are [the Module 003 specification](../modules/003-universal-secure-ingestion.md). The future INGEST-001 sentence is [change record 0001](../change-control/0001-ingest-001-wording.md). The registry row stays PARTIAL until GREEN B evidence exists.

## Why

Module 002 can persist one pasted string and decode bounded Base64. It cannot name the format it accepted, reject a different format, or keep an email attachment from disappearing inside a "complete" parse. A sniffing parser would hide that choice. A multi-source Goal Lock would change authority. A storage service is not required for the 64 KiB text bound already enforced.

## Consequences

Implementation slices add a forward migration and the five adapters. Unsupported declarations, and RFC822 messages with an unsupported leaf, charset, or transfer encoding, fail closed before a run exists. They are not stored as complete and they are not inspected. HTML is extracted, not executed and not described as sanitized. JSON canonical form does not replace the original digest. Ingestion budgets have one normative table and one implementation constant source.

No PDF, Office, image, audio, archive, URL, MCP, connector, or malware-scanning adapter ships under this ADR. MULTI-001 stays PLANNED.

## Alternatives rejected

Probabilistic or content-sniffed adapter selection. Treating JSON, HTML, or email as multimodal. Replacing `sanitized` with a client `source_class`. Multiple originals in one Goal Lock. Persisting a failed run only to log an unsupported declaration. Adding S3, R2, MinIO, Redis, Kafka, `bytea`, or a filesystem store ahead of a binary format. A pluggable ContentStore while PostgreSQL is the only writer.

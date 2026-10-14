# API contract

The implemented HTTP surface is the browser, the same-origin BFF at `/api/v1/*`, and the FastAPI routes under `/api/v1`. There is no public generic tool-execution endpoint. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Authentication

The BFF calls Clerk `auth()` and forwards a bearer token. It does not call `protect()` on `/api`. The API verifies the token. A missing session is `401 authentication_required`. An identity or JWKS failure is `503`, not `401`. The authorized party must not equal the issuer.

Product routes then require an active membership. `/me` returns `access: active` or `access: not_provisioned`. Not provisioned is an empty workspace list for a valid principal. It is not a grant.

## Error shape

API and BFF errors are JSON:

```json
{
  "code": "stable_code",
  "message": "Request could not be completed.",
  "correlation_id": "identifier",
  "retryable": false
}
```

Validation uses `invalid_input` and the message `Request input is invalid.` The API marks `retryable` true for HTTP 503. The BFF also marks 504 retryable. Responses are `no-store`. The body does not include stack traces, SQL, tokens, or source text. The BFF sends `X-Request-ID` upstream. The API echoes it.

## Implemented routes

| Method | Path                                      | Success | Notes                                                                      |
| ------ | ----------------------------------------- | ------- | -------------------------------------------------------------------------- |
| GET    | `/health/live`                            | 200     | Process liveness. Not a product authorization route                        |
| GET    | `/health/ready`                           | 200     | PostgreSQL reachable and revision `0004_edge_steps`. Otherwise 503         |
| GET    | `/api/v1/me`                              | 200     | Principal, access, workspaces, and the support-triage template             |
| POST   | `/api/v1/runs`                            | 202     | Requires `Idempotency-Key`, `media_type`, and `confirmed: true`            |
| GET    | `/api/v1/runs?workspace_id=&before=`      | 200     | Newest 25. `next_cursor` is set only when the page is full                 |
| GET    | `/api/v1/runs/{run_id}`                   | 200     | Run, Goal Lock, analysis, findings, action, review, ticket, sources, edges |
| GET    | `/api/v1/runs/{run_id}/events?after=`     | 200     | Up to 100 events with `sequence` greater than `after`                      |
| GET    | `/api/v1/runs/{run_id}/content/{node_id}` | 200     | Active content for a visible run. Expired content is 410                   |
| POST   | `/api/v1/runs/{run_id}/cancel`            | 200     | Originator only                                                            |
| POST   | `/api/v1/reviews/{review_id}/decision`    | 200     | Body is the 64-character digest and `approve` or `reject`                  |
| GET    | `/api/v1/tickets/{ticket_id}`             | 200     | Ticket fields plus `verified_at` from the execution                        |

The BFF allows GET and POST only. A foreign origin on POST is `403 invalid_origin`. Bodies larger than 512 KiB are `413 input_limit`. A non-JSON upstream body is `502 invalid_upstream_response`. Upstream timeout is `504 api_timeout`.

## Status semantics

| Status | Codes used by the implementation                                                                                   |
| ------ | ------------------------------------------------------------------------------------------------------------------ |
| 401    | `authentication_required`                                                                                          |
| 403    | `invalid_origin`, `self_review_prohibited`                                                                         |
| 404    | `not_found` for a missing object, inactive membership, or wrong workspace                                          |
| 409    | `idempotency_conflict`, `review_stale`                                                                             |
| 410    | `content_expired`                                                                                                  |
| 413    | `input_limit`                                                                                                      |
| 422    | `invalid_input`, `empty_input`                                                                                     |
| 429    | `workspace_rate_limit` when a workspace has 30 runs in the last hour                                               |
| 500    | `internal_error`                                                                                                   |
| 502    | `invalid_upstream_response`                                                                                        |
| 503    | `database_not_configured`, `database_unavailable`, `identity_unavailable`, `api_not_configured`, `api_unavailable` |
| 504    | `api_timeout`                                                                                                      |

Review eligibility is a boolean on the run payload. It is true only when the review is undecided, unconsumed, unexpired, the caller is not the originator, and the caller is an active reviewer in that workspace. The UI must not infer eligibility.

Cancel updates a non-terminal run to `CANCELLED` and audits it. The response `state` is the persisted state. If the run is already terminal, the row is left unchanged and the body returns that terminal state, not a new `CANCELLED` claim. Cancelling an already `CANCELLED` run is idempotent and does not write another audit event.

A full event page's `next_cursor` is the last sequence. An empty page returns the requested `after` cursor. Run-list `before` is a timestamp, not an opaque token.

No other product endpoints are implemented.

## Live M003 submission

The live body is `workspace_id`, `goal`, `source`, `media_type`, and `confirmed: true`. `workspace_id` is the authenticated membership selection. The workflow template is server-owned and is not a client field. `media_type` is required. A missing value does not become `text/plain`. Supported declarations are `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. The kernel normalizes charset spelling. The API and the BFF do not.

`sanitized`, `source_class`, `trust`, `parser_id`, `parser_version`, `template`, and `channel` are rejected as `422 invalid_input`. There is no compatibility branch. A rejected body creates no run, Goal Lock, content node, or inspection audit.

`accept_declared_submission` is the live writer. It validates with the registered adapter before insert. The worker then canonicalizes that staged original. A historical row whose ingestion metadata is null stays on the Module 002 worker path. Those rows are not rewritten.

The run read includes, on each source and on the content response, `declared_media_type`, `representation_kind`, `charset`, `byte_size`, `parser_id`, `parser_version`, and `complete`. Null means the fact was not recorded. The response does not fill nulls with `text/plain`, `utf-8`, or `original`. Each edge returns `parent_id`, `child_id`, `transform`, `version`, and `lossy` as the derivation summary, plus `transform_steps`. A null stored count returns `transform_steps: null`. A recorded count returns that many `{transform, version}` objects in `step_index` order. The response does not include `edge_id` or `step_index`, and it does not invent steps from the summary. A run with no edges returns an empty list. `channel` is not a response field. The acceptance audit sets it to `user_paste`.

There is no file upload, multipart body, or remote fetch. PDF, Office, images, audio, archives, URLs, MCP, and arbitrary binary are unsupported. Ingestion is not malware scanning.

`source_digest` is SHA-256 of the UTF-8 encoding of the validated source string. It is not a hash of the HTTP JSON bytes. The normalized declared media type is part of the staged submission digest and is not a Goal Lock field. The same source text declared as `text/plain` and as `text/html` are different idempotent submissions. Budgets are the single table in the module specification. Content responses stay JSON text with `nosniff`. Submitted HTML is not returned as `text/html`.

Additional pre-accept codes, with no run and no inspection audit:

| Status | Code                           | When                                                                                                                                       |
| ------ | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 422    | `unsupported_media_type`       | Declared type outside the five                                                                                                             |
| 422    | `malformed_content`            | Malformed JSON, duplicate keys, non-finite numbers, invalid structure, malformed quoted-printable, or an email leaf that does not decode   |
| 422    | `unsupported_embedded_content` | An embedded MIME leaf, charset, or transfer encoding outside the supported set                                                             |
| 422    | `input_limit`                  | JSON nesting, JSON members, HTML tags or attributes, email header or MIME part budget, derived representation count, or derived text bytes |
| 413    | `input_limit`                  | Goal bytes, source bytes, or the existing 512 KiB BFF body                                                                                 |

Post-accept ingestion failure is a persisted `FAILED` run whose `failure` is `parser_limit_exceeded`, `ingestion_incomplete`, `source_integrity_failure`, or `canonicalization_failure`. `parser_limit_exceeded` is the defense-in-depth code for a budget that validation already proved, and for later bounded Base64 derivation. It does not enter `PROPOSING`, call the model, or ALLOW. `unsupported_embedded_content` is not a run-failure code. No new route, multipart body, or upload is added. The BFF stays JSON, 512 KiB, and GET/POST only. A pre-accept 4xx does not consume the 30 accepted-run quota.

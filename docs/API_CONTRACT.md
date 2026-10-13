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

| Method | Path                                      | Success | Notes                                                                |
| ------ | ----------------------------------------- | ------- | -------------------------------------------------------------------- |
| GET    | `/health/live`                            | 200     | Process liveness. Not a product authorization route                  |
| GET    | `/health/ready`                           | 200     | PostgreSQL reachable and revision `0002_worker_claim`. Otherwise 503 |
| GET    | `/api/v1/me`                              | 200     | Principal, access, workspaces, and the support-triage template       |
| POST   | `/api/v1/runs`                            | 202     | Requires `Idempotency-Key`, `confirmed: true`, and `sanitized: true` |
| GET    | `/api/v1/runs?workspace_id=&before=`      | 200     | Newest 25. `next_cursor` is set only when the page is full           |
| GET    | `/api/v1/runs/{run_id}`                   | 200     | Run, Goal Lock, analysis, findings, action, review, ticket, sources  |
| GET    | `/api/v1/runs/{run_id}/events?after=`     | 200     | Up to 100 events with `sequence` greater than `after`                |
| GET    | `/api/v1/runs/{run_id}/content/{node_id}` | 200     | Active content for a visible run. Expired content is 410             |
| POST   | `/api/v1/runs/{run_id}/cancel`            | 200     | Originator only                                                      |
| POST   | `/api/v1/reviews/{review_id}/decision`    | 200     | Body is the 64-character digest and `approve` or `reject`            |
| GET    | `/api/v1/tickets/{ticket_id}`             | 200     | Ticket fields plus `verified_at` from the execution                  |

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

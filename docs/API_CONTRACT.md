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

| Method | Path                                                       | Success | Notes                                                                            |
| ------ | ---------------------------------------------------------- | ------- | -------------------------------------------------------------------------------- |
| GET    | `/health/live`                                             | 200     | Process liveness. Not a product authorization route                              |
| GET    | `/health/ready`                                            | 200     | PostgreSQL reachable and revision `0007_lineage_execution_lookup`. Otherwise 503 |
| GET    | `/api/v1/me`                                               | 200     | Principal, access, workspaces, and the support-triage template                   |
| POST   | `/api/v1/runs`                                             | 202     | Requires `Idempotency-Key`, `media_type`, and `confirmed: true`                  |
| GET    | `/api/v1/runs?workspace_id=&before=`                       | 200     | Newest 25. `next_cursor` is set only when the page is full                       |
| GET    | `/api/v1/runs/{run_id}`                                    | 200     | Run, Goal Lock, analysis, findings, action, review, ticket, sources, edges       |
| GET    | `/api/v1/runs/{run_id}/events?after=`                      | 200     | Up to 100 events with `sequence` greater than `after`                            |
| GET    | `/api/v1/runs/{run_id}/content/{node_id}`                  | 200     | Active content for a visible run. Expired content is 410                         |
| GET    | `/api/v1/runs/{run_id}/lineage`                            | 200     | Run lineage. Structural metadata only. See the lineage section                   |
| GET    | `/api/v1/runs/{run_id}/lineage/nodes/{node_id}?direction=` | 200     | One content node with bounded ancestry and descendants                           |
| GET    | `/api/v1/runs/{run_id}/lineage/actions/{action_id}`        | 200     | One action's causal path                                                         |
| POST   | `/api/v1/runs/{run_id}/cancel`                             | 200     | Originator only                                                                  |
| POST   | `/api/v1/reviews/{review_id}/decision`                     | 200     | Body is the 64-character digest and `approve` or `reject`                        |
| GET    | `/api/v1/tickets/{ticket_id}`                              | 200     | Ticket fields plus `verified_at` from the execution                              |

The BFF allows GET and POST only. Its generic same-origin proxy already forwards the three lineage GET paths and the `direction` query unchanged, with the server-side token and a fresh `X-Request-ID`, and it adds no body for a GET. No BFF code was added for lineage. A foreign origin on POST is `403 invalid_origin`. Bodies larger than 512 KiB are `413 input_limit`. A non-JSON upstream body is `502 invalid_upstream_response`. Upstream timeout is `504 api_timeout`.

## Status semantics

| Status | Codes used by the implementation                                                                                                |
| ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| 401    | `authentication_required`                                                                                                       |
| 403    | `invalid_origin`, `self_review_prohibited`                                                                                      |
| 404    | `not_found` for a missing object, inactive membership, or wrong workspace (and, from M004 Slice D, inactive workspace on reads) |
| 409    | `idempotency_conflict`, `review_stale`                                                                                          |
| 410    | `content_expired`                                                                                                               |
| 413    | `input_limit`                                                                                                                   |
| 422    | `invalid_input`, `empty_input`                                                                                                  |
| 429    | `workspace_rate_limit` when a workspace has 30 runs in the last hour                                                            |
| 500    | `internal_error`                                                                                                                |
| 502    | `invalid_upstream_response`                                                                                                     |
| 503    | `database_not_configured`, `database_unavailable`, `identity_unavailable`, `api_not_configured`, `api_unavailable`              |
| 504    | `api_timeout`                                                                                                                   |

Review eligibility is a boolean on the run payload. It is true only when the review is undecided, unconsumed, unexpired, the caller is not the originator, and the caller is an active reviewer in that workspace. The UI must not infer eligibility.

Cancel updates a non-terminal run to `CANCELLED` and audits it. The response `state` is the persisted state. If the run is already terminal, the row is left unchanged and the body returns that terminal state, not a new `CANCELLED` claim. Cancelling an already `CANCELLED` run is idempotent and does not write another audit event.

A full event page's `next_cursor` is the last sequence. An empty page returns the requested `after` cursor. Run-list `before` is a timestamp, not an opaque token.

## Run failure codes for model evidence and lineage

A persisted `FAILED` run carries a stable `failure` code on the run payload. These are run failure codes, not HTTP status codes, and no new route, field, or status exists for them. Two codes were added with M004 Slice C1:

| Code                     | Meaning                                                                                                                                                                                                                                                                             |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `invalid_model_evidence` | A model proposal or finding cited an evidence id that is malformed, over the bound, outside the run or workspace, not among the sources supplied to the model, or whose quote is absent. Nothing from the result was persisted and the guard never saw it. It is not a policy BLOCK |
| `lineage_write_failure`  | A required structural lineage write was rejected by a lineage integrity rule, or the server-side producer provider, model, or prompt version was unusable. The authorization or result transaction rolled back, so no ticket, execution, or decision survives                       |

`lineage_write_failure` does not mean a general database failure. A statement timeout, cancellation, lock failure, lost connection, or shutdown, a ticket failure, a provider failure, and `invalid_model_evidence` keep their own codes. A database failure that is not a lineage integrity failure ends the run as `worker_failure`. The run payload itself does not expose guard decisions, producer provenance, or review timestamps. The lineage endpoints below do.

No other product endpoints are implemented.

## Lineage endpoints (IMPLEMENTED in M004 Slice E)

Three authenticated, read-only GET endpoints expose the internal lineage read service (`lineage_read`, `lineage_assemble`, `lineage_graph`). They are run-centric. There is no cross-run, workspace-wide, or global lineage query, and no UI. Lineage is evidence of what happened. It is never an input to authorization, review eligibility, or execution, and `decide_review` and `cancel` are unchanged.

| Path                                                      | Response model      | Content                                                                                                           |
| --------------------------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `/api/v1/runs/{run_id}/lineage`                           | `RunLineage`        | The whole bounded run lineage                                                                                     |
| `/api/v1/runs/{run_id}/lineage/nodes/{node_id}?direction` | `NodeLineageView`   | One content node, its bounded walk, the edges among them, its findings, and the source, retention, bounds context |
| `/api/v1/runs/{run_id}/lineage/actions/{action_id}`       | `ActionLineageView` | One action's proposal, evidence, producer, decisions, review, execution, ticket reference, stage, and path        |

**Identity.** `run_id`, `node_id`, and `action_id` are persisted ids, without the entity prefix. Response entities use stable prefixed ids (`goal_lock:`, `content:`, `edge:`, `finding:`, `proposal:`, `guard_decision:`, `review:`, `execution:`, `ticket:`). A caller strips the prefix to request a focused view. A prefixed id in a path is a `404 not_found` at the API and a `400 invalid_path` at the BFF.

**Visibility.** Each read uses the canonical rule: active membership, active workspace, matching workspace and run. The trusted run row supplies the workspace and run id for every query, and no client value takes part. A missing run, a foreign run, an inactive membership, an inactive workspace, a missing node or action, and a node or action of another run or workspace are the same `404 not_found` body. There is no `403` for a guessed id. A caller-supplied `workspace_id` query parameter or header has no effect.

**Input.** `direction` is `ancestors`, `descendants`, or `both` (default `both`). Any other value is `422 invalid_input`. No route accepts a depth, limit, page size, or bound switch. Unknown query parameters are ignored. The server owns every bound: nodes 300, edges 300, transform steps 1200, findings 2730, actions 8, decisions 16, reviews 8, executions 8, tickets 8, evidence ids 16, traversal depth 3.

**Status and headers.** `200`, `401 authentication_required`, `404 not_found`, `422 invalid_input`, and `503 database_not_configured` use the existing error shape. A database that is configured but unreachable is not mapped to 503 by the API today and returns `500 internal_error`, as for every other route. That split is repository-wide, not lineage-specific. Every response is `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`, and echoes `X-Request-ID`. A stored anomaly is never an HTTP error. It is reported in the body. A successful lineage read emits one `lineage_read_completed` key=value log on the existing API logger. A 404 is not logged.

**Truncation.** A reached bound still returns `200`. `bounds.truncated` is `true`, `bounds.truncated_sets` names each capped set, `bounds.caps` and `bounds.observed` give the caps and loaded counts, and an `integrity` entry with code `bound_exceeded` and status `unverifiable` is present. Checks that need a capped set are `unverifiable`, never falsely `inconsistent`. The focused views carry the same `bounds`. A traversal that was clipped by depth or node cap carries `truncated: true` on that walk. Slice F proved every still-supported write path (M002 legacy inspection, M003 secure ingestion, M004 writers) persists at most 273 nodes and 3 actions, below the server caps of 300 and 8. Focused `404` is therefore existence or visibility, not cap truncation, under current contracts. The implementation would still report `404` if a node were omitted from the capped set; no still-supported writer can produce that omission. Findings remain a diagnostic set whose cap is above the legal maximum but may still truncate if constructed above it.

**Metadata only.** The responses carry no content body, ticket title or body, finding explanation or quote, model summary, model reasoning, raw provider response, prompt text, or SQL. Findings carry `family`, `origin`, offsets, and `version`. Tickets carry identity only. The producer carries the recorded provider, requested model, prompt version, and opaque response id (or `state: not_recorded` with null fields). The response id is an opaque JSON string. It is never altered, escaped, or interpreted as markup. Audit events are not read.

**Run response.** `run`, `read_time`, `goal_lock`, `source_binding`, `contents`, `edges` (with `steps` and `steps_state`), `findings`, `actions` (each with `stage`, `proposal`, `decisions`, `review`, `execution`, `ticket`, `path`), `relationships` (`kind`, `source`, `target`, `basis`), `integrity` (`code`, `status`, `subject`), `retention`, and `bounds`. Ordering is explicit: contents by creation time and id, edges by parent and child, steps by index, findings by node, offsets and id, actions by creation time and id, decisions by ordinal, relationships by kind, source, target and basis, and integrity by code, subject and status. `read_time` is the database clock at the read and is the only field that differs between two reads of unchanged data.

**Node response.** `run`, `read_time`, `direction`, `node`, `ancestors` and `descendants` (a walk or `null` when not requested, with `nodes` as `[entity id, depth]` ordered by depth then id), `related`, `edges`, `findings`, `citing_proposals`, `relationships`, `source_binding`, `retention`, `integrity`, and `bounds`. `integrity` holds the findings that name an entity in the view plus every run-level finding.

**Action response.** `run`, `read_time`, `goal_lock`, `source_binding`, `action`, `evidence`, `findings` (stored on the cited evidence, a structural co-location and not a record of model reliance), `relationships`, `retention`, `integrity`, and `bounds`. Other actions of the run are not included, even when they cite the same evidence.

**Retention.** `retention.state` is one of `available`, `expired_body_pending_deletion`, `inconsistent`, or `unverifiable`. `removed_by_retention` is reserved in the schema and is never emitted, because no persisted fact proves that retention deleted content. An absent source is `inconsistent` before the run could be eligible for retention (24 hours after run creation, with no grace period) and `unverifiable` after. No deleted graph is synthesized.

**Legacy and missing facts.** A fact the database never recorded is `not_recorded` and is not an anomaly: producer metadata (`producer.state`), guard decision history (`decisions` is empty and `stage` may be `latest_only`), the execution authorization link (`execution.authorization: not_recorded`, with a `execution_authorized_by` relationship whose `target` is `null` and `basis` is `not_recorded`), and review timestamps (`review.not_recorded` lists the null ones). A contradiction between recorded facts is `inconsistent`. A check that cannot be evaluated is `unverifiable`. These are distinct and are not collapsed into `null`.

**Verified path.** `action.path.complete` is `true` only when the stage is `verified` (an execution with a recorded `verified_at`), every path step is `consistent`, and no integrity finding names an entity on the path. The route does not rebuild it.

**OpenAPI.** The application does not serve OpenAPI or docs (`openapi_url` is disabled). The schema generated from the typed routes and models is tested, so the inputs and response models above are the same models the routes return, with no second hand-written schema.

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

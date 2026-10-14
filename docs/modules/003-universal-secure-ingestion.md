# Module 003 — Universal secure ingestion

**Specification. Slice A, as amended by A1 on 13 October 2026.** Slice B added schema `0003_secure_ingestion`. H1 added schema `0004_edge_steps`. H2A teaches the worker to canonicalize a staged M003 original. H2B mounts that path on `POST /runs`. The live body requires `media_type` and rejects `sanitized`. Supported live declarations are `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. Historical Module 002 rows stay readable. I1 is the authenticated Workbench submission surface. I2 is the authenticated run narrative: original and derived evidence, recorded transform steps, and legacy nulls shown as not recorded. Slice J is the public execution narrative and the Clerk auth shell. Slice K closed the module on 15 October 2026: the security shield, disposable-database browser proof, and `pnpm verify` passed, and INGEST-001 is IMPLEMENTED for the approved sentence.

Product, security, architecture, data, and API authority stay in the canonical contracts. This specification binds the M003 implementation. It does not override those contracts. [ADR 0003](../adr/0003-declared-format-ingestion.md) records the architecture decision. [Change record 0001](../change-control/0001-ingest-001-wording.md) records the future INGEST-001 wording.

## Position

"Universal" means a stable ingestion boundary and a typed adapter architecture. It does not mean every media type is supported.

The first production adapter set is exactly:

| Declared media type | Adapter id        | Version |
| ------------------- | ----------------- | ------- |
| `text/plain`        | `text_plain`      | 1       |
| `application/json`  | `json_structured` | 1       |
| `text/markdown`     | `markdown`        | 1       |
| `text/html`         | `html_inert`      | 1       |
| `message/rfc822`    | `email_rfc822`    | 1       |

These are text-family formats. They are not multimodal. MULTI-001 stays PLANNED. PDF, Office, image, audio, archive, URL, MCP, connector, and arbitrary binary support are not this module.

Authority stays outside the pipeline. Ingestion cannot create, expand, or waive a Goal Lock. Model output cannot repair a failed parse or mark incomplete evidence complete.

## Goal Lock

Each accepted run binds exactly one original source:

- `source_id` — the original content node
- `source_digest` — SHA-256 of the UTF-8 encoding of the validated source string

For this JSON submission API, that string is the source value after JSON parsing and adapter validation. The HTTP JSON serialization is not the digest. Two requests whose escaping differs, but whose validated source strings are equal, have the same `source_digest`. A canonical or decoded child is never the input.

The Goal Lock envelope does not gain a source list, an attachment list, or a media-type field. Media type is not authority. Derived representations are evidence under that original. They are not additional authority roots. A second original, or an attachment treated as its own authority root, requires a separate Architecture Change Request and ADR.

## Representations

| Kind             | Meaning                                                                    |
| ---------------- | -------------------------------------------------------------------------- |
| `original`       | Exact submitted text. Immutable. The Goal Lock source when it is the root. |
| `canonical_text` | Adapter-derived text linked to its parent.                                 |
| `decoded_text`   | Bounded Base64 child of a text representation.                             |
| `active_content` | Bounded active HTML text linked to its parent. Not authority.              |

Every node stores `trust = untrusted`. A transform never upgrades trust. Edges record `transform`, `version`, and `lossy`. Canonicalization that discards lexical form sets `lossy = true`. The original row remains.

There is one original per run. There is no client attachment array.

## Format selection

The client declares one allowlisted media type. That declaration selects the adapter. The adapter validates the body.

The server does not switch adapters because the body looks like a different format. Examples:

- `application/json` must pass the JSON rules below. It is not reclassified as `text/plain` when parsing fails.
- `message/rfc822` must satisfy the email adapter.
- `text/html` is handled only by `html_inert`.
- `text/plain` and `text/markdown` stay on the declared adapter. Markup inside them is untrusted text, not a reason to invoke `html_inert`.

A charset parameter of `utf-8` or `us-ascii` is accepted, compared case-insensitively. Any other parameter or charset is `malformed_content`. Comparison of the media type itself is case-insensitive, and the stored value is the lowercase allowlisted type.

High-confidence invalidity fails closed before a run exists. See the error table.

Declared type metadata may be stored on the original node. It is not a trust score and it is not authority. On that original, the declared media type and the representation kind are immutable. On a derived node, `parser_id` and `parser_version` are immutable. A derived node never becomes an authority root.

## Channel metadata

The client does not send a trust class. The live body is `goal`, `source`, `media_type`, and `confirmed`, plus the membership `workspace_id`. The workflow template is server-owned. `sanitized` is rejected; it is not a control, and it is not replaced by `source_class`. There is no file upload and no remote fetch.

The server records `channel` from the submission boundary. The only M003 path is authenticated `POST /api/v1/runs`, and that path records `user_paste`. `api_submission` and `connector` are names reserved for a later boundary. They are not accepted from the client, and they do not grant authority. `channel` is not a `0003_secure_ingestion` column and is not stored yet.

## UTF-8 and Unicode

- The original must be strict UTF-8. Invalid sequences are `malformed_content` and create no run.
- U+0000 is rejected with `malformed_content` and creates no run. PostgreSQL `text` cannot store NUL without altering the original, and the original must not be altered to fit the column.
- The original is not normalized (no NFC, NFKC, or compatibility folding). `source_digest` is SHA-256 of the UTF-8 encoding of the validated source string, not of the raw HTTP body.
- A leading U+FEFF is kept in `text/plain`, `text/markdown`, and `text/html`. It is rejected inside `application/json` and `message/rfc822` as `malformed_content`.
- Characters are not stripped from a stored original. U+0001–U+0008, U+000B, U+000C, U+000E–U+001F, U+007F, bidi controls U+202A–U+202E and U+2066–U+2069, and these invisible characters are deterministic inspection evidence: U+00AD, U+200B–U+200F, U+2028, U+2029, U+2060–U+2064, U+FEFF. The finding family is `Encoded Instructions`. The explanation states that the character was preserved, not removed.
- That finding uses the existing uncertainty rule, so the run can require review. It does not change `trust`.
- JSON strings follow the JSON grammar. Unescaped controls inside a JSON string are `malformed_content`.

## JSON (`application/json`)

- Persist the original submitted text and its digest.
- Reject malformed JSON, duplicate object keys at any depth, and non-finite numbers (`NaN`, `Infinity`, `-Infinity`), including non-standard tokens and numbers that overflow to a non-finite value.
- Nesting depth is the number of objects and arrays open at once. A scalar root has depth 0. Depth above 32 is pre-accept `input_limit`.
- A JSON member is one object key/value pair or one array element. The count is the sum over the whole document. A scalar root adds no member. More than 2,048 members is pre-accept `input_limit`.
- Integer tokens without a fraction or exponent stay integers. Finite fractional or exponent tokens may be re-encoded.
- Nesting and member caps are in the budget table. Exceeding either is pre-accept `422 input_limit` and creates no run.
- The canonical child is UTF-8 JSON with object keys sorted by Unicode code point, separators `,` and `:`, and `ensure_ascii` false. This matches the repository's existing canonical JSON encoding.
- The edge is `transform = json-canonical`, `version = 1`, `lossy = true`, because whitespace and key order are not preserved.
- The Goal Lock `source_digest` remains the digest of the validated original string. Canonical JSON does not replace it.

## HTML (`text/html`)

This is inert extraction, not sanitized HTML. `html_inert` version `1` implements it. `POST /runs` calls it when the client declares `text/html` and validation succeeds.

- Persist the original as untrusted text.
- Do not execute script, style, or event handlers.
- Do not fetch URLs, resolve remote entities, or parse with an XML/DTD parser.
- Do not render submitted HTML with `dangerouslySetInnerHTML` or as `text/html`.
- Use the Python standard-library HTML parser only. Its tolerance is not validity, safety, or trust, and it does not select another adapter.
- A start tag is one parser start tag. An attribute is one attribute on a start tag. The counts are cumulative. More than 2,000 start tags or 8,000 attributes is pre-accept `422 input_limit` and creates no run.
- The visible child (`representation_kind = canonical_text`, `transform = html-visible-text`, `version = 1`, `lossy = true`) is decoded text outside `script`, `style`, and `template`. Comments are not visible text. Block tags and `br` insert a separator, and the child then collapses each whitespace run to one U+0020. Inline tags do not insert a separator, so `<em>c</em>at` stays `cat`. This is not browser layout. Entities follow the standard-library parser.
- The active child (`representation_kind = active_content`, `transform = html-active-content`, `version = 1`, `lossy = true`) records, in document order, non-empty `script`, `style`, and `template` bodies, comments, `on*` attributes, and the attributes `href`, `src`, `srcset`, `action`, `formaction`, `srcdoc`, `cite`, `data`, `poster`, `background`, `longdesc`, `ping`, `alt`, `title`, `value`, `placeholder`, `aria-label`, and `style`. `data` is that URL attribute, not every `data-*` attribute. `style` is copied as text and is not fetched or executed. A `meta` element whose `http-equiv` is `refresh` also records that `http-equiv` and `content` pair. Other `content` attributes are not collected. `srcdoc` is copied as text and is not parsed as a second document. URLs are not fetched.
- An empty visible result or an empty active result is omitted. It is not stored as an empty node.
- Active content is evidence. It does not allow, block, or require review by itself. Action Guard remains the enforcement boundary.
- Pre-accept validation builds the deterministic children in memory. If their count exceeds 32 derived representations, excluding the original, or their UTF-8 bytes exceed 131,072, the result is `422 input_limit` and no run is created. Canonicalization still refuses the same condition with `parser_limit_exceeded` if it is reached after acceptance. The adapter does not truncate and does not drop the active child to fit.
- Children that exist link to the original. The original remains the Goal Lock root.

## Email (`message/rfc822`)

`email_rfc822` version `1` is implemented and is not called by `POST /runs`. No remote fetch and no attachment file is written. `message/external-body` is unsupported embedded content.

- The header budget is the UTF-8 byte length of the original header section from the start through the first `\r\n\r\n` or `\n\n`, whichever occurs first, including that separator. If neither separator exists, the whole source is the header section. More than 16,384 bytes is pre-accept `422 input_limit`.
- The part budget counts every MIME entity below the top-level message, including multipart containers and leaves. The top-level message does not count. More than 32 is pre-accept `422 input_limit`. Nested containers count, so nesting cannot hide parts. There is no separate email nesting-depth integer.
- A nested `message/rfc822`, including a top-level body whose `Content-Type` is `message/rfc822`, is `422 unsupported_embedded_content`. It is not traversed.
- `multipart/*` is a container. Every leaf is visited. `multipart/alternative` does not drop a sibling.
- A leaf is supported only for `text/plain`, `text/html`, `text/markdown`, or `application/json`. A missing `Content-Type` on a non-multipart entity is `text/plain` by the RFC 2045 default. That default is not content sniffing.
- A missing charset means `us-ascii`. `utf-8` and `us-ascii` are supported. Any other charset is `unsupported_embedded_content`. Bytes that do not decode under the selected charset are `malformed_content`. Invalid bytes are not replaced.
- Transfer encodings are absent, `7bit`, `8bit`, `quoted-printable`, and `base64`. `binary` and any other token are `unsupported_embedded_content`. A duplicate encoding header is `malformed_content`. `base64` or `quoted-printable` on a multipart container is `malformed_content`. Quoted-printable is checked before decode: `=` must introduce two hexadecimal digits or a soft line break (`=\n` or `=\r\n`). Any other escape is `malformed_content`. Line length is not an extra rejection. Invalid bytes are not replaced.
- A leaf that does not decode, including strict Base64, is `malformed_content`. The whole message fails. The leaf is not dropped.
- Defects attached by the standard-library parser are fatal `malformed_content`, except `ObsoleteHeaderDefect`, `NonPrintableDefect`, `NonASCIILocalPartDefect`, and `InvalidDateDefect`. Any other defect, including an unknown class, a missing boundary, or an unclosed boundary, is fatal. There is no partial message.
- A leading U+FEFF is `malformed_content`.
- When a selected header is present, one lossy `canonical_text` child records it. The selected names are `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, `Message-ID`, and `Content-Type`. The edge is `transform = email-headers`, `version = 1`, `lossy = true`. A missing `Bcc` is not invented. A present header is untrusted text, not an authenticated identity.
- Leaves reuse the existing adapters. The flattened edges are `email-part-text`, `email-part-markdown`, `email-part-json`, `email-part-html-visible`, and `email-part-html-active`, all version `1` and `lossy = true`. Each child also carries an ordered `transform_steps` chain. A text or Markdown leaf is `email-part-decode` then its part transform. A JSON leaf is `email-part-decode` then `json-canonical`. An HTML child is `email-part-decode` then `html-visible-text` or `html-active-content`. Parser id and version stay with the leaf adapter. The chain is not a database id. The adapter does not build database rows.
- A structurally valid supported leaf whose decoded body is empty or whitespace-only under the text, Markdown, or HTML emptiness rule adds no derived node. That leaf was still traversed and validated. It is not unsupported content and it is not dropped as unknown. This exception is only for a leaf inside an email. A top-level `text/plain` or `text/markdown` submission that is empty or whitespace-only remains `empty_input`.
- Pre-accept validation proves the full deterministic result, including child canonicalization, the aggregate derived representation count, and the aggregate derived UTF-8 bytes. Exceeding either derived budget is `422 input_limit` and would create no run. The original message is not one of the 32 derived representations. Canonicalization still applies `parser_limit_exceeded` if that proof is somehow bypassed. The adapter does not truncate or drop a later part.
- The original RFC822 string remains the Goal Lock root.

## Plain text and Markdown

`text_plain` version `1` and `markdown` version `1` validate UTF-8, reject NUL, and keep the declared adapter. Content is not sniffed into another adapter. Markdown is not rendered to HTML. The original is the text representation. Both adapters return no derived representation: there is no canonical copy of the same text. Further children come only from the bounded Base64 decoder. Neither adapter is called by `POST /runs` yet.

## Base64 children

After a representation is accepted as complete text, the existing bounded decoder may add `decoded_text` children: at most 16 matches per representation, exact standard Base64, UTF-8, printable, inside the derived-byte and depth caps. A match that does not decode is skipped. Exceeding a cap sets `parser_limit_exceeded`, `complete = false`, and `FAILED`, and does not call the model. Decoder id remains `bounded-decoder`, version `1`, edge `transform = base64`, `lossy = false` when the decode is exact.

## Versioned ingestion security budgets

This is the only normative budget table. Other contracts point here. Changing a value requires focused boundary and security tests. The implementation defines these integers once and adapters read that one source. They are not adapter-local literals, and they are not casually user-configurable. The Module 002 worker lease is a workflow lease, not a row in this table.

| Budget                        | Value   |
| ----------------------------- | ------- |
| Goal bytes                    | 4,096   |
| Source bytes                  | 65,536  |
| Derived text bytes            | 131,072 |
| Derivation depth              | 2       |
| Base64 matches/representation | 16      |
| JSON nesting depth            | 32      |
| JSON members                  | 2,048   |
| HTML start tags               | 2,000   |
| HTML attributes               | 8,000   |
| Derived representations/run   | 32      |
| Transform steps/edge          | 4       |
| Email header bytes            | 16,384  |
| Email MIME parts              | 32      |
| Proposal evidence IDs         | 16      |
| BFF request body              | 512 KiB |
| Accepted runs/workspace/hour  | 30      |
| Originals/run                 | 1       |
| Network fetches               | 0       |
| Archive/decompression         | 0       |

The 30 accepted runs per workspace per hour are a business quota on created runs. A pre-accept 4xx does not create a run and does not consume that quota. Derived representations/run counts derived children only. The one immutable original is not part of that 32. The field is `derived_representations_per_run`. Transform steps/edge is the maximum ordered chain on one edge. The field is `transform_steps_per_edge`. It is not a representation count. The body cap and the parser budgets bound the cost of one attempt. They do not prevent generic or distributed rejected-request abuse. That protection stays PARTIAL under SEC-001. M003 does not add a distributed rate limiter. Production-scale distributed rate protection belongs to later enterprise security infrastructure unless an earlier measured need requires it.

## Acceptance lifecycle

For this 64 KiB text-family scope the order is fixed:

authenticate → authorize workspace → envelope and size validation → declared media-type allowlist → bounded pure adapter validation → accept the run, the original, and the Goal Lock → worker canonicalization → derived evidence → deterministic inspection → model.

Adapter validation before acceptance is pure, side-effect free, bounded, deterministic, and free of network calls, database writes, and model calls. It may build the deterministic derived children in memory. A condition that validation can decide, including derived representation count and derived UTF-8 bytes, does not become an ordinary post-accept input error. The one original source is outside the 32 derived representations. `parser_limit_exceeded` remains the post-accept backstop when a later derivation, including bounded Base64, exceeds a budget or the pre-accept proof is violated.

## Errors

Pre-accept responses use the existing JSON error shape. They create no run, no Goal Lock, no content node, no model call, and no audit event that claims inspection. The log may include `correlation_id`, the error code, the declared type, and `byte_size`. It must not include the source text, and it must not present the raw HTTP body as `source_digest`.

| Condition                                                                                                                                                                                                                         | HTTP | Code                           | Run                    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ------------------------------ | ---------------------- |
| Declared type outside the five                                                                                                                                                                                                    | 422  | `unsupported_media_type`       | none                   |
| Malformed JSON, duplicate JSON keys, non-finite JSON numbers, invalid UTF-8, NUL, structurally invalid RFC822/MIME, malformed quoted-printable, email leaf decoding failure, disallowed top-level charset or media-type parameter | 422  | `malformed_content`            | none                   |
| Unsupported embedded MIME leaf, charset, or transfer encoding                                                                                                                                                                     | 422  | `unsupported_embedded_content` | none                   |
| JSON nesting, JSON members, HTML start tags, HTML attributes, email header bytes, email MIME part count, derived representation count, or derived text bytes over the budget table                                                | 422  | `input_limit`                  | none                   |
| Goal or source bytes over the budget table, or BFF body over 512 KiB                                                                                                                                                              | 413  | `input_limit`                  | none                   |
| Empty or whitespace-only source                                                                                                                                                                                                   | 422  | `empty_input`                  | none                   |
| Schema failure, including `sanitized` or `source_class` after removal, or more than one original                                                                                                                                  | 422  | `invalid_input`                | none                   |
| Same idempotency key, different submission digest                                                                                                                                                                                 | 409  | `idempotency_conflict`         | existing row unchanged |

`text/plain` and `text/markdown` are not reclassified by sniffing. `text/html` stays on `html_inert`. The declared allowlisted adapter remains selected.

Post-accept failure is only a processing or invariant failure after a run and Goal Lock exist. It is not a repeat of a validation result. `runs.state` is `FAILED`, `runs.complete` is false, and the run does not enter `PROPOSING`. There is no model call, no ALLOW, and no business side effect. There is no quarantine state.

| Condition                                                                                                                                                                                                                                                    | `runs.failure`             | Audit                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------- | ---------------------- |
| Worker derivation exceeds derived bytes, depth, Base64 matches, or representation count after validation accepted the source. This includes a deterministic adapter budget that validation already proved and that is reached again only as defense in depth | `parser_limit_exceeded`    | `INGESTION_INCOMPLETE` |
| Worker canonicalization cannot finish the derived evidence, and the cause is not a budget, digest, or internal fault                                                                                                                                         | `ingestion_incomplete`     | `INGESTION_INCOMPLETE` |
| Persisted original digest differs from Goal Lock `source_digest`                                                                                                                                                                                             | `source_integrity_failure` | existing failure audit |
| Parser or canonicalizer fails internally after acceptance                                                                                                                                                                                                    | `canonicalization_failure` | `INGESTION_INCOMPLETE` |

`unsupported_media_type` and `unsupported_embedded_content` are only pre-accept codes. They are not run-failure codes.

## Evidence completeness

`runs.complete` may become true only when every accepted representation was produced inside the budgets and every email leaf was supported and represented. Deterministic findings do not by themselves clear or set completeness.

The model is called only from `PROPOSING` after a complete inspection. `FAILED` from ingestion does not enter `PROPOSING`.

User-visible labels come from persisted fields: a stored original, `complete`, `runs.failure`, and the inspection audit type. The labels scanned, safe, verified content, and malware-free are forbidden. Content is not quarantined unless a future schema stores that disposition. M003 does not.

## Idempotency

One submission key per workspace and principal. The submission digest is the canonical digest of the client object: workspace, template, goal, validated source string, `confirmed`, and the normalized declared media type. Normalization is the lowercase allowlisted type with parameters removed. Server `channel` is not part of that object. The same source string with `text/plain` and with `text/html` are different submissions. That binding does not add the media type to the Goal Lock and does not enlarge authority.

The same key and digest returns the original run. A different digest is `idempotency_conflict`. A pre-accept 422 does not consume the key.

Removing `sanitized` changes the client object. Keys already stored with the old object do not match a body that omits the field. Clients use a new key. The implementation must not ignore `sanitized` in order to keep the old digest, because ignoring it would keep a false control in the contract.

## Parser version

Parser version is not part of the Goal Lock, `source_digest`, or the submission digest. It identifies the implementation that produced a derived interpretation. An accepted or idempotent run is not silently reprocessed because a newer adapter version is deployed. Historical evidence stays immutable. Reprocessing under a newer parser version has to be explicit, through a future replay capability, and has to write new immutable evidence. Module 003 does not implement that replay.

## Retention and tenancy

Retention is unchanged: content nodes expire after 24 hours; audit events are eligible for deletion after 30 days; the operator command performs the delete. New node columns follow the node. There is no separate binary retention, because no binary is stored.

A principal reads content only through an active membership in that workspace. Missing membership and missing objects stay non-enumerating `not_found`. Ingestion does not add a cross-workspace read.

## Audit and observability

`RUN_ACCEPTED` remains the acceptance event. Its detail adds `declared_media_type`, `byte_size`, `channel`, and `parser_id`. It does not add source text.

| Event                     | When                | Detail                                                            |
| ------------------------- | ------------------- | ----------------------------------------------------------------- |
| `INGESTION_CANONICALIZED` | a child is stored   | parent id, child id, transform, lossy, parser id, parser version  |
| `INGESTION_INCOMPLETE`    | post-accept failure | reason code, declared type, parser id, parser version, part count |

No `INSPECTION_COMPLETED` event is written for a 422 or for an incomplete run. Worker and API logs add correlation id, run id, workspace id, principal id, declared type, parser id and version, representation count, complete flag, failure code, `retryable=false` for parse failures, elapsed milliseconds, byte size, and a digest prefix. They do not add source text, tokens, or SQL parameters.

OBS-001 stays PARTIAL. These fields are not a metrics platform.

## Persistence

PostgreSQL `text` remains the store for this bounded text family. Revisions `0003_secure_ingestion` and `0004_edge_steps` are applied. `0001_security_slice`, `0002_worker_claim`, and `0003_secure_ingestion` were not rewritten. The ingestion kernel reads this budget table from one immutable source. All five contracted adapters are registered. `accept_declared_submission` validates with the exact adapter and inserts the original node with `declared_media_type`, `representation_kind = original`, the declared charset when the client sent one, `byte_size` as the UTF-8 length of the validated source, and null parser id and version. It does not insert derived children or edges. The live `POST /runs` route calls that function. A historical Module 002 node keeps those columns null. A missing charset parameter is stored as null. It is not filled in as `utf-8`. When the worker claims a staged original, it rechecks the persisted root, canonicalizes with the adapter for the stored media type, and commits the derived nodes, summary edges, and ordered steps in one transaction before inspection can reach the model. A legacy original, whose ingestion metadata is null, keeps the Module 002 inspection path. New Base64 edges record one `base64` / `1` step. Historical edges stay null.

`0003_secure_ingestion` adds nullable columns on `content_nodes`: `declared_media_type`, `representation_kind`, `parser_id`, `parser_version`, `charset`, and `byte_size`. They are written at insert when the staged path accepts a run. Existing rows stay NULL, meaning not recorded. They are not backfilled. `validated_media_type` and `channel` are not columns in this revision. The staged acceptance audit records server-derived `channel = user_paste`. The client cannot send it. The immutability trigger continues to reject every update. `trust` stays constrained to `untrusted`. `content` stays `text NOT NULL`. These columns are storage only. They do not make INGEST-001 IMPLEMENTED.

No `bytea`, filesystem object, S3, R2, MinIO, Redis, or Kafka. A ContentStore protocol is not added while PostgreSQL is the only writer. A later binary format needs its own ADR before object storage.

## Transform chain and the edge row

`content_edges.transform` and `content_edges.version` are the summary of the whole parent-to-child derivation. `content_edge_steps` is the exact ordered interpretation history. The summary is not defined as the final step. Equality between the summary and the last step is not required. A valid future chain can summarize as `email-part-json` version `1` while the steps are `email-part-decode` version `1` and then `json-canonical` version `1`.

`transform_step_count` NULL means the chain was not recorded. The read is `transform_steps = null`. It is not `[]` and it is not a one-step chain copied from the summary. A count of N, from 1 through 4, means exactly N ordered step rows with indexes 1 through N. Historical edges, including existing `base64` edges, stay NULL. They are not backfilled.

The worker records provenance by inserting `transform_step_count` equal to the length of the actual `TransformStep` chain and inserting those steps. It does not synthesize a chain from the edge summary. If a recorded derivation has no actual steps, it fails closed. A new Base64 edge records summary `base64` / `1`, count `1`, and step `base64` / `1`. Historical edges stay null.

`parser_id` and `parser_version` on the child say which adapter produced that representation. The step rows say what happened from parent to child. Both stay. The public edge response returns `transform_steps` from those rows. A null count is `null`. The summary fields stay separate.

The bound is `transform_steps_per_edge` = 4 in the one budget source. The database checks use that same maximum. Chain completeness is enforced at transaction commit. Node deletion cascades to the edge and then to its steps. Steps have no separate retention clock. Edge rows and step rows cannot be updated. Deletes remain available for retention.

Readiness requires `0004_edge_steps`.

## Capability status

| ID                                                       | Through implementation                           | At GREEN B, only with evidence               |
| -------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------- |
| INGEST-001                                               | IMPLEMENTED with the change-record 0001 sentence | IMPLEMENTED                                  |
| MULTI-001                                                | PLANNED                                          | PLANNED                                      |
| PROV-001, THREAT-001, UX-001, A11Y-001, OBS-001, SEC-001 | PARTIAL                                          | PARTIAL unless a later record says otherwise |

IMPLEMENTED does not mean every media type is supported. Malware scanning is not a capability of this module.

## Slices after A

| Slice | Work                                                                                | Not in the slice                            |
| ----- | ----------------------------------------------------------------------------------- | ------------------------------------------- |
| B     | Revision `0003_secure_ingestion`, readiness, NULL legacy, schema tests              | Parsers and routes                          |
| C     | Kernel: allowlist, budgets, registry, pre-accept error model. Routes stay unchanged | Silent sniffing; format parsers             |
| D     | `text_plain` version `1`. The paste path and `POST /runs` stay on Module 002        | Calling paste "email"; other format parsers |
| E     | `json_structured` version `1` and `markdown` version `1`, not on `POST /runs`       | HTML and email                              |
| F     | `html_inert` and `email_rfc822`, including unsupported-leaf failure                 | Fetch, PDF, Office                          |
| G     | Required `media_type`; remove `sanitized`; provenance and edges on the run payload  | Multipart upload                            |
| H     | Worker canonicalization, failure codes, audit, logs; no model when incomplete       | A new queue                                 |
| I     | I1 Workbench submission. I2 run narrative from persisted evidence and steps.        | File upload; Slice J                        |
| J     | Public execution narrative and Clerk auth shell. Lavender field is the pre-footer.  | Slice K; multimodal or multi-agent claims   |
| K     | Security shield, disposable-database browser proof, `pnpm verify`, GREEN B          | M004                                        |

Slice J preserves a separate light homepage hero. The lavender/violet field is only the pre-footer closing region: large editorial white type, one high-contrast call to action, wide whitespace, no card grid, immediately above the footer. The product UI stays on the paper, ivory, stone, champagne, ink, lavender, plum, copper, coral, amber, and rose palette. A supplied logo file, if one arrives later, is inspected and referenced from the canonical brand path. Slice A does not draw one.

## Release criteria

Slice A is complete when this specification and the contract deltas agree, and no runtime file has changed to implement them.

GREEN B for M003 additionally requires:

- Each of the five adapters has a production parser, validation, provenance, and tests on the real submit and worker path.
- An unsupported declared type returns 422 with no run, no envelope, and no model call.
- An email with an unsupported leaf, charset, or transfer encoding returns 422 `unsupported_embedded_content` and writes no run.
- The same validated source string submitted as `text/plain` and as `text/html` does not share an idempotency digest. `source_digest` matches across equivalent JSON escaping and does not hash the HTTP body.
- Budget integers are read from one canonical source.
- Malformed JSON, duplicate keys, non-finite numbers, invalid UTF-8, and NUL create no run.
- The stored original digest equals `source_digest`.
- Every child is `untrusted` and has a parent edge.
- Incomplete evidence cannot ALLOW.
- A body that still sends `sanitized` or `source_class` is `invalid_input`.
- No parser dependency beyond the Python 3.12 standard library.
- Tenant isolation, idempotency, and worker restart are tested on the disposable database.
- The UI does not display scanned, safe, or malware-free.
- INGEST-001 is IMPLEMENTED only with the change-record 0001 sentence. Slice K satisfied that record.

## Non-goals

PDF, Office, images, audio, archives, arbitrary binary upload, URL fetch, SSRF controls for a fetcher, MCP, connectors, malware scanning, object storage, cross-run deduplication, and a second Goal Lock source. No placeholder endpoint or control may imply that those exist.

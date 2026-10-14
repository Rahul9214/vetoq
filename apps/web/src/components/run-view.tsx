"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { AuditEvent, RunDetail } from "@/lib/contracts";
import {
  failureLabel,
  mediaLabel,
  outcomeDetail,
  outcomeTitle,
  reasonLabel,
  representationLabel,
  transformLabel,
} from "@/lib/run-narrative";
import {
  findingsStage,
  goalLockStage,
  guardStage,
  isTerminal,
  proposalStage,
  sourceStage,
} from "@/lib/run-state";

type Source = RunDetail["sources"][number];
type Edge = RunDetail["edges"][number];

function recorded(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === ""
    ? "Not recorded"
    : String(value);
}

function lockValue(lock: Record<string, unknown>, key: string): string | null {
  const value = lock[key];
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

export function RunView({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [content, setContent] = useState<Record<string, string>>({});
  const [openDetail, setOpenDetail] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [observedAt, setObservedAt] = useState<number | null>(null);
  const reviewHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cursor = 0;
    let delay = 1500;

    async function refresh() {
      try {
        const [detail, audit] = await Promise.all([
          api<RunDetail>(`/runs/${runId}`),
          api<{ items: AuditEvent[]; next_cursor?: number }>(
            `/runs/${runId}/events?after=${cursor}`,
          ),
        ]);
        if (!active) return;
        const replaceEvents = cursor === 0;
        setRun(detail);
        setEvents((current) =>
          replaceEvents ? audit.items : [...current, ...audit.items],
        );
        cursor = audit.next_cursor ?? cursor;
        setError("");
        delay = 1500;
        if (isTerminal(detail.state)) return;
        const wait = detail.state === "AWAITING_REVIEW" ? 15000 : delay;
        timer = setTimeout(() => void refresh(), wait);
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "run_unavailable");
        delay = Math.min(15000, delay * 2);
        timer = setTimeout(() => void refresh(), delay);
      }
    }

    void refresh();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (run?.state === "AWAITING_REVIEW") reviewHeading.current?.focus();
  }, [run?.state]);

  useEffect(() => {
    const timer = window.setTimeout(() => setObservedAt(Date.now()), 0);
    return () => window.clearTimeout(timer);
  }, [run?.review?.expires_at, run?.review?.decision]);

  async function loadContent(nodeId: string) {
    if (content[nodeId]) return;
    try {
      const result = await api<{ content: string }>(
        `/runs/${runId}/content/${nodeId}`,
      );
      setContent((current) => ({ ...current, [nodeId]: result.content }));
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "evidence_unavailable",
      );
    }
  }

  async function review(decision: "approve" | "reject") {
    if (!run?.review) return;
    setPending(true);
    setError("");
    try {
      await api(`/reviews/${run.review.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ digest: run.review.digest, decision }),
      });
      setRun(await api<RunDetail>(`/runs/${runId}`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "review_failed");
    } finally {
      setPending(false);
    }
  }

  async function cancel() {
    setPending(true);
    try {
      await api(`/runs/${runId}/cancel`, { method: "POST" });
      setRun(await api<RunDetail>(`/runs/${runId}`));
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "cancellation_failed",
      );
    } finally {
      setPending(false);
    }
  }

  if (error && !run) {
    return (
      <section className="system-failure" aria-labelledby="run-error-title">
        <p className="eyebrow">Protected evidence unavailable</p>
        <h1 id="run-error-title">This run could not be opened.</h1>
        <code>{error}</code>
      </section>
    );
  }

  if (!run) {
    return (
      <section className="loading-state" aria-live="polite" aria-busy="true">
        <span className="loading-pulse" aria-hidden="true" />
        <p>Reading persisted run evidence…</p>
      </section>
    );
  }

  const canCancel = !isTerminal(run.state) && run.state !== "AWAITING_REVIEW";
  const goal = String(run.goal_lock.goal ?? run.goal);
  const proposal = run.action?.proposal;
  const evidenceIds = (proposal?.evidence_ids ?? []).filter(
    (id) => typeof id === "string" && id.length > 0,
  );
  const verdict = run.action?.verdict;
  const sourcesById = new Map(run.sources.map((source) => [source.id, source]));
  const childIds = new Set(run.edges.map((edge) => edge.child_id));
  const edgesByParent = new Map<string, Edge[]>();
  for (const edge of run.edges) {
    const list = edgesByParent.get(edge.parent_id) ?? [];
    list.push(edge);
    edgesByParent.set(edge.parent_id, list);
  }
  const roots = run.sources.filter((source) => !childIds.has(source.id));

  return (
    <article className="run-narrative">
      <header className="run-hero">
        <div>
          <Link className="back-link" href="/">
            ← Security workbench
          </Link>
          <p className="eyebrow">Run</p>
          <h1>{outcomeTitle(run)}</h1>
          <p className="run-outcome">{outcomeDetail(run)}</p>
        </div>
        <div className="run-hero-state">
          <StatusBadge value={run.state} />
          <p className="run-identity">
            <span>{run.id}</span>
            <time dateTime={run.created_at}>
              Started {new Date(run.created_at).toLocaleString()}
            </time>
          </p>
          {canCancel ? (
            <button
              className="button button-secondary"
              disabled={pending}
              onClick={() => void cancel()}
            >
              Cancel run
            </button>
          ) : null}
        </div>
      </header>

      {error ? (
        <p className="notice notice-error" role="alert">
          The latest refresh failed: {error}
        </p>
      ) : null}
      {run.failure ? (
        <section className="notice notice-error" aria-label="Run failure">
          <strong>{failureLabel(run.failure)}</strong>
          <span className="run-code">{run.failure}</span>
          {run.state === "FAILED" && !run.ticket ? (
            <p>No execution is recorded for this run.</p>
          ) : null}
        </section>
      ) : null}

      <section className="run-stage" aria-labelledby="goal-title">
        <p className="run-stage-index">01 · Intent</p>
        <div>
          <h2 id="goal-title">Confirmed goal</h2>
          <p className="run-goal">{goal}</p>
          <p className="field-help">
            This is the outcome the run was allowed to pursue.
          </p>
          <StatusBadge value={goalLockStage(run)} />
        </div>
      </section>

      <section className="run-stage" aria-labelledby="authority-title">
        <p className="run-stage-index">02 · Authority</p>
        <div>
          <h2 id="authority-title">Granted authority</h2>
          <p className="field-help">
            This boundary was sealed for this run. Membership in another
            workspace does not widen it.
          </p>
          <dl className="authority-facts">
            <div>
              <dt>Tool</dt>
              <dd>{recorded(lockValue(run.goal_lock, "tool"))}</dd>
            </div>
            <div>
              <dt>Destination</dt>
              <dd>{recorded(lockValue(run.goal_lock, "destination"))}</dd>
            </div>
            <div>
              <dt>Writes</dt>
              <dd>{recorded(lockValue(run.goal_lock, "max_writes"))}</dd>
            </div>
            <div>
              <dt>Expires</dt>
              <dd>{new Date(run.expires_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Policy</dt>
              <dd>{recorded(lockValue(run.goal_lock, "policy_revision"))}</dd>
            </div>
            <div>
              <dt>Workspace</dt>
              <dd className="run-code">{run.workspace_id}</dd>
            </div>
          </dl>
          <TechnicalDetails title="Goal Lock record">
            <dl className="authority-facts">
              {(
                [
                  ["Principal", "principal"],
                  ["Template", "template"],
                  ["Tool version", "tool_version"],
                  ["Source", "source_id"],
                  ["Source digest", "source_digest"],
                  ["Proposal limit", "max_proposals"],
                ] as const
              ).map(([label, key]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd className="run-code">
                    {recorded(lockValue(run.goal_lock, key))}
                  </dd>
                </div>
              ))}
            </dl>
          </TechnicalDetails>
        </div>
      </section>

      <section className="run-stage" aria-labelledby="evidence-title">
        <p className="run-stage-index">03 · Evidence</p>
        <div>
          <h2 id="evidence-title">Evidence</h2>
          <p className="field-help">
            Original evidence and each derived record stay untrusted text.
            Relationships come from the recorded parent and child links.
          </p>
          <StatusBadge value={sourceStage(run)} />
          {roots.length ? (
            <ol className="evidence-tree">
              {roots.map((source) => (
                <EvidenceNode
                  key={source.id}
                  source={source}
                  edgesByParent={edgesByParent}
                  sourcesById={sourcesById}
                  content={content}
                  openDetail={openDetail}
                  onToggleDetail={(id) =>
                    setOpenDetail((current) => ({
                      ...current,
                      [id]: !current[id],
                    }))
                  }
                  onLoad={(id) => void loadContent(id)}
                />
              ))}
            </ol>
          ) : (
            <p>No evidence record is stored for this run.</p>
          )}
        </div>
      </section>

      <section className="run-stage" aria-labelledby="findings-title">
        <p className="run-stage-index">04 · Findings</p>
        <div>
          <h2 id="findings-title">Security findings</h2>
          <p className="field-help">
            Findings are security evidence about a recorded span. They do not
            prove intent, and they do not grant authority.
          </p>
          <StatusBadge value={findingsStage(run)} />
          {run.findings.length ? (
            <ol className="finding-list">
              {run.findings.map((finding) => {
                const linked = sourcesById.has(finding.node_id);
                return (
                  <li key={finding.id} id={`finding-${finding.id}`}>
                    <p className="finding-family">{finding.family}</p>
                    <p>{finding.explanation}</p>
                    <p>
                      {linked ? (
                        <a href={`#evidence-${finding.node_id}`}>
                          Evidence {finding.node_id.slice(0, 8)}
                        </a>
                      ) : (
                        <span>Evidence {finding.node_id.slice(0, 8)}</span>
                      )}
                      <span>
                        {" "}
                        · offsets {finding.start_offset}–{finding.end_offset}
                      </span>
                      <span> · {finding.origin} evidence</span>
                    </p>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p>No security finding is recorded for this run.</p>
          )}
        </div>
      </section>

      <section className="run-stage" aria-labelledby="proposal-title">
        <p className="run-stage-index">05 · Proposal</p>
        <div>
          <h2 id="proposal-title">Proposed action</h2>
          <p className="field-help">
            This is what the agent asked to do. It is separate from the
            authority granted above.
          </p>
          <StatusBadge value={proposalStage(run)} />
          {run.analysis ? (
            <p>
              <span className="run-kicker">Model note</span>{" "}
              {run.analysis.summary}
            </p>
          ) : (
            <p>No completed model note is recorded yet.</p>
          )}
          {proposal ? (
            <dl className="authority-facts">
              <div>
                <dt>Tool</dt>
                <dd>{proposal.tool}</dd>
              </div>
              <div>
                <dt>Target workspace</dt>
                <dd className="run-code">{proposal.arguments.workspace_id}</dd>
              </div>
              <div>
                <dt>Title</dt>
                <dd>{proposal.arguments.title}</dd>
              </div>
              <div>
                <dt>Body</dt>
                <dd>{proposal.arguments.body}</dd>
              </div>
              {evidenceIds.length ? (
                <div>
                  <dt>Evidence used</dt>
                  <dd>
                    {evidenceIds.map((id) =>
                      sourcesById.has(id) ? (
                        <a key={id} href={`#evidence-${id}`}>
                          {id.slice(0, 8)}{" "}
                        </a>
                      ) : (
                        <span key={id}>{id.slice(0, 8)} </span>
                      ),
                    )}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <p>No action proposal is recorded.</p>
          )}
        </div>
      </section>

      <section className="run-stage run-guard" aria-labelledby="guard-title">
        <p className="run-stage-index">06 · Guard</p>
        <div>
          <h2 id="guard-title">Guard decision</h2>
          <p className="field-help">
            The deterministic guard compared the exact proposed action with the
            sealed authority. The model note is not this decision.
          </p>
          {run.action ? (
            <>
              <StatusBadge value={guardStage(run)} />
              <p className="run-decision">
                {verdict === "ALLOW"
                  ? "The deterministic guard allowed this exact proposed action."
                  : verdict === "BLOCK"
                    ? "Blocked before the prohibited side effect."
                    : verdict === "REVIEW"
                      ? "Execution has not occurred. An authorized reviewer must decide on this exact action."
                      : "The guard has not recorded a verdict."}
              </p>
              {run.action.reasons.length ? (
                <ul className="reason-list">
                  {run.action.reasons.map((code) => (
                    <li key={code}>
                      <span>{reasonLabel(code)}</span>
                      <span className="run-code">{code}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No guard reason is recorded yet.</p>
              )}
              <TechnicalDetails title="Action record">
                <p className="run-code">{run.action.digest}</p>
              </TechnicalDetails>
            </>
          ) : (
            <p>No proposed action has reached the guard.</p>
          )}
        </div>
      </section>

      {run.review ? (
        <section className="run-stage" aria-labelledby="review-title">
          <p className="run-stage-index">07 · Review</p>
          <div>
            <h2 id="review-title" ref={reviewHeading} tabIndex={-1}>
              Review this exact action
            </h2>
            {!run.review.decision ? (
              <p>
                Execution has not occurred. Approval binds only this digest. It
                does not widen the granted authority. The action is checked
                again before execution.
              </p>
            ) : null}
            <ol className="review-history">
              <li>Review requested</li>
              {run.review.decision ? (
                <li>
                  {run.review.decision === "approve" ? "Approved" : "Rejected"}
                </li>
              ) : observedAt !== null &&
                new Date(run.review.expires_at).getTime() <= observedAt ? (
                <li>Expired</li>
              ) : (
                <li>
                  Waiting · expires{" "}
                  {new Date(run.review.expires_at).toLocaleString()}
                </li>
              )}
            </ol>
            {!run.review.decision ? (
              <>
                <p className="run-code">{run.review.digest}</p>
                {run.review.eligible ? (
                  <div className="button-row">
                    <button
                      className="button button-primary"
                      disabled={pending}
                      onClick={() => void review("approve")}
                    >
                      Approve exact action
                    </button>
                    <button
                      className="button button-danger"
                      disabled={pending}
                      onClick={() => void review("reject")}
                    >
                      Reject
                    </button>
                  </div>
                ) : (
                  <p>
                    The requesting principal cannot approve this exact action. A
                    different active reviewer is required.
                  </p>
                )}
              </>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="run-stage" aria-labelledby="outcome-title">
        <p className="run-stage-index">08 · Effect</p>
        <div>
          <h2 id="outcome-title">What happened</h2>
          <ol className="effect-stages">
            <li>{proposal ? "Proposed" : "Not proposed"}</li>
            <li>{verdict === "ALLOW" ? "Authorized" : "Not authorized"}</li>
            <li>{run.ticket ? "Executed" : "Not executed"}</li>
            <li>
              {run.ticket?.verified_at
                ? "Verified"
                : "Verification not recorded"}
            </li>
          </ol>
          {run.ticket ? (
            <>
              <h3>
                {run.ticket.verified_at
                  ? "Verified execution"
                  : "Executed, verification not recorded"}
              </h3>
              <p>{run.ticket.title}</p>
              <p className="field-help">
                Created {new Date(run.ticket.created_at).toLocaleString()}
                {run.ticket.verified_at
                  ? ` · Verified ${new Date(run.ticket.verified_at).toLocaleString()}`
                  : ""}
              </p>
              <Link
                className="button button-secondary"
                href={`/tickets/${run.ticket.id}`}
              >
                {run.ticket.verified_at
                  ? "Open verified ticket"
                  : "Open committed ticket"}
              </Link>
            </>
          ) : (
            <p>
              {run.state === "BLOCKED"
                ? "Blocked before the prohibited side effect. No privileged write occurred."
                : run.state === "NO_ACTION"
                  ? "The workflow completed without a business-side effect."
                  : run.state === "FAILED"
                    ? "No execution is recorded for this run."
                    : "No execution is recorded yet."}
            </p>
          )}
        </div>
      </section>

      <details className="run-audit">
        <summary>Audit timeline</summary>
        <section aria-labelledby="audit-title">
          <h2 id="audit-title">Run timeline</h2>
          <p className="field-help">{events.length} persisted events</p>
          <ol className="timeline">
            {events.map((item) => (
              <li key={item.sequence}>
                <span>{item.sequence.toString().padStart(2, "0")}</span>
                <div>
                  <strong>{item.type.replaceAll("_", " ")}</strong>
                  <time dateTime={item.created_at}>
                    {new Date(item.created_at).toLocaleString()}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </details>
    </article>
  );
}

function TechnicalDetails({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="technical-detail">
      <button
        className="text-button"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {title}
      </button>
      {open ? children : null}
    </div>
  );
}

function EvidenceNode({
  source,
  edgesByParent,
  sourcesById,
  content,
  openDetail,
  onToggleDetail,
  onLoad,
}: {
  source: Source;
  edgesByParent: Map<string, Edge[]>;
  sourcesById: Map<string, Source>;
  content: Record<string, string>;
  openDetail: Record<string, boolean>;
  onToggleDetail: (id: string) => void;
  onLoad: (id: string) => void;
}) {
  const outgoing = edgesByParent.get(source.id) ?? [];
  const open = Boolean(openDetail[source.id]);
  const loaded = content[source.id];
  return (
    <li>
      <article
        id={`evidence-${source.id}`}
        aria-labelledby={`kind-${source.id}`}
      >
        <p id={`kind-${source.id}`} className="evidence-kind">
          {representationLabel(source.representation_kind)}
        </p>
        <h3>{mediaLabel(source.declared_media_type)}</h3>
        <p className="run-code">
          {source.declared_media_type ?? "Not recorded"}
          {source.representation_kind === null
            ? " · Representation not recorded"
            : ""}
        </p>
        <p>{source.complete ? "Complete" : "Incomplete"}</p>
        <button
          className="text-button"
          type="button"
          aria-expanded={Boolean(loaded)}
          onClick={() => onLoad(source.id)}
        >
          {loaded ? "Protected text loaded" : "View protected text"}
        </button>
        {loaded ? <pre className="evidence-text">{loaded}</pre> : null}
        <div className="technical-detail">
          <button
            className="text-button"
            type="button"
            aria-expanded={open}
            onClick={() => onToggleDetail(source.id)}
          >
            Technical details
          </button>
          {open ? (
            <dl className="authority-facts">
              <div>
                <dt>Digest</dt>
                <dd className="run-code">{source.digest}</dd>
              </div>
              <div>
                <dt>Bytes</dt>
                <dd>{recorded(source.byte_size)}</dd>
              </div>
              <div>
                <dt>Charset</dt>
                <dd>{recorded(source.charset)}</dd>
              </div>
              <div>
                <dt>Parser</dt>
                <dd className="run-code">
                  {source.parser_id && source.parser_version
                    ? `${source.parser_id} / ${source.parser_version}`
                    : "Not recorded"}
                </dd>
              </div>
              <div>
                <dt>Expires</dt>
                <dd>{new Date(source.expires_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Origin</dt>
                <dd>{source.origin}</dd>
              </div>
            </dl>
          ) : null}
        </div>
      </article>
      {outgoing.length ? (
        <ol className="derivation-list">
          {outgoing.map((edge) => {
            const child = sourcesById.get(edge.child_id);
            return (
              <li key={`${edge.parent_id}:${edge.child_id}:${edge.transform}`}>
                <p className="derivation-summary">
                  <span className="run-kicker">Derivation summary</span>
                  {transformLabel(edge.transform)}
                  <span className="run-code">
                    {edge.transform}/{edge.version}
                    {edge.lossy ? " · lossy" : ""}
                  </span>
                </p>
                {edge.transform_steps === null ? (
                  <p>Transform history not recorded</p>
                ) : (
                  <ol className="step-list">
                    {edge.transform_steps.map((step, index) => (
                      <li key={`${index}:${step.transform}:${step.version}`}>
                        {transformLabel(step.transform)}
                        <span className="run-code">
                          {step.transform}/{step.version}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
                {child ? (
                  <ol className="evidence-tree">
                    <EvidenceNode
                      source={child}
                      edgesByParent={edgesByParent}
                      sourcesById={sourcesById}
                      content={content}
                      openDetail={openDetail}
                      onToggleDetail={onToggleDetail}
                      onLoad={onLoad}
                    />
                  </ol>
                ) : (
                  <p>The derived record is not in this response.</p>
                )}
              </li>
            );
          })}
        </ol>
      ) : null}
    </li>
  );
}

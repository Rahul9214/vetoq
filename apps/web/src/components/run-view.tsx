"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { AuditEvent, RunDetail } from "@/lib/contracts";
import {
  findingsStage,
  goalLockStage,
  guardStage,
  isTerminal,
  proposalStage,
  sourceStage,
} from "@/lib/run-state";

function StageHeader({
  number,
  kicker,
  title,
  state,
}: {
  number: string;
  kicker: string;
  title: string;
  state?: string;
}) {
  return (
    <header className="stage-header">
      <span className="stage-number" aria-hidden="true">
        {number}
      </span>
      <div>
        <p className="eyebrow">{kicker}</p>
        <h2>{title}</h2>
      </div>
      {state ? <StatusBadge value={state} /> : null}
    </header>
  );
}

export function RunView({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [content, setContent] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
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
  const verdict = run.action?.verdict;
  const outcomeState = run.ticket?.verified_at
    ? "VERIFIED"
    : run.ticket
      ? "VERIFYING"
      : run.state;

  return (
    <div className="run-story">
      <header className="run-hero">
        <div>
          <Link className="back-link" href="/">
            ← Security workbench
          </Link>
          <p className="eyebrow">Guarded run / {run.id.slice(0, 8)}</p>
          <h1>{goal}</h1>
          <p>
            Every stage below is persisted evidence. Model analysis informs the
            proposal; deterministic policy owns the decision.
          </p>
        </div>
        <div className="run-hero-state">
          <StatusBadge value={run.state} />
          <time dateTime={run.created_at}>
            Started {new Date(run.created_at).toLocaleString()}
          </time>
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
          <strong>Processing stopped:</strong> {run.failure}
        </section>
      ) : null}

      <nav className="stage-index" aria-label="Run evidence stages">
        {[
          ["01", "Goal Lock", "goal-lock"],
          ["02", "Source", "source-provenance"],
          ["03", "Findings", "inspection-findings"],
          ["04", "AI Proposal", "ai-proposal"],
          ["05", "Action Guard", "action-guard"],
          ["06", "Outcome", "execution-outcome"],
        ].map(([number, label, anchor]) => (
          <a key={anchor} href={`#${anchor}`}>
            <span>{number}</span>
            {label}
          </a>
        ))}
      </nav>

      <div className="stage-stack">
        <section
          id="goal-lock"
          className="evidence-stage stage-authority"
          aria-labelledby="goal-lock-title"
        >
          <StageHeader
            number="01"
            kicker="Immutable authority"
            title="Goal Lock"
            state={goalLockStage(run)}
          />
          <p className="stage-lead" id="goal-lock-title">
            User-confirmed authority was sealed before untrusted content reached
            model analysis.
          </p>
          <dl className="evidence-ledger">
            <div>
              <dt>Authorized goal</dt>
              <dd>{goal}</dd>
            </div>
            <div>
              <dt>Workspace</dt>
              <dd>{run.workspace_id}</dd>
            </div>
            <div>
              <dt>Permitted tool</dt>
              <dd>{String(run.goal_lock.tool)}</dd>
            </div>
            <div>
              <dt>Destination</dt>
              <dd>{String(run.goal_lock.destination)}</dd>
            </div>
            <div>
              <dt>Write limit</dt>
              <dd>{String(run.goal_lock.max_writes)}</dd>
            </div>
            <div>
              <dt>Expires</dt>
              <dd>{new Date(run.expires_at).toLocaleString()}</dd>
            </div>
          </dl>
        </section>

        <section
          id="source-provenance"
          className="evidence-stage"
          aria-labelledby="source-title"
        >
          <StageHeader
            number="02"
            kicker="Untrusted by construction"
            title="Source / Provenance"
            state={sourceStage(run)}
          />
          <p className="stage-lead" id="source-title">
            Original and derived content retain supplier, trust, digest, and
            retention metadata.
          </p>
          <div className="source-grid">
            {run.sources.map((source) => (
              <article className="source-card" key={source.id}>
                <header>
                  <div>
                    <strong>{source.origin}</strong>
                    <span>{source.supplier}</span>
                  </div>
                  <span className="trust-label">UNTRUSTED</span>
                </header>
                <dl>
                  <div>
                    <dt>Digest</dt>
                    <dd>{source.digest.slice(0, 16)}…</dd>
                  </div>
                  <div>
                    <dt>Capture</dt>
                    <dd>{source.complete ? "Complete" : "Incomplete"}</dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd>{new Date(source.expires_at).toLocaleString()}</dd>
                  </div>
                </dl>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => void loadContent(source.id)}
                  aria-expanded={Boolean(content[source.id])}
                >
                  {content[source.id]
                    ? "Protected text loaded"
                    : "View protected text"}
                </button>
                {content[source.id] ? (
                  <pre className="evidence-text">{content[source.id]}</pre>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <section
          id="inspection-findings"
          className="evidence-stage"
          aria-labelledby="findings-title"
        >
          <StageHeader
            number="03"
            kicker="Deterministic + contextual evidence"
            title="Inspection Findings"
            state={findingsStage(run)}
          />
          <p className="stage-lead" id="findings-title">
            Findings identify suspicious spans and their source records. They do
            not grant or remove authority.
          </p>
          {run.findings.length ? (
            <ol className="finding-list">
              {run.findings.map((finding) => (
                <li key={finding.id}>
                  <div className="finding-topline">
                    <span className="finding-family">{finding.family}</span>
                    <span className="finding-origin">
                      {finding.origin} evidence
                    </span>
                  </div>
                  <p>{finding.explanation}</p>
                  <small>
                    Source {finding.node_id.slice(0, 8)} · offsets{" "}
                    {finding.start_offset}–{finding.end_offset}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="stage-empty">
              No suspicious finding has been persisted for this run.
            </p>
          )}
        </section>

        <section
          id="ai-proposal"
          className="evidence-stage stage-proposal"
          aria-labelledby="proposal-title"
        >
          <StageHeader
            number="04"
            kicker="Provider-neutral model evidence"
            title="AI Proposal"
            state={proposalStage(run)}
          />
          <div className="proposal-layout">
            <div>
              <h3 id="proposal-title">Contextual analysis</h3>
              {run.analysis ? (
                <>
                  <p>{run.analysis.summary}</p>
                  <p className="metadata">
                    {run.analysis.provider} / {run.analysis.model} / observed{" "}
                    {run.analysis.elapsed_ms} ms
                  </p>
                </>
              ) : (
                <p className="stage-empty">
                  No completed model analysis is available yet.
                </p>
              )}
            </div>
            <div className="proposal-record">
              <span className="record-label">Typed proposal</span>
              {proposal ? (
                <dl>
                  <div>
                    <dt>Tool</dt>
                    <dd>{proposal.tool}</dd>
                  </div>
                  <div>
                    <dt>Workspace argument</dt>
                    <dd>{proposal.arguments.workspace_id}</dd>
                  </div>
                  <div>
                    <dt>Title</dt>
                    <dd>{proposal.arguments.title}</dd>
                  </div>
                  <div>
                    <dt>Body</dt>
                    <dd>{proposal.arguments.body}</dd>
                  </div>
                </dl>
              ) : (
                <p>No action proposal exists.</p>
              )}
            </div>
          </div>
        </section>

        <section
          id="action-guard"
          className="evidence-stage stage-guard"
          aria-labelledby="guard-title"
        >
          <StageHeader
            number="05"
            kicker="Deterministic enforcement"
            title="Action Guard"
            state={guardStage(run)}
          />
          <p className="stage-lead" id="guard-title">
            The exact typed action is compared with the immutable Goal Lock,
            current membership, policy revision, approval state, and write
            budget.
          </p>
          {run.action ? (
            <div className="guard-decision">
              <div className="verdict-panel">
                <StatusBadge value={guardStage(run)} />
                <strong>
                  {verdict === "ALLOW"
                    ? "Exact action is inside confirmed authority."
                    : verdict === "BLOCK"
                      ? "Execution is prohibited before any write."
                      : verdict === "REVIEW"
                        ? "Exact-action human review is required."
                        : "Authorization has not completed."}
                </strong>
              </div>
              <dl className="guard-ledger">
                <div>
                  <dt>Policy reasons</dt>
                  <dd>
                    {run.action.reasons.join(", ") ||
                      "No policy reason persisted yet"}
                  </dd>
                </div>
                <div>
                  <dt>Action digest</dt>
                  <dd className="digest">{run.action.digest}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <p className="stage-empty">
              No action has reached deterministic authorization.
            </p>
          )}
        </section>

        {run.review && !run.review.decision ? (
          <section className="review-panel" aria-labelledby="review-title">
            <p className="eyebrow">Exact-action review</p>
            <h2 id="review-title" ref={reviewHeading} tabIndex={-1}>
              Review this exact action
            </h2>
            <p>
              Review is required because{" "}
              {run.action?.reasons.join(", ") || "the action is uncertain"}.
              Approval binds only this digest. It cannot authorize a different
              action or enlarge the Goal Lock.
            </p>
            <dl className="guard-ledger">
              <div>
                <dt>Tool</dt>
                <dd>
                  {proposal?.tool ?? "unavailable"}
                  {proposal
                    ? ` version ${String(run.goal_lock.tool_version ?? "unavailable")}`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>Action</dt>
                <dd>{proposal?.arguments.title ?? "unavailable"}</dd>
              </div>
              <div>
                <dt>Workspace</dt>
                <dd>{proposal?.arguments.workspace_id ?? run.workspace_id}</dd>
              </div>
              <div>
                <dt>Destination</dt>
                <dd>{String(run.goal_lock.destination ?? "unavailable")}</dd>
              </div>
              <div>
                <dt>Findings</dt>
                <dd>
                  {run.findings.map((finding) => finding.family).join(", ") ||
                    "None persisted"}
                </dd>
              </div>
            </dl>
            <p className="digest">{run.review.digest}</p>
            <p>Expires {new Date(run.review.expires_at).toLocaleString()}</p>
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
          </section>
        ) : null}

        <section
          id="execution-outcome"
          className="evidence-stage stage-outcome"
          aria-labelledby="outcome-title"
        >
          <StageHeader
            number="06"
            kicker="Verified effect"
            title="Execution Outcome"
            state={outcomeState}
          />
          <div className="outcome-content">
            {run.ticket ? (
              <>
                <div>
                  <h3 id="outcome-title">
                    {run.ticket.verified_at
                      ? "Ticket persisted and read back"
                      : "Ticket committed; verification pending"}
                  </h3>
                  <p>{run.ticket.title}</p>
                  <p className="metadata">
                    Created {new Date(run.ticket.created_at).toLocaleString()}
                  </p>
                </div>
                <Link
                  className="button button-primary"
                  href={`/tickets/${run.ticket.id}`}
                >
                  {run.ticket.verified_at
                    ? "Open verified ticket"
                    : "Open committed ticket"}
                </Link>
              </>
            ) : (
              <div>
                <h3 id="outcome-title">
                  {run.state === "BLOCKED"
                    ? "No privileged write occurred"
                    : run.state === "NO_ACTION"
                      ? "Analysis completed without an action"
                      : run.state === "FAILED"
                        ? "The run stopped without a verified action"
                        : "Awaiting a terminal outcome"}
                </h3>
                <p>
                  {run.state === "BLOCKED"
                    ? "The Action Guard persisted its veto before the ticket dispatcher."
                    : "VETOQ will display an outcome only after it is persisted and verified."}
                </p>
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="audit-panel" aria-labelledby="audit-title">
        <header className="panel-heading">
          <div>
            <p className="eyebrow">Append-only application audit</p>
            <h2 id="audit-title">Run timeline</h2>
          </div>
          <span>{events.length} persisted events</span>
        </header>
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
    </div>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { Me, RunSummary } from "@/lib/contracts";

const defaultGoal =
  "Review this support email and create one support ticket in the confirmed workspace.";

export function Workbench() {
  const router = useRouter();
  const errorId = useId();
  const idempotencyKey = useRef<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [goal, setGoal] = useState(defaultGoal);
  const [source, setSource] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [pending, setPending] = useState(false);
  const [identityError, setIdentityError] = useState("");
  const [runsError, setRunsError] = useState("");
  const [submitError, setSubmitError] = useState("");

  const loadIdentity = useCallback(() => {
    return api<Me>("/me")
      .then((identity) => {
        setMe(identity);
        setWorkspaceId(
          (current) => current || identity.workspaces[0]?.id || "",
        );
      })
      .catch((reason: unknown) => {
        setIdentityError(
          reason instanceof Error ? reason.message : "identity_unavailable",
        );
      });
  }, []);

  useEffect(() => {
    void loadIdentity();
  }, [loadIdentity]);

  useEffect(() => {
    if (!workspaceId) return;
    void api<{ items: RunSummary[] }>(
      `/runs?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
      .then((result) => {
        setRunsError("");
        setRuns(result.items);
      })
      .catch((reason: unknown) =>
        setRunsError(
          reason instanceof Error ? reason.message : "runs_unavailable",
        ),
      );
  }, [workspaceId]);

  function resetSubmissionIdentity() {
    idempotencyKey.current = null;
    setSubmitError("");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setSubmitError("");
    idempotencyKey.current ??= crypto.randomUUID();
    try {
      const result = await api<{ id: string }>("/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey.current,
        },
        body: JSON.stringify({
          workspace_id: workspaceId,
          template: "support-triage/1",
          goal,
          source,
          confirmed: true,
          sanitized: true,
        }),
      });
      idempotencyKey.current = null;
      router.push(`/runs/${result.id}`);
    } catch (reason) {
      setSubmitError(
        reason instanceof Error ? reason.message : "submission_failed",
      );
      setPending(false);
    }
  }

  if (identityError && !me) {
    return (
      <section
        className="system-failure"
        aria-labelledby="workspace-error-title"
      >
        <p className="eyebrow">Workspace boundary unavailable</p>
        <h2 id="workspace-error-title">
          The authenticated workspace could not be opened.
        </h2>
        <p>
          VETOQ has stopped before accepting content. Restore the API and
          persistence boundary, then retry.
        </p>
        <code>{identityError}</code>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => {
            setIdentityError("");
            void loadIdentity();
          }}
        >
          Retry workspace check
        </button>
      </section>
    );
  }

  if (!me) {
    return (
      <section className="loading-state" aria-live="polite" aria-busy="true">
        <span className="loading-pulse" aria-hidden="true" />
        <div>
          <p className="eyebrow">Authenticated boundary</p>
          <p>Verifying identity, persistence, and workspace membership…</p>
        </div>
      </section>
    );
  }

  if (me.access !== "active" || me.workspaces.length === 0) {
    return (
      <section className="empty-state" aria-labelledby="membership-title">
        <div className="empty-state-mark" aria-hidden="true">
          !
        </div>
        <div>
          <p className="eyebrow">Access pending</p>
          <h2 id="membership-title">No VETOQ workspace membership</h2>
          <p>
            Clerk verified this identity. A VETOQ operator must grant an
            explicit server-side workspace membership before any run can begin.
          </p>
          <code>{me.principal}</code>
        </div>
      </section>
    );
  }

  const workspace =
    me.workspaces.find((item) => item.id === workspaceId) ?? me.workspaces[0];

  return (
    <div className="workbench">
      <section
        className="security-status"
        aria-labelledby="security-status-title"
      >
        <div>
          <p className="eyebrow">Current security state</p>
          <h2 id="security-status-title">Ready for a goal-bound run</h2>
        </div>
        <div className="security-checks" role="list">
          <div role="listitem">
            <span aria-hidden="true">✓</span>
            <strong>Identity verified</strong>
            <small>Clerk session</small>
          </div>
          <div role="listitem">
            <span aria-hidden="true">✓</span>
            <strong>Workspace authorized</strong>
            <small>{workspace?.name}</small>
          </div>
          <div role="listitem">
            <span aria-hidden="true">•</span>
            <strong>Policy revision</strong>
            <small>{workspace?.policy_revision}</small>
          </div>
        </div>
      </section>

      <div className="workbench-primary">
        <section className="run-composer" aria-labelledby="submit-title">
          <header className="panel-heading">
            <div>
              <p className="eyebrow">New security run</p>
              <h2 id="submit-title">Confirm authority before analysis</h2>
            </div>
            <span className="step-count">01 / Goal Lock</span>
          </header>
          <form
            onSubmit={submit}
            aria-describedby={submitError ? errorId : undefined}
          >
            <div className="field-group">
              <label htmlFor="workspace">Authorized workspace</label>
              <p className="field-help">
                The Action Guard binds every proposal to this destination.
              </p>
              <select
                id="workspace"
                value={workspaceId}
                onChange={(event) => {
                  setWorkspaceId(event.target.value);
                  resetSubmissionIdentity();
                }}
              >
                {me.workspaces.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field-group">
              <label htmlFor="goal">Authorized goal</label>
              <p className="field-help">
                State the single outcome this run may pursue.
              </p>
              <textarea
                id="goal"
                value={goal}
                maxLength={4096}
                required
                onChange={(event) => {
                  setGoal(event.target.value);
                  resetSubmissionIdentity();
                }}
              />
            </div>
            <div className="field-group">
              <label htmlFor="source">Untrusted support-email text</label>
              <p className="field-help">
                Paste synthetic or sanitized content only. It remains untrusted.
              </p>
              <textarea
                id="source"
                className="source-field"
                value={source}
                maxLength={65536}
                required
                onChange={(event) => {
                  setSource(event.target.value);
                  resetSubmissionIdentity();
                }}
                placeholder="Paste the support request to inspect…"
              />
            </div>
            <div className="goal-lock-preview" aria-label="Goal Lock preview">
              <div className="lock-icon" aria-hidden="true">
                ⌁
              </div>
              <div>
                <strong>Goal Lock</strong>
                <span>Immutable before model analysis</span>
              </div>
              <dl>
                <div>
                  <dt>Tool</dt>
                  <dd>{me.template.tool}</dd>
                </div>
                <div>
                  <dt>Destination</dt>
                  <dd>{me.template.destination}</dd>
                </div>
                <div>
                  <dt>Limit</dt>
                  <dd>{me.template.max_writes} write</dd>
                </div>
                <div>
                  <dt>Expiry</dt>
                  <dd>{me.template.expires_minutes} min</dd>
                </div>
              </dl>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
                required
              />
              <span>
                I confirm this exact scope and that the source is synthetic or
                sanitized.
              </span>
            </label>
            {submitError ? (
              <p id={errorId} className="form-error" role="alert">
                {submitError}
              </p>
            ) : null}
            <button
              className="button button-primary submit-button"
              disabled={!confirmed || pending}
              type="submit"
            >
              {pending ? "Persisting Goal Lock…" : "Start guarded analysis"}
              <span aria-hidden="true">→</span>
            </button>
          </form>
        </section>

        <aside className="boundary-panel" aria-labelledby="boundary-title">
          <p className="eyebrow">Execution boundary</p>
          <h2 id="boundary-title">
            The model cannot authorize its own proposal.
          </h2>
          <div className="boundary-route" aria-label="Authority path">
            <span>Untrusted source</span>
            <i aria-hidden="true">↓</i>
            <span>AI evidence</span>
            <i aria-hidden="true">↓</i>
            <strong>Deterministic Action Guard</strong>
            <i aria-hidden="true">↓</i>
            <span>Verified local ticket</span>
          </div>
          <p className="boundary-note">
            Unknown tools, changed arguments, stale approval, or a different
            workspace fail closed.
          </p>
        </aside>
      </div>

      <section className="recent-runs" aria-labelledby="recent-title">
        <header className="panel-heading">
          <div>
            <p className="eyebrow">Persistent evidence</p>
            <h2 id="recent-title">Recent runs</h2>
          </div>
          <span>{workspace?.name}</span>
        </header>
        {runsError ? (
          <p className="notice notice-error" role="alert">
            Unable to load runs: {runsError}
          </p>
        ) : null}
        {!runsError && runs.length === 0 ? (
          <div className="runs-empty">
            <span aria-hidden="true">◇</span>
            <p>No runs exist in this workspace yet.</p>
          </div>
        ) : (
          <ol className="run-list">
            {runs.map((run) => (
              <li key={run.id}>
                <Link href={`/runs/${run.id}`}>
                  <StatusBadge value={run.state} />
                  <strong>{run.goal}</strong>
                  <time dateTime={run.created_at}>
                    {new Date(run.created_at).toLocaleString()}
                  </time>
                  <span className="row-arrow" aria-hidden="true">
                    ↗
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

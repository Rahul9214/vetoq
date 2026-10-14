"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { Me, RunSummary } from "@/lib/contracts";

const defaultGoal =
  "Review this support email and create one support ticket in the confirmed workspace.";

const declaredFormats = [
  {
    value: "text/plain",
    label: "Plain text",
    guidance: "Ordinary pasted text.",
  },
  {
    value: "application/json",
    label: "JSON",
    guidance:
      "Strict JSON. Duplicate keys and malformed structures are rejected.",
  },
  {
    value: "text/markdown",
    label: "Markdown",
    guidance: "Markdown stays untrusted text and is not rendered.",
  },
  {
    value: "text/html",
    label: "HTML",
    guidance: "HTML stays inert. Scripts and resources are not executed.",
  },
  {
    value: "message/rfc822",
    label: "Email (RFC822)",
    guidance:
      "Paste raw RFC822 or MIME source. Unsupported attachments are rejected.",
  },
] as const;

const submissionMessages: Record<string, string> = {
  malformed_content: "This content does not match the declared format.",
  unsupported_media_type: "That declared format is not accepted.",
  unsupported_embedded_content:
    "An embedded part, charset, or transfer encoding in this message is not accepted.",
  input_limit: "This submission exceeds an accepted size or structure limit.",
  idempotency_conflict:
    "This submission key was already used for a different goal, format, or content.",
  invalid_input: "The submission could not be accepted as entered.",
};

export const confirmationLabel =
  "I confirm this goal, this authority, and this untrusted submission.";

function presentSubmissionError(raw: string) {
  const code = /^[a-z0-9_]{1,64}$/.test(raw) ? raw : "submission_failed";
  return {
    code,
    message: submissionMessages[code] ?? "The submission was not accepted.",
  };
}

export function Workbench() {
  const router = useRouter();
  const errorId = useId();
  const gateId = useId();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const idempotencyKey = useRef<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [goal, setGoal] = useState(defaultGoal);
  const [mediaType, setMediaType] = useState("");
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

  useEffect(() => {
    if (!submitError) return;
    errorRef.current?.focus();
  }, [submitError]);

  function resetSubmissionIdentity() {
    idempotencyKey.current = null;
    setSubmitError("");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !confirmed || mediaType === "") return;
    setPending(true);
    setSubmitError("");
    if (!declaredFormats.some((item) => item.value === mediaType)) {
      setSubmitError("invalid_input");
      setPending(false);
      return;
    }
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
          goal,
          source,
          media_type: mediaType,
          confirmed: true,
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
  const selectedFormat = declaredFormats.find(
    (item) => item.value === mediaType,
  );
  const presentedError = submitError
    ? presentSubmissionError(submitError)
    : null;
  const gate = pending
    ? "Submitting…"
    : mediaType === ""
      ? "Choose a declared format to continue."
      : !confirmed
        ? "Confirm the goal, the authority, and this untrusted submission."
        : "The submission can be sent.";
  const sourceDescribedBy = submitError
    ? `source-help ${errorId}`
    : "source-help";

  return (
    <div className="workbench">
      <form
        className="workbench-form"
        onSubmit={submit}
        aria-busy={pending}
        aria-describedby={submitError ? errorId : undefined}
      >
        <div className="workbench-intent">
          <section className="workbench-goal" aria-labelledby="intent-title">
            <p className="section-index">01 · Intent</p>
            <h2 id="intent-title">What this run may accomplish</h2>
            <p className="field-help" id="goal-help">
              State the single outcome. Authority stays with this goal, not with
              the content.
            </p>
            <label htmlFor="goal">Authorized goal</label>
            <textarea
              id="goal"
              className="goal-field"
              value={goal}
              maxLength={4096}
              required
              aria-describedby="goal-help"
              onChange={(event) => {
                setGoal(event.target.value);
                resetSubmissionIdentity();
              }}
            />
          </section>

          <section
            className="workbench-authority"
            aria-labelledby="authority-title"
          >
            <p className="section-index">02 · Authority</p>
            <h2 id="authority-title">Authority granted for that goal</h2>
            <p className="field-help" id="authority-help">
              Membership selects the workspace. The server checks it. Content
              cannot widen this scope.
            </p>
            <dl className="authority-facts">
              <div>
                <dt>Tool</dt>
                <dd>{me.template.tool}</dd>
              </div>
              <div>
                <dt>Destination</dt>
                <dd>{me.template.destination}</dd>
              </div>
              <div>
                <dt>Writes</dt>
                <dd>{me.template.max_writes}</dd>
              </div>
              <div>
                <dt>Expires</dt>
                <dd>{me.template.expires_minutes} min</dd>
              </div>
              <div>
                <dt>Policy</dt>
                <dd>{workspace?.policy_revision}</dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd>{workspace?.role}</dd>
              </div>
            </dl>
            <label htmlFor="workspace">Authorized workspace</label>
            <select
              id="workspace"
              value={workspaceId}
              aria-describedby="authority-help"
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
            <p className="authority-note">
              A proposal can recommend an action. It cannot grant this
              authority.
            </p>
          </section>
        </div>

        <section className="workbench-content">
          <div className="workbench-content-layout">
            <div>
              <p className="section-index">03 · Content</p>
              <h2 id="content-title">Untrusted business content</h2>
              <div className="field-group">
                <label htmlFor="media-type">Declared format</label>
                <p id="format-help" className="field-help">
                  Choose how this paste should be read. The content stays
                  untrusted. Nothing here detects a format for you.
                </p>
                <select
                  id="media-type"
                  value={mediaType}
                  required
                  aria-describedby="format-help format-guidance format-choice"
                  onChange={(event) => {
                    setMediaType(event.target.value);
                    resetSubmissionIdentity();
                  }}
                >
                  <option value="">Select a format</option>
                  {declaredFormats.map((item) => (
                    <option value={item.value} key={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <p id="format-choice" className="format-choice">
                  <span>Selected</span>
                  <strong>
                    {selectedFormat?.label ?? "No format selected"}
                  </strong>
                </p>
                <p id="format-guidance" className="field-help">
                  {selectedFormat?.guidance ??
                    "A format is required. There is no default."}
                </p>
              </div>
              <div className="field-group">
                <p id="source-help" className="field-help">
                  Paste the content in the declared format. It remains untrusted
                  text.
                </p>
                <textarea
                  id="source"
                  className={
                    mediaType === "" || mediaType === "text/plain"
                      ? "source-field source-field--prose"
                      : "source-field"
                  }
                  value={source}
                  maxLength={65536}
                  required
                  aria-labelledby="content-title"
                  aria-invalid={submitError ? true : undefined}
                  aria-describedby={sourceDescribedBy}
                  onChange={(event) => {
                    setSource(event.target.value);
                    resetSubmissionIdentity();
                  }}
                  placeholder="Paste untrusted content in the declared format"
                />
              </div>
            </div>
            <aside className="content-aside" aria-label="Content boundary">
              <p>Content is untrusted.</p>
              <p>Authority comes from the goal and the scope above.</p>
            </aside>
          </div>
        </section>

        <section className="workbench-confirm" aria-labelledby="confirm-title">
          <div>
            <p className="section-index">04 · Confirm</p>
            <h2 id="confirm-title">Confirm and submit</h2>
            <p className="field-help">
              Confirm the intended goal, the authority above, and the submission
              of untrusted content. This does not mean the content is safe,
              sanitized, or trustworthy.
            </p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
                required
              />
              <span>{confirmationLabel}</span>
            </label>
          </div>
          <div className="workbench-action">
            {presentedError ? (
              <p
                id={errorId}
                ref={errorRef}
                className="form-error"
                role="alert"
                tabIndex={-1}
              >
                <span className="form-error-message">
                  {presentedError.message}
                </span>
                <span className="form-error-code">{presentedError.code}</span>
              </p>
            ) : null}
            <p id={gateId} className="submit-gate">
              {gate}
            </p>
            <button
              className="button submit-button"
              disabled={!confirmed || mediaType === "" || pending}
              type="submit"
              aria-describedby={submitError ? `${gateId} ${errorId}` : gateId}
            >
              {pending ? "Submitting…" : "Start guarded analysis"}
            </button>
          </div>
        </section>
      </form>

      <section className="recent-runs" aria-labelledby="recent-title">
        <header className="recent-runs-heading">
          <h2 id="recent-title">Recent runs</h2>
          <span>{workspace?.name}</span>
        </header>
        {runsError ? (
          <p className="notice notice-error" role="alert">
            Unable to load runs: {runsError}
          </p>
        ) : null}
        {!runsError && runs.length === 0 ? (
          <div className="runs-empty">
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
                </Link>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

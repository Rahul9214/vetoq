"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { Ticket } from "@/lib/contracts";

export function TicketView({ ticketId }: { ticketId: string }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api<Ticket>(`/tickets/${ticketId}`)
      .then(setTicket)
      .catch((reason: unknown) =>
        setError(
          reason instanceof Error ? reason.message : "ticket_unavailable",
        ),
      );
  }, [ticketId]);

  if (error) {
    return (
      <section className="system-failure" aria-labelledby="ticket-error-title">
        <p className="eyebrow">Protected outcome unavailable</p>
        <h1 id="ticket-error-title">This ticket could not be opened.</h1>
        <code>{error}</code>
      </section>
    );
  }

  if (!ticket) {
    return (
      <section className="loading-state" aria-live="polite" aria-busy="true">
        <span className="loading-pulse" aria-hidden="true" />
        <p>Reading the persisted ticket…</p>
      </section>
    );
  }

  return (
    <article className="ticket-record">
      <Link className="back-link" href={`/runs/${ticket.run_id}`}>
        ← Return to run evidence
      </Link>
      <header className="ticket-heading">
        <div>
          <p className="eyebrow">Local ticket / PostgreSQL record</p>
          <h1>{ticket.title}</h1>
        </div>
        <StatusBadge value={ticket.verified_at ? "VERIFIED" : "VERIFYING"} />
      </header>
      <section className="ticket-proof" aria-labelledby="ticket-proof-title">
        <div className="ticket-proof-mark" aria-hidden="true">
          ✓
        </div>
        <div>
          <p className="eyebrow">Execution outcome</p>
          <h2 id="ticket-proof-title">
            {ticket.verified_at
              ? "Committed and read back"
              : "Committed; read-back pending"}
          </h2>
          <p>
            This record exists because the exact proposal passed deterministic
            authorization.
          </p>
        </div>
      </section>
      <section
        className="ticket-content"
        aria-labelledby="ticket-content-title"
      >
        <p className="eyebrow">Persisted content</p>
        <h2 id="ticket-content-title">Ticket body</h2>
        <p>{ticket.body}</p>
      </section>
      <dl className="evidence-ledger ticket-ledger">
        <div>
          <dt>Ticket ID</dt>
          <dd>{ticket.id}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{new Date(ticket.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt>Verified</dt>
          <dd>
            {ticket.verified_at
              ? new Date(ticket.verified_at).toLocaleString()
              : "Pending"}
          </dd>
        </div>
      </dl>
    </article>
  );
}

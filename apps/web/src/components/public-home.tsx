import Link from "next/link";

import { VetoqWordmark } from "./vetoq-mark";

const outcomes = [
  {
    title: "Define the authority first",
    body: "The organization states the goal, the destination, and the write limit before the agent reads anything.",
  },
  {
    title: "Know what evidence shaped the action",
    body: "The note the agent reasons over stays attached to the proposal, including how a derived record was produced.",
  },
  {
    title: "Compare the proposal with the scope actually granted",
    body: "Action Guard checks the exact requested change against that authority and the evidence it relies on.",
  },
  {
    title: "Stop scope expansion before a side effect",
    body: "An action aimed outside the granted destination is stopped before the write.",
  },
  {
    title: "Pause for a person when the action is consequential and uncertain",
    body: "Review applies to that exact action. It does not widen the authority already granted.",
  },
  {
    title: "See what changed afterward",
    body: "Proposed, authorized, executed, and verified stay separate. An attempt is not treated as a finished result.",
  },
] as const;

const pathSteps = [
  ["Goal confirmed", "The intended outcome is sealed for this run."],
  ["Inspect evidence", "The agent reasons over the submitted record."],
  ["Authority boundary", "Tool, destination, and write limit stay fixed."],
  [
    "Analyze the action",
    "The proposal is read as a request, not a permission.",
  ],
  [
    "Compare with policy",
    "The exact request meets the granted scope, or it does not.",
  ],
  ["Decision", "Allow, review, or stop before the side effect."],
  [
    "Human review if required",
    "An authorized person decides on that action only.",
  ],
  ["Revalidate", "The action is checked again before execution."],
  ["Execute", "The permitted side effect is attempted."],
  [
    "Verify",
    "The resulting change is confirmed, when verification is recorded.",
  ],
] as const;

export function PublicHome() {
  return (
    <>
      <main id="main-content" tabIndex={-1} className="public-home">
        <section className="public-hero" aria-labelledby="public-hero-title">
          <div className="public-shell public-hero__layout">
            <div className="public-hero__copy">
              <p className="public-kicker">Agent Execution Security Platform</p>
              <p className="public-tagline">
                Trust the Goal. Verify the Action.
              </p>
              <h1 id="public-hero-title">
                Give AI room to work
                <span> without giving it unlimited authority.</span>
              </h1>
              <p className="public-lede">
                VETOQ keeps consequential agent actions inside the goal, scope,
                and evidence your organization actually approved.
              </p>
              <div className="public-actions">
                <a className="button button--primary" href="#execution-path">
                  See how VETOQ works
                </a>
                <Link className="button button--quiet" href="/sign-in">
                  Open secure workbench
                </Link>
              </div>
            </div>
            <figure className="boundary-stage" aria-labelledby="hero-visual">
              <figcaption id="hero-visual">
                <span>Product illustration</span>
                <span>One action meets the boundary</span>
              </figcaption>
              <ol className="boundary-flow">
                <li>
                  <span>Goal</span>
                  <strong>Create one support ticket</strong>
                </li>
                <li>
                  <span>Evidence</span>
                  <strong>The untrusted note</strong>
                </li>
                <li>
                  <span>Proposed action</span>
                  <strong>Open that ticket</strong>
                </li>
                <li className="boundary-flow__gate">
                  <span>Authority boundary</span>
                  <strong>Granted destination and write limit</strong>
                  <i className="boundary-scan" aria-hidden="true" />
                </li>
                <li>
                  <span>Decision</span>
                  <strong>Allowed, or stopped</strong>
                </li>
              </ol>
              <div className="boundary-outcomes">
                <p>
                  <span>Inside scope</span>
                  Create the approved ticket. Allowed.
                </p>
                <p>
                  <span>Outside scope</span>
                  Reach another workspace. Stopped before the side effect.
                </p>
              </div>
            </figure>
          </div>
        </section>

        <section
          className="public-section public-section--champagne"
          id="problem"
          aria-labelledby="problem-title"
        >
          <div className="public-shell public-split">
            <div>
              <p className="public-kicker">The gap</p>
              <h2 id="problem-title">
                Credentials do not answer whether this action was delegated.
              </h2>
            </div>
            <div className="public-prose">
              <p>
                AI agents can reason quickly. A real business action still needs
                a boundary that was set for this run.
              </p>
              <p>
                Traditional application permissions usually answer whether a
                service has credentials. They do not necessarily answer whether
                this particular agent action is within the goal and scope
                delegated for this particular run.
              </p>
            </div>
          </div>
        </section>

        <section
          className="public-section public-section--stone"
          id="changes"
          aria-labelledby="changes-title"
        >
          <div className="public-shell">
            <p className="public-kicker">What changes</p>
            <h2 id="changes-title">
              Authority is settled before the agent acts.
            </h2>
            <ol className="outcome-list">
              {outcomes.map((item, index) => (
                <li key={item.title}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section
          className="public-section public-section--paper"
          id="execution-path"
          aria-labelledby="path-title"
        >
          <div className="public-shell">
            <p className="public-kicker">Illustrative execution path</p>
            <h2 id="path-title">From a confirmed goal to a verified result.</h2>
            <p className="public-prose public-prose--narrow">
              This is the product path. It is not live customer telemetry.
            </p>
            <div className="execution-path">
              <i className="path-cursor" aria-hidden="true" />
              <ol>
                {pathSteps.map(([title, body]) => (
                  <li key={title}>
                    <strong>{title}</strong>
                    <span>{body}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        <section
          className="public-section public-section--ivory"
          id="boundary"
          aria-labelledby="boundary-title"
        >
          <div className="public-shell">
            <p className="public-kicker">Three different things</p>
            <h2 id="boundary-title">
              Evidence does not become authority. The model does not authorize
              itself.
            </h2>
            <div className="model-trio">
              <article>
                <h3>Authority</h3>
                <p>What the organization granted for this run.</p>
              </article>
              <article>
                <h3>Evidence</h3>
                <p>What the agent reasoned over.</p>
              </article>
              <article>
                <h3>Action</h3>
                <p>What the agent proposes to change.</p>
              </article>
            </div>
            <div className="guard-statement">
              <p className="public-kicker">Action Guard</p>
              <p>
                The deterministic guard compares the exact proposed action with
                the granted authority and the evidence that action relies on.
                Goal Lock is the boundary. The proposal is the request.
              </p>
            </div>
          </div>
        </section>

        <section
          className="public-section public-section--champagne"
          id="review"
          aria-labelledby="review-title"
        >
          <div className="public-shell public-split">
            <div>
              <p className="public-kicker">Human review</p>
              <h2 id="review-title">
                A consequential action can wait for an authorized person.
              </h2>
            </div>
            <div className="public-prose">
              <p>
                When policy requires it, execution has not happened yet. The
                reviewer decides on the exact action in front of them.
              </p>
              <p>
                Approval does not expand the Goal Lock. Before anything runs,
                the action is checked again against the same authority.
              </p>
            </div>
          </div>
        </section>

        <section
          className="public-section public-section--stone"
          id="verification"
          aria-labelledby="verification-title"
        >
          <div className="public-shell">
            <p className="public-kicker">After the decision</p>
            <h2 id="verification-title">
              An attempted tool call is not a completed result.
            </h2>
            <ol className="verify-stages" aria-label="Execution stages">
              <li>
                <strong>Proposed</strong>
                <span>The agent asked for a change.</span>
              </li>
              <li>
                <strong>Authorized</strong>
                <span>The guard allowed that exact action.</span>
              </li>
              <li>
                <strong>Executed</strong>
                <span>The side effect was attempted.</span>
              </li>
              <li>
                <strong>Verified</strong>
                <span>
                  The resulting change was confirmed for the current ticket
                  action, when that confirmation is recorded.
                </span>
              </li>
            </ol>
          </div>
        </section>

        <section
          className="public-section public-section--paper"
          id="enterprise"
          aria-labelledby="enterprise-title"
        >
          <div className="public-shell public-split">
            <div>
              <p className="public-kicker">Built toward operations</p>
              <h2 id="enterprise-title">
                The architecture is designed for a bounded workspace.
              </h2>
            </div>
            <div className="public-prose">
              <p>
                The current platform is built around server-authoritative
                identity, workspace isolation, an immutable Goal Lock, bounded
                text ingestion, a deterministic policy boundary, human review,
                audit evidence, restart-safe execution, verification, and
                retention controls.
              </p>
              <p>
                The live workbench accepts declared plain text, JSON, Markdown,
                HTML, and email. This page does not claim a certification, a
                completed compliance program, or coverage beyond that text.
              </p>
            </div>
          </div>
        </section>

        <section className="public-close" aria-labelledby="close-title">
          <div className="public-shell public-close__layout">
            <p className="public-kicker public-kicker--inverse">
              Agent execution security
            </p>
            <h2 id="close-title">
              AI can move fast. Your authority should not move with it.
            </h2>
            <Link className="button public-close__cta" href="/sign-in">
              See VETOQ in action
            </Link>
          </div>
        </section>
      </main>

      <footer className="public-footer">
        <div className="public-shell public-footer__grid">
          <div>
            <VetoqWordmark />
            <p>Agent Execution Security Platform</p>
            <p className="public-tagline">Trust the Goal. Verify the Action.</p>
          </div>
          <nav aria-label="Product">
            <h2>Product</h2>
            <a href="#problem">The gap</a>
            <a href="#execution-path">How it works</a>
            <a href="#boundary">The boundary</a>
            <a href="#review">Review</a>
          </nav>
          <nav aria-label="Access">
            <h2>Access</h2>
            <Link href="/sign-in">Sign in</Link>
            <Link href="/sign-up">Create account</Link>
          </nav>
        </div>
        <div className="public-shell public-footer__base">
          <p>© 2026 VETOQ</p>
        </div>
      </footer>
    </>
  );
}

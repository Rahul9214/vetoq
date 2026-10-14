import Link from "next/link";
import type { ReactNode } from "react";

import { VetoqWordmark } from "./vetoq-mark";

type AuthShellProps = {
  children: ReactNode;
  mode: "sign-in" | "sign-up";
};

const authCopy = {
  "sign-in": {
    eyebrow: "Sign in",
    title: "Define the authority.",
    support: "Then verify the action.",
    prompt: "New to VETOQ?",
    linkLabel: "Create an account",
    linkHref: "/sign-up",
    region: "Sign in",
  },
  "sign-up": {
    eyebrow: "Create access",
    title: "Verify the action.",
    support: "Start by defining the authority.",
    prompt: "Already have an account?",
    linkLabel: "Sign in",
    linkHref: "/sign-in",
    region: "Create account",
  },
} as const;

export function AuthShell({ children, mode }: AuthShellProps) {
  const copy = authCopy[mode];

  return (
    <main id="main-content" tabIndex={-1} className="auth-shell">
      <section className="auth-narrative" aria-labelledby="auth-brand-title">
        <Link className="auth-home" href="/" aria-label="VETOQ home">
          <VetoqWordmark />
        </Link>
        <div className="auth-narrative__copy">
          <p className="public-kicker">{copy.eyebrow}</p>
          <h1 id="auth-brand-title">{copy.title}</h1>
          <p>{copy.support}</p>
          <p className="public-tagline">Trust the Goal. Verify the Action.</p>
          <p className="auth-note">
            Submitted content stays untrusted. Execution stays inside the
            authority granted for the run.
          </p>
        </div>
      </section>
      <section className="auth-panel" aria-label={copy.region}>
        <div className="auth-panel__frame">
          {children}
          <p className="auth-switch">
            {copy.prompt} <Link href={copy.linkHref}>{copy.linkLabel}</Link>
          </p>
        </div>
      </section>
    </main>
  );
}

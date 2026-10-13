import Link from "next/link";
import type { ReactNode } from "react";

import { VetoqMark, VetoqWordmark } from "./vetoq-mark";

type AuthShellProps = {
  children: ReactNode;
  mode: "sign-in" | "sign-up";
};

const authCopy = {
  "sign-in": {
    eyebrow: "Return to the execution boundary",
    title: "Continue with your verified identity.",
    prompt: "New to VETOQ?",
    linkLabel: "Create an account",
    linkHref: "/sign-up",
  },
  "sign-up": {
    eyebrow: "Establish a verified identity",
    title: "Create your secure workbench access.",
    prompt: "Already have an account?",
    linkLabel: "Sign in",
    linkHref: "/sign-in",
  },
} as const;

const capabilities = [
  {
    title: "Identity before workspace access",
    body: "Authentication establishes the principal; explicit membership determines which workspace they may enter.",
  },
  {
    title: "Goal Lock before inspection",
    body: "Authorized intent is sealed before untrusted support content enters the analysis path.",
  },
  {
    title: "Deterministic control before execution",
    body: "Action Guard verifies the exact proposal before any privileged tool operation can run.",
  },
] as const;

export function AuthShell({ children, mode }: AuthShellProps) {
  const copy = authCopy[mode];

  return (
    <main id="main-content" className="auth-shell">
      <section className="auth-shell__brand" aria-labelledby="auth-brand-title">
        <Link
          className="auth-shell__home-link"
          href="/"
          aria-label="VETOQ home"
        >
          <VetoqWordmark />
        </Link>
        <div className="auth-shell__brand-copy">
          <p className="section-kicker">{copy.eyebrow}</p>
          <h1 id="auth-brand-title">{copy.title}</h1>
          <p className="auth-shell__tagline">
            Trust the Goal. Verify the Action.
          </p>
        </div>
        <ol className="auth-capabilities">
          {capabilities.map((capability, index) => (
            <li key={capability.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h2>{capability.title}</h2>
                <p>{capability.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="auth-shell__brand-mark" aria-hidden="true">
          <VetoqMark />
        </div>
      </section>

      <section
        className="auth-shell__form-region"
        aria-label={mode === "sign-in" ? "Sign in" : "Create account"}
      >
        <div className="auth-shell__mobile-brand">
          <Link href="/" aria-label="VETOQ home">
            <VetoqWordmark />
          </Link>
        </div>
        <div className="auth-shell__form-frame">
          {children}
          <p className="auth-shell__switch">
            {copy.prompt} <Link href={copy.linkHref}>{copy.linkLabel}</Link>
          </p>
        </div>
        <p className="auth-shell__trust-note">
          Authentication proves identity. Workspace membership and deterministic
          policy grant authority.
        </p>
      </section>
    </main>
  );
}

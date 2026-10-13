"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { PublicHome } from "@/components/public-home";
import { Workbench } from "@/components/workbench";
import { VetoqWordmark } from "@/components/vetoq-mark";

function SessionLoadingShell() {
  return (
    <div
      className="auth-loading-frame"
      role="status"
      aria-label="Loading VETOQ session"
    >
      <header className="site-header site-header-loading">
        <div className="nav-shell">
          <div className="brand-link">
            <VetoqWordmark />
          </div>
          <div className="nav-actions">
            <span className="auth-loading-badge">
              <span className="loading-pulse" aria-hidden="true" />
              <span>Verifying session</span>
            </span>
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="loading-main page-shell">
        <div className="loading-skeleton-container" aria-hidden="true">
          <div className="skeleton-line skeleton-line--kicker" />
          <div className="skeleton-line skeleton-line--heading" />
          <div className="skeleton-line skeleton-line--subheading" />
          <div className="skeleton-grid">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
        </div>
      </main>
    </div>
  );
}

export function HomeView({ initialUserId }: { initialUserId: string | null }) {
  const { isLoaded, isSignedIn } = useAuth();

  useEffect(() => {
    if (window.location.hash !== "#main-content") return;
    document.getElementById("main-content")?.focus();
  }, [isLoaded]);

  if (!isLoaded && initialUserId === null) {
    return <SessionLoadingShell />;
  }

  const signedIn = isLoaded ? Boolean(isSignedIn) : Boolean(initialUserId);

  if (!signedIn) {
    return (
      <div className="public-frame">
        <AppHeader mode="public" />
        <PublicHome />
      </div>
    );
  }

  return (
    <div className="console-frame">
      <AppHeader mode="console" />
      <main id="main-content" tabIndex={-1} className="console-main page-shell">
        <section className="console-intro" aria-labelledby="console-title">
          <div>
            <p className="eyebrow">Execution security / support triage</p>
            <h1 id="console-title">
              Verify the next action before it becomes an effect.
            </h1>
          </div>
          <p>
            Bind untrusted text to confirmed authority, inspect the proposal,
            and preserve the outcome as audit evidence.
          </p>
        </section>
        <Workbench />
      </main>
      <footer className="console-footer page-shell">
        <span>VETOQ</span>
        <span>Trust the Goal. Verify the Action.</span>
      </footer>
    </div>
  );
}

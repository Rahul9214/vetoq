"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { VetoqWordmark } from "@/components/vetoq-mark";

const publicLinks = [
  ["The gap", "#problem"],
  ["How it works", "#execution-path"],
  ["The boundary", "#boundary"],
  ["Review", "#review"],
] as const;

export function AppHeader({
  mode = "console",
}: {
  mode?: "public" | "console";
}) {
  const { isLoaded, isSignedIn } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuButton.current?.focus();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  return (
    <header
      className={`site-header ${
        mode === "public" ? "site-header-public" : "site-header-console"
      }`}
    >
      <div className="nav-shell">
        <Link className="brand-link" href="/" aria-label="VETOQ home">
          <VetoqWordmark />
        </Link>

        {mode === "public" ? (
          <nav className="desktop-nav" aria-label="Primary navigation">
            {publicLinks.map(([label, href]) => (
              <Link key={href} href={href}>
                {label}
              </Link>
            ))}
          </nav>
        ) : (
          <p className="console-context">
            <span className="signal-dot" aria-hidden="true" />
            Security workbench
          </p>
        )}

        <div className="nav-actions">
          {!isLoaded ? (
            <span className="auth-loading" role="status">
              Verifying session
            </span>
          ) : isSignedIn ? (
            <>
              {mode === "public" ? (
                <Link className="button button-primary nav-cta" href="/">
                  Open console
                </Link>
              ) : null}
              <span className="session-label">Session active</span>
              <UserButton
                appearance={{
                  variables: {
                    colorPrimary: "#61d5a0",
                    colorForeground: "#f3f0e7",
                    colorBackground: "#151b18",
                    colorMutedForeground: "#98a69e",
                    colorNeutral: "#f3f0e7",
                    borderRadius: "10px",
                  },
                  elements: {
                    avatarBox: "vetoq-user-avatar",
                    userButtonPopoverCard: "vetoq-user-popover",
                    userButtonPopoverActionButton: "vetoq-user-action",
                  },
                }}
              />
            </>
          ) : (
            <>
              <Link className="nav-sign-in" href="/sign-in">
                Sign in
              </Link>
              <Link className="button button-primary nav-cta" href="/sign-in">
                Open secure workbench
              </Link>
            </>
          )}
          {mode === "public" ? (
            <button
              ref={menuButton}
              className="menu-button"
              type="button"
              aria-expanded={menuOpen}
              aria-controls="mobile-navigation"
              aria-label={menuOpen ? "Close navigation" : "Open navigation"}
              onClick={() => setMenuOpen((current) => !current)}
            >
              <span aria-hidden="true" />
              <span aria-hidden="true" />
            </button>
          ) : null}
        </div>
      </div>
      {mode === "public" && menuOpen ? (
        <nav
          id="mobile-navigation"
          className="mobile-nav"
          aria-label="Mobile navigation"
        >
          {publicLinks.map(([label, href]) => (
            <Link key={href} href={href} onClick={() => setMenuOpen(false)}>
              {label}
            </Link>
          ))}
          {!isSignedIn ? (
            <>
              <Link href="/sign-in" onClick={() => setMenuOpen(false)}>
                Sign in
              </Link>
              <Link href="/sign-in" onClick={() => setMenuOpen(false)}>
                Open secure workbench
              </Link>
            </>
          ) : null}
        </nav>
      ) : null}
    </header>
  );
}

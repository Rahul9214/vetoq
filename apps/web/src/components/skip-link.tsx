"use client";

export function SkipLink() {
  return (
    <a
      className="skip-link"
      href="#main-content"
      tabIndex={0}
      onClick={() => {
        document.getElementById("main-content")?.focus();
      }}
    >
      Skip to main content
    </a>
  );
}

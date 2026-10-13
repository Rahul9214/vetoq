import { cva } from "class-variance-authority";

const badge = cva("status", {
  variants: {
    tone: {
      allow: "status-allow",
      review: "status-review",
      block: "status-block",
      neutral: "status-neutral",
    },
  },
});

const allowed = new Set(["ALLOW", "COMPLETED", "VERIFIED", "NO_ACTION"]);
const attention = new Set([
  "REVIEW",
  "AWAITING_REVIEW",
  "VERIFYING",
  "AUTHORIZING",
  "PROPOSING",
  "INSPECTING",
  "QUEUED",
  "PENDING",
]);

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toUpperCase();
  const tone = allowed.has(normalized)
    ? "allow"
    : attention.has(normalized)
      ? "review"
      : normalized === "BLOCK" || normalized === "BLOCKED"
        ? "block"
        : "neutral";
  const symbol =
    tone === "allow"
      ? "✓"
      : tone === "review"
        ? "◐"
        : tone === "block"
          ? "×"
          : "•";

  return (
    <span className={badge({ tone })}>
      <span className="status-symbol" aria-hidden="true">
        {symbol}
      </span>
      {normalized.replaceAll("_", " ")}
    </span>
  );
}

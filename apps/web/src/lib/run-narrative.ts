import type { RunDetail } from "@/lib/contracts";

const mediaLabels: Record<string, string> = {
  "text/plain": "Plain text",
  "application/json": "JSON",
  "text/markdown": "Markdown",
  "text/html": "HTML",
  "message/rfc822": "Email (RFC822)",
};

const representationLabels: Record<string, string> = {
  original: "Original",
  canonical_text: "Canonical text",
  decoded_text: "Decoded text",
  active_content: "Active content",
};

const transformLabels: Record<string, string> = {
  "json-canonical": "JSON canonicalization",
  "html-visible-text": "HTML visible text",
  "html-active-content": "HTML active content",
  "email-headers": "Email headers",
  "email-part-json": "Email JSON part",
  "email-part-text": "Email text part",
  "email-part-markdown": "Email Markdown part",
  "email-part-html-visible": "Email HTML visible text",
  "email-part-html-active": "Email HTML active content",
  "email-part-decode": "MIME part decode",
  base64: "Base64 decode",
};

const reasonLabels: Record<string, string> = {
  GOAL_SCOPE_MISMATCH:
    "The proposed target did not match the authority granted for this run.",
  TOOL_NOT_GRANTED: "The proposed tool is outside the granted authority.",
  IDENTITY_OR_MEMBERSHIP_INVALID:
    "The identity or workspace membership was not valid for this action.",
  REVOKED_OR_CANCELLED: "The workspace was inactive or the run was cancelled.",
  INVALID_STATE: "The run was not in a state that can authorize an action.",
  POLICY_UNAVAILABLE_OR_STALE:
    "The policy revision did not match the granted authority.",
  GOAL_EXPIRED: "The granted authority had expired.",
  LIMIT_EXHAUSTED: "The write or proposal limit for this run was already used.",
  INCOMPLETE_OR_INVALID_EVIDENCE:
    "The proposal did not rely on a complete recorded evidence set.",
  ARGUMENT_OR_ENVELOPE_MUTATION:
    "The proposed action did not match the sealed record.",
  ALREADY_EXECUTED: "An execution for this run is already recorded.",
  SELF_REVIEW_PROHIBITED: "The person who started the run cannot approve it.",
  APPROVAL_INVALID_OR_STALE:
    "The recorded approval did not match this exact action or had expired.",
  MATERIAL_UNCERTAINTY:
    "The proposal needs an authorized reviewer before execution.",
  WITHIN_CONFIRMED_AUTHORITY:
    "The proposed action fit the granted authority and the recorded evidence rules.",
};

const failureLabels: Record<string, string> = {
  source_integrity_failure:
    "The stored source did not match the sealed submission.",
  canonicalization_failure:
    "The declared content could not be turned into the expected derived evidence.",
  parser_limit_exceeded: "The content exceeded a recorded processing limit.",
  ingestion_incomplete: "Ingestion did not finish a complete evidence chain.",
  model_attempt_limit: "The model attempt limit was reached.",
};

export function mediaLabel(value: string | null): string {
  if (value === null) return "Not recorded";
  return mediaLabels[value] ?? value;
}

export function representationLabel(value: string | null): string {
  if (value === null) return "Legacy evidence";
  return representationLabels[value] ?? value;
}

export function transformLabel(value: string): string {
  return transformLabels[value] ?? value;
}

export function reasonLabel(code: string): string {
  return reasonLabels[code] ?? "A persisted guard reason is recorded.";
}

export function failureLabel(code: string): string {
  return failureLabels[code] ?? "The run is recorded as failed.";
}

export function outcomeTitle(run: RunDetail): string {
  if (run.ticket?.verified_at) return "Verified execution";
  switch (run.state) {
    case "COMPLETED":
      return "Completed";
    case "BLOCKED":
      return "Blocked before execution";
    case "AWAITING_REVIEW":
      return "Waiting for review";
    case "NO_ACTION":
      return "No action required";
    case "FAILED":
      return run.ticket ? "Failed" : "Failed before execution";
    case "CANCELLED":
      return "Cancelled";
    case "EXPIRED":
      return "Expired";
    default:
      return run.state
        .toLowerCase()
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
}

export function outcomeDetail(run: RunDetail): string {
  if (run.ticket?.verified_at) {
    return "VETOQ verified the resulting side effect against the executed action.";
  }
  switch (run.state) {
    case "COMPLETED":
      return run.ticket
        ? "A side effect is recorded. Verification is not recorded."
        : "The run is completed. No execution record is attached.";
    case "BLOCKED":
      return "The guard stopped the proposed action before the prohibited side effect.";
    case "AWAITING_REVIEW":
      return "Execution has not occurred. This exact action is waiting for an authorized reviewer.";
    case "NO_ACTION":
      return "The workflow completed without a business-side effect.";
    case "FAILED":
      return run.failure
        ? failureLabel(run.failure)
        : "The run is recorded as failed. No execution is recorded.";
    case "CANCELLED":
      return "This run was cancelled. No further effect is recorded from that point.";
    case "EXPIRED":
      return "The granted authority expired before a terminal effect was recorded.";
    default:
      return "No terminal outcome is recorded yet.";
  }
}

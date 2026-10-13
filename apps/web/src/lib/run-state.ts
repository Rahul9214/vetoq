import { TERMINAL_STATES, type RunDetail } from "@/lib/contracts";

export function isTerminal(state: string): boolean {
  return (TERMINAL_STATES as readonly string[]).includes(state);
}

export function goalLockStage(run: RunDetail): string {
  return run.goal_lock.goal || run.goal ? "SEALED" : run.state;
}

export function sourceStage(run: RunDetail): string {
  if (run.sources.length === 0) return run.state;
  return run.sources.every((source) => source.complete)
    ? "RECORDED"
    : "INCOMPLETE";
}

export function findingsStage(run: RunDetail): string {
  if (run.findings.length > 0) return "RECORDED";
  if (
    run.analysis ||
    run.action ||
    isTerminal(run.state) ||
    run.state === "AUTHORIZING" ||
    run.state === "AWAITING_REVIEW" ||
    run.state === "VERIFYING"
  ) {
    return "NONE";
  }
  return run.state;
}

export function proposalStage(run: RunDetail): string {
  if (run.action?.verdict) return run.action.verdict;
  if (run.action) return "PROPOSED";
  if (run.analysis) return "NO_ACTION";
  return run.state;
}

export function guardStage(run: RunDetail): string {
  return run.action?.verdict ?? run.state;
}

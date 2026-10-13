"""Provider-independent, closed security contracts."""

import hashlib
import json
from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

POLICY: Final = "support-triage/1"
TERMINAL = {"COMPLETED", "NO_ACTION", "BLOCKED", "FAILED", "CANCELLED", "EXPIRED"}
FAMILIES = (
    "Instruction Override",
    "Role Change",
    "Secret Extraction",
    "Tool Abuse",
    "Credential Theft",
    "Context Poisoning",
    "Multi-Step Jailbreaks",
    "Encoded Instructions",
    "Indirect Prompt Injection",
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoalLock(Strict):
    version: Literal[1] = 1
    template: Literal["support-triage/1"] = "support-triage/1"
    principal: str
    workspace_id: UUID
    source_id: UUID
    source_digest: str
    goal: str
    tool: Literal["tickets.create"] = "tickets.create"
    tool_version: Literal[1] = 1
    destination: Literal["local-ticket-store"] = "local-ticket-store"
    expires_at: datetime
    policy_revision: str = "support-triage/1"
    max_writes: Literal[1] = 1
    max_proposals: Literal[3] = 3
    max_continuations: Literal[1] = 1


class TicketArguments(Strict):
    workspace_id: UUID
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=8000)


class Proposal(Strict):
    tool: str = Field(min_length=1, max_length=80)
    tool_version: int
    arguments: TicketArguments
    evidence_ids: list[UUID] = Field(min_length=1, max_length=16)


class ModelFinding(Strict):
    family: Literal[
        "Instruction Override",
        "Role Change",
        "Secret Extraction",
        "Tool Abuse",
        "Credential Theft",
        "Context Poisoning",
        "Multi-Step Jailbreaks",
        "Encoded Instructions",
        "Indirect Prompt Injection",
    ]
    evidence_id: UUID
    quote: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=600)


class Analysis(Strict):
    findings: list[ModelFinding] = Field(max_length=30)
    uncertain: bool
    summary: str = Field(min_length=1, max_length=1000)
    proposal: Proposal | None


class Submission(Strict):
    workspace_id: UUID
    template: Literal["support-triage/1"]
    goal: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1, max_length=65536)
    confirmed: Literal[True]
    sanitized: Literal[True]


class ReviewDecision(Strict):
    digest: str = Field(pattern="^[a-f0-9]{64}$")
    decision: Literal["approve", "reject"]


class Decision(Strict):
    verdict: Literal["ALLOW", "BLOCK", "REVIEW"]
    reasons: list[str]


def digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def action_digest(run_id: str, envelope: GoalLock, proposal: Proposal) -> str:
    return digest(
        {
            "version": 1,
            "run_id": run_id,
            "envelope": envelope.model_dump(mode="json"),
            "proposal": proposal.model_dump(mode="json"),
        }
    )

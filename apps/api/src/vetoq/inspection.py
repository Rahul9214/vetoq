"""Bounded, inert text inspection. Heuristics are evidence, never authority."""

import base64
import hashlib
import re
from dataclasses import dataclass
from uuid import uuid4

RULES = {
    "Instruction Override": (
        r"(?i)ignore (?:all |the |previous |prior )*(?:instructions|rules)"
        r"|override (?:the )?(?:goal|instructions)"
    ),
    "Role Change": r"(?i)you are now|system\s*(?:message|:)|developer\s*:",
    "Secret Extraction": (
        r"(?i)(?:reveal|read|extract|print).{0,40}"
        r"(?:secret|system prompt|environment)"
    ),
    "Tool Abuse": r"(?i)tickets\.create|(?:different|another|workspace B) workspace|workspace B",
    "Credential Theft": (
        r"(?i)(?:send|steal|reveal|extract).{0,40}"
        r"(?:password|credential|api.key|token)"
    ),
    "Context Poisoning": (
        r"(?i)(?:policy|approval|administrator).{0,40}"
        r"(?:changed|approved|permits|override)"
    ),
    "Multi-Step Jailbreaks": r"(?i)first.{0,100}(?:then|next)|step [12]",
    "Encoded Instructions": r"(?i)base64|decode (?:this|the)|[A-Za-z0-9+/]{40,}={0,2}",
    "Indirect Prompt Injection": (
        r"(?i)(?:assistant|agent).{0,30}(?:must|ignore|execute)"
        r"|ignore previous instructions"
    ),
}


@dataclass(frozen=True)
class Representation:
    id: str
    content: str
    parent: str | None = None
    transform: str = "original"


def content_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def inspect(
    source_id: str, source: str
) -> tuple[list[Representation], list[dict[str, str | int]], bool]:
    nodes = [Representation(source_id, source)]
    complete = True
    total = 0
    frontier = nodes[:]
    for depth in range(3):
        following: list[Representation] = []
        for parent in frontier:
            matches = list(
                re.finditer(
                    r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/])", parent.content
                )
            )
            if len(matches) > 16:
                complete = False
            for match in matches[:16]:
                try:
                    decoded = base64.b64decode(match.group(), validate=True).decode("utf-8")
                except (ValueError, UnicodeError):
                    continue
                if not decoded.strip() or not decoded.isprintable():
                    continue
                if depth == 2 or total + len(decoded.encode()) > 131072:
                    complete = False
                    continue
                total += len(decoded.encode())
                child = Representation(str(uuid4()), decoded, parent.id, "base64/1")
                nodes.append(child)
                following.append(child)
        frontier = following
    findings: list[dict[str, str | int]] = []
    for node in nodes:
        for family, pattern in RULES.items():
            rule_match = re.search(pattern, node.content)
            if rule_match:
                findings.append(
                    {
                        "node_id": node.id,
                        "family": family,
                        "start": rule_match.start(),
                        "end": rule_match.end(),
                        "explanation": (
                            "Bounded heuristic match; contextual interpretation required."
                        ),
                    }
                )
    return nodes, findings, complete

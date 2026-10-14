"""Bounded, inert text inspection. Heuristics are evidence, never authority."""

import base64
import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from vetoq.ingestion.limits import BUDGETS

# The module specification names this decoder. It is not a media-type adapter.
DECODER_ID = "bounded-decoder"
DECODER_VERSION = "1"
_BASE64_TEXT = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/])")

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


def collect_findings(nodes: Sequence[Representation]) -> list[dict[str, str | int]]:
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
    return findings


def bounded_base64(
    roots: Sequence[Representation],
    *,
    derived_bytes: int,
    derived_count: int,
    enforce_count: bool,
    identify: Callable[[str, int], str],
) -> tuple[list[Representation], bool]:
    """Decode Base64 children from `roots`. The roots themselves are not returned.

    Byte and depth caps match the Module 002 decoder. `enforce_count` adds the
    run-wide derived-representation cap, which staged M003 uses and the legacy
    single-source inspection does not. A cap stops that child from being added.
    Earlier children stay in the returned list and `complete` is false.
    """

    children: list[Representation] = []
    complete = True
    total = derived_bytes
    count = derived_count
    ordinals: dict[str, int] = {}
    frontier = list(roots)
    for depth in range(BUDGETS.derivation_depth + 1):
        following: list[Representation] = []
        for parent in frontier:
            matches = list(_BASE64_TEXT.finditer(parent.content))
            if len(matches) > BUDGETS.base64_matches_per_representation:
                complete = False
            for match in matches[: BUDGETS.base64_matches_per_representation]:
                try:
                    decoded = base64.b64decode(match.group(), validate=True).decode("utf-8")
                except (ValueError, UnicodeError):
                    continue
                if not decoded.strip() or not decoded.isprintable():
                    continue
                encoded_size = len(decoded.encode())
                over_count = enforce_count and count + 1 > BUDGETS.derived_representations_per_run
                if (
                    depth == BUDGETS.derivation_depth
                    or total + encoded_size > BUDGETS.derived_text_bytes
                    or over_count
                ):
                    complete = False
                    continue
                total += encoded_size
                count += 1
                ordinal = ordinals.get(parent.id, 0)
                ordinals[parent.id] = ordinal + 1
                child = Representation(identify(parent.id, ordinal), decoded, parent.id, "base64/1")
                children.append(child)
                following.append(child)
        frontier = following
    return children, complete


def inspect(
    source_id: str, source: str
) -> tuple[list[Representation], list[dict[str, str | int]], bool]:
    root = Representation(source_id, source)
    children, complete = bounded_base64(
        [root],
        derived_bytes=0,
        derived_count=0,
        enforce_count=False,
        identify=lambda _parent, _ordinal: str(uuid4()),
    )
    nodes = [root, *children]
    return nodes, collect_findings(nodes), complete

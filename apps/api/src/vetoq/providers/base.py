"""Domain-facing inference boundary; no vendor SDK types."""

from dataclasses import dataclass
from typing import Protocol

from vetoq.contracts import Analysis, GoalLock


@dataclass(frozen=True)
class InferenceRequest:
    envelope: GoalLock
    sources: dict[str, str]
    continuation: bool = False


@dataclass(frozen=True)
class InferenceResult:
    analysis: Analysis
    provider: str
    model: str
    request_id: str
    elapsed_ms: int
    prompt_version: str


class ProviderError(Exception):
    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Provider(Protocol):
    def analyze(self, request: InferenceRequest) -> InferenceResult: ...

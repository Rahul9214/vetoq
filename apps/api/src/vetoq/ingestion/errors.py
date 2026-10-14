"""Pre-accept ingestion errors and post-accept processing codes.

Pre-accept errors create no run. Processing codes are persisted run failures.
They are not HTTP validation results, and neither type carries source text.
"""

from typing import Literal

PreAcceptCode = Literal[
    "unsupported_media_type",
    "unsupported_embedded_content",
    "malformed_content",
    "input_limit",
    "empty_input",
    "invalid_input",
]

ProcessingCode = Literal[
    "parser_limit_exceeded",
    "ingestion_incomplete",
    "source_integrity_failure",
    "canonicalization_failure",
]

RegistryCode = Literal["adapter_not_implemented", "adapter_already_registered"]


class IngestionError(Exception):
    """A pre-accept failure. `str(error)` is the stable code and nothing else."""

    def __init__(self, code: PreAcceptCode, status: int) -> None:
        super().__init__(code)
        self.code: PreAcceptCode = code
        self.status = status


class ProcessingFailure(Exception):
    """A post-accept run failure. This is not a 4xx validation response."""

    def __init__(self, code: ProcessingCode) -> None:
        super().__init__(code)
        self.code: ProcessingCode = code


class RegistryError(Exception):
    """Registry lookup failed closed. This does not select another adapter."""

    def __init__(self, code: RegistryCode) -> None:
        super().__init__(code)
        self.code: RegistryCode = code


def unsupported_media_type() -> IngestionError:
    return IngestionError("unsupported_media_type", 422)


def unsupported_embedded_content() -> IngestionError:
    return IngestionError("unsupported_embedded_content", 422)


def malformed_content() -> IngestionError:
    return IngestionError("malformed_content", 422)


def input_limit(status: Literal[413, 422]) -> IngestionError:
    return IngestionError("input_limit", status)


def empty_input() -> IngestionError:
    return IngestionError("empty_input", 422)


def invalid_input() -> IngestionError:
    return IngestionError("invalid_input", 422)

"""markdown version 1.

The original Markdown string is the textual evidence. It is not rendered,
fetched, or rewritten. This adapter adds no second copy of that string.
"""

from vetoq.ingestion.contracts import Canonicalization
from vetoq.ingestion.errors import unsupported_media_type
from vetoq.ingestion.media_types import DeclaredFormat, MediaType, normalize_media_type
from vetoq.ingestion.source_text import AcceptedSource, validate_source_text


class Markdown:
    """Pure text/markdown validation. Embedded markup stays untrusted text."""

    media_type = MediaType.MARKDOWN
    parser_id = "markdown"
    parser_version = "1"

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        if declaration.media_type is not MediaType.MARKDOWN:
            raise unsupported_media_type()
        return validate_source_text(source, declaration.charset)

    def accept(self, source: str, declared: str) -> AcceptedSource:
        declaration = normalize_media_type(declared)
        exact = self.validate(source, declaration)
        return AcceptedSource(
            source=exact,
            declaration=declaration,
            byte_size=len(exact.encode("utf-8")),
        )

    def canonicalize(self, source: str, declaration: DeclaredFormat) -> Canonicalization:
        self.validate(source, declaration)
        return Canonicalization()

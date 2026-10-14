"""text_plain version 1.

The original string is the textual evidence. This adapter does not add a
second copy of that string. Its parser id describes the adapter. It is not
metadata written onto the original row.
"""

from vetoq.ingestion.contracts import Canonicalization
from vetoq.ingestion.errors import unsupported_media_type
from vetoq.ingestion.media_types import DeclaredFormat, MediaType, normalize_media_type
from vetoq.ingestion.source_text import AcceptedSource, validate_source_text


class TextPlain:
    """Pure text/plain validation. The source stays untrusted."""

    media_type = MediaType.TEXT_PLAIN
    parser_id = "text_plain"
    parser_version = "1"

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        if declaration.media_type is not MediaType.TEXT_PLAIN:
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

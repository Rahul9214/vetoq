"""Explicit allowlist of ingestion adapters.

Contract support and runtime registration are separate. Lookup never substitutes
another media type, and this module does not import adapters by name from input.
"""

from vetoq.ingestion.contracts import IngestionAdapter
from vetoq.ingestion.email_rfc822 import EmailRfc822
from vetoq.ingestion.errors import RegistryError, unsupported_media_type
from vetoq.ingestion.html_inert import HtmlInert
from vetoq.ingestion.json_structured import JsonStructured
from vetoq.ingestion.markdown import Markdown
from vetoq.ingestion.media_types import MediaType, normalize_media_type
from vetoq.ingestion.text_plain import TextPlain


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[MediaType, IngestionAdapter] = {}

    def contract_supported(self) -> frozenset[MediaType]:
        return frozenset(MediaType)

    def implemented(self) -> frozenset[MediaType]:
        return frozenset(self._adapters)

    def register(self, adapter: IngestionAdapter) -> None:
        media_type = adapter.media_type
        if not isinstance(media_type, MediaType):
            raise unsupported_media_type()
        if media_type in self._adapters:
            raise RegistryError("adapter_already_registered")
        if not callable(adapter.validate) or not callable(adapter.canonicalize):
            raise RegistryError("adapter_not_implemented")
        self._adapters[media_type] = adapter

    def resolve(self, media_type: MediaType) -> IngestionAdapter:
        if not isinstance(media_type, MediaType):
            raise unsupported_media_type()
        adapter = self._adapters.get(media_type)
        if adapter is None:
            raise RegistryError("adapter_not_implemented")
        return adapter

    def resolve_declared(self, value: str) -> IngestionAdapter:
        declaration = normalize_media_type(value)
        return self.resolve(declaration.media_type)


def new_registry() -> AdapterRegistry:
    """An empty registry. Import does not register an adapter."""
    return AdapterRegistry()


def production_registry() -> AdapterRegistry:
    """The five contracted adapters. Lookup does not fall back.

    ``POST /runs`` validates through ``accept_declared_submission``, which
    resolves the declared adapter here. The worker resolves an adapter only
    for a staged original.
    """

    registry = AdapterRegistry()
    registry.register(TextPlain())
    registry.register(JsonStructured())
    registry.register(Markdown())
    registry.register(HtmlInert())
    registry.register(EmailRfc822())
    return registry

"""Ingestion kernel.

Format adapters are registered by ``production_registry``. ``POST /runs``
validates through that registry before it persists an original. The worker
calls the same registry for a staged original.
"""

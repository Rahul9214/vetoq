"""Persist staged M003 derivations. This module does not choose a route.

The live submission path stays Module 002. A staged original is recognized
only from stored metadata. Source text is not a type detector.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Connection

from vetoq.contracts import GoalLock
from vetoq.db import execute, one, rows
from vetoq.ingestion.contracts import (
    DerivedRepresentation,
    IngestionAdapter,
    TransformStep,
)
from vetoq.ingestion.errors import IngestionError, ProcessingFailure, RegistryError
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import Charset, DeclaredFormat, MediaType
from vetoq.ingestion.registry import AdapterRegistry, production_registry
from vetoq.inspection import (
    DECODER_ID,
    DECODER_VERSION,
    Representation,
    bounded_base64,
    collect_findings,
    content_digest,
)

_NAMESPACE = UUID("8f3c2a1e-6b47-5d90-a1c4-2e7b9d0f4a18")
_METADATA = (
    "declared_media_type",
    "representation_kind",
    "parser_id",
    "parser_version",
    "charset",
    "byte_size",
)
Record = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class StoredChild:
    node_id: str
    parent_id: str
    edge_id: str
    content: str
    kind: str
    parser_id: str
    parser_version: str
    supplier: str
    transform: str
    version: str
    lossy: bool
    steps: tuple[TransformStep, ...]


def derived_node_id(run_id: str, parent_id: str, ordinal: int, transform: str, version: str) -> str:
    material = "\n".join((run_id, parent_id, str(ordinal), transform, version))
    return str(uuid5(_NAMESPACE, "node\n" + material))


def derived_edge_id(run_id: str, parent_id: str, child_id: str) -> str:
    return str(uuid5(_NAMESPACE, "\n".join(("edge", run_id, parent_id, child_id))))


def finding_id(run_id: str, node_id: str, family: str, start: int, end: int) -> str:
    return str(
        uuid5(_NAMESPACE, "\n".join(("finding", run_id, node_id, family, str(start), str(end))))
    )


def is_staged_original(node: dict[str, Any]) -> bool:
    """True only when the stored row says it is an M003 original."""

    return node["representation_kind"] == "original" and node["declared_media_type"] is not None


def legacy_metadata_absent(node: dict[str, Any]) -> bool:
    return all(node[column] is None for column in _METADATA)


def persist_recorded_base64(
    connection: Connection,
    *,
    workspace_id: str,
    run_id: str,
    node_id: str,
    edge_id: str,
    parent_id: str,
    content: str,
    complete: bool,
    expires_at: object,
) -> None:
    """Insert one new decoded node, its edge, and the real base64/1 step."""

    child = _base64_child(node_id, edge_id, parent_id, content)
    _insert_node(connection, workspace_id, run_id, child, complete, expires_at)
    _insert_edge(connection, workspace_id, run_id, child)


def ingest_staged(
    connection: Connection,
    run: dict[str, Any],
    envelope: GoalLock,
    original: dict[str, Any],
    audit: dict[str, object],
    record: Record,
    *,
    registry: AdapterRegistry | None = None,
) -> tuple[list[Representation], list[dict[str, str | int]], bool]:
    """Revalidate, persist derived provenance, then inspect the persisted set.

    The caller owns the transaction. A failure before or during the inserts
    leaves that transaction able to roll every derived row back.
    """

    media, declaration = _authority(run, envelope, original)
    selected = production_registry() if registry is None else registry
    audit["source_id"] = original["id"]
    audit["declared_media_type"] = media.value
    audit["part_count"] = 0
    try:
        adapter = selected.resolve(media)
    except RegistryError:
        raise ProcessingFailure("canonicalization_failure") from None
    if adapter.media_type is not media:
        raise ProcessingFailure("canonicalization_failure")
    audit["parser_id"] = adapter.parser_id
    audit["parser_version"] = adapter.parser_version
    parts = _canonicalize(adapter, original["content"], declaration)
    children = _plan(run["id"], original["id"], original["content"], parts)
    audit["part_count"] = len(children)
    _reject_unexpected(connection, run["id"], original["id"], children)
    for child in children:
        _ensure_child(connection, run, original, child, record)
    nodes = [Representation(original["id"], original["content"]), *_views(children)]
    findings = collect_findings(nodes)
    _ensure_findings(connection, run, findings)
    audit["derived_count"] = len(children)
    return nodes, findings, True


def _authority(
    run: dict[str, Any], envelope: GoalLock, original: dict[str, Any]
) -> tuple[MediaType, DeclaredFormat]:
    if str(envelope.workspace_id) != run["workspace_id"]:
        raise ProcessingFailure("source_integrity_failure")
    if str(envelope.source_id) != original["id"]:
        raise ProcessingFailure("source_integrity_failure")
    if original["workspace_id"] != run["workspace_id"] or original["run_id"] != run["id"]:
        raise ProcessingFailure("source_integrity_failure")
    if original["trust"] != "untrusted" or original["representation_kind"] != "original":
        raise ProcessingFailure("source_integrity_failure")
    if original["parser_id"] is not None or original["parser_version"] is not None:
        raise ProcessingFailure("source_integrity_failure")
    digest = content_digest(original["content"])
    if original["digest"] != digest or original["digest"] != envelope.source_digest:
        raise ProcessingFailure("source_integrity_failure")
    if original["byte_size"] != len(original["content"].encode("utf-8")):
        raise ProcessingFailure("source_integrity_failure")
    try:
        media = MediaType(original["declared_media_type"])
    except ValueError:
        raise ProcessingFailure("source_integrity_failure") from None
    charset: Charset | None = None
    if original["charset"] is not None:
        try:
            charset = Charset(original["charset"])
        except ValueError:
            raise ProcessingFailure("source_integrity_failure") from None
    return media, DeclaredFormat(media, charset)


def _canonicalize(
    adapter: IngestionAdapter, content: str, declaration: DeclaredFormat
) -> tuple[DerivedRepresentation, ...]:
    try:
        exact = adapter.validate(content, declaration)
        if exact != content:
            raise ProcessingFailure("canonicalization_failure")
        result = adapter.canonicalize(content, declaration)
    except ProcessingFailure:
        raise
    except IngestionError as error:
        if error.code == "input_limit":
            raise ProcessingFailure("parser_limit_exceeded") from None
        raise ProcessingFailure("canonicalization_failure") from None
    except RegistryError:
        raise ProcessingFailure("canonicalization_failure") from None
    total = sum(len(part.content.encode()) for part in result.derived)
    _require_budget(len(result.derived), total)
    return result.derived


def _plan(
    run_id: str,
    original_id: str,
    original_content: str,
    parts: tuple[DerivedRepresentation, ...],
) -> tuple[StoredChild, ...]:
    planned: list[StoredChild] = []
    roots = [Representation(original_id, original_content)]
    derived_bytes = 0
    for ordinal, part in enumerate(parts):
        node_id = derived_node_id(
            run_id, original_id, ordinal, part.transform, part.transform_version
        )
        planned.append(_from_part(run_id, original_id, node_id, part))
        roots.append(Representation(node_id, part.content, original_id))
        derived_bytes += len(part.content.encode())
    decoded, complete = bounded_base64(
        roots,
        derived_bytes=derived_bytes,
        derived_count=len(parts),
        enforce_count=True,
        identify=lambda parent, ordinal: derived_node_id(run_id, parent, ordinal, "base64", "1"),
    )
    if not complete:
        raise ProcessingFailure("parser_limit_exceeded")
    for child in decoded:
        if child.parent is None:
            raise ProcessingFailure("canonicalization_failure")
        planned.append(
            _base64_child(
                child.id,
                derived_edge_id(run_id, child.parent, child.id),
                child.parent,
                child.content,
            )
        )
    return tuple(planned)


def _from_part(
    run_id: str, parent_id: str, node_id: str, part: DerivedRepresentation
) -> StoredChild:
    return StoredChild(
        node_id=node_id,
        parent_id=parent_id,
        edge_id=derived_edge_id(run_id, parent_id, node_id),
        content=part.content,
        kind=part.kind.value,
        parser_id=part.parser_id,
        parser_version=part.parser_version,
        supplier=f"{part.parser_id}/{part.parser_version}",
        transform=part.transform,
        version=part.transform_version,
        lossy=part.lossy,
        steps=_recorded_steps(part),
    )


def _base64_child(node_id: str, edge_id: str, parent_id: str, content: str) -> StoredChild:
    return StoredChild(
        node_id=node_id,
        parent_id=parent_id,
        edge_id=edge_id,
        content=content,
        kind="decoded_text",
        parser_id=DECODER_ID,
        parser_version=DECODER_VERSION,
        supplier=f"{DECODER_ID}/{DECODER_VERSION}",
        transform="base64",
        version="1",
        lossy=False,
        steps=(TransformStep("base64", "1"),),
    )


def _recorded_steps(part: DerivedRepresentation) -> tuple[TransformStep, ...]:
    steps = part.transform_steps
    if not steps:
        raise ProcessingFailure("canonicalization_failure")
    if len(steps) > BUDGETS.transform_steps_per_edge:
        raise ProcessingFailure("parser_limit_exceeded")
    return steps


def _require_budget(count: int, total: int) -> None:
    if count > BUDGETS.derived_representations_per_run or total > BUDGETS.derived_text_bytes:
        raise ProcessingFailure("parser_limit_exceeded")


def _reject_unexpected(
    connection: Connection, run_id: str, original_id: str, children: tuple[StoredChild, ...]
) -> None:
    expected_nodes = {child.node_id for child in children}
    expected_edges = {child.edge_id for child in children}
    stored_nodes = {
        row["id"]
        for row in rows(
            connection,
            "SELECT id FROM content_nodes WHERE run_id=:run AND id<>:original",
            {"run": run_id, "original": original_id},
        )
    }
    stored_edges = {
        row["id"]
        for row in rows(
            connection, "SELECT id FROM content_edges WHERE run_id=:run", {"run": run_id}
        )
    }
    if not stored_nodes <= expected_nodes or not stored_edges <= expected_edges:
        raise ProcessingFailure("canonicalization_failure")


def _ensure_child(
    connection: Connection,
    run: dict[str, Any],
    original: dict[str, Any],
    child: StoredChild,
    record: Record,
) -> None:
    existing = one(connection, "SELECT * FROM content_nodes WHERE id=:id", {"id": child.node_id})
    if existing is None:
        _insert_node(
            connection,
            run["workspace_id"],
            run["id"],
            child,
            True,
            original["expires_at"],
        )
        _insert_edge(connection, run["workspace_id"], run["id"], child)
        record(
            "INGESTION_CANONICALIZED",
            {
                "parent_id": child.parent_id,
                "child_id": child.node_id,
                "transform": child.transform,
                "lossy": child.lossy,
                "parser_id": child.parser_id,
                "parser_version": child.parser_version,
                "child_digest": content_digest(child.content),
            },
        )
        return
    _verify_node(existing, run, child)
    edge = one(connection, "SELECT * FROM content_edges WHERE id=:id", {"id": child.edge_id})
    if edge is None:
        raise ProcessingFailure("canonicalization_failure")
    _verify_edge(edge, run, child)
    _verify_steps(connection, child)


def _views(children: tuple[StoredChild, ...]) -> list[Representation]:
    return [
        Representation(
            child.node_id,
            child.content,
            child.parent_id,
            f"{child.transform}/{child.version}",
        )
        for child in children
    ]


def _ensure_findings(
    connection: Connection, run: dict[str, Any], findings: list[dict[str, str | int]]
) -> None:
    for finding in findings:
        start = int(finding["start"])
        end = int(finding["end"])
        family = str(finding["family"])
        node_id = str(finding["node_id"])
        identifier = finding_id(run["id"], node_id, family, start, end)
        existing = one(connection, "SELECT * FROM findings WHERE id=:id", {"id": identifier})
        if existing is None:
            execute(
                connection,
                """
                INSERT INTO findings(
                    id,workspace_id,run_id,node_id,origin,family,explanation,
                    start_offset,end_offset,version
                ) VALUES(
                    :id,:workspace,:run,:node,'deterministic',:family,
                    :explanation,:start,:end,'rules/1'
                )
                """,
                {
                    "id": identifier,
                    "workspace": run["workspace_id"],
                    "run": run["id"],
                    "node": node_id,
                    "family": family,
                    "explanation": finding["explanation"],
                    "start": start,
                    "end": end,
                },
            )
            continue
        if (
            existing["run_id"] != run["id"]
            or existing["workspace_id"] != run["workspace_id"]
            or existing["node_id"] != node_id
            or existing["family"] != family
            or existing["start_offset"] != start
            or existing["end_offset"] != end
        ):
            raise ProcessingFailure("canonicalization_failure")


def _verify_node(existing: dict[str, Any], run: dict[str, Any], child: StoredChild) -> None:
    digest = content_digest(child.content)
    if (
        existing["workspace_id"] != run["workspace_id"]
        or existing["run_id"] != run["id"]
        or existing["origin"] != "derived"
        or existing["supplier"] != child.supplier
        or existing["digest"] != digest
        or existing["content"] != child.content
        or existing["trust"] != "untrusted"
        or existing["complete"] is not True
        or existing["declared_media_type"] is not None
        or existing["representation_kind"] != child.kind
        or existing["parser_id"] != child.parser_id
        or existing["parser_version"] != child.parser_version
        or existing["charset"] != "utf-8"
        or existing["byte_size"] != len(child.content.encode("utf-8"))
    ):
        raise ProcessingFailure("canonicalization_failure")


def _verify_edge(edge: dict[str, Any], run: dict[str, Any], child: StoredChild) -> None:
    if (
        edge["workspace_id"] != run["workspace_id"]
        or edge["run_id"] != run["id"]
        or edge["parent_id"] != child.parent_id
        or edge["child_id"] != child.node_id
        or edge["transform"] != child.transform
        or edge["version"] != child.version
        or edge["lossy"] is not child.lossy
        or edge["transform_step_count"] != len(child.steps)
    ):
        raise ProcessingFailure("canonicalization_failure")


def _verify_steps(connection: Connection, child: StoredChild) -> None:
    stored = rows(
        connection,
        """
        SELECT step_index,transform,version FROM content_edge_steps
        WHERE edge_id=:edge ORDER BY step_index
        """,
        {"edge": child.edge_id},
    )
    expected = [
        {"step_index": index, "transform": step.transform, "version": step.version}
        for index, step in enumerate(child.steps, start=1)
    ]
    if stored != expected:
        raise ProcessingFailure("canonicalization_failure")


def _insert_node(
    connection: Connection,
    workspace_id: str,
    run_id: str,
    child: StoredChild,
    complete: bool,
    expires_at: object,
) -> None:
    execute(
        connection,
        """
        INSERT INTO content_nodes(
            id,workspace_id,run_id,origin,supplier,digest,content,
            trust,complete,expires_at,
            declared_media_type,representation_kind,parser_id,parser_version,
            charset,byte_size
        ) VALUES(
            :id,:workspace,:run,'derived',:supplier,:digest,:content,
            'untrusted',:complete,:expires,
            NULL,:kind,:parser,:parser_version,'utf-8',:bytes
        )
        """,
        {
            "id": child.node_id,
            "workspace": workspace_id,
            "run": run_id,
            "supplier": child.supplier,
            "digest": content_digest(child.content),
            "content": child.content,
            "complete": complete,
            "expires": expires_at,
            "kind": child.kind,
            "parser": child.parser_id,
            "parser_version": child.parser_version,
            "bytes": len(child.content.encode("utf-8")),
        },
    )


def _insert_edge(
    connection: Connection, workspace_id: str, run_id: str, child: StoredChild
) -> None:
    execute(
        connection,
        """
        INSERT INTO content_edges(
            id,workspace_id,run_id,parent_id,child_id,
            transform,version,lossy,transform_step_count
        ) VALUES(
            :id,:workspace,:run,:parent,:child,:transform,:version,:lossy,:count
        )
        """,
        {
            "id": child.edge_id,
            "workspace": workspace_id,
            "run": run_id,
            "parent": child.parent_id,
            "child": child.node_id,
            "transform": child.transform,
            "version": child.version,
            "lossy": child.lossy,
            "count": len(child.steps),
        },
    )
    for index, step in enumerate(child.steps, start=1):
        execute(
            connection,
            """
            INSERT INTO content_edge_steps(edge_id,step_index,transform,version)
            VALUES(:edge,:index,:transform,:version)
            """,
            {
                "edge": child.edge_id,
                "index": index,
                "transform": step.transform,
                "version": step.version,
            },
        )

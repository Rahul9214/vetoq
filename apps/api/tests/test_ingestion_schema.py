"""Schema 0004 storage rules. No worker canonicalization and no route change."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from vetoq.config import Settings
from vetoq.contracts import GoalLock
from vetoq.db import engine_for, execute, one

API_ROOT = Path(__file__).resolve().parents[1]
FRESH_DATABASE = "vetoq_m003_migrate_test"
DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
M002_SOURCE = (API_ROOT / "migrations" / "versions" / "0001_security_slice.py").read_text(
    encoding="utf-8"
)
M002_CLAIM = (API_ROOT / "migrations" / "versions" / "0002_worker_claim.py").read_text(
    encoding="utf-8"
)


def test_revision_chain_has_one_head() -> None:
    script = ScriptDirectory(str(API_ROOT / "migrations"))
    assert script.get_heads() == ["0007_lineage_execution_lookup"]
    lookup = script.get_revision("0007_lineage_execution_lookup")
    strict = script.get_revision("0006_lineage_enforcement")
    lineage = script.get_revision("0005_provenance_lineage")
    current = script.get_revision("0004_edge_steps")
    revision = script.get_revision("0003_secure_ingestion")
    previous = script.get_revision("0002_worker_claim")
    assert lookup is not None and strict is not None and lineage is not None and current is not None
    assert revision is not None and previous is not None
    assert lookup.down_revision == "0006_lineage_enforcement"
    assert strict.down_revision == "0005_provenance_lineage"
    assert lineage.down_revision == "0004_edge_steps"
    assert current.down_revision == "0003_secure_ingestion"
    assert revision.down_revision == "0002_worker_claim"
    assert previous.down_revision == "0001_security_slice"


def test_applied_migrations_were_not_rewritten_for_ingestion_metadata() -> None:
    assert "declared_media_type" not in M002_SOURCE
    assert "declared_media_type" not in M002_CLAIM
    assert "transform_step_count" not in M002_SOURCE
    assert "transform_step_count" not in M002_CLAIM
    source = (API_ROOT / "migrations" / "versions" / "0003_secure_ingestion.py").read_text(
        encoding="utf-8"
    )
    assert "transform_step_count" not in source
    assert "Destructive rollback requires an explicit operator recovery plan" in source
    steps = (API_ROOT / "migrations" / "versions" / "0004_edge_steps.py").read_text(
        encoding="utf-8"
    )
    assert "Destructive rollback requires an explicit operator recovery plan" in steps


def test_goal_lock_does_not_gain_ingestion_fields() -> None:
    assert "media_type" not in GoalLock.model_fields
    assert "parser_id" not in GoalLock.model_fields
    assert {"source_id", "source_digest"}.issubset(GoalLock.model_fields)


def _engine(url: str) -> Engine:
    return engine_for(Settings(_env_file=None, environment="test", database_url=SecretStr(url)))


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    database = _engine(DATABASE_URL)
    try:
        require_disposable_engine(database)
    except UnsafeTestDatabase as error:
        database.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    yield database
    database.dispose()


def _replace_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, ""))


def _seed(connection: Connection) -> tuple[str, str]:
    workspace, principal, run_id = str(uuid4()), "user_" + uuid4().hex, str(uuid4())
    execute(
        connection,
        "INSERT INTO workspaces(id,name) VALUES(:id,'Schema fixture')",
        {"id": workspace},
    )
    execute(
        connection,
        """
        INSERT INTO memberships(workspace_id,principal,role)
        VALUES(:workspace,:principal,'operator')
        """,
        {"workspace": workspace, "principal": principal},
    )
    execute(
        connection,
        """
        INSERT INTO runs(
          id,workspace_id,principal,submission_key,submission_digest,
          envelope,state,expires_at
        ) VALUES(
          :run,:workspace,:principal,:key,'digest',
          CAST('{}' AS jsonb),'QUEUED',now()+interval '30 minutes'
        )
        """,
        {"run": run_id, "workspace": workspace, "principal": principal, "key": uuid4().hex},
    )
    return workspace, run_id


def _insert_node(connection: Connection, workspace: str, run_id: str, **columns: object) -> str:
    node_id = str(uuid4())
    payload: dict[str, object] = {
        "id": node_id,
        "workspace": workspace,
        "run": run_id,
        "origin": "pasted-email",
        "supplier": "user_schema",
        "digest": "a" * 64,
        "content": "hello",
        "declared_media_type": None,
        "representation_kind": None,
        "parser_id": None,
        "parser_version": None,
        "charset": None,
        "byte_size": None,
    }
    payload.update(columns)
    execute(
        connection,
        """
        INSERT INTO content_nodes(
          id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at,
          declared_media_type,representation_kind,parser_id,parser_version,charset,byte_size
        ) VALUES(
          :id,:workspace,:run,:origin,:supplier,:digest,:content,'untrusted',true,
          now()+interval '24 hours',:declared_media_type,:representation_kind,
          :parser_id,:parser_version,:charset,:byte_size
        )
        """,
        payload,
    )
    return node_id


@pytest.mark.integration
def test_fresh_database_migrates_from_base_to_ingestion_head() -> None:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    fresh_url = _replace_database(DATABASE_URL, FRESH_DATABASE)
    require_disposable_url(fresh_url, DEVELOPMENT_URLS)
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
            (FRESH_DATABASE,),
        )
        connection.execute(f"DROP DATABASE IF EXISTS {FRESH_DATABASE}")
        connection.execute(f"CREATE DATABASE {FRESH_DATABASE}")
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=API_ROOT,
            env={
                **os.environ,
                "VETOQ_DATABASE_URL": fresh_url,
                "PYTHONPATH": str(API_ROOT / "src"),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.replace(fresh_url, "[redacted]")
        fresh = _engine(fresh_url)
        try:
            require_disposable_engine(fresh)
            with fresh.connect() as connection:
                version = connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                ).scalar_one()
                columns = {
                    row[0]
                    for row in connection.exec_driver_sql(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='content_nodes'
                        """
                    )
                }
                edge_columns = {
                    row[0]
                    for row in connection.exec_driver_sql(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='content_edges'
                        """
                    )
                }
                step_table = connection.exec_driver_sql(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name='content_edge_steps'
                    """
                ).scalar_one_or_none()
            assert version == "0007_lineage_execution_lookup"
            assert {
                "declared_media_type",
                "representation_kind",
                "parser_id",
                "parser_version",
                "charset",
                "byte_size",
            }.issubset(columns)
            assert "transform_step_count" in edge_columns
            assert step_table == 1
        finally:
            fresh.dispose()
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (FRESH_DATABASE,),
            )
            connection.execute(f"DROP DATABASE IF EXISTS {FRESH_DATABASE}")


@pytest.mark.integration
def test_legacy_content_row_remains_valid_with_null_metadata(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id = _seed(connection)
        node_id = str(uuid4())
        execute(
            connection,
            """
            INSERT INTO content_nodes(
              id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
            ) VALUES(
              :id,:workspace,:run,'pasted-email','user_schema','digest','legacy',
              'untrusted',true,now()+interval '24 hours'
            )
            """,
            {"id": node_id, "workspace": workspace, "run": run_id},
        )
        stored = one(
            connection,
            """
            SELECT declared_media_type, representation_kind, parser_id,
                   parser_version, charset, byte_size
            FROM content_nodes WHERE id=:id
            """,
            {"id": node_id},
        )
    assert stored == {
        "declared_media_type": None,
        "representation_kind": None,
        "parser_id": None,
        "parser_version": None,
        "charset": None,
        "byte_size": None,
    }


@pytest.mark.integration
def test_original_and_derived_metadata_rows_insert(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id = _seed(connection)
        original = _insert_node(
            connection,
            workspace,
            run_id,
            declared_media_type="text/plain",
            representation_kind="original",
            charset="utf-8",
            byte_size=5,
        )
        derived = _insert_node(
            connection,
            workspace,
            run_id,
            representation_kind="canonical_text",
            parser_id="json_structured",
            parser_version="1",
            charset="utf-8",
            byte_size=2,
            content="{}",
        )
        _insert_node(
            connection,
            workspace,
            run_id,
            representation_kind="decoded_text",
            parser_id="bounded-decoder",
            parser_version="1",
            byte_size=4,
        )
        _insert_node(
            connection,
            workspace,
            run_id,
            representation_kind="active_content",
            parser_id="html_inert",
            parser_version="1",
            byte_size=5,
        )
        edge_id = str(uuid4())
        execute(
            connection,
            """
            INSERT INTO content_edges(
              id,workspace_id,run_id,parent_id,child_id,transform,version,lossy
            ) VALUES(:id,:workspace,:run,:parent,:child,'json-canonical','1',true)
            """,
            {
                "id": edge_id,
                "workspace": workspace,
                "run": run_id,
                "parent": original,
                "child": derived,
            },
        )
        edge = one(
            connection,
            "SELECT transform,version,lossy FROM content_edges WHERE id=:id",
            {"id": edge_id},
        )
        edge_columns = [
            row[0]
            for row in connection.exec_driver_sql(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name='content_edges' ORDER BY ordinal_position
                """
            )
        ]
    assert edge == {"transform": "json-canonical", "version": "1", "lossy": True}
    assert edge_columns == [
        "id",
        "workspace_id",
        "run_id",
        "parent_id",
        "child_id",
        "transform",
        "version",
        "lossy",
        "transform_step_count",
    ]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("declared_media_type", "application/pdf", "content_declared_media_type"),
        ("charset", "utf-16", "content_charset"),
        ("byte_size", -1, "content_byte_size"),
        ("representation_kind", "pdf_page", "content_representation_kind"),
    ],
)
def test_invalid_ingestion_metadata_is_rejected(
    database: Engine, column: str, value: object, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        with database.begin() as connection:
            workspace, run_id = _seed(connection)
            _insert_node(connection, workspace, run_id, **{column: value})


@pytest.mark.integration
@pytest.mark.parametrize(
    "columns",
    [
        {"parser_id": "json_structured"},
        {"parser_version": "1"},
    ],
)
def test_parser_identity_must_be_paired(database: Engine, columns: dict[str, str]) -> None:
    with pytest.raises(IntegrityError, match="content_parser_pair"):
        with database.begin() as connection:
            workspace, run_id = _seed(connection)
            _insert_node(connection, workspace, run_id, **columns)


@pytest.mark.integration
def test_derived_representation_requires_a_parser_pair(database: Engine) -> None:
    with pytest.raises(IntegrityError, match="content_derived_parser"):
        with database.begin() as connection:
            workspace, run_id = _seed(connection)
            _insert_node(connection, workspace, run_id, representation_kind="decoded_text")


@pytest.mark.integration
@pytest.mark.parametrize(
    "column",
    [
        "declared_media_type",
        "representation_kind",
        "parser_id",
        "parser_version",
        "charset",
        "byte_size",
        "content",
        "digest",
        "trust",
    ],
)
def test_content_metadata_and_body_stay_immutable(database: Engine, column: str) -> None:
    with database.begin() as connection:
        workspace, run_id = _seed(connection)
        node_id = _insert_node(
            connection,
            workspace,
            run_id,
            declared_media_type="text/html",
            representation_kind="active_content",
            parser_id="html_inert",
            parser_version="1",
            charset="us-ascii",
            byte_size=5,
        )
    value: object = {
        "declared_media_type": "text/plain",
        "representation_kind": "original",
        "parser_id": "markdown",
        "parser_version": "2",
        "charset": "utf-8",
        "byte_size": 0,
        "content": "changed",
        "digest": "changed",
        "trust": "untrusted",
    }[column]
    with pytest.raises(DBAPIError, match="immutable_content"):
        with database.begin() as connection:
            execute(
                connection,
                f"UPDATE content_nodes SET {column}=:value WHERE id=:id",
                {"value": value, "id": node_id},
            )

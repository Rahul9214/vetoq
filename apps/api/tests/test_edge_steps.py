"""0004 edge-step schema. No worker write and no public activation."""

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from vetoq.config import Settings
from vetoq.db import engine_for, execute, one, rows
from vetoq.ingestion.contracts import TransformStep, recorded_transform_steps
from vetoq.ingestion.limits import BUDGETS

API_ROOT = Path(__file__).resolve().parents[1]
FRESH_DATABASE = "vetoq_m003_edge_steps_test"
DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration


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
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
            WHERE state IN ('QUEUED','PROPOSING','AUTHORIZING','VERIFYING','AWAITING_REVIEW')
            """,
        )
    database.dispose()


def _seed(connection: Connection) -> tuple[str, str, str, str]:
    workspace, principal, run_id = str(uuid4()), "user_" + uuid4().hex, str(uuid4())
    execute(
        connection,
        "INSERT INTO workspaces(id,name) VALUES(:id,'Edge steps')",
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
    parent, child = str(uuid4()), str(uuid4())
    for node_id, content in ((parent, "parent"), (child, "child")):
        execute(
            connection,
            """
            INSERT INTO content_nodes(
              id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
            ) VALUES(
              :id,:workspace,:run,'pasted-email','user_schema',:digest,:content,
              'untrusted',true,now()+interval '24 hours'
            )
            """,
            {
                "id": node_id,
                "workspace": workspace,
                "run": run_id,
                "digest": "b" * 64,
                "content": content,
            },
        )
    return workspace, run_id, parent, child


def _insert_edge(
    connection: Connection,
    workspace: str,
    run_id: str,
    parent: str,
    child: str,
    *,
    count: int | None,
    transform: str = "email-part-json",
    version: str = "1",
) -> str:
    edge_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO content_edges(
          id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,
          transform_step_count
        ) VALUES(
          :id,:workspace,:run,:parent,:child,:transform,:version,true,:count
        )
        """,
        {
            "id": edge_id,
            "workspace": workspace,
            "run": run_id,
            "parent": parent,
            "child": child,
            "transform": transform,
            "version": version,
            "count": count,
        },
    )
    return edge_id


def _insert_step(
    connection: Connection,
    edge_id: str,
    index: int,
    transform: str = "email-part-decode",
    version: str = "1",
) -> None:
    execute(
        connection,
        """
        INSERT INTO content_edge_steps(edge_id,step_index,transform,version)
        VALUES(:edge,:index,:transform,:version)
        """,
        {"edge": edge_id, "index": index, "transform": transform, "version": version},
    )


def _step_count(connection: Connection, edge_id: str) -> int:
    value = connection.execute(
        text("SELECT count(*) FROM content_edge_steps WHERE edge_id=:edge"),
        {"edge": edge_id},
    ).scalar_one()
    assert isinstance(value, int)
    return value


def test_historical_edge_has_null_count_and_no_steps(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id, parent, child = _seed(connection)
        edge_id = str(uuid4())
        execute(
            connection,
            """
            INSERT INTO content_edges(
              id,workspace_id,run_id,parent_id,child_id,transform,version,lossy
            ) VALUES(:id,:workspace,:run,:parent,:child,'base64','1',false)
            """,
            {
                "id": edge_id,
                "workspace": workspace,
                "run": run_id,
                "parent": parent,
                "child": child,
            },
        )
        stored = one(
            connection,
            "SELECT transform,version,transform_step_count FROM content_edges WHERE id=:id",
            {"id": edge_id},
        )
        found = rows(
            connection,
            """
            SELECT step_index,transform,version FROM content_edge_steps
            WHERE edge_id=:id ORDER BY step_index
            """,
            {"id": edge_id},
        )
    assert stored == {"transform": "base64", "version": "1", "transform_step_count": None}
    assert found == []
    assert recorded_transform_steps(None, ()) is None


def test_one_step_and_two_step_chains_commit(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id, parent, child = _seed(connection)
        single = _insert_edge(
            connection, workspace, run_id, parent, child, count=1, transform="json-canonical"
        )
        _insert_step(connection, single, 1, "json-canonical")
    with database.begin() as connection:
        other_child = str(uuid4())
        execute(
            connection,
            """
            INSERT INTO content_nodes(
              id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
            ) VALUES(
              :id,:workspace,:run,'derived','json_structured/1',:digest,'{}',
              'untrusted',true,now()+interval '24 hours'
            )
            """,
            {"id": other_child, "workspace": workspace, "run": run_id, "digest": "c" * 64},
        )
        paired = _insert_edge(connection, workspace, run_id, parent, other_child, count=2)
        _insert_step(connection, paired, 1, "email-part-decode")
        _insert_step(connection, paired, 2, "json-canonical")
        stored = rows(
            connection,
            """
            SELECT step_index,transform,version FROM content_edge_steps
            WHERE edge_id=:id ORDER BY step_index
            """,
            {"id": paired},
        )
    assert stored == [
        {"step_index": 1, "transform": "email-part-decode", "version": "1"},
        {"step_index": 2, "transform": "json-canonical", "version": "1"},
    ]
    assert recorded_transform_steps(
        2,
        (
            TransformStep("email-part-decode", "1"),
            TransformStep("json-canonical", "1"),
        ),
    ) == (
        TransformStep("email-part-decode", "1"),
        TransformStep("json-canonical", "1"),
    )


def test_incomplete_gap_and_unrecorded_step_fail_at_commit(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id, parent, child = _seed(connection)
    with pytest.raises(DBAPIError, match="edge_steps_incomplete"):
        with database.begin() as connection:
            edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=2)
            _insert_step(connection, edge_id, 1)
    with pytest.raises(DBAPIError, match="edge_steps_incomplete"):
        with database.begin() as connection:
            edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=2)
            _insert_step(connection, edge_id, 1)
            _insert_step(connection, edge_id, 3, "json-canonical")
    with pytest.raises(DBAPIError, match="edge_steps_incomplete"):
        with database.begin() as connection:
            edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=None)
            _insert_step(connection, edge_id, 1)
    with database.connect() as connection:
        remaining = connection.execute(
            text("SELECT count(*) FROM content_edges WHERE run_id=:run"),
            {"run": run_id},
        ).scalar_one()
    assert remaining == 0


@pytest.mark.parametrize(
    ("statement", "params", "constraint"),
    [
        (
            """
            INSERT INTO content_edges(
              id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,
              transform_step_count
            ) VALUES(:id,:workspace,:run,:parent,:child,'base64','1',false,0)
            """,
            {},
            "content_edge_step_count",
        ),
        (
            """
            INSERT INTO content_edges(
              id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,
              transform_step_count
            ) VALUES(:id,:workspace,:run,:parent,:child,'base64','1',false,5)
            """,
            {},
            "content_edge_step_count",
        ),
    ],
)
def test_step_count_outside_one_through_four_is_rejected(
    database: Engine, statement: str, params: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        with database.begin() as connection:
            workspace, run_id, parent, child = _seed(connection)
            execute(
                connection,
                statement,
                {
                    "id": str(uuid4()),
                    "workspace": workspace,
                    "run": run_id,
                    "parent": parent,
                    "child": child,
                    **params,
                },
            )


@pytest.mark.parametrize(
    ("index", "transform", "version", "constraint"),
    [
        (0, "base64", "1", "content_edge_step_index"),
        (5, "base64", "1", "content_edge_step_index"),
        (1, " ", "1", "content_edge_step_transform"),
        (1, "", "1", "content_edge_step_transform"),
        (1, "x" * 81, "1", "content_edge_step_transform"),
        (1, "base64", "", "content_edge_step_version"),
        (1, "base64", " ", "content_edge_step_version"),
        (1, "base64", "v" * 81, "content_edge_step_version"),
    ],
)
def test_malformed_step_is_rejected(
    database: Engine, index: int, transform: str, version: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        with database.begin() as connection:
            workspace, run_id, parent, child = _seed(connection)
            edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=1)
            _insert_step(connection, edge_id, index, transform, version)


def test_duplicate_step_index_is_rejected(database: Engine) -> None:
    with pytest.raises(IntegrityError, match="content_edge_steps_pkey"):
        with database.begin() as connection:
            workspace, run_id, parent, child = _seed(connection)
            edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=1)
            _insert_step(connection, edge_id, 1, "json-canonical")
            _insert_step(connection, edge_id, 1, "json-canonical")


def test_edge_and_step_updates_are_rejected(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id, parent, child = _seed(connection)
        edge_id = _insert_edge(
            connection, workspace, run_id, parent, child, count=1, transform="json-canonical"
        )
        _insert_step(connection, edge_id, 1, "json-canonical")
    with pytest.raises(DBAPIError, match="immutable_edge"):
        with database.begin() as connection:
            execute(
                connection,
                "UPDATE content_edges SET transform='base64' WHERE id=:id",
                {"id": edge_id},
            )
    with pytest.raises(DBAPIError, match="immutable_edge_step"):
        with database.begin() as connection:
            execute(
                connection,
                "UPDATE content_edge_steps SET transform='base64' WHERE edge_id=:id",
                {"id": edge_id},
            )


def test_node_delete_cascades_to_steps_and_a_partial_delete_rolls_back(database: Engine) -> None:
    with database.begin() as connection:
        workspace, run_id, parent, child = _seed(connection)
        edge_id = _insert_edge(connection, workspace, run_id, parent, child, count=2)
        _insert_step(connection, edge_id, 1, "email-part-decode")
        _insert_step(connection, edge_id, 2, "json-canonical")
    with pytest.raises(DBAPIError, match="edge_steps_incomplete"):
        with database.begin() as connection:
            execute(
                connection,
                "DELETE FROM content_edge_steps WHERE edge_id=:id AND step_index=2",
                {"id": edge_id},
            )
    with database.connect() as connection:
        assert _step_count(connection, edge_id) == 2
    with database.begin() as connection:
        execute(connection, "DELETE FROM content_nodes WHERE id=:id", {"id": child})
        assert _step_count(connection, edge_id) == 0
        assert one(connection, "SELECT id FROM content_edges WHERE id=:id", {"id": edge_id}) is None


def test_runtime_budget_matches_the_database_bound(database: Engine) -> None:
    with database.connect() as connection:
        definitions = {
            row[0]: row[1]
            for row in connection.exec_driver_sql(
                """
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname IN ('content_edge_step_count', 'content_edge_step_index')
                """
            )
        }
    for name in ("content_edge_step_count", "content_edge_step_index"):
        numbers = [int(item) for item in re.findall(r"\d+", definitions[name])]
        assert max(numbers) == BUDGETS.transform_steps_per_edge
        assert 0 not in numbers


def _signature(engine: Engine) -> tuple[tuple[object, ...], ...]:
    with engine.connect() as connection:
        columns = connection.exec_driver_sql(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name IN ('content_edges', 'content_edge_steps')
            ORDER BY table_name, ordinal_position
            """
        ).all()
        constraints = connection.exec_driver_sql(
            """
            SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid IN ('content_edges'::regclass, 'content_edge_steps'::regclass)
            ORDER BY 1, 2
            """
        ).all()
        triggers = connection.exec_driver_sql(
            """
            SELECT tgrelid::regclass::text, tgname, pg_get_triggerdef(oid)
            FROM pg_trigger
            WHERE tgrelid IN ('content_edges'::regclass, 'content_edge_steps'::regclass)
              AND NOT tgisinternal
            ORDER BY 1, 2
            """
        ).all()
        functions = connection.exec_driver_sql(
            """
            SELECT proname, pg_get_functiondef(oid)
            FROM pg_proc
            WHERE proname IN (
              'protect_edge', 'protect_edge_step', 'enforce_recorded_edge_steps'
            )
            ORDER BY 1
            """
        ).all()
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    return (
        tuple(tuple(row) for row in columns),
        tuple(tuple(row) for row in constraints),
        tuple(tuple(row) for row in triggers),
        tuple(tuple(row) for row in functions),
        (version,),
    )


def test_fresh_test_and_development_schemas_match() -> None:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    development = next(
        (url for url in DEVELOPMENT_URLS if urlsplit(url).path.strip("/") == "vetoq"),
        None,
    )
    if development is None:
        pytest.fail("development database name is not the expected local name")
    fresh_url = urlunsplit(
        (urlsplit(DATABASE_URL).scheme, urlsplit(DATABASE_URL).netloc, f"/{FRESH_DATABASE}", "", "")
    )
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
        test = _engine(DATABASE_URL)
        live = _engine(development)
        try:
            require_disposable_engine(fresh)
            require_disposable_engine(test)
            signature = _signature(fresh)
            assert signature == _signature(test)
            assert signature == _signature(live)
            assert signature[-1] == ("0004_edge_steps",)
        finally:
            fresh.dispose()
            test.dispose()
            live.dispose()
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (FRESH_DATABASE,),
            )
            connection.execute(f"DROP DATABASE IF EXISTS {FRESH_DATABASE}")

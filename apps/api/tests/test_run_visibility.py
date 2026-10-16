"""M004 Slice D: one canonical read-visibility rule for run-scoped GET routes.

A run, its events, its content and its ticket are readable only with an active membership in
an active workspace. Every other case is the same non-enumerating 404. Fixtures are labeled
synthetic test data.
"""

import inspect
import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Engine
from test_database_integration import TicketProvider, get_as, provision, submission

from vetoq import routes, visibility
from vetoq.config import Settings
from vetoq.db import engine_for, execute, one
from vetoq.workflow import submit, tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, development_urls())
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    engine = engine_for(
        Settings(_env_file=None, environment="test", database_url=SecretStr(DATABASE_URL))
    )
    try:
        require_disposable_engine(engine)
    except UnsafeTestDatabase as error:
        engine.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    with engine.begin() as connection:
        execute(
            connection,
            """
            UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
            WHERE state IN ('QUEUED','PROPOSING','AUTHORIZING','VERIFYING','AWAITING_REVIEW')
            """,
        )
    yield engine
    engine.dispose()


@dataclass
class Fixture:
    owner: str
    workspace: UUID
    run_id: str
    node_id: str
    ticket_id: str

    def paths(self) -> list[str]:
        return [
            f"/api/v1/runs/{self.run_id}",
            f"/api/v1/runs/{self.run_id}/events",
            f"/api/v1/runs/{self.run_id}/content/{self.node_id}",
            f"/api/v1/tickets/{self.ticket_id}",
        ]


NOT_FOUND = (404, "not_found", "Request could not be completed.", False)


def refused(actor: str, path: str) -> tuple[int, object, object, object]:
    """The refusal without its per-request correlation id."""

    status, body = get_as(actor, path)
    return status, body.get("code"), body.get("message"), body.get("retryable")


def completed_run(database: Engine) -> Fixture:
    owner = "user_" + uuid4().hex
    workspace, _ = provision(database, owner)
    run_id = submit(database, owner, submission(workspace), "visible-" + uuid4().hex)
    for _ in range(12):
        if not tick(database, TicketProvider(workspace)):
            break
    with database.connect() as connection:
        node = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
        ticket = one(connection, "SELECT id FROM tickets WHERE run_id=:r", {"r": run_id})
    assert node is not None and ticket is not None
    return Fixture(owner, workspace, run_id, str(node["id"]), str(ticket["id"]))


def test_an_active_member_reads_the_run_events_content_and_ticket(database: Engine) -> None:
    fixture = completed_run(database)
    for path in fixture.paths():
        status, body = get_as(fixture.owner, path)
        assert status == 200, path
    status, run = get_as(fixture.owner, fixture.paths()[0])
    assert run["state"] == "COMPLETED"
    # A client-supplied workspace id is not a selector. The persisted run decides.
    other = uuid4()
    status, again = get_as(fixture.owner, f"{fixture.paths()[0]}?workspace_id={other}")
    assert status == 200 and again["workspace_id"] == run["workspace_id"] == str(fixture.workspace)


def test_a_principal_of_another_workspace_gets_the_same_404_everywhere(database: Engine) -> None:
    fixture = completed_run(database)
    outsider = "user_" + uuid4().hex
    provision(database, outsider)
    for path in fixture.paths():
        assert refused(outsider, path) == NOT_FOUND, path


def test_inactive_membership_loses_every_read(database: Engine) -> None:
    fixture = completed_run(database)
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE memberships SET active=false WHERE workspace_id=:w AND principal=:p",
            {"w": str(fixture.workspace), "p": fixture.owner},
        )
    for path in fixture.paths():
        assert refused(fixture.owner, path) == NOT_FOUND, path


def test_inactive_workspace_hides_the_run_and_everything_scoped_to_it(database: Engine) -> None:
    fixture = completed_run(database)
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE workspaces SET active=false WHERE id=:w",
            {"w": str(fixture.workspace)},
        )
    for path in fixture.paths():
        assert refused(fixture.owner, path) == NOT_FOUND, path
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE workspaces SET active=true WHERE id=:w",
            {"w": str(fixture.workspace)},
        )
    for path in fixture.paths():
        assert get_as(fixture.owner, path)[0] == 200, path


def test_missing_objects_are_indistinguishable_from_foreign_objects(database: Engine) -> None:
    fixture = completed_run(database)
    missing = [
        f"/api/v1/runs/{uuid4()}",
        f"/api/v1/runs/{uuid4()}/events",
        f"/api/v1/runs/{fixture.run_id}/content/{uuid4()}",
        f"/api/v1/tickets/{uuid4()}",
    ]
    for path in missing:
        assert refused(fixture.owner, path) == NOT_FOUND, path


def test_a_node_of_another_run_is_not_readable_through_this_run(database: Engine) -> None:
    first = completed_run(database)
    second = completed_run(database)
    status, _ = get_as(first.owner, f"/api/v1/runs/{first.run_id}/content/{second.node_id}")
    assert status == 404


def test_read_routes_use_the_one_canonical_helper_and_no_membership_only_join() -> None:
    assert "from vetoq.visibility import visible_run" in inspect.getsource(routes)
    for handler in (routes.get_run, routes.get_events, routes.get_content, routes.get_ticket):
        source = inspect.getsource(handler)
        assert "visible_run(" in source, handler.__name__
        assert "JOIN memberships" not in source, handler.__name__
    ticket = inspect.getsource(routes.get_ticket)
    assert "run_id" in ticket and "visible_run" in ticket
    helper = inspect.getsource(visibility.visible_run)
    assert "JOIN workspaces" in helper and "w.active" in helper and "m.active" in helper

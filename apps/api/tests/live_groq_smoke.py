"""Manual, real-provider smoke against disposable PostgreSQL and synthetic content."""

import json
import os
from uuid import uuid4

from disposable_database import (
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr

from vetoq.config import Settings
from vetoq.contracts import LegacySubmission
from vetoq.db import engine_for, execute, one
from vetoq.providers.groq import GroqProvider
from vetoq.workflow import submit, tick


def main() -> None:
    database_url = os.environ.get("VETOQ_TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError("VETOQ_TEST_DATABASE_URL is required")
    require_disposable_url(database_url, development_urls())
    provider_settings = Settings()
    database_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=SecretStr(database_url),
    )
    database = engine_for(database_settings)
    require_disposable_engine(database)
    workspace = uuid4()
    principal = "user_live_" + uuid4().hex
    with database.begin() as connection:
        execute(
            connection,
            "INSERT INTO workspaces(id,name) VALUES(:id,'Live Groq Smoke')",
            {"id": str(workspace)},
        )
        execute(
            connection,
            """
            INSERT INTO memberships(workspace_id,principal,role)
            VALUES(:workspace,:principal,'reviewer')
            """,
            {"workspace": str(workspace), "principal": principal},
        )
    run_id = submit(
        database,
        principal,
        LegacySubmission(
            workspace_id=workspace,
            template="support-triage/1",
            goal="Review this synthetic email and create one support ticket.",
            source=(
                "Synthetic customer cannot sign in after a password reset. "
                "Please create a support ticket."
            ),
            confirmed=True,
            sanitized=True,
        ),
        "live-groq-smoke-1",
    )
    provider = GroqProvider(provider_settings)
    for _ in range(8):
        if not tick(database, provider):
            break
        with database.connect() as connection:
            state = one(
                connection,
                "SELECT state FROM runs WHERE id=:run",
                {"run": run_id},
            )
        if state and state["state"] in {
            "COMPLETED",
            "NO_ACTION",
            "BLOCKED",
            "FAILED",
            "CANCELLED",
            "EXPIRED",
            "AWAITING_REVIEW",
        }:
            break
    with database.connect() as connection:
        evidence = one(
            connection,
            """
            SELECT r.state,r.writes,r.analysis,a.verdict,t.id AS ticket_id,
                   e.verified_at,(SELECT count(*) FROM tickets WHERE run_id=r.id) AS tickets
            FROM runs r
            LEFT JOIN actions a ON a.run_id=r.id
            LEFT JOIN tickets t ON t.run_id=r.id
            LEFT JOIN executions e ON e.run_id=r.id
            WHERE r.id=:run
            """,
            {"run": run_id},
        )
    database.dispose()
    if evidence is None:
        raise RuntimeError("live run disappeared")
    output = {
        "state": evidence["state"],
        "writes": evidence["writes"],
        "verdict": evidence["verdict"],
        "ticket_id_present": evidence["ticket_id"] is not None,
        "ticket_count": evidence["tickets"],
        "verified": evidence["verified_at"] is not None,
        "provider": evidence["analysis"].get("provider") if evidence["analysis"] else None,
        "model": evidence["analysis"].get("model") if evidence["analysis"] else None,
    }
    print(json.dumps(output, sort_keys=True))
    if output != {
        "state": "COMPLETED",
        "writes": 1,
        "verdict": "ALLOW",
        "ticket_id_present": True,
        "ticket_count": 1,
        "verified": True,
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }:
        raise RuntimeError("live Groq smoke did not complete the authorized ticket")


if __name__ == "__main__":
    main()

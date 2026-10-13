"""Explicit operator and runner commands; none are public HTTP endpoints."""

import argparse
import logging
import signal
from threading import Event

from vetoq.config import Settings
from vetoq.db import engine_for, execute
from vetoq.providers.groq import GroqProvider
from vetoq.workflow import run_worker

logger = logging.getLogger("vetoq.worker")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="vetoq")
    subcommands = result.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run-worker")
    run.add_argument("--once", action="store_true")
    provision = subcommands.add_parser("provision")
    provision.add_argument("--workspace-id", required=True)
    provision.add_argument("--workspace-name", required=True)
    provision.add_argument("--principal", required=True)
    provision.add_argument("--role", choices=("operator", "reviewer"), required=True)
    subcommands.add_parser("retain")
    return result


def main() -> None:
    arguments = parser().parse_args()
    settings = Settings()
    database = engine_for(settings)
    if arguments.command == "provision":
        with database.begin() as connection:
            execute(
                connection,
                """
                INSERT INTO workspaces(id,name) VALUES(:id,:name)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name
                """,
                {"id": arguments.workspace_id, "name": arguments.workspace_name},
            )
            execute(
                connection,
                """
                INSERT INTO memberships(workspace_id,principal,role)
                VALUES(:workspace,:principal,:role)
                ON CONFLICT(workspace_id,principal)
                DO UPDATE SET role=excluded.role,active=true
                """,
                {
                    "workspace": arguments.workspace_id,
                    "principal": arguments.principal,
                    "role": arguments.role,
                },
            )
        return
    if arguments.command == "retain":
        with database.begin() as connection:
            execute(connection, "DELETE FROM content_nodes WHERE expires_at<=now()")
            execute(
                connection,
                "DELETE FROM audit_events WHERE created_at<=now()-interval '30 days'",
            )
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    provider = GroqProvider(settings)
    stop = Event()

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    run_worker(database, provider, once=bool(arguments.once), stop=stop)


if __name__ == "__main__":
    main()

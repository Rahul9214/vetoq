import re

from vetoq.schema import DDL


def test_initial_migration_contains_only_the_eleven_approved_business_tables() -> None:
    tables = set(re.findall(r"CREATE TABLE ([a-z_]+)", DDL))
    assert tables == {
        "workspaces",
        "memberships",
        "runs",
        "content_nodes",
        "content_edges",
        "findings",
        "actions",
        "reviews",
        "executions",
        "audit_events",
        "tickets",
    }


def test_database_enforces_goal_action_content_and_audit_immutability() -> None:
    for trigger in (
        "immutable_run",
        "immutable_action",
        "immutable_content",
        "append_only_audit",
    ):
        assert f"CREATE TRIGGER {trigger}" in DDL

from unittest.mock import MagicMock

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    require_disposable_engine,
    require_disposable_url,
)

DEVELOPMENT = "postgresql://vetoq:fixture-only@127.0.0.1:55432/vetoq"


@pytest.mark.parametrize(
    "url",
    [
        DEVELOPMENT,
        "postgresql://vetoq:fixture-only@127.0.0.1:55432/",
        "postgresql://vetoq:fixture-only@127.0.0.1:55432/_test",
        "postgresql://vetoq:fixture-only@127.0.0.1:55432/vetoq_testing",
        "postgresql://vetoq:fixture-only@127.0.0.1:5432/postgres",
    ],
)
def test_non_test_database_names_are_refused(url: str) -> None:
    with pytest.raises(UnsafeTestDatabase) as error:
        require_disposable_url(url, [DEVELOPMENT])
    assert "fixture-only" not in str(error.value)


def test_configured_development_database_is_refused_even_with_a_test_name() -> None:
    development = "postgresql://vetoq:fixture-only@localhost:55432/vetoq_test"
    with pytest.raises(UnsafeTestDatabase, match="differ"):
        require_disposable_url(
            "postgresql://other:fixture-only@localhost:55432/vetoq_test", [development]
        )


def test_dedicated_test_database_is_accepted() -> None:
    require_disposable_url(
        "postgresql://vetoq:fixture-only@127.0.0.1:55432/vetoq_test", [DEVELOPMENT]
    )


@pytest.mark.parametrize(("connected", "safe"), [("vetoq_test", True), ("vetoq", False)])
def test_server_reported_database_name_is_checked(connected: str, safe: bool) -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = connected
    if safe:
        require_disposable_engine(engine)
    else:
        with pytest.raises(UnsafeTestDatabase):
            require_disposable_engine(engine)

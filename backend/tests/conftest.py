import sqlite3

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from main import app


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Make SQLite enforce the same foreign-key ordering expected by Postgres."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """Disable the rate limiter for every test by default.
    Tests that specifically exercise rate limiting re-enable it themselves."""
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = True

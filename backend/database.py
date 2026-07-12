"""Create the process-wide SQLAlchemy engine and request-scoped sessions.

Importing ``config`` establishes the environment precedence before the database
URL is read. SQLite enables cross-thread access because FastAPI's test/client
execution may use different threads; production Postgres receives no SQLite
options. ``get_db`` always closes its session, while callers retain explicit
commit/rollback ownership so data and audit rows can remain atomic.
"""

import os
from collections.abc import Generator

import config  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./school_ai.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

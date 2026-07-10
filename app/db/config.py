import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "shop_tracking.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH}"


def get_database_url() -> str:
    """Return the configured database URL, defaulting to local SQLite."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    if url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve()


def _ensure_sqlite_directory(database_url: str) -> None:
    database_path = _sqlite_database_path(database_url)
    if database_path is None:
        return
    database_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(
    database_url: str | None = None,
    *,
    echo: bool = False,
) -> Engine:
    """Create an engine that works with SQLite now and PostgreSQL later."""
    database_url = database_url or get_database_url()
    _ensure_sqlite_directory(database_url)
    engine = create_engine(database_url, echo=echo)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine

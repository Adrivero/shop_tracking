"""Create a consistent backup of the local SQLite database."""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.db.config import PROJECT_ROOT, get_database_url


def backup_database(
    destination: str | Path | None = None,
    *,
    database_url: str | None = None,
) -> Path:
    database_url = database_url or get_database_url()
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError("The built-in backup command only supports file-based SQLite")

    source = Path(url.database).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source}")

    if destination is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = PROJECT_ROOT / "backups" / f"shop_tracking-{timestamp}.db"
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, nargs="?")
    arguments = parser.parse_args()
    print(f"Backup written to: {backup_database(arguments.destination)}")


if __name__ == "__main__":
    main()

"""
Keeps the local development database (a SQLite file) in step with the models.

`Base.metadata.create_all` creates missing tables but never adds a column to a table that already exists. After a pull that adds
a column, an older `local-dev.db` then fails halfway through start-up and half the screens break. For a local SQLite file the
data is only demo data, so when the file is out of step it is set aside as a dated backup and a fresh one is built.
Other databases (PostgreSQL in production) are never touched here; they are changed by migrations.
"""
import datetime
import logging
import os
import sqlite3
import time
from typing import List, Optional

from sqlalchemy.engine import make_url

logger = logging.getLogger("urban-core")


def _sqlite_path(url: str) -> Optional[str]:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database or parsed.database == ":memory:":
        return None
    return os.path.abspath(parsed.database)


def missing_columns(path: str, metadata) -> List[str]:
    """`table.column` for every column the models have that the file's existing tables lack. Tables not yet in the file are not drift."""
    found: List[str] = []
    con = sqlite3.connect(path)
    try:
        for table in metadata.tables.values():
            have = {row[1] for row in con.execute(f'PRAGMA table_info("{table.name}")')}
            if have:
                found.extend(f"{table.name}.{c.name}" for c in table.columns if c.name not in have)
    finally:
        con.close()
    return found


def ensure_local_schema(url: str, metadata) -> Optional[str]:
    """
    Call before the engine is first used. Returns the backup file's path when an out-of-step database was set aside, else None.
    """
    path = _sqlite_path(url)
    if path is None or not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    try:
        missing = missing_columns(path, metadata)
    except sqlite3.DatabaseError as e:
        missing = [f"unreadable file ({e})"]
    if not missing:
        return None
    backup = f"{path}.old-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    # A copy of the API that was only just stopped can hold the file for a few seconds on Windows, so try for a while
    for attempt in range(15):
        try:
            os.replace(path, backup)
            break
        except OSError as e:
            if attempt == 14:
                logger.error("The local database %s is out of step with the code (%s) but could not be replaced (%s). "
                             "Stop any other running copy of the API and start again.", path, ", ".join(missing[:5]), e)
                raise
            time.sleep(1)
    logger.warning("The local database was out of step with the code (missing %s). It was kept as %s and a fresh one is being built.",
                   ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""), backup)
    return backup

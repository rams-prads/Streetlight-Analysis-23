"""One-time product rename SUVIDHA -> PUROJAS for rows already sitting in a database.

The code and seeds now say PUROJAS, but a database seeded before the rename still holds the old name
in plain text columns (SSO provider names, IdP labels, backup bucket paths, service URLs, ...). This
rewrites those values once at start-up. It is idempotent: once no row matches, every UPDATE touches
nothing. JSON columns are left to their owners (see security.py's notification_recipients).
"""
import logging

from sqlalchemy import String, Text, func, update

logger = logging.getLogger("urban-core")

_PAIRS = (("SUVIDHA", "PUROJAS"), ("Suvidha", "Purojas"), ("suvidha", "purojas"))


def _renamed(col):
    expr = col
    for old, new in _PAIRS:
        expr = func.replace(expr, old, new)
    return expr


def rename_legacy_brand(sync_conn, metadata) -> None:
    touched = 0
    for table in metadata.sorted_tables:
        for col in table.columns:
            if not isinstance(col.type, (String, Text)):
                continue
            stmt = update(table).where(func.lower(col).like("%suvidha%")).values({col.name: _renamed(col)})
            touched += sync_conn.execute(stmt).rowcount or 0
    if touched:
        logger.info("Renamed SUVIDHA -> PUROJAS in %d stored values.", touched)

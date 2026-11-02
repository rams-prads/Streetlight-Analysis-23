import os
import sqlite3

import sqlalchemy as sa

from app.db.dev_schema import ensure_local_schema, missing_columns


def _models():
    meta = sa.MetaData()
    sa.Table("things", meta, sa.Column("id", sa.String, primary_key=True), sa.Column("name", sa.String), sa.Column("added_later", sa.String))
    sa.Table("brand_new", meta, sa.Column("id", sa.String, primary_key=True))
    return meta


def _db(path, ddl):
    con = sqlite3.connect(path)
    con.execute(ddl)
    con.commit()
    con.close()


def test_file_in_step_is_left_alone(tmp_path):
    path = tmp_path / "dev.db"
    _db(path, "CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT, added_later TEXT)")   # a table the file lacks is not drift
    assert missing_columns(str(path), _models()) == []
    assert ensure_local_schema(f"sqlite+aiosqlite:///{path}", _models()) is None
    assert path.exists()


def test_file_missing_a_column_is_set_aside(tmp_path):
    path = tmp_path / "dev.db"
    _db(path, "CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT)")
    backup = ensure_local_schema(f"sqlite+aiosqlite:///{path}", _models())
    assert backup and os.path.exists(backup) and not path.exists()                       # create_all then builds a fresh file


def test_unreadable_file_is_set_aside(tmp_path):
    path = tmp_path / "dev.db"
    path.write_bytes(b"this is not a database" * 50)
    assert ensure_local_schema(f"sqlite+aiosqlite:///{path}", _models())


def test_other_databases_and_new_files_are_never_touched(tmp_path):
    assert ensure_local_schema("postgresql+asyncpg://u:p@localhost/db", _models()) is None
    assert ensure_local_schema(f"sqlite+aiosqlite:///{tmp_path / 'missing.db'}", _models()) is None
    assert ensure_local_schema("sqlite+aiosqlite:///:memory:", _models()) is None

"""A database created before a column existed must be upgraded in place, not crash the app."""

import sqlite3

import pytest
from sqlalchemy import inspect, text

import app.models  # noqa: F401
from app.db.session import Base, add_missing_columns, init_db, make_engine


@pytest.fixture()
def old_db(tmp_path):
    """A SQLite file shaped like the pre-verification schema: users has no is_verified column."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, "
        "password_hash VARCHAR(255) NOT NULL, display_name VARCHAR(80) NOT NULL, created_at DATETIME NOT NULL)"
    )
    conn.execute("INSERT INTO users VALUES (1, 'old@campus.edu', 'x', 'Old Timer', '2026-01-01 00:00:00')")
    conn.commit()
    conn.close()
    engine = make_engine(f"sqlite:///{path}")
    yield engine
    engine.dispose()


def test_missing_column_is_added_and_existing_rows_are_kept(old_db):
    assert "is_verified" not in {c["name"] for c in inspect(old_db).get_columns("users")}

    init_db(old_db)

    assert "is_verified" in {c["name"] for c in inspect(old_db).get_columns("users")}
    with old_db.connect() as conn:
        row = conn.execute(text("SELECT email, display_name, is_verified FROM users")).one()
    assert (row.email, row.display_name) == ("old@campus.edu", "Old Timer")  # nothing lost
    assert row.is_verified == 0  # existing accounts default to unverified


def test_new_tables_are_created_alongside(old_db):
    init_db(old_db)
    assert {"listings", "bids", "notifications", "email_verifications"} <= set(inspect(old_db).get_table_names())


def test_running_it_twice_changes_nothing(old_db):
    init_db(old_db)
    assert add_missing_columns(old_db) == []


def test_reports_what_it_added(old_db):
    Base.metadata.create_all(old_db)  # creates the other tables, leaves users as it is
    # the old table lacks every column added since: all of them are found and added in one pass
    assert set(add_missing_columns(old_db)) == {"users.is_verified", "users.department", "users.year_of_study", "users.password_changed_at"}


def test_fresh_database_needs_no_upgrade(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    init_db(engine)
    assert add_missing_columns(engine) == []
    engine.dispose()

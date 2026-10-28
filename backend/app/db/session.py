from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")  # fast commits while crash-safe in WAL
            cur.execute("PRAGMA busy_timeout=5000")  # wait up to 5s on concurrent writes instead of locking
            cur.execute("PRAGMA cache_size=-64000")  # 64MB RAM cache for hot pages and indexes
            cur.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def _sql_literal(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def add_missing_columns(bind: Engine) -> list[str]:
    """Add columns the models have but an existing table lacks. Returns what it added.

    `create_all` only creates missing *tables*, so a database made before a column existed
    would otherwise break with "no such column". This only ever adds columns (never drops or
    alters), so it cannot lose data. It is a stand-in for real migrations (Alembic), which a
    renamed or retyped column would still need.
    """
    added: list[str] = []
    inspector = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column.type.compile(bind.dialect)}'
                if not column.nullable:
                    # A NOT NULL column needs a value for the rows that already exist.
                    default = column.default
                    if default is None or not getattr(default, "is_scalar", False):
                        raise RuntimeError(
                            f"Cannot add NOT NULL column {table.name}.{column.name} without a simple default. "
                            "Delete the local database file and restart."
                        )
                    ddl += f" NOT NULL DEFAULT {_sql_literal(default.arg)}"
                conn.exec_driver_sql(ddl)
                added.append(f"{table.name}.{column.name}")
    return added


def init_db(bind: Engine | None = None) -> None:
    import app.models  # noqa: F401  (register tables on Base.metadata)

    bind = bind or engine
    Base.metadata.create_all(bind)
    add_missing_columns(bind)

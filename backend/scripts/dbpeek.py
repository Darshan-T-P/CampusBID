"""Look inside the CampusBid database (read-only; safe while the server is running).

    python scripts/dbpeek.py                 # every table: row count + the latest few rows
    python scripts/dbpeek.py users bids      # only those tables
    python scripts/dbpeek.py -n 20 listings  # show 20 rows instead of 5
    python scripts/dbpeek.py --db other.db   # a different database file
"""

import argparse
import sqlite3
import sys
from pathlib import Path

HIDDEN = {"password_hash", "code_hash"}  # never print secrets, even hashed ones


def fmt(value, width=28):
    text = "NULL" if value is None else str(value).replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def show(conn, table, limit):
    columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
    count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"\n== {table}  ({count} row{'s' if count != 1 else ''})")
    if count == 0:
        return
    shown = [c for c in columns if c not in HIDDEN]
    order = "id" if "id" in columns else "rowid"
    rows = conn.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in shown)} FROM "{table}" ORDER BY {order} DESC LIMIT ?', (limit,)).fetchall()
    widths = [max(len(c), *(len(fmt(r[i])) for r in rows)) for i, c in enumerate(shown)]
    print("  " + "  ".join(c.ljust(w) for c, w in zip(shown, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(fmt(v).ljust(w) for v, w in zip(row, widths)))
    if count > limit:
        print(f"  … {count - limit} older row(s) not shown (use -n)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tables", nargs="*", help="tables to show (default: all)")
    parser.add_argument("-n", type=int, default=5, help="rows per table (default 5)")
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "campusbid.db"))
    args = parser.parse_args()

    path = Path(args.db)
    if not path.exists():
        sys.exit(f"No database at {path}. Start the backend once to create it.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # read-only: cannot modify anything
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    wanted = args.tables or names
    unknown = [t for t in wanted if t not in names]
    if unknown:
        sys.exit(f"Unknown table(s): {', '.join(unknown)}. Tables: {', '.join(names)}")
    print(f"Database: {path}")
    for table in wanted:
        show(conn, table, args.n)


if __name__ == "__main__":
    main()

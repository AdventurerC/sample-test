"""Look up a novel by title in novels.db and run main.py against its URL.

Any extra arguments after the title are forwarded to main.py, e.g.:

  python fetch_novel.py 镇魂
  python fetch_novel.py 镇魂 --send
  python fetch_novel.py modu -o ./books --delay 2.0
  python fetch_novel.py 镇魂 --exact
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

DB_PATH = "novels.db"


def lookup(title: str, exact: bool, db_path: str) -> list[tuple[str, str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        if exact:
            sql = "SELECT title, author, genre, link FROM novels WHERE title = ?"
            params: tuple = (title,)
        else:
            sql = "SELECT title, author, genre, link FROM novels WHERE title LIKE ?"
            params = (f"%{title}%",)
        return list(conn.execute(sql, params))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find a novel by title in novels.db and invoke main.py on its URL.",
        epilog="Any additional arguments after the title are passed through to main.py.",
    )
    parser.add_argument("title", help="Title (or substring) to look up")
    parser.add_argument("--exact", action="store_true", help="Require exact title match")
    parser.add_argument("--db", default=DB_PATH, help="Path to the SQLite db")
    # Everything after a `--` is forwarded verbatim to main.py.
    args, passthrough = parser.parse_known_args()

    matches = lookup(args.title, args.exact, args.db)
    if not matches:
        print(f"No novel found matching title: {args.title!r}", file=sys.stderr)
        sys.exit(1)

    if len(matches) > 1:
        print(f"Multiple matches for {args.title!r}:", file=sys.stderr)
        for i, (t, a, g, l) in enumerate(matches, 1):
            print(f"  {i}. [{g}] {t} — {a or '(unknown)'} — {l}", file=sys.stderr)
        print("Refine the title or use --exact.", file=sys.stderr)
        sys.exit(1)

    title, author, genre, link = matches[0]
    print(f"Found: [{genre}] {title} — {author or '(unknown)'}")
    print(f"URL:   {link}")

    main_py = Path(__file__).parent / "main.py"
    cmd = [sys.executable, str(main_py), link, *passthrough]
    print(f"Running: {' '.join(cmd)}\n")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

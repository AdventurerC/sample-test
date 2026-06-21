"""Query the local novels.db by title, author, or genre (substring match).

The --title and --author flags search both the original text and pinyin romanization,
so you can use either Chinese text or pinyin interchangeably.

Usage:
  python query_novels.py --title 镇魂
  python query_novels.py --title "zhen hun"
  python query_novels.py --author priest
  python query_novels.py --author "mo xiang tong xiu"
  python query_novels.py --title modu --author priest
  python query_novels.py --genre baihe
  python query_novels.py --title 魂 --exact
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

DB_PATH = "novels.db"


def query(
    title: str | None = None,
    author: str | None = None,
    genre: str | None = None,
    exact: bool = False,
    db_path: str = DB_PATH,
) -> list[tuple[str, str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        clauses: list[str] = []
        params: list[str] = []

        if title:
            # Search both title and title_pinyin
            if exact:
                clauses.append("(title = ? OR title_pinyin = ?)")
                params.extend([title, title])
            else:
                clauses.append("(title LIKE ? OR title_pinyin LIKE ?)")
                params.extend([f"%{title}%", f"%{title}%"])

        if author:
            # Search both author and author_pinyin
            if exact:
                clauses.append("(author = ? OR author_pinyin = ?)")
                params.extend([author, author])
            else:
                clauses.append("(author LIKE ? OR author_pinyin LIKE ?)")
                params.extend([f"%{author}%", f"%{author}%"])

        if genre:
            clauses.append("genre LIKE ?")
            params.append(f"%{genre}%")

        sql = "SELECT title, author, genre, link FROM novels"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY genre, title"
        return list(conn.execute(sql, params))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local novels database.")
    parser.add_argument("--title", "-t", help="Match against the title (searches both Chinese and pinyin)")
    parser.add_argument("--author", "-a", help="Match against the author (searches both Chinese and pinyin)")
    parser.add_argument("--genre", "-g", help="Match against the genre")
    parser.add_argument(
        "--exact", action="store_true", help="Require an exact match (default: substring)"
    )
    parser.add_argument("--db", default=DB_PATH, help="Path to the SQLite db")
    args = parser.parse_args()

    if not any([args.title, args.author, args.genre]):
        parser.error("Provide at least one of --title, --author, --genre")

    rows = query(args.title, args.author, args.genre, args.exact, args.db)
    if not rows:
        print("No matches.")
        sys.exit(1)

    width_title = max(len(r[0]) for r in rows)
    width_author = max(len(r[1] or "") for r in rows)
    width_genre = max(len(r[2]) for r in rows)
    for title, author, genre, link in rows:
        print(
            f"{title:<{width_title}}  "
            f"{(author or ''):<{width_author}}  "
            f"{genre:<{width_genre}}  {link}"
        )
    print(f"\n{len(rows)} match(es).")


if __name__ == "__main__":
    main()

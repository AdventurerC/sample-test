"""Migrate novels.db to add title_pinyin and author_pinyin columns."""

from __future__ import annotations

import sqlite3
from pypinyin import lazy_pinyin, Style

DB_PATH = "novels.db"


def to_pinyin(text: str | None) -> str | None:
    """Convert Chinese text to pinyin (space-separated)."""
    if not text:
        return None
    pinyin_list = lazy_pinyin(text, style=Style.NORMAL, errors="ignore")
    return " ".join(pinyin_list).strip() or None


def migrate() -> None:
    """Add pinyin columns and populate them from existing titles and authors."""
    conn = sqlite3.connect(DB_PATH)
    
    # Add columns if they don't exist
    try:
        conn.execute("ALTER TABLE novels ADD COLUMN title_pinyin TEXT")
        print("Added title_pinyin column")
    except sqlite3.OperationalError:
        print("title_pinyin column already exists")
    
    try:
        conn.execute("ALTER TABLE novels ADD COLUMN author_pinyin TEXT")
        print("Added author_pinyin column")
    except sqlite3.OperationalError:
        print("author_pinyin column already exists")
    
    conn.commit()
    
    # Populate pinyin columns for rows that don't have them
    rows = conn.execute("SELECT rowid, title, author FROM novels WHERE title_pinyin IS NULL OR author_pinyin IS NULL").fetchall()
    print(f"Populating pinyin for {len(rows)} rows...")
    
    for rowid, title, author in rows:
        title_py = to_pinyin(title)
        author_py = to_pinyin(author)
        conn.execute(
            "UPDATE novels SET title_pinyin = ?, author_pinyin = ? WHERE rowid = ?",
            (title_py, author_py, rowid)
        )
    
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
    print(f"Migration complete! Database now has {total} rows with pinyin data.")
    conn.close()


if __name__ == "__main__":
    migrate()

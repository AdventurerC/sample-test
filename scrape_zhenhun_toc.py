"""Scrape zhenhunxiaoshuo.com chunai TOC pages into a local SQLite db."""

from __future__ import annotations

import sqlite3
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypinyin import lazy_pinyin, Style

BASE = "https://www.zhenhunxiaoshuo.com"
PAGES = [f"{BASE}/chunai/"] + [f"{BASE}/chunai{i}/" for i in range(2, 6)]
DB_PATH = "novels.db"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS novels (
            title  TEXT NOT NULL,
            author TEXT,
            title_pinyin TEXT,
            author_pinyin TEXT,
            genre  TEXT NOT NULL,
            link   TEXT NOT NULL,
            UNIQUE(title, link)
        )
        """
    )
    # Add new columns if they don't exist (migration)
    try:
        conn.execute("ALTER TABLE novels ADD COLUMN title_pinyin TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE novels ADD COLUMN author_pinyin TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def to_pinyin(text: str | None) -> str | None:
    """Convert Chinese text to pinyin (space-separated)."""
    if not text:
        return None
    pinyin_list = lazy_pinyin(text, style=Style.NORMAL, errors="ignore")
    return " ".join(pinyin_list).strip() or None


def scrape_page(url: str) -> list[tuple[str, str, str]]:
    """Return list of (title, author, link) from one TOC page."""
    resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    article = soup.select_one("article") or soup.select_one(".entry-content")
    if not article:
        return []

    rows: list[tuple[str, str, str]] = []
    for tr in article.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        a = tds[0].find("a")
        if not a or not a.get("href"):
            continue  # header row
        title = a.get_text(strip=True)
        link = urljoin(BASE, a["href"])
        author = tds[1].get_text(" ", strip=True)
        if title:
            rows.append((title, author, link))
    return rows


def main() -> None:
    conn = init_db(DB_PATH)
    total_inserted = 0
    for page in PAGES:
        print(f"Fetching {page}")
        try:
            rows = scrape_page(page)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            continue
        print(f"  found {len(rows)} entries")
        for title, author, link in rows:
            title_py = to_pinyin(title)
            author_py = to_pinyin(author)
            cur = conn.execute(
                "INSERT OR IGNORE INTO novels (title, author, title_pinyin, author_pinyin, genre, link) VALUES (?, ?, ?, ?, 'danmei', ?)",
                (title, author, title_py, author_py, link),
            )
            total_inserted += cur.rowcount
        conn.commit()
        time.sleep(1.0)

    print(f"\nInserted {total_inserted} new rows.")
    count = conn.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
    print(f"Total rows in 'novels' table: {count}")
    print("\nSample:")
    for row in conn.execute("SELECT title, author, genre, link FROM novels LIMIT 10"):
        print(" ", row)
    conn.close()


if __name__ == "__main__":
    main()

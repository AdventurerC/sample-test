"""Scrape zhenhunxiaoshuo.com baihe TOC into the local SQLite db.

Authors are fetched from each individual novel page (format: 作者：name).
"""

from __future__ import annotations

import re
import sqlite3
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypinyin import lazy_pinyin, Style

BASE = "https://www.zhenhunxiaoshuo.com"
TOC_URL = f"{BASE}/baihexiaoshuo/"
DB_PATH = "novels.db"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}
AUTHOR_RE = re.compile(r"作者[：:]\s*([^\s　<\n]+)")


def to_pinyin(text: str | None) -> str | None:
    """Convert Chinese text to pinyin (space-separated)."""
    if not text:
        return None
    pinyin_list = lazy_pinyin(text, style=Style.NORMAL, errors="ignore")
    return " ".join(pinyin_list).strip() or None


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


def scrape_toc(client: httpx.Client, url: str) -> list[tuple[str, str]]:
    """Return list of (title, link) from the TOC page."""
    resp = client.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    article = soup.select_one("article") or soup.select_one(".entry-content")
    if not article:
        return []

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in article.find_all("a"):
        href = a.get("href") or ""
        title = a.get_text(strip=True)
        if not href or not title:
            continue
        link = urljoin(BASE, href)
        # Skip non-novel links (external, anchors, the TOC itself, etc.)
        if not link.startswith(BASE):
            continue
        if link.rstrip("/") in {BASE, TOC_URL.rstrip("/")}:
            continue
        if link in seen:
            continue
        seen.add(link)
        out.append((title, link))
    return out


def fetch_author(client: httpx.Client, url: str) -> str:
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    fetch failed: {exc}")
        return ""
    soup = BeautifulSoup(resp.content, "lxml")
    text = soup.get_text("\n", strip=True)
    m = AUTHOR_RE.search(text)
    return m.group(1).strip() if m else ""


def main() -> None:
    conn = init_db(DB_PATH)
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        print(f"Fetching TOC: {TOC_URL}")
        entries = scrape_toc(client, TOC_URL)
        print(f"  found {len(entries)} novels")

        inserted = 0
        updated = 0
        for i, (title, link) in enumerate(entries, 1):
            existing = conn.execute(
                "SELECT author FROM novels WHERE title = ? AND link = ?",
                (title, link),
            ).fetchone()
            if existing and existing[0]:
                print(f"  [{i}/{len(entries)}] {title} -- already has author, skipping")
                continue

            author = fetch_author(client, link)
            print(f"  [{i}/{len(entries)}] {title} -- 作者: {author or '(unknown)'}")
            author_py = to_pinyin(author)
            if existing:
                if author:
                    conn.execute(
                        "UPDATE novels SET author = ?, author_pinyin = ? WHERE title = ? AND link = ?",
                        (author, author_py, title, link),
                    )
                    updated += 1
            else:
                title_py = to_pinyin(title)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO novels (title, author, title_pinyin, author_pinyin, genre, link) VALUES (?, ?, ?, ?, 'baihe', ?)",
                    (title, author, title_py, author_py, link),
                )
                inserted += cur.rowcount
            if (inserted + updated) % 10 == 0:
                conn.commit()
            time.sleep(0.6)
        conn.commit()

    print(f"\nInserted {inserted} new rows, updated {updated} existing rows.")
    total = conn.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
    baihe = conn.execute("SELECT COUNT(*) FROM novels WHERE genre='baihe'").fetchone()[0]
    print(f"Total rows: {total} (baihe: {baihe})")
    print("\nSample baihe entries:")
    for row in conn.execute(
        "SELECT title, author, genre, link FROM novels WHERE genre='baihe' LIMIT 10"
    ):
        print(" ", row)
    conn.close()


if __name__ == "__main__":
    main()

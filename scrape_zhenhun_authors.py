"""Scrape the author index (zhenhunxiaoshuo.com/作者/) and fill in any novels
that aren't already in novels.db. Genre is left blank for new entries.
"""

from __future__ import annotations

import sqlite3
import time
from urllib.parse import urljoin, unquote

import httpx
from bs4 import BeautifulSoup
from pypinyin import lazy_pinyin, Style

BASE = "https://www.zhenhunxiaoshuo.com"
INDEX_URL = f"{BASE}/%e4%bd%9c%e8%80%85/"  # /作者/
DB_PATH = "novels.db"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# Skip author-index navigation links and similar non-author entries.
SKIP_ANCHOR_TEXT = {"【快速查询", "】", ""}


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


def fetch_soup(client: httpx.Client, url: str) -> BeautifulSoup | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    fetch failed: {exc}")
        return None
    return BeautifulSoup(resp.content, "lxml")


def scrape_author_index(client: httpx.Client) -> list[tuple[str, str]]:
    """Return list of (author_name, author_page_url)."""
    soup = fetch_soup(client, INDEX_URL)
    if not soup:
        return []
    article = soup.select_one("article") or soup.select_one(".entry-content")
    if not article:
        return []

    authors: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in article.find_all("a"):
        href = a.get("href") or ""
        name = a.get_text(strip=True)
        if not href or name in SKIP_ANCHOR_TEXT:
            continue
        link = urljoin(BASE, href)
        # Author pages live one level under the domain root.
        if not link.startswith(BASE):
            continue
        if link.endswith(".html"):
            continue  # e.g. /chaxun.html
        if link in seen:
            continue
        seen.add(link)
        authors.append((name, link))
    return authors


def scrape_author_page(
    client: httpx.Client, author_url: str
) -> list[tuple[str, str]]:
    """Return list of (title, novel_url) found on an author's page."""
    soup = fetch_soup(client, author_url)
    if not soup:
        return []
    article = soup.select_one("article") or soup.select_one(".entry-content")
    if not article:
        return []

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tr in article.find_all("tr"):
        a = tr.find("a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        link = urljoin(BASE, a["href"])
        # Skip the bare site root and the author-index navigation links.
        if link.rstrip("/") == BASE.rstrip("/"):
            # special-case: 镇魂 lives at "/" — keep it as a valid novel link.
            pass
        if link in seen:
            continue
        seen.add(link)
        out.append((title, link))
    return out


def main() -> None:
    conn = init_db(DB_PATH)

    # Pre-load existing (title, link) and existing links for fast lookup.
    existing_pairs = {
        (t, l) for t, l in conn.execute("SELECT title, link FROM novels")
    }
    existing_links = {l for _, l in existing_pairs}
    print(f"DB starts with {len(existing_pairs)} rows.")

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        print(f"Fetching author index: {INDEX_URL}")
        authors = scrape_author_index(client)
        print(f"  found {len(authors)} authors")

        inserted = 0
        for i, (author, author_url) in enumerate(authors, 1):
            display_author = unquote(author)
            entries = scrape_author_page(client, author_url)
            new_for_author = 0
            for title, link in entries:
                if (title, link) in existing_pairs or link in existing_links:
                    continue
                title_py = to_pinyin(title)
                author_py = to_pinyin(display_author)
                conn.execute(
                    "INSERT OR IGNORE INTO novels (title, author, title_pinyin, author_pinyin, genre, link) "
                    "VALUES (?, ?, ?, ?, '', ?)",
                    (title, display_author, title_py, author_py, link),
                )
                existing_pairs.add((title, link))
                existing_links.add(link)
                inserted += 1
                new_for_author += 1
            print(
                f"  [{i}/{len(authors)}] {display_author}: "
                f"{len(entries)} listed, {new_for_author} new"
            )
            if i % 10 == 0:
                conn.commit()
            time.sleep(0.5)
        conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
    blank_genre = conn.execute(
        "SELECT COUNT(*) FROM novels WHERE genre = ''"
    ).fetchone()[0]
    print(f"\nInserted {inserted} new rows.")
    print(f"DB now has {total} rows total ({blank_genre} with blank genre).")

    hit = conn.execute(
        "SELECT title, author, genre, link FROM novels WHERE link LIKE '%hongbai%'"
    ).fetchall()
    if hit:
        print("\nhongbai* matches:")
        for r in hit:
            print(" ", r)
    conn.close()


if __name__ == "__main__":
    main()

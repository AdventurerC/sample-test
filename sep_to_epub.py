"""Fetch a Stanford Encyclopedia of Philosophy article and build an EPUB."""

from __future__ import annotations

import sys
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from epub_builder import build_epub
from scrapers.base import Chapter, NovelMetadata


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def fetch_sep(url: str) -> NovelMetadata:
    resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Title
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else "SEP Article"

    # Author(s) – SEP puts them in #article-copyright or a "Copyright" block;
    # the author line itself sits in #pubinfo or a div with class "credits".
    author = "Stanford Encyclopedia of Philosophy"
    pubinfo = soup.select_one("#pubinfo")
    if pubinfo:
        # First line usually: "First published Mon Aug 2, 2021; ..."
        # Author appears in a preceding <p> with id "author" or similar; fall back.
        pass
    # The author is typically inside a <div id="article-copyright"> or near top.
    copyright_div = soup.select_one("#article-copyright")
    if copyright_div:
        # e.g. "Copyright © 2024 by\nJonathan Schaffer <schaffer@philosophy.rutgers.edu>"
        text = copyright_div.get_text(" ", strip=True)
        if "by" in text:
            after = text.split("by", 1)[1].strip()
            # strip trailing email/angle brackets
            author = after.split("<")[0].strip().rstrip(".").strip()

    # Main content
    preamble = soup.select_one("#preamble")
    main = soup.select_one("#main-text") or soup.select_one("#aueditable") or soup.body

    # Rewrite relative links/images to absolute
    for root in (preamble, main):
        if not root:
            continue
        for tag, attr in (("a", "href"), ("img", "src")):
            for el in root.find_all(tag):
                if el.has_attr(attr):
                    el[attr] = urljoin(url, el[attr])

    # Split into chapters by top-level <h2> sections.
    chapters: list[Chapter] = []
    # Build a flat list of children, grouping by h2.
    current_title = "Introduction"
    current_buf: list[str] = []
    idx = 0

    def flush():
        nonlocal idx, current_buf, current_title
        html = "".join(current_buf).strip()
        if html:
            idx += 1
            chapters.append(Chapter(title=current_title, content_html=html, index=idx))
        current_buf = []

    if preamble:
        for child in preamble.children:
            if getattr(child, "name", None) is None:
                t = str(child).strip()
                if t:
                    current_buf.append(str(child))
            else:
                current_buf.append(str(child))
        flush()
        current_title = "Untitled"

    for child in main.children:
        name = getattr(child, "name", None)
        if name in ("h2", "h3"):
            flush()
            current_title = child.get_text(" ", strip=True)
            continue
        if name is None:
            # NavigableString
            text = str(child).strip()
            if text:
                current_buf.append(str(child))
            continue
        # Skip the article's own title h1 if present in main
        if name == "h1":
            continue
        current_buf.append(str(child))
    flush()

    if not chapters:
        chapters = [Chapter(title=title, content_html=str(main), index=1)]

    return NovelMetadata(
        title=title,
        author=author,
        description=f"Stanford Encyclopedia of Philosophy article: {title}",
        cover_url=None,
        language="en",
        chapters=chapters,
    )


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://plato.stanford.edu/entries/causation-metaphysics/"
    print(f"Fetching {url}")
    meta = fetch_sep(url)
    print(f"Title: {meta.title}")
    print(f"Author: {meta.author}")
    print(f"Sections: {len(meta.chapters)}")
    build_epub(meta, output_dir=".")


if __name__ == "__main__":
    main()

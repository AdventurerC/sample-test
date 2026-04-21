"""Build an EPUB file from scraped novel data."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from ebooklib import epub

from scrapers.base import NovelMetadata


def build_epub(meta: NovelMetadata, output_dir: str = ".") -> Path:
    """Create an EPUB file and return its path."""
    book = epub.EpubBook()

    # -- metadata ------------------------------------------------------------
    book.set_identifier(f"webnovel-{_slug(meta.title)}")
    book.set_title(meta.title)
    book.set_language(meta.language)
    book.add_author(meta.author)

    # -- optional cover image ------------------------------------------------
    if meta.cover_url:
        try:
            resp = httpx.get(meta.cover_url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            ext = _guess_ext(resp.headers.get("content-type", ""), meta.cover_url)
            cover_name = f"cover.{ext}"
            book.set_cover(cover_name, resp.content)
        except Exception as exc:
            print(f"  Warning: could not download cover image: {exc}")

    # -- CSS -----------------------------------------------------------------
    css = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=_DEFAULT_CSS.encode("utf-8"),
    )
    book.add_item(css)

    # -- chapters ------------------------------------------------------------
    epub_chapters: list[epub.EpubHtml] = []
    for ch in meta.chapters:
        ec = epub.EpubHtml(
            title=ch.title,
            file_name=f"ch{ch.index:04d}.xhtml",
            lang=meta.language,
        )
        ec.content = (
            f"<html><head><link rel='stylesheet' href='style/default.css'/></head>"
            f"<body><h1>{ch.title}</h1>{ch.content_html}</body></html>"
        )
        ec.add_item(css)
        book.add_item(ec)
        epub_chapters.append(ec)

    # -- table of contents & spine -------------------------------------------
    book.toc = epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters

    # -- write ---------------------------------------------------------------
    out_path = Path(output_dir) / f"{_slug(meta.title)}.epub"
    epub.write_epub(str(out_path), book, {})
    print(f"EPUB saved to: {out_path}")
    return out_path


# -- helpers -----------------------------------------------------------------

def _slug(text: str) -> str:
    """Create a filesystem-safe slug from a title."""
    # Keep CJK characters, alphanumeric, replace the rest with underscores
    import re
    slug = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+", "_", text)
    return slug.strip("_")[:80]


def _guess_ext(content_type: str, url: str) -> str:
    if "png" in content_type or url.endswith(".png"):
        return "png"
    if "gif" in content_type or url.endswith(".gif"):
        return "gif"
    if "webp" in content_type or url.endswith(".webp"):
        return "webp"
    return "jpg"


_DEFAULT_CSS = """
body {
    font-family: serif;
    margin: 1em;
    line-height: 1.8;
}
h1 {
    font-size: 1.4em;
    margin-bottom: 0.8em;
    text-align: center;
}
p {
    text-indent: 2em;
    margin: 0.4em 0;
}
"""

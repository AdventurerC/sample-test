"""Scraper for gongzicp.com (长佩文学)."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from .base import BaseScraper, NovelMetadata


class GongzicpScraper(BaseScraper):
    """
    gongzicp.com is a Chinese BL / romance webnovel platform.

    Novel page:   https://www.gongzicp.com/novel-<id>.html
    Chapter page: https://www.gongzicp.com/read-<id>.html

    Supports authenticated sessions via cookies for accessing purchased
    chapters.  Pass cookies via config.yaml (see config.example.yaml).
    """

    BASE = "https://www.gongzicp.com"

    def fetch_metadata(self, novel_url: str) -> NovelMetadata:
        soup = self.get_soup(novel_url)

        title_tag = soup.select_one("h3, h1, .novel-title, .book-title")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author = "Unknown"
        # Author line like "邀君月下 著"
        author_tag = soup.select_one('a[href*="/zone/author-"]')
        if author_tag:
            author = author_tag.get_text(strip=True)

        desc_tag = soup.select_one(
            ".novel-desc, .book-desc, .novel-info, .book-summary"
        )
        description = desc_tag.get_text(strip=True)[:500] if desc_tag else ""

        cover_tag = soup.select_one(
            'meta[property="og:image"], img[src*="resourcecp-cdn"]'
        )
        cover_url = None
        if cover_tag:
            cover_url = cover_tag.get("content") or cover_tag.get("src")

        return NovelMetadata(
            title=title,
            author=author,
            description=description,
            cover_url=cover_url,
            language="zh",
        )

    def fetch_chapter_list(self, novel_url: str) -> list[tuple[str, str]]:
        soup = self.get_soup(novel_url)
        chapters: list[tuple[str, str]] = []
        seen: set[str] = set()

        # Chapter links are: <a href="/read-8006134.html">这封信给他</a>
        for a in soup.select('a[href*="/read-"]'):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text:
                continue
            full_url = urljoin(self.BASE, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            chapters.append((text, full_url))

        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self.get_soup(chapter_url)

        # Free chapter content is typically in a content div.
        for selector in [
            ".novel-content",
            ".chapter-content",
            ".read-content",
            ".article-content",
            "#novelContent",
            "article",
        ]:
            body = soup.select_one(selector)
            if body:
                for tag in body.select("script, style, .ad, .comment"):
                    tag.decompose()
                return str(body)

        # Check if this is a login-walled chapter
        if soup.select_one(".login-tip, .pay-tip, .vip-tip"):
            print("    ⚠ Paywalled chapter — skipping (check your cookies in config.yaml)")
            return "<p>[This chapter requires purchase on gongzicp.com. Update your cookies in config.yaml.]</p>"

        # Fallback
        paragraphs = soup.find_all("p")
        if paragraphs:
            return "".join(str(p) for p in paragraphs)

        return "<p>(Could not extract chapter content.)</p>"

"""Scraper for zhenhunxiaoshuo.com (镇魂小说网)."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper, NovelMetadata


class ZhenhunScraper(BaseScraper):
    """
    zhenhunxiaoshuo.com hosts free-to-read Chinese web novels.

    Novel index page:  https://www.zhenhunxiaoshuo.com/<slug>/
    Chapter page:      https://www.zhenhunxiaoshuo.com/<id>.html
    """

    BASE = "https://www.zhenhunxiaoshuo.com"

    def fetch_metadata(self, novel_url: str) -> NovelMetadata:
        soup = self.get_soup(novel_url)

        # The <h1> on the novel index page is typically the title
        title_tag = soup.select_one("h1, .entry-title, .novel-title")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        # Author is often in the description paragraph
        author = "Unknown"
        desc_tag = soup.select_one(".entry-content, .novel-desc, article")
        description = ""
        if desc_tag:
            description = desc_tag.get_text(strip=True)[:500]
            # Try to pull author from description text like "作者：priest"
            m = re.search(r"作者[：:]\s*(\S+)", description)
            if m:
                author = m.group(1)

        cover_tag = soup.select_one('meta[property="og:image"]')
        cover_url = cover_tag["content"] if cover_tag else None

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
        seen_urls: set[str] = set()

        # Chapter links look like: <a href="https://www.zhenhunxiaoshuo.com/976.html">第1章 序章</a>
        # They live inside the main content area.  Filter to links whose href
        # ends with a numeric .html path (the chapter ID).
        for a in soup.select("a[href]"):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text:
                continue
            full_url = urljoin(novel_url, href)
            # Only keep links that point to chapter pages on the same domain
            if self.BASE not in full_url:
                continue
            if not re.search(r"/\d+\.html$", full_url):
                continue
            if full_url in seen_urls:
                continue
            # Skip the 简介 (summary) page which also ends in .html
            if "简介" in text:
                continue
            seen_urls.add(full_url)
            chapters.append((text, full_url))

        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self.get_soup(chapter_url)

        # The chapter text is in the main content area.
        # Try several common selectors.
        for selector in [
            ".entry-content",
            ".article-content",
            "article",
            ".post-content",
            ".content",
        ]:
            body = soup.select_one(selector)
            if body:
                # Remove navigation links, share widgets, comment sections
                for tag in body.select(
                    "nav, .navigation, .social-share, .comments-area, "
                    ".post-navigation, script, style, .sharedaddy"
                ):
                    tag.decompose()
                return str(body)

        # Fallback: just grab all <p> tags in the page
        paragraphs = soup.find_all("p")
        return "".join(str(p) for p in paragraphs)

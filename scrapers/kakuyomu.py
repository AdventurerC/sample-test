"""Scraper for kakuyomu.jp — Japanese web novel site by Kadokawa."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from .base import BaseScraper, Chapter, NovelMetadata


class KakuyomuScraper(BaseScraper):
    """
    Kakuyomu renders its table-of-contents server-side, but chapter text is
    loaded via an embedded JSON blob (Apollo / Next.js data).  We parse both
    from the raw HTML so no browser automation is needed.
    """

    BASE = "https://kakuyomu.jp"

    # -- interface -----------------------------------------------------------

    def fetch_metadata(self, novel_url: str) -> NovelMetadata:
        soup = self.get_soup(novel_url)

        title_tag = soup.select_one("#workTitle a, .NewBox_headerTitle__text")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author_tag = soup.select_one("#workAuthor-activityName a, .partialGift__author")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        desc_tag = soup.select_one("#introduction, .NewBox_synopsis")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        cover_tag = soup.select_one('meta[property="og:image"]')
        cover_url = cover_tag["content"] if cover_tag else None

        return NovelMetadata(
            title=title,
            author=author,
            description=description,
            cover_url=cover_url,
            language="ja",
        )

    def fetch_chapter_list(self, novel_url: str) -> list[tuple[str, str]]:
        soup = self.get_soup(novel_url)
        chapters: list[tuple[str, str]] = []

        # Kakuyomu TOC: <a class="WorkTocSection_link__..." href="/works/.../episodes/...">
        for link in soup.select('a[href*="/episodes/"]'):
            href = link.get("href", "")
            if "/episodes/" not in href:
                continue
            ch_title = link.get_text(strip=True)
            ch_url = urljoin(self.BASE, href)
            if ch_title and (ch_title, ch_url) not in chapters:
                chapters.append((ch_title, ch_url))

        if not chapters:
            # Fallback: try extracting from __NEXT_DATA__ JSON
            chapters = self._chapters_from_next_data(soup, novel_url)

        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self.get_soup(chapter_url)

        # Episode body is inside <div class="widget-episodeBody js-episode-body">
        body = soup.select_one(".widget-episodeBody, .js-episode-body")
        if body:
            return str(body)

        # Fallback: look for honbun (本文) in __NEXT_DATA__
        script = soup.select_one("script#__NEXT_DATA__")
        if script:
            try:
                data = json.loads(script.string)
                text = self._dig(data, "body") or self._dig(data, "honbun") or ""
                if text:
                    paragraphs = text.split("\n")
                    return "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
            except (json.JSONDecodeError, TypeError):
                pass

        # Last resort: grab all <p> inside <main>
        main = soup.select_one("main")
        if main:
            return "".join(str(p) for p in main.find_all("p"))

        return "<p>(Could not extract chapter content.)</p>"

    # -- internal helpers ----------------------------------------------------

    def _chapters_from_next_data(
        self, soup, novel_url: str
    ) -> list[tuple[str, str]]:
        script = soup.select_one("script#__NEXT_DATA__")
        if not script:
            return []
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            return []

        episodes = self._dig(data, "episodes") or self._dig(data, "tableOfContents")
        if not isinstance(episodes, list):
            return []

        chapters = []
        work_id = novel_url.rstrip("/").split("/")[-1]
        for ep in episodes:
            ep_id = ep.get("id") or ep.get("episodeId")
            title = ep.get("title", f"Episode {ep_id}")
            url = f"{self.BASE}/works/{work_id}/episodes/{ep_id}"
            chapters.append((title, url))
        return chapters

    @staticmethod
    def _dig(data, key):
        """Recursively find the first value matching *key* in nested dicts."""
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for v in data.values():
                result = KakuyomuScraper._dig(v, key)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = KakuyomuScraper._dig(item, key)
                if result is not None:
                    return result
        return None

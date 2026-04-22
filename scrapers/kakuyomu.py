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

        title_tag = soup.select_one(
            "#workTitle a, .NewBox_headerTitle__text, h1"
        )
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author_tag = soup.select_one(
            '#workAuthor-activityName a, .partialGift__author, a[href^="/users/"]'
        )
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

        # Prefer the Apollo/Next.js data because the rendered TOC collapses
        # long works into accordions, so only a handful of <a> links exist
        # in the initial HTML.
        chapters = self._chapters_from_apollo(soup, novel_url)
        if chapters:
            return chapters

        # Fallback: DOM scrape (small works with fully-expanded TOC).
        seen_urls: set[str] = set()
        shortcut_labels = {"1話目から読む", "最新話から読む"}
        dom_chapters: list[tuple[str, str]] = []
        for link in soup.select('a[href*="/episodes/"]'):
            href = link.get("href", "")
            if "/episodes/" not in href:
                continue
            ch_title = link.get_text(strip=True)
            ch_url = urljoin(self.BASE, href)
            if not ch_title or ch_url in seen_urls:
                continue
            if ch_title in shortcut_labels:
                continue
            seen_urls.add(ch_url)
            dom_chapters.append((ch_title, ch_url))
        return dom_chapters

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

    def _chapters_from_apollo(
        self, soup, novel_url: str
    ) -> list[tuple[str, str]]:
        """Extract the full chapter list from the Apollo cache in __NEXT_DATA__.

        The rendered TOC uses accordions, so many works only render a
        handful of episode <a> tags. The Apollo state, however, always
        contains every public episode via
        ``Work.tableOfContentsV2 -> TableOfContentsChapter.episodeUnions``.
        """
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.string:
            return []
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            return []

        apollo = (
            data.get("props", {})
            .get("pageProps", {})
            .get("__APOLLO_STATE__")
        )
        if not isinstance(apollo, dict):
            return []

        work_id = novel_url.rstrip("/").split("/")[-1]
        work = apollo.get(f"Work:{work_id}")
        if not isinstance(work, dict):
            return []

        toc = work.get("tableOfContentsV2") or work.get("tableOfContents")
        if not isinstance(toc, list):
            return []

        chapters: list[tuple[str, str]] = []
        for toc_ref in toc:
            toc_key = toc_ref.get("__ref") if isinstance(toc_ref, dict) else None
            if not toc_key:
                continue
            toc_entry = apollo.get(toc_key)
            if not isinstance(toc_entry, dict):
                continue
            for ep_ref in toc_entry.get("episodeUnions", []) or []:
                ep_key = ep_ref.get("__ref") if isinstance(ep_ref, dict) else None
                if not ep_key:
                    continue
                ep = apollo.get(ep_key)
                if not isinstance(ep, dict):
                    continue
                ep_id = ep.get("id")
                title = ep.get("title") or f"Episode {ep_id}"
                if not ep_id:
                    continue
                url = f"{self.BASE}/works/{work_id}/episodes/{ep_id}"
                chapters.append((title, url))
        return chapters

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

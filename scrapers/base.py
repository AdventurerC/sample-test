"""Base scraper interface and shared data models."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup


@dataclass
class Chapter:
    title: str
    content_html: str  # cleaned HTML body of the chapter
    index: int = 0


@dataclass
class NovelMetadata:
    title: str
    author: str = "Unknown"
    description: str = ""
    cover_url: str | None = None
    language: str = "zh"
    chapters: list[Chapter] = field(default_factory=list)


class BaseScraper(ABC):
    """All site scrapers inherit from this."""

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            cookies=cookies,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )

    # -- public API ----------------------------------------------------------

    def scrape(self, novel_url: str, delay: float = 1.5) -> NovelMetadata:
        """Scrape an entire novel. Returns metadata with chapters populated."""
        meta = self.fetch_metadata(novel_url)
        chapter_urls = self.fetch_chapter_list(novel_url)
        print(f"Found {len(chapter_urls)} chapters for '{meta.title}'")

        for i, (ch_title, ch_url) in enumerate(chapter_urls, start=1):
            print(f"  [{i}/{len(chapter_urls)}] {ch_title}")
            html = self.fetch_chapter_content(ch_url)
            meta.chapters.append(Chapter(title=ch_title, content_html=html, index=i))
            if i < len(chapter_urls):
                time.sleep(delay)

        return meta

    # -- subclasses must implement -------------------------------------------

    @abstractmethod
    def fetch_metadata(self, novel_url: str) -> NovelMetadata:
        """Return title, author, description, cover URL, etc."""

    @abstractmethod
    def fetch_chapter_list(self, novel_url: str) -> list[tuple[str, str]]:
        """Return ordered list of (chapter_title, chapter_url)."""

    @abstractmethod
    def fetch_chapter_content(self, chapter_url: str) -> str:
        """Return cleaned HTML content for a single chapter."""

    # -- helpers available to subclasses -------------------------------------

    def get_soup(self, url: str) -> BeautifulSoup:
        resp = self.client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def close(self) -> None:
        self.client.close()

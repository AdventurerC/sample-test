"""Scraper for gongzicp.com.

Strategy
--------
Gongzicp is a Vue SPA that fetches chapter content through a JSON API
(``/webapi/novel/chapterGetInfo``). The ``content`` field is AES-128-CBC
encrypted with a key/IV hard-coded in the site's JS bundle. The JS only
decrypts and renders content if various client-side checks pass (login
state, anti-bot, etc.), so scraping the rendered DOM is fragile. We call
the API directly and decrypt ourselves.

The table-of-contents page is still loaded with Playwright since the
chapter listing is JS-rendered.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from .base import BaseScraper, NovelMetadata


# Extracted from the site's JS bundle (ReadPc.*.js -> `new be("iGzsYn","dTBMUnJidSRFbg==")`).
_AES_KEY = b"u0LRrbu$Enm84koA"
_AES_IV = b"$h$b3!iGzsYnnshj"


def _decrypt_content(b64_ciphertext: str) -> str:
    ct = base64.b64decode(b64_ciphertext)
    decryptor = Cipher(algorithms.AES(_AES_KEY), modes.CBC(_AES_IV)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


class GongzicpScraper(BaseScraper):
    """Scrapes gongzicp.com (Vue SPA + encrypted chapter API)."""

    BASE = "https://www.gongzicp.com"

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    def __init__(self, cookies=None):
        from playwright.sync_api import sync_playwright

        self._cookies = {k: str(v) for k, v in (cookies or {}).items() if k != "raw"}
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self._UA,
            viewport={"width": 1280, "height": 900},
        )
        if self._cookies:
            self._context.add_cookies([
                {"name": n, "value": v, "domain": ".gongzicp.com", "path": "/"}
                for n, v in self._cookies.items()
            ])
        self._page = self._context.new_page()

        self._api = httpx.Client(
            timeout=30,
            follow_redirects=True,
            cookies=self._cookies,
            headers={
                "User-Agent": self._UA,
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.BASE + "/",
            },
        )

    def get_soup(self, url):
        self._page.goto(url, wait_until="networkidle", timeout=45_000)
        try:
            self._page.wait_for_selector(
                "a[href*='/read-'], .cp-reader .content", timeout=15_000
            )
        except Exception:
            pass
        self._page.wait_for_timeout(1000)
        return BeautifulSoup(self._page.content(), "lxml")

    def close(self):
        try:
            self._api.close()
        except Exception:
            pass
        try:
            self._context.close()
        finally:
            try:
                self._browser.close()
            finally:
                self._pw.stop()

    def fetch_metadata(self, novel_url):
        soup = self.get_soup(novel_url)

        title_tag = soup.select_one("h3")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author = "Unknown"
        page_title = soup.title.get_text(strip=True) if soup.title else ""
        if "_" in page_title:
            parts = page_title.split("_")
            if len(parts) >= 2 and parts[1].endswith("著"):
                author = parts[1][:-1]

        desc_tag = soup.select_one(".cp-novel-intro, .intro, .novel-desc")
        description = desc_tag.get_text(strip=True)[:500] if desc_tag else ""

        cover_tag = soup.select_one('meta[property="og:image"]') or soup.select_one(
            'img[src*="resourcecp-cdn"]'
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

    def fetch_chapter_list(self, novel_url):
        soup = self.get_soup(novel_url)
        chapters = []
        seen = set()

        for a in soup.select('a[href*="/read-"]'):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not text or not href:
                continue
            full_url = urljoin(self.BASE, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            chapters.append((text, full_url))

        return chapters

    _CID_RE = re.compile(r"/read-(\d+)")

    def _fetch_chapter_info(self, cid: str, chapter_url: str) -> dict | None:
        """Call the chapter API once. Returns chapterInfo dict or None on error."""
        api_url = f"{self.BASE}/webapi/novel/chapterGetInfo?cid={cid}&server=0"
        try:
            resp = self._api.get(api_url, headers={"Referer": chapter_url})
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"    [!] API fetch failed for cid={cid}: {e}")
            return None

        if payload.get("code") != 200:
            msg = payload.get("msg", "unknown error")
            print(f"    [!] API error for cid={cid}: {msg}")
            return None

        return (payload.get("data") or {}).get("chapterInfo") or {}

    def fetch_chapter_content(self, chapter_url):
        import time

        m = self._CID_RE.search(chapter_url)
        if not m:
            return "<p>[Could not parse chapter id from URL.]</p>"
        cid = m.group(1)

        # Retry on empty content — the server occasionally returns an empty
        # `content` field under load / soft rate limiting, even for free
        # chapters. A short backoff clears it.
        info = None
        enc = None
        for attempt in range(4):
            info = self._fetch_chapter_info(cid, chapter_url)
            if info is None:
                time.sleep(2 * (attempt + 1))
                continue

            if info.get("lock") == 1 or (
                info.get("chapter_ispay") == 1 and info.get("isSub") != 1
            ):
                print(
                    f"    [!] Paywalled chapter cid={cid} "
                    f"(not purchased on this account)"
                )
                return (
                    "<p>[Paywalled chapter. Verify your gongzicp cookies "
                    "belong to an account that has purchased it.]</p>"
                )

            enc = info.get("content")
            if enc:
                break
            print(f"    [!] Empty content for cid={cid}, retrying ({attempt + 1}/4)...")
            time.sleep(2 * (attempt + 1))

        if not enc:
            return "<p>[Empty chapter content after retries.]</p>"

        try:
            plaintext = _decrypt_content(enc)
        except Exception as e:
            print(f"    [!] Decryption failed for cid={cid}: {e}")
            return "<p>[Decryption failed.]</p>"

        paragraphs = []
        for line in plaintext.splitlines():
            line = line.strip()
            if not line:
                continue
            line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            paragraphs.append(f"<p>{line}</p>")

        if not paragraphs:
            return "<p>[Empty chapter content.]</p>"

        return "\n".join(paragraphs)

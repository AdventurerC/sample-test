from scrapers.base import BaseScraper, Chapter, NovelMetadata
from scrapers.kakuyomu import KakuyomuScraper
from scrapers.zhenhun import ZhenhunScraper
from scrapers.gongzicp import GongzicpScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "kakuyomu.jp": KakuyomuScraper,
    "www.zhenhunxiaoshuo.com": ZhenhunScraper,
    "zhenhunxiaoshuo.com": ZhenhunScraper,
    "gongzicp.com": GongzicpScraper,
    "www.gongzicp.com": GongzicpScraper,
}


def get_scraper(url: str, cookies: dict[str, str] | None = None) -> BaseScraper:
    """Return the appropriate scraper instance for a given novel URL."""
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    scraper_cls = SCRAPERS.get(host)
    if scraper_cls is None:
        supported = ", ".join(SCRAPERS.keys())
        raise ValueError(f"No scraper for host '{host}'. Supported: {supported}")
    return scraper_cls(cookies=cookies)

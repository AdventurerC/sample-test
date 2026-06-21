#!/usr/bin/env python3
"""
webnovel-to-kindle
~~~~~~~~~~~~~~~~~~
Scrape a Chinese/Japanese webnovel, package it as EPUB, and optionally
email it to your Kindle.

Usage
-----
  # Scrape + build EPUB (does NOT send to Kindle by default)
  python main.py "https://www.zhenhunxiaoshuo.com/modu/"

  # Send to Kindle (requires SMTP config in config.yaml)
  python main.py "https://www.zhenhunxiaoshuo.com/modu/" --send

  # Explicit opt-out (same as default)
  python main.py "https://www.zhenhunxiaoshuo.com/modu/" --no-send

  # Send an already-built EPUB without scraping
  python main.py --send-only ./my-book.epub

  # Custom output directory
  python main.py "https://www.zhenhunxiaoshuo.com/modu/" -o ./books

  # Override delay between chapter requests
  python main.py "https://www.zhenhunxiaoshuo.com/modu/" --delay 2.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from epub_builder import build_epub
from kindle_sender import send_to_kindle
from scrapers import get_scraper


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_cookies(url: str, config: dict) -> dict[str, str] | None:
    """Extract cookies for the given URL's host from the config."""
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    all_cookies = config.get("cookies", {})

    # Try exact match first, then without "www."
    site_cookies = all_cookies.get(host) or all_cookies.get(host.removeprefix("www."))
    if not site_cookies:
        return None

    # Support "raw" cookie header string: "key1=val1; key2=val2"
    if isinstance(site_cookies, dict) and "raw" in site_cookies:
        raw = site_cookies["raw"]
        parsed = {}
        for pair in raw.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                parsed[k.strip()] = v.strip()
        return parsed

    if isinstance(site_cookies, dict):
        return {k: str(v) for k, v in site_cookies.items()}

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape a webnovel, build an EPUB, and optionally send to Kindle."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="URL of the novel's table-of-contents page (omit when using --send-only)",
    )
    parser.add_argument(
        "-o", "--output", default=".", help="Directory to save the EPUB (default: .)"
    )
    parser.add_argument(
        "--send-only",
        metavar="EPUB_PATH",
        help="Skip scraping and send an existing EPUB file to Kindle",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Seconds to wait between chapter requests (default: from config or 1.5)",
    )
    send_group = parser.add_mutually_exclusive_group()
    send_group.add_argument(
        "--send",
        dest="send",
        action="store_true",
        default=False,
        help="Send the EPUB to Kindle after building (default: do not send)",
    )
    send_group.add_argument(
        "--no-send",
        dest="send",
        action="store_false",
        help="Do not send the EPUB to Kindle (this is the default)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.send_only:
        epub_path = Path(args.send_only)
        if not epub_path.exists():
            print(f"EPUB not found: {epub_path}", file=sys.stderr)
            sys.exit(1)
        if args.send is False:
            print("--send-only conflicts with --no-send.", file=sys.stderr)
            sys.exit(1)
        # Force send semantics for --send-only.
        args.send = True
    else:
        if not args.url:
            parser.error("url is required unless --send-only is used")

        delay = args.delay or config.get("scraping", {}).get("delay", 1.5)

        # --- resolve cookies for this site ----------------------------------
        cookies = _resolve_cookies(args.url, config)

        # --- scrape ---------------------------------------------------------
        scraper = get_scraper(args.url, cookies=cookies)
        try:
            novel = scraper.scrape(args.url, delay=delay)
        finally:
            scraper.close()

        if not novel.chapters:
            print("No chapters found. Check the URL or the scraper selectors.", file=sys.stderr)
            sys.exit(1)

        # --- build EPUB -----------------------------------------------------
        epub_path = build_epub(novel, output_dir=args.output)

    # --- send to Kindle -----------------------------------------------------
    if not args.send:
        print("Done. (Kindle send skipped; pass --send to email the EPUB.)")
        return

    smtp = config.get("smtp", {})
    kindle_email = config.get("kindle_email")
    sender_email = config.get("sender_email")

    missing = []
    if not smtp.get("host"):
        missing.append("smtp.host")
    if not smtp.get("password"):
        missing.append("smtp.password")
    if not kindle_email:
        missing.append("kindle_email")
    if not sender_email:
        missing.append("sender_email")

    if missing:
        print(
            f"Cannot send: missing config keys: {', '.join(missing)}\n"
            f"Copy config.example.yaml → config.yaml and fill in your values.",
            file=sys.stderr,
        )
        sys.exit(1)

    emails = [e.strip() for e in str(kindle_email).split(",") if e.strip()]
    for email in emails:
        send_to_kindle(
            epub_path,
            kindle_email=email,
            sender_email=sender_email,
            smtp_host=smtp["host"],
            smtp_port=smtp.get("port", 587),
            smtp_user=smtp.get("username", sender_email),
            smtp_password=smtp["password"],
        )

    print("Done.")


if __name__ == "__main__":
    main()

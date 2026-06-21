# webnovel-to-kindle

Scrape a Chinese/Japanese webnovel into an EPUB and optionally email it to your Kindle.

> ⚠️ **This is entirely vibecoded.** It was hacked together through trial and error as a test of Opus 4.7 capabilities.

## Supported sites

| Site | URL pattern | Notes |
|------|-------------|-------|
| Kakuyomu | `https://kakuyomu.jp/works/<id>` | Works out of the box. |
| 镇魂小说网 | `https://www.zhenhunxiaoshuo.com/<slug>/` | Works out of the box. |
| 长佩文学网 (gongzicp) | `https://www.gongzicp.com/novel-<id>.html` | ⚠️ See warning below. |

### ⚠️ Gongzicp warning

Gongzicp support is **unstable and fragile**:

- **You must provide your own cookies from a logged-in account that has purchased the chapters you're downloading.** This tool does *not* bypass paywalls — it just uses your existing access. Free chapters work without purchase, paid chapters require that your account owns them.
- Chapter content is AES-encrypted on the API and decrypted client-side. The key/IV are hard-coded in the site's JS bundle and are extracted by hand into [scrapers/gongzicp.py](scrapers/gongzicp.py). **If gongzicp rotates the key, the scraper will silently produce gibberish until the key is re-extracted.**
- The API occasionally returns empty `content` fields under load. The scraper retries up to 4 times with backoff, but rate-limiting can still cause failures.
- Cookies expire. If you start seeing `[Paywalled chapter...]` warnings after things used to work, log back in and re-copy them.

The other two scrapers are much more stable because they don't fight encryption or SPAs.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium        # only needed for gongzicp
```

Copy the example config:
```powershell
Copy-Item config.example.yaml config.yaml
```
Then edit `config.yaml` with your SMTP credentials, Kindle email, and any site cookies.

### Getting gongzicp cookies

1. Log in to gongzicp.com in your browser.
2. Open DevTools → Application → Cookies → `https://www.gongzicp.com`.
3. Copy these cookie values into `config.yaml` under `cookies.gongzicp.com`:
   - `_c_n_`
   - `_c_n_n_`
   - `_c_WBKFRo` (the actual login token)
   - `PHPSESSID`

## Usage

```powershell
# Scrape + build EPUB (does NOT send to Kindle by default)
python main.py "https://kakuyomu.jp/works/16818023214131449614"

# Send to Kindle (requires SMTP config)
python main.py "<url>" --send

# Send a pre-built EPUB
python main.py --send-only ./my-book.epub

# Custom output dir + custom delay between chapters
python main.py "<url>" -o ./books --delay 2.0
```

## Local novel database (zhenhunxiaoshuo only)

A SQLite database (`novels.db`) of titles, authors, genres, and links scraped
from zhenhunxiaoshuo.com. Schema: `(title, author, genre, link)`.

### Populating the db

```powershell
# danmei TOC pages (chunai/, chunai2/ … chunai5/) — sets genre='danmei'
python scrape_zhenhun_toc.py

# baihe TOC (visits each novel page to extract 作者：xxx) — sets genre='baihe'
python scrape_zhenhun_baihe.py

# Author index (/作者/) — fills in everything else, genre left blank
python scrape_zhenhun_authors.py
```

All three scripts are idempotent — re-running only inserts new rows.

### Querying the db

```powershell
# Search by title / author / genre (substring by default; combinable)
python query_novels.py --title 镇魂
python query_novels.py --title "zhen hun"        # same book, searched by pinyin
python query_novels.py --author priest
python query_novels.py --author "mo xiang tong xiu"
python query_novels.py --genre baihe
python query_novels.py --title 魂 --exact
```

All searches on `--title` and `--author` automatically search both the original text and pinyin romanization.

### Fetch a novel by title

`fetch_novel.py` looks up a title in the db and runs `main.py` against its URL.
Any extra args are forwarded verbatim to `main.py`:

```powershell
python fetch_novel.py 镇魂
python fetch_novel.py 红白囍 --send
python fetch_novel.py modu -o ./books --delay 2.0
```

If the title matches multiple rows, the script lists them and exits — refine
the title or pass `--exact`.

## Building an EPUB from a Stanford Encyclopedia of Philosophy article

```powershell
python sep_to_epub.py https://plato.stanford.edu/entries/causation-metaphysics/
```

## Project layout

```
main.py                      # CLI entry point (scrape → EPUB → optional Kindle)
epub_builder.py              # EPUB packaging (ebooklib)
kindle_sender.py             # SMTP send to Kindle
sep_to_epub.py               # One-off: Stanford Encyclopedia of Philosophy → EPUB
scrapers/
  base.py                    # BaseScraper interface + NovelMetadata / Chapter
  kakuyomu.py                # kakuyomu.jp (Next.js Apollo cache)
  zhenhun.py                 # zhenhunxiaoshuo.com (plain HTML)
  gongzicp.py                # gongzicp.com (Playwright + AES-decrypt API)
scrape_zhenhun_toc.py        # Populate novels.db from chunai TOC pages
scrape_zhenhun_baihe.py      # Populate novels.db from baihe TOC
scrape_zhenhun_authors.py    # Populate novels.db from author index
query_novels.py              # Search novels.db by title/author (both Chinese and pinyin)
migrate_db.py                # One-time migration: adds pinyin columns to existing novels.db
fetch_novel.py               # Look up title in novels.db → call main.py
novels.db                    # SQLite db (title, author, title_pinyin, author_pinyin, genre, link)
config.example.yaml          # template config
requirements.txt
```

## Security notes

- **`config.yaml` contains your SMTP password and site cookies.** It's gitignored by default — keep it that way. If you ever paste cookies or an SMTP app password into a chat or commit, rotate them.
- For Gmail, use an [App Password](https://myaccount.google.com/apppasswords), never your real password.
- Add your SMTP sender address to Amazon's "Approved Personal Document E-mail List" or the send will silently drop on Amazon's side.

## Why does gongzicp "break" when the other two don't?

- Kakuyomu ships its chapter list in a Next.js JSON blob — easy to parse.
- Zhenhunxiaoshuo serves plain server-rendered HTML — easier still.
- Gongzicp is a Vue SPA whose chapter text is (a) loaded via XHR and (b) AES-encrypted, with (c) anti-bot checks that prevent a headless browser from triggering the decryption itself. We therefore call the API directly and decrypt in Python using keys scraped out of the JS bundle. Any of those three layers can change without notice.

## License

Do what you want. For personal/archival use only — respect the authors and don't redistribute scraped content.

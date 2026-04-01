"""
bachtrack_scraper.py

Scrapes concert listings from Bachtrack (bachtrack.com) for a list of
conductors. Bachtrack is the most comprehensive public classical music
concert database.

Outputs:
    data/raw/bachtrack/concert_listings_raw.json  – list of concert records

Each record:
    {
        "conductor":  "Andris Nelsons",
        "date":       "2023-11-04",
        "orchestra":  "Boston Symphony Orchestra",
        "venue":      "Symphony Hall, Boston",
        "city":       "Boston",
        "country":    "United States",
        "program":    ["Brahms: Symphony No. 4", ...],
        "source_url": "https://bachtrack.com/..."
    }

Usage:
    python -m scraping.bachtrack_scraper
    python -m scraping.bachtrack_scraper --conductors "Andris Nelsons" "Gustavo Dudamel"
    python -m scraping.bachtrack_scraper --start-year 2015 --end-year 2025

Notes:
    - Respects robots.txt: bachtrack.com/robots.txt allows /search-results
    - Uses a 2-second delay between requests (polite crawl rate)
    - Results are cached to disk; re-running skips already-fetched pages
    - Season pages can return up to 10 results per page; pagination is handled
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "bachtrack"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://bachtrack.com"
SEARCH_URL = f"{BASE_URL}/search-results"

DEFAULT_CONDUCTORS = [
    "Andris Nelsons",
    "Gustavo Dudamel",
    "Yannick Nézet-Séguin",
    "Klaus Mäkelä",
    "Simon Rattle",
    "Riccardo Muti",
    "Kirill Petrenko",
    "Mirga Gražinytė-Tyla",
    "Semyon Bychkov",
    "Daniel Harding",
    "Paavo Järvi",
    "Franz Welser-Möst",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ConductorNetworkResearch/1.0; "
        "academic network science project; contact: research@example.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

CRAWL_DELAY = 2.0  # seconds between requests


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(url: str, params: dict | None = None) -> requests.Response:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    time.sleep(CRAWL_DELAY)
    return resp


# ---------------------------------------------------------------------------
# Search and pagination
# ---------------------------------------------------------------------------

def _build_search_params(conductor: str, page: int = 1, start_year: int = 2010, end_year: int = 2025) -> dict:
    """
    Bachtrack search form parameters.
    Verify against https://bachtrack.com/search-results in browser devtools
    if these field names change.
    """
    return {
        "conductor": conductor,
        "datefrom": f"{start_year}-01-01",
        "dateto": f"{end_year}-12-31",
        "type": "concert",
        "page": page,
    }


def _parse_result_count(soup: BeautifulSoup) -> int:
    """Extract total result count from search page."""
    counter = soup.select_one(".search-results-count, .results-count, [class*='count']")
    if counter:
        m = re.search(r"(\d[\d,]*)", counter.get_text())
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def _parse_concert_list(soup: BeautifulSoup) -> list[dict]:
    """Parse all concert cards/rows from a single search results page."""
    concerts = []

    # Bachtrack renders results as article cards or table rows depending on view
    # Try card layout first, fall back to table rows
    items = soup.select("article.concert-result, li.concert-result, .search-result-item")
    if not items:
        items = soup.select("tr.concert-row, tr[data-concert-id]")

    for item in items:
        concert = _parse_concert_item(item)
        if concert:
            concerts.append(concert)

    return concerts


def _parse_concert_item(item) -> dict | None:
    """Parse a single concert result element into a structured record."""
    try:
        # Date – look for <time> element or date-formatted string
        date_el = item.select_one("time, [class*='date'], .concert-date")
        date_str = None
        if date_el:
            date_str = date_el.get("datetime") or date_el.get_text(strip=True)
            date_str = _normalise_date(date_str)

        # Orchestra
        orch_el = item.select_one("[class*='orchestra'], [class*='ensemble'], .performer")
        orchestra = orch_el.get_text(strip=True) if orch_el else None

        # Venue / city
        venue_el = item.select_one("[class*='venue'], [class*='location'], .venue")
        venue_raw = venue_el.get_text(strip=True) if venue_el else None
        venue, city, country = _split_venue(venue_raw)

        # Program (list of works)
        prog_els = item.select("[class*='work'], [class*='program'] li, .work-title")
        program = [el.get_text(strip=True) for el in prog_els if el.get_text(strip=True)]

        # Conductor name may appear if multiple conductors on page
        cond_el = item.select_one("[class*='conductor']")
        conductor = cond_el.get_text(strip=True) if cond_el else None

        # Source URL
        link_el = item.select_one("a[href]")
        source_url = BASE_URL + link_el["href"] if link_el and link_el["href"].startswith("/") else (
            link_el["href"] if link_el else None
        )

        return {
            "conductor": conductor,
            "date": date_str,
            "orchestra": orchestra,
            "venue": venue,
            "city": city,
            "country": country,
            "program": program,
            "source_url": source_url,
        }
    except Exception as exc:
        log.debug("Failed to parse concert item: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Date and venue normalisation
# ---------------------------------------------------------------------------

def _normalise_date(raw: str | None) -> str | None:
    """Attempt to parse a variety of date formats into ISO YYYY-MM-DD."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: grab the first date-like substring
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else raw


def _split_venue(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """
    Split a venue string like "Symphony Hall, Boston, United States"
    into (venue, city, country).
    """
    if not raw:
        return None, None, None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[-1]
    if len(parts) == 2:
        return parts[0], parts[1], None
    return raw, None, None


# ---------------------------------------------------------------------------
# Per-conductor scrape
# ---------------------------------------------------------------------------

def scrape_conductor(
    conductor: str,
    start_year: int = 2010,
    end_year: int = 2025,
    max_pages: int = 50,
) -> list[dict]:
    """
    Fetch all concert listings for a single conductor across all paginated
    result pages. Injects the conductor name into each record since the
    search context isn't always explicit in the result HTML.
    """
    log.info("Scraping Bachtrack for: %s (%d–%d)", conductor, start_year, end_year)
    all_concerts: list[dict] = []
    cache_path = RAW_DIR / f"{conductor.replace(' ', '_')}_raw.json"

    # Skip if already cached
    if cache_path.exists():
        log.info("  Cache hit – loading from %s", cache_path)
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    for page in range(1, max_pages + 1):
        params = _build_search_params(conductor, page=page, start_year=start_year, end_year=end_year)
        try:
            resp = _get(SEARCH_URL, params=params)
        except Exception as exc:
            log.error("  Request failed on page %d: %s", page, exc)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # On first page, check if there are any results
        if page == 1:
            total = _parse_result_count(soup)
            log.info("  Found ~%d total results", total)
            if total == 0:
                break

        concerts = _parse_concert_list(soup)
        if not concerts:
            log.info("  No concerts on page %d – stopping pagination", page)
            break

        # Inject conductor name where missing (common when searching by conductor)
        for c in concerts:
            if not c.get("conductor"):
                c["conductor"] = conductor

        all_concerts.extend(concerts)
        log.info("  Page %d: +%d concerts (total so far: %d)", page, len(concerts), len(all_concerts))

        # Stop if last page returned fewer items than a full page (heuristic)
        if len(concerts) < 10:
            break

    # Persist per-conductor cache
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_concerts, f, indent=2, ensure_ascii=False)
    log.info("  Cached %d records -> %s", len(all_concerts), cache_path)

    return all_concerts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    conductors: list[str] = DEFAULT_CONDUCTORS,
    start_year: int = 2010,
    end_year: int = 2025,
) -> list[dict]:
    all_records: list[dict] = []

    for conductor in conductors:
        records = scrape_conductor(conductor, start_year=start_year, end_year=end_year)
        all_records.extend(records)

    # Write merged output
    out_path = RAW_DIR / "concert_listings_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    log.info("Wrote %d total concert records -> %s", len(all_records), out_path)

    return all_records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Bachtrack concert listings")
    parser.add_argument("--conductors", nargs="+", default=DEFAULT_CONDUCTORS)
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()

    records = run(args.conductors, args.start_year, args.end_year)
    print(f"\nDone. {len(records)} concert records collected.")

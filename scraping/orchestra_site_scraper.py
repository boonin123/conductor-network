"""
orchestra_site_scraper.py

Scrapes season programme archives from individual orchestra websites.
These are authoritative sources for home-turf appearances and allow
verification of Bachtrack data.

Supported orchestras and their scraping strategies are defined in
ORCHESTRA_CONFIGS below. Each config specifies:
  - base_url: the orchestra's website root
  - seasons_url: the archive/calendar page
  - parser: a function name in this module that handles that site's HTML
  - seasons: list of season years to attempt (e.g. 2018 = 2018-19 season)

Outputs:
    data/raw/orchestra_websites/<slug>_seasons_raw.json

Each record:
    {
        "orchestra":  "Boston Symphony Orchestra",
        "conductor":  "Andris Nelsons",
        "role":       "Music Director",   # or "Guest Conductor"
        "date":       "2023-11-04",
        "venue":      "Symphony Hall",
        "city":       "Boston",
        "program":    ["Brahms: Symphony No. 4", ...],
        "season":     2023,
        "source_url": "https://..."
    }

Usage:
    python -m scraping.orchestra_site_scraper
    python -m scraping.orchestra_site_scraper --orchestras bso laphil
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "orchestra_websites"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CRAWL_DELAY = 2.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ConductorNetworkResearch/1.0; "
        "academic network science project)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Seasons to scrape: 2013-14 through 2024-25
DEFAULT_SEASONS = list(range(2013, 2025))


# ---------------------------------------------------------------------------
# Orchestra configurations
# ---------------------------------------------------------------------------

ORCHESTRA_CONFIGS: dict[str, dict] = {
    "bso": {
        "name": "Boston Symphony Orchestra",
        "slug": "bso",
        "city": "Boston",
        "country": "United States",
        # BSO archives season programmes at URLs like:
        # https://www.bso.org/events/season-archive/season/[YEAR]-[YEAR+1]
        "seasons_url_template": "https://www.bso.org/events/season-archive/season/{year}-{year1}",
        "parser": "parse_bso",
    },
    "laphil": {
        "name": "Los Angeles Philharmonic",
        "slug": "laphil",
        "city": "Los Angeles",
        "country": "United States",
        # LA Phil uses a JSON API for their calendar
        "seasons_url_template": "https://www.laphil.com/api/concerts?season={year}-{year1}&page=1&per_page=200",
        "parser": "parse_laphil",
    },
    "philadelphia": {
        "name": "Philadelphia Orchestra",
        "slug": "philadelphia",
        "city": "Philadelphia",
        "country": "United States",
        "seasons_url_template": "https://www.philorch.org/performance/?season={year}-{year1}",
        "parser": "parse_philorch",
    },
    "berlin": {
        "name": "Berliner Philharmoniker",
        "slug": "berlin",
        "city": "Berlin",
        "country": "Germany",
        # Berlin Phil has a Digital Concert Hall and public calendar
        "seasons_url_template": "https://www.berliner-philharmoniker.de/en/concerts/calendar/?year={year}",
        "parser": "parse_berlin",
    },
    "gewandhaus": {
        "name": "Gewandhausorchester Leipzig",
        "slug": "gewandhaus",
        "city": "Leipzig",
        "country": "Germany",
        "seasons_url_template": "https://www.gewandhausorchester.de/en/spielplan/?season={year}",
        "parser": "parse_gewandhaus",
    },
    "chicago": {
        "name": "Chicago Symphony Orchestra",
        "slug": "chicago",
        "city": "Chicago",
        "country": "United States",
        "seasons_url_template": "https://cso.org/performances/season-archive/?season={year}-{year1}",
        "parser": "parse_chicago",
    },
    "nyphil": {
        "name": "New York Philharmonic",
        "slug": "nyphil",
        "city": "New York",
        "country": "United States",
        "seasons_url_template": "https://nyphil.org/concerts-tickets/explore/season-archive?season={year}-{year1}",
        "parser": "parse_nyphil",
    },
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(url: str, params: dict | None = None, as_json: bool = False):
    resp = requests.get(url, params=params, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    time.sleep(CRAWL_DELAY)
    return resp.json() if as_json else BeautifulSoup(resp.text, "lxml")


# ---------------------------------------------------------------------------
# Shared parsing utilities
# ---------------------------------------------------------------------------

def _extract_conductor_role(text: str) -> tuple[str | None, str]:
    """
    Given a conductor credit string like "Andris Nelsons, Music Director"
    return (name, role). Role defaults to "Guest Conductor".
    """
    parts = [p.strip() for p in text.split(",", 1)]
    name = parts[0] if parts else None
    role = parts[1] if len(parts) > 1 else "Guest Conductor"
    return name, role


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else raw


def _season_from_date(date_str: str | None) -> int | None:
    """Return season start year: a concert in Nov 2023 belongs to season 2023."""
    if not date_str:
        return None
    try:
        month = int(date_str[5:7])
        year = int(date_str[:4])
        return year if month >= 9 else year - 1
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Orchestra-specific parsers
# ---------------------------------------------------------------------------

def parse_bso(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """
    BSO season archive page parser.
    The BSO lists events as <article> cards with conductor, date, program info.
    """
    records = []
    for card in soup.select("article.event-card, .concert-listing, li.event"):
        try:
            date_el = card.select_one("time, .event-date, [class*='date']")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = card.select_one("[class*='conductor'], .artist-name")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = card.select(".work, [class*='program'] li, .repertoire-item")
            program = [el.get_text(strip=True) for el in prog_els]

            venue_el = card.select_one("[class*='venue'], .location")
            venue = venue_el.get_text(strip=True) if venue_el else "Symphony Hall"

            link_el = card.select_one("a[href]")
            source_url = link_el["href"] if link_el else None
            if source_url and source_url.startswith("/"):
                source_url = "https://www.bso.org" + source_url

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": venue,
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("BSO parse error: %s", exc)

    return records


def parse_laphil(data: dict | list, season: int, config: dict) -> list[dict]:
    """
    LA Phil JSON API response parser.
    The API returns a list of concert objects with structured fields.
    """
    records = []
    items = data if isinstance(data, list) else data.get("concerts", data.get("data", []))

    for item in items:
        try:
            date_str = _parse_date(item.get("date") or item.get("start_date"))
            conductor = item.get("conductor") or item.get("primary_conductor")
            role = "Music Director" if item.get("is_music_director") else "Guest Conductor"
            program = [w.get("title", "") for w in item.get("works", [])]
            venue = item.get("venue", {}).get("name") or "Walt Disney Concert Hall"
            source_url = item.get("url") or item.get("permalink")

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": venue,
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("LA Phil parse error: %s", exc)

    return records


def parse_philorch(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """Philadelphia Orchestra season page parser."""
    records = []
    for card in soup.select(".performance-card, article.event, .concert-item"):
        try:
            date_el = card.select_one("time, .date")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = card.select_one("[class*='conductor'], .artist")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = card.select(".work-title, .program-item")
            program = [el.get_text(strip=True) for el in prog_els]

            link_el = card.select_one("a[href]")
            source_url = link_el["href"] if link_el else None

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": "Verizon Hall",
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("Philadelphia parse error: %s", exc)

    return records


def parse_berlin(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """Berliner Philharmoniker calendar page parser."""
    records = []
    for event in soup.select(".concert-item, .event-entry, article[class*='concert']"):
        try:
            date_el = event.select_one("time, .date-display")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = event.select_one(".conductor-name, [itemprop='performer']")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = event.select(".work-item, .program-line")
            program = [el.get_text(strip=True) for el in prog_els]

            link_el = event.select_one("a[href]")
            source_url = link_el["href"] if link_el else None
            if source_url and source_url.startswith("/"):
                source_url = "https://www.berliner-philharmoniker.de" + source_url

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": "Philharmonie Berlin",
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("Berlin parse error: %s", exc)

    return records


def parse_gewandhaus(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """Gewandhausorchester Leipzig calendar page parser."""
    records = []
    for event in soup.select(".event-item, .concert-row, [class*='veranstaltung']"):
        try:
            date_el = event.select_one("time, .datum, .date")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = event.select_one(".dirigent, .conductor, [class*='conductor']")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = event.select(".werk, .work, [class*='program']")
            program = [el.get_text(strip=True) for el in prog_els]

            link_el = event.select_one("a[href]")
            source_url = link_el["href"] if link_el else None
            if source_url and source_url.startswith("/"):
                source_url = "https://www.gewandhausorchester.de" + source_url

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": "Gewandhaus",
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("Gewandhaus parse error: %s", exc)

    return records


def parse_chicago(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """Chicago Symphony Orchestra season archive parser."""
    records = []
    for card in soup.select(".concert-card, .performance-item, article.event"):
        try:
            date_el = card.select_one("time, .concert-date, .date")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = card.select_one("[class*='conductor'], .artist-name")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = card.select(".work-title, .program li")
            program = [el.get_text(strip=True) for el in prog_els]

            link_el = card.select_one("a[href]")
            source_url = link_el["href"] if link_el else None
            if source_url and source_url.startswith("/"):
                source_url = "https://cso.org" + source_url

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": "Orchestra Hall",
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("Chicago parse error: %s", exc)

    return records


def parse_nyphil(soup: BeautifulSoup, season: int, config: dict) -> list[dict]:
    """New York Philharmonic season archive parser."""
    records = []
    for card in soup.select(".performance-card, .event-item, [class*='concert']"):
        try:
            date_el = card.select_one("time, .date, [class*='date']")
            date_str = _parse_date(date_el.get("datetime") or date_el.get_text() if date_el else None)

            cond_el = card.select_one("[class*='conductor'], .performer-name")
            conductor, role = (
                _extract_conductor_role(cond_el.get_text(strip=True)) if cond_el else (None, "Guest Conductor")
            )

            prog_els = card.select(".work, .program-work")
            program = [el.get_text(strip=True) for el in prog_els]

            link_el = card.select_one("a[href]")
            source_url = link_el["href"] if link_el else None

            records.append({
                "orchestra": config["name"],
                "conductor": conductor,
                "role": role,
                "date": date_str,
                "venue": "David Geffen Hall",
                "city": config["city"],
                "country": config["country"],
                "program": program,
                "season": season,
                "source_url": source_url,
            })
        except Exception as exc:
            log.debug("NY Phil parse error: %s", exc)

    return records


# ---------------------------------------------------------------------------
# Parser dispatch
# ---------------------------------------------------------------------------

PARSER_MAP = {
    "parse_bso": parse_bso,
    "parse_laphil": parse_laphil,
    "parse_philorch": parse_philorch,
    "parse_berlin": parse_berlin,
    "parse_gewandhaus": parse_gewandhaus,
    "parse_chicago": parse_chicago,
    "parse_nyphil": parse_nyphil,
}


# ---------------------------------------------------------------------------
# Per-orchestra scrape
# ---------------------------------------------------------------------------

def scrape_orchestra(slug: str, seasons: list[int] = DEFAULT_SEASONS) -> list[dict]:
    config = ORCHESTRA_CONFIGS[slug]
    parser_fn = PARSER_MAP[config["parser"]]
    is_json_api = "laphil" in slug  # expand as needed
    all_records: list[dict] = []

    cache_path = RAW_DIR / f"{slug}_seasons_raw.json"
    if cache_path.exists():
        log.info("Cache hit – loading %s from disk", slug)
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    log.info("Scraping %s (%d seasons)", config["name"], len(seasons))

    for season in seasons:
        url = config["seasons_url_template"].format(year=season, year1=season + 1)
        log.info("  Season %d-%d: %s", season, season + 1, url)
        try:
            data = _get(url, as_json=is_json_api)
            records = parser_fn(data, season, config)
            all_records.extend(records)
            log.info("  -> %d events parsed", len(records))
        except Exception as exc:
            log.warning("  Failed for season %d: %s", season, exc)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    log.info("Cached %d records -> %s", len(all_records), cache_path)

    return all_records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    orchestra_slugs: list[str] | None = None,
    seasons: list[int] = DEFAULT_SEASONS,
) -> list[dict]:
    slugs = orchestra_slugs or list(ORCHESTRA_CONFIGS.keys())
    all_records: list[dict] = []

    for slug in slugs:
        if slug not in ORCHESTRA_CONFIGS:
            log.warning("Unknown orchestra slug: %s — skipping", slug)
            continue
        records = scrape_orchestra(slug, seasons=seasons)
        all_records.extend(records)

    out_path = RAW_DIR / "all_orchestras_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    log.info("Wrote %d total records -> %s", len(all_records), out_path)

    return all_records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape orchestra season archives")
    parser.add_argument(
        "--orchestras",
        nargs="+",
        choices=list(ORCHESTRA_CONFIGS.keys()),
        default=list(ORCHESTRA_CONFIGS.keys()),
        help="Orchestra slugs to scrape",
    )
    parser.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    args = parser.parse_args()

    records = run(args.orchestras, args.seasons)
    print(f"\nDone. {len(records)} concert records collected.")

"""
geocoder.py

Resolves venue and city names to (latitude, longitude) using the Nominatim
geocoding service (OpenStreetMap). Results are cached to disk to avoid
re-querying the API on subsequent runs.

Nominatim usage policy:
  - Maximum 1 request per second (enforced here with a 1.1s delay)
  - Must identify the application via a unique User-Agent
  - No bulk geocoding of large datasets in a tight loop
  - See: https://operations.osmfoundation.org/policies/nominatim/

Outputs:
    data/processed/venues_geocoded.json   – {venue_key: {lat, lon, display_name}}
    data/external/world_cities.csv        – common city lookup table (supplemental)

Usage:
    python -m scraping.geocoder                  # geocode all venues in processed data
    python -m scraping.geocoder --query "Symphony Hall, Boston"
"""

import argparse
import json
import logging
import time
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
EXTERNAL_DIR = Path(__file__).parent.parent / "data" / "external"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

CACHE_PATH = PROCESSED_DIR / "venues_geocoded.json"
NOMINATIM_DELAY = 1.1  # seconds – Nominatim policy: max 1 req/sec

# Well-known venues that are tricky for Nominatim – hard-coded fallbacks
VENUE_OVERRIDES: dict[str, dict] = {
    "Symphony Hall, Boston":         {"lat": 42.3428,  "lon": -71.0857, "city": "Boston",       "country": "United States"},
    "Walt Disney Concert Hall":      {"lat": 34.0553,  "lon": -118.0993,"city": "Los Angeles",   "country": "United States"},
    "Carnegie Hall":                 {"lat": 40.7651,  "lon": -73.9800, "city": "New York",      "country": "United States"},
    "David Geffen Hall":             {"lat": 40.7725,  "lon": -73.9836, "city": "New York",      "country": "United States"},
    "Verizon Hall":                  {"lat": 39.9527,  "lon": -75.1635, "city": "Philadelphia",  "country": "United States"},
    "Orchestra Hall, Chicago":       {"lat": 41.8826,  "lon": -87.6243, "city": "Chicago",       "country": "United States"},
    "Philharmonie Berlin":           {"lat": 52.5097,  "lon": 13.3692,  "city": "Berlin",        "country": "Germany"},
    "Gewandhaus":                    {"lat": 51.3396,  "lon": 12.3758,  "city": "Leipzig",       "country": "Germany"},
    "Royal Albert Hall":             {"lat": 51.5009,  "lon": -0.1773,  "city": "London",        "country": "United Kingdom"},
    "Barbican Centre":               {"lat": 51.5200,  "lon": -0.0943,  "city": "London",        "country": "United Kingdom"},
    "Musikverein":                   {"lat": 48.2005,  "lon": 16.3726,  "city": "Vienna",        "country": "Austria"},
    "Concertgebouw":                 {"lat": 52.3560,  "lon": 4.8777,   "city": "Amsterdam",     "country": "Netherlands"},
    "Elbphilharmonie":               {"lat": 53.5413,  "lon": 9.9840,   "city": "Hamburg",       "country": "Germany"},
    "Salle Pleyel":                  {"lat": 48.8762,  "lon": 2.3015,   "city": "Paris",         "country": "France"},
    "Philharmonie de Paris":         {"lat": 48.8937,  "lon": 2.3940,   "city": "Paris",         "country": "France"},
}


# ---------------------------------------------------------------------------
# Geocoder setup
# ---------------------------------------------------------------------------

def _get_geolocator() -> Nominatim:
    return Nominatim(
        user_agent="ConductorNetworkResearch/1.0 (academic; contact=research@example.com)",
        timeout=10,
    )


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Geocoding logic
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _nominatim_query(geolocator: Nominatim, query: str) -> dict | None:
    """Run a single Nominatim query with retry logic."""
    try:
        location = geolocator.geocode(query, exactly_one=True, language="en")
        time.sleep(NOMINATIM_DELAY)
        if location:
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "display_name": location.address,
            }
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        log.warning("Nominatim error for '%s': %s", query, exc)
        raise  # let tenacity retry
    return None


def geocode_venue(
    venue: str,
    city: str | None = None,
    country: str | None = None,
    cache: dict | None = None,
    geolocator: Nominatim | None = None,
) -> dict | None:
    """
    Resolve a venue to {lat, lon, display_name, city, country}.

    Resolution order:
      1. Hard-coded overrides (VENUE_OVERRIDES)
      2. In-memory / on-disk cache
      3. Nominatim query: venue + city + country (most specific)
      4. Nominatim query: city + country (fallback if venue unknown)
    """
    # Build a normalised cache key
    parts = [p for p in [venue, city, country] if p]
    cache_key = ", ".join(parts).lower().strip()

    # 1. Hard-coded override – try with and without city/country suffix
    for override_key, override_val in VENUE_OVERRIDES.items():
        if override_key.lower() in cache_key or cache_key in override_key.lower():
            result = dict(override_val)
            result.setdefault("display_name", override_key)
            return result

    # 2. Cache hit
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    if geolocator is None:
        geolocator = _get_geolocator()

    # 3. Specific query
    specific_query = ", ".join(parts)
    result = _nominatim_query(geolocator, specific_query)

    # 4. Fallback: city + country only
    if result is None and city:
        fallback_parts = [p for p in [city, country] if p]
        result = _nominatim_query(geolocator, ", ".join(fallback_parts))

    if result:
        result["city"] = city
        result["country"] = country
        if cache is not None:
            cache[cache_key] = result
    else:
        log.warning("Could not geocode: %s", cache_key)

    return result


# ---------------------------------------------------------------------------
# Batch geocoding from processed data files
# ---------------------------------------------------------------------------

def collect_venues() -> list[dict]:
    """
    Collect all unique (venue, city, country) triples from raw scraped data.
    """
    venues: dict[str, dict] = {}

    def _add(venue, city, country):
        key = ", ".join(p for p in [venue, city, country] if p).lower()
        if key not in venues:
            venues[key] = {"venue": venue, "city": city, "country": country}

    # From Bachtrack
    bachtrack_path = RAW_DIR / "bachtrack" / "concert_listings_raw.json"
    if bachtrack_path.exists():
        with open(bachtrack_path, encoding="utf-8") as f:
            for record in json.load(f):
                _add(record.get("venue"), record.get("city"), record.get("country"))

    # From orchestra sites
    orchestra_path = RAW_DIR / "orchestra_websites" / "all_orchestras_raw.json"
    if orchestra_path.exists():
        with open(orchestra_path, encoding="utf-8") as f:
            for record in json.load(f):
                _add(record.get("venue"), record.get("city"), record.get("country"))

    # From Wikipedia orchestras
    wiki_orch_path = RAW_DIR / "wikipedia" / "orchestras_raw.json"
    if wiki_orch_path.exists():
        with open(wiki_orch_path, encoding="utf-8") as f:
            for record in json.load(f):
                _add(record.get("venue"), record.get("city"), record.get("country"))

    return list(venues.values())


def run_batch() -> dict:
    """Geocode all discovered venues, using cache to skip already-resolved ones."""
    cache = _load_cache()
    geolocator = _get_geolocator()
    venues = collect_venues()

    log.info("Geocoding %d unique venue/city combinations", len(venues))
    resolved = 0
    failed = 0

    for v in venues:
        result = geocode_venue(
            venue=v.get("venue", ""),
            city=v.get("city"),
            country=v.get("country"),
            cache=cache,
            geolocator=geolocator,
        )
        if result:
            resolved += 1
        else:
            failed += 1

    _save_cache(cache)
    log.info("Resolved: %d, Failed: %d -> %s", resolved, failed, CACHE_PATH)
    return cache


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geocode venues and cities")
    parser.add_argument("--query", type=str, help="Single venue query to test")
    args = parser.parse_args()

    if args.query:
        geolocator = _get_geolocator()
        result = geocode_venue(args.query, geolocator=geolocator)
        print(json.dumps(result, indent=2))
    else:
        cache = run_batch()
        print(f"\nDone. {len(cache)} venues geocoded.")

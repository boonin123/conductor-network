"""
wikipedia_scraper.py

Extracts conductor and orchestra data from Wikipedia infoboxes using the
MediaWiki API via mwclient. Produces two JSON files in data/raw/wikipedia/:
  - conductors_raw.json   – one record per conductor
  - orchestras_raw.json   – one record per orchestra discovered

Each conductor record contains:
  - name, birth_year, nationality
  - positions: list of {role, orchestra, start_year, end_year}
  - wikipedia_url

Run:
    python -m scraping.wikipedia_scraper
"""

import json
import logging
import re
import time
from pathlib import Path

import mwclient
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "wikipedia"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Conductor seed list – Wikipedia article titles
# ---------------------------------------------------------------------------
CONDUCTOR_PAGES = [
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

# Roles we consider "permanent positions" (case-insensitive substring match)
POSITION_ROLES = [
    "music director",
    "principal conductor",
    "chief conductor",
    "artistic director",
    "principal guest conductor",
    "conductor laureate",
    "conductor emeritus",
]

# Infobox parameter names that encode position information
POSITION_PARAMS = [
    "occupation",
    "employer",
    "works",
    # mwclient surfaces named params from {{Infobox musical artist}} etc.
]

# ---------------------------------------------------------------------------
# MediaWiki client
# ---------------------------------------------------------------------------

def get_client() -> mwclient.Site:
    site = mwclient.Site("en.wikipedia.org", path="/w/")
    site.requests["timeout"] = 30
    return site


# ---------------------------------------------------------------------------
# Infobox parsing helpers
# ---------------------------------------------------------------------------

def _strip_wiki_markup(text: str) -> str:
    """Remove wikilinks, templates, and HTML tags from a string."""
    # [[Target|Label]] -> Label, [[Target]] -> Target
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    # {{...}} templates
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # <ref>...</ref>
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    # remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # leading/trailing whitespace and pipes
    return text.strip().strip("|").strip()


def _extract_year(text: str | None) -> int | None:
    """Return the first 4-digit year found in text, or None."""
    if not text:
        return None
    m = re.search(r"\b(1[89]\d{2}|20[012]\d)\b", text)
    return int(m.group(1)) if m else None


def _parse_infobox(wikitext: str) -> dict:
    """
    Pull key-value pairs out of the first infobox template in raw wikitext.
    Returns a flat dict of {param_name: raw_value}.
    """
    # Find the infobox block – find opening {{ then match braces
    start = wikitext.find("{{Infobox")
    if start == -1:
        start = wikitext.find("{{infobox")
    if start == -1:
        return {}

    depth = 0
    end = start
    for i, ch in enumerate(wikitext[start:], start):
        if wikitext[i : i + 2] == "{{":
            depth += 1
        elif wikitext[i : i + 2] == "}}":
            depth -= 1
            if depth == 0:
                end = i + 2
                break

    infobox_text = wikitext[start:end]

    params: dict[str, str] = {}
    # Split on newline-pipe to get param lines: | key = value
    for line in re.split(r"\n\s*\|", infobox_text):
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower().replace(" ", "_")
        params[key] = value.strip()

    return params


def _parse_positions(wikitext: str, page_title: str) -> list[dict]:
    """
    Extract permanent conducting positions from the wikitext.

    Strategy:
      1. Look for the ==Conducting positions== or ==Career== section and parse
         tables / bullet lists that list role, orchestra, and years.
      2. Fall back to the infobox 'employer' or free-text career section.
      3. Scan for patterns like "Music Director of the X Orchestra (YYYY–YYYY)"
         in the body text.
    """
    positions = []

    # Pattern: common role phrase followed by orchestra name and optional years
    # e.g. "music director of the Boston Symphony Orchestra since 2014"
    # e.g. "Chief Conductor of the Gewandhausorchester Leipzig (2018–present)"
    role_pattern = re.compile(
        r"(?P<role>"
        + "|".join(re.escape(r) for r in POSITION_ROLES)
        + r")"
        r"(?:\s+of\s+(?:the\s+)?)?"
        # Greedy capture — stops at comma, paren, or newline; trailing noise stripped below
        r"(?P<orchestra>[A-Z][^\n,(]{4,60})"
        # Optional year block: "(2014–present)", "(2010–2018)", "since 2014", or bare "2014"
        r"(?:\s*[\(\[]?\s*(?:since\s+)?(?P<start>\d{4})(?:\s*[–\-]\s*(?P<end>\d{4}|present|ongoing))?\s*[\)\]]?)?",
        re.IGNORECASE,
    )

    for m in role_pattern.finditer(wikitext):
        role = m.group("role").strip().title()
        raw_orch = m.group("orchestra")
        # Strip trailing prepositions/connectors left by the greedy match
        raw_orch = re.sub(r'\s+(?:since|in|from|at|during)\s*$', '', raw_orch, flags=re.IGNORECASE)
        orchestra = _strip_wiki_markup(raw_orch.strip().rstrip(",;. "))
        start_year = int(m.group("start")) if m.group("start") else None
        end_raw = m.group("end") if m.group("end") else None
        end_year = None if end_raw in (None, "present", "ongoing") else int(end_raw)
        is_current = end_raw in ("present", "ongoing") or end_raw is None

        # Filter noise: skip very short or clearly non-orchestra strings
        if len(orchestra) < 6 or orchestra.lower().startswith("the "):
            orchestra = orchestra[4:] if orchestra.lower().startswith("the ") else orchestra

        positions.append(
            {
                "role": role,
                "orchestra": orchestra,
                "start_year": start_year,
                "end_year": end_year,
                "is_current": is_current,
            }
        )

    # Deduplicate by (role, orchestra)
    seen = set()
    unique: list[dict] = []
    for p in positions:
        key = (p["role"].lower(), p["orchestra"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# Per-conductor fetch
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_conductor(site: mwclient.Site, title: str) -> dict | None:
    log.info("Fetching: %s", title)
    page = site.pages[title]
    if not page.exists:
        log.warning("Page not found: %s", title)
        return None

    wikitext = page.text()
    infobox = _parse_infobox(wikitext)

    # Birth year – try infobox first, then body text
    birth_year = _extract_year(infobox.get("birth_date", "") or infobox.get("born", ""))
    if not birth_year:
        bm = re.search(r"born[^\d]*(\d{4})", wikitext[:500], re.IGNORECASE)
        birth_year = int(bm.group(1)) if bm else None

    # Nationality from infobox
    nationality_raw = infobox.get("nationality", "") or infobox.get("origin", "")
    nationality = _strip_wiki_markup(nationality_raw) or None

    positions = _parse_positions(wikitext, title)

    record = {
        "name": title,
        "birth_year": birth_year,
        "nationality": nationality,
        "positions": positions,
        "wikipedia_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "infobox_raw": {k: v for k, v in infobox.items() if k in (
            "birth_date", "born", "nationality", "origin",
            "employer", "occupation", "genre",
        )},
    }

    time.sleep(1)  # polite delay between requests
    return record


# ---------------------------------------------------------------------------
# Orchestra discovery
# ---------------------------------------------------------------------------

def _collect_orchestras(conductors: list[dict]) -> list[dict]:
    """
    Build a deduplicated list of orchestras mentioned in position records.
    Returns minimal stubs; full metadata will be enriched later.
    """
    seen: dict[str, dict] = {}
    for c in conductors:
        for pos in c.get("positions", []):
            name = pos["orchestra"]
            if name not in seen:
                seen[name] = {"name": name, "conductors": []}
            seen[name]["conductors"].append(
                {
                    "conductor": c["name"],
                    "role": pos["role"],
                    "start_year": pos["start_year"],
                    "end_year": pos["end_year"],
                }
            )
    return list(seen.values())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(conductor_pages: list[str] = CONDUCTOR_PAGES) -> tuple[list[dict], list[dict]]:
    site = get_client()
    conductors: list[dict] = []

    for title in conductor_pages:
        record = fetch_conductor(site, title)
        if record:
            conductors.append(record)

    orchestras = _collect_orchestras(conductors)

    # Persist raw results
    conductors_path = RAW_DIR / "conductors_raw.json"
    orchestras_path = RAW_DIR / "orchestras_raw.json"

    with open(conductors_path, "w", encoding="utf-8") as f:
        json.dump(conductors, f, indent=2, ensure_ascii=False)
    log.info("Wrote %d conductor records -> %s", len(conductors), conductors_path)

    with open(orchestras_path, "w", encoding="utf-8") as f:
        json.dump(orchestras, f, indent=2, ensure_ascii=False)
    log.info("Wrote %d orchestra stubs -> %s", len(orchestras), orchestras_path)

    return conductors, orchestras


if __name__ == "__main__":
    conductors, orchestras = run()
    print(f"\nDone. {len(conductors)} conductors, {len(orchestras)} orchestras discovered.")
    for c in conductors:
        print(f"\n  {c['name']} ({c['birth_year']}, {c['nationality']})")
        for p in c["positions"]:
            end = p["end_year"] or "present"
            print(f"    {p['role']} @ {p['orchestra']} ({p['start_year']}–{end})")

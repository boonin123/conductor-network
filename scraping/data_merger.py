"""
data_merger.py

Merges and deduplicates raw data from all scrapers into clean, analysis-ready
CSV files in data/processed/.

Pipeline:
  1. Load raw JSON from Wikipedia, Bachtrack, and orchestra site scrapers
  2. Normalise orchestra/conductor/venue names via fuzzy matching
  3. Deduplicate concert events (same conductor + date + orchestra = one event)
  4. Classify each appearance as permanent-position or guest
  5. Write processed CSVs:
     - conductors.csv
     - orchestras.csv
     - positions.csv          (permanent roles)
     - guest_appearances.csv  (individual guest events)
     - nodes_all.csv
     - edges_all.csv

Usage:
    python -m scraping.data_merger
"""

import json
import logging
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Fuzzy match score threshold (0-100). Pairs scoring above this are considered
# the same entity. Tune this carefully — too low causes false merges.
FUZZY_THRESHOLD = 88

# ---------------------------------------------------------------------------
# Canonical name maps – hand-verified corrections applied before fuzzy pass
# ---------------------------------------------------------------------------

ORCHESTRA_ALIASES: dict[str, str] = {
    "BSO": "Boston Symphony Orchestra",
    "Boston Symphony": "Boston Symphony Orchestra",
    "Boston Sym. Orch.": "Boston Symphony Orchestra",
    "LA Phil": "Los Angeles Philharmonic",
    "LA Philharmonic": "Los Angeles Philharmonic",
    "Los Angeles Phil": "Los Angeles Philharmonic",
    "LAPhil": "Los Angeles Philharmonic",
    "Philadelphia": "Philadelphia Orchestra",
    "The Philadelphia Orchestra": "Philadelphia Orchestra",
    "Berliner Philharmoniker": "Berlin Philharmonic",
    "Berlin Phil": "Berlin Philharmonic",
    "BPO": "Berlin Philharmonic",
    "Gewandhausorchester Leipzig": "Gewandhaus Orchestra Leipzig",
    "Gewandhausorchester": "Gewandhaus Orchestra Leipzig",
    "LGO": "Gewandhaus Orchestra Leipzig",
    "CSO": "Chicago Symphony Orchestra",
    "NY Phil": "New York Philharmonic",
    "New York Phil": "New York Philharmonic",
    "NYPhil": "New York Philharmonic",
    "Orchestre de Paris": "Orchestre de Paris",
    "Vienna Philharmonic": "Vienna Philharmonic",
    "Wiener Philharmoniker": "Vienna Philharmonic",
    "VPO": "Vienna Philharmonic",
    "Concertgebouw Orchestra": "Royal Concertgebouw Orchestra",
    "RCO": "Royal Concertgebouw Orchestra",
    "LSO": "London Symphony Orchestra",
}

CONDUCTOR_ALIASES: dict[str, str] = {
    "Nelsons": "Andris Nelsons",
    "A. Nelsons": "Andris Nelsons",
    "Dudamel": "Gustavo Dudamel",
    "G. Dudamel": "Gustavo Dudamel",
    "Nézet-Séguin": "Yannick Nézet-Séguin",
    "Nezet-Seguin": "Yannick Nézet-Séguin",
    "Mäkelä": "Klaus Mäkelä",
    "Makela": "Klaus Mäkelä",
    "Rattle": "Simon Rattle",
    "S. Rattle": "Simon Rattle",
    "Sir Simon Rattle": "Simon Rattle",
    "Petrenko": "Kirill Petrenko",
    "K. Petrenko": "Kirill Petrenko",
    "Muti": "Riccardo Muti",
    "R. Muti": "Riccardo Muti",
}

ROLE_NORMALISATION: dict[str, str] = {
    "music director": "Music Director",
    "chief conductor": "Chief Conductor",
    "principal conductor": "Principal Conductor",
    "artistic director": "Artistic Director",
    "principal guest conductor": "Principal Guest Conductor",
    "conductor laureate": "Conductor Laureate",
    "conductor emeritus": "Conductor Emeritus",
    "guest conductor": "Guest Conductor",
    "guest": "Guest Conductor",
}


# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------

def normalise_orchestra(name: str | None, canonical_set: list[str] | None = None) -> str | None:
    """
    Resolve an orchestra name to its canonical form.
      1. None / empty -> None
      2. Exact alias lookup
      3. Fuzzy match against known canonical set (if provided)
    """
    if not name or not name.strip():
        return None
    name = name.strip()

    # Exact alias
    if name in ORCHESTRA_ALIASES:
        return ORCHESTRA_ALIASES[name]

    # Case-insensitive alias
    lower = name.lower()
    for alias, canonical in ORCHESTRA_ALIASES.items():
        if alias.lower() == lower:
            return canonical

    # Fuzzy match
    if canonical_set:
        match, score, _ = process.extractOne(name, canonical_set, scorer=fuzz.token_sort_ratio)
        if score >= FUZZY_THRESHOLD:
            return match

    return name


def normalise_conductor(name: str | None) -> str | None:
    if not name or not name.strip():
        return None
    name = name.strip()
    if name in CONDUCTOR_ALIASES:
        return CONDUCTOR_ALIASES[name]
    lower = name.lower()
    for alias, canonical in CONDUCTOR_ALIASES.items():
        if alias.lower() == lower:
            return canonical
    return name


def normalise_role(role: str | None) -> str:
    if not role:
        return "Guest Conductor"
    return ROLE_NORMALISATION.get(role.lower().strip(), role.strip())


def _season_from_date(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        year = int(date_str[:4])
        month = int(date_str[5:7])
        return year if month >= 9 else year - 1
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Load raw data
# ---------------------------------------------------------------------------

def load_wikipedia_conductors() -> list[dict]:
    path = RAW_DIR / "wikipedia" / "conductors_raw.json"
    if not path.exists():
        log.warning("Wikipedia conductors not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_bachtrack() -> list[dict]:
    path = RAW_DIR / "bachtrack" / "concert_listings_raw.json"
    if not path.exists():
        log.warning("Bachtrack data not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_orchestra_sites() -> list[dict]:
    path = RAW_DIR / "orchestra_websites" / "all_orchestras_raw.json"
    if not path.exists():
        log.warning("Orchestra site data not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_geocache() -> dict:
    path = PROCESSED_DIR / "venues_geocoded.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Build processed tables
# ---------------------------------------------------------------------------

def build_conductors(wiki_data: list[dict]) -> pd.DataFrame:
    rows = []
    for c in wiki_data:
        rows.append({
            "conductor_id": re.sub(r"\W+", "_", c["name"].lower()),
            "name": c["name"],
            "birth_year": c.get("birth_year"),
            "nationality": c.get("nationality"),
            "wikipedia_url": c.get("wikipedia_url"),
        })
    df = pd.DataFrame(rows).drop_duplicates(subset=["name"])
    log.info("Conductors: %d records", len(df))
    return df


def build_positions(wiki_data: list[dict], canonical_orchestras: list[str]) -> pd.DataFrame:
    rows = []
    for c in wiki_data:
        for pos in c.get("positions", []):
            orch = normalise_orchestra(pos.get("orchestra"), canonical_orchestras)
            if not orch:
                continue
            rows.append({
                "conductor": c["name"],
                "orchestra": orch,
                "role": normalise_role(pos.get("role")),
                "start_year": pos.get("start_year"),
                "end_year": pos.get("end_year"),
                "is_current": pos.get("is_current", False),
            })
    df = pd.DataFrame(rows).drop_duplicates(subset=["conductor", "orchestra", "role", "start_year"])
    log.info("Positions: %d records", len(df))
    return df


def build_guest_appearances(
    bachtrack: list[dict],
    orchestra_sites: list[dict],
    positions_df: pd.DataFrame,
    canonical_orchestras: list[str],
) -> pd.DataFrame:
    """
    Combine Bachtrack + orchestra site records into a single appearance table.
    Classify each as 'permanent_home' or 'guest' based on whether the
    conductor held a permanent position at that orchestra at that time.
    """
    all_records = []

    for src_name, records in [("bachtrack", bachtrack), ("orchestra_site", orchestra_sites)]:
        for r in records:
            conductor = normalise_conductor(r.get("conductor"))
            orchestra = normalise_orchestra(r.get("orchestra"), canonical_orchestras)
            if not conductor or not orchestra:
                continue

            date_str = r.get("date")
            season = _season_from_date(date_str) or r.get("season")

            all_records.append({
                "conductor": conductor,
                "orchestra": orchestra,
                "date": date_str,
                "season": season,
                "venue": r.get("venue"),
                "city": r.get("city"),
                "country": r.get("country"),
                "program": "|".join(r.get("program") or []),
                "source": src_name,
                "source_url": r.get("source_url"),
            })

    df = pd.DataFrame(all_records)
    if df.empty:
        log.warning("No appearance records found")
        return df

    # Deduplicate: same conductor + date + orchestra = one event
    df = df.drop_duplicates(subset=["conductor", "date", "orchestra"])

    # Classify appearance type
    def _classify(row):
        if positions_df.empty:
            return "guest"
        mask = (
            (positions_df["conductor"] == row["conductor"])
            & (positions_df["orchestra"] == row["orchestra"])
        )
        pos = positions_df[mask]
        if pos.empty:
            return "guest"
        season = row.get("season")
        if season is None:
            return "permanent_home"
        for _, p in pos.iterrows():
            start = p["start_year"] or 0
            end = p["end_year"] or 9999
            if start <= season <= end:
                return "permanent_home"
        return "guest"

    df["appearance_type"] = df.apply(_classify, axis=1)
    log.info("Guest appearances: %d records (%d guest, %d home)",
             len(df),
             (df["appearance_type"] == "guest").sum(),
             (df["appearance_type"] == "permanent_home").sum())
    return df


def build_orchestras(wiki_data: list[dict], appearances_df: pd.DataFrame, geocache: dict) -> pd.DataFrame:
    """Build a deduplicated orchestra table with geocoordinates."""
    names: set[str] = set()

    # From Wikipedia position data
    for c in wiki_data:
        for pos in c.get("positions", []):
            n = normalise_orchestra(pos.get("orchestra"))
            if n:
                names.add(n)

    # From appearance data
    if not appearances_df.empty:
        for n in appearances_df["orchestra"].dropna().unique():
            names.add(str(n))

    rows = []
    for name in sorted(names):
        # Find lat/lon from geocache – try orchestra name as venue key
        geo = None
        for key, val in geocache.items():
            if name.lower() in key:
                geo = val
                break

        rows.append({
            "orchestra_id": re.sub(r"\W+", "_", name.lower()),
            "name": name,
            "city": geo.get("city") if geo else None,
            "country": geo.get("country") if geo else None,
            "lat": geo.get("lat") if geo else None,
            "lon": geo.get("lon") if geo else None,
        })

    df = pd.DataFrame(rows)
    log.info("Orchestras: %d records", len(df))
    return df


# ---------------------------------------------------------------------------
# Build graph node/edge tables
# ---------------------------------------------------------------------------

def build_nodes(conductors_df: pd.DataFrame, orchestras_df: pd.DataFrame) -> pd.DataFrame:
    cond_nodes = conductors_df[["conductor_id", "name"]].rename(
        columns={"conductor_id": "node_id", "name": "label"}
    ).assign(node_type="conductor")

    orch_nodes = orchestras_df[["orchestra_id", "name", "city", "country", "lat", "lon"]].rename(
        columns={"orchestra_id": "node_id", "name": "label"}
    ).assign(node_type="orchestra")

    df = pd.concat([cond_nodes, orch_nodes], ignore_index=True)
    log.info("Nodes: %d total", len(df))
    return df


def build_edges(positions_df: pd.DataFrame, appearances_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    # Permanent position edges
    for _, p in positions_df.iterrows():
        src_id = re.sub(r"\W+", "_", p["conductor"].lower())
        tgt_id = re.sub(r"\W+", "_", p["orchestra"].lower())
        rows.append({
            "source_id": src_id,
            "target_id": tgt_id,
            "edge_type": "permanent_position",
            "role": p["role"],
            "start_year": p.get("start_year"),
            "end_year": p.get("end_year"),
            "is_current": p.get("is_current"),
            "appearance_count": None,
            "season": None,
            "date": None,
        })

    # Guest appearance edges – one row per season per conductor-orchestra pair
    if not appearances_df.empty:
        grouped = appearances_df.groupby(["conductor", "orchestra", "season", "appearance_type"])
        for (conductor, orchestra, season, app_type), group in grouped:
            src_id = re.sub(r"\W+", "_", conductor.lower())
            tgt_id = re.sub(r"\W+", "_", orchestra.lower())
            rows.append({
                "source_id": src_id,
                "target_id": tgt_id,
                "edge_type": "guest_appearance" if app_type == "guest" else "permanent_home",
                "role": "Guest Conductor" if app_type == "guest" else "Music Director",
                "start_year": season,
                "end_year": season,
                "is_current": False,
                "appearance_count": len(group),
                "season": season,
                "date": None,
            })

    df = pd.DataFrame(rows)
    log.info("Edges: %d total", len(df))
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> dict[str, pd.DataFrame]:
    log.info("Loading raw data...")
    wiki_data = load_wikipedia_conductors()
    bachtrack = load_bachtrack()
    orchestra_sites = load_orchestra_sites()
    geocache = load_geocache()

    # Build canonical orchestra name list from Wikipedia positions
    canonical_orchestras = sorted({
        normalise_orchestra(pos.get("orchestra")) or pos.get("orchestra", "")
        for c in wiki_data
        for pos in c.get("positions", [])
        if pos.get("orchestra")
    })
    canonical_orchestras = [o for o in canonical_orchestras if o]
    log.info("Canonical orchestra list: %d names", len(canonical_orchestras))

    log.info("Building processed tables...")
    conductors_df = build_conductors(wiki_data)
    positions_df = build_positions(wiki_data, canonical_orchestras)
    appearances_df = build_guest_appearances(bachtrack, orchestra_sites, positions_df, canonical_orchestras)
    orchestras_df = build_orchestras(wiki_data, appearances_df, geocache)
    nodes_df = build_nodes(conductors_df, orchestras_df)
    edges_df = build_edges(positions_df, appearances_df)

    # Write to disk
    tables = {
        "conductors": conductors_df,
        "orchestras": orchestras_df,
        "positions": positions_df,
        "guest_appearances": appearances_df,
        "nodes_all": nodes_df,
        "edges_all": edges_df,
    }
    for name, df in tables.items():
        path = PROCESSED_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        log.info("Wrote %s -> %s", name, path)

    log.info("Data merger complete.")
    return tables


if __name__ == "__main__":
    run()

# Conductor Network

A network science investigation into whether Andris Nelsons was "stretched thin" across multiple conducting commitments — and whether that contributed to his non-renewal as Boston Symphony Orchestra Music Director.

Using graph theory, we compare Nelsons's orchestral involvement (degree centrality, geographic dispersion, home-share ratio, transatlantic transitions) against 7 peer conductors across seasons 2013–2024.

---

## Quickstart

```bash
git clone https://github.com/boonin123/conductor-network.git
cd conductor-network
pip install -r requirements.txt

# Run the dashboard (works immediately on sample data)
python -m dashboard.app
# → http://localhost:8051
```

No scraping required to explore the dashboard — a realistic sample dataset is built in.

---

## What's Inside

### Dashboard (3 tabs)

| Tab | What you see |
|---|---|
| **Geographic Map** | World map with great-circle arc overlays — orchestra nodes sized by visiting conductors, conductor diamonds at home city, arc opacity by permanence |
| **Network Graph** | Force-directed graph with Louvain community coloring; layout toggles (cose / concentric / breadthfirst); click any conductor node to load their profile |
| **Temporal Chart** | Season-by-season home vs. guest appearances per conductor; home-share ratio trend line with 50% reference |

The left panel shows a **conductor profile card** on node click: centrality scores, positions held with dates, and a career sparkline.

### Analysis Metrics

| Metric | Definition |
|---|---|
| `home_share_ratio` | Fraction of a season's appearances at permanent-position orchestras |
| `geographic_dispersion` | Mean pairwise haversine distance (km) across venues visited in a season |
| `transatlantic_transitions` | Minimum implied Atlantic crossings: `2 × min(Americas venues, European venues)` |
| `degree_by_edge_type` | Outgoing edge counts broken down by `permanent_position` / `guest_appearance` / `permanent_home` |
| `conductor_centrality_table` | Degree, weighted degree, betweenness, PageRank per conductor |
| `ego_network_size_over_time` | Distinct orchestras connected per season (permanent + seasonal) |

### Scraping Pipeline

Data sources (not yet run against live sites):

| Scraper | Source | Output |
|---|---|---|
| `wikipedia_scraper.py` | Wikipedia infoboxes via MediaWiki API | Permanent positions, years |
| `bachtrack_scraper.py` | Bachtrack concert database | Guest appearances with dates and programs |
| `orchestra_site_scraper.py` | BSO, LA Phil, Philadelphia, Berlin Phil, Gewandhaus, Chicago, NY Phil | Season archives |
| `geocoder.py` | Nominatim (OpenStreetMap) | Venue lat/lon |
| `data_merger.py` | All of the above | 6 clean CSVs in `data/processed/` |

To run the full pipeline:

```bash
python -m scraping.wikipedia_scraper
python -m scraping.bachtrack_scraper
python -m scraping.orchestra_site_scraper
python -m scraping.geocoder
python -m scraping.data_merger
python -m dashboard.app   # auto-detects real data
```

---

## Project Structure

```
conductor-network/
├── scraping/       — data acquisition (Wikipedia, Bachtrack, orchestra sites, geocoding)
├── network/        — graph construction (builder.py) and metrics (metrics.py)
├── dashboard/      — Dash app (app.py, components/, data.py, layout.py)
├── notebooks/      — planned analysis notebooks (00–08)
├── tests/          — 125 unit tests (pytest)
└── data/           — raw/ and processed/ (gitignored); external/ for reference files
```

---

## Running Tests

```bash
pytest tests/ -v
# 125 passed in ~1s (all offline, no network calls)
```

---

## Graph Schema

**Nodes**
- `conductor` — name, nationality, birth year
- `orchestra` — name, city, country, lat/lon, tier (`big5` / `regional` / `chamber`)

**Edges**
- `permanent_position` — structural role (Music Director, Chief Conductor, etc.) with year range
- `permanent_home` — counted appearances at a home orchestra in a given season
- `guest_appearance` — counted appearances at a guest orchestra in a given season

---

## Key Findings (sample data)

The sample data is generated with **historically realistic appearance counts** reflecting Nelsons's actual trajectory:

- BSO home appearances: **18 in 2014 → 7 in 2024** (58% decline)
- Leipzig appointment (2018) coincides with a sharp drop in BSO appearances
- Nelsons's `geographic_dispersion` (Boston ↔ Leipzig ↔ guest venues) is among the highest in the comparison pool
- His `home_share_ratio` drops below 0.5 in later seasons — meaning more than half his appearances are away from either permanent home

These patterns will be statistically tested once real data is scraped.

---

## Tech Stack

`networkx` · `pandas` · `plotly` · `dash` · `dash-cytoscape` · `dash-bootstrap-components` · `python-louvain` · `mwclient` · `beautifulsoup4` · `rapidfuzz` · `geopy` · `tenacity`

---

## Roadmap

- [ ] Run scraping pipeline against live sources
- [ ] Complete notebooks 00–08 (analysis pipeline)
- [ ] Add Met Opera / Paris Opera nodes
- [ ] Conductor comparison side-by-side panel in dashboard
- [ ] Public deployment (Render / HuggingFace Spaces)

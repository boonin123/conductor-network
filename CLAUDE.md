# Conductor Network Science Project

## Project Overview

This project investigates the claim that Maestro Andris Nelsons's non-renewal as Boston Symphony Orchestra (BSO) Music Director was related to overextension across multiple conducting commitments. Using network science, we quantify and compare his orchestral involvement against peer conductors to assess whether the "stretched thin" narrative holds statistical weight.

**Two deliverables:**
1. A Jupyter notebook suite with reproducible statistical network analysis
2. An interactive Dash dashboard visualizing conductor networks overlaid on a geographic map

---

## Status

| Layer | Status | Notes |
|---|---|---|
| Scraping pipeline | ✅ Built | Not yet run against live sources |
| `network/builder.py` | ✅ Complete | 125/125 tests passing |
| `network/metrics.py` | ✅ Complete | 125/125 tests passing |
| Dashboard | ✅ Running | Sample data; swap for real data after scraping |
| Notebooks | ⬜ Not started | Next phase |

---

## Research Questions

1. **Degree centrality**: How many distinct organizational relationships does each conductor maintain simultaneously? Is Nelsons an outlier?
2. **Temporal workload**: How does concert frequency per season compare across conductors? Does Nelsons show anomalous gaps at BSO?
3. **Multi-positional strain**: What is the structural cost of holding multiple Music Director positions simultaneously?
4. **Geographic dispersion**: How geographically scattered are each conductor's engagements? Does Nelsons's transatlantic footprint exceed peers?
5. **Community structure**: Do conductors cluster into regional/institutional communities? Is Nelsons a bridge node spanning European and American worlds?
6. **Betweenness centrality**: Does high betweenness (being a connector between communities) correlate with shorter tenure?
7. **Ego network evolution**: How has Nelsons's ego network grown over time (2013–2025), and when did it peak in complexity?

---

## Conductor Comparison Pool

Primary subject: **Andris Nelsons** (BSO 2014–2025; Leipzig Gewandhaus Orchestra 2018–present)

Peer comparators:
- Gustavo Dudamel (LA Phil + Paris Opera)
- Yannick Nézet-Séguin (Philadelphia Orchestra + Met Opera + Orchestre Métropolitain)
- Klaus Mäkelä (Concertgebouw + Oslo + Chicago incoming)
- Simon Rattle (London Symphony Orchestra)
- Riccardo Muti (Chicago Symphony Orchestra, emeritus)
- Kirill Petrenko (Berlin Philharmonic)
- Mirga Gražinytė-Tyla (City of Birmingham)

---

## Project Directory Structure

```
conductor-network/
├── CLAUDE.md
├── README.md
├── requirements.txt
│
├── data/
│   ├── raw/                          # Never modified after collection (gitignored)
│   │   ├── wikipedia/
│   │   ├── bachtrack/
│   │   └── orchestra_websites/
│   ├── processed/                    # Output of data_merger.py (gitignored)
│   │   ├── conductors.csv
│   │   ├── orchestras.csv
│   │   ├── positions.csv
│   │   ├── guest_appearances.csv
│   │   ├── nodes_all.csv
│   │   └── edges_all.csv
│   └── external/
│       └── world_cities.csv
│
├── scraping/
│   ├── wikipedia_scraper.py          # Permanent positions from infoboxes → conductors_raw.json
│   ├── bachtrack_scraper.py          # Paginated concert listings → concert_listings_raw.json
│   ├── orchestra_site_scraper.py     # 7 orchestra sites, 12 seasons each
│   ├── geocoder.py                   # Nominatim geocoding with 22 hard-coded overrides
│   └── data_merger.py                # Fuzzy entity resolution → 6 processed CSVs
│
├── network/
│   ├── builder.py                    # build_graph(), get_ego_network(), get_season_subgraph(),
│   │                                 # conductor_orchestra_bipartite(), validate_graph(), load_graph()
│   ├── metrics.py                    # degree_by_edge_type(), home_share_ratio(),
│   │                                 # geographic_dispersion(), transatlantic_transitions(),
│   │                                 # conductor_centrality_table(), ego_network_size_over_time()
│   ├── temporal.py                   # (placeholder — time-sliced utilities)
│   └── geo.py                        # (placeholder — geographic projections)
│
├── notebooks/
│   ├── 00_data_acquisition.ipynb     # ⬜ Scraping runs, raw data validation
│   ├── 01_data_cleaning.ipynb        # ⬜ Normalization, entity resolution
│   ├── 02_network_construction.ipynb # ⬜ Build MultiDiGraph, validate schema
│   ├── 03_descriptive_stats.ipynb    # ⬜ EDA: summary tables, degree distributions
│   ├── 04_centrality_analysis.ipynb  # ⬜ Main deliverable: centrality + peer comparison
│   ├── 05_temporal_analysis.ipynb    # ⬜ Season-by-season evolution
│   ├── 06_geographic_analysis.ipynb  # ⬜ Dispersion metrics, transatlantic transitions
│   ├── 07_community_detection.ipynb  # ⬜ Louvain/Leiden community structure
│   └── 08_conclusions.ipynb          # ⬜ Synthesis, narrative, key figures
│
├── dashboard/
│   ├── app.py                        # Dash app + all callbacks; run with `python -m dashboard.app`
│   ├── data.py                       # load_data(), generate_sample_data(), filter_data()
│   ├── layout.py                     # Two-panel dbc.Container layout
│   ├── assets/style.css
│   └── components/
│       ├── filters.py                # Left-panel controls (conductor, season, edge type, layout)
│       ├── map_view.py               # Plotly Scattergeo with great-circle arc traces
│       ├── network_view.py           # dash-cytoscape + Louvain community coloring
│       ├── conductor_profile.py      # Profile card with centrality badges + sparkline
│       └── timeline_view.py          # Stacked bar (home/guest) + home-share ratio line
│
└── tests/
    ├── test_scraping.py              # ✅ 70 tests (offline, no network calls)
    ├── test_network_builder.py       # ✅ 30 tests
    └── test_metrics.py               # ✅ 25 tests
```

---

## Running the Project

### Dashboard (sample data, no scraping required)
```bash
cd ~/Desktop/conductor-network
python -m dashboard.app              # → http://localhost:8051
python -m dashboard.app --port 8052  # custom port
```

### Full pipeline (real data)
```bash
# 1. Scrape permanent positions from Wikipedia
python -m scraping.wikipedia_scraper

# 2. Scrape concert listings from Bachtrack
python -m scraping.bachtrack_scraper

# 3. Scrape orchestra season archives
python -m scraping.orchestra_site_scraper

# 4. Geocode venues
python -m scraping.geocoder

# 5. Merge and deduplicate all sources
python -m scraping.data_merger

# 6. Restart dashboard — it auto-detects the processed CSVs
python -m dashboard.app
```

### Tests
```bash
pytest tests/ -v   # 125 tests, ~1s
```

---

## Technology Stack

### Analysis
| Purpose | Library |
|---|---|
| Graph data structure | `networkx` (MultiDiGraph) |
| Tabular data | `pandas` |
| Community detection | `python-louvain` (with `cdlib` fallback) |
| Statistical testing | `scipy.stats` (prefer non-parametric given small N) |
| Notebook charts | `matplotlib`, `seaborn`, `plotly` |

### Dashboard
| Purpose | Library |
|---|---|
| App framework | `Dash` + `dash-bootstrap-components` (FLATLY theme) |
| Geographic map | `plotly.graph_objects.Scattergeo` |
| Network graph | `dash-cytoscape` |

### Data Acquisition
| Purpose | Library |
|---|---|
| HTTP / HTML scraping | `requests`, `beautifulsoup4`, `lxml` |
| Wikipedia API | `mwclient` |
| Geocoding | `geopy` (Nominatim) |
| Fuzzy entity resolution | `rapidfuzz` |
| Retry logic | `tenacity` |

---

## Graph Schema

**Node types** (`node_type` attribute):
- `conductor`: label, nationality, birth_year
- `orchestra`: label, city, country, lat, lon, tier (`big5` / `regional` / `chamber`)

**Edge types** (`edge_type` attribute):
- `permanent_position`: conductor → orchestra | role, start_year, end_year, is_current
- `permanent_home`: conductor → orchestra | season, appearance_count (home appearances that season)
- `guest_appearance`: conductor → orchestra | season, appearance_count

**Projected graphs:**
- Conductor-orchestra bipartite (weight = total appearance count)
- Conductor co-appearance graph (shared orchestras)

---

## Notebook Analysis Plan

### 03 — Descriptive Statistics
- Conductor × (permanent positions, guest appearances, distinct orchestras, countries, active years)
- BSO appearances per season vs. Leipzig and guest total for Nelsons
- "Home share" ratio comparison across all conductors

### 04 — Centrality Analysis *(primary deliverable)*
- Degree, weighted degree, betweenness, PageRank on the bipartite projection
- Z-score: is Nelsons a statistical outlier vs. peers?
- Scatter: centrality vs. tenure length

### 05 — Temporal Analysis
- Time-sliced subgraphs per season (2013–2025)
- BSO share trend: when did BSO stop being the majority of Nelsons's schedule?
- Ego network size over time: when did complexity peak?

### 06 — Geographic Analysis
- Geographic dispersion index per conductor per season
- Transatlantic transitions: inferred Boston ↔ Leipzig crossing count
- Geographic centroid drift over career

### 07 — Community Detection
- Louvain on projected conductor-orchestra graph
- Do communities map to geographic regions?
- Is Nelsons a cross-community bridge? Compute bridge centrality.

### 08 — Conclusions
- Directly address "stretched thin" with effect sizes (Mann-Whitney U, Cohen's d)
- Confounders: COVID gaps (2020–22), Leipzig predates BSO, pandemic touring disruption
- Statistical note: N ≈ 10–15; report effect sizes, not just p-values

---

## Key Implementation Notes

- **All analytical logic lives in `network/`** — notebooks and dashboard both import from there. Notebooks = exploration. Dashboard = presentation only.
- **Sample data encodes the story**: BSO home appearances deliberately decline from 18 → 7 (2014 → 2024) in `generate_sample_data()` to reflect the real trajectory. The dashboard is already illustrative before scrapers are run.
- **Fuzzy threshold**: set to 82 in `data_merger.py`. Tune up if false merges appear; tune down if known aliases aren't resolving.
- **Geocoder cache**: `data/processed/venues_geocoded.json` — delete to force re-geocoding.
- **Statistical rigor**: small N (~10–15 conductors). Prefer Mann-Whitney U and Cohen's d over t-tests. Be explicit about this in notebook 08.

---

## Future Work

### Immediate (before notebooks)
- [ ] Run `wikipedia_scraper.py` and validate position extraction for all 8 conductors
- [ ] Run `bachtrack_scraper.py` — check robots.txt compliance, inspect first-page HTML to verify CSS selectors in `_parse_concert_list()`
- [ ] Validate `orchestra_site_scraper.py` against live BSO and Gewandhaus pages — site HTML changes frequently
- [ ] Run `data_merger.py` and audit entity resolution output for false merges / missed aliases

### Notebook phase
- [ ] `00_data_acquisition.ipynb` — scraping runs with raw data validation
- [ ] `01_data_cleaning.ipynb` — document all normalisation decisions
- [ ] `02_network_construction.ipynb` — build and validate full graph
- [ ] `03`–`08` analysis notebooks (see plan above)

### Dashboard enhancements
- [ ] Add a **conductor comparison panel**: side-by-side metric table for selected conductors
- [ ] Add **recordings layer** (Discogs/AllMusic data) as a third edge type
- [ ] Export selected ego network as PNG / GraphML from the network tab
- [ ] Deploy to a public URL (Render free tier, Railway, or HuggingFace Spaces)

### Data improvements
- [ ] Add Met Opera and Paris Opera as orchestra nodes (relevant for Nézet-Séguin and Dudamel)
- [ ] Extend conductor list: Jakub Hrůša, Robin Ticciati, Dalia Stasevska
- [ ] Cross-reference with recording contracts (Deutsche Grammophon, Sony Classical) as proxy for prestige/demand

---

## Changelog

### Session 1 — 2026-04-01
**Spec & scaffold**
- Created `CLAUDE.md` with full project specification, research questions, graph schema, and notebook + dashboard plans
- Initialized GitHub repo at `boonin123/conductor-network`
- Created full directory skeleton with Python packages

**Scraping layer**
- `scraping/wikipedia_scraper.py`: extracts permanent positions from Wikipedia infoboxes via `mwclient`; greedy orchestra regex with trailing-preposition strip; handles "since YYYY" year syntax
- `scraping/bachtrack_scraper.py`: paginated concert listings with per-conductor disk cache; 2s polite crawl delay
- `scraping/orchestra_site_scraper.py`: HTML/JSON parsers for BSO, LA Phil, Philadelphia, Berlin, Gewandhaus, Chicago, NY Phil across 12 seasons
- `scraping/geocoder.py`: Nominatim geocoding with 22 hard-coded venue overrides (Symphony Hall, Walt Disney Concert Hall, etc.), disk cache, batch mode
- `scraping/data_merger.py`: multi-source merge → 6 processed CSVs; `rapidfuzz` entity resolution; fuzzy threshold 82

**Network layer**
- `network/builder.py`: `build_graph()`, `get_ego_network()`, `get_season_subgraph()`, `conductor_orchestra_bipartite()`, `validate_graph()`, `load_graph()`
- `network/metrics.py`: `degree_by_edge_type()`, `home_share_ratio()`, `geographic_dispersion()` (haversine), `transatlantic_transitions()`, `conductor_centrality_table()`, `ego_network_size_over_time()`

**Test suite**
- `tests/test_scraping.py`: 70 offline tests
- `tests/test_network_builder.py`: 30 tests
- `tests/test_metrics.py`: 25 tests
- **125/125 tests passing**

**Dashboard**
- `dashboard/data.py`: `AppData` dataclass, `generate_sample_data()` (8 conductors, 12 orchestras, 2013–2024 with realistic BSO decline curve), `load_data()` with CSV fallback, `filter_data()`
- `dashboard/components/filters.py`: sticky left-panel controls
- `dashboard/components/map_view.py`: Scattergeo with grouped great-circle arcs (None-separator technique), orchestra circles, conductor diamonds
- `dashboard/components/network_view.py`: `dash-cytoscape` elements + stylesheet; Louvain community detection with `python-louvain` fallback; per-element background color; ego `dimmed` class
- `dashboard/components/conductor_profile.py`: centrality badges, positions list, dual-axis sparkline
- `dashboard/components/timeline_view.py`: `make_subplots` stacked bars + home-share ratio line with 50% reference
- `dashboard/layout.py`: two-panel `dbc.Container` (4/8 split), sample-data warning alert
- `dashboard/app.py`: 3 callbacks (visualisations, layout toggle, profile card); default port 8051

**Bug fixes**
- `_extract_year(None)` now returns `None` instead of crashing
- Orchestra regex made greedy with trailing-preposition strip
- Fuzzy threshold lowered 88 → 82
- NaN → `int` cast guarded in `map_view.py`

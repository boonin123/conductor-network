# Conductor Network Science Project

## Project Overview

This project investigates the claim that Maestro Andris Nelsons's non-renewal as Boston Symphony Orchestra (BSO) Music Director was related to overextension across multiple conducting commitments. Using network science, we quantify and compare his orchestral involvement against peer conductors to assess whether the "stretched thin" narrative holds statistical weight.

**Two deliverables:**
1. A Jupyter notebook suite with reproducible statistical network analysis
2. An interactive dashboard visualizing conductor networks overlaid on a geographic map

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

Peer comparators (adjust as data permits):
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
├── CLAUDE.md                         # This file
├── README.md
├── requirements.txt
│
├── data/
│   ├── raw/                          # Never modified after collection
│   │   ├── wikipedia/
│   │   ├── bachtrack/
│   │   └── orchestra_websites/
│   ├── processed/
│   │   ├── conductors.csv
│   │   ├── orchestras.csv            # Includes lat/lon
│   │   ├── positions.csv             # Permanent roles: who, where, start/end year
│   │   ├── guest_appearances.csv     # Individual guest events
│   │   ├── nodes_all.csv
│   │   └── edges_all.csv             # Schema: source_id, target_id, edge_type, role, start_date, end_date, appearance_count, season, venue_id
│   └── external/
│       └── world_cities.csv          # Geocoding reference
│
├── scraping/
│   ├── wikipedia_scraper.py          # Conductor/orchestra infobox extraction (build first)
│   ├── bachtrack_scraper.py          # Concert listing scraper
│   ├── orchestra_site_scraper.py     # Per-orchestra season page scrapers
│   ├── geocoder.py                   # Venue/city lat-lon resolution via Nominatim
│   └── data_merger.py                # Deduplication and cross-source entity resolution
│
├── notebooks/
│   ├── 00_data_acquisition.ipynb     # Scraping runs, raw data validation
│   ├── 01_data_cleaning.ipynb        # Normalization, deduplication, entity resolution
│   ├── 02_network_construction.ipynb # Build MultiDiGraph, validate schema
│   ├── 03_descriptive_stats.ipynb    # EDA: summary tables, degree distributions
│   ├── 04_centrality_analysis.ipynb  # Main deliverable: centrality metrics + peer comparison
│   ├── 05_temporal_analysis.ipynb    # Season-by-season network evolution
│   ├── 06_geographic_analysis.ipynb  # Dispersion metrics, transatlantic transitions
│   ├── 07_community_detection.ipynb  # Louvain/Leiden community structure
│   └── 08_conclusions.ipynb          # Synthesis, narrative, key figures
│
├── network/
│   ├── builder.py                    # Graph construction from processed CSVs (imported by all notebooks + dashboard)
│   ├── metrics.py                    # Custom metric computations
│   ├── temporal.py                   # Time-sliced subgraph utilities
│   └── geo.py                        # Geographic graph projections
│
└── dashboard/
    ├── app.py                        # Main Dash entry point
    ├── layout.py                     # Top-level layout
    ├── assets/
    │   └── style.css
    └── components/
        ├── map_view.py               # Plotly Scattergeo geographic network overlay (most complex)
        ├── network_view.py           # dash-cytoscape force-directed graph
        ├── conductor_profile.py      # Selected conductor stats card
        ├── timeline_view.py          # Seasonal activity stacked chart
        └── filters.py                # Year range, conductor selector, edge type toggles
```

---

## Technology Stack

### Analysis
| Purpose | Library |
|---|---|
| Graph data structure | `networkx` (MultiDiGraph) |
| Tabular data | `pandas` |
| Community detection | `cdlib` (Louvain/Leiden) or `python-louvain` |
| Statistical testing | `scipy.stats` (prefer non-parametric given small N) |
| Notebook charts | `matplotlib`, `seaborn`, `plotly` |

### Dashboard
| Purpose | Library |
|---|---|
| App framework | `Dash` (Plotly) |
| Geographic map | `plotly.graph_objects.Scattergeo` |
| Network graph | `dash-cytoscape` |
| Styling | Dash Bootstrap Components |

### Data Acquisition
| Purpose | Library |
|---|---|
| HTTP / scraping | `requests`, `beautifulsoup4`, `lxml` |
| Wikipedia API | `mwclient` or `wikipedia-api` |
| Geocoding | `geopy` (Nominatim — free, no API key) |
| Fuzzy matching | `rapidfuzz` (entity resolution) |
| Rate limiting | `tenacity` |

---

## Graph Schema

**Node types** (distinguished by `node_type` attribute):
- `conductor`: name, nationality, birth_year, active_since
- `orchestra`: name, city, country, lat, lon, tier (Big 5 / regional / chamber)
- `venue`: name, city, country, lat, lon, capacity
- `season`: year integer (e.g., 2019 = 2018–19 season)

**Edge types** (distinguished by `edge_type` attribute):
- `permanent_position`: conductor → orchestra | role, start_year, end_year
- `guest_appearance`: conductor → orchestra | date, program, venue
- `performs_at`: orchestra → venue | home/guest flag
- `active_in`: conductor → season (derived)

**Projected graphs for analysis:**
- Conductor-orchestra bipartite (weight = total appearances)
- Conductor co-appearance graph (shared orchestra connections)
- Orchestra similarity graph (shared conducting personnel)

---

## Notebook Analysis Plan

### 03 — Descriptive Statistics
- Table: conductor × (permanent positions, guest appearances, distinct orchestras, countries, active years)
- Bar chart: total engagements per conductor per season
- Nelsons-specific: BSO appearances per season vs. Leipzig and guest total
- "Home share" ratio: what fraction of each conductor's appearances are at their primary employer?

### 04 — Centrality Analysis (primary deliverable)
- Degree, weighted degree, betweenness, PageRank on conductor-orchestra bipartite
- Scatter plot: centrality score vs. tenure length (does high centrality predict shorter tenure?)
- Nelsons as outlier? Z-score vs. peer distribution

### 05 — Temporal Analysis
- Time-sliced subgraphs per season (2013–2025)
- Track Nelsons's degree over time; identify when external engagement grew most sharply
- BSO share trend: when did BSO stop being the majority of his schedule?

### 06 — Geographic Analysis
- Per conductor per season: distinct countries, mean distance between consecutive concerts, geographic centroid
- Transatlantic transitions: count Boston ↔ Leipzig flights implied by schedule
- Geographic dispersion index: variance of (lat, lon) across season appearances

### 07 — Community Detection
- Louvain on projected conductor-orchestra graph
- Do communities map to geographic regions?
- Is Nelsons a cross-community bridge? Compute bridge score.

### 08 — Conclusions
- Directly address "stretched thin" claim with effect sizes
- Note confounders: COVID gaps (2020–22), Leipzig appointment predates BSO role
- Statistical note: N is small (10–15 conductors); use non-parametric tests, report effect sizes not just p-values

---

## Dashboard Layout

**Left panel (40%):** Controls + Conductor Profile Card
- Multi-select dropdown: conductor selection
- Year range slider: season filter
- Edge type radio: permanent only / guest only / all
- Profile card on node click: name, positions, centrality scores, career sparkline

**Right panel (60%):** Tabbed visualizations

**Tab 1 — Geographic Map (`map_view.py`)**
- Orchestra nodes: circles sized by number of visiting conductors, colored by tier
- Conductor nodes: diamonds at home-base city
- Edges: great-circle arc lines weighted by appearance count; permanent = high opacity, guest = low opacity
- Ego network highlight on conductor selection: connected orchestras enlarge, others dim

**Tab 2 — Network Graph (`network_view.py`)**
- `dash-cytoscape` force-directed layout (cose-bilkent default)
- Conductor nodes colored by community; orchestra nodes sized by prestige tier
- Edge thickness by appearance weight
- Hover tooltip: role, years active, appearance count
- Layout toggle: force-directed / concentric (centrality-ordered) / breadthfirst

**Tab 3 — Temporal Chart (`timeline_view.py`)**
- Stacked area: home-orchestra appearances vs. guest appearances per season per conductor
- Small multiples: "home share" ratio over time for each selected conductor

---

## Data Acquisition Strategy

### Phase 1: Permanent Positions (Wikipedia infoboxes)
Extract for each conductor: all permanent roles (Music Director, Principal Conductor, Principal Guest Conductor) with start/end years. This is the backbone of the graph — build `wikipedia_scraper.py` first.

### Phase 2: Orchestra Metadata
For each orchestra in the resulting set: city, country, venue, lat/lon. Geocode via Nominatim, cache results.

### Phase 3: Guest Appearances
**Bachtrack** is the primary source (most comprehensive concert database). Check robots.txt, use respectful rate limiting. Each result: date, conductor, orchestra, venue, program.

**Orchestra season archives**: BSO, LA Phil, Philadelphia, Berlin Phil, etc. post programs on their websites (often 5–10 seasons back).

**Fallback**: Manual curation from press releases for Nelsons and 2–3 key comparators if scraping is incomplete.

### Phase 4: Entity Resolution
Orchestra names vary across sources ("BSO", "Boston Symphony", "Boston Symphony Orchestra"). Use `rapidfuzz` for fuzzy matching before deduplication. Same for venues and conductor name variants.

---

## Key Implementation Notes

- **All analytical logic lives in `network/`** so both notebooks and dashboard import from the same source. Notebooks = exploration. Dashboard = presentation only.
- **`network/builder.py` is the central hub** — define graph schema here; all other code depends on it.
- **`wikipedia_scraper.py` quality determines data quality everywhere downstream** — invest in robust entity resolution here.
- **`map_view.py` is the most technically complex dashboard component** — the geographic network overlay is the project's signature visual.
- **`edges_all.csv` schema is load-bearing** — design columns carefully: `source_id, target_id, edge_type, role, start_date, end_date, appearance_count, season, venue_id`.
- **Statistical rigor note**: With ~10–15 conductors in the comparison pool, prefer Mann-Whitney U and Cohen's d over t-tests and raw p-values.
- All scraping writes to `data/raw/` with timestamps. All cleaning decisions documented in `01_data_cleaning.ipynb` with explicit justifications.
- Pin all package versions in `requirements.txt` for reproducibility.

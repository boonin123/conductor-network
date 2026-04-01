"""
dashboard/data.py

Single source of truth for dashboard data. Loads the graph from
data/processed/ CSVs if they exist; falls back to a hardcoded
sample dataset so the dashboard runs without scrapers having been run.

Public API:
    load_data() -> AppData
    filter_data(app_data, conductor_ids, season_range, edge_types) -> FilteredData
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from network.builder import build_graph, load_graph
from network.metrics import conductor_centrality_table

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class AppData:
    graph: nx.MultiDiGraph
    nodes_df: pd.DataFrame
    edges_df: pd.DataFrame
    centrality_df: pd.DataFrame
    conductors: list[str]                   # sorted conductor node_ids
    conductor_labels: dict[str, str]        # {node_id: display label}
    seasons: list[int]
    is_sample: bool = False


@dataclass
class FilteredData:
    graph: nx.MultiDiGraph
    nodes_df: pd.DataFrame
    edges_df: pd.DataFrame


# ---------------------------------------------------------------------------
# Edge type helpers
# ---------------------------------------------------------------------------

EDGE_TYPE_GROUPS = {
    "all":       ["permanent_position", "permanent_home", "guest_appearance"],
    "permanent": ["permanent_position", "permanent_home"],
    "guest":     ["guest_appearance"],
}


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    return re.sub(r"\W+", "_", name.lower()).strip("_")


def generate_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generates a realistic sample dataset covering 8 conductors,
    10 orchestras, and seasons 2013–2024.
    """

    # --- Conductors ----------------------------------------------------------
    conductors_raw = [
        ("Andris Nelsons",        None,    None),
        ("Gustavo Dudamel",       None,    None),
        ("Yannick Nézet-Séguin",  None,    None),
        ("Klaus Mäkelä",          None,    None),
        ("Simon Rattle",          None,    None),
        ("Riccardo Muti",         None,    None),
        ("Kirill Petrenko",       None,    None),
        ("Mirga Gražinytė-Tyla",  None,    None),
    ]

    # --- Orchestras (with real coordinates) ----------------------------------
    orchestras_raw = [
        ("Boston Symphony Orchestra",         "Boston",       "USA",         42.3453, -71.0872, "big5"),
        ("Los Angeles Philharmonic",           "Los Angeles",  "USA",         34.0549, -118.2426, "big5"),
        ("Philadelphia Orchestra",             "Philadelphia", "USA",         39.9526, -75.1652, "big5"),
        ("Berlin Philharmonic",                "Berlin",       "Germany",     52.5096,  13.3690, "big5"),
        ("Gewandhaus Orchestra Leipzig",       "Leipzig",      "Germany",     51.3400,  12.3747, "big5"),
        ("Chicago Symphony Orchestra",         "Chicago",      "USA",         41.8799, -87.6278, "big5"),
        ("London Symphony Orchestra",          "London",       "UK",          51.5074,  -0.0999, "big5"),
        ("Royal Concertgebouw Orchestra",      "Amsterdam",    "Netherlands", 52.3580,   4.8836, "big5"),
        ("Oslo Philharmonic",                  "Oslo",         "Norway",      59.9139,  10.7522, "regional"),
        ("City of Birmingham Symphony Orchestra", "Birmingham","UK",          52.4862,  -1.8904, "regional"),
        ("Vienna Philharmonic",                "Vienna",       "Austria",     48.2005,  16.3726, "big5"),
        ("New York Philharmonic",              "New York",     "USA",         40.7725, -73.9836, "big5"),
    ]

    # Build nodes_df
    node_rows = []
    for name, lat, lon in conductors_raw:
        node_rows.append({
            "node_id": _slug(name), "label": name,
            "node_type": "conductor", "lat": lat, "lon": lon,
            "city": None, "country": None, "tier": None,
        })
    for name, city, country, lat, lon, tier in orchestras_raw:
        node_rows.append({
            "node_id": _slug(name), "label": name,
            "node_type": "orchestra", "lat": lat, "lon": lon,
            "city": city, "country": country, "tier": tier,
        })
    nodes_df = pd.DataFrame(node_rows)

    # --- Permanent positions (role, start, end | None = current) ------------
    # (conductor_name, orchestra_name, role, start, end)
    permanent_positions = [
        ("Andris Nelsons",       "Boston Symphony Orchestra",          "Music Director",           2014, 2024),
        ("Andris Nelsons",       "Gewandhaus Orchestra Leipzig",       "Chief Conductor",          2018, None),
        ("Gustavo Dudamel",      "Los Angeles Philharmonic",           "Music Director",           2009, None),
        ("Yannick Nézet-Séguin", "Philadelphia Orchestra",             "Music Director",           2012, None),
        ("Yannick Nézet-Séguin", "New York Philharmonic",              "Music Director",           2018, None),
        ("Klaus Mäkelä",         "Oslo Philharmonic",                  "Chief Conductor",          2020, None),
        ("Klaus Mäkelä",         "Royal Concertgebouw Orchestra",      "Chief Conductor Designate",2022, None),
        ("Simon Rattle",         "London Symphony Orchestra",          "Music Director",           2017, None),
        ("Riccardo Muti",        "Chicago Symphony Orchestra",         "Music Director",           2010, 2023),
        ("Kirill Petrenko",      "Berlin Philharmonic",                "Chief Conductor",          2019, None),
        ("Mirga Gražinytė-Tyla","City of Birmingham Symphony Orchestra","Music Director",          2016, 2022),
    ]

    # Guest appearance patterns: (conductor, orchestra, seasons_list, count_per_season)
    guest_appearances = [
        # Nelsons guest appearances outside BSO/Leipzig
        ("Andris Nelsons",       "Berlin Philharmonic",            [2015,2017,2019,2021,2023], 3),
        ("Andris Nelsons",       "Vienna Philharmonic",            [2016,2018,2020,2022],      2),
        ("Andris Nelsons",       "Royal Concertgebouw Orchestra",  [2015,2019,2023],           2),
        ("Andris Nelsons",       "Los Angeles Philharmonic",       [2017,2021],                3),
        ("Andris Nelsons",       "Chicago Symphony Orchestra",     [2016,2020,2022],           2),
        # Dudamel
        ("Gustavo Dudamel",      "Berlin Philharmonic",            [2014,2016,2018,2020,2022], 3),
        ("Gustavo Dudamel",      "Vienna Philharmonic",            [2015,2017,2019,2021,2023], 2),
        ("Gustavo Dudamel",      "Boston Symphony Orchestra",      [2015,2019],                2),
        # Nézet-Séguin
        ("Yannick Nézet-Séguin", "Vienna Philharmonic",            [2014,2016,2018,2020],      2),
        ("Yannick Nézet-Séguin", "Berlin Philharmonic",            [2015,2017,2021,2023],      2),
        ("Yannick Nézet-Séguin", "Royal Concertgebouw Orchestra",  [2016,2020],                2),
        # Mäkelä
        ("Klaus Mäkelä",         "Berlin Philharmonic",            [2021,2022,2023],           3),
        ("Klaus Mäkelä",         "Chicago Symphony Orchestra",     [2022,2023],                2),
        # Rattle
        ("Simon Rattle",         "Berlin Philharmonic",            [2017,2019,2021,2023],      3),
        ("Simon Rattle",         "Vienna Philharmonic",            [2018,2020,2022],           2),
        ("Simon Rattle",         "Boston Symphony Orchestra",      [2018,2022],                2),
        # Petrenko
        ("Kirill Petrenko",      "Vienna Philharmonic",            [2019,2021,2023],           3),
        ("Kirill Petrenko",      "Royal Concertgebouw Orchestra",  [2020,2022],                2),
    ]

    # Home appearance counts per season (realistic, reflecting "stretching")
    # Nelsons BSO home share drops noticeably after 2018 (Leipzig appointment)
    nelsons_bso_home = {
        2014:18, 2015:20, 2016:19, 2017:18, 2018:14, 2019:12, 2020:8,
        2021:10, 2022:9, 2023:8, 2024:7,
    }
    nelsons_lgw_home = {
        2018:10, 2019:12, 2020:6, 2021:9, 2022:10, 2023:11, 2024:12,
    }
    dudamel_laph_home = {
        2013:22, 2014:22, 2015:21, 2016:20, 2017:20, 2018:19, 2019:18,
        2020:12, 2021:14, 2022:18, 2023:17, 2024:17,
    }
    nezet_phil_home = {
        2013:16, 2014:17, 2015:16, 2016:15, 2017:14, 2018:10, 2019:10,
        2020:8,  2021:9,  2022:10, 2023:10, 2024:11,
    }
    nezet_nyphil_home = {
        2018:12, 2019:14, 2020:8, 2021:10, 2022:11, 2023:12, 2024:13,
    }
    makela_oslo_home  = {2020:14, 2021:16, 2022:12, 2023:12, 2024:12}
    makela_rcg_home   = {2022:10, 2023:11, 2024:13}
    rattle_lso_home   = {2017:16, 2018:17, 2019:16, 2020:10, 2021:12, 2022:14, 2023:14, 2024:14}
    muti_cso_home     = {2013:16, 2014:15, 2015:14, 2016:13, 2017:12, 2018:11, 2019:10, 2020:6, 2021:8, 2022:9, 2023:8}
    petrenko_bph_home = {2019:14, 2020:8, 2021:11, 2022:14, 2023:15, 2024:16}
    mirga_cbso_home   = {2016:14, 2017:15, 2018:13, 2019:12, 2020:8, 2021:10, 2022:9}

    conductor_home_maps = {
        ("Andris Nelsons",        "Boston Symphony Orchestra"):           nelsons_bso_home,
        ("Andris Nelsons",        "Gewandhaus Orchestra Leipzig"):        nelsons_lgw_home,
        ("Gustavo Dudamel",       "Los Angeles Philharmonic"):            dudamel_laph_home,
        ("Yannick Nézet-Séguin",  "Philadelphia Orchestra"):             nezet_phil_home,
        ("Yannick Nézet-Séguin",  "New York Philharmonic"):              nezet_nyphil_home,
        ("Klaus Mäkelä",          "Oslo Philharmonic"):                   makela_oslo_home,
        ("Klaus Mäkelä",          "Royal Concertgebouw Orchestra"):      makela_rcg_home,
        ("Simon Rattle",          "London Symphony Orchestra"):           rattle_lso_home,
        ("Riccardo Muti",         "Chicago Symphony Orchestra"):          muti_cso_home,
        ("Kirill Petrenko",       "Berlin Philharmonic"):                 petrenko_bph_home,
        ("Mirga Gražinytė-Tyla", "City of Birmingham Symphony Orchestra"): mirga_cbso_home,
    }

    # --- Build edges_df -------------------------------------------------------
    edge_rows = []

    # Permanent positions
    for cond, orch, role, start, end in permanent_positions:
        is_current = end is None
        edge_rows.append({
            "source_id": _slug(cond), "target_id": _slug(orch),
            "edge_type": "permanent_position", "role": role,
            "start_year": start, "end_year": end,
            "is_current": is_current, "appearance_count": None, "season": None,
        })

    # Home appearances
    for (cond, orch), season_map in conductor_home_maps.items():
        for season, count in season_map.items():
            # Find the matching permanent position to get role
            role = next(
                (r for c, o, r, s, e in permanent_positions
                 if c == cond and o == orch),
                "Music Director"
            )
            edge_rows.append({
                "source_id": _slug(cond), "target_id": _slug(orch),
                "edge_type": "permanent_home", "role": role,
                "start_year": season, "end_year": season,
                "is_current": False, "appearance_count": count, "season": season,
            })

    # Guest appearances
    for cond, orch, seasons_list, count in guest_appearances:
        for season in seasons_list:
            edge_rows.append({
                "source_id": _slug(cond), "target_id": _slug(orch),
                "edge_type": "guest_appearance", "role": "Guest Conductor",
                "start_year": season, "end_year": season,
                "is_current": False, "appearance_count": count, "season": season,
            })

    edges_df = pd.DataFrame(edge_rows)
    return nodes_df, edges_df


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_data() -> AppData:
    """
    Load processed CSVs if available, otherwise fall back to sample data.
    Computes centrality once at load time.
    """
    is_sample = False
    try:
        graph = load_graph()
        from pathlib import Path
        nodes_df = pd.read_csv(Path(__file__).parent.parent / "data" / "processed" / "nodes_all.csv")
        edges_df = pd.read_csv(Path(__file__).parent.parent / "data" / "processed" / "edges_all.csv")
    except FileNotFoundError:
        is_sample = True
        nodes_df, edges_df = generate_sample_data()
        graph = build_graph(nodes_df, edges_df)

    # Compute centrality once
    try:
        centrality_df = conductor_centrality_table(graph)
    except Exception:
        # Fallback: empty centrality table
        conductors_in_graph = [
            n for n, d in graph.nodes(data=True) if d.get("node_type") == "conductor"
        ]
        centrality_df = pd.DataFrame({
            "conductor": conductors_in_graph,
            "degree": 0, "weighted_degree": 0.0,
            "betweenness": 0.0, "pagerank": 0.0,
        })

    # Conductor metadata
    conductor_rows = nodes_df[nodes_df["node_type"] == "conductor"]
    conductors = sorted(conductor_rows["node_id"].tolist())
    conductor_labels = dict(zip(conductor_rows["node_id"], conductor_rows["label"]))

    # Season range
    season_vals = edges_df["season"].dropna().astype(int)
    seasons = sorted(season_vals.unique().tolist()) if len(season_vals) else [2013, 2024]

    return AppData(
        graph=graph,
        nodes_df=nodes_df,
        edges_df=edges_df,
        centrality_df=centrality_df,
        conductors=conductors,
        conductor_labels=conductor_labels,
        seasons=seasons,
        is_sample=is_sample,
    )


# ---------------------------------------------------------------------------
# Filter helper
# ---------------------------------------------------------------------------

def filter_data(
    app_data: AppData,
    conductor_ids: list[str] | None,
    season_range: list[int] | None,
    edge_type_filter: str = "all",
) -> FilteredData:
    """
    Apply UI filter state to produce a filtered subgraph.
    Permanent_position edges are always included (they define structure).
    """
    if not conductor_ids:
        conductor_ids = app_data.conductors

    season_min, season_max = (
        (season_range[0], season_range[1]) if season_range and len(season_range) == 2
        else (app_data.seasons[0], app_data.seasons[-1])
    )

    allowed_edge_types = EDGE_TYPE_GROUPS.get(edge_type_filter, EDGE_TYPE_GROUPS["all"])

    edges = app_data.edges_df
    nodes = app_data.nodes_df

    # Always keep permanent_position edges for structural integrity
    mask_permanent = edges["edge_type"] == "permanent_position"
    mask_type = edges["edge_type"].isin(allowed_edge_types)
    mask_season = (
        edges["season"].isna() |
        (edges["season"].between(season_min, season_max))
    )
    mask_conductor = edges["source_id"].isin(conductor_ids)

    edges_filtered = edges[
        mask_conductor & (mask_permanent | (mask_type & mask_season))
    ].copy()

    # Include nodes referenced by filtered edges + selected conductor nodes
    referenced_node_ids = (
        set(edges_filtered["source_id"].tolist()) |
        set(edges_filtered["target_id"].tolist()) |
        set(conductor_ids)
    )
    nodes_filtered = nodes[nodes["node_id"].isin(referenced_node_ids)].copy()

    graph_filtered = build_graph(nodes_filtered, edges_filtered)

    return FilteredData(
        graph=graph_filtered,
        nodes_df=nodes_filtered,
        edges_df=edges_filtered,
    )

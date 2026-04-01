"""
network/metrics.py

Custom metric computations on the conductor-orchestra MultiDiGraph.
All functions are pure (no side effects, no disk I/O) and importable
by both notebooks and the dashboard.

Public API:
    degree_by_edge_type(graph, conductor_id)          -> dict[str, int]
    home_share_ratio(graph, conductor_id, season)     -> float | None
    geographic_dispersion(graph, conductor_id, season)-> float | None
    transatlantic_transitions(graph, conductor_id, season) -> int
    conductor_centrality_table(graph)                 -> pd.DataFrame
    ego_network_size_over_time(graph, conductor_id, seasons) -> dict[int, int]
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations

import networkx as nx
import pandas as pd

# Longitude threshold separating the Americas from Europe/Africa.
# Venues with lon < ATLANTIC_THRESHOLD are classified as "Americas";
# those with lon >= ATLANTIC_THRESHOLD as "Europe/Africa/Asia".
ATLANTIC_THRESHOLD = -25.0

# Edge types that count as home-orchestra appearances
HOME_EDGE_TYPES = {"permanent_home"}

# Edge types that count as guest appearances
GUEST_EDGE_TYPES = {"guest_appearance"}

# Edge types that represent a permanent structural tie (season-agnostic)
PERMANENT_EDGE_TYPES = {"permanent_position"}


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_conductor(graph: nx.MultiDiGraph, conductor_id: str) -> None:
    if conductor_id not in graph:
        raise KeyError(f"Conductor '{conductor_id}' not found in graph")


def _season_edges(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    season: int,
    edge_types: set[str] | None = None,
) -> list[tuple[str, dict]]:
    """
    Return list of (target_node_id, edge_data) for edges from conductor_id
    whose season == season and whose edge_type is in edge_types (or all if None).
    """
    results = []
    for _, tgt, data in graph.out_edges(conductor_id, data=True):
        if data.get("season") != season:
            continue
        if edge_types is None or data.get("edge_type") in edge_types:
            results.append((tgt, data))
    return results


def _appearance_count(data: dict) -> float:
    """Extract appearance_count from edge data, defaulting to 1."""
    c = data.get("appearance_count")
    return float(c) if c is not None else 1.0


# ---------------------------------------------------------------------------
# Public metrics
# ---------------------------------------------------------------------------

def degree_by_edge_type(graph: nx.MultiDiGraph, conductor_id: str) -> dict[str, int]:
    """
    Count outgoing edges from conductor_id broken down by edge_type.
    Counts each edge in the MultiDiGraph individually (parallel edges are
    counted separately), reflecting the full multiplicity of connections.

    Returns: {"permanent_position": N, "guest_appearance": M, ...}
    Raises: KeyError if conductor_id not in graph.
    """
    _require_conductor(graph, conductor_id)
    counts: dict[str, int] = defaultdict(int)
    for _, _, data in graph.out_edges(conductor_id, data=True):
        edge_type = data.get("edge_type", "unknown")
        counts[edge_type] += 1
    return dict(counts)


def home_share_ratio(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    season: int,
) -> float | None:
    """
    Fraction of a conductor's appearances in a season that are at their
    permanent-position orchestras.

        home_share = home_appearances / (home_appearances + guest_appearances)

    Returns None if the conductor had no appearances in that season.
    """
    _require_conductor(graph, conductor_id)

    home_total = 0.0
    guest_total = 0.0

    for _, tgt, data in graph.out_edges(conductor_id, data=True):
        if data.get("season") != season:
            continue
        edge_type = data.get("edge_type", "")
        count = _appearance_count(data)
        if edge_type in HOME_EDGE_TYPES:
            home_total += count
        elif edge_type in GUEST_EDGE_TYPES:
            guest_total += count

    total = home_total + guest_total
    if total == 0.0:
        return None

    return home_total / total


def geographic_dispersion(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    season: int,
) -> float | None:
    """
    Mean pairwise great-circle distance (km) between all distinct orchestra
    venues visited by the conductor in the given season.

    Venues are weighted by appearance_count — a venue with more appearances
    contributes more to the centroid calculation.

    Returns:
        0.0 if only one distinct venue was visited
        None if no seasonal appearances exist for that season
    """
    _require_conductor(graph, conductor_id)

    # Collect distinct venues with their coordinates and total appearance weight
    venue_weights: dict[str, tuple[float, float, float]] = {}  # node_id -> (lat, lon, weight)

    for _, tgt, data in graph.out_edges(conductor_id, data=True):
        if data.get("season") != season:
            continue
        orch_data = graph.nodes.get(tgt, {})
        lat = orch_data.get("lat")
        lon = orch_data.get("lon")
        if lat is None or lon is None:
            continue
        count = _appearance_count(data)
        if tgt in venue_weights:
            existing_lat, existing_lon, existing_w = venue_weights[tgt]
            venue_weights[tgt] = (existing_lat, existing_lon, existing_w + count)
        else:
            venue_weights[tgt] = (float(lat), float(lon), count)

    if not venue_weights:
        return None

    venues = list(venue_weights.values())  # [(lat, lon, weight), ...]

    if len(venues) == 1:
        return 0.0

    # Mean pairwise distance (unweighted across pairs)
    distances = [
        _haversine_km(a[0], a[1], b[0], b[1])
        for a, b in combinations(venues, 2)
    ]
    return sum(distances) / len(distances)


def transatlantic_transitions(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    season: int,
) -> int:
    """
    Minimum number of transatlantic crossings implied by a conductor's
    seasonal activity — inferred from whether they had appearances in both
    the Americas (lon < -25°) and Europe/Africa/Asia (lon >= -25°).

    Without precise concert dates we cannot reconstruct the exact sequence,
    so we return the theoretical minimum: 2 × min(#American_venues, #European_venues).
    This is conservative — the real number is typically higher.

    Returns 0 if the conductor only appeared on one side of the Atlantic
    or had no appearances in that season.
    """
    _require_conductor(graph, conductor_id)

    americas_venues: set[str] = set()
    europe_venues: set[str] = set()

    for _, tgt, data in graph.out_edges(conductor_id, data=True):
        if data.get("season") != season:
            continue
        orch_data = graph.nodes.get(tgt, {})
        lon = orch_data.get("lon")
        if lon is None:
            continue
        if float(lon) < ATLANTIC_THRESHOLD:
            americas_venues.add(tgt)
        else:
            europe_venues.add(tgt)

    if not americas_venues or not europe_venues:
        return 0

    # Each visit to a European venue from an Americas base (or vice versa)
    # requires at least one crossing each way
    return 2 * min(len(americas_venues), len(europe_venues))


def conductor_centrality_table(graph: nx.MultiDiGraph) -> pd.DataFrame:
    """
    Compute centrality metrics for every conductor node in the graph.

    Metrics computed on the conductor-orchestra bipartite projection
    (undirected, weighted by appearance counts):
      - degree:           number of distinct orchestras connected to
      - weighted_degree:  sum of edge weights (total appearances)
      - betweenness:      betweenness centrality on the bipartite graph
      - pagerank:         PageRank on the full MultiDiGraph

    Returns a DataFrame with columns:
        conductor, degree, weighted_degree, betweenness, pagerank
    """
    from network.builder import conductor_orchestra_bipartite

    conductor_ids = [
        n for n, d in graph.nodes(data=True) if d.get("node_type") == "conductor"
    ]

    if not conductor_ids:
        return pd.DataFrame(columns=["conductor", "degree", "weighted_degree", "betweenness", "pagerank"])

    bp = conductor_orchestra_bipartite(graph)

    # Betweenness on bipartite graph
    betweenness = nx.betweenness_centrality(bp, weight="weight")

    # PageRank on the full graph (undirected view for stability with sparse graphs)
    undirected = graph.to_undirected()
    pagerank = nx.pagerank(undirected, weight=None, alpha=0.85)

    rows = []
    for cid in conductor_ids:
        deg = bp.degree(cid) if cid in bp else 0
        w_deg = sum(d.get("weight", 0) for _, _, d in bp.edges(cid, data=True)) if cid in bp else 0.0
        rows.append({
            "conductor": cid,
            "degree": int(deg),
            "weighted_degree": float(w_deg),
            "betweenness": float(betweenness.get(cid, 0.0)),
            "pagerank": float(pagerank.get(cid, 0.0)),
        })

    return pd.DataFrame(rows)


def ego_network_size_over_time(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    seasons: list[int],
) -> dict[int, int]:
    """
    For each season in `seasons`, count the number of distinct orchestras
    connected to the conductor — combining:
      - Permanent positions active in that season (start_year <= season <= end_year)
      - Any seasonal appearance edges (guest or home) with season == S

    Returns {season: distinct_orchestra_count}
    """
    _require_conductor(graph, conductor_id)

    if not seasons:
        return {}

    result: dict[int, int] = {}

    for season in seasons:
        orchestras: set[str] = set()

        for _, tgt, data in graph.out_edges(conductor_id, data=True):
            tgt_type = graph.nodes.get(tgt, {}).get("node_type")
            if tgt_type != "orchestra":
                continue

            edge_type = data.get("edge_type", "")

            if edge_type == "permanent_position":
                start = data.get("start_year") or 0
                end = data.get("end_year") or 9999
                if start <= season <= end:
                    orchestras.add(tgt)
            elif data.get("season") == season:
                orchestras.add(tgt)

        result[season] = len(orchestras)

    return result

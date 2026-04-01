"""
network/builder.py

Constructs the conductor-orchestra MultiDiGraph from processed CSV data.
This module is the central hub imported by all notebooks and the dashboard.

Public API:
    build_graph(nodes_df, edges_df)          -> nx.MultiDiGraph
    get_ego_network(graph, conductor_id)     -> nx.MultiDiGraph
    get_season_subgraph(graph, season)       -> nx.MultiDiGraph
    conductor_orchestra_bipartite(graph)     -> nx.Graph
    validate_graph(graph)                    -> list[str]
    load_graph()                             -> nx.MultiDiGraph   (from processed CSVs)
"""

from __future__ import annotations

import logging
from pathlib import Path

import networkx as nx
import pandas as pd

log = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

VALID_NODE_TYPES = {"conductor", "orchestra", "venue", "season"}
VALID_EDGE_TYPES = {"permanent_position", "guest_appearance", "permanent_home", "performs_at", "active_in"}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> nx.MultiDiGraph:
    """
    Build a MultiDiGraph from nodes and edges DataFrames.

    nodes_df columns: node_id, label, node_type, [lat, lon, ...]
    edges_df columns: source_id, target_id, edge_type, role, start_year,
                      end_year, is_current, appearance_count, season
    """
    g = nx.MultiDiGraph()

    for _, row in nodes_df.iterrows():
        attrs = {k: v for k, v in row.items() if k != "node_id" and not _is_na(v)}
        g.add_node(str(row["node_id"]), **attrs)

    for _, row in edges_df.iterrows():
        src = str(row["source_id"])
        tgt = str(row["target_id"])
        attrs = {k: v for k, v in row.items()
                 if k not in ("source_id", "target_id") and not _is_na(v)}
        g.add_edge(src, tgt, **attrs)

    log.debug("Built graph: %d nodes, %d edges", g.number_of_nodes(), g.number_of_edges())
    return g


def _is_na(value) -> bool:
    """Return True for None, NaN, or pandas NA so we don't pollute node attrs."""
    if value is None:
        return True
    try:
        import math
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Subgraph helpers
# ---------------------------------------------------------------------------

def get_ego_network(graph: nx.MultiDiGraph, conductor_id: str, radius: int = 1) -> nx.MultiDiGraph:
    """
    Return the ego network centred on conductor_id up to `radius` hops.
    Raises KeyError if the node is not in the graph.
    """
    if conductor_id not in graph:
        raise KeyError(f"Node '{conductor_id}' not found in graph")

    # nx.ego_graph works on the underlying undirected view for neighbour discovery
    ego_nodes = {conductor_id}
    frontier = {conductor_id}
    for _ in range(radius):
        next_frontier = set()
        for node in frontier:
            next_frontier.update(graph.successors(node))
            next_frontier.update(graph.predecessors(node))
        next_frontier -= ego_nodes
        ego_nodes |= next_frontier
        frontier = next_frontier

    return graph.subgraph(ego_nodes).copy()


def get_season_subgraph(graph: nx.MultiDiGraph, season: int) -> nx.MultiDiGraph:
    """
    Return a subgraph containing:
      - All nodes
      - Permanent-position edges (season-agnostic, always included)
      - Seasonal edges (guest_appearance, permanent_home) whose season matches

    This allows temporal slicing while preserving the structural backbone.
    """
    sg = nx.MultiDiGraph()
    sg.add_nodes_from(graph.nodes(data=True))

    for u, v, data in graph.edges(data=True):
        edge_season = data.get("season")
        edge_type = data.get("edge_type", "")

        if edge_type == "permanent_position":
            # Check the permanent position was active in this season
            start = data.get("start_year") or 0
            end = data.get("end_year") or 9999
            if start <= season <= end:
                sg.add_edge(u, v, **data)
        elif edge_season == season:
            sg.add_edge(u, v, **data)

    return sg


# ---------------------------------------------------------------------------
# Bipartite projection
# ---------------------------------------------------------------------------

def conductor_orchestra_bipartite(graph: nx.MultiDiGraph) -> nx.Graph:
    """
    Project the MultiDiGraph onto an undirected conductor-orchestra bipartite
    graph. Each conductor-orchestra pair becomes a single edge; the weight is
    the total appearance_count across all edges between that pair, with
    permanent positions contributing a weight of 1 if no count is available.

    Only conductor and orchestra nodes are included.
    """
    bp = nx.Graph()

    # Add typed nodes
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") in ("conductor", "orchestra"):
            bp.add_node(node_id, **data)

    # Aggregate weights per conductor-orchestra pair
    weights: dict[tuple[str, str], float] = {}
    for u, v, data in graph.edges(data=True):
        u_type = graph.nodes[u].get("node_type")
        v_type = graph.nodes[v].get("node_type")
        if not (
            (u_type == "conductor" and v_type == "orchestra") or
            (u_type == "orchestra" and v_type == "conductor")
        ):
            continue

        pair = (min(u, v), max(u, v))
        count = data.get("appearance_count")
        weight = float(count) if count is not None else 1.0
        weights[pair] = weights.get(pair, 0.0) + weight

    for (u, v), weight in weights.items():
        if bp.has_node(u) and bp.has_node(v):
            bp.add_edge(u, v, weight=weight)

    return bp


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_graph(graph: nx.MultiDiGraph) -> list[str]:
    """
    Run structural sanity checks on the graph.
    Returns a list of error strings; empty list means the graph is valid.
    """
    errors: list[str] = []

    # Node checks
    for node_id, data in graph.nodes(data=True):
        if "node_type" not in data:
            errors.append(f"Node '{node_id}' missing required attribute 'node_type'")
        elif data["node_type"] not in VALID_NODE_TYPES:
            errors.append(
                f"Node '{node_id}' has unknown node_type '{data['node_type']}'"
                f" (expected one of {VALID_NODE_TYPES})"
            )

    # Edge checks
    for u, v, key, data in graph.edges(keys=True, data=True):
        if "edge_type" not in data:
            errors.append(f"Edge ({u} -> {v}, key={key}) missing 'edge_type'")
        if "role" not in data:
            errors.append(f"Edge ({u} -> {v}, key={key}) missing 'role'")

        # Check both endpoints have node_type (catches auto-created stub nodes)
        for endpoint, label in [(u, "source"), (v, "target")]:
            if "node_type" not in graph.nodes[endpoint]:
                errors.append(
                    f"Edge ({u} -> {v}): {label} node '{endpoint}' "
                    f"is missing 'node_type' (may be auto-created by edge addition)"
                )

    if errors:
        log.warning("Graph validation found %d issue(s)", len(errors))
    return errors


# ---------------------------------------------------------------------------
# Load from disk
# ---------------------------------------------------------------------------

def load_graph() -> nx.MultiDiGraph:
    """
    Build the graph from the processed CSV files produced by data_merger.py.
    Raises FileNotFoundError if the processed data hasn't been generated yet.
    """
    nodes_path = PROCESSED_DIR / "nodes_all.csv"
    edges_path = PROCESSED_DIR / "edges_all.csv"

    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError(
            f"Processed data not found at {PROCESSED_DIR}. "
            "Run `python -m scraping.data_merger` first."
        )

    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)
    log.info("Loaded %d nodes, %d edges from disk", len(nodes_df), len(edges_df))

    return build_graph(nodes_df, edges_df)

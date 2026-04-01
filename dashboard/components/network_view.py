"""
dashboard/components/network_view.py

Builds cytoscape element lists and stylesheets for the network graph tab.
Pure functions — no Dash callbacks.
"""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import plotly.express as px

# Community detection — optional dependencies
try:
    from community import best_partition as louvain_partition
    _HAS_LOUVAIN = True
except ImportError:
    _HAS_LOUVAIN = False

_COMMUNITY_PALETTE = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------

def compute_communities(graph: nx.MultiDiGraph) -> dict[str, int]:
    """
    Run Louvain community detection on the bipartite undirected projection.
    Returns {node_id: community_int}. Falls back to all-zeros if louvain
    is unavailable or the graph is empty.
    """
    if not _HAS_LOUVAIN or graph.number_of_nodes() == 0:
        return {n: 0 for n in graph.nodes()}

    try:
        from network.builder import conductor_orchestra_bipartite
        bp = conductor_orchestra_bipartite(graph)
        undirected = bp.to_undirected() if bp.is_directed() else bp
        partition = louvain_partition(undirected, random_state=42)
        # Remap community ints to be 0-indexed and compact
        unique = sorted(set(partition.values()))
        remap = {old: new for new, old in enumerate(unique)}
        return {node: remap[comm] for node, comm in partition.items()}
    except Exception:
        return {n: 0 for n in graph.nodes()}


def get_community_palette(n_communities: int) -> list[str]:
    palette = _COMMUNITY_PALETTE
    return [palette[i % len(palette)] for i in range(max(n_communities, 1))]


# ---------------------------------------------------------------------------
# Cytoscape element builder
# ---------------------------------------------------------------------------

def build_cytoscape_elements(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    community_map: dict[str, int] | None,
    centrality_df: pd.DataFrame | None,
    selected_conductor: str | None = None,
) -> list[dict]:
    """
    Returns list of cytoscape element dicts.
    Nodes get per-element `style` for community color (cytoscape
    stylesheet cannot reference data fields for color directly).
    """
    if community_map is None:
        community_map = {}

    palette = get_community_palette(max(community_map.values(), default=0) + 1)

    # Build degree lookup from centrality_df
    degree_map: dict[str, int] = {}
    wdegree_map: dict[str, float] = {}
    if centrality_df is not None and not centrality_df.empty:
        for _, row in centrality_df.iterrows():
            degree_map[row["conductor"]]  = int(row.get("degree", 0))
            wdegree_map[row["conductor"]] = float(row.get("weighted_degree", 0.0))

    elements: list[dict] = []
    node_ids_present: set[str] = set()

    # ── Nodes ──────────────────────────────────────────────────────────────
    for _, row in nodes_df.iterrows():
        nid       = str(row["node_id"])
        ntype     = str(row.get("node_type", ""))
        label     = str(row.get("label", nid))
        tier      = str(row.get("tier", "")) if row.get("tier") else ""
        community = community_map.get(nid, 0)
        node_ids_present.add(nid)

        classes = [ntype]
        if tier:
            classes.append(tier)
        if nid == selected_conductor:
            classes.append("selected")

        node_color = (
            palette[community % len(palette)]
            if ntype == "conductor"
            else _orchestra_color(tier)
        )

        elements.append({
            "data": {
                "id":             nid,
                "label":          label,
                "node_type":      ntype,
                "tier":           tier,
                "community":      community,
                "degree":         degree_map.get(nid, 0),
                "weighted_degree":wdegree_map.get(nid, 0.0),
            },
            "classes": " ".join(classes),
            "style":   {"background-color": node_color},
        })

    # ── Edges ──────────────────────────────────────────────────────────────
    for i, row in edges_df.iterrows():
        src  = str(row["source_id"])
        tgt  = str(row["target_id"])
        if src not in node_ids_present or tgt not in node_ids_present:
            continue

        etype    = str(row.get("edge_type", ""))
        role     = str(row.get("role", ""))
        count    = row.get("appearance_count")
        weight   = _normalise_weight(float(count) if count else 1.0)
        season   = row.get("season")
        label    = f"{role} ({season})" if season else role

        edge_class = "permanent" if "permanent" in etype else "guest"

        elements.append({
            "data": {
                "id":         f"{src}-{tgt}-{etype}-{i}",
                "source":     src,
                "target":     tgt,
                "edge_type":  etype,
                "weight":     weight,
                "role":       role,
                "label":      label,
            },
            "classes": edge_class,
        })

    return elements


def _orchestra_color(tier: str) -> str:
    return {
        "big5":     "#1565C0",
        "regional": "#42A5F5",
        "chamber":  "#80DEEA",
    }.get(tier, "#78909C")


def _normalise_weight(raw: float, lo: float = 1.0, hi: float = 30.0) -> float:
    """Map raw appearance count to a 1–10 display weight."""
    clamped = max(lo, min(raw, hi))
    return 1.0 + 9.0 * (math.log(clamped) - math.log(lo)) / (math.log(hi) - math.log(lo))


# ---------------------------------------------------------------------------
# Stylesheet builder
# ---------------------------------------------------------------------------

def build_cytoscape_stylesheet(
    community_palette: list[str] | None = None,
    selected_conductor: str | None = None,
) -> list[dict]:
    """
    Returns the cytoscape CSS stylesheet.
    Community colors are applied via per-element `style` in elements list;
    the stylesheet handles shape, size, and structural properties.
    """
    base = [
        # ── Default node ────────────────────────────────────────────────
        {
            "selector": "node",
            "style": {
                "label":            "data(label)",
                "font-size":        "9px",
                "text-valign":      "bottom",
                "text-halign":      "center",
                "text-margin-y":    "4px",
                "text-wrap":        "wrap",
                "text-max-width":   "80px",
                "background-color": "#78909C",
                "color":            "#424242",
                "width":            "24px",
                "height":           "24px",
                "border-width":     "1px",
                "border-color":     "#ffffff",
                "border-opacity":   "0.6",
            },
        },
        # ── Conductor nodes ─────────────────────────────────────────────
        {
            "selector": "node.conductor",
            "style": {
                "shape":    "diamond",
                "width":    "38px",
                "height":   "38px",
                "font-size": "10px",
                "font-weight": "bold",
            },
        },
        # ── Orchestra tiers ─────────────────────────────────────────────
        {
            "selector": "node.orchestra.big5",
            "style": {"width": "28px", "height": "28px"},
        },
        {
            "selector": "node.orchestra.regional",
            "style": {"width": "20px", "height": "20px"},
        },
        {
            "selector": "node.orchestra.chamber",
            "style": {"width": "14px", "height": "14px"},
        },
        # ── Selected node ────────────────────────────────────────────────
        {
            "selector": "node.selected",
            "style": {
                "border-width":   "3px",
                "border-color":   "#E91E63",
                "width":          "50px",
                "height":         "50px",
            },
        },
        # ── Dimmed node (ego highlighting) ──────────────────────────────
        {
            "selector": "node.dimmed",
            "style": {"opacity": "0.15"},
        },
        # ── Default edge ────────────────────────────────────────────────
        {
            "selector": "edge",
            "style": {
                "curve-style":     "bezier",
                "opacity":         "0.5",
                "line-color":      "#B0BEC5",
                "width":           "mapData(weight, 1, 10, 1, 6)",
                "target-arrow-shape": "none",
            },
        },
        # ── Permanent edges ─────────────────────────────────────────────
        {
            "selector": "edge.permanent",
            "style": {
                "line-color": "#1565C0",
                "opacity":    "0.75",
                "line-style": "solid",
            },
        },
        # ── Guest edges ─────────────────────────────────────────────────
        {
            "selector": "edge.guest",
            "style": {
                "line-color": "#FF7043",
                "opacity":    "0.45",
                "line-style": "dashed",
                "line-dash-pattern": [6, 3],
            },
        },
        # ── Hovered node ────────────────────────────────────────────────
        {
            "selector": "node:selected",
            "style": {
                "border-width": "3px",
                "border-color": "#E91E63",
            },
        },
    ]

    # Ego highlighting: if a conductor is selected, add dimmed class
    # styles to non-neighbours (applied by callback via classes on elements)
    if selected_conductor:
        base.append({
            "selector": f"node#{selected_conductor}",
            "style": {
                "border-width": "4px",
                "border-color": "#E91E63",
                "opacity":      "1.0",
            },
        })

    return base

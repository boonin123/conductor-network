"""
dashboard/app.py

Dash app entry point. All callbacks are centralized here.

Run:
    python -m dashboard.app
    # or:
    python dashboard/app.py
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import Input, Output, State, callback_context

import dashboard.data as data
import dashboard.layout as layout
from dashboard.components import (
    map_view,
    network_view,
    conductor_profile,
    timeline_view,
)
from dashboard.components.filters import (
    ID_CONDUCTOR_DROPDOWN,
    ID_SEASON_SLIDER,
    ID_EDGE_TYPE_RADIO,
    ID_LAYOUT_RADIO,
    ID_PROFILE_CONTAINER,
)
from network.metrics import (
    ego_network_size_over_time,
    home_share_ratio,
)

# ---------------------------------------------------------------------------
# Initialise
# ---------------------------------------------------------------------------

cyto.load_extra_layouts()

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    title="Conductor Network",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server  # expose for WSGI deployment (gunicorn/waitress)

# Load data once at startup
APP_DATA = data.load_data()

# Pre-compute community map once (expensive)
_COMMUNITY_MAP = network_view.compute_communities(APP_DATA.graph)
_COMMUNITY_PALETTE = network_view.get_community_palette(
    max(_COMMUNITY_MAP.values(), default=0) + 1
)

app.layout = layout.build_layout(APP_DATA)


# ---------------------------------------------------------------------------
# Callback 1 — update all three visualisation tabs + cytoscape layout
# ---------------------------------------------------------------------------

@app.callback(
    Output("map-graph",        "figure"),
    Output("cytoscape-graph",  "elements"),
    Output("cytoscape-graph",  "stylesheet"),
    Output("timeline-graph",   "figure"),
    Input(ID_CONDUCTOR_DROPDOWN, "value"),
    Input(ID_SEASON_SLIDER,      "value"),
    Input(ID_EDGE_TYPE_RADIO,    "value"),
    Input("selected-node-store", "data"),
)
def update_visualisations(
    selected_conductors: list[str] | None,
    season_range: list[int] | None,
    edge_type: str | None,
    selected_node: str | None,
):
    edge_type = edge_type or "all"
    selected_conductors = selected_conductors or APP_DATA.conductors

    # Filter data
    filtered = data.filter_data(
        APP_DATA,
        conductor_ids=selected_conductors,
        season_range=season_range,
        edge_type_filter=edge_type,
    )

    # ── Map ────────────────────────────────────────────────────────────────
    map_fig = map_view.build_map_figure(
        nodes_df=filtered.nodes_df,
        edges_df=filtered.edges_df,
        selected_conductors=selected_conductors,
        edge_type_filter=edge_type,
    )

    # ── Cytoscape ─────────────────────────────────────────────────────────
    # Recompute communities on filtered subgraph or reuse global map
    community_map = {
        n: _COMMUNITY_MAP.get(n, 0)
        for n in filtered.nodes_df["node_id"].tolist()
    }
    cyto_elements = network_view.build_cytoscape_elements(
        nodes_df=filtered.nodes_df,
        edges_df=filtered.edges_df,
        community_map=community_map,
        centrality_df=APP_DATA.centrality_df,
        selected_conductor=selected_node,
    )

    # Apply ego-highlighting classes when a node is selected
    if selected_node:
        neighbor_ids = _get_ego_neighbours(filtered.graph, selected_node)
        cyto_elements = _apply_ego_classes(cyto_elements, selected_node, neighbor_ids)

    cyto_stylesheet = network_view.build_cytoscape_stylesheet(
        community_palette=_COMMUNITY_PALETTE,
        selected_conductor=selected_node,
    )

    # ── Timeline ──────────────────────────────────────────────────────────
    visible_seasons = _visible_seasons(season_range)
    timeline_fig = timeline_view.build_timeline_figure(
        graph=filtered.graph,
        conductor_ids=selected_conductors,
        conductor_labels=APP_DATA.conductor_labels,
        seasons=visible_seasons,
        edge_type_filter=edge_type,
    )

    return map_fig, cyto_elements, cyto_stylesheet, timeline_fig


# ---------------------------------------------------------------------------
# Callback 2 — cytoscape layout toggle
# ---------------------------------------------------------------------------

@app.callback(
    Output("cytoscape-graph", "layout"),
    Input(ID_LAYOUT_RADIO, "value"),
)
def update_cytoscape_layout(layout_name: str) -> dict:
    layout_name = layout_name or "cose"
    opts: dict = {"name": layout_name, "animate": True}
    if layout_name == "concentric":
        opts["concentric"] = "function(node){ return node.data('degree'); }"
        opts["levelWidth"] = "function(){ return 2; }"
    elif layout_name == "cose":
        opts["nodeOverlap"]     = 20
        opts["idealEdgeLength"] = 80
        opts["gravity"]         = 80
    return opts


# ---------------------------------------------------------------------------
# Callback 3 — profile card on node click
# ---------------------------------------------------------------------------

@app.callback(
    Output(ID_PROFILE_CONTAINER, "children"),
    Output("selected-node-store",  "data"),
    Input("cytoscape-graph", "tapNodeData"),
    Input("map-graph",        "clickData"),
    State(ID_CONDUCTOR_DROPDOWN, "value"),
    State(ID_SEASON_SLIDER,      "value"),
    prevent_initial_call=True,
)
def update_profile_card(
    cyto_tap: dict | None,
    map_click: dict | None,
    selected_conductors: list[str] | None,
    season_range: list[int] | None,
):
    """Triggered by clicking a node in either the map or network graph."""
    ctx = callback_context
    if not ctx.triggered:
        return conductor_profile.build_empty_profile_card(), None

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    conductor_id = None
    if trigger_id == "cytoscape-graph" and cyto_tap:
        if cyto_tap.get("node_type") == "conductor":
            conductor_id = cyto_tap["id"]
    elif trigger_id == "map-graph" and map_click:
        # Map click — try to extract conductor from hovertext
        pts = map_click.get("points", [])
        if pts:
            htext = pts[0].get("hovertext", "")
            # Match conductor node_ids from hovertext label
            for cid, label in APP_DATA.conductor_labels.items():
                if label in htext:
                    conductor_id = cid
                    break

    if not conductor_id:
        return conductor_profile.build_empty_profile_card(), None

    return _build_profile_for(conductor_id, selected_conductors, season_range), conductor_id


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_profile_for(
    conductor_id: str,
    selected_conductors: list[str] | None,
    season_range: list[int] | None,
) -> dash.development.base_component.Component:
    label = APP_DATA.conductor_labels.get(conductor_id, conductor_id)

    # Centrality
    cdf = APP_DATA.centrality_df
    crow_df = cdf[cdf["conductor"] == conductor_id]
    centrality_row = crow_df.iloc[0].to_dict() if not crow_df.empty else {
        "conductor": conductor_id, "degree": 0, "weighted_degree": 0.0,
        "betweenness": 0.0, "pagerank": 0.0,
    }

    # Seasons to show
    seasons = _visible_seasons(season_range)

    # Ego sizes
    try:
        ego_sizes = ego_network_size_over_time(APP_DATA.graph, conductor_id, seasons)
    except Exception:
        ego_sizes = {s: 0 for s in seasons}

    # Home share by season
    home_shares: dict[int, float | None] = {}
    for s in seasons:
        try:
            home_shares[s] = home_share_ratio(APP_DATA.graph, conductor_id, s)
        except Exception:
            home_shares[s] = None

    # Positions from edges
    positions = _get_conductor_positions(conductor_id)

    return conductor_profile.build_profile_card(
        conductor_id=conductor_id,
        label=label,
        centrality_row=centrality_row,
        ego_sizes=ego_sizes,
        positions=positions,
        home_share_by_season=home_shares,
    )


def _get_conductor_positions(conductor_id: str) -> list[dict]:
    perm = APP_DATA.edges_df[
        (APP_DATA.edges_df["source_id"] == conductor_id) &
        (APP_DATA.edges_df["edge_type"] == "permanent_position")
    ]
    positions = []
    for _, row in perm.iterrows():
        tgt_id = row["target_id"]
        orch_row = APP_DATA.nodes_df[APP_DATA.nodes_df["node_id"] == tgt_id]
        orch_label = orch_row.iloc[0]["label"] if not orch_row.empty else tgt_id
        end = row.get("end_year")
        positions.append({
            "orchestra":   orch_label,
            "role":        row.get("role", "Conductor"),
            "start_year":  row.get("start_year"),
            "end_year":    None if (end is None or str(end) in ("nan", "None")) else int(end),
            "is_current":  bool(row.get("is_current", False)) or end is None,
        })
    return positions


def _visible_seasons(season_range: list[int] | None) -> list[int]:
    if not season_range or len(season_range) < 2:
        return APP_DATA.seasons
    return [s for s in APP_DATA.seasons if season_range[0] <= s <= season_range[1]]


def _get_ego_neighbours(graph, conductor_id: str) -> set[str]:
    if conductor_id not in graph:
        return set()
    return set(graph.successors(conductor_id)) | set(graph.predecessors(conductor_id))


def _apply_ego_classes(
    elements: list[dict],
    selected_id: str,
    neighbour_ids: set[str],
) -> list[dict]:
    """Add 'dimmed' class to nodes/edges not in the ego network."""
    in_ego = neighbour_ids | {selected_id}
    result = []
    for el in elements:
        el = dict(el)
        el_data = el.get("data", {})
        if "source" in el_data:
            # Edge: dim if neither endpoint is in ego
            if el_data["source"] not in in_ego and el_data["target"] not in in_ego:
                el["classes"] = el.get("classes", "") + " dimmed"
        else:
            # Node: dim if not in ego
            if el_data.get("id") not in in_ego:
                existing = el.get("classes", "")
                el["classes"] = existing + " dimmed"
        result.append(el)
    return result


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)

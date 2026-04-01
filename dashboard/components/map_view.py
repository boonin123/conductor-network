"""
dashboard/components/map_view.py

Builds the geographic network map (Tab 1): orchestra nodes on a world
map with great-circle arc overlays per conductor-orchestra relationship.
Pure function — no Dash callbacks.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

_CONDUCTOR_PALETTE = px.colors.qualitative.Set1


def _conductor_color(conductor_id: str, conductor_ids: list[str]) -> str:
    idx = sorted(conductor_ids).index(conductor_id) if conductor_id in conductor_ids else 0
    return _CONDUCTOR_PALETTE[idx % len(_CONDUCTOR_PALETTE)]


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _node_coords(nodes_df: pd.DataFrame, node_id: str) -> tuple[float | None, float | None]:
    row = nodes_df[nodes_df["node_id"] == node_id]
    if row.empty:
        return None, None
    lat = row.iloc[0].get("lat")
    lon = row.iloc[0].get("lon")
    try:
        return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def _conductor_home_coords(
    conductor_id: str,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
) -> tuple[float | None, float | None]:
    """
    Return the lat/lon home for a conductor.
    Priority: conductor node's own lat/lon (if set) → primary permanent
    position orchestra's lat/lon → None.
    """
    lat, lon = _node_coords(nodes_df, conductor_id)
    if lat is not None:
        return lat, lon

    # Fall back to primary permanent position (most recent start_year)
    perm = edges_df[
        (edges_df["source_id"] == conductor_id) &
        (edges_df["edge_type"] == "permanent_position")
    ].copy()
    if perm.empty:
        return None, None

    perm = perm.sort_values("start_year", ascending=False)
    primary_orch = perm.iloc[0]["target_id"]
    return _node_coords(nodes_df, primary_orch)


# ---------------------------------------------------------------------------
# Arc traces (one trace per conductor, multi-line via None separators)
# ---------------------------------------------------------------------------

def _build_arc_traces(
    edges_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    conductor_ids: list[str],
    selected_conductors: list[str],
    edge_type_filter: str,
) -> list[go.Scattergeo]:
    traces = []

    permanent_types = {"permanent_position", "permanent_home"}
    guest_types     = {"guest_appearance"}

    for cid in conductor_ids:
        color      = _conductor_color(cid, conductor_ids)
        is_sel     = cid in selected_conductors
        opacity    = 0.75 if is_sel else 0.25
        label      = _get_label(nodes_df, cid)

        cond_edges = edges_df[edges_df["source_id"] == cid]

        lats_perm, lons_perm = [], []
        lats_guest, lons_guest = [], []
        hover_perm, hover_guest = [], []

        for _, erow in cond_edges.iterrows():
            etype = str(erow.get("edge_type", ""))
            tgt   = str(erow["target_id"])
            role  = str(erow.get("role", ""))
            count = erow.get("appearance_count")
            try:
                count_str = f"{int(count)}" if (count is not None and count == count) else "—"
            except (TypeError, ValueError):
                count_str = "—"

            src_lat, src_lon = _conductor_home_coords(cid, nodes_df, edges_df)
            tgt_lat, tgt_lon = _node_coords(nodes_df, tgt)

            if src_lat is None or tgt_lat is None:
                continue

            hover_txt = f"{label} → {_get_label(nodes_df, tgt)}<br>{role}<br>Appearances: {count_str}"
            arc = [src_lat, tgt_lat, None]
            arc_lon = [src_lon, tgt_lon, None]

            if etype in permanent_types:
                lats_perm  += arc
                lons_perm  += arc_lon
                hover_perm += [hover_txt, hover_txt, None]
            elif etype in guest_types:
                lats_guest  += arc
                lons_guest  += arc_lon
                hover_guest += [hover_txt, hover_txt, None]

        if lats_perm:
            traces.append(go.Scattergeo(
                lat=lats_perm, lon=lons_perm,
                mode="lines",
                line=dict(width=2, color=color),
                opacity=opacity,
                name=f"{label} (perm.)",
                legendgroup=cid,
                showlegend=is_sel,
                hoverinfo="text",
                hovertext=hover_perm,
            ))

        if lats_guest:
            traces.append(go.Scattergeo(
                lat=lats_guest, lon=lons_guest,
                mode="lines",
                line=dict(width=1.2, color=color, dash="dot"),
                opacity=opacity * 0.65,
                name=f"{label} (guest)",
                legendgroup=cid,
                showlegend=False,
                hoverinfo="text",
                hovertext=hover_guest,
            ))

    return traces


def _get_label(nodes_df: pd.DataFrame, node_id: str) -> str:
    row = nodes_df[nodes_df["node_id"] == node_id]
    return row.iloc[0]["label"] if not row.empty else node_id


# ---------------------------------------------------------------------------
# Orchestra node scatter
# ---------------------------------------------------------------------------

def _build_orchestra_scatter(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
) -> go.Scattergeo:
    orch_nodes = nodes_df[nodes_df["node_type"] == "orchestra"].copy()
    if orch_nodes.empty:
        return go.Scattergeo()

    # Count distinct conductors per orchestra
    orch_cond_counts = (
        edges_df[edges_df["edge_type"] == "permanent_position"]
        .groupby("target_id")["source_id"]
        .nunique()
        .to_dict()
    )

    lats, lons, sizes, colors, texts = [], [], [], [], []
    tier_colors = {"big5": "#1565C0", "regional": "#1976D2", "chamber": "#42A5F5"}

    for _, row in orch_nodes.iterrows():
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue

        oid    = str(row["node_id"])
        tier   = str(row.get("tier", ""))
        n_cond = orch_cond_counts.get(oid, 0)
        size   = 8 + 3 * math.log(n_cond + 1)
        color  = tier_colors.get(tier, "#78909C")

        lats.append(lat)
        lons.append(lon)
        sizes.append(size)
        colors.append(color)
        texts.append(
            f"<b>{row['label']}</b><br>{row.get('city','')}, {row.get('country','')}"
            f"<br>{n_cond} conductor{'s' if n_cond != 1 else ''}"
        )

    return go.Scattergeo(
        lat=lats, lon=lons,
        mode="markers",
        marker=dict(
            size=sizes, color=colors,
            symbol="circle",
            line=dict(width=1, color="white"),
        ),
        name="Orchestras",
        hoverinfo="text",
        hovertext=texts,
        showlegend=True,
    )


# ---------------------------------------------------------------------------
# Conductor home-city scatter
# ---------------------------------------------------------------------------

def _build_conductor_scatter(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    conductor_ids: list[str],
    selected_conductors: list[str],
) -> go.Scattergeo:
    lats, lons, texts, colors, sizes, symbols = [], [], [], [], [], []

    for cid in conductor_ids:
        lat, lon = _conductor_home_coords(cid, nodes_df, edges_df)
        if lat is None:
            continue

        is_sel = cid in selected_conductors
        label  = _get_label(nodes_df, cid)

        lats.append(lat)
        lons.append(lon)
        texts.append(f"<b>{label}</b>")
        colors.append("#E91E63" if is_sel else "#9C27B0")
        sizes.append(16 if is_sel else 10)
        symbols.append("diamond" if is_sel else "diamond-open")

    return go.Scattergeo(
        lat=lats, lon=lons,
        mode="markers",
        marker=dict(
            size=sizes, color=colors, symbol=symbols,
            line=dict(width=1.5, color="white"),
        ),
        name="Conductors",
        hoverinfo="text",
        hovertext=texts,
        showlegend=True,
    )


# ---------------------------------------------------------------------------
# Public figure builder
# ---------------------------------------------------------------------------

def build_map_figure(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    selected_conductors: list[str],
    edge_type_filter: str = "all",
) -> go.Figure:
    """
    Returns the full geographic network Scattergeo figure.
    """
    if nodes_df.empty:
        return _empty_map_figure()

    conductor_ids = nodes_df[nodes_df["node_type"] == "conductor"]["node_id"].tolist()
    if not conductor_ids:
        return _empty_map_figure()

    # Filter edges based on edge_type_filter
    from dashboard.data import EDGE_TYPE_GROUPS
    allowed = EDGE_TYPE_GROUPS.get(edge_type_filter, EDGE_TYPE_GROUPS["all"])
    edges_filtered = edges_df[edges_df["edge_type"].isin(allowed)]

    traces: list[go.BaseTraceType] = []
    traces += _build_arc_traces(
        edges_filtered, nodes_df,
        conductor_ids, selected_conductors, edge_type_filter,
    )
    traces.append(_build_orchestra_scatter(nodes_df, edges_df))
    traces.append(_build_conductor_scatter(nodes_df, edges_df, conductor_ids, selected_conductors))

    fig = go.Figure(data=traces)
    fig.update_layout(
        geo=dict(
            projection_type="natural earth",
            showland=True,       landcolor="#F5F5F5",
            showocean=True,      oceancolor="#E3F2FD",
            showcoastlines=True, coastlinecolor="#BDBDBD",
            showframe=False,
            bgcolor="rgba(0,0,0,0)",
            showlakes=True,      lakecolor="#E3F2FD",
        ),
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01,
            font=dict(size=10), bgcolor="rgba(255,255,255,0.7)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        height=560,
        uirevision="map",
    )
    return fig


def _empty_map_figure() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        geo=dict(
            projection_type="natural earth",
            showland=True, landcolor="#F5F5F5",
            showocean=True, oceancolor="#E3F2FD",
            showcoastlines=True, coastlinecolor="#BDBDBD",
        ),
        height=560,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(
            text="No data available for the current filter selection.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=13, color="#9E9E9E"),
        )],
    )
    return fig

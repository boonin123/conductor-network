"""
dashboard/components/timeline_view.py

Builds the temporal chart (Tab 3): stacked home vs guest appearances
per season with a home-share ratio overlay.
Pure function — no Dash callbacks.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

import networkx as nx

from network.metrics import home_share_ratio

# Qualitative color palette (one color per conductor)
_PALETTE = px.colors.qualitative.Set2


def _conductor_color(conductor_id: str, conductor_ids: list[str]) -> str:
    idx = sorted(conductor_ids).index(conductor_id) if conductor_id in conductor_ids else 0
    return _PALETTE[idx % len(_PALETTE)]


def _seasonal_counts(
    graph: nx.MultiDiGraph,
    conductor_id: str,
    seasons: list[int],
) -> tuple[dict[int, float], dict[int, float], dict[int, float | None]]:
    """
    Returns (home_counts, guest_counts, home_shares) for a conductor across seasons.
    """
    home_counts: dict[int, float]  = {}
    guest_counts: dict[int, float] = {}
    shares: dict[int, float | None] = {}

    for season in seasons:
        h, g = 0.0, 0.0
        if conductor_id in graph:
            for _, _, data in graph.out_edges(conductor_id, data=True):
                if data.get("season") != season:
                    continue
                count = float(data.get("appearance_count") or 1)
                if data.get("edge_type") == "permanent_home":
                    h += count
                elif data.get("edge_type") == "guest_appearance":
                    g += count
        home_counts[season]  = h
        guest_counts[season] = g
        shares[season] = home_share_ratio(graph, conductor_id, season) if conductor_id in graph else None

    return home_counts, guest_counts, shares


def build_timeline_figure(
    graph: nx.MultiDiGraph,
    conductor_ids: list[str],
    conductor_labels: dict[str, str],
    seasons: list[int],
    edge_type_filter: str = "all",
) -> go.Figure:
    """
    Two stacked subplots:
      Top (70%):  Grouped+stacked bar — home (solid) and guest (hatched) appearances
      Bottom (30%): Line — home share ratio per season per conductor
    """
    if not conductor_ids or not seasons:
        return _empty_figure("Select conductors and a season range to view the timeline.")

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.70, 0.30],
        vertical_spacing=0.06,
        subplot_titles=["Appearances per Season", "Home Share Ratio"],
    )

    x_labels = [f"'{str(s)[-2:]}" for s in seasons]

    for cid in conductor_ids:
        label  = conductor_labels.get(cid, cid)
        color  = _conductor_color(cid, conductor_ids)
        home_c, guest_c, shares = _seasonal_counts(graph, cid, seasons)

        home_vals  = [home_c.get(s, 0)  for s in seasons]
        guest_vals = [guest_c.get(s, 0) for s in seasons]
        share_vals = [shares.get(s)      for s in seasons]
        share_clean = [v if v is not None else float("nan") for v in share_vals]

        # Home appearances bar (full opacity)
        fig.add_trace(go.Bar(
            name=f"{label} · home",
            x=x_labels,
            y=home_vals,
            offsetgroup=cid,
            marker_color=color,
            marker_opacity=0.9,
            legendgroup=cid,
            hovertemplate=f"<b>{label}</b><br>Season: %{{x}}<br>Home: %{{y:.0f}}<extra></extra>",
        ), row=1, col=1)

        # Guest appearances bar (lower opacity, same color)
        fig.add_trace(go.Bar(
            name=f"{label} · guest",
            x=x_labels,
            y=guest_vals,
            offsetgroup=cid,
            base=home_vals,
            marker_color=color,
            marker_opacity=0.35,
            legendgroup=cid,
            showlegend=False,
            hovertemplate=f"<b>{label}</b><br>Season: %{{x}}<br>Guest: %{{y:.0f}}<extra></extra>",
        ), row=1, col=1)

        # Home share ratio line
        fig.add_trace(go.Scatter(
            name=label,
            x=x_labels,
            y=share_clean,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5),
            legendgroup=cid,
            showlegend=False,
            hovertemplate=f"<b>{label}</b><br>Season: %{{x}}<br>Home share: %{{y:.1%}}<extra></extra>",
            connectgaps=False,
        ), row=2, col=1)

    # Reference line at 50% in ratio subplot
    fig.add_hline(
        y=0.5, row=2, col=1,
        line_dash="dot", line_color="#9E9E9E", line_width=1,
        annotation_text="50%",
        annotation_position="right",
        annotation_font_size=10,
    )

    fig.update_layout(
        barmode="group",
        bargap=0.15,
        bargroupgap=0.05,
        height=480,
        margin=dict(l=40, r=40, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FAFAFA",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            font=dict(size=11),
        ),
        uirevision="timeline",
        hovermode="x unified",
    )

    fig.update_yaxes(title_text="Appearances", row=1, col=1, gridcolor="#EEEEEE")
    fig.update_yaxes(
        title_text="Home share", row=2, col=1,
        range=[0, 1], tickformat=".0%",
        gridcolor="#EEEEEE",
    )
    fig.update_xaxes(showgrid=False)

    return fig


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=13, color="#9E9E9E"),
    )
    fig.update_layout(
        height=480, margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig

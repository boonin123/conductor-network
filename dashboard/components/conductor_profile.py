"""
dashboard/components/conductor_profile.py

Builds the conductor profile card shown in the left panel when a
conductor node is clicked. Pure functions — no Dash callbacks.
"""

from __future__ import annotations

import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_profile_card(
    conductor_id: str,
    label: str,
    centrality_row: dict,
    ego_sizes: dict[int, int],
    positions: list[dict],
    home_share_by_season: dict[int, float | None],
) -> dbc.Card:
    """
    Returns a styled profile card.

    centrality_row: {"conductor": id, "degree": int, "weighted_degree": float,
                     "betweenness": float, "pagerank": float}
    positions:      [{"orchestra": str, "role": str, "start_year": int,
                      "end_year": int|None, "is_current": bool}]
    """
    degree        = int(centrality_row.get("degree", 0))
    w_degree      = float(centrality_row.get("weighted_degree", 0.0))
    betweenness   = float(centrality_row.get("betweenness", 0.0))
    pagerank      = float(centrality_row.get("pagerank", 0.0))

    return dbc.Card([
        dbc.CardHeader(
            html.Strong(label, className="card-title"),
            className="py-2",
        ),
        dbc.CardBody([

            # ── Centrality badges ────────────────────────────────────────
            html.Div([
                _metric_badge("Degree",       str(degree),             "primary"),
                _metric_badge("Appearances",  f"{w_degree:.0f}",       "success"),
                _metric_badge("Betweenness",  f"{betweenness:.4f}",    "warning"),
                _metric_badge("PageRank",     f"{pagerank:.4f}",       "info"),
            ], className="mb-3 d-flex flex-wrap gap-1"),

            # ── Positions ────────────────────────────────────────────────
            html.P("Positions", className="fw-semibold small mb-1"),
            _build_positions_list(positions),

            # ── Career sparkline ─────────────────────────────────────────
            html.P("Career overview", className="fw-semibold small mt-3 mb-1"),
            dcc.Graph(
                figure=_build_sparkline(ego_sizes, home_share_by_season),
                config={"displayModeBar": False, "staticPlot": True},
                style={"height": "110px"},
            ),

        ]),
    ], className="profile-card shadow-sm")


def build_empty_profile_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            html.P(
                "Click a conductor node to see their profile",
                className="text-muted fst-italic small text-center mb-0",
            )
        ),
        className="shadow-sm",
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _metric_badge(label: str, value: str, color: str) -> html.Span:
    return html.Span([
        html.Small(label + ": ", className="text-muted"),
        dbc.Badge(value, color=color, className="metric-badge"),
    ], className="me-1")


def _build_positions_list(positions: list[dict]) -> dbc.ListGroup:
    if not positions:
        return html.P("No positions on record", className="text-muted small")

    items = []
    for pos in sorted(positions, key=lambda p: -(p.get("start_year") or 0)):
        start  = pos.get("start_year") or "?"
        end    = "present" if pos.get("is_current") or pos.get("end_year") is None else pos["end_year"]
        role   = pos.get("role", "Conductor")
        orch   = pos.get("orchestra", "")
        items.append(
            dbc.ListGroupItem([
                html.Div(orch, className="fw-semibold small"),
                html.Div(f"{role} · {start}–{end}", className="text-muted small"),
            ], className="py-1 px-2 border-0 border-bottom")
        )
    return dbc.ListGroup(items, flush=True, className="small")


def _build_sparkline(
    ego_sizes: dict[int, int],
    home_share_by_season: dict[int, float | None],
) -> go.Figure:
    """
    Mini two-trace figure: bar for ego network size, line for home share.
    """
    seasons = sorted(set(ego_sizes.keys()) | set(home_share_by_season.keys()))
    if not seasons:
        return go.Figure()

    sizes  = [ego_sizes.get(s, 0) for s in seasons]
    shares = [home_share_by_season.get(s) for s in seasons]
    # Replace None with NaN for proper gap rendering
    shares_clean = [s if s is not None else float("nan") for s in shares]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=seasons, y=sizes,
        name="Orchestras",
        marker_color="#90CAF9",
        yaxis="y",
        hovertemplate="%{x}: %{y} orchestras<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=seasons, y=shares_clean,
        name="Home share",
        mode="lines+markers",
        line=dict(color="#E91E63", width=1.5),
        marker=dict(size=4),
        yaxis="y2",
        hovertemplate="%{x}: %{y:.0%}<extra></extra>",
    ))

    fig.update_layout(
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis2=dict(
            overlaying="y", side="right",
            range=[0, 1], showticklabels=False,
            showgrid=False, zeroline=False,
        ),
        xaxis=dict(showgrid=False, tickfont=dict(size=9)),
        margin=dict(l=0, r=0, t=4, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        height=110,
        barmode="group",
    )
    return fig

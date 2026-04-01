"""
dashboard/components/filters.py

Left-panel filter controls. Pure layout — no callbacks.
All component IDs are declared here as constants so app.py can
import them rather than hard-coding strings.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

# ---------------------------------------------------------------------------
# Component ID constants (imported by app.py to wire callbacks)
# ---------------------------------------------------------------------------
ID_CONDUCTOR_DROPDOWN  = "conductor-dropdown"
ID_SEASON_SLIDER       = "season-slider"
ID_EDGE_TYPE_RADIO     = "edge-type-radio"
ID_LAYOUT_RADIO        = "cytoscape-layout-radio"
ID_PROFILE_CONTAINER   = "profile-card-container"


def build_filters_panel(
    conductor_options: list[dict],
    season_min: int,
    season_max: int,
    default_conductors: list[str],
) -> html.Div:
    """
    Returns the sticky left panel containing filter controls and
    a placeholder for the conductor profile card.

    conductor_options: [{"label": "Andris Nelsons", "value": "andris_nelsons"}, ...]
    """

    # Slider marks: show every year, but only label every 2 to avoid crowding
    slider_marks = {
        y: {"label": str(y), "style": {"fontSize": "11px"}}
        for y in range(season_min, season_max + 1)
        if y % 2 == 0 or y in (season_min, season_max)
    }

    return html.Div(
        className="filters-panel",
        children=[
            # ── Filter card ─────────────────────────────────────────────────
            dbc.Card([
                dbc.CardHeader(
                    html.Strong("Filters"),
                    className="py-2",
                ),
                dbc.CardBody([
                    # Conductor selector
                    html.Label("Conductors", className="fw-semibold small mb-1"),
                    dcc.Dropdown(
                        id=ID_CONDUCTOR_DROPDOWN,
                        options=conductor_options,
                        value=default_conductors,
                        multi=True,
                        placeholder="Select conductors…",
                        clearable=True,
                        className="mb-3",
                    ),

                    # Season range slider
                    html.Label("Season Range", className="fw-semibold small mb-1"),
                    dcc.RangeSlider(
                        id=ID_SEASON_SLIDER,
                        min=season_min,
                        max=season_max,
                        step=1,
                        value=[season_min, season_max],
                        marks=slider_marks,
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="mb-3",
                    ),

                    # Edge type
                    html.Label("Edge Type", className="fw-semibold small mb-1"),
                    dbc.RadioItems(
                        id=ID_EDGE_TYPE_RADIO,
                        options=[
                            {"label": "All connections",     "value": "all"},
                            {"label": "Permanent positions", "value": "permanent"},
                            {"label": "Guest appearances",   "value": "guest"},
                        ],
                        value="all",
                        inline=False,
                        className="mb-3",
                    ),

                    # Network layout selector (only relevant for Tab 2)
                    html.Label("Network Layout", className="fw-semibold small mb-1"),
                    dbc.RadioItems(
                        id=ID_LAYOUT_RADIO,
                        options=[
                            {"label": "Force-directed",  "value": "cose"},
                            {"label": "Concentric",      "value": "concentric"},
                            {"label": "Breadth-first",   "value": "breadthfirst"},
                        ],
                        value="cose",
                        inline=False,
                        className="mb-0",
                    ),
                ]),
            ], className="mb-3 shadow-sm"),

            # ── Profile card container ────────────────────────────────────
            html.Div(
                id=ID_PROFILE_CONTAINER,
                children=_empty_profile_hint(),
            ),
        ],
    )


def _empty_profile_hint() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            html.P(
                "Click a conductor node to see their profile",
                className="text-muted fst-italic small text-center mb-0",
            )
        ),
        className="shadow-sm",
    )

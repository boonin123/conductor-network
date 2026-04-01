"""
dashboard/layout.py

Assembles the full two-panel app layout from components.
Called once at startup; sets app.layout.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import dcc, html

from dashboard.data import AppData
from dashboard.components.filters import build_filters_panel
from dashboard.components.network_view import build_cytoscape_stylesheet


def build_layout(app_data: AppData) -> dbc.Container:
    conductor_options = [
        {"label": app_data.conductor_labels[cid], "value": cid}
        for cid in app_data.conductors
    ]
    season_min = app_data.seasons[0]  if app_data.seasons else 2013
    season_max = app_data.seasons[-1] if app_data.seasons else 2024

    # All conductors selected by default
    default_conductors = app_data.conductors[:]

    return dbc.Container(
        fluid=True,
        className="px-3 py-2",
        children=[

            # ── Header ────────────────────────────────────────────────────
            dbc.Row(
                dbc.Col([
                    html.H4(
                        "Conductor Network · Andris Nelsons & Peers",
                        className="mb-0 fw-bold text-primary",
                    ),
                    html.Small(
                        "Investigating the 'stretched thin' claim through network science",
                        className="text-muted",
                    ),
                    dbc.Alert(
                        "Showing sample data — run the scraping pipeline to load real data.",
                        id="sample-data-alert",
                        color="warning",
                        is_open=app_data.is_sample,
                        dismissable=True,
                        className="sample-data-alert mt-1 mb-0 py-1 px-2",
                    ),
                ]),
                className="mb-2 pt-2 border-bottom",
            ),

            # ── Main two-panel row ────────────────────────────────────────
            dbc.Row([

                # Left panel — filters + profile card
                dbc.Col(
                    build_filters_panel(
                        conductor_options=conductor_options,
                        season_min=season_min,
                        season_max=season_max,
                        default_conductors=default_conductors,
                    ),
                    width=4,
                    className="pe-2",
                ),

                # Right panel — tabs
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Tabs(
                                id="main-tabs",
                                active_tab="tab-map",
                                children=[

                                    # Tab 1 — Geographic Map
                                    dbc.Tab(
                                        label="Geographic Map",
                                        tab_id="tab-map",
                                        children=dcc.Graph(
                                            id="map-graph",
                                            config={
                                                "displayModeBar": True,
                                                "modeBarButtonsToRemove": [
                                                    "select2d", "lasso2d",
                                                ],
                                            },
                                            style={"height": "560px"},
                                        ),
                                    ),

                                    # Tab 2 — Network Graph
                                    dbc.Tab(
                                        label="Network Graph",
                                        tab_id="tab-network",
                                        children=cyto.Cytoscape(
                                            id="cytoscape-graph",
                                            layout={"name": "cose"},
                                            style={
                                                "width": "100%",
                                                "height": "560px",
                                                "border": "1px solid #E0E0E0",
                                                "borderRadius": "4px",
                                            },
                                            elements=[],
                                            stylesheet=build_cytoscape_stylesheet(),
                                            responsive=True,
                                            minZoom=0.15,
                                            maxZoom=4.0,
                                        ),
                                    ),

                                    # Tab 3 — Temporal Chart
                                    dbc.Tab(
                                        label="Temporal Chart",
                                        tab_id="tab-timeline",
                                        children=dcc.Graph(
                                            id="timeline-graph",
                                            config={"displayModeBar": False},
                                            style={"height": "480px"},
                                        ),
                                    ),

                                ],
                            ),
                        ], className="p-2"),
                    ], className="shadow-sm"),
                    width=8,
                    className="ps-0",
                ),

            ], className="gx-2"),

            # ── Hidden stores ─────────────────────────────────────────────
            dcc.Store(id="selected-node-store", storage_type="memory"),
        ],
    )

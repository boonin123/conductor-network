"""
test_metrics.py

Tests for network/metrics.py — custom metric computations on the
conductor-orchestra graph.

All tests use small, hand-crafted graphs so expected values can be
computed analytically and verified without running the full pipeline.

Run:
    pytest tests/test_metrics.py -v
"""

import math
import networkx as nx
import pytest

try:
    from network.metrics import (
        degree_by_edge_type,
        home_share_ratio,
        geographic_dispersion,
        transatlantic_transitions,
        conductor_centrality_table,
        ego_network_size_over_time,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not METRICS_AVAILABLE,
    reason="network.metrics not yet implemented",
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_graph() -> nx.MultiDiGraph:
    """
    Minimal graph with 2 conductors and 3 orchestras.

    Nelsons:
      - permanent_position @ BSO (2014–present)
      - permanent_position @ Leipzig (2018–present)
      - guest_appearance @ LAPhil, season 2022, count=3
      - permanent_home @ BSO, season 2022, count=12
      - permanent_home @ Leipzig, season 2022, count=8

    Dudamel:
      - permanent_position @ LAPhil (2009–present)
      - permanent_home @ LAPhil, season 2022, count=22
    """
    g = nx.MultiDiGraph()

    # Nodes
    g.add_node("andris_nelsons",             node_type="conductor", label="Andris Nelsons")
    g.add_node("gustavo_dudamel",            node_type="conductor", label="Gustavo Dudamel")
    g.add_node("boston_symphony_orchestra",  node_type="orchestra", label="Boston Symphony Orchestra",
               lat=42.34, lon=-71.09, city="Boston", country="United States")
    g.add_node("gewandhaus_orchestra",       node_type="orchestra", label="Gewandhaus Orchestra Leipzig",
               lat=51.34, lon=12.38,  city="Leipzig", country="Germany")
    g.add_node("los_angeles_philharmonic",   node_type="orchestra", label="Los Angeles Philharmonic",
               lat=34.06, lon=-118.10, city="Los Angeles", country="United States")

    # Nelsons permanent positions
    g.add_edge("andris_nelsons", "boston_symphony_orchestra",
               edge_type="permanent_position", role="Music Director",
               start_year=2014, end_year=None, season=None, appearance_count=None)
    g.add_edge("andris_nelsons", "gewandhaus_orchestra",
               edge_type="permanent_position", role="Chief Conductor",
               start_year=2018, end_year=None, season=None, appearance_count=None)

    # Nelsons season 2022
    g.add_edge("andris_nelsons", "boston_symphony_orchestra",
               edge_type="permanent_home", role="Music Director",
               start_year=2022, end_year=2022, season=2022, appearance_count=12)
    g.add_edge("andris_nelsons", "gewandhaus_orchestra",
               edge_type="permanent_home", role="Chief Conductor",
               start_year=2022, end_year=2022, season=2022, appearance_count=8)
    g.add_edge("andris_nelsons", "los_angeles_philharmonic",
               edge_type="guest_appearance", role="Guest Conductor",
               start_year=2022, end_year=2022, season=2022, appearance_count=3)

    # Dudamel permanent position
    g.add_edge("gustavo_dudamel", "los_angeles_philharmonic",
               edge_type="permanent_position", role="Music Director",
               start_year=2009, end_year=None, season=None, appearance_count=None)
    g.add_edge("gustavo_dudamel", "los_angeles_philharmonic",
               edge_type="permanent_home", role="Music Director",
               start_year=2022, end_year=2022, season=2022, appearance_count=22)

    return g


@pytest.fixture
def graph():
    return _make_graph()


# ---------------------------------------------------------------------------
# degree_by_edge_type
# ---------------------------------------------------------------------------

class TestDegreeByEdgeType:
    """
    degree_by_edge_type(graph, conductor_id) -> dict
    Returns counts of edges broken down by edge_type for a given conductor.
    e.g. {"permanent_position": 2, "guest_appearance": 1, "permanent_home": 2}
    """

    def test_nelsons_permanent_positions(self, graph):
        result = degree_by_edge_type(graph, "andris_nelsons")
        assert result.get("permanent_position", 0) == 2

    def test_nelsons_guest_appearances(self, graph):
        result = degree_by_edge_type(graph, "andris_nelsons")
        assert result.get("guest_appearance", 0) == 1

    def test_dudamel_one_permanent_position(self, graph):
        result = degree_by_edge_type(graph, "gustavo_dudamel")
        assert result.get("permanent_position", 0) == 1

    def test_returns_dict(self, graph):
        result = degree_by_edge_type(graph, "andris_nelsons")
        assert isinstance(result, dict)

    def test_raises_for_unknown_conductor(self, graph):
        with pytest.raises((KeyError, ValueError)):
            degree_by_edge_type(graph, "nonexistent_conductor")


# ---------------------------------------------------------------------------
# home_share_ratio
# ---------------------------------------------------------------------------

class TestHomeShareRatio:
    """
    home_share_ratio(graph, conductor_id, season) -> float
    = home_appearances / total_appearances for that season (0.0 – 1.0).
    Nelsons 2022: home=12+8=20, guest=3, total=23 -> 20/23 ≈ 0.8696
    Dudamel 2022: home=22, guest=0, total=22 -> 1.0
    """

    def test_nelsons_2022(self, graph):
        ratio = home_share_ratio(graph, "andris_nelsons", 2022)
        assert ratio == pytest.approx(20 / 23, abs=0.001)

    def test_dudamel_2022_all_home(self, graph):
        ratio = home_share_ratio(graph, "gustavo_dudamel", 2022)
        assert ratio == pytest.approx(1.0, abs=0.001)

    def test_range_is_0_to_1(self, graph):
        ratio = home_share_ratio(graph, "andris_nelsons", 2022)
        assert 0.0 <= ratio <= 1.0

    def test_returns_none_for_season_with_no_data(self, graph):
        result = home_share_ratio(graph, "andris_nelsons", 1990)
        assert result is None or math.isnan(result)

    def test_returns_float(self, graph):
        ratio = home_share_ratio(graph, "andris_nelsons", 2022)
        assert isinstance(ratio, float)


# ---------------------------------------------------------------------------
# geographic_dispersion
# ---------------------------------------------------------------------------

class TestGeographicDispersion:
    """
    geographic_dispersion(graph, conductor_id, season) -> float
    Returns the mean pairwise great-circle distance (km) between all venues
    visited by the conductor in the given season, weighted by appearance_count.
    A higher score means more geographically scattered activity.
    """

    def test_nelsons_dispersed_across_continents(self, graph):
        # Nelsons visits Boston, Leipzig, and LA in 2022 — large dispersion
        dispersion = geographic_dispersion(graph, "andris_nelsons", 2022)
        assert dispersion > 1000, f"Expected > 1000km dispersion, got {dispersion:.1f}"

    def test_dudamel_single_venue_zero_dispersion(self, graph):
        # Dudamel only at LA in 2022 — zero or near-zero dispersion
        dispersion = geographic_dispersion(graph, "gustavo_dudamel", 2022)
        assert dispersion == pytest.approx(0.0, abs=1.0)

    def test_returns_non_negative_float(self, graph):
        dispersion = geographic_dispersion(graph, "andris_nelsons", 2022)
        assert isinstance(dispersion, float)
        assert dispersion >= 0.0

    def test_returns_none_for_missing_season(self, graph):
        result = geographic_dispersion(graph, "andris_nelsons", 1990)
        assert result is None or result == 0.0

    def test_nelsons_greater_than_dudamel(self, graph):
        d_nelsons = geographic_dispersion(graph, "andris_nelsons", 2022)
        d_dudamel = geographic_dispersion(graph, "gustavo_dudamel", 2022)
        assert d_nelsons > d_dudamel


# ---------------------------------------------------------------------------
# transatlantic_transitions
# ---------------------------------------------------------------------------

class TestTransatlanticTransitions:
    """
    transatlantic_transitions(graph, conductor_id, season) -> int
    Counts the number of times a conductor crossed the Atlantic (between
    North America and Europe) in a given season, inferred from the sequence
    of appearances. Uses a longitude threshold (~-30°W) to classify continent.
    """

    def test_nelsons_has_transitions(self, graph):
        # Nelsons appears in Boston (Americas) and Leipzig (Europe) in 2022
        transitions = transatlantic_transitions(graph, "andris_nelsons", 2022)
        assert transitions >= 1, f"Expected >= 1 transitions, got {transitions}"

    def test_dudamel_no_transitions(self, graph):
        # Dudamel only in LA — no transatlantic movement
        transitions = transatlantic_transitions(graph, "gustavo_dudamel", 2022)
        assert transitions == 0

    def test_returns_non_negative_int(self, graph):
        transitions = transatlantic_transitions(graph, "andris_nelsons", 2022)
        assert isinstance(transitions, int)
        assert transitions >= 0

    def test_returns_zero_for_missing_season(self, graph):
        transitions = transatlantic_transitions(graph, "andris_nelsons", 1990)
        assert transitions == 0


# ---------------------------------------------------------------------------
# conductor_centrality_table
# ---------------------------------------------------------------------------

class TestConductorCentralityTable:
    """
    conductor_centrality_table(graph) -> pd.DataFrame
    Returns one row per conductor with columns:
      conductor, degree, weighted_degree, betweenness, pagerank
    """

    def test_returns_dataframe(self, graph):
        import pandas as pd
        result = conductor_centrality_table(graph)
        assert isinstance(result, pd.DataFrame)

    def test_one_row_per_conductor(self, graph):
        result = conductor_centrality_table(graph)
        conductors = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "conductor"]
        assert len(result) == len(conductors)

    def test_required_columns(self, graph):
        result = conductor_centrality_table(graph)
        for col in ["conductor", "degree", "weighted_degree", "betweenness", "pagerank"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_nelsons_higher_degree_than_dudamel(self, graph):
        result = conductor_centrality_table(graph)
        nelsons_row = result[result["conductor"] == "andris_nelsons"].iloc[0]
        dudamel_row = result[result["conductor"] == "gustavo_dudamel"].iloc[0]
        assert nelsons_row["degree"] > dudamel_row["degree"], \
            "Nelsons should have higher degree (more orchestral connections)"

    def test_centrality_values_are_non_negative(self, graph):
        result = conductor_centrality_table(graph)
        for col in ["degree", "weighted_degree", "betweenness", "pagerank"]:
            assert (result[col] >= 0).all(), f"Negative values in {col}"

    def test_pagerank_sums_to_approximately_one(self, graph):
        result = conductor_centrality_table(graph)
        # PageRank sums to 1 over all nodes; conductor-only subset will be < 1
        total = result["pagerank"].sum()
        assert 0 < total <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# ego_network_size_over_time
# ---------------------------------------------------------------------------

class TestEgoNetworkSizeOverTime:
    """
    ego_network_size_over_time(graph, conductor_id, seasons) -> dict[int, int]
    Returns {season: number_of_distinct_orchestras} for each season.
    """

    def test_returns_dict(self, graph):
        result = ego_network_size_over_time(graph, "andris_nelsons", [2020, 2021, 2022])
        assert isinstance(result, dict)

    def test_seasons_are_keys(self, graph):
        seasons = [2020, 2021, 2022]
        result = ego_network_size_over_time(graph, "andris_nelsons", seasons)
        for s in seasons:
            assert s in result

    def test_2022_includes_guest_orchestra(self, graph):
        result = ego_network_size_over_time(graph, "andris_nelsons", [2022])
        # In 2022 Nelsons has: BSO (home) + Leipzig (home) + LAPhil (guest) = 3
        assert result[2022] >= 3

    def test_values_are_non_negative_ints(self, graph):
        result = ego_network_size_over_time(graph, "andris_nelsons", [2022])
        for season, count in result.items():
            assert isinstance(count, int)
            assert count >= 0

    def test_empty_season_list_returns_empty_dict(self, graph):
        result = ego_network_size_over_time(graph, "andris_nelsons", [])
        assert result == {}

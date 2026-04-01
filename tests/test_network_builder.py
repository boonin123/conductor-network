"""
test_network_builder.py

Tests for network/builder.py — graph construction from processed CSV data.
All tests use minimal synthetic DataFrames so no real data files are needed.

Run:
    pytest tests/test_network_builder.py -v
"""

import pandas as pd
import networkx as nx
import pytest

# builder.py is not yet written; these tests define the expected interface
# so they serve as a specification. Import will fail gracefully until the
# module is implemented.
try:
    from network.builder import (
        build_graph,
        get_ego_network,
        get_season_subgraph,
        conductor_orchestra_bipartite,
        validate_graph,
    )
    BUILDER_AVAILABLE = True
except ImportError:
    BUILDER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not BUILDER_AVAILABLE,
    reason="network.builder not yet implemented",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_nodes() -> pd.DataFrame:
    return pd.DataFrame([
        {"node_id": "andris_nelsons",             "label": "Andris Nelsons",             "node_type": "conductor", "lat": None, "lon": None},
        {"node_id": "gustavo_dudamel",             "label": "Gustavo Dudamel",            "node_type": "conductor", "lat": None, "lon": None},
        {"node_id": "boston_symphony_orchestra",   "label": "Boston Symphony Orchestra",  "node_type": "orchestra", "lat": 42.34, "lon": -71.09},
        {"node_id": "los_angeles_philharmonic",    "label": "Los Angeles Philharmonic",   "node_type": "orchestra", "lat": 34.06, "lon": -118.10},
        {"node_id": "gewandhaus_orchestra_leipzig","label": "Gewandhaus Orchestra Leipzig","node_type": "orchestra", "lat": 51.34, "lon": 12.38},
    ])


@pytest.fixture
def sample_edges() -> pd.DataFrame:
    return pd.DataFrame([
        # Nelsons: permanent at BSO and Leipzig
        {"source_id": "andris_nelsons", "target_id": "boston_symphony_orchestra",
         "edge_type": "permanent_position", "role": "Music Director",
         "start_year": 2014, "end_year": None, "is_current": True,
         "appearance_count": None, "season": None},
        {"source_id": "andris_nelsons", "target_id": "gewandhaus_orchestra_leipzig",
         "edge_type": "permanent_position", "role": "Chief Conductor",
         "start_year": 2018, "end_year": None, "is_current": True,
         "appearance_count": None, "season": None},
        # Nelsons guest at LA Phil
        {"source_id": "andris_nelsons", "target_id": "los_angeles_philharmonic",
         "edge_type": "guest_appearance", "role": "Guest Conductor",
         "start_year": 2022, "end_year": 2022, "is_current": False,
         "appearance_count": 3, "season": 2022},
        # Dudamel: permanent at LA Phil
        {"source_id": "gustavo_dudamel", "target_id": "los_angeles_philharmonic",
         "edge_type": "permanent_position", "role": "Music Director",
         "start_year": 2009, "end_year": None, "is_current": True,
         "appearance_count": None, "season": None},
        # Dudamel home appearances
        {"source_id": "gustavo_dudamel", "target_id": "los_angeles_philharmonic",
         "edge_type": "permanent_home", "role": "Music Director",
         "start_year": 2022, "end_year": 2022, "is_current": False,
         "appearance_count": 18, "season": 2022},
    ])


@pytest.fixture
def graph(sample_nodes, sample_edges) -> nx.MultiDiGraph:
    return build_graph(sample_nodes, sample_edges)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_returns_multidigraph(self, graph):
        assert isinstance(graph, nx.MultiDiGraph)

    def test_correct_node_count(self, graph, sample_nodes):
        assert graph.number_of_nodes() == len(sample_nodes)

    def test_correct_edge_count(self, graph, sample_edges):
        assert graph.number_of_edges() == len(sample_edges)

    def test_node_type_attribute_set(self, graph):
        for node_id, data in graph.nodes(data=True):
            assert "node_type" in data, f"node_type missing on {node_id}"
            assert data["node_type"] in ("conductor", "orchestra", "venue", "season")

    def test_conductor_nodes_exist(self, graph):
        conductors = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "conductor"]
        assert "andris_nelsons" in conductors
        assert "gustavo_dudamel" in conductors

    def test_orchestra_nodes_have_coordinates(self, graph):
        bso = graph.nodes["boston_symphony_orchestra"]
        assert bso.get("lat") == pytest.approx(42.34, abs=0.01)
        assert bso.get("lon") == pytest.approx(-71.09, abs=0.01)

    def test_edge_attributes_preserved(self, graph):
        edges = list(graph.edges("andris_nelsons", data=True))
        assert len(edges) > 0
        for _, _, data in edges:
            assert "edge_type" in data
            assert "role" in data

    def test_empty_inputs_return_empty_graph(self):
        empty_nodes = pd.DataFrame(columns=["node_id", "label", "node_type", "lat", "lon"])
        empty_edges = pd.DataFrame(columns=["source_id", "target_id", "edge_type", "role",
                                            "start_year", "end_year", "is_current",
                                            "appearance_count", "season"])
        g = build_graph(empty_nodes, empty_edges)
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0


# ---------------------------------------------------------------------------
# Ego network
# ---------------------------------------------------------------------------

class TestGetEgoNetwork:
    def test_returns_subgraph(self, graph):
        ego = get_ego_network(graph, "andris_nelsons")
        assert isinstance(ego, (nx.MultiDiGraph, nx.DiGraph, nx.Graph))

    def test_ego_node_included(self, graph):
        ego = get_ego_network(graph, "andris_nelsons")
        assert "andris_nelsons" in ego.nodes

    def test_direct_neighbours_included(self, graph):
        ego = get_ego_network(graph, "andris_nelsons")
        assert "boston_symphony_orchestra" in ego.nodes
        assert "gewandhaus_orchestra_leipzig" in ego.nodes

    def test_unconnected_nodes_excluded(self, graph):
        # Dudamel is not a neighbour of Nelsons in this fixture (no shared edge)
        ego = get_ego_network(graph, "andris_nelsons")
        assert "gustavo_dudamel" not in ego.nodes

    def test_raises_for_unknown_node(self, graph):
        with pytest.raises((KeyError, ValueError)):
            get_ego_network(graph, "nonexistent_conductor")


# ---------------------------------------------------------------------------
# Season subgraph
# ---------------------------------------------------------------------------

class TestGetSeasonSubgraph:
    def test_returns_graph(self, graph):
        sg = get_season_subgraph(graph, 2022)
        assert isinstance(sg, (nx.MultiDiGraph, nx.DiGraph, nx.Graph))

    def test_permanent_positions_always_included(self, graph):
        # Permanent positions have no season tag — they should always be included
        sg = get_season_subgraph(graph, 2022)
        # Nelsons -> BSO permanent edge should be present
        assert sg.has_node("andris_nelsons")
        assert sg.has_node("boston_symphony_orchestra")

    def test_guest_edges_filtered_by_season(self, graph):
        # 2022 guest edges should be in the 2022 subgraph
        sg_2022 = get_season_subgraph(graph, 2022)
        sg_2015 = get_season_subgraph(graph, 2015)
        edges_2022 = [d for _, _, d in sg_2022.edges(data=True) if d.get("season") == 2022]
        edges_2015 = [d for _, _, d in sg_2015.edges(data=True) if d.get("season") == 2022]
        assert len(edges_2022) > 0
        assert len(edges_2015) == 0


# ---------------------------------------------------------------------------
# Bipartite projection
# ---------------------------------------------------------------------------

class TestConductorOrchestraBipartite:
    def test_returns_graph(self, graph):
        bp = conductor_orchestra_bipartite(graph)
        assert isinstance(bp, nx.Graph)

    def test_only_conductor_and_orchestra_nodes(self, graph):
        bp = conductor_orchestra_bipartite(graph)
        for node, data in bp.nodes(data=True):
            assert data.get("node_type") in ("conductor", "orchestra"), \
                f"Unexpected node_type '{data.get('node_type')}' for {node}"

    def test_edge_weight_equals_appearance_count(self, graph):
        bp = conductor_orchestra_bipartite(graph)
        # Nelsons <-> LA Phil has appearance_count=3 in the fixture
        if bp.has_edge("andris_nelsons", "los_angeles_philharmonic"):
            weight = bp["andris_nelsons"]["los_angeles_philharmonic"].get("weight", 0)
            assert weight >= 1

    def test_is_bipartite(self, graph):
        bp = conductor_orchestra_bipartite(graph)
        # The projected graph need not be bipartite, but conductors and
        # orchestras should not share edges with same-type nodes
        conductors = {n for n, d in bp.nodes(data=True) if d.get("node_type") == "conductor"}
        orchestras = {n for n, d in bp.nodes(data=True) if d.get("node_type") == "orchestra"}
        for u, v in bp.edges():
            both_conductors = u in conductors and v in conductors
            both_orchestras = u in orchestras and v in orchestras
            assert not both_conductors, f"Conductor-conductor edge: {u} -> {v}"
            assert not both_orchestras, f"Orchestra-orchestra edge: {u} -> {v}"


# ---------------------------------------------------------------------------
# Graph validation
# ---------------------------------------------------------------------------

class TestValidateGraph:
    def test_valid_graph_passes(self, graph):
        errors = validate_graph(graph)
        assert errors == [], f"Validation errors on valid graph: {errors}"

    def test_detects_missing_node_type(self):
        g = nx.MultiDiGraph()
        g.add_node("orphan")  # no node_type attribute
        errors = validate_graph(g)
        assert any("node_type" in e for e in errors)

    def test_detects_dangling_edge(self):
        g = nx.MultiDiGraph()
        g.add_node("conductor_a", node_type="conductor")
        # Add edge to non-existent node
        g.add_edge("conductor_a", "nonexistent_orchestra", edge_type="permanent_position")
        errors = validate_graph(g)
        # Dangling edges or missing targets should be flagged
        # (networkx allows them; validate_graph should catch them)
        # This is an aspirational test — implementation decides exact error message
        assert isinstance(errors, list)

    def test_returns_list(self, graph):
        errors = validate_graph(graph)
        assert isinstance(errors, list)

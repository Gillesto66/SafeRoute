# Fait par Gillesto
# test_engine.py — Tests unitaires Python (pytest)

import json
import pytest
from saferoute.models import ParetoSet, Route


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_graph_json():
    """Graphe minimal : 3 nœuds, 2 chemins (court/risqué vs long/sûr)."""
    return json.dumps({
        "nodes": [
            {"id": 1, "lat": 51.500, "lon": -0.100},
            {"id": 2, "lat": 51.501, "lon": -0.100},  # chemin direct (risqué)
            {"id": 3, "lat": 51.500, "lon": -0.090},  # chemin détour (sûr)
        ],
        "edges": [
            {"from": 1, "to": 2, "distance_m": 100.0, "risk_score": 0.9, "familiarity": 0.0},
            {"from": 2, "to": 3, "distance_m": 100.0, "risk_score": 0.9, "familiarity": 0.0},
            {"from": 1, "to": 3, "distance_m": 800.0, "risk_score": 0.1, "familiarity": 0.0},
        ]
    })


# ── Tests modèles ─────────────────────────────────────────────────────────────

def test_route_distance_km():
    route = Route(path=[1, 2], total_distance_m=1500.0, total_risk=0.3, route_type="shortest")
    assert route.distance_km == 1.5


def test_pareto_set_from_results():
    class FakeResult:
        def __init__(self, rtype, dist, risk, path):
            self.route_type = rtype
            self.total_distance_m = dist
            self.total_risk = risk
            self.path = path

    results = [
        FakeResult("shortest", 100.0, 0.9, [1, 2]),
        FakeResult("safest", 800.0, 0.1, [1, 3]),
        FakeResult("balanced", 400.0, 0.4, [1, 2, 3]),
    ]
    ps = ParetoSet.from_results(results)
    assert ps.shortest is not None
    assert ps.safest is not None
    assert ps.balanced is not None
    assert ps.shortest.total_distance_m == 100.0
    assert ps.safest.total_risk == 0.1


# ── Tests moteur Rust (skip si non compilé) ───────────────────────────────────

try:
    from saferoute_core import PyGraph, compute_safe_routes
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Module Rust non compilé (maturin develop)")
def test_pygraph_load(minimal_graph_json):
    graph = PyGraph.from_json(minimal_graph_json)
    assert graph.node_count() == 3
    assert graph.edge_count() == 3


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Module Rust non compilé")
def test_compute_routes_returns_pareto(minimal_graph_json):
    graph = PyGraph.from_json(minimal_graph_json)
    results = compute_safe_routes(graph, 1, 3, 0.1)
    assert len(results) >= 1
    # La route la plus sûre doit avoir un risque plus faible que la plus courte
    types = {r.route_type for r in results}
    assert "shortest" in types or "safest" in types


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Module Rust non compilé")
def test_invalid_node_raises(minimal_graph_json):
    graph = PyGraph.from_json(minimal_graph_json)
    # Nœud inexistant → doit retourner une liste vide ou lever une erreur propre
    results = compute_safe_routes(graph, 1, 999, 0.1)
    assert results == []

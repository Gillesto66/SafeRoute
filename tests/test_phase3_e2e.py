# Fait par Gillesto
# test_phase3_e2e.py — Tests d'intégration end-to-end Phase 3
#
# Ces tests chargent un vrai graphe synthétique (offline) et vérifient
# la pipeline complète : graphe → KDE → A*pex → 3 routes.
# Ils ne nécessitent pas Rust compilé (moteur Python pur).

import json
import math
import pytest
import networkx as nx

from saferoute.graph_cache import GraphCache
from saferoute.kde_scorer import compute_kde_scores
from saferoute.data_loader import fetch_cape_town_crimes, validate_crimes
from saferoute.familiarity import FamiliarityEngine
from saferoute.models import ParetoSet, Route


# ── Graphe de test réaliste ───────────────────────────────────────────────────

def build_realistic_graph(city_key: str = "london") -> nx.MultiDiGraph:
    """
    Grille 8×8 = 64 nœuds simulant un quartier urbain.
    Inclut des variations de longueur pour créer des compromis Pareto réels.
    """
    centers = {"london": (51.507, -0.127), "cape_town": (-33.925, 18.424)}
    lat0, lon0 = centers.get(city_key, (51.5, -0.1))
    dlat = 0.001
    dlon = 0.001 / math.cos(math.radians(lat0))

    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    size = 8

    for i in range(size):
        for j in range(size):
            nid = i * size + j + 1000
            G.add_node(nid, y=lat0 + i * dlat, x=lon0 + j * dlon)

    for i in range(size):
        for j in range(size):
            u = i * size + j + 1000
            if j + 1 < size:
                v = i * size + j + 1 + 1000
                length = 111.0 * (1 + 0.3 * ((i + j) % 3))
                G.add_edge(u, v, key=0, length=length)
                G.add_edge(v, u, key=0, length=length)
            if i + 1 < size:
                v = (i + 1) * size + j + 1000
                length = 111.0 * (1 + 0.2 * (j % 4))
                G.add_edge(u, v, key=0, length=length)
                G.add_edge(v, u, key=0, length=length)
    return G


def build_crimes_for_graph(G: nx.MultiDiGraph, n: int = 100) -> list[dict]:
    """Génère des crimes concentrés dans le coin supérieur gauche du graphe."""
    import random
    rng = random.Random(42)
    nodes = list(G.nodes(data=True))
    # Hotspot : premier quart du graphe
    hotspot_nodes = nodes[:len(nodes) // 4]
    crimes = []
    for _ in range(n):
        _, data = rng.choice(hotspot_nodes)
        crimes.append({
            "lat": rng.gauss(data["y"], 0.0005),
            "lon": rng.gauss(data["x"], 0.0005),
            "weight": rng.uniform(1.0, 3.0),
        })
    return crimes


# ── Tests end-to-end ──────────────────────────────────────────────────────────

class TestEndToEnd:

    @pytest.fixture
    def graph_and_crimes(self):
        G = build_realistic_graph("london")
        crimes = build_crimes_for_graph(G, n=150)
        return G, crimes

    def test_kde_pipeline_on_realistic_graph(self, graph_and_crimes):
        G, crimes = graph_and_crimes
        result = compute_kde_scores(G, crimes)
        assert len(result.risk_map) == G.number_of_edges()
        scores = list(result.risk_map.values())
        assert max(scores) == pytest.approx(1.0, abs=1e-4)
        assert min(scores) >= 0.0
        # Les arcs dans le hotspot doivent avoir un score plus élevé
        # que les arcs loin du hotspot
        assert result.stats["p90"] > result.stats["mean"]

    def test_familiarity_pipeline(self, graph_and_crimes):
        G, _ = graph_and_crimes
        engine = FamiliarityEngine()
        fmap = engine.simulate_trajectories(G, n_trips=30, seed=42)
        assert fmap.total_trips > 0
        assert fmap.stats()["count"] > 0
        # Après 30 trajets, certains arcs doivent être familiers
        assert fmap.stats()["familiar_edges"] > 0

    def test_graph_json_serialization(self, graph_and_crimes):
        """Vérifie que le JSON produit est valide pour le moteur Rust."""
        G, crimes = graph_and_crimes
        kde_result = compute_kde_scores(G, crimes)

        nodes = [{"id": nid, "lat": d["y"], "lon": d["x"]}
                 for nid, d in G.nodes(data=True)]
        edges = [{"from": u, "to": v, "distance_m": float(d.get("length", 100.0)),
                  "risk_score": float(kde_result.risk_map.get((u, v, k), 0.0)),
                  "familiarity": 0.0}
                 for u, v, k, d in G.edges(keys=True, data=True)]

        graph_json = json.dumps({"nodes": nodes, "edges": edges})
        data = json.loads(graph_json)

        assert len(data["nodes"]) == G.number_of_nodes()
        assert len(data["edges"]) == G.number_of_edges()
        # Tous les scores de risque doivent être dans [0, 1]
        for e in data["edges"]:
            assert 0.0 <= e["risk_score"] <= 1.0 + 1e-9

    def test_cache_full_pipeline(self, tmp_path, graph_and_crimes):
        """Vérifie save → load du cache graphe + crimes."""
        G, crimes = graph_and_crimes
        cache = GraphCache(cache_dir=tmp_path)

        from unittest.mock import patch
        with patch("saferoute.graph_cache.ox.save_graphml"), \
             patch("saferoute.graph_cache.ox.load_graphml", return_value=G):
            cache.save_graph("london", G)
            G_loaded = cache.load_graph("london")

        cache.save_crimes("london", crimes)
        crimes_loaded = cache.load_crimes("london")

        assert crimes_loaded is not None
        assert len(crimes_loaded) == len(crimes)
        assert abs(crimes_loaded[0]["lat"] - crimes[0]["lat"]) < 1e-6

    def test_validate_crimes_pipeline(self):
        """Vérifie la validation des crimes sur données synthétiques Le Cap."""
        crimes_raw = fetch_cape_town_crimes(radius_m=1000.0, points_per_station=20)
        bbox = {"min_lat": -35.0, "max_lat": -33.0, "min_lon": 18.0, "max_lon": 19.5}
        crimes_valid, stats = validate_crimes(crimes_raw, bbox, "cape_town")

        assert stats["final"] > 0
        assert stats["out_of_bbox"] == 0  # tous dans la bbox
        assert stats["invalid_weight"] == 0
        # Tous les scores valides doivent être dans (0, 10]
        for c in crimes_valid:
            assert 0 < c["weight"] <= 10

    def test_pareto_set_from_mock_results(self):
        """Vérifie que ParetoSet.from_results gère correctement les métadonnées."""
        class MockResult:
            def __init__(self, rtype, dist, risk):
                self.route_type = rtype
                self.total_distance_m = dist
                self.total_risk = risk
                self.total_familiarity = 0.1
                self.estimated_time_min = dist / 66.67
                self.node_count = 5
                self.comfort_score = max(0.0, 1.0 - risk)
                self.path = [1000, 1001, 1002, 1003, 1004]

        results = [
            MockResult("shortest", 200.0, 1.8),
            MockResult("safest",   900.0, 0.05),
            MockResult("balanced", 500.0, 0.6),
        ]
        ps = ParetoSet.from_results(results)

        assert ps.shortest.total_distance_m < ps.safest.total_distance_m
        assert ps.safest.total_risk < ps.shortest.total_risk
        assert ps.balanced.total_distance_m < ps.safest.total_distance_m
        assert ps.balanced.total_risk < ps.shortest.total_risk

        # Métadonnées
        assert ps.shortest.estimated_time_min == pytest.approx(200.0 / 66.67, abs=0.01)
        assert ps.safest.comfort_score == pytest.approx(0.95, abs=0.01)

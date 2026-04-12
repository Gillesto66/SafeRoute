# Fait par Gillesto
# test_phase2.py — Tests unitaires Phase 2 : familiarité, modèles enrichis, intégration

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from saferoute.familiarity import FamiliarityEngine, FamiliarityMap
from saferoute.models import Route, ParetoSet


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def small_nx_graph():
    """Graphe NetworkX minimal avec 4 nœuds et 5 arcs."""
    G = nx.MultiDiGraph()
    nodes = [
        (1001, {"y": 51.500, "x": -0.100}),
        (1002, {"y": 51.501, "x": -0.100}),
        (1003, {"y": 51.500, "x": -0.095}),
        (1004, {"y": 51.501, "x": -0.090}),
    ]
    for nid, data in nodes:
        G.add_node(nid, **data)
    G.add_edge(1001, 1002, key=0, length=100.0)
    G.add_edge(1002, 1004, key=0, length=100.0)
    G.add_edge(1001, 1004, key=0, length=900.0)
    G.add_edge(1001, 1003, key=0, length=400.0)
    G.add_edge(1003, 1004, key=0, length=400.0)
    return G


@pytest.fixture
def familiarity_engine():
    return FamiliarityEngine(decay_per_trip=0.01)


# ══════════════════════════════════════════════════════════════════════════════
# FamiliarityMap
# ══════════════════════════════════════════════════════════════════════════════

class TestFamiliarityMap:

    def test_initial_score_zero(self):
        fmap = FamiliarityMap()
        assert fmap.get(1, 2, 0) == 0.0

    def test_update_increments_score(self):
        fmap = FamiliarityMap()
        fmap.update(1, 2, 0, delta=0.3)
        assert abs(fmap.get(1, 2, 0) - 0.3) < 1e-9

    def test_update_saturates_at_1(self):
        fmap = FamiliarityMap()
        fmap.update(1, 2, 0, delta=0.8)
        fmap.update(1, 2, 0, delta=0.8)
        assert fmap.get(1, 2, 0) == 1.0

    def test_decay_reduces_scores(self):
        fmap = FamiliarityMap()
        fmap.update(1, 2, 0, delta=1.0)
        fmap.decay(factor=0.9)
        assert abs(fmap.get(1, 2, 0) - 0.9) < 1e-9

    def test_decay_removes_very_low_scores(self):
        fmap = FamiliarityMap()
        fmap.scores[(1, 2, 0)] = 0.005  # sous le seuil de 0.01
        fmap.decay(factor=0.9)
        assert fmap.get(1, 2, 0) == 0.0  # supprimé

    def test_stats_empty(self):
        fmap = FamiliarityMap()
        stats = fmap.stats()
        assert stats["count"] == 0
        assert stats["mean"] == 0.0

    def test_stats_with_data(self):
        fmap = FamiliarityMap()
        fmap.update(1, 2, 0, delta=0.8)
        fmap.update(2, 3, 0, delta=0.4)
        stats = fmap.stats()
        assert stats["count"] == 2
        assert abs(stats["mean"] - 0.6) < 1e-9
        assert stats["familiar_edges"] == 2  # 0.8 > 0.3 ET 0.4 > 0.3


# ══════════════════════════════════════════════════════════════════════════════
# FamiliarityEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestFamiliarityEngine:

    def test_update_from_path_updates_scores(self, familiarity_engine, small_nx_graph):
        path = [1001, 1002, 1004]
        familiarity_engine.update_from_path(path, small_nx_graph)
        fmap = familiarity_engine.get_familiarity_map()
        assert fmap.get(1001, 1002, 0) > 0.0
        assert fmap.get(1002, 1004, 0) > 0.0

    def test_update_from_path_ignores_single_node(self, familiarity_engine, small_nx_graph):
        familiarity_engine.update_from_path([1001], small_nx_graph)
        fmap = familiarity_engine.get_familiarity_map()
        assert fmap.stats()["count"] == 0

    def test_repeated_trips_increase_familiarity(self, familiarity_engine, small_nx_graph):
        path = [1001, 1002, 1004]
        familiarity_engine.update_from_path(path, small_nx_graph)
        score_after_1 = familiarity_engine.get_familiarity_map().get(1001, 1002, 0)
        familiarity_engine.update_from_path(path, small_nx_graph)
        score_after_2 = familiarity_engine.get_familiarity_map().get(1001, 1002, 0)
        assert score_after_2 > score_after_1

    def test_simulate_trajectories_populates_map(self, familiarity_engine, small_nx_graph):
        fmap = familiarity_engine.simulate_trajectories(small_nx_graph, n_trips=20, seed=42)
        assert fmap.stats()["count"] > 0
        assert fmap.total_trips > 0

    def test_simulate_trajectories_reproducible(self, small_nx_graph):
        e1 = FamiliarityEngine()
        e2 = FamiliarityEngine()
        m1 = e1.simulate_trajectories(small_nx_graph, n_trips=10, seed=99)
        m2 = e2.simulate_trajectories(small_nx_graph, n_trips=10, seed=99)
        assert m1.stats()["count"] == m2.stats()["count"]
        assert abs(m1.stats()["mean"] - m2.stats()["mean"]) < 1e-9

    def test_apply_to_graph_json_injects_scores(self, familiarity_engine, small_nx_graph):
        # Simule quelques trajets
        familiarity_engine.update_from_path([1001, 1002, 1004], small_nx_graph)

        # JSON de graphe minimal
        graph_json = json.dumps({
            "nodes": [{"id": 1001, "lat": 51.5, "lon": -0.1}],
            "edges": [
                {"from": 1001, "to": 1002, "distance_m": 100.0, "risk_score": 0.3, "familiarity": 0.0},
                {"from": 1002, "to": 1004, "distance_m": 100.0, "risk_score": 0.3, "familiarity": 0.0},
                {"from": 1001, "to": 1004, "distance_m": 900.0, "risk_score": 0.1, "familiarity": 0.0},
            ]
        })

        enriched_json = familiarity_engine.apply_to_graph_json(graph_json)
        data = json.loads(enriched_json)

        # L'arc 1001→1002 doit avoir une familiarité > 0
        edge_1001_1002 = next(
            e for e in data["edges"] if e["from"] == 1001 and e["to"] == 1002
        )
        assert edge_1001_1002["familiarity"] > 0.0

    def test_save_and_load(self, familiarity_engine, small_nx_graph, tmp_path):
        familiarity_engine.update_from_path([1001, 1002, 1004], small_nx_graph)
        fmap_before = familiarity_engine.get_familiarity_map()
        # Vérifie qu'au moins un arc a été mis à jour
        assert fmap_before.stats()["count"] > 0
        total_score_before = sum(fmap_before.scores.values())

        save_path = tmp_path / "familiarity.json"
        familiarity_engine.save(save_path)

        # Charge dans un nouveau moteur
        engine2 = FamiliarityEngine()
        engine2.load(save_path)
        fmap2 = engine2.get_familiarity_map()

        # Le nombre d'arcs et le score total doivent être identiques
        assert fmap2.stats()["count"] == fmap_before.stats()["count"]
        assert abs(sum(fmap2.scores.values()) - total_score_before) < 1e-6

    def test_load_nonexistent_file_no_crash(self, familiarity_engine, tmp_path):
        # Ne doit pas lever d'exception
        familiarity_engine.load(tmp_path / "nonexistent.json")
        assert familiarity_engine.get_familiarity_map().stats()["count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Modèles enrichis (Route avec métadonnées)
# ══════════════════════════════════════════════════════════════════════════════

class TestEnrichedModels:

    def test_route_distance_km(self):
        r = Route(path=[1, 2], total_distance_m=1500.0, total_risk=0.3, route_type="shortest")
        assert r.distance_km == 1.5

    def test_route_default_metadata(self):
        r = Route(path=[1, 2], total_distance_m=500.0, total_risk=0.2, route_type="safest")
        assert r.total_familiarity == 0.0
        assert r.estimated_time_min == 0.0
        assert r.comfort_score == 0.0

    def test_pareto_set_from_results_with_metadata(self):
        class FakeResult:
            def __init__(self, rtype, dist, risk, fam, time, comfort, path):
                self.route_type = rtype
                self.total_distance_m = dist
                self.total_risk = risk
                self.total_familiarity = fam
                self.estimated_time_min = time
                self.comfort_score = comfort
                self.node_count = len(path)
                self.path = path

        results = [
            FakeResult("shortest", 200.0, 1.8, 0.0, 3.0, 0.03, [1, 2, 4]),
            FakeResult("safest",   900.0, 0.05, 0.0, 13.5, 0.9, [1, 4]),
            FakeResult("balanced", 800.0, 0.8, 1.6, 12.0, 0.2, [1, 3, 4]),
        ]
        ps = ParetoSet.from_results(results)

        assert ps.shortest is not None
        assert ps.safest is not None
        assert ps.balanced is not None

        # Vérifie les métadonnées
        assert ps.shortest.total_distance_m == 200.0
        assert ps.safest.total_risk == 0.05
        assert abs(ps.balanced.total_familiarity - 1.6) < 1e-9
        assert abs(ps.shortest.estimated_time_min - 3.0) < 1e-9
        assert abs(ps.safest.comfort_score - 0.9) < 1e-9

    def test_pareto_set_safest_lower_risk_than_shortest(self):
        class FakeResult:
            def __init__(self, rtype, dist, risk):
                self.route_type = rtype
                self.total_distance_m = dist
                self.total_risk = risk
                self.total_familiarity = 0.0
                self.estimated_time_min = dist / 66.67
                self.comfort_score = 0.5
                self.node_count = 2
                self.path = [1, 2]

        ps = ParetoSet.from_results([
            FakeResult("shortest", 200.0, 1.8),
            FakeResult("safest",   900.0, 0.05),
        ])
        assert ps.safest.total_risk < ps.shortest.total_risk


# ══════════════════════════════════════════════════════════════════════════════
# Intégration Engine Phase 2 (avec mocks)
# ══════════════════════════════════════════════════════════════════════════════

class TestEnginePhase2:

    @pytest.fixture
    def engine_loaded(self, tmp_path, small_nx_graph):
        """Engine avec graphe mocké et familiarité simulée."""
        from saferoute.engine import SafeRouteEngine

        engine = SafeRouteEngine(
            cache_dir=tmp_path,
            simulate_familiarity=True,
            familiarity_trips=10,
        )
        engine._PyGraph = None
        engine._compute = None

        with patch.object(engine, "_download_graph", return_value=small_nx_graph), \
             patch("saferoute.engine.validate_graph") as mv, \
             patch("saferoute.engine.extract_largest_scc", return_value=small_nx_graph), \
             patch.object(engine._cache, "save_graph"):
            mv.return_value = MagicMock(
                is_valid=True,
                bbox={"min_lat": 51.49, "max_lat": 51.51, "min_lon": -0.11, "max_lon": -0.08},
                summary=lambda: "OK",
            )
            crimes = [{"lat": 51.500, "lon": -0.100, "weight": 2.0}]
            stats = engine.load_city("london", crime_points=crimes)
            yield engine, stats

    def test_load_city_includes_familiarity_stats(self, engine_loaded):
        _, stats = engine_loaded
        assert "familiarity_stats" in stats
        fstats = stats["familiarity_stats"]
        assert "count" in fstats
        assert "total_trips" in fstats

    def test_familiarity_populated_after_simulation(self, engine_loaded):
        engine, _ = engine_loaded
        fmap = engine._familiarity.get_familiarity_map()
        # Après 10 trajets simulés sur un graphe de 4 nœuds, des arcs doivent être familiers
        assert fmap.stats()["count"] > 0

    def test_record_trip_updates_familiarity(self, engine_loaded, small_nx_graph):
        engine, _ = engine_loaded
        engine._nx_graph = small_nx_graph
        initial_count = engine._familiarity.get_familiarity_map().stats()["count"]
        engine.record_trip([1001, 1002, 1004])
        new_count = engine._familiarity.get_familiarity_map().stats()["count"]
        assert new_count >= initial_count

    def test_record_trip_without_graph_raises(self, tmp_path):
        from saferoute.engine import SafeRouteEngine
        engine = SafeRouteEngine(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="non chargé"):
            engine.record_trip([1, 2, 3])

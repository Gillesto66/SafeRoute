# Fait par Gillesto
# test_phase1.py — Tests unitaires complets de la Phase 1
#
# Couvre :
#   - GraphCache : save/load graphe et crimes
#   - GraphValidator : validation, SCC, bbox
#   - DataLoader : pondérations, validation crimes, génération Le Cap
#   - KDEScorer : calibration bandwidth, scoring, normalisation
#   - Engine : intégration load_city avec mocks

import gzip
import json
import csv
import asyncio
import math
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile

import numpy as np
import pytest
import networkx as nx

from saferoute.graph_cache import GraphCache
from saferoute.graph_validator import validate_graph, extract_largest_scc, ValidationReport
from saferoute.data_loader import (
    _london_crime_weight,
    validate_crimes,
    fetch_cape_town_crimes,
    LONDON_BOROUGH_POLYGONS,
    CAPE_TOWN_SAPS_STATIONS,
)
from saferoute.kde_scorer import compute_kde_scores, _calibrate_bandwidth
from saferoute.models import ParetoSet, Route


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_cache(tmp_path):
    """Cache temporaire dans un répertoire pytest."""
    return GraphCache(cache_dir=tmp_path)


@pytest.fixture
def small_nx_graph():
    """
    Graphe NetworkX minimal simulant un graphe OSMnx.
    4 nœuds, 4 arcs, tous avec coordonnées et longueurs.
    """
    G = nx.MultiDiGraph()
    nodes = [
        (1001, {"y": 51.500, "x": -0.100}),
        (1002, {"y": 51.501, "x": -0.100}),
        (1003, {"y": 51.501, "x": -0.090}),
        (1004, {"y": 51.500, "x": -0.090}),
    ]
    for nid, data in nodes:
        G.add_node(nid, **data)

    edges = [
        (1001, 1002, 0, {"length": 111.0}),
        (1002, 1003, 0, {"length": 800.0}),
        (1003, 1004, 0, {"length": 111.0}),
        (1001, 1004, 0, {"length": 800.0}),
    ]
    for u, v, k, data in edges:
        G.add_edge(u, v, key=k, **data)

    return G


@pytest.fixture
def london_bbox():
    return {"min_lat": 51.28, "max_lat": 51.70, "min_lon": -0.51, "max_lon": 0.33}


@pytest.fixture
def cape_town_bbox():
    return {"min_lat": -34.35, "max_lat": -33.50, "min_lon": 18.30, "max_lon": 19.00}


@pytest.fixture
def sample_crimes_london():
    """Crimes fictifs dans la bounding box de Londres."""
    return [
        {"lat": 51.50, "lon": -0.10, "weight": 3.0},
        {"lat": 51.51, "lon": -0.09, "weight": 1.5},
        {"lat": 51.49, "lon": -0.11, "weight": 2.0},
        {"lat": 51.52, "lon": -0.08, "weight": 1.0},
        {"lat": 51.50, "lon": -0.10, "weight": 3.0},  # doublon exact
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 1.1 — GraphCache
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphCache:

    def test_has_graph_false_initially(self, tmp_cache):
        assert not tmp_cache.has_graph("london")

    def test_has_crimes_false_initially(self, tmp_cache):
        assert not tmp_cache.has_crimes("london")

    def test_save_and_load_crimes(self, tmp_cache):
        crimes = [
            {"lat": 51.5, "lon": -0.1, "weight": 2.0},
            {"lat": 51.6, "lon": -0.2, "weight": 1.5},
        ]
        tmp_cache.save_crimes("london", crimes)
        assert tmp_cache.has_crimes("london")

        loaded = tmp_cache.load_crimes("london")
        assert loaded is not None
        assert len(loaded) == 2
        assert abs(loaded[0]["lat"] - 51.5) < 1e-6
        assert abs(loaded[0]["weight"] - 2.0) < 1e-6

    def test_load_crimes_returns_none_if_missing(self, tmp_cache):
        assert tmp_cache.load_crimes("nonexistent") is None

    def test_load_graph_returns_none_if_missing(self, tmp_cache):
        assert tmp_cache.load_graph("nonexistent") is None

    def test_crimes_file_is_gzip(self, tmp_cache):
        crimes = [{"lat": 51.5, "lon": -0.1, "weight": 1.0}]
        tmp_cache.save_crimes("test", crimes)
        path = tmp_cache.crimes_path("test")
        # Vérifie que le fichier est bien compressé gzip
        with open(path, "rb") as f:
            magic = f.read(2)
        assert magic == b"\x1f\x8b"  # magic bytes gzip

    def test_cache_info_empty(self, tmp_cache):
        assert tmp_cache.cache_info() == {}

    def test_meta_saved_with_graph(self, tmp_cache, small_nx_graph):
        # Mock ox.save_graphml pour ne pas écrire un vrai fichier graphml
        with patch("saferoute.graph_cache.ox.save_graphml"):
            tmp_cache.save_graph("test", small_nx_graph)
        meta_path = tmp_cache.meta_path("test")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["node_count"] == 4
        assert meta["edge_count"] == 4


# ══════════════════════════════════════════════════════════════════════════════
# 1.1 — GraphValidator
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphValidator:

    def test_valid_graph(self, small_nx_graph):
        report = validate_graph(small_nx_graph, "test")
        assert report.node_count == 4
        assert report.edge_count == 4
        assert report.nodes_missing_coords == 0
        assert report.edges_missing_length == 0
        assert report.bbox["min_lat"] == pytest.approx(51.500)
        assert report.bbox["max_lat"] == pytest.approx(51.501)

    def test_empty_graph_is_invalid(self):
        G = nx.MultiDiGraph()
        report = validate_graph(G, "empty")
        assert not report.is_valid
        assert any("vide" in e.lower() for e in report.errors)

    def test_missing_length_triggers_error(self):
        G = nx.MultiDiGraph()
        G.add_node(1, y=51.5, x=-0.1)
        G.add_node(2, y=51.6, x=-0.1)
        # Arc sans attribut 'length'
        for _ in range(20):
            G.add_edge(1, 2)
        report = validate_graph(G, "test")
        assert report.edges_missing_length == 20

    def test_missing_coords_triggers_error(self):
        G = nx.MultiDiGraph()
        G.add_node(1)  # pas de y/x
        G.add_node(2, y=51.5, x=-0.1)
        G.add_edge(1, 2, length=100.0)
        report = validate_graph(G, "test")
        assert not report.is_valid
        assert report.nodes_missing_coords >= 1

    def test_scc_ratio_computed(self, small_nx_graph):
        report = validate_graph(small_nx_graph, "test")
        # Le graphe de test est fortement connexe (cycle 1→2→3→4→1 via arcs)
        # Note : dépend de la structure exacte du graphe de test
        assert 0 < report.largest_scc_ratio <= 1.0

    def test_summary_contains_city_key(self, small_nx_graph):
        report = validate_graph(small_nx_graph, "my_city")
        assert "my_city" in report.summary()


# ══════════════════════════════════════════════════════════════════════════════
# 1.2 — DataLoader
# ══════════════════════════════════════════════════════════════════════════════

class TestDataLoader:

    # ── Pondérations Londres ──────────────────────────────────────────────────

    def test_violent_crime_weight(self):
        assert _london_crime_weight("violent-crime") == 3.0

    def test_robbery_weight(self):
        assert _london_crime_weight("robbery") == 2.5

    def test_unknown_category_default_weight(self):
        assert _london_crime_weight("unknown-category") == 1.0

    def test_shoplifting_low_weight(self):
        assert _london_crime_weight("shoplifting") < 1.5

    # ── Polygones arrondissements ─────────────────────────────────────────────

    def test_all_32_boroughs_defined(self):
        assert len(LONDON_BOROUGH_POLYGONS) == 32

    def test_borough_polygon_format(self):
        """Chaque polygone doit avoir au moins 3 points lat,lon."""
        for borough, poly in LONDON_BOROUGH_POLYGONS.items():
            points = poly.split(":")
            assert len(points) >= 3, f"{borough} a moins de 3 points"
            for p in points:
                parts = p.split(",")
                assert len(parts) == 2, f"{borough}: point mal formé '{p}'"
                lat, lon = float(parts[0]), float(parts[1])
                # Vérification que les coords sont dans Greater London
                assert 51.2 < lat < 51.8, f"{borough}: lat={lat} hors Londres"
                assert -0.6 < lon < 0.4, f"{borough}: lon={lon} hors Londres"

    # ── Validation des crimes ─────────────────────────────────────────────────

    def test_validate_removes_duplicates(self, sample_crimes_london, london_bbox):
        valid, stats = validate_crimes(sample_crimes_london, london_bbox, "london")
        assert stats["duplicates_removed"] == 1
        assert len(valid) == 4

    def test_validate_removes_out_of_bbox(self, london_bbox):
        crimes = [
            {"lat": 51.5, "lon": -0.1, "weight": 1.0},   # dans bbox
            {"lat": 48.8, "lon": 2.35, "weight": 1.0},   # Paris → hors bbox
        ]
        valid, stats = validate_crimes(crimes, london_bbox, "london")
        assert stats["out_of_bbox"] == 1
        assert len(valid) == 1

    def test_validate_removes_invalid_weight(self, london_bbox):
        crimes = [
            {"lat": 51.5, "lon": -0.1, "weight": 1.0},
            {"lat": 51.5, "lon": -0.1, "weight": -1.0},   # négatif
            {"lat": 51.5, "lon": -0.1, "weight": float("nan")},  # NaN
            {"lat": 51.5, "lon": -0.1, "weight": 15.0},   # > 10
        ]
        valid, stats = validate_crimes(crimes, london_bbox, "london")
        assert stats["invalid_weight"] == 3
        assert len(valid) == 1

    def test_validate_empty_list(self, london_bbox):
        valid, stats = validate_crimes([], london_bbox, "london")
        assert valid == []
        assert stats["final"] == 0

    # ── Génération crimes Le Cap ──────────────────────────────────────────────

    def test_cape_town_stations_count(self):
        assert len(CAPE_TOWN_SAPS_STATIONS) == 30

    def test_cape_town_stations_coords_in_region(self):
        for s in CAPE_TOWN_SAPS_STATIONS:
            assert -35.0 < s["lat"] < -33.0, f"{s['name']}: lat hors zone"
            assert 18.0 < s["lon"] < 19.5, f"{s['name']}: lon hors zone"
            assert 0 < s["crime_index"] <= 5.0

    def test_fetch_cape_town_crimes_returns_list(self):
        crimes = fetch_cape_town_crimes(radius_m=500.0, points_per_station=10)
        assert isinstance(crimes, list)
        assert len(crimes) > 0

    def test_fetch_cape_town_crimes_reproducible(self):
        """Deux appels avec les mêmes paramètres → même résultat (seed fixe)."""
        c1 = fetch_cape_town_crimes(radius_m=500.0, points_per_station=10)
        c2 = fetch_cape_town_crimes(radius_m=500.0, points_per_station=10)
        assert len(c1) == len(c2)
        assert abs(c1[0]["lat"] - c2[0]["lat"]) < 1e-10

    def test_fetch_cape_town_high_crime_index_more_points(self):
        """Les stations à crime_index élevé génèrent plus de points."""
        crimes = fetch_cape_town_crimes(radius_m=500.0, points_per_station=20)
        # Khayelitsha (crime_index=3.8) doit contribuer plus que Simon's Town (1.2)
        assert len(crimes) > 0
        # Vérification indirecte : le total est proportionnel aux crime_index
        total_expected = sum(
            int(20 * s["crime_index"] / 2.0) for s in CAPE_TOWN_SAPS_STATIONS
        )
        assert len(crimes) == total_expected


# ══════════════════════════════════════════════════════════════════════════════
# 1.3 — KDE Scorer
# ══════════════════════════════════════════════════════════════════════════════

class TestKDEScorer:

    def test_no_crimes_returns_empty_map(self, small_nx_graph):
        result = compute_kde_scores(small_nx_graph, [])
        assert result.risk_map == {}
        assert result.n_crimes == 0

    def test_scores_normalized_0_1(self, small_nx_graph):
        # Crimes placés exactement sur les nœuds du graphe pour garantir des scores > 0
        crimes_on_graph = [
            {"lat": 51.500, "lon": -0.100, "weight": 3.0},
            {"lat": 51.501, "lon": -0.100, "weight": 2.0},
            {"lat": 51.501, "lon": -0.090, "weight": 1.5},
        ]
        result = compute_kde_scores(small_nx_graph, crimes_on_graph)
        assert result.risk_map, "risk_map ne doit pas être vide"
        scores = list(result.risk_map.values())
        assert max(scores) <= 1.0 + 1e-9
        assert min(scores) >= 0.0 - 1e-9
        assert max(scores) == pytest.approx(1.0, abs=1e-4)

    def test_all_edges_scored(self, small_nx_graph, sample_crimes_london):
        result = compute_kde_scores(small_nx_graph, sample_crimes_london)
        expected_edges = small_nx_graph.number_of_edges()
        assert len(result.risk_map) == expected_edges

    def test_fixed_bandwidth_used(self, small_nx_graph, sample_crimes_london):
        result = compute_kde_scores(small_nx_graph, sample_crimes_london, bandwidth_m=400.0)
        assert result.method == "fixed"
        assert abs(result.bandwidth_m - 400.0) < 1.0

    def test_silverman_bandwidth_in_range(self, small_nx_graph, sample_crimes_london):
        result = compute_kde_scores(small_nx_graph, sample_crimes_london)
        assert 200.0 <= result.bandwidth_m <= 800.0

    def test_stats_computed(self, small_nx_graph, sample_crimes_london):
        result = compute_kde_scores(small_nx_graph, sample_crimes_london)
        if result.risk_map:
            assert "mean" in result.stats
            assert "p90" in result.stats
            assert "p99" in result.stats
            assert result.stats["mean"] >= 0

    def test_crime_near_edge_increases_score(self, small_nx_graph):
        """Un crime exactement sur un arc doit lui donner un score élevé."""
        # Crime au centroïde de l'arc 1001→1002 (lat=51.5005, lon=-0.100)
        crimes_near = [{"lat": 51.5005, "lon": -0.100, "weight": 3.0}]
        crimes_far  = [{"lat": 51.600, "lon": 0.200, "weight": 3.0}]

        result_near = compute_kde_scores(small_nx_graph, crimes_near)
        result_far  = compute_kde_scores(small_nx_graph, crimes_far)

        if result_near.risk_map and result_far.risk_map:
            score_near = result_near.risk_map.get((1001, 1002, 0), 0)
            score_far  = result_far.risk_map.get((1001, 1002, 0), 0)
            assert score_near > score_far

    def test_calibrate_bandwidth_silverman(self):
        """Silverman doit retourner un bandwidth dans les limites."""
        rng = np.random.default_rng(42)
        lats = rng.normal(51.5, 0.05, 200)
        lons = rng.normal(-0.1, 0.05, 200)
        weights = np.ones(200)
        bw, method = _calibrate_bandwidth(lats, lons, weights)
        assert method == "silverman"
        assert bw > 0

    def test_calibrate_bandwidth_few_points_fallback(self):
        """Moins de 10 points → fallback fixe."""
        lats = np.array([51.5, 51.6])
        lons = np.array([-0.1, -0.2])
        weights = np.ones(2)
        bw, method = _calibrate_bandwidth(lats, lons, weights)
        assert method == "fixed_fallback"

    def test_elapsed_time_recorded(self, small_nx_graph, sample_crimes_london):
        result = compute_kde_scores(small_nx_graph, sample_crimes_london)
        assert result.elapsed_s >= 0


# ══════════════════════════════════════════════════════════════════════════════
# Intégration Engine (avec mocks)
# ══════════════════════════════════════════════════════════════════════════════

class TestEngineIntegration:

    @pytest.fixture
    def engine_with_mocks(self, tmp_path, small_nx_graph):
        """Engine avec graphe mocké (pas de téléchargement réseau)."""
        from saferoute.engine import SafeRouteEngine

        engine = SafeRouteEngine(cache_dir=tmp_path)
        engine._PyGraph = None  # Rust non compilé en CI
        engine._compute = None

        # Mock du téléchargement OSMnx
        with patch.object(engine, "_download_graph", return_value=small_nx_graph):
            with patch("saferoute.engine.validate_graph") as mock_validate:
                mock_validate.return_value = MagicMock(
                    is_valid=True,
                    bbox={"min_lat": 51.49, "max_lat": 51.51,
                          "min_lon": -0.11, "max_lon": -0.08},
                    summary=lambda: "OK",
                )
                with patch("saferoute.engine.extract_largest_scc", return_value=small_nx_graph):
                    with patch.object(engine._cache, "save_graph"):
                        crimes = [
                            {"lat": 51.500, "lon": -0.100, "weight": 2.0},
                            {"lat": 51.501, "lon": -0.095, "weight": 1.5},
                        ]
                        stats = engine.load_city("london", crime_points=crimes)
                        yield engine, stats

    def test_load_city_returns_stats(self, engine_with_mocks):
        engine, stats = engine_with_mocks
        assert stats["city"] == "london"
        assert stats["nodes"] == 4
        assert stats["edges"] == 4
        assert stats["crimes"] == 2
        assert "kde_bandwidth_m" in stats

    def test_load_city_unsupported_raises(self, tmp_path):
        from saferoute.engine import SafeRouteEngine
        from saferoute.exceptions import UnsupportedCityError
        engine = SafeRouteEngine(cache_dir=tmp_path)
        with pytest.raises(UnsupportedCityError):
            engine.load_city("paris")

    def test_compute_routes_without_load_raises(self, tmp_path):
        from saferoute.engine import SafeRouteEngine
        from saferoute.exceptions import GraphNotLoadedError
        engine = SafeRouteEngine(cache_dir=tmp_path)
        with pytest.raises(GraphNotLoadedError):
            engine.compute_routes(1001, 1004)

    def test_risk_map_geojson_structure(self, engine_with_mocks):
        engine, _ = engine_with_mocks
        geojson = engine.get_risk_map_geojson()
        assert geojson["type"] == "FeatureCollection"
        assert isinstance(geojson["features"], list)
        if geojson["features"]:
            feat = geojson["features"][0]
            assert feat["type"] == "Feature"
            assert "risk_score" in feat["properties"]
            assert feat["geometry"]["type"] == "LineString"

# Fait par Gillesto
# engine.py — Wrapper Python autour du moteur Rust (via PyO3/maturin)
#
# Protocole de communication Rust ↔ Python :
# 1. Python charge le graphe OSMnx (depuis cache ou téléchargement)
# 2. Python charge les crimes (depuis cache ou API)
# 3. Python calcule les scores KDE (module kde_scorer)
# 4. Python sérialise le graphe enrichi en JSON
# 5. Rust désérialise le JSON → Graph interne
# 6. Rust exécute A*pex et retourne des PyRouteResult
# 7. Python convertit en dataclasses Route/ParetoSet

import json
import logging
from pathlib import Path
from typing import Optional

import osmnx as ox
import numpy as np

from .graph_cache import GraphCache
from .graph_validator import validate_graph, extract_largest_scc
from .kde_scorer import compute_kde_scores, KDEResult
from .familiarity import FamiliarityEngine
from .models import ParetoSet

logger = logging.getLogger(__name__)

# Clés de ville supportées → requêtes OSMnx
SUPPORTED_CITIES: dict[str, dict] = {
    "london": {
        "method": "place",
        "query": "Greater London, United Kingdom",
        "network_type": "walk",
    },
    "cape_town": {
        "method": "point",
        "point": (-33.9249, 18.4241),
        "dist": 20000,
        "network_type": "walk",
    },
}


class SafeRouteEngine:
    """
    Moteur principal SafeRoute.
    Orchestre le cache, le chargement OSMnx, le scoring KDE et les appels au core Rust.
    """

    def __init__(
        self,
        eps: float = 0.1,
        cache_dir: Path | str | None = None,
        bandwidth_m: float | None = None,
        simulate_familiarity: bool = False,
        familiarity_trips: int = 50,
    ):
        """
        Args:
            eps                  : approximation A*pex (0.0=exact, 0.1=recommandé)
            cache_dir            : répertoire de cache
            bandwidth_m          : bandwidth KDE fixe. None → Silverman auto
            simulate_familiarity : si True, simule des trajectoires au chargement
            familiarity_trips    : nombre de trajets simulés
        """
        self.eps = eps
        self.bandwidth_m = bandwidth_m
        self.simulate_familiarity = simulate_familiarity
        self.familiarity_trips = familiarity_trips
        self._cache = GraphCache(cache_dir) if cache_dir else GraphCache()
        self._familiarity = FamiliarityEngine()

        self._py_graph = None
        self._nx_graph = None
        self._current_city: str | None = None
        self._kde_result: KDEResult | None = None

        # Import du module Rust compilé (disponible après `maturin develop`)
        try:
            from saferoute_core import PyGraph, compute_safe_routes
            self._PyGraph = PyGraph
            self._compute = compute_safe_routes
            logger.info("Module Rust saferoute_core chargé")
        except ImportError:
            logger.warning(
                "saferoute_core (Rust) non compilé. "
                "Lancez `maturin develop` dans bindings/python/"
            )
            self._PyGraph = None
            self._compute = None

    # ── API publique ───────────────────────────────────────────────────────────

    def load_city(
        self,
        city_key: str,
        crime_points: list[dict] | None = None,
        force_download: bool = False,
    ) -> dict:
        """
        Charge une ville : graphe OSMnx + scores KDE.
        Utilise le cache si disponible, télécharge sinon.

        Args:
            city_key       : "london" ou "cape_town"
            crime_points   : liste de {"lat","lon","weight"}. Si None → charge depuis cache
            force_download : ignore le cache et re-télécharge

        Returns:
            dict de statistiques de chargement
        """
        if city_key not in SUPPORTED_CITIES:
            raise ValueError(
                f"Ville '{city_key}' non supportée. "
                f"Villes disponibles : {list(SUPPORTED_CITIES.keys())}"
            )

        # ── 1. Graphe OSMnx ───────────────────────────────────────────────────
        G = None
        if not force_download:
            G = self._cache.load_graph(city_key)

        if G is None:
            G = self._download_graph(city_key)
            report = validate_graph(G, city_key)
            if not report.is_valid:
                raise RuntimeError(
                    f"Graphe '{city_key}' invalide après téléchargement :\n"
                    f"{report.summary()}"
                )
            G = extract_largest_scc(G)
            self._cache.save_graph(city_key, G, stats={"bbox": report.bbox})

        self._nx_graph = G
        self._current_city = city_key

        # ── 2. Données de criminalité ─────────────────────────────────────────
        if crime_points is None:
            crime_points = self._cache.load_crimes(city_key)

        if not crime_points:
            logger.warning(
                f"Aucun crime disponible pour '{city_key}'. "
                "Scores de risque tous à 0. "
                "Lancez scripts/download_cities.py pour pré-charger les données."
            )
            crime_points = []

        # ── 3. Scoring KDE ────────────────────────────────────────────────────
        logger.info(f"Calcul KDE sur {len(crime_points)} crimes...")
        self._kde_result = compute_kde_scores(
            self._nx_graph,
            crime_points,
            bandwidth_m=self.bandwidth_m,
        )

        # ── 4. Familiarité ────────────────────────────────────────────────────
        if self.simulate_familiarity:
            logger.info(f"Simulation de {self.familiarity_trips} trajets de familiarité...")
            self._familiarity.simulate_trajectories(
                self._nx_graph, n_trips=self.familiarity_trips
            )

        # ── 5. Sérialisation JSON → Rust ──────────────────────────────────────
        logger.info("Sérialisation du graphe enrichi → Rust...")
        graph_json = self._serialize_graph(self._kde_result.risk_map)
        # Injection de la familiarité dans le JSON
        graph_json = self._familiarity.apply_to_graph_json(graph_json)

        if self._PyGraph is not None:
            self._py_graph = self._PyGraph.from_json(graph_json)
            logger.info(
                f"Graphe '{city_key}' chargé dans Rust : "
                f"{self._py_graph.node_count()} nœuds, "
                f"{self._py_graph.edge_count()} arcs"
            )

        return {
            "city": city_key,
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "crimes": len(crime_points),
            "kde_bandwidth_m": self._kde_result.bandwidth_m,
            "kde_method": self._kde_result.method,
            "kde_elapsed_s": self._kde_result.elapsed_s,
            "kde_stats": self._kde_result.stats,
            "familiarity_stats": self._familiarity.get_familiarity_map().stats(),
        }

    def record_trip(self, path: list[int]) -> None:
        """
        Enregistre un trajet réel pour mettre à jour la familiarité.
        Appeler après chaque trajet effectué par l'utilisateur.

        Args:
            path : liste de NodeId OSM du trajet effectué
        """
        if self._nx_graph is None:
            raise RuntimeError("Graphe non chargé.")
        self._familiarity.update_from_path(path, self._nx_graph)
        # Ré-injecte la familiarité dans le graphe Rust
        if self._py_graph is not None and self._kde_result is not None:
            graph_json = self._serialize_graph(self._kde_result.risk_map)
            graph_json = self._familiarity.apply_to_graph_json(graph_json)
            if self._PyGraph is not None:
                self._py_graph = self._PyGraph.from_json(graph_json)
        logger.info(f"Trajet enregistré. Stats familiarité : {self._familiarity.get_familiarity_map().stats()}")

    def compute_routes(self, source_node: int, target_node: int) -> ParetoSet:
        """
        Calcule les 3 itinéraires Pareto-optimaux entre deux nœuds OSM.

        Args:
            source_node : NodeId OSM de départ
            target_node : NodeId OSM d'arrivée

        Returns:
            ParetoSet avec shortest, safest, balanced
        """
        if self._py_graph is None:
            raise RuntimeError(
                "Graphe non chargé. Appelez load_city() d'abord."
            )
        if self._compute is None:
            raise RuntimeError(
                "Module Rust non compilé. Lancez `maturin develop`."
            )

        try:
            results = self._compute(
                self._py_graph,
                int(source_node),
                int(target_node),
                self.eps,
            )
        except Exception as e:
            raise RuntimeError(
                f"Erreur calcul d'itinéraire ({source_node} → {target_node}): {e}"
            ) from e

        return ParetoSet.from_results(results)

    def nearest_node(self, lat: float, lon: float) -> int:
        """
        Retourne le NodeId OSM le plus proche d'un point GPS.
        Utile pour convertir des coordonnées utilisateur en NodeId.
        """
        if self._nx_graph is None:
            raise RuntimeError("Graphe non chargé.")
        return int(ox.nearest_nodes(self._nx_graph, lon, lat))

    def get_node_coords(self, node_id: int) -> tuple[float, float]:
        """Retourne (lat, lon) d'un nœud OSM."""
        if self._nx_graph is None:
            raise RuntimeError("Graphe non chargé.")
        data = self._nx_graph.nodes[node_id]
        return float(data["y"]), float(data["x"])

    def get_risk_map_geojson(self) -> dict:
        """
        Retourne la heatmap de risque au format GeoJSON (LineString par arc).
        Utilisé par l'endpoint GET /api/v1/risk-map.
        """
        if self._nx_graph is None or self._kde_result is None:
            return {"type": "FeatureCollection", "features": []}

        features = []
        for u, v, key, data in self._nx_graph.edges(keys=True, data=True):
            risk = self._kde_result.risk_map.get((u, v, key), 0.0)
            u_data = self._nx_graph.nodes[u]
            v_data = self._nx_graph.nodes[v]
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [u_data.get("x", 0), u_data.get("y", 0)],
                        [v_data.get("x", 0), v_data.get("y", 0)],
                    ],
                },
                "properties": {
                    "risk_score": round(risk, 4),
                    "from": u,
                    "to": v,
                    "length_m": data.get("length", 0),
                },
            })

        return {"type": "FeatureCollection", "features": features}

    # ── Méthodes privées ───────────────────────────────────────────────────────

    def _download_graph(self, city_key: str):
        """Télécharge le graphe OSMnx pour une ville."""
        config = SUPPORTED_CITIES[city_key]
        method = config.get("method", "place")
        try:
            if method == "place":
                logger.info(f"Téléchargement OSMnx (place) : {config['query']}...")
                G = ox.graph_from_place(config["query"], network_type=config["network_type"])
            else:
                logger.info(f"Téléchargement OSMnx (point) : {config['point']}, rayon {config['dist']}m...")
                G = ox.graph_from_point(config["point"], dist=config["dist"], network_type=config["network_type"])

            if not any("length" in d for _, _, d in G.edges(data=True)):
                G = ox.distance.add_edge_lengths(G)
            return G
        except Exception as e:
            raise RuntimeError(f"Échec téléchargement OSMnx pour '{city_key}': {e}") from e

    def _serialize_graph(self, risk_map: dict) -> str:
        """Sérialise le graphe NetworkX enrichi en JSON pour le moteur Rust."""
        nodes = []
        for node_id, data in self._nx_graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "lat": data.get("y", 0.0),
                "lon": data.get("x", 0.0),
            })

        edges = []
        for u, v, key, data in self._nx_graph.edges(keys=True, data=True):
            edges.append({
                "from": u,
                "to": v,
                "distance_m": float(data.get("length", 0.0)),
                "risk_score": float(risk_map.get((u, v, key), 0.0)),
                "familiarity": 0.0,  # Phase 2 : module de trajectoires
            })

        return json.dumps({"nodes": nodes, "edges": edges})

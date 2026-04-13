# Fait par Gillesto
# familiarity.py — Module de simulation et calcul de la familiarité utilisateur
#
# La familiarité est le 3ème objectif de la formule :
#   C = w1·Distance + w2·Risque - w3·Familiarité
#
# Une route familière coûte MOINS cher → l'algorithme la préfère à risque égal.
#
# Sources :
#   - Balteanu et al., "Mining Driving Preferences in Multi-cost Networks", 2013
#   - Roadmap SafeRoute : "marquer des routes comme connues et réduire leur coût"
#
# Deux modes :
#   1. Simulation  : génère des trajectoires fictives pour tester la pipeline
#   2. Mise à jour : met à jour les scores depuis des trajectoires GPS réelles

import json
import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FamiliarityMap:
    """
    Carte de familiarité : score [0.0, 1.0] par arc (u, v, key).
    0.0 = jamais emprunté, 1.0 = très familier.
    """
    scores: dict = field(default_factory=dict)  # {(u, v, key): float}
    total_trips: int = 0

    def get(self, u: int, v: int, key: int = 0) -> float:
        return self.scores.get((u, v, key), 0.0)

    def update(self, u: int, v: int, key: int, delta: float = 0.1) -> None:
        """Incrémente le score d'un arc (avec saturation à 1.0)."""
        current = self.scores.get((u, v, key), 0.0)
        self.scores[(u, v, key)] = min(1.0, current + delta)

    def decay(self, factor: float = 0.95) -> None:
        """
        Applique un facteur de décroissance temporelle.
        Les routes non empruntées récemment deviennent moins familières.
        factor=0.95 → perd 5% de familiarité par période.
        """
        self.scores = {k: v * factor for k, v in self.scores.items() if v * factor > 0.01}

    def to_edge_dict(self) -> dict:
        """Retourne {(u, v, key): score} pour injection dans le graphe."""
        return dict(self.scores)

    def stats(self) -> dict:
        if not self.scores:
            return {"count": 0, "mean": 0.0, "max": 0.0, "familiar_edges": 0}
        vals = list(self.scores.values())
        return {
            "count": len(vals),
            "mean": sum(vals) / len(vals),
            "max": max(vals),
            "familiar_edges": sum(1 for v in vals if v > 0.3),
            "total_trips": self.total_trips,
        }


class FamiliarityEngine:
    """
    Moteur de familiarité : calcule et met à jour les scores d'arcs
    à partir de trajectoires utilisateur (réelles ou simulées).
    """

    def __init__(self, decay_per_trip: float = 0.02):
        """
        Args:
            decay_per_trip : décroissance appliquée à chaque nouveau trajet
                             (simule l'oubli progressif des routes peu fréquentées)
        """
        self.decay_per_trip = decay_per_trip
        self._fmap = FamiliarityMap()

    # ── API publique ───────────────────────────────────────────────────────────

    def update_from_path(self, path: list[int], nx_graph) -> None:
        """
        Met à jour la familiarité depuis un chemin (liste de NodeId OSM).

        Args:
            path     : liste de NodeId OSM [n1, n2, n3, ...]
            nx_graph : graphe NetworkX pour trouver les clés d'arcs
        """
        if len(path) < 2:
            return

        # Décroissance légère à chaque nouveau trajet
        if self.decay_per_trip > 0:
            self._fmap.decay(factor=1.0 - self.decay_per_trip)

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # Trouve la clé de l'arc dans le multigraphe
            if nx_graph.has_edge(u, v):
                keys = list(nx_graph[u][v].keys())
                key = keys[0] if keys else 0
                # Incrément inversement proportionnel à la longueur de l'arc
                # (les arcs courts sont "plus familiers" par unité de distance)
                length = nx_graph[u][v][key].get("length", 100.0)
                delta = min(0.15, 100.0 / max(length, 1.0))
                self._fmap.update(u, v, key, delta)

        self._fmap.total_trips += 1
        # Ne pas loguer les stats détaillées (données de mobilité utilisateur)
        logger.debug("Trajet enregistré : %d nœuds", len(path))

    def simulate_trajectories(
        self,
        nx_graph,
        n_trips: int = 50,
        seed: int = 42,
    ) -> FamiliarityMap:
        """
        Génère des trajectoires fictives pour simuler un utilisateur habitué
        à certains corridors de la ville.

        Stratégie :
        - Sélectionne aléatoirement N paires (source, destination)
        - Calcule le plus court chemin NetworkX (proxy pour le comportement réel)
        - Met à jour la familiarité pour chaque arc emprunté

        Args:
            nx_graph : graphe NetworkX OSMnx
            n_trips  : nombre de trajets simulés
            seed     : graine pour reproductibilité

        Returns:
            FamiliarityMap mise à jour
        """
        import networkx as nx

        rng = random.Random(seed)
        nodes = list(nx_graph.nodes())

        if len(nodes) < 2:
            logger.warning("Graphe trop petit pour simuler des trajectoires")
            return self._fmap

        successful = 0
        for _ in range(n_trips):
            src = rng.choice(nodes)
            dst = rng.choice(nodes)
            if src == dst:
                continue

            try:
                # Plus court chemin par longueur (comportement utilisateur naïf)
                path = nx.shortest_path(nx_graph, src, dst, weight="length")
                self.update_from_path(path, nx_graph)
                successful += 1
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        logger.info(
            f"Simulation : {successful}/{n_trips} trajets réussis | "
            f"stats={self._fmap.stats()}"
        )
        return self._fmap

    def get_familiarity_map(self) -> FamiliarityMap:
        return self._fmap

    def apply_to_graph_json(self, graph_json: str) -> str:
        """
        Injecte les scores de familiarité dans le JSON du graphe
        avant envoi au moteur Rust.

        Args:
            graph_json : JSON produit par engine._serialize_graph()

        Returns:
            JSON enrichi avec les scores de familiarité
        """
        data = json.loads(graph_json)
        fmap = self._fmap.scores

        updated = 0
        for edge in data.get("edges", []):
            key = (edge["from"], edge["to"], 0)
            score = fmap.get(key, 0.0)
            if score > 0:
                edge["familiarity"] = round(score, 4)
                updated += 1

        logger.debug(f"Familiarité injectée : {updated}/{len(data.get('edges', []))} arcs")
        return json.dumps(data)

    def save(self, path: Path | str) -> None:
        """Sauvegarde la carte de familiarité en JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_trips": self._fmap.total_trips,
            # Clé : "u|v|k" avec séparateur | pour éviter les ambiguïtés
            "scores": {f"{int(u)}|{int(v)}|{int(k)}": v
                       for (u, v, k), v in self._fmap.scores.items()},
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"Familiarité sauvegardée : {len(self._fmap.scores)} arcs → {path}")

    def load(self, path: Path | str) -> None:
        """Charge une carte de familiarité depuis JSON."""
        path = Path(path)
        if not path.exists():
            logger.warning(f"Fichier de familiarité introuvable : {path}")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._fmap.total_trips = data.get("total_trips", 0)
        self._fmap.scores = {}
        for key_str, val in data.get("scores", {}).items():
            parts = key_str.split("|")
            if len(parts) == 3:
                try:
                    u, v, k = int(parts[0]), int(parts[1]), int(parts[2])
                    self._fmap.scores[(u, v, k)] = float(val)
                except ValueError:
                    continue
        logger.info(f"Familiarité chargée : {len(self._fmap.scores)} arcs depuis {path}")

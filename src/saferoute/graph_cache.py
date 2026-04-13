# Fait par Gillesto
# graph_cache.py — Cache local des graphes OSMnx et des données de criminalité
#
# Stratégie :
#   - Graphe OSMnx  → fichier .graphml (format natif NetworkX, fidèle aux attributs OSM)
#   - Crimes        → fichier .csv.gz   (compressé, lecture rapide avec pandas)
#   - Métadonnées   → fichier .json     (date de téléchargement, stats de validation)
#
# Pourquoi .graphml et pas .pkl ?
#   .pkl est lié à la version Python/NetworkX → risque de corruption entre envs.
#   .graphml est un standard XML portable et lisible par QGIS/Gephi.

import gzip
import json
import logging
import os
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import osmnx as ox

from .exceptions import CacheCorruptionError

logger = logging.getLogger(__name__)


def _default_cache_dir() -> Path:
    """Retourne le répertoire de cache par défaut.

    Priorité :
    1. Variable d'environnement ``SAFEROUTE_CACHE_DIR``
    2. ``platformdirs.user_cache_dir("saferoute")`` (ex: ~/.cache/saferoute)

    Returns:
        Chemin vers le répertoire de cache.
    """
    env = os.environ.get("SAFEROUTE_CACHE_DIR")
    if env:
        return Path(env)
    try:
        from platformdirs import user_cache_dir
        return Path(user_cache_dir("saferoute"))
    except ImportError:
        return Path.home() / ".cache" / "saferoute"


class GraphCache:
    """
    Gestionnaire de cache pour les graphes OSMnx et les données de criminalité.

    Usage :
        cache = GraphCache()
        G = cache.load_graph("london") or cache.save_graph("london", G)
        crimes = cache.load_crimes("london") or cache.save_crimes("london", crimes)
    """

    def __init__(self, cache_dir: Path | str | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache initialisé dans : {self.cache_dir}")

    # ── Graphe OSMnx ──────────────────────────────────────────────────────────

    def graph_path(self, city_key: str) -> Path:
        """Retourne le chemin du fichier .graphml pour une ville."""
        return self.cache_dir / f"{city_key}_graph.graphml"

    def meta_path(self, city_key: str) -> Path:
        return self.cache_dir / f"{city_key}_meta.json"

    def has_graph(self, city_key: str) -> bool:
        return self.graph_path(city_key).exists()

    def save_graph(self, city_key: str, G, stats: dict | None = None) -> None:
        """
        Sauvegarde un graphe NetworkX en .graphml + métadonnées JSON.

        Args:
            city_key : identifiant court ex. "london", "cape_town"
            G        : graphe NetworkX (MultiDiGraph OSMnx)
            stats    : dict optionnel de statistiques de validation
        """
        path = self.graph_path(city_key)
        ox.save_graphml(G, filepath=str(path))

        meta = {
            "city_key": city_key,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "stats": stats or {},
        }
        self.meta_path(city_key).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        logger.info(
            f"Graphe '{city_key}' sauvegardé : "
            f"{meta['node_count']} nœuds, {meta['edge_count']} arcs → {path}"
        )

    def load_graph(self, city_key: str):
        """
        Charge un graphe depuis le cache .graphml.
        Retourne None si le cache n'existe pas.
        """
        path = self.graph_path(city_key)
        if not path.exists():
            return None
        logger.info(f"Chargement graphe '{city_key}' depuis le cache...")
        try:
            G = ox.load_graphml(filepath=str(path))
        except Exception as e:
            logger.error(f"Cache corrompu pour '{city_key}' : {e} — suppression du fichier")
            path.unlink(missing_ok=True)
            self.meta_path(city_key).unlink(missing_ok=True)
            raise CacheCorruptionError(path, str(e)) from e
        meta = self._load_meta(city_key)
        if meta:
            logger.info(
                f"Cache '{city_key}' : {meta.get('node_count')} nœuds, "
                f"{meta.get('edge_count')} arcs (téléchargé le {meta.get('downloaded_at', '?')})"
            )
        return G

    def _load_meta(self, city_key: str) -> dict | None:
        path = self.meta_path(city_key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ── Données de criminalité ─────────────────────────────────────────────────

    def crimes_path(self, city_key: str) -> Path:
        return self.cache_dir / f"{city_key}_crimes.csv.gz"

    def has_crimes(self, city_key: str) -> bool:
        return self.crimes_path(city_key).exists()

    def save_crimes(self, city_key: str, crimes: list[dict]) -> None:
        """
        Sauvegarde une liste de crimes en CSV compressé gzip.
        Chaque entrée : {"lat": float, "lon": float, "weight": float}
        """
        path = self.crimes_path(city_key)
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["lat", "lon", "weight"])
            writer.writeheader()
            writer.writerows(crimes)
        logger.info(f"Crimes '{city_key}' sauvegardés : {len(crimes)} entrées → {path}")

    def load_crimes(self, city_key: str) -> list[dict] | None:
        """
        Charge les crimes depuis le cache CSV.gz.
        Retourne None si le cache n'existe pas.
        """
        path = self.crimes_path(city_key)
        if not path.exists():
            return None
        crimes = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    crimes.append({
                        "lat": float(row["lat"]),
                        "lon": float(row["lon"]),
                        "weight": float(row["weight"]),
                    })
                except (KeyError, ValueError):
                    continue
        logger.info(f"Crimes '{city_key}' chargés depuis le cache : {len(crimes)} entrées")
        return crimes

    def cache_info(self) -> dict:
        """Retourne un résumé de l'état du cache."""
        info = {}
        for meta_file in self.cache_dir.glob("*_meta.json"):
            city_key = meta_file.stem.replace("_meta", "")
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            crimes_path = self.crimes_path(city_key)
            info[city_key] = {
                "graph": meta,
                "crimes_cached": crimes_path.exists(),
                "crimes_size_kb": round(crimes_path.stat().st_size / 1024, 1)
                if crimes_path.exists() else 0,
            }
        return info

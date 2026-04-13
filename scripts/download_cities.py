# Fait par Gillesto
# download_cities.py — Script de téléchargement et validation des graphes OSMnx
#
# Usage :
#   python scripts/download_cities.py                    # télécharge les deux villes
#   python scripts/download_cities.py --city london      # Londres seulement
#   python scripts/download_cities.py --city cape_town   # Le Cap seulement
#   python scripts/download_cities.py --force            # re-télécharge même si en cache
#   python scripts/download_cities.py --offline          # génère des données de test locales
#   python scripts/download_cities.py --timeout 120      # timeout réseau en secondes
#
# En cas d'erreur réseau, utilisez --offline pour générer un graphe synthétique
# permettant de tester toute la pipeline sans connexion internet.

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ajoute src/ au path pour les imports (structure src-layout)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("download_cities")

from saferoute.graph_cache import GraphCache
from saferoute.graph_validator import validate_graph, extract_largest_scc
from saferoute.data_loader import fetch_london_crimes, fetch_cape_town_crimes, validate_crimes


# ── Configuration OSMnx ───────────────────────────────────────────────────────

CITIES = {
    "london": {
        "method": "place",
        "query": "Greater London, United Kingdom",
        "network_type": "walk",
    },
    "cape_town": {
        # Nominatim ne retourne pas de polygone pour "Cape Town" →
        # on utilise graph_from_point avec le centre GPS + rayon 20km
        "method": "point",
        "point": (-33.9249, 18.4241),  # centre de Cape Town CBD
        "dist": 20000,                  # 20 km de rayon
        "network_type": "walk",
    },
}


def _configure_osmnx(timeout: int) -> None:
    """Configure OSMnx avec timeout personnalisé."""
    import osmnx as ox
    # ox.settings.timeout suffit — OSMnx le passe lui-même à requests.
    # NE PAS mettre timeout dans requests_kwargs en même temps, sinon
    # requests reçoit timeout deux fois → "multiple values for keyword argument 'timeout'"
    ox.settings.timeout = timeout
    ox.settings.max_query_area_size = 25_000_000_000
    ox.settings.nominatim_endpoint = "https://nominatim.openstreetmap.org/"
    ox.settings.overpass_endpoint = "https://overpass-api.de/api/"
    logger.info(f"OSMnx configuré : timeout={timeout}s")


# ── Téléchargement avec retry ─────────────────────────────────────────────────

def _download_with_retry(city_key: str, config: dict, max_retries: int = 3, timeout: int = 300):
    """Télécharge un graphe OSMnx avec retry exponentiel.
    Supporte deux méthodes : 'place' (polygone Nominatim) et 'point' (rayon GPS).
    """
    import osmnx as ox

    method = config.get("method", "place")

    for attempt in range(1, max_retries + 1):
        try:
            if method == "place":
                query = config["query"]
                logger.info(f"Tentative {attempt}/{max_retries} : {query}")
                G = ox.graph_from_place(query, network_type=config["network_type"])
            else:  # point
                point = config["point"]
                dist = config["dist"]
                logger.info(f"Tentative {attempt}/{max_retries} : point {point}, rayon {dist}m")
                G = ox.graph_from_point(point, dist=dist, network_type=config["network_type"])

            # OSMnx v2+ calcule les longueurs automatiquement — add_edge_lengths supprimé
            if not any("length" in d for _, _, d in G.edges(data=True)):
                G = ox.distance.add_edge_lengths(G)
            return G

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"Tentative {attempt} échouée : {e}")
            if attempt < max_retries:
                logger.info(f"Nouvelle tentative dans {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Échec après {max_retries} tentatives pour '{city_key}'.\n"
                    f"Dernière erreur : {e}\n"
                    f"→ Vérifiez votre connexion internet ou utilisez --offline"
                ) from e


# ── Mode offline : graphe synthétique ────────────────────────────────────────

def _build_synthetic_graph(city_key: str):
    """
    Construit un graphe synthétique réaliste pour tests offline.
    Simule une grille de rues 10×10 avec coordonnées GPS réelles.
    """
    import networkx as nx
    import math

    # Centres GPS des deux villes
    centers = {
        "london":    (51.5074, -0.1278),
        "cape_town": (-33.9249, 18.4241),
    }
    lat0, lon0 = centers.get(city_key, (51.5, -0.1))

    # Espacement entre nœuds : ~200m en degrés
    dlat = 200 / 111_000
    dlon = 200 / (111_000 * math.cos(math.radians(lat0)))

    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    G.graph["name"] = f"Synthetic {city_key}"

    grid_size = 10  # grille 10×10 = 100 nœuds
    node_id = 1000

    # Création des nœuds
    node_grid = {}
    for i in range(grid_size):
        for j in range(grid_size):
            nid = node_id + i * grid_size + j
            lat = lat0 + i * dlat
            lon = lon0 + j * dlon
            G.add_node(nid, y=lat, x=lon, osmid=nid, street_count=4)
            node_grid[(i, j)] = nid

    # Création des arcs (grille bidirectionnelle)
    for i in range(grid_size):
        for j in range(grid_size):
            u = node_grid[(i, j)]
            # Arc horizontal
            if j + 1 < grid_size:
                v = node_grid[(i, j + 1)]
                length = dlon * 111_000 * math.cos(math.radians(lat0))
                G.add_edge(u, v, key=0, length=length, name=f"Street_{i}", highway="residential")
                G.add_edge(v, u, key=0, length=length, name=f"Street_{i}", highway="residential")
            # Arc vertical
            if i + 1 < grid_size:
                v = node_grid[(i + 1, j)]
                length = dlat * 111_000
                G.add_edge(u, v, key=0, length=length, name=f"Avenue_{j}", highway="residential")
                G.add_edge(v, u, key=0, length=length, name=f"Avenue_{j}", highway="residential")

    logger.info(
        f"Graphe synthétique '{city_key}' : "
        f"{G.number_of_nodes()} nœuds, {G.number_of_edges()} arcs"
    )
    return G


def _build_synthetic_crimes(city_key: str) -> list[dict]:
    """Génère des crimes synthétiques pour tests offline."""
    import random
    import math

    centers = {
        "london":    (51.5074, -0.1278),
        "cape_town": (-33.9249, 18.4241),
    }
    lat0, lon0 = centers.get(city_key, (51.5, -0.1))
    rng = random.Random(42)

    crimes = []
    # 3 hotspots de criminalité
    hotspots = [
        (lat0 + 0.005, lon0 + 0.005, 3.0),
        (lat0 + 0.010, lon0 - 0.003, 2.0),
        (lat0 - 0.002, lon0 + 0.008, 1.5),
    ]
    for hlat, hlon, weight in hotspots:
        for _ in range(100):
            crimes.append({
                "lat": rng.gauss(hlat, 0.002),
                "lon": rng.gauss(hlon, 0.002),
                "weight": weight,
            })

    logger.info(f"Crimes synthétiques '{city_key}' : {len(crimes)} points")
    return crimes


# ── Fonctions principales ─────────────────────────────────────────────────────

async def download_london(cache: GraphCache, force: bool, offline: bool, timeout: int) -> bool:
    city_key = "london"

    # ── Graphe ────────────────────────────────────────────────────────────────
    if cache.has_graph(city_key) and not force:
        logger.info("Graphe Londres déjà en cache.")
        G = cache.load_graph(city_key)
    elif offline:
        logger.info("Mode offline : génération du graphe synthétique Londres...")
        G = _build_synthetic_graph(city_key)
        cache.save_graph(city_key, G, stats={"mode": "synthetic"})
    else:
        try:
            G = _download_with_retry(
                "london",
                CITIES["london"],
                timeout=timeout,
            )
        except RuntimeError as e:
            logger.error(str(e))
            return False

        report = validate_graph(G, city_key)
        if not report.is_valid:
            logger.error(f"Graphe Londres invalide :\n{report.summary()}")
            return False

        G = extract_largest_scc(G)
        cache.save_graph(city_key, G, stats={
            "scc_ratio": report.largest_scc_ratio,
            "bbox": report.bbox,
        })

    # ── Crimes ────────────────────────────────────────────────────────────────
    if cache.has_crimes(city_key) and not force:
        logger.info("Crimes Londres déjà en cache.")
    elif offline:
        logger.info("Mode offline : génération des crimes synthétiques Londres...")
        crimes = _build_synthetic_crimes(city_key)
        cache.save_crimes(city_key, crimes)
    else:
        logger.info("Récupération des crimes de Londres via Police UK API...")
        crimes_raw = await fetch_london_crimes(months=["2024-01", "2024-02", "2024-03"])

        if not crimes_raw:
            logger.warning("Aucun crime récupéré — vérifiez la connexion réseau")
            return False

        G_loaded = cache.load_graph(city_key)
        lats = [d.get("y", 0) for _, d in G_loaded.nodes(data=True)]
        lons = [d.get("x", 0) for _, d in G_loaded.nodes(data=True)]
        bbox = {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        }
        crimes_valid, stats = validate_crimes(crimes_raw, bbox, city_key)
        logger.info(f"Validation crimes Londres : {stats}")
        cache.save_crimes(city_key, crimes_valid)

    logger.info("✅ Londres : graphe + crimes prêts")
    return True


async def download_cape_town(cache: GraphCache, force: bool, offline: bool, timeout: int) -> bool:
    city_key = "cape_town"

    # ── Graphe ────────────────────────────────────────────────────────────────
    if cache.has_graph(city_key) and not force:
        logger.info("Graphe Le Cap déjà en cache.")
        G = cache.load_graph(city_key)
    elif offline:
        logger.info("Mode offline : génération du graphe synthétique Le Cap...")
        G = _build_synthetic_graph(city_key)
        cache.save_graph(city_key, G, stats={"mode": "synthetic"})
    else:
        try:
            G = _download_with_retry(
                "cape_town",
                CITIES["cape_town"],
                timeout=timeout,
            )
        except RuntimeError as e:
            logger.error(str(e))
            return False

        report = validate_graph(G, city_key)
        if not report.is_valid:
            logger.error(f"Graphe Le Cap invalide :\n{report.summary()}")
            return False

        G = extract_largest_scc(G)
        cache.save_graph(city_key, G, stats={
            "scc_ratio": report.largest_scc_ratio,
            "bbox": report.bbox,
        })

    # ── Crimes ────────────────────────────────────────────────────────────────
    if cache.has_crimes(city_key) and not force:
        logger.info("Crimes Le Cap déjà en cache.")
    else:
        if offline:
            crimes_raw = _build_synthetic_crimes(city_key)
        else:
            logger.info("Génération des points de criminalité Le Cap (données SAPS)...")
            crimes_raw = fetch_cape_town_crimes(radius_m=1500.0, points_per_station=80)

        G_loaded = cache.load_graph(city_key)
        lats = [d.get("y", 0) for _, d in G_loaded.nodes(data=True)]
        lons = [d.get("x", 0) for _, d in G_loaded.nodes(data=True)]
        bbox = {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        }
        crimes_valid, stats = validate_crimes(crimes_raw, bbox, city_key)
        logger.info(f"Validation crimes Le Cap : {stats}")
        cache.save_crimes(city_key, crimes_valid)

    logger.info("✅ Le Cap : graphe + crimes prêts")
    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Télécharge et valide les graphes OSMnx pour SafeRoute"
    )
    parser.add_argument(
        "--city", choices=["london", "cape_town", "both"], default="both",
        help="Ville à télécharger (défaut: both)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-télécharge même si le cache existe",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Génère des données synthétiques sans connexion internet (pour tests)",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Timeout réseau en secondes (défaut: 300)",
    )
    parser.add_argument(
        "--cache-dir", type=str, default=None,
        help="Répertoire de cache (défaut: data/cache/)",
    )
    args = parser.parse_args()

    _configure_osmnx(args.timeout)
    cache = GraphCache(cache_dir=args.cache_dir) if args.cache_dir else GraphCache()

    if args.offline:
        logger.info("⚠️  Mode OFFLINE activé — données synthétiques uniquement")

    success = True
    if args.city in ("london", "both"):
        ok = await download_london(cache, args.force, args.offline, args.timeout)
        success = success and ok

    if args.city in ("cape_town", "both"):
        ok = await download_cape_town(cache, args.force, args.offline, args.timeout)
        success = success and ok

    logger.info("\n=== État du cache ===")
    for ck, info in cache.cache_info().items():
        meta = info["graph"]
        logger.info(
            f"  {ck}: {meta.get('node_count')} nœuds, {meta.get('edge_count')} arcs | "
            f"crimes={'✅' if info['crimes_cached'] else '❌'} ({info['crimes_size_kb']} KB)"
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

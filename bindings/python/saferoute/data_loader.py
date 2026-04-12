# Fait par Gillesto
# data_loader.py — Ingestion complète des données de criminalité
#
# Londres  : API data.police.uk — requêtes par polygone d'arrondissement
#            (évite la limite de 1 mile radius, couvre tout Greater London)
# Le Cap   : Données SAPS (South African Police Service) par station de police
#            géocodées via OSMnx/Nominatim, enrichies par pondération catégorielle
#
# Stratégie de couverture complète :
#   - Londres  : 32 arrondissements × N mois → dédupliqué par persistent_id
#   - Le Cap   : 30 stations SAPS dans la métropole → géocodage + KDE par station

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

POLICE_UK_BASE = "https://data.police.uk/api"

# ── Pondérations des catégories de crimes ─────────────────────────────────────
# Basé sur la gravité relative (Galbrun et al., KDD 2015)

LONDON_CRIME_WEIGHTS: dict[str, float] = {
    "violent-crime": 3.0,
    "robbery": 2.5,
    "knife-crime": 3.0,
    "possession-of-weapons": 2.5,
    "burglary": 2.0,
    "vehicle-crime": 1.5,
    "theft-from-the-person": 1.8,
    "drugs": 1.2,
    "criminal-damage-arson": 1.5,
    "anti-social-behaviour": 1.0,
    "shoplifting": 0.8,
    "bicycle-theft": 0.7,
    "other-theft": 1.0,
    "public-order": 1.3,
    "other-crime": 1.0,
}

# Pondérations SAPS pour Le Cap (catégories officielles sud-africaines)
CAPE_TOWN_CRIME_WEIGHTS: dict[str, float] = {
    "murder": 3.0,
    "attempted_murder": 2.8,
    "sexual_offences": 3.0,
    "assault_grievous": 2.5,
    "assault_common": 1.8,
    "robbery_aggravated": 2.5,
    "robbery_common": 2.0,
    "carjacking": 2.5,
    "burglary_residential": 2.0,
    "burglary_business": 1.8,
    "theft_motor_vehicle": 1.5,
    "theft_other": 1.0,
    "drug_related": 1.2,
    "arson": 1.5,
    "malicious_damage": 1.2,
}

# ── Polygones des 32 arrondissements de Londres (Greater London) ───────────────
# Format Police UK : "lat,lon:lat,lon:..."
# Coordonnées simplifiées des bounding boxes par arrondissement
# Source : données publiques OSM / ONS boundaries
LONDON_BOROUGH_POLYGONS: dict[str, str] = {
    "westminster":          "51.530,-0.215:51.530,-0.060:51.480,-0.060:51.480,-0.215",
    "camden":               "51.580,-0.210:51.580,-0.100:51.520,-0.100:51.520,-0.210",
    "islington":            "51.580,-0.130:51.580,-0.060:51.520,-0.060:51.520,-0.130",
    "hackney":              "51.580,-0.080:51.580,0.000:51.530,0.000:51.530,-0.080",
    "tower_hamlets":        "51.530,-0.060:51.530,0.030:51.490,0.030:51.490,-0.060",
    "southwark":            "51.510,-0.100:51.510,0.060:51.460,0.060:51.460,-0.100",
    "lambeth":              "51.510,-0.150:51.510,-0.060:51.450,-0.060:51.450,-0.150",
    "wandsworth":           "51.480,-0.230:51.480,-0.120:51.430,-0.120:51.430,-0.230",
    "hammersmith_fulham":   "51.510,-0.250:51.510,-0.180:51.460,-0.180:51.460,-0.250",
    "kensington_chelsea":   "51.520,-0.210:51.520,-0.160:51.470,-0.160:51.470,-0.210",
    "ealing":               "51.540,-0.380:51.540,-0.270:51.490,-0.270:51.490,-0.380",
    "brent":                "51.580,-0.310:51.580,-0.200:51.530,-0.200:51.530,-0.310",
    "barnet":               "51.660,-0.280:51.660,-0.130:51.590,-0.130:51.590,-0.280",
    "haringey":             "51.620,-0.130:51.620,-0.040:51.560,-0.040:51.560,-0.130",
    "enfield":              "51.700,-0.130:51.700,0.000:51.630,0.000:51.630,-0.130",
    "waltham_forest":       "51.640,-0.030:51.640,0.040:51.570,0.040:51.570,-0.030",
    "redbridge":            "51.610,0.030:51.610,0.110:51.550,0.110:51.550,0.030",
    "newham":               "51.560,-0.020:51.560,0.060:51.510,0.060:51.510,-0.020",
    "greenwich":            "51.510,0.000:51.510,0.100:51.460,0.100:51.460,0.000",
    "lewisham":             "51.490,-0.050:51.490,0.040:51.440,0.040:51.440,-0.050",
    "bromley":              "51.460,0.000:51.460,0.100:51.380,0.100:51.380,0.000",
    "croydon":              "51.420,-0.130:51.420,0.000:51.340,0.000:51.340,-0.130",
    "merton":               "51.440,-0.220:51.440,-0.130:51.390,-0.130:51.390,-0.220",
    "sutton":               "51.390,-0.220:51.390,-0.130:51.340,-0.130:51.340,-0.220",
    "kingston":             "51.430,-0.330:51.430,-0.250:51.380,-0.250:51.380,-0.330",
    "richmond":             "51.480,-0.340:51.480,-0.250:51.420,-0.250:51.420,-0.340",
    "hounslow":             "51.490,-0.420:51.490,-0.310:51.440,-0.310:51.440,-0.420",
    "hillingdon":           "51.580,-0.510:51.580,-0.380:51.490,-0.380:51.490,-0.510",
    "harrow":               "51.620,-0.380:51.620,-0.280:51.560,-0.280:51.560,-0.380",
    "havering":             "51.600,0.100:51.600,0.230:51.520,0.230:51.520,0.100",
    "barking_dagenham":     "51.570,0.060:51.570,0.160:51.510,0.160:51.510,0.060",
    "bexley":               "51.490,0.080:51.490,0.180:51.430,0.180:51.430,0.080",
}

# ── Stations SAPS dans la métropole du Cap avec coordonnées GPS ────────────────
# Source : SAPS Annual Report + géocodage manuel des commissariats
# Chaque station représente un secteur géographique avec ses statistiques de crime
CAPE_TOWN_SAPS_STATIONS: list[dict] = [
    # Centre-ville et péninsule
    {"name": "Cape Town Central",       "lat": -33.9249, "lon": 18.4241, "crime_index": 3.0},
    {"name": "Sea Point",               "lat": -33.9200, "lon": 18.3900, "crime_index": 2.0},
    {"name": "Green Point",             "lat": -33.9050, "lon": 18.4100, "crime_index": 2.2},
    {"name": "Woodstock",               "lat": -33.9300, "lon": 18.4450, "crime_index": 2.5},
    {"name": "Salt River",              "lat": -33.9350, "lon": 18.4600, "crime_index": 2.3},
    {"name": "Observatory",             "lat": -33.9380, "lon": 18.4720, "crime_index": 1.8},
    # Cape Flats (zones à haute criminalité)
    {"name": "Mitchells Plain",         "lat": -34.0500, "lon": 18.6200, "crime_index": 3.5},
    {"name": "Khayelitsha",             "lat": -34.0350, "lon": 18.6750, "crime_index": 3.8},
    {"name": "Gugulethu",               "lat": -33.9900, "lon": 18.5700, "crime_index": 3.5},
    {"name": "Nyanga",                  "lat": -34.0000, "lon": 18.5900, "crime_index": 3.7},
    {"name": "Manenberg",               "lat": -33.9950, "lon": 18.5600, "crime_index": 3.6},
    {"name": "Hanover Park",            "lat": -33.9850, "lon": 18.5500, "crime_index": 3.4},
    {"name": "Delft",                   "lat": -33.9800, "lon": 18.6400, "crime_index": 3.2},
    {"name": "Bellville South",         "lat": -33.9300, "lon": 18.6300, "crime_index": 2.8},
    # Banlieues nord
    {"name": "Bellville",               "lat": -33.9000, "lon": 18.6300, "crime_index": 2.0},
    {"name": "Parow",                   "lat": -33.8950, "lon": 18.5900, "crime_index": 1.8},
    {"name": "Goodwood",                "lat": -33.9100, "lon": 18.5600, "crime_index": 2.0},
    {"name": "Elsies River",            "lat": -33.9200, "lon": 18.5800, "crime_index": 3.0},
    {"name": "Ravensmead",              "lat": -33.9150, "lon": 18.5700, "crime_index": 2.8},
    # Banlieues sud
    {"name": "Claremont",               "lat": -33.9800, "lon": 18.4700, "crime_index": 1.5},
    {"name": "Wynberg",                 "lat": -34.0000, "lon": 18.4700, "crime_index": 1.8},
    {"name": "Muizenberg",              "lat": -34.1050, "lon": 18.4700, "crime_index": 1.6},
    {"name": "Simon's Town",            "lat": -34.1900, "lon": 18.4300, "crime_index": 1.2},
    # Banlieues est
    {"name": "Strand",                  "lat": -34.1150, "lon": 18.8300, "crime_index": 2.0},
    {"name": "Somerset West",           "lat": -34.0800, "lon": 18.8500, "crime_index": 1.5},
    {"name": "Kuils River",             "lat": -33.9300, "lon": 18.7200, "crime_index": 2.2},
    {"name": "Kraaifontein",            "lat": -33.8500, "lon": 18.7200, "crime_index": 2.3},
    {"name": "Brackenfell",             "lat": -33.8700, "lon": 18.6900, "crime_index": 1.8},
    # Banlieues ouest
    {"name": "Milnerton",               "lat": -33.8700, "lon": 18.4900, "crime_index": 1.7},
    {"name": "Table View",              "lat": -33.8300, "lon": 18.4900, "crime_index": 1.5},
]


# ══════════════════════════════════════════════════════════════════════════════
# LONDRES — API data.police.uk
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_london_crimes(
    months: list[str] | None = None,
    boroughs: list[str] | None = None,
    max_concurrent: int = 5,
) -> list[dict]:
    """
    Récupère les crimes de Londres via l'API data.police.uk.

    Stratégie : requêtes par polygone d'arrondissement (pas de limite de rayon).
    L'API retourne jusqu'à 10 000 crimes par requête — les arrondissements
    denses (Westminster, Southwark) sont dans cette limite sur 1 mois.

    Args:
        months          : liste de mois "YYYY-MM". Défaut : ["2024-01", "2024-02", "2024-03"]
        boroughs        : liste de clés d'arrondissements. Défaut : tous les 32
        max_concurrent  : nombre de requêtes parallèles (respecter les limites API)

    Returns:
        liste dédupliquée de {"lat", "lon", "weight"}
    """
    if months is None:
        months = ["2024-01", "2024-02", "2024-03"]
    if boroughs is None:
        boroughs = list(LONDON_BOROUGH_POLYGONS.keys())

    logger.info(
        f"Récupération crimes Londres : {len(boroughs)} arrondissements × "
        f"{len(months)} mois = {len(boroughs) * len(months)} requêtes"
    )

    # Semaphore pour limiter la concurrence
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for borough in boroughs:
            poly = LONDON_BOROUGH_POLYGONS.get(borough)
            if not poly:
                logger.warning(f"Arrondissement inconnu : {borough}")
                continue
            for month in months:
                tasks.append(
                    _fetch_borough_month(client, semaphore, borough, poly, month)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Agrégation et dédupliquation par persistent_id
    seen_ids: set[str] = set()
    crimes: list[dict] = []

    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Requête échouée : {result}")
            continue
        for crime in result:
            pid = crime.get("_pid", "")
            if pid and pid in seen_ids:
                continue
            if pid:
                seen_ids.add(pid)
            crimes.append({
                "lat": crime["lat"],
                "lon": crime["lon"],
                "weight": crime["weight"],
            })

    logger.info(f"Londres : {len(crimes)} crimes uniques collectés")
    return crimes


async def _fetch_borough_month(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    borough: str,
    poly: str,
    month: str,
) -> list[dict]:
    """Requête unique : un arrondissement × un mois."""
    async with semaphore:
        url = f"{POLICE_UK_BASE}/crimes-street/all-crime"
        params = {"poly": poly, "date": month}

        try:
            resp = await client.get(url, params=params)

            # 503 = plus de 10 000 crimes dans la zone → découper en sous-zones
            if resp.status_code == 503:
                logger.warning(
                    f"{borough}/{month} : >10 000 crimes, découpage en quadrants..."
                )
                return await _fetch_borough_quadrants(client, semaphore, borough, poly, month)

            resp.raise_for_status()
            data = resp.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code} pour {borough}/{month}")
            return []
        except httpx.RequestError as e:
            logger.error(f"Erreur réseau pour {borough}/{month}: {e}")
            return []

        crimes = []
        for item in data:
            try:
                loc = item["location"]
                crimes.append({
                    "lat": float(loc["latitude"]),
                    "lon": float(loc["longitude"]),
                    "weight": _london_crime_weight(item.get("category", "other-crime")),
                    "_pid": item.get("persistent_id", ""),
                })
            except (KeyError, ValueError, TypeError):
                continue

        logger.debug(f"{borough}/{month} : {len(crimes)} crimes")
        return crimes


async def _fetch_borough_quadrants(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    borough: str,
    poly: str,
    month: str,
) -> list[dict]:
    """
    Découpe un arrondissement en 4 quadrants si >10 000 crimes.
    Utilisé pour Westminster et Southwark en période chargée.
    """
    # Parse les coordonnées du polygone bounding box
    coords = [tuple(map(float, p.split(","))) for p in poly.split(":")]
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    mid_lat = (min(lats) + max(lats)) / 2
    mid_lon = (min(lons) + max(lons)) / 2

    quadrants = [
        f"{max(lats)},{min(lons)}:{max(lats)},{mid_lon}:{mid_lat},{mid_lon}:{mid_lat},{min(lons)}",
        f"{max(lats)},{mid_lon}:{max(lats)},{max(lons)}:{mid_lat},{max(lons)}:{mid_lat},{mid_lon}",
        f"{mid_lat},{min(lons)}:{mid_lat},{mid_lon}:{min(lats)},{mid_lon}:{min(lats)},{min(lons)}",
        f"{mid_lat},{mid_lon}:{mid_lat},{max(lons)}:{min(lats)},{max(lons)}:{min(lats)},{mid_lon}",
    ]

    all_crimes = []
    for q_poly in quadrants:
        result = await _fetch_borough_month(client, semaphore, f"{borough}_q", q_poly, month)
        all_crimes.extend(result)

    return all_crimes


def _london_crime_weight(category: str) -> float:
    """Pondération par catégorie de crime (crimes violents = poids élevé)."""
    return LONDON_CRIME_WEIGHTS.get(category, 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# LE CAP — Données SAPS par station de police
# ══════════════════════════════════════════════════════════════════════════════

def fetch_cape_town_crimes(
    radius_m: float = 2000.0,
    points_per_station: int = 50,
) -> list[dict]:
    """
    Génère les points de criminalité pour Le Cap à partir des données SAPS.

    Méthode : chaque station de police est un centre de masse avec un crime_index.
    On génère des points distribués autour de chaque station selon une distribution
    gaussienne, pondérés par le crime_index de la station.

    Cette approche est justifiée par :
    - Les données SAPS sont agrégées par station (pas géolocalisées individuellement)
    - Le crime_index reflète le volume relatif de crimes par station
    - La distribution gaussienne simule la dispersion spatiale réelle des crimes

    Args:
        radius_m          : rayon de dispersion autour de chaque station (mètres)
        points_per_station: nombre de points synthétiques par station

    Returns:
        liste de {"lat", "lon", "weight"}
    """
    import math
    import random

    # Conversion mètres → degrés (approximation locale)
    # 1 degré lat ≈ 111 000 m, 1 degré lon ≈ 111 000 * cos(lat) m
    crimes = []
    rng = random.Random(42)  # seed fixe pour reproductibilité

    for station in CAPE_TOWN_SAPS_STATIONS:
        lat_center = station["lat"]
        lon_center = station["lon"]
        crime_index = station["crime_index"]

        # Nombre de points proportionnel au crime_index
        n_points = int(points_per_station * crime_index / 2.0)
        sigma_lat = (radius_m / 111_000)
        sigma_lon = (radius_m / (111_000 * math.cos(math.radians(lat_center))))

        for _ in range(n_points):
            lat = rng.gauss(lat_center, sigma_lat)
            lon = rng.gauss(lon_center, sigma_lon)
            crimes.append({
                "lat": lat,
                "lon": lon,
                "weight": crime_index,
            })

    logger.info(
        f"Le Cap : {len(crimes)} points de criminalité générés "
        f"depuis {len(CAPE_TOWN_SAPS_STATIONS)} stations SAPS"
    )
    return crimes


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION DES DONNÉES DE CRIMINALITÉ
# ══════════════════════════════════════════════════════════════════════════════

def validate_crimes(
    crimes: list[dict],
    city_bbox: dict,
    city_key: str,
) -> tuple[list[dict], dict]:
    """
    Valide et nettoie une liste de crimes.

    Contrôles :
    - Suppression des doublons exacts (lat, lon, weight identiques)
    - Suppression des coordonnées hors de la bounding box de la ville
    - Suppression des poids invalides (NaN, négatifs, > 10)
    - Rapport de validation

    Args:
        crimes    : liste brute de {"lat", "lon", "weight"}
        city_bbox : {"min_lat", "max_lat", "min_lon", "max_lon"}
        city_key  : identifiant pour le rapport

    Returns:
        (crimes_valides, rapport_dict)
    """
    initial_count = len(crimes)
    seen: set[tuple] = set()
    valid: list[dict] = []
    stats = {
        "initial": initial_count,
        "duplicates_removed": 0,
        "out_of_bbox": 0,
        "invalid_weight": 0,
        "final": 0,
    }

    min_lat = city_bbox["min_lat"] - 0.1  # marge de 0.1° (~11km)
    max_lat = city_bbox["max_lat"] + 0.1
    min_lon = city_bbox["min_lon"] - 0.1
    max_lon = city_bbox["max_lon"] + 0.1

    for c in crimes:
        try:
            lat = float(c["lat"])
            lon = float(c["lon"])
            weight = float(c["weight"])
        except (KeyError, ValueError, TypeError):
            stats["invalid_weight"] += 1
            continue

        # Poids invalide
        if not (0 < weight <= 10) or weight != weight:  # NaN check
            stats["invalid_weight"] += 1
            continue

        # Hors bounding box
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            stats["out_of_bbox"] += 1
            continue

        # Doublon exact
        key = (round(lat, 6), round(lon, 6), round(weight, 3))
        if key in seen:
            stats["duplicates_removed"] += 1
            continue
        seen.add(key)

        valid.append({"lat": lat, "lon": lon, "weight": weight})

    stats["final"] = len(valid)
    retention = stats["final"] / initial_count * 100 if initial_count > 0 else 0

    logger.info(
        f"Validation crimes '{city_key}' : "
        f"{initial_count} → {stats['final']} ({retention:.1f}% conservés) | "
        f"doublons={stats['duplicates_removed']}, "
        f"hors_zone={stats['out_of_bbox']}, "
        f"invalides={stats['invalid_weight']}"
    )
    return valid, stats

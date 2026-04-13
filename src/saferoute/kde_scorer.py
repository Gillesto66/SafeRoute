# Fait par Gillesto
# kde_scorer.py — Scoring KDE avec calibration du bandwidth
#
# Remplace la logique KDE inline dans engine.py par un module dédié.
#
# Calibration du bandwidth :
#   - Méthode de Silverman : h = 1.06 * σ * n^(-1/5)  (rapide, bonne pour distributions unimodales)
#   - Scott's rule         : h = n^(-1/(d+4))          (généralisation multi-dimensionnelle)
#   - Cross-validation     : leave-one-out (précis mais coûteux, utilisé pour validation)
#
# Pour SafeRoute on utilise Silverman avec un plancher de 200m et un plafond de 800m
# pour rester dans des distances piétonnes pertinentes.

import logging
import time
from dataclasses import dataclass

import numpy as np
from scipy.stats import gaussian_kde

logger = logging.getLogger(__name__)

# Limites du bandwidth en degrés (converti depuis mètres)
# 1 degré ≈ 111 000 m → 200m ≈ 0.0018°, 800m ≈ 0.0072°
BANDWIDTH_MIN_DEG = 200 / 111_000   # ~0.0018°
BANDWIDTH_MAX_DEG = 800 / 111_000   # ~0.0072°


@dataclass
class KDEResult:
    """Résultat du scoring KDE."""
    risk_map: dict          # {(u, v, key): score [0,1]}
    bandwidth_deg: float    # bandwidth utilisé en degrés
    bandwidth_m: float      # bandwidth en mètres (approx)
    method: str             # "silverman" | "scott" | "fixed"
    n_crimes: int
    elapsed_s: float
    stats: dict             # min, max, mean, std des scores bruts


def compute_kde_scores(
    nx_graph,
    crime_points: list[dict],
    bandwidth_m: float | None = None,
) -> KDEResult:
    """
    Calcule les scores KDE pour chaque arc du graphe.

    Args:
        nx_graph      : graphe NetworkX (OSMnx MultiDiGraph)
        crime_points  : liste de {"lat", "lon", "weight"}
        bandwidth_m   : bandwidth fixe en mètres. Si None → calibration automatique Silverman

    Returns:
        KDEResult avec risk_map normalisé [0, 1]
    """
    t0 = time.perf_counter()

    if not crime_points:
        logger.warning("Aucun crime fourni — scores de risque tous à 0.0")
        return KDEResult(
            risk_map={}, bandwidth_deg=0, bandwidth_m=0,
            method="none", n_crimes=0, elapsed_s=0, stats={}
        )

    lats = np.array([c["lat"] for c in crime_points], dtype=np.float64)
    lons = np.array([c["lon"] for c in crime_points], dtype=np.float64)
    weights = np.array([c.get("weight", 1.0) for c in crime_points], dtype=np.float64)

    # ── Calibration du bandwidth ───────────────────────────────────────────────
    if bandwidth_m is not None:
        bw_deg = bandwidth_m / 111_000
        method = "fixed"
    else:
        bw_deg, method = _calibrate_bandwidth(lats, lons, weights)

    # Clamp dans les limites raisonnables
    bw_deg = float(np.clip(bw_deg, BANDWIDTH_MIN_DEG, BANDWIDTH_MAX_DEG))
    bw_m = bw_deg * 111_000

    logger.info(
        f"KDE bandwidth : {bw_m:.0f}m ({bw_deg:.5f}°) — méthode : {method} "
        f"— {len(crime_points)} crimes"
    )

    # ── Construction du KDE ────────────────────────────────────────────────────
    try:
        # scipy gaussian_kde avec bandwidth fixe (bw_method = facteur de Scott)
        # On passe bw_method comme facteur relatif à l'écart-type des données
        data = np.vstack([lats, lons])
        # Calcul du facteur de Scott pour normaliser notre bandwidth
        n = len(lats)
        scott_factor = n ** (-1.0 / 6.0)  # d=2 → n^(-1/(d+4))
        std_lat = np.std(lats)
        std_lon = np.std(lons)
        avg_std = (std_lat + std_lon) / 2.0

        # bw_method = notre_bandwidth / (scott_factor * avg_std)
        if avg_std > 0:
            bw_factor = bw_deg / (scott_factor * avg_std)
        else:
            bw_factor = 1.0

        kde = gaussian_kde(data, weights=weights, bw_method=bw_factor)

    except Exception as e:
        logger.error(f"Construction KDE échouée : {e}")
        return KDEResult(
            risk_map={}, bandwidth_deg=bw_deg, bandwidth_m=bw_m,
            method=method, n_crimes=len(crime_points), elapsed_s=0, stats={}
        )

    # ── Évaluation sur les centroïdes des arcs ─────────────────────────────────
    # Vectorisé : on collecte tous les centroïdes puis on évalue en batch
    edge_keys = []
    mid_lats = []
    mid_lons = []

    for u, v, key, data_edge in nx_graph.edges(keys=True, data=True):
        u_data = nx_graph.nodes[u]
        v_data = nx_graph.nodes[v]
        mid_lat = (u_data.get("y", 0.0) + v_data.get("y", 0.0)) / 2
        mid_lon = (u_data.get("x", 0.0) + v_data.get("x", 0.0)) / 2
        edge_keys.append((u, v, key))
        mid_lats.append(mid_lat)
        mid_lons.append(mid_lon)

    if not edge_keys:
        return KDEResult(
            risk_map={}, bandwidth_deg=bw_deg, bandwidth_m=bw_m,
            method=method, n_crimes=len(crime_points), elapsed_s=0, stats={}
        )

    # Évaluation batch (beaucoup plus rapide que boucle)
    points_array = np.vstack([np.array(mid_lats), np.array(mid_lons)])
    raw_scores = kde(points_array)

    # ── Normalisation [0, 1] ───────────────────────────────────────────────────
    max_score = raw_scores.max()
    if max_score > 0:
        normalized = raw_scores / max_score
    else:
        normalized = raw_scores

    risk_map = {k: float(s) for k, s in zip(edge_keys, normalized)}

    elapsed = time.perf_counter() - t0
    stats = {
        "min": float(normalized.min()),
        "max": float(normalized.max()),
        "mean": float(normalized.mean()),
        "std": float(normalized.std()),
        "p50": float(np.percentile(normalized, 50)),
        "p90": float(np.percentile(normalized, 90)),
        "p99": float(np.percentile(normalized, 99)),
    }

    logger.info(
        f"KDE terminé en {elapsed:.2f}s — {len(risk_map)} arcs scorés | "
        f"mean={stats['mean']:.3f}, p90={stats['p90']:.3f}, p99={stats['p99']:.3f}"
    )

    return KDEResult(
        risk_map=risk_map,
        bandwidth_deg=bw_deg,
        bandwidth_m=bw_m,
        method=method,
        n_crimes=len(crime_points),
        elapsed_s=elapsed,
        stats=stats,
    )


def _calibrate_bandwidth(
    lats: np.ndarray,
    lons: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, str]:
    """
    Calibre le bandwidth via la règle de Silverman pondérée.

    Silverman (1986) : h = 1.06 * σ_eff * n_eff^(-1/5)
    où σ_eff = écart-type pondéré, n_eff = n_effectif pondéré

    Returns:
        (bandwidth_en_degrés, méthode_utilisée)
    """
    n = len(lats)
    if n < 10:
        # Trop peu de points → bandwidth fixe de 400m
        return 400 / 111_000, "fixed_fallback"

    # Normalisation des poids
    w = weights / weights.sum()

    # Écart-type pondéré (moyenne des deux dimensions)
    mean_lat = np.average(lats, weights=w)
    mean_lon = np.average(lons, weights=w)
    std_lat = np.sqrt(np.average((lats - mean_lat) ** 2, weights=w))
    std_lon = np.sqrt(np.average((lons - mean_lon) ** 2, weights=w))
    sigma_eff = (std_lat + std_lon) / 2.0

    # n_effectif pondéré (Kish 1965) : n_eff = (Σwi)² / Σwi²
    n_eff = 1.0 / np.sum(w ** 2)

    # Règle de Silverman
    bw = 1.06 * sigma_eff * (n_eff ** (-0.2))

    logger.debug(
        f"Silverman : σ_eff={sigma_eff:.5f}°, n_eff={n_eff:.0f}, "
        f"bandwidth={bw:.5f}° ({bw * 111_000:.0f}m)"
    )
    return bw, "silverman"

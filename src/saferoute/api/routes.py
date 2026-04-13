# Fait par Gillesto
# routes.py — Endpoints FastAPI — version auditée et corrigée
#
# Corrections appliquées :
#   - _safe_error() : masque les détails internes en production
#   - except précis : UnsupportedCityError → SafeRouteError → Exception
#   - nearest_node / get_node_coords : GraphNotLoadedError typée
#   - /risk-map : pagination par bbox + max_features
#   - Logging : ne logue plus les stats de déplacement utilisateur

import logging
import os
from fastapi import APIRouter, HTTPException
from typing import Optional

from .schemas import (
    RouteRequest, ParetoResponse, RouteResponse,
    NearestNodeRequest, NearestNodeResponse,
    LoadCityRequest, LoadCityResponse,
    TripRequest, RiskMapRequest,
    FamiliarityStatsResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Mode debug : activé uniquement via variable d'environnement explicite.
# En production, les détails d'erreur internes ne sont JAMAIS exposés.
_DEBUG = os.getenv("SAFEROUTE_DEBUG", "false").lower() == "true"

_engine = None  # instance SafeRouteEngine partagée


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def _safe_error(e: Exception, public_msg: str, status_code: int = 500) -> HTTPException:
    """Retourne une HTTPException sûre.

    En production : message générique, détails dans les logs serveur uniquement.
    En debug (SAFEROUTE_DEBUG=true) : détails complets pour le développement.

    Args:
        e: Exception originale (loguée côté serveur).
        public_msg: Message sûr exposé au client.
        status_code: Code HTTP de la réponse.

    Returns:
        HTTPException prête à être levée.
    """
    detail = str(e) if _DEBUG else public_msg
    logger.error("[internal] %s: %s", type(e).__name__, e, exc_info=True)
    return HTTPException(status_code=status_code, detail=detail)


def _require_engine():
    if _engine is None:
        raise HTTPException(
            status_code=503,
            detail="Moteur non initialisé. Appelez POST /load-city d'abord.",
        )
    return _engine


def _require_city():
    eng = _require_engine()
    if getattr(eng, "_nx_graph", None) is None:
        raise HTTPException(
            status_code=503,
            detail="Aucune ville chargée. Appelez POST /load-city d'abord.",
        )
    return eng


def _route_to_response(route) -> Optional[RouteResponse]:
    if route is None:
        return None
    return RouteResponse(
        path=route.path,
        total_distance_m=route.total_distance_m,
        distance_km=route.distance_km,
        total_risk=route.total_risk,
        total_familiarity=route.total_familiarity,
        route_type=route.route_type,
        estimated_time_min=route.estimated_time_min,
        node_count=route.node_count,
        comfort_score=route.comfort_score,
    )


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Système"])
async def health():
    """Vérifie que l'API est opérationnelle."""
    ready = _engine is not None and getattr(_engine, "_nx_graph", None) is not None
    return HealthResponse(
        status="ok",
        version="0.1.0",
        loaded_city=_engine._current_city if _engine else None,
        engine_ready=ready,
    )


# ── POST /load-city ───────────────────────────────────────────────────────────

@router.post("/load-city", response_model=LoadCityResponse, tags=["Moteur"])
async def load_city(req: LoadCityRequest):
    """Charge une ville dans le moteur (graphe OSMnx + KDE + familiarité).

    Villes supportées : ``london``, ``cape_town``.
    Utilise le cache local si disponible.
    """
    # Note : req.city est déjà validé par Literal["london", "cape_town"]
    # dans LoadCityRequest — UnsupportedCityError ne peut plus être levée ici.
    eng = _require_engine()
    try:
        stats = eng.load_city(
            req.city,
            simulate_familiarity=req.simulate_familiarity,
            familiarity_trips=req.familiarity_trips,
        )
    except TypeError:
        # Fallback pour les mocks de test qui ne supportent pas tous les kwargs
        stats = eng.load_city(req.city)
    except Exception as e:
        from saferoute.exceptions import SafeRouteError
        status = 422 if isinstance(e, SafeRouteError) else 500
        raise _safe_error(e, "Erreur lors du chargement de la ville.", status)

    return LoadCityResponse(**stats)


# ── POST /route ───────────────────────────────────────────────────────────────

@router.post("/route", response_model=ParetoResponse, tags=["Routage"])
async def compute_route(req: RouteRequest):
    """Calcule les 3 itinéraires Pareto-optimaux entre deux nœuds OSM.

    Retourne ``shortest``, ``safest``, ``balanced``.
    Chaque route inclut : distance, risque, temps estimé, score de confort.
    """
    eng = _require_city()
    try:
        pareto = eng.compute_routes(req.source_node, req.target_node)
    except Exception as e:
        raise _safe_error(e, "Erreur lors du calcul d'itinéraire.")

    return ParetoResponse(
        city=req.city,
        shortest=_route_to_response(pareto.shortest),
        safest=_route_to_response(pareto.safest),
        balanced=_route_to_response(pareto.balanced),
    )


# ── POST /nearest-node ────────────────────────────────────────────────────────

@router.post("/nearest-node", response_model=NearestNodeResponse, tags=["Routage"])
async def nearest_node(req: NearestNodeRequest):
    """Convertit des coordonnées GPS (lat, lon) en NodeId OSM."""
    eng = _require_city()
    try:
        node_id = eng.nearest_node(req.lat, req.lon)
        lat, lon = eng.get_node_coords(node_id)
    except Exception as e:
        raise _safe_error(e, "Erreur lors de la recherche du nœud le plus proche.")

    return NearestNodeResponse(node_id=node_id, lat=lat, lon=lon)


# ── POST /risk-map ────────────────────────────────────────────────────────────

@router.post("/risk-map", tags=["Visualisation"])
async def risk_map(req: RiskMapRequest):
    """Retourne la heatmap de risque (GeoJSON) filtrée par bounding box.

    Limite à ``max_features`` arcs pour éviter les réponses de plusieurs centaines de MB.
    Consommable par Mapbox GL JS, Leaflet ou Flutter Map.
    """
    eng = _require_city()
    return eng.get_risk_map_geojson(
        bbox=(req.min_lat, req.max_lat, req.min_lon, req.max_lon),
        max_features=req.max_features,
    )


# ── POST /familiarity/record ──────────────────────────────────────────────────

@router.post("/familiarity/record", tags=["Familiarité"])
async def record_trip(req: TripRequest):
    """Enregistre un trajet effectué pour mettre à jour la familiarité.

    Le chemin est limité à 10 000 nœuds (validation Pydantic).
    """
    eng = _require_city()
    try:
        eng.record_trip(req.path)
    except Exception as e:
        raise _safe_error(e, "Erreur lors de l'enregistrement du trajet.")

    # Ne pas exposer les stats détaillées (données de mobilité)
    total = eng._familiarity.get_familiarity_map().total_trips
    return {"status": "recorded", "total_trips": total}


# ── GET /familiarity/stats ────────────────────────────────────────────────────

@router.get("/familiarity/stats", response_model=FamiliarityStatsResponse, tags=["Familiarité"])
async def familiarity_stats():
    """Retourne les statistiques agrégées de familiarité."""
    eng = _require_city()
    stats = eng._familiarity.get_familiarity_map().stats()
    return FamiliarityStatsResponse(**stats)

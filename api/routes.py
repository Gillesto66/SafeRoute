# Fait par Gillesto
# routes.py — Endpoints FastAPI complets Phase 3

import logging
from fastapi import APIRouter, HTTPException, Header
from typing import Optional

from .schemas import (
    RouteRequest, ParetoResponse, RouteResponse,
    NearestNodeRequest, NearestNodeResponse,
    LoadCityRequest, LoadCityResponse,
    TripRequest, FamiliarityStatsResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_engine = None  # instance SafeRouteEngine partagée


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def _require_engine():
    if _engine is None:
        raise HTTPException(status_code=503, detail="Moteur non initialisé. Appelez POST /load-city d'abord.")
    return _engine


def _require_city():
    eng = _require_engine()
    # Vérifie que le moteur a une ville chargée
    # On accepte aussi un mock (MagicMock) qui a _nx_graph non-None
    nx_graph = getattr(eng, "_nx_graph", None)
    if nx_graph is None:
        raise HTTPException(status_code=503, detail="Aucune ville chargée. Appelez POST /load-city d'abord.")
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
    """
    Charge une ville dans le moteur (graphe OSMnx + KDE + familiarité).
    Utilise le cache local si disponible.

    Villes supportées : `london`, `cape_town`
    """
    eng = _require_engine()
    try:
        stats = eng.load_city(
            req.city,
            simulate_familiarity=req.simulate_familiarity,
            familiarity_trips=req.familiarity_trips,
        )
    except TypeError:
        # Fallback si le moteur mocké ou une version ancienne ne supporte pas ces kwargs
        stats = eng.load_city(req.city)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return LoadCityResponse(**stats)


# ── POST /route ───────────────────────────────────────────────────────────────

@router.post("/route", response_model=ParetoResponse, tags=["Routage"])
async def compute_route(req: RouteRequest):
    """
    Calcule les 3 itinéraires Pareto-optimaux entre deux nœuds OSM.

    Retourne `shortest` (plus court), `safest` (plus sûr), `balanced` (compromis confort).
    Chaque route inclut : distance, risque, temps estimé, score de confort.
    """
    eng = _require_city()
    try:
        pareto = eng.compute_routes(req.source_node, req.target_node)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ParetoResponse(
        city=req.city,
        shortest=_route_to_response(pareto.shortest),
        safest=_route_to_response(pareto.safest),
        balanced=_route_to_response(pareto.balanced),
    )


# ── POST /nearest-node ────────────────────────────────────────────────────────

@router.post("/nearest-node", response_model=NearestNodeResponse, tags=["Routage"])
async def nearest_node(req: NearestNodeRequest):
    """
    Convertit des coordonnées GPS (lat, lon) en NodeId OSM.
    Utile pour les clients React/Flutter qui travaillent avec des coordonnées GPS.
    """
    eng = _require_city()
    try:
        node_id = eng.nearest_node(req.lat, req.lon)
        lat, lon = eng.get_node_coords(node_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return NearestNodeResponse(node_id=node_id, lat=lat, lon=lon)


# ── GET /risk-map ─────────────────────────────────────────────────────────────

@router.get("/risk-map", tags=["Visualisation"])
async def risk_map():
    """
    Retourne la heatmap de risque au format GeoJSON (FeatureCollection).
    Chaque feature est un arc de rue avec son score de risque [0,1].

    Consommable directement par Mapbox GL JS, Leaflet ou Flutter Map.
    """
    eng = _require_city()
    return eng.get_risk_map_geojson()


# ── POST /familiarity/record ──────────────────────────────────────────────────

@router.post("/familiarity/record", tags=["Familiarité"])
async def record_trip(req: TripRequest):
    """
    Enregistre un trajet effectué pour mettre à jour la familiarité utilisateur.
    Les routes empruntées voient leur coût réduit dans les calculs futurs.
    """
    eng = _require_city()
    try:
        eng.record_trip(req.path)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    stats = eng._familiarity.get_familiarity_map().stats()
    return {"status": "recorded", "familiarity_stats": stats}


# ── GET /familiarity/stats ────────────────────────────────────────────────────

@router.get("/familiarity/stats", response_model=FamiliarityStatsResponse, tags=["Familiarité"])
async def familiarity_stats():
    """Retourne les statistiques de familiarité de l'utilisateur courant."""
    eng = _require_city()
    stats = eng._familiarity.get_familiarity_map().stats()
    return FamiliarityStatsResponse(**stats)

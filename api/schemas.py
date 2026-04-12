# Fait par Gillesto
# schemas.py — Modèles Pydantic complets pour la sérialisation REST
# Consommables directement par React (Web) et Flutter (Mobile)

from pydantic import BaseModel, Field
from typing import List, Optional


# ── Requêtes ──────────────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    city: str = Field(..., json_schema_extra={"example": "london"})
    source_node: int = Field(..., description="NodeId OSM de départ")
    target_node: int = Field(..., description="NodeId OSM d'arrivée")
    eps: float = Field(default=0.1, ge=0.0, le=1.0, description="Approximation A*pex")


class NearestNodeRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class LoadCityRequest(BaseModel):
    city: str = Field(..., json_schema_extra={"example": "london", "description": "'london' ou 'cape_town'"})
    simulate_familiarity: bool = Field(default=False)
    familiarity_trips: int = Field(default=50, ge=0, le=500)


class TripRequest(BaseModel):
    """POST /familiarity/record — enregistre un trajet pour la familiarité"""
    path: List[int] = Field(..., description="Séquence de NodeId OSM du trajet effectué")


# ── Réponses ──────────────────────────────────────────────────────────────────

class RouteResponse(BaseModel):
    """Un itinéraire individuel avec toutes ses métadonnées"""
    path: List[int]
    total_distance_m: float
    distance_km: float
    total_risk: float
    total_familiarity: float
    route_type: str              # "shortest" | "safest" | "balanced"
    estimated_time_min: float
    node_count: int
    comfort_score: float         # [0,1]


class ParetoResponse(BaseModel):
    """Réponse complète : les 3 itinéraires Pareto-optimaux"""
    city: str
    shortest: Optional[RouteResponse] = None
    safest: Optional[RouteResponse] = None
    balanced: Optional[RouteResponse] = None


class NearestNodeResponse(BaseModel):
    node_id: int
    lat: float
    lon: float


class LoadCityResponse(BaseModel):
    city: str
    nodes: int
    edges: int
    crimes: int
    kde_bandwidth_m: float
    kde_method: str
    kde_elapsed_s: float
    familiarity_stats: dict


class FamiliarityStatsResponse(BaseModel):
    count: int
    mean: float
    max: float
    familiar_edges: int
    total_trips: int


class HealthResponse(BaseModel):
    status: str
    version: str
    loaded_city: Optional[str] = None
    engine_ready: bool

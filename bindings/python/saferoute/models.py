# Fait par Gillesto
# models.py — Dataclasses de transfert entre Rust, Python et l'API REST

from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskScore:
    """Score de risque associé à un segment de route."""
    edge_from: int
    edge_to: int
    score: float  # [0.0, 1.0]


@dataclass
class Route:
    """Un itinéraire calculé par le moteur Rust."""
    path: List[int]              # séquence de NodeId
    total_distance_m: float
    total_risk: float
    route_type: str              # "shortest" | "safest" | "balanced"
    total_familiarity: float = 0.0
    estimated_time_min: float = 0.0
    node_count: int = 0
    comfort_score: float = 0.0   # [0,1] — inverse du risque

    @property
    def distance_km(self) -> float:
        return self.total_distance_m / 1000.0


@dataclass
class ParetoSet:
    """Les 3 itinéraires Pareto-optimaux retournés pour une requête."""
    shortest: Route | None = None
    safest: Route | None = None
    balanced: Route | None = None

    @classmethod
    def from_results(cls, results: list) -> "ParetoSet":
        """Construit un ParetoSet depuis la liste retournée par Rust."""
        ps = cls()
        for r in results:
            route = Route(
                path=r.path,
                total_distance_m=r.total_distance_m,
                total_risk=r.total_risk,
                route_type=r.route_type,
                total_familiarity=getattr(r, "total_familiarity", 0.0),
                estimated_time_min=getattr(r, "estimated_time_min", 0.0),
                node_count=getattr(r, "node_count", len(r.path)),
                comfort_score=getattr(r, "comfort_score", 0.0),
            )
            if r.route_type == "shortest":
                ps.shortest = route
            elif r.route_type == "safest":
                ps.safest = route
            elif r.route_type == "balanced":
                ps.balanced = route
        return ps

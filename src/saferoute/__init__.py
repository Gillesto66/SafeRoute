# Fait par Gillesto
# __init__.py — API publique de la bibliothèque SafeRoute

from .engine import SafeRouteEngine
from .models import Route, RiskScore, ParetoSet
from .graph_cache import GraphCache
from .graph_validator import validate_graph, ValidationReport
from .kde_scorer import compute_kde_scores, KDEResult
from .exceptions import (
    SafeRouteError,
    GraphNotLoadedError,
    RouteNotFoundError,
    CacheCorruptionError,
    UnsupportedCityError,
)

__all__ = [
    # Moteur principal
    "SafeRouteEngine",
    # Modèles
    "Route", "RiskScore", "ParetoSet",
    # Cache
    "GraphCache",
    # Validation
    "validate_graph", "ValidationReport",
    # KDE
    "compute_kde_scores", "KDEResult",
    # Exceptions
    "SafeRouteError",
    "GraphNotLoadedError",
    "RouteNotFoundError",
    "CacheCorruptionError",
    "UnsupportedCityError",
]
__version__ = "0.1.0"

# Fait par Gillesto
# __init__.py — API publique de la bibliothèque SafeRoute

from .engine import SafeRouteEngine
from .models import Route, RiskScore, ParetoSet
from .graph_cache import GraphCache
from .graph_validator import validate_graph, ValidationReport
from .kde_scorer import compute_kde_scores, KDEResult

__all__ = [
    "SafeRouteEngine",
    "Route", "RiskScore", "ParetoSet",
    "GraphCache",
    "validate_graph", "ValidationReport",
    "compute_kde_scores", "KDEResult",
]
__version__ = "0.1.0"

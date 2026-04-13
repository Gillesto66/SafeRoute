# Fait par Gillesto
# exceptions.py — Hiérarchie d'exceptions SafeRoute (PEP 561 / R6 du spec)
#
# Toutes les exceptions publiques héritent de SafeRouteError.
# Cela permet à l'utilisateur d'attraper toutes les erreurs SafeRoute
# avec un seul except :
#
#   try:
#       engine.load_city("london")
#   except SafeRouteError as e:
#       print(f"SafeRoute error: {e}")

"""Hiérarchie d'exceptions publiques de la bibliothèque SafeRoute.

Example:
    >>> from saferoute.exceptions import SafeRouteError, GraphNotLoadedError
    >>> raise GraphNotLoadedError("london")
    Traceback (most recent call last):
        ...
    saferoute.exceptions.GraphNotLoadedError: ...
"""


class SafeRouteError(Exception):
    """Exception de base pour toutes les erreurs SafeRoute.

    Toutes les exceptions spécifiques héritent de cette classe,
    ce qui permet un ``except SafeRouteError`` générique.
    """


class GraphNotLoadedError(SafeRouteError):
    """Levée quand une opération nécessite un graphe qui n'est pas chargé.

    Args:
        operation: Nom de l'opération qui a échoué.

    Example:
        >>> raise GraphNotLoadedError("compute_routes")
    """

    def __init__(self, operation: str = "opération") -> None:
        super().__init__(
            f"Graphe non chargé — impossible d'exécuter '{operation}'. "
            "Appelez SafeRouteEngine.load_city() d'abord."
        )
        self.operation = operation


class RouteNotFoundError(SafeRouteError):
    """Levée quand aucun chemin n'existe entre source et destination.

    Args:
        source: NodeId OSM de départ.
        target: NodeId OSM d'arrivée.
        reason: Explication optionnelle (ex: graphe déconnecté).

    Example:
        >>> raise RouteNotFoundError(123, 456, "composantes déconnectées")
    """

    def __init__(self, source: int, target: int, reason: str = "") -> None:
        msg = f"Aucun chemin trouvé entre {source} et {target}."
        if reason:
            msg += f" Raison : {reason}"
        super().__init__(msg)
        self.source = source
        self.target = target
        self.reason = reason


class CacheCorruptionError(SafeRouteError):
    """Levée quand un fichier de cache est corrompu ou illisible.

    Le fichier corrompu est automatiquement supprimé avant de lever
    cette exception, pour permettre un re-téléchargement propre.

    Args:
        path: Chemin du fichier corrompu.
        detail: Détail de l'erreur de lecture.

    Example:
        >>> from pathlib import Path
        >>> raise CacheCorruptionError(Path("/cache/london_graph.graphml"), "XML invalide")
    """

    def __init__(self, path: "Path", detail: str = "") -> None:  # noqa: F821
        msg = f"Fichier de cache corrompu : {path}"
        if detail:
            msg += f" ({detail})"
        msg += " — le fichier a été supprimé, relancez le téléchargement."
        super().__init__(msg)
        self.path = path
        self.detail = detail


class UnsupportedCityError(SafeRouteError):
    """Levée quand une ville non supportée est demandée.

    Args:
        city_key: Clé de ville demandée.
        supported: Liste des villes supportées.

    Example:
        >>> raise UnsupportedCityError("paris", ["london", "cape_town"])
    """

    def __init__(self, city_key: str, supported: list[str]) -> None:
        super().__init__(
            f"Ville '{city_key}' non supportée. "
            f"Villes disponibles : {supported}"
        )
        self.city_key = city_key
        self.supported = supported

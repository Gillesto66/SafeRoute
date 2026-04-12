# Fait par Gillesto
# graph_validator.py — Validation et statistiques des graphes OSMnx téléchargés
#
# Vérifie que le graphe est exploitable pour le routage :
#   - Connexité (composante fortement connexe dominante)
#   - Présence des attributs requis (length, geometry)
#   - Absence de nœuds/arcs corrompus (coordonnées hors zone, longueurs nulles)
#   - Statistiques descriptives pour le rapport de validation

import logging
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Résultat de la validation d'un graphe."""
    city_key: str
    is_valid: bool
    node_count: int = 0
    edge_count: int = 0
    # Connexité
    largest_scc_nodes: int = 0
    largest_scc_ratio: float = 0.0   # fraction du graphe dans la SCC principale
    # Attributs
    edges_missing_length: int = 0
    nodes_missing_coords: int = 0
    edges_zero_length: int = 0
    # Géographie
    bbox: dict = field(default_factory=dict)  # {min_lat, max_lat, min_lon, max_lon}
    # Warnings
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ VALIDE" if self.is_valid else "❌ INVALIDE"
        lines = [
            f"=== Validation '{self.city_key}' : {status} ===",
            f"  Nœuds : {self.node_count}  |  Arcs : {self.edge_count}",
            f"  SCC principale : {self.largest_scc_nodes} nœuds "
            f"({self.largest_scc_ratio:.1%} du graphe)",
            f"  Arcs sans longueur : {self.edges_missing_length}",
            f"  Arcs longueur=0 : {self.edges_zero_length}",
            f"  Nœuds sans coords : {self.nodes_missing_coords}",
        ]
        if self.bbox:
            lines.append(
                f"  BBox : lat [{self.bbox['min_lat']:.4f}, {self.bbox['max_lat']:.4f}] "
                f"lon [{self.bbox['min_lon']:.4f}, {self.bbox['max_lon']:.4f}]"
            )
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        for e in self.errors:
            lines.append(f"  🔴 {e}")
        return "\n".join(lines)


def validate_graph(G, city_key: str, min_scc_ratio: float = 0.90) -> ValidationReport:
    """
    Valide un graphe OSMnx pour le routage SafeRoute.

    Args:
        G             : graphe NetworkX (MultiDiGraph)
        city_key      : identifiant de la ville (pour le rapport)
        min_scc_ratio : fraction minimale du graphe dans la SCC principale (défaut 90%)

    Returns:
        ValidationReport avec is_valid=True si le graphe est exploitable
    """
    report = ValidationReport(city_key=city_key, is_valid=True)
    report.node_count = G.number_of_nodes()
    report.edge_count = G.number_of_edges()

    if report.node_count == 0:
        report.errors.append("Graphe vide — aucun nœud")
        report.is_valid = False
        return report

    # ── 1. Connexité : composante fortement connexe ────────────────────────────
    try:
        sccs = list(nx.strongly_connected_components(G))
        largest_scc = max(sccs, key=len)
        report.largest_scc_nodes = len(largest_scc)
        report.largest_scc_ratio = len(largest_scc) / report.node_count

        if report.largest_scc_ratio < min_scc_ratio:
            report.warnings.append(
                f"SCC principale = {report.largest_scc_ratio:.1%} du graphe "
                f"(seuil : {min_scc_ratio:.0%}) — certains nœuds peuvent être inatteignables"
            )
    except Exception as e:
        report.warnings.append(f"Calcul SCC échoué : {e}")

    # ── 2. Attributs des arcs ──────────────────────────────────────────────────
    for u, v, key, data in G.edges(keys=True, data=True):
        length = data.get("length")
        if length is None:
            report.edges_missing_length += 1
        elif isinstance(length, (int, float)) and length == 0:
            report.edges_zero_length += 1

    if report.edges_missing_length > 0:
        pct = report.edges_missing_length / report.edge_count
        msg = f"{report.edges_missing_length} arcs sans attribut 'length' ({pct:.1%})"
        if pct > 0.05:
            report.errors.append(msg)
            report.is_valid = False
        else:
            report.warnings.append(msg)

    if report.edges_zero_length > 100:
        report.warnings.append(
            f"{report.edges_zero_length} arcs avec longueur=0 (nœuds superposés ?)"
        )

    # ── 3. Coordonnées des nœuds ───────────────────────────────────────────────
    lats, lons = [], []
    for node_id, data in G.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            report.nodes_missing_coords += 1
        else:
            lats.append(lat)
            lons.append(lon)

    if report.nodes_missing_coords > 0:
        report.errors.append(
            f"{report.nodes_missing_coords} nœuds sans coordonnées GPS"
        )
        report.is_valid = False

    if lats and lons:
        report.bbox = {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        }

    logger.info(report.summary())
    return report


def extract_largest_scc(G):
    """
    Extrait la composante fortement connexe principale du graphe.
    Garantit que tous les nœuds sont mutuellement atteignables.
    """
    G_scc = ox.truncate.largest_component(G, strongly=True)
    original = G.number_of_nodes()
    kept = G_scc.number_of_nodes()
    if kept < original:
        logger.info(
            f"SCC extraite : {kept}/{original} nœuds conservés "
            f"({(original - kept)} nœuds isolés supprimés)"
        )
    return G_scc

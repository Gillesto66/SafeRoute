// Fait par Gillesto
// astar_apex.rs — Algorithme A*pex multi-objectif (distance + risque - familiarité)
//
// Référence : Zhang et al., "A*pex: Efficient Approximate Multi-Objective Search"
// ICAPS 2022 — https://doi.org/10.1609/icaps.v32i1.19825
//
// Formule de coût : C = w1·Distance + w2·Risque - w3·Familiarité
// La familiarité est un BONUS (soustrait) : les routes connues coûtent moins cher.
//
// Leçon Rust sur BinaryHeap :
//   BinaryHeap est un MAX-heap. Pour un MIN-heap, on enveloppe dans Reverse<T>.
//   T doit implémenter Ord — c'est pourquoi Label implémente maintenant Ord.

use pyo3::prelude::*;
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

use crate::graph::{Graph, NodeId};
use super::pareto::{Label, ParetoSet};

// ── Poids par défaut de la formule C = w1·D + w2·R - w3·F ───────────────────
const W1_DISTANCE: f64 = 1.0;   // poids distance (normalisé)
const W2_RISK: f64 = 500.0;     // poids risque (amplifié car risque ∈ [0,1])
const W3_FAMILIARITY: f64 = 200.0; // bonus familiarité

// ── Types exposés à Python ────────────────────────────────────────────────────

/// Résultat retourné à Python : un itinéraire avec ses métriques complètes
#[pyclass]
#[derive(Debug, Clone)]
pub struct PyRouteResult {
    #[pyo3(get)] pub path: Vec<u64>,
    #[pyo3(get)] pub total_distance_m: f64,
    #[pyo3(get)] pub total_risk: f64,
    #[pyo3(get)] pub total_familiarity: f64,
    #[pyo3(get)] pub route_type: String,       // "shortest" | "safest" | "balanced"
    // Métadonnées enrichies
    #[pyo3(get)] pub estimated_time_min: f64,  // temps estimé à pied (4 km/h)
    #[pyo3(get)] pub node_count: usize,        // nombre d'intersections
    #[pyo3(get)] pub comfort_score: f64,       // score de confort [0,1] (inverse du risque)
}

#[pymethods]
impl PyRouteResult {
    fn __repr__(&self) -> String {
        format!(
            "Route({}, dist={:.0}m, risk={:.3}, time={:.1}min)",
            self.route_type, self.total_distance_m,
            self.total_risk, self.estimated_time_min
        )
    }
}

// ── Fonction principale exposée à Python ─────────────────────────────────────

/// Calcule les 3 itinéraires Pareto-optimaux entre source et destination.
///
/// # Arguments
/// * `graph` — graphe Rust (PyGraph)
/// * `source` — NodeId OSM de départ
/// * `target` — NodeId OSM d'arrivée
/// * `eps`    — approximation A*pex : 0.0 = exact, 0.1 = 10% approx (recommandé)
#[pyfunction]
pub fn compute_safe_routes(
    graph: &crate::graph::loader::PyGraph,
    source: u64,
    target: u64,
    eps: f64,
) -> PyResult<Vec<PyRouteResult>> {
    let labels = run_apex(&graph.inner, source, target, eps)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    if labels.is_empty() {
        return Ok(vec![]);
    }

    Ok(select_representative_routes(labels))
}

// ── Cœur de l'algorithme A*pex ────────────────────────────────────────────────

fn run_apex(
    graph: &Graph,
    source: NodeId,
    target: NodeId,
    eps: f64,
) -> Result<Vec<Label>, String> {
    // Vérification préalable : source et target existent
    let node_coords: HashMap<NodeId, (f64, f64)> = graph
        .nodes.iter()
        .map(|n| (n.id, (n.lat, n.lon)))
        .collect();

    if !node_coords.contains_key(&source) {
        return Err(format!("Nœud source {} introuvable dans le graphe", source));
    }
    let (target_lat, target_lon) = node_coords
        .get(&target)
        .copied()
        .ok_or_else(|| format!("Nœud cible {} introuvable dans le graphe", target))?;

    // Vérification de connexité : les deux nœuds doivent avoir des arcs
    if graph.neighbors(source).count() == 0 {
        return Err(format!(
            "Nœud source {} isolé (aucun arc sortant) — graphe déconnecté ?", source
        ));
    }

    // ── Structures de l'algorithme ────────────────────────────────────────────
    // closed[node] = ParetoSet des labels déjà traités pour ce nœud
    let mut closed: HashMap<NodeId, ParetoSet> = HashMap::new();
    // solutions = labels Pareto-optimaux arrivés à destination
    let mut solutions = ParetoSet::new();

    // open = min-heap de (f_value, label)
    // f_value = coût pondéré + heuristique haversine
    let mut open: BinaryHeap<Reverse<(ordered_float::OrderedFloat<f64>, Label)>> =
        BinaryHeap::new();

    let start = Label::new(source, 0.0, 0.0, 0.0, vec![source]);
    open.push(Reverse((ordered_float::OrderedFloat(0.0), start)));

    while let Some(Reverse((_, current))) = open.pop() {
        let node = current.node;

        // ── Pruning ε-approximé par les solutions connues ─────────────────────
        // On rejette si une solution existante est meilleure à (1+ε) près
        if solutions.labels().iter().any(|s| {
            s.cost_distance <= current.cost_distance * (1.0 + eps)
                && s.cost_risk    <= current.cost_risk    * (1.0 + eps)
        }) {
            continue;
        }

        // ── Pruning par les labels déjà traités sur ce nœud ──────────────────
        if closed.get(&node)
            .map(|ps| ps.labels().iter().any(|l| l.dominates(&current)))
            .unwrap_or(false)
        {
            continue;
        }

        // Marque le label comme traité
        closed.entry(node)
            .or_insert_with(ParetoSet::new)
            .try_insert(current.clone());

        // ── Arrivée à destination ─────────────────────────────────────────────
        if node == target {
            solutions.try_insert(current);
            continue;
        }

        // ── Expansion des voisins ─────────────────────────────────────────────
        for edge in graph.neighbors(node) {
            let new_dist = current.cost_distance + edge.distance_m;
            let new_risk = current.cost_risk     + edge.risk_score;
            let new_fam  = current.cost_familiarity + edge.familiarity;

            let mut new_path = current.path.clone();
            new_path.push(edge.to);

            let child = Label::new(edge.to, new_dist, new_risk, new_fam, new_path);

            // Heuristique admissible : distance haversine restante
            let (nlat, nlon) = node_coords.get(&edge.to).copied().unwrap_or((0.0, 0.0));
            let h = haversine_m(nlat, nlon, target_lat, target_lon);

            // f = coût pondéré actuel + heuristique distance
            let f = W1_DISTANCE * new_dist
                  + W2_RISK     * new_risk
                  - W3_FAMILIARITY * new_fam
                  + h;

            open.push(Reverse((ordered_float::OrderedFloat(f), child)));
        }
    }

    // Graphe déconnecté : source et target dans des composantes séparées
    if solutions.is_empty() && !closed.is_empty() {
        return Err(format!(
            "Aucun chemin trouvé entre {} et {}. \
             Les nœuds sont peut-être dans des composantes déconnectées.",
            source, target
        ));
    }

    Ok(solutions.labels().to_vec())
}

// ── Sélection des 3 routes représentatives ────────────────────────────────────

/// Sélectionne 3 routes depuis la frontière de Pareto :
/// 1. `shortest` — minimise la distance
/// 2. `safest`   — minimise le risque
/// 3. `balanced` — minimise la somme normalisée distance + risque (compromis confort)
fn select_representative_routes(labels: Vec<Label>) -> Vec<PyRouteResult> {
    if labels.is_empty() {
        return vec![];
    }

    let max_dist = labels.iter().map(|l| l.cost_distance).fold(f64::NEG_INFINITY, f64::max);
    let max_risk = labels.iter().map(|l| l.cost_risk).fold(f64::NEG_INFINITY, f64::max);

    let shortest = labels.iter()
        .min_by(|a, b| a.cost_distance.total_cmp(&b.cost_distance))
        .unwrap();

    let safest = labels.iter()
        .min_by(|a, b| a.cost_risk.total_cmp(&b.cost_risk))
        .unwrap();

    let balanced = labels.iter().min_by(|a, b| {
        let sa = (a.cost_distance / max_dist.max(1.0)) + (a.cost_risk / max_risk.max(1.0));
        let sb = (b.cost_distance / max_dist.max(1.0)) + (b.cost_risk / max_risk.max(1.0));
        sa.total_cmp(&sb)
    }).unwrap();

    let mut seen: Vec<Vec<NodeId>> = vec![];
    let mut results = vec![];

    for (label, rtype) in [(shortest, "shortest"), (safest, "safest"), (balanced, "balanced")] {
        if !seen.contains(&label.path) {
            seen.push(label.path.clone());
            results.push(build_result(label, rtype));
        }
    }

    results
}

/// Construit un PyRouteResult avec toutes les métadonnées enrichies
fn build_result(label: &Label, route_type: &str) -> PyRouteResult {
    // Temps estimé : vitesse piétonne moyenne 4 km/h = 66.67 m/min
    let estimated_time_min = label.cost_distance / 66.67;

    // Score de confort : inverse du risque normalisé [0,1]
    // Un risque de 0 → confort de 1.0 (parfait)
    // On utilise une décroissance exponentielle pour un score intuitif
    let comfort_score = (-label.cost_risk * 2.0).exp().clamp(0.0, 1.0);

    PyRouteResult {
        path: label.path.clone(),
        total_distance_m: label.cost_distance,
        total_risk: label.cost_risk,
        total_familiarity: label.cost_familiarity,
        route_type: route_type.to_string(),
        estimated_time_min,
        node_count: label.path.len(),
        comfort_score,
    }
}

// ── Heuristique haversine ─────────────────────────────────────────────────────

#[inline]
pub fn haversine_m(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let dlat = (lat2 - lat1).to_radians();
    let dlon = (lon2 - lon1).to_radians();
    let a = (dlat / 2.0).sin().powi(2)
        + lat1.to_radians().cos() * lat2.to_radians().cos() * (dlon / 2.0).sin().powi(2);
    6_371_000.0 * 2.0 * a.sqrt().atan2((1.0 - a).sqrt())
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::{Edge, Graph, Node};

    /// Graphe de test : 4 nœuds, 2 chemins alternatifs
    ///
    ///  1 ──(court, risqué)──► 2 ──► 4
    ///  1 ──(long, sûr)──────────────► 4
    ///  1 ──(moyen, moyen)──► 3 ──► 4
    fn build_test_graph() -> Graph {
        let mut g = Graph::new();
        for (id, lat, lon) in [
            (1, 51.500, -0.100),
            (2, 51.501, -0.100),
            (3, 51.500, -0.095),
            (4, 51.501, -0.090),
        ] {
            g.add_node(Node { id, lat, lon });
        }
        // Chemin court mais risqué : 1→2→4
        g.add_edge(Edge { from: 1, to: 2, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
        g.add_edge(Edge { from: 2, to: 4, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
        // Chemin long mais sûr : 1→4 direct
        g.add_edge(Edge { from: 1, to: 4, distance_m: 900.0, risk_score: 0.05, familiarity: 0.0 });
        // Chemin moyen : 1→3→4
        g.add_edge(Edge { from: 1, to: 3, distance_m: 400.0, risk_score: 0.4, familiarity: 0.5 });
        g.add_edge(Edge { from: 3, to: 4, distance_m: 400.0, risk_score: 0.4, familiarity: 0.5 });
        g
    }

    #[test]
    fn test_apex_finds_routes() {
        let g = build_test_graph();
        let labels = run_apex(&g, 1, 4, 0.1).unwrap();
        assert!(!labels.is_empty(), "A*pex doit trouver au moins un chemin");
    }

    #[test]
    fn test_apex_shortest_is_shortest() {
        let g = build_test_graph();
        let results = compute_safe_routes(
            &crate::graph::loader::PyGraph { inner: g },
            1, 4, 0.0,
        ).unwrap();
        let shortest = results.iter().find(|r| r.route_type == "shortest");
        assert!(shortest.is_some());
        // Le chemin court (1→2→4) = 200m
        assert!(shortest.unwrap().total_distance_m <= 250.0);
    }

    #[test]
    fn test_apex_safest_has_lower_risk() {
        let g = build_test_graph();
        let results = compute_safe_routes(
            &crate::graph::loader::PyGraph { inner: g },
            1, 4, 0.0,
        ).unwrap();
        let shortest = results.iter().find(|r| r.route_type == "shortest");
        let safest   = results.iter().find(|r| r.route_type == "safest");
        if let (Some(sh), Some(sa)) = (shortest, safest) {
            assert!(sa.total_risk <= sh.total_risk,
                "safest doit avoir un risque ≤ shortest");
        }
    }

    #[test]
    fn test_apex_unknown_target_returns_error() {
        let g = build_test_graph();
        let result = run_apex(&g, 1, 9999, 0.1);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("introuvable"));
    }

    #[test]
    fn test_apex_disconnected_returns_error() {
        let mut g = Graph::new();
        g.add_node(Node { id: 1, lat: 51.5, lon: -0.1 });
        g.add_node(Node { id: 2, lat: 51.6, lon: -0.1 });
        // Pas d'arc entre 1 et 2
        let result = run_apex(&g, 1, 2, 0.1);
        assert!(result.is_err());
    }

    #[test]
    fn test_metadata_estimated_time() {
        let g = build_test_graph();
        let results = compute_safe_routes(
            &crate::graph::loader::PyGraph { inner: g },
            1, 4, 0.1,
        ).unwrap();
        for r in &results {
            // Temps = distance / 66.67 m/min
            let expected = r.total_distance_m / 66.67;
            assert!((r.estimated_time_min - expected).abs() < 0.01);
        }
    }

    #[test]
    fn test_metadata_comfort_score_range() {
        let g = build_test_graph();
        let results = compute_safe_routes(
            &crate::graph::loader::PyGraph { inner: g },
            1, 4, 0.1,
        ).unwrap();
        for r in &results {
            assert!(r.comfort_score >= 0.0 && r.comfort_score <= 1.0,
                "comfort_score hors [0,1] : {}", r.comfort_score);
        }
    }

    #[test]
    fn test_haversine_known_distance() {
        // Distance Londres → Paris ≈ 340 km
        let d = haversine_m(51.5074, -0.1278, 48.8566, 2.3522);
        assert!((d - 340_000.0).abs() < 5_000.0,
            "Haversine Londres→Paris : {:.0}m (attendu ~340 000m)", d);
    }

    #[test]
    fn test_familiarity_reduces_cost() {
        // Un arc familier doit avoir un coût pondéré plus faible
        let l_familiar   = super::super::pareto::Label::new(1, 500.0, 0.3, 0.8, vec![]);
        let l_unfamiliar = super::super::pareto::Label::new(1, 500.0, 0.3, 0.0, vec![]);
        assert!(
            l_familiar.weighted_cost(W1_DISTANCE, W2_RISK, W3_FAMILIARITY)
            < l_unfamiliar.weighted_cost(W1_DISTANCE, W2_RISK, W3_FAMILIARITY),
            "La familiarité doit réduire le coût pondéré"
        );
    }
}

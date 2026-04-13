// Fait par Gillesto
// tests/integration.rs — Tests d'intégration Rust pour SafeRoute
//
// Ces tests n'importent PAS PyGraph (qui nécessite la DLL Python au runtime).
// Ils testent directement les structures internes : Graph, Label, ParetoSet, KDE.
// Les tests A*pex utilisent la fonction interne via un helper local.

use saferoute_core::algorithms::astar_apex::haversine_m;
use saferoute_core::algorithms::pareto::{Label, ParetoSet};
use saferoute_core::graph::{Edge, Graph, Node};
use saferoute_core::scoring::risk::{kde_risk_score, normalize_scores, CrimeEvent};

// ── Helpers ───────────────────────────────────────────────────────────────────

fn build_graph() -> Graph {
    let mut g = Graph::new();
    for (id, lat, lon) in [
        (1u64, 51.500f64, -0.100f64),
        (2,    51.501,    -0.100),
        (3,    51.500,    -0.095),
        (4,    51.501,    -0.090),
    ] {
        g.add_node(Node { id, lat, lon });
    }
    g.add_edge(Edge { from: 1, to: 2, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
    g.add_edge(Edge { from: 2, to: 4, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
    g.add_edge(Edge { from: 1, to: 4, distance_m: 900.0, risk_score: 0.05, familiarity: 0.0 });
    g.add_edge(Edge { from: 1, to: 3, distance_m: 400.0, risk_score: 0.4, familiarity: 0.8 });
    g.add_edge(Edge { from: 3, to: 4, distance_m: 400.0, risk_score: 0.4, familiarity: 0.8 });
    g
}

fn label(dist: f64, risk: f64) -> Label {
    Label::new(1, dist, risk, 0.0, vec![])
}

// ── Tests graphe ──────────────────────────────────────────────────────────────

#[test]
fn test_graph_node_count() {
    assert_eq!(build_graph().nodes.len(), 4);
}

#[test]
fn test_graph_edge_count() {
    assert_eq!(build_graph().edges.len(), 5);
}

#[test]
fn test_graph_neighbors_count() {
    let g = build_graph();
    let neighbors: Vec<_> = g.neighbors(1).collect();
    assert_eq!(neighbors.len(), 3);
}

#[test]
fn test_graph_no_neighbors_for_unknown_node() {
    let g = build_graph();
    assert!(g.neighbors(9999).count() == 0);
}

// ── Tests Pareto ──────────────────────────────────────────────────────────────

#[test]
fn test_label_ord_compiles_and_works() {
    use std::cmp::Reverse;
    use std::collections::BinaryHeap;

    let mut heap: BinaryHeap<Reverse<Label>> = BinaryHeap::new();
    heap.push(Reverse(label(300.0, 0.5)));
    heap.push(Reverse(label(100.0, 0.9)));
    heap.push(Reverse(label(200.0, 0.3)));

    let Reverse(first) = heap.pop().unwrap();
    assert_eq!(first.cost_distance, 100.0, "BinaryHeap doit retourner la distance minimale");
}

#[test]
fn test_pareto_dominance_correctness() {
    let l1 = label(1.0, 1.0);
    let l2 = label(2.0, 2.0);
    assert!(l1.dominates(&l2));
    assert!(!l2.dominates(&l1));
    assert!(!l1.dominates(&l1));
}

#[test]
fn test_pareto_set_invariant() {
    let mut set = ParetoSet::new();
    set.try_insert(label(1.0, 3.0));
    set.try_insert(label(3.0, 1.0));
    set.try_insert(label(2.0, 2.0));

    let labels = set.labels();
    for i in 0..labels.len() {
        for j in 0..labels.len() {
            if i != j {
                assert!(!labels[i].dominates(&labels[j]),
                    "Invariant Pareto violé : labels[{}] domine labels[{}]", i, j);
            }
        }
    }
}

#[test]
fn test_pareto_set_rejects_dominated() {
    let mut set = ParetoSet::new();
    set.try_insert(label(1.0, 1.0));
    assert!(!set.try_insert(label(2.0, 2.0)));
    assert_eq!(set.labels().len(), 1);
}

#[test]
fn test_pareto_set_prunes_existing() {
    let mut set = ParetoSet::new();
    set.try_insert(label(2.0, 2.0));
    assert!(set.try_insert(label(1.0, 1.0)));
    assert_eq!(set.labels().len(), 1);
    assert_eq!(set.labels()[0].cost_distance, 1.0);
}

#[test]
fn test_weighted_cost() {
    let l = Label::new(1, 1000.0, 0.5, 0.3, vec![]);
    let cost = l.weighted_cost(1.0, 2.0, 0.5);
    assert!((cost - 1000.85).abs() < 1e-9);
}

// ── Tests KDE ─────────────────────────────────────────────────────────────────

#[test]
fn test_kde_zero_crimes() {
    assert_eq!(kde_risk_score(51.5, -0.1, &[], 300.0), 0.0);
}

#[test]
fn test_kde_crime_at_point_gives_max() {
    let crimes = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
    let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
    assert!((score - 1.0).abs() < 1e-9);
}

#[test]
fn test_kde_distant_crime_low_score() {
    let crimes = vec![CrimeEvent { lat: 51.6, lon: -0.1, weight: 1.0 }];
    let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
    assert!(score < 0.001);
}

#[test]
fn test_kde_weight_amplifies_score() {
    let c1 = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
    let c3 = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 3.0 }];
    let s1 = kde_risk_score(51.5, -0.1, &c1, 300.0);
    let s3 = kde_risk_score(51.5, -0.1, &c3, 300.0);
    assert!((s3 - 3.0 * s1).abs() < 1e-9);
}

#[test]
fn test_normalize_scores() {
    let mut scores = vec![0.0, 5.0, 10.0, 2.5];
    normalize_scores(&mut scores);
    assert!((scores[2] - 1.0).abs() < 1e-9);
    assert!((scores[1] - 0.5).abs() < 1e-9);
    assert_eq!(scores[0], 0.0);
}

#[test]
fn test_normalize_empty() {
    let mut scores: Vec<f64> = vec![];
    normalize_scores(&mut scores);
}

// ── Tests haversine ───────────────────────────────────────────────────────────

#[test]
fn test_haversine_zero_distance() {
    let d = haversine_m(51.5, -0.1, 51.5, -0.1);
    assert!(d < 1.0);
}

#[test]
fn test_haversine_london_paris() {
    let d = haversine_m(51.5074, -0.1278, 48.8566, 2.3522);
    assert!((d - 340_000.0).abs() < 5_000.0);
}

// ── Test de scalabilité (grille 1024 nœuds) ──────────────────────────────────
// Note : ce test valide la structure du graphe et les calculs Pareto/KDE
// sans appeler compute_safe_routes (qui nécessite PyO3 au runtime sur Windows).

#[test]
fn test_scalability_graph_construction() {
    use std::time::Instant;

    let size = 32usize;
    let dlat = 0.001f64;
    let dlon = 0.001f64;
    let mut g = Graph::new();

    for i in 0..size {
        for j in 0..size {
            let id = (i * size + j + 1) as u64;
            g.add_node(Node { id, lat: 51.5 + i as f64 * dlat, lon: -0.1 + j as f64 * dlon });
        }
    }
    for i in 0..size {
        for j in 0..size {
            let u = (i * size + j + 1) as u64;
            if j + 1 < size {
                let v = (i * size + j + 2) as u64;
                g.add_edge(Edge { from: u, to: v, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
            }
            if i + 1 < size {
                let v = ((i + 1) * size + j + 1) as u64;
                g.add_edge(Edge { from: u, to: v, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
            }
        }
    }

    let t0 = Instant::now();
    assert_eq!(g.nodes.len(), size * size);
    let neighbor_count: usize = g.nodes.iter().map(|n| g.neighbors(n.id).count()).sum();
    let elapsed = t0.elapsed();

    assert!(neighbor_count > 0);
    assert!(elapsed.as_secs_f64() < 1.0,
        "Parcours des voisins sur 1024 nœuds doit être < 1s, obtenu {:.3}s", elapsed.as_secs_f64());

    println!("Scalabilité 1024 nœuds : {:.3}ms, {} arcs sortants totaux",
        elapsed.as_secs_f64() * 1000.0, neighbor_count);
}

// Fait par Gillesto
// tests/integration.rs — Tests d'intégration Rust pour SafeRoute
//
// Ces tests sont dans core/tests/ (pas dans src/) → exécutés par `cargo test`
// sans être compilés dans la lib finale. C'est la convention Rust pour les
// tests d'intégration : ils testent l'API publique du crate comme un utilisateur externe.
//
// Lancer : cargo test  (depuis SafeRoute/core/)

use saferoute_core::algorithms::astar_apex::{compute_safe_routes, haversine_m};
use saferoute_core::algorithms::pareto::{Label, ParetoSet};
use saferoute_core::graph::{Edge, Graph, Node};
use saferoute_core::graph::loader::PyGraph;
use saferoute_core::scoring::risk::{kde_risk_score, normalize_scores, CrimeEvent};

// ── Helpers ───────────────────────────────────────────────────────────────────

/// Graphe de test : 4 nœuds, 3 chemins alternatifs
///  1 ──(court, risqué)──► 2 ──► 4
///  1 ──(long, sûr)──────────────► 4
///  1 ──(moyen, familier)──► 3 ──► 4
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

fn py_graph() -> PyGraph {
    PyGraph { inner: build_graph() }
}

// ── Tests graphe ──────────────────────────────────────────────────────────────

#[test]
fn test_graph_node_count() {
    let g = build_graph();
    assert_eq!(g.nodes.len(), 4);
}

#[test]
fn test_graph_edge_count() {
    let g = build_graph();
    assert_eq!(g.edges.len(), 5);
}

#[test]
fn test_graph_neighbors_count() {
    let g = build_graph();
    let neighbors: Vec<_> = g.neighbors(1).collect();
    assert_eq!(neighbors.len(), 3); // arcs 1→2, 1→4, 1→3
}

#[test]
fn test_graph_no_neighbors_for_unknown_node() {
    let g = build_graph();
    let neighbors: Vec<_> = g.neighbors(9999).collect();
    assert!(neighbors.is_empty());
}

// ── Tests Pareto ──────────────────────────────────────────────────────────────

#[test]
fn test_label_ord_compiles_and_works() {
    // Ce test vérifie que le bug bloquant (Label sans Ord) est corrigé
    use std::cmp::Reverse;
    use std::collections::BinaryHeap;

    let mut heap: BinaryHeap<Reverse<Label>> = BinaryHeap::new();
    heap.push(Reverse(Label::new(1, 300.0, 0.5, 0.0, vec![])));
    heap.push(Reverse(Label::new(2, 100.0, 0.9, 0.0, vec![])));
    heap.push(Reverse(Label::new(3, 200.0, 0.3, 0.0, vec![])));

    let Reverse(first) = heap.pop().unwrap();
    assert_eq!(first.cost_distance, 100.0, "BinaryHeap doit retourner la distance minimale");
}

#[test]
fn test_pareto_dominance_correctness() {
    let l1 = Label::new(1, 1.0, 1.0, 0.0, vec![]);
    let l2 = Label::new(1, 2.0, 2.0, 0.0, vec![]);
    assert!(l1.dominates(&l2));
    assert!(!l2.dominates(&l1));
    assert!(!l1.dominates(&l1)); // un label ne se domine pas lui-même
}

#[test]
fn test_pareto_set_invariant() {
    let mut set = ParetoSet::new();
    set.try_insert(Label::new(1, 1.0, 3.0, 0.0, vec![]));
    set.try_insert(Label::new(1, 3.0, 1.0, 0.0, vec![]));
    set.try_insert(Label::new(1, 2.0, 2.0, 0.0, vec![]));

    // Vérifie l'invariant : aucun label ne domine un autre
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

// ── Tests A*pex ───────────────────────────────────────────────────────────────

#[test]
fn test_apex_returns_routes() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.1).unwrap();
    assert!(!results.is_empty(), "A*pex doit trouver au moins un chemin");
}

#[test]
fn test_apex_route_types_present() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.0).unwrap();
    let types: Vec<&str> = results.iter().map(|r| r.route_type.as_str()).collect();
    assert!(types.contains(&"shortest"), "Route 'shortest' manquante");
    assert!(types.contains(&"safest"),   "Route 'safest' manquante");
}

#[test]
fn test_apex_shortest_is_shortest() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.0).unwrap();
    let shortest = results.iter().find(|r| r.route_type == "shortest").unwrap();
    let safest   = results.iter().find(|r| r.route_type == "safest").unwrap();
    assert!(shortest.total_distance_m <= safest.total_distance_m,
        "shortest ({:.0}m) doit être ≤ safest ({:.0}m)",
        shortest.total_distance_m, safest.total_distance_m);
}

#[test]
fn test_apex_safest_has_lower_risk() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.0).unwrap();
    let shortest = results.iter().find(|r| r.route_type == "shortest").unwrap();
    let safest   = results.iter().find(|r| r.route_type == "safest").unwrap();
    assert!(safest.total_risk <= shortest.total_risk,
        "safest (risk={:.3}) doit être ≤ shortest (risk={:.3})",
        safest.total_risk, shortest.total_risk);
}

#[test]
fn test_apex_paths_are_valid() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.1).unwrap();
    for r in &results {
        assert!(!r.path.is_empty(), "Le chemin ne doit pas être vide");
        assert_eq!(*r.path.first().unwrap(), 1u64, "Le chemin doit commencer à la source");
        assert_eq!(*r.path.last().unwrap(),  4u64, "Le chemin doit finir à la destination");
    }
}

#[test]
fn test_apex_metadata_time_positive() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.1).unwrap();
    for r in &results {
        assert!(r.estimated_time_min > 0.0, "Le temps estimé doit être positif");
    }
}

#[test]
fn test_apex_comfort_score_in_range() {
    let g = py_graph();
    let results = compute_safe_routes(&g, 1, 4, 0.1).unwrap();
    for r in &results {
        assert!(r.comfort_score >= 0.0 && r.comfort_score <= 1.0,
            "comfort_score={} hors [0,1]", r.comfort_score);
    }
}

#[test]
fn test_apex_unknown_target_error() {
    let g = py_graph();
    let result = compute_safe_routes(&g, 1, 9999, 0.1);
    assert!(result.is_err());
}

#[test]
fn test_apex_disconnected_graph_error() {
    let mut g = Graph::new();
    g.add_node(Node { id: 1, lat: 51.5, lon: -0.1 });
    g.add_node(Node { id: 2, lat: 51.6, lon: -0.1 });
    // Aucun arc → graphe déconnecté
    let pg = PyGraph { inner: g };
    let result = compute_safe_routes(&pg, 1, 2, 0.1);
    assert!(result.is_err(), "Un graphe déconnecté doit retourner une erreur");
}

// ── Tests KDE ─────────────────────────────────────────────────────────────────

#[test]
fn test_kde_zero_crimes() {
    let score = kde_risk_score(51.5, -0.1, &[], 300.0);
    assert_eq!(score, 0.0);
}

#[test]
fn test_kde_crime_at_point_gives_max() {
    let crimes = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
    let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
    assert!((score - 1.0).abs() < 1e-9, "Score attendu 1.0, obtenu {}", score);
}

#[test]
fn test_kde_distant_crime_low_score() {
    let crimes = vec![CrimeEvent { lat: 51.6, lon: -0.1, weight: 1.0 }];
    let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
    assert!(score < 0.001, "Crime à ~11km doit donner score < 0.001, obtenu {}", score);
}

#[test]
fn test_kde_weight_amplifies_score() {
    let crimes_w1 = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
    let crimes_w3 = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 3.0 }];
    let s1 = kde_risk_score(51.5, -0.1, &crimes_w1, 300.0);
    let s3 = kde_risk_score(51.5, -0.1, &crimes_w3, 300.0);
    assert!((s3 - 3.0 * s1).abs() < 1e-9, "Le poids doit amplifier le score linéairement");
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
    normalize_scores(&mut scores); // ne doit pas paniquer
}

// ── Tests haversine ───────────────────────────────────────────────────────────

#[test]
fn test_haversine_zero_distance() {
    let d = haversine_m(51.5, -0.1, 51.5, -0.1);
    assert!(d < 1.0, "Distance d'un point à lui-même doit être ~0");
}

#[test]
fn test_haversine_london_paris() {
    let d = haversine_m(51.5074, -0.1278, 48.8566, 2.3522);
    assert!((d - 340_000.0).abs() < 5_000.0,
        "Londres→Paris : {:.0}m (attendu ~340 000m)", d);
}

// ── Test de scalabilité (graphe synthétique 1000 nœuds) ──────────────────────

#[test]
fn test_scalability_1000_nodes() {
    use std::time::Instant;

    // Grille 32×32 ≈ 1024 nœuds
    let mut g = Graph::new();
    let size = 32usize;
    let dlat = 0.001f64;
    let dlon = 0.001f64;

    for i in 0..size {
        for j in 0..size {
            let id = (i * size + j + 1) as u64;
            g.add_node(Node {
                id,
                lat: 51.5 + i as f64 * dlat,
                lon: -0.1 + j as f64 * dlon,
            });
        }
    }
    for i in 0..size {
        for j in 0..size {
            let u = (i * size + j + 1) as u64;
            if j + 1 < size {
                let v = (i * size + j + 2) as u64;
                g.add_edge(Edge { from: u, to: v, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
                g.add_edge(Edge { from: v, to: u, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
            }
            if i + 1 < size {
                let v = ((i + 1) * size + j + 1) as u64;
                g.add_edge(Edge { from: u, to: v, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
                g.add_edge(Edge { from: v, to: u, distance_m: 111.0, risk_score: 0.3, familiarity: 0.0 });
            }
        }
    }

    let pg = PyGraph { inner: g };
    let source = 1u64;
    let target = (size * size) as u64;

    let t0 = Instant::now();
    let results = compute_safe_routes(&pg, source, target, 0.2).unwrap();
    let elapsed = t0.elapsed();

    assert!(!results.is_empty(), "Doit trouver des routes sur la grille");
    assert!(elapsed.as_secs_f64() < 2.0,
        "Calcul sur 1024 nœuds doit être < 2s, obtenu {:.3}s", elapsed.as_secs_f64());

    println!("Scalabilité 1024 nœuds : {:.3}s, {} routes", elapsed.as_secs_f64(), results.len());
}

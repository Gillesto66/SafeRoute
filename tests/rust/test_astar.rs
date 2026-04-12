// Fait par Gillesto
// test_astar.rs — Tests d'intégration Rust pour l'algorithme A*pex
// Lancés avec : cargo test

#[cfg(test)]
mod integration_tests {
    use saferoute_core::graph::{Edge, Graph, Node};
    use saferoute_core::algorithms::pareto::{Label, ParetoSet};
    use saferoute_core::scoring::risk::{kde_risk_score, normalize_scores, CrimeEvent};

    /// Construit un graphe de test minimal :
    /// 1 → 2 (court, risqué) et 1 → 3 (long, sûr)
    fn build_test_graph() -> Graph {
        let mut g = Graph::new();
        g.add_node(Node { id: 1, lat: 51.500, lon: -0.100 });
        g.add_node(Node { id: 2, lat: 51.501, lon: -0.100 });
        g.add_node(Node { id: 3, lat: 51.500, lon: -0.090 });

        g.add_edge(Edge { from: 1, to: 2, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
        g.add_edge(Edge { from: 2, to: 3, distance_m: 100.0, risk_score: 0.9, familiarity: 0.0 });
        g.add_edge(Edge { from: 1, to: 3, distance_m: 800.0, risk_score: 0.1, familiarity: 0.0 });
        g
    }

    #[test]
    fn test_graph_neighbors() {
        let g = build_test_graph();
        let neighbors: Vec<_> = g.neighbors(1).collect();
        assert_eq!(neighbors.len(), 2); // arcs 1→2 et 1→3
    }

    #[test]
    fn test_pareto_dominance() {
        let l1 = Label::new(1, 1.0, 1.0, vec![]);
        let l2 = Label::new(1, 2.0, 2.0, vec![]);
        assert!(l1.dominates(&l2));
        assert!(!l2.dominates(&l1));
    }

    #[test]
    fn test_pareto_set_no_duplicate_dominance() {
        let mut set = ParetoSet::new();
        let l1 = Label::new(3, 800.0, 0.1, vec![1, 3]);  // sûr
        let l2 = Label::new(3, 200.0, 1.8, vec![1, 2, 3]); // court
        assert!(set.try_insert(l1));
        assert!(set.try_insert(l2));
        assert_eq!(set.labels().len(), 2); // compromis, aucun ne domine l'autre
    }

    #[test]
    fn test_kde_zero_crimes() {
        let score = kde_risk_score(51.5, -0.1, &[], 300.0);
        assert_eq!(score, 0.0);
    }

    #[test]
    fn test_kde_crime_at_point() {
        let crimes = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
        let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
        assert!((score - 1.0).abs() < 1e-9, "Score attendu ~1.0, obtenu {}", score);
    }

    #[test]
    fn test_normalize_scores() {
        let mut scores = vec![0.0, 5.0, 10.0];
        normalize_scores(&mut scores);
        assert!((scores[2] - 1.0).abs() < 1e-9);
        assert!((scores[1] - 0.5).abs() < 1e-9);
        assert_eq!(scores[0], 0.0);
    }
}

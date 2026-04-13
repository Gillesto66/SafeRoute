// Fait par Gillesto
// pareto.rs — Gestion de la frontière de Pareto (labels non-dominés)
//
// Leçon Rust : BinaryHeap<T> exige que T implémente Ord.
// f64 n'implémente PAS Ord (à cause de NaN), donc Label non plus par défaut.
// Solution : on implémente manuellement PartialOrd + Ord sur Label
// en traitant les NaN comme des valeurs maximales (comportement sûr).

use crate::graph::NodeId;

/// Label multi-objectif attaché à un nœud pendant la recherche A*pex.
/// Représente un chemin partiel avec ses coûts cumulés.
#[derive(Debug, Clone, PartialEq)]
pub struct Label {
    pub node: NodeId,
    pub cost_distance: f64,   // objectif 1 : distance cumulée (mètres)
    pub cost_risk: f64,       // objectif 2 : risque cumulé [0, N]
    pub cost_familiarity: f64,// objectif 3 : familiarité cumulée [0, N] (bonus négatif)
    pub path: Vec<NodeId>,    // séquence de nœuds pour reconstruction
}

impl Label {
    pub fn new(
        node: NodeId,
        cost_distance: f64,
        cost_risk: f64,
        cost_familiarity: f64,
        path: Vec<NodeId>,
    ) -> Self {
        Self { node, cost_distance, cost_risk, cost_familiarity, path }
    }

    /// Coût scalaire pondéré : C = w1·dist + w2·risk - w3·familiarity
    /// Utilisé pour le tri dans la priority queue (heuristique f = g + h)
    #[inline]
    pub fn weighted_cost(&self, w1: f64, w2: f64, w3: f64) -> f64 {
        w1 * self.cost_distance + w2 * self.cost_risk - w3 * self.cost_familiarity
    }

    /// Dominance de Pareto biobjectif (distance + risque).
    /// La familiarité est un bonus, pas un objectif à minimiser séparément.
    /// self domine other ⟺ self ≤ other sur dist ET risk, ET < sur au moins un.
    pub fn dominates(&self, other: &Label) -> bool {
        self.cost_distance <= other.cost_distance
            && self.cost_risk <= other.cost_risk
            && (self.cost_distance < other.cost_distance
                || self.cost_risk < other.cost_risk)
    }
}

// ── Implémentation de Ord pour BinaryHeap ────────────────────────────────────
// Leçon Rust : Ord est requis par BinaryHeap. On trie par cost_distance
// (objectif principal), avec cost_risk comme tie-breaker.
// On utilise total_cmp() qui gère NaN de façon déterministe (NaN > tout).

impl Eq for Label {}

impl PartialOrd for Label {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Label {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // Tri par distance d'abord, puis par risque
        self.cost_distance
            .total_cmp(&other.cost_distance)
            .then(self.cost_risk.total_cmp(&other.cost_risk))
    }
}

// ── ParetoSet ─────────────────────────────────────────────────────────────────

/// Ensemble de labels non-dominés pour un nœud donné.
/// Invariant : aucun label ne domine un autre dans cet ensemble.
#[derive(Debug, Default)]
pub struct ParetoSet {
    labels: Vec<Label>,
}

impl ParetoSet {
    pub fn new() -> Self {
        Self::default()
    }

    /// Tente d'insérer un label.
    /// Retourne `true` si inséré (non dominé).
    /// Supprime les labels existants dominés par le nouveau.
    pub fn try_insert(&mut self, candidate: Label) -> bool {
        if self.labels.iter().any(|l| l.dominates(&candidate)) {
            return false;
        }
        self.labels.retain(|l| !candidate.dominates(l));
        self.labels.push(candidate);
        true
    }

    pub fn labels(&self) -> &[Label] {
        &self.labels
    }

    pub fn is_empty(&self) -> bool {
        self.labels.is_empty()
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::cmp::Reverse;
    use std::collections::BinaryHeap;

    fn label(dist: f64, risk: f64) -> Label {
        Label::new(1, dist, risk, 0.0, vec![])
    }

    #[test]
    fn test_dominance_basic() {
        let l1 = label(1.0, 1.0);
        let l2 = label(2.0, 2.0);
        assert!(l1.dominates(&l2));
        assert!(!l2.dominates(&l1));
    }

    #[test]
    fn test_no_dominance_tradeoff() {
        let l1 = label(1.0, 3.0);
        let l2 = label(3.0, 1.0);
        assert!(!l1.dominates(&l2));
        assert!(!l2.dominates(&l1));
    }

    #[test]
    fn test_equal_labels_no_dominance() {
        let l1 = label(2.0, 2.0);
        let l2 = label(2.0, 2.0);
        assert!(!l1.dominates(&l2)); // égaux → pas de dominance stricte
    }

    #[test]
    fn test_pareto_set_insert_and_prune() {
        let mut set = ParetoSet::new();
        assert!(set.try_insert(label(1.0, 3.0)));
        assert!(set.try_insert(label(3.0, 1.0)));
        // (2.0, 2.0) n'est dominé par aucun des deux
        assert!(set.try_insert(label(2.0, 2.0)));
        assert_eq!(set.labels().len(), 3);
    }

    #[test]
    fn test_pareto_set_rejects_dominated() {
        let mut set = ParetoSet::new();
        set.try_insert(label(1.0, 1.0));
        // (2.0, 2.0) est dominé par (1.0, 1.0)
        assert!(!set.try_insert(label(2.0, 2.0)));
        assert_eq!(set.labels().len(), 1);
    }

    #[test]
    fn test_pareto_set_prunes_existing() {
        let mut set = ParetoSet::new();
        set.try_insert(label(2.0, 2.0));
        // (1.0, 1.0) domine (2.0, 2.0) → doit supprimer l'existant
        assert!(set.try_insert(label(1.0, 1.0)));
        assert_eq!(set.labels().len(), 1);
        assert_eq!(set.labels()[0].cost_distance, 1.0);
    }

    #[test]
    fn test_label_ord_in_binary_heap() {
        // Vérifie que Label peut être utilisé dans BinaryHeap<Reverse<Label>>
        // (c'est le bug bloquant corrigé dans cette version)
        let mut heap: BinaryHeap<Reverse<Label>> = BinaryHeap::new();
        heap.push(Reverse(label(300.0, 0.5)));
        heap.push(Reverse(label(100.0, 0.9)));
        heap.push(Reverse(label(200.0, 0.3)));

        // Le min-heap doit retourner la distance la plus courte en premier
        let Reverse(first) = heap.pop().unwrap();
        assert_eq!(first.cost_distance, 100.0);
    }

    #[test]
    fn test_weighted_cost() {
        let l = Label::new(1, 1000.0, 0.5, 0.3, vec![]);
        // C = 1.0*1000 + 2.0*0.5 - 0.5*0.3 = 1000 + 1.0 - 0.15 = 1000.85
        let cost = l.weighted_cost(1.0, 2.0, 0.5);
        assert!((cost - 1000.85).abs() < 1e-9);
    }
}

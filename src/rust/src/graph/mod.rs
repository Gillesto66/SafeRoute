// Fait par Gillesto
// graph/mod.rs — Structures de données du graphe routier

pub mod loader;

use serde::{Deserialize, Serialize};

pub type NodeId = u64;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub id: NodeId,
    pub lat: f64,
    pub lon: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub from: NodeId,
    pub to: NodeId,
    pub distance_m: f64,
    pub risk_score: f64,
    pub familiarity: f64,
}

#[derive(Debug, Default)]
pub struct Graph {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub adjacency: std::collections::HashMap<NodeId, Vec<usize>>,
}

impl Graph {
    pub fn new() -> Self { Self::default() }

    pub fn add_node(&mut self, node: Node) {
        self.nodes.push(node);
    }

    pub fn add_edge(&mut self, edge: Edge) {
        let idx = self.edges.len();
        self.adjacency.entry(edge.from).or_default().push(idx);
        self.edges.push(edge);
    }

    pub fn neighbors(&self, node_id: NodeId) -> impl Iterator<Item = &Edge> {
        self.adjacency
            .get(&node_id)
            .map(|idxs| idxs.as_slice())
            .unwrap_or(&[])
            .iter()
            .map(|&i| &self.edges[i])
    }
}

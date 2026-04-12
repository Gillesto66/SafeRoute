// Fait par Gillesto
// graph/loader.rs — Chargement du graphe depuis JSON (produit par OSMnx côté Python)
// Protocole : Python sérialise le graphe OSMnx en JSON → Rust le désérialise

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use super::{Edge, Graph, Node, NodeId};

/// Format JSON attendu depuis Python/OSMnx
#[derive(Deserialize)]
struct GraphJson {
    nodes: Vec<NodeJson>,
    edges: Vec<EdgeJson>,
}

#[derive(Deserialize)]
struct NodeJson {
    id: NodeId,
    lat: f64,
    lon: f64,
}

#[derive(Deserialize)]
struct EdgeJson {
    from: NodeId,
    to: NodeId,
    distance_m: f64,
    risk_score: f64,
    familiarity: Option<f64>, // optionnel, défaut 0.0
}

/// Wrapper Python-visible du graphe Rust
#[pyclass]
pub struct PyGraph {
    pub inner: Graph,
}

#[pymethods]
impl PyGraph {
    /// Construit un PyGraph depuis une chaîne JSON
    /// Appelé depuis Python : `PyGraph.from_json(json_str)`
    #[staticmethod]
    pub fn from_json(json_str: &str) -> PyResult<Self> {
        let data: GraphJson = serde_json::from_str(json_str)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

        let mut graph = Graph::new();

        for n in data.nodes {
            graph.add_node(Node { id: n.id, lat: n.lat, lon: n.lon });
        }

        for e in data.edges {
            graph.add_edge(Edge {
                from: e.from,
                to: e.to,
                distance_m: e.distance_m,
                risk_score: e.risk_score,
                familiarity: e.familiarity.unwrap_or(0.0),
            });
        }

        Ok(PyGraph { inner: graph })
    }

    /// Nombre de nœuds (utile pour les tests Python)
    pub fn node_count(&self) -> usize {
        self.inner.nodes.len()
    }

    /// Nombre d'arcs
    pub fn edge_count(&self) -> usize {
        self.inner.edges.len()
    }
}

// Fait par Gillesto
// lib.rs — Point d'entrée PyO3 : expose le moteur Rust à Python

use pyo3::prelude::*;

pub mod algorithms;
pub mod graph;
pub mod scoring;

use algorithms::astar_apex::PyRouteResult;
use graph::loader::PyGraph;

#[pymodule]
fn saferoute_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyGraph>()?;
    m.add_class::<PyRouteResult>()?;
    m.add_function(wrap_pyfunction!(algorithms::astar_apex::compute_safe_routes, m)?)?;
    Ok(())
}

# SafeRoute — Fait par Gillesto

Bibliothèque hybride Python + Rust de routage sûr multi-objectif.
Villes MVP : Londres (Police UK API) et Le Cap (Cape Town Open Data).

## Prérequis

- Rust stable (`rustup install stable`)
- Python 3.10+
- `maturin` (`pip install maturin`)

## Installation

```bash
# 1. Compiler le core Rust et l'installer dans l'env Python
cd bindings/python
pip install -e ".[dev]"
maturin develop --release

# 2. Lancer les tests Rust
cd ../../core
cargo test

# 3. Lancer les tests Python
cd ..
pytest tests/python/

# 4. Démarrer l'API
uvicorn api.main:app --reload
```

## Utilisation rapide

```python
from saferoute import SafeRouteEngine

engine = SafeRouteEngine(eps=0.1)
engine.load_city("London, UK", crime_points=[...])

pareto = engine.compute_routes(source_node=123456, target_node=789012)
print(pareto.shortest)   # Route la plus courte
print(pareto.safest)     # Route la plus sûre
print(pareto.balanced)   # Compromis confort
```

## Formule de coût

```
C_total = w1 * Distance + w2 * Risque - w3 * Familiarité
```

Algorithme : A*pex biobjectif (Zhang et al., ICAPS 2022)

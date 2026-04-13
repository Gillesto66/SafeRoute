# SafeRoute

> Fait par Gillesto

[![CI](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/saferoute)](https://pypi.org/project/saferoute/)
[![Python](https://img.shields.io/pypi/pyversions/saferoute)](https://pypi.org/project/saferoute/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://gillesto66.github.io/SafeRoute/)

**Bibliothèque de routage piéton sûr multi-objectif** — calcule 3 itinéraires Pareto-optimaux
en tenant compte de la distance, du risque criminel et de la familiarité de l'utilisateur.

Core Rust compilé via PyO3/maturin. Données réelles : **Londres** (Police UK API) et **Le Cap** (SAPS).

## Installation

```bash
pip install saferoute
pip install "saferoute[api]"   # avec le serveur FastAPI
```

> Rust n'est **pas** requis pour l'installation — le wheel contient le binaire précompilé.

## Exemple rapide

```python
from saferoute import SafeRouteEngine

engine = SafeRouteEngine(eps=0.1)
engine.load_city("london")

source = engine.nearest_node(lat=51.5074, lon=-0.1278)
target = engine.nearest_node(lat=51.5155, lon=-0.0922)

pareto = engine.compute_routes(source, target)
print(pareto.shortest)   # Route la plus courte
print(pareto.safest)     # Route la plus sûre
print(pareto.balanced)   # Compromis confort
```

## Formule de coût

```
C = w₁ · Distance + w₂ · Risque − w₃ · Familiarité
```

Algorithme : **A\*pex** ε-approximé (Zhang et al., ICAPS 2022)

## Documentation

[https://gillesto66.github.io/SafeRoute/](https://gillesto66.github.io/SafeRoute/)

## Développement

```bash
# Prérequis : Rust (https://rustup.rs)
pip install -e ".[dev,api]"
python -m maturin develop --release
python -m pytest tests/ -q
```

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le guide complet.

## Licence

MIT — voir [LICENSE](LICENSE)

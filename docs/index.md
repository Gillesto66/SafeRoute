# SafeRoute

> Fait par Gillesto

**Bibliothèque de routage piéton sûr multi-objectif** — calcule 3 itinéraires Pareto-optimaux
entre deux points en tenant compte de la distance, du risque criminel et de la familiarité
de l'utilisateur avec les rues.

[![CI](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/saferoute)](https://pypi.org/project/saferoute/)
[![Python](https://img.shields.io/pypi/pyversions/saferoute)](https://pypi.org/project/saferoute/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Fonctionnalités

- **Algorithme A\*pex** — recherche de chemins multi-objectif ε-approximée (Zhang et al., ICAPS 2022)
- **Scoring KDE** — estimation par noyau gaussien de la densité criminelle sur chaque arc
- **Familiarité** — les routes connues de l'utilisateur voient leur coût réduit
- **3 itinéraires Pareto** — `shortest`, `safest`, `balanced`
- **Core Rust** — moteur de calcul compilé via PyO3/maturin pour des performances maximales
- **API REST** — FastAPI avec 7 endpoints, compatible React et Flutter

## Installation rapide

```bash
pip install saferoute
pip install "saferoute[api]"   # avec le serveur FastAPI
```

## Exemple en 10 lignes

```python
from saferoute import SafeRouteEngine

# Initialiser le moteur
engine = SafeRouteEngine(eps=0.1)

# Charger une ville (utilise le cache local si disponible)
engine.load_city("london")

# Convertir des coordonnées GPS en NodeId OSM
source = engine.nearest_node(lat=51.5074, lon=-0.1278)  # Centre de Londres
target = engine.nearest_node(lat=51.5155, lon=-0.0922)  # Shoreditch

# Calculer les 3 itinéraires Pareto-optimaux
pareto = engine.compute_routes(source, target)

print(pareto.shortest)   # Route la plus courte
print(pareto.safest)     # Route la plus sûre
print(pareto.balanced)   # Compromis confort
```

## Formule de coût

```
C = w₁ · Distance + w₂ · Risque − w₃ · Familiarité
```

## Villes supportées

| Ville | Source des données | Graphe |
|-------|-------------------|--------|
| Londres | [data.police.uk](https://data.police.uk) | 501k nœuds, 1.2M arcs |
| Le Cap | Données SAPS | 127k nœuds, 360k arcs |

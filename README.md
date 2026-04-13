# SafeRoute

> Fait par Gillesto

[![CI](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/Gillesto66/SafeRoute/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/saferoute)](https://pypi.org/project/saferoute/)
[![Python](https://img.shields.io/pypi/pyversions/saferoute)](https://pypi.org/project/saferoute/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://gillesto66.github.io/SafeRoute/)

---

## Qu'est-ce que SafeRoute ?

SafeRoute est une **bibliothèque Python de routage piéton sûr** qui calcule simultanément
trois itinéraires entre deux points d'une ville, en optimisant des objectifs contradictoires :

| Itinéraire | Optimise | Compromis |
|------------|----------|-----------|
| `shortest` | Distance minimale | Peut traverser des zones à risque |
| `safest` | Risque criminel minimal | Peut allonger le trajet de 20–40% |
| `balanced` | Équilibre distance + sécurité + familiarité | Recommandé pour un usage quotidien |

Le moteur de calcul est écrit en **Rust** (algorithme A\*pex, KDE gaussien) et exposé à Python
via PyO3/maturin. Les données de criminalité proviennent de sources officielles :
**Police UK API** pour Londres et **SAPS** pour Le Cap.

---

## Pourquoi SafeRoute ?

Les applications de navigation classiques (Google Maps, Waze) optimisent uniquement la distance
ou le temps. SafeRoute résout un problème différent : **comment rentrer chez soi en sécurité ?**

La formule de coût intègre trois dimensions :

```
C = w₁ · Distance + w₂ · Risque − w₃ · Familiarité
```

- **Risque** : densité criminelle sur chaque segment de rue, calculée par KDE gaussien
  à partir des données historiques de criminalité géolocalisées
- **Familiarité** : les rues que vous empruntez régulièrement voient leur coût réduit —
  une rue connue est une rue plus sûre subjectivement
- **Algorithme** : A\*pex ε-approximé (Zhang et al., ICAPS 2022) — garantit des solutions
  à 10% de l'optimal Pareto exact, avec des temps de calcul < 2 secondes sur Londres

---

## Installation

```bash
# Bibliothèque seule (calcul d'itinéraires)
pip install saferoute

# Avec le serveur REST FastAPI
pip install "saferoute[api]"
```

> Rust n'est **pas** requis — le wheel PyPI contient le binaire Rust précompilé.

---

## Exemple concret : trouver le chemin le plus sûr à Londres

```python
from saferoute import SafeRouteEngine
from saferoute.exceptions import SafeRouteError

# 1. Initialiser le moteur (eps=0.1 → approximation à 10% de l'optimal)
engine = SafeRouteEngine(eps=0.1)

# 2. Charger la ville — utilise le cache local si disponible,
#    télécharge OSMnx + données de criminalité sinon (~5 min la première fois)
engine.load_city("london")

# 3. Convertir des coordonnées GPS en identifiants de nœuds OSM
#    Départ : Gare de London Bridge
source = engine.nearest_node(lat=51.5055, lon=-0.0873)
#    Arrivée : Borough Market
target = engine.nearest_node(lat=51.5055, lon=-0.0910)

# 4. Calculer les 3 itinéraires Pareto-optimaux
try:
    pareto = engine.compute_routes(source, target)
except SafeRouteError as e:
    print(f"Erreur : {e}")
    raise

# 5. Comparer les résultats
print(f"Plus court  : {pareto.shortest.total_distance_m:.0f}m "
      f"en {pareto.shortest.estimated_time_min:.1f} min "
      f"(risque={pareto.shortest.total_risk:.3f})")

print(f"Plus sûr    : {pareto.safest.total_distance_m:.0f}m "
      f"en {pareto.safest.estimated_time_min:.1f} min "
      f"(risque={pareto.safest.total_risk:.3f})")

print(f"Équilibré   : {pareto.balanced.total_distance_m:.0f}m "
      f"en {pareto.balanced.estimated_time_min:.1f} min "
      f"(risque={pareto.balanced.total_risk:.3f})")

# Exemple de sortie typique :
# Plus court  : 380m en 5.7 min (risque=0.847)
# Plus sûr    : 510m en 7.7 min (risque=0.112)
# Équilibré   : 430m en 6.5 min (risque=0.341)

# 6. Enregistrer le trajet effectué pour améliorer les recommandations futures
#    (les rues empruntées régulièrement voient leur coût réduit)
engine.record_trip(pareto.balanced.path)
```

---

## Utiliser l'API REST

```bash
# Démarrer le serveur
uvicorn saferoute.api.main:app --reload
# → Documentation interactive : http://localhost:8000/docs
```

```bash
# Charger une ville
curl -X POST http://localhost:8000/api/v1/load-city \
     -H "Content-Type: application/json" \
     -d '{"city": "london"}'

# Calculer les 3 itinéraires
curl -X POST http://localhost:8000/api/v1/route \
     -H "Content-Type: application/json" \
     -d '{
       "city": "london",
       "source_node": 123456789,
       "target_node": 987654321,
       "eps": 0.1
     }'
```

Réponse JSON consommable directement par React ou Flutter :

```json
{
  "city": "london",
  "shortest": {
    "path": [123456789, 111, 222, 987654321],
    "total_distance_m": 380.0,
    "distance_km": 0.38,
    "total_risk": 0.847,
    "estimated_time_min": 5.7,
    "comfort_score": 0.17,
    "route_type": "shortest"
  },
  "safest": { "..." : "..." },
  "balanced": { "..." : "..." }
}
```

---

## Villes supportées

| Ville | Données de criminalité | Graphe routier |
|-------|----------------------|----------------|
| **Londres** | [data.police.uk](https://data.police.uk) — 100k crimes/trimestre | 501k nœuds, 1.2M arcs |
| **Le Cap** | SAPS — 30 stations de police | 127k nœuds, 360k arcs |

---

## Architecture

```
SafeRoute/
├── src/
│   ├── saferoute/          ← Package Python
│   │   ├── engine.py       ← Orchestrateur principal
│   │   ├── exceptions.py   ← SafeRouteError, GraphNotLoadedError, ...
│   │   └── api/            ← Serveur FastAPI (optionnel)
│   └── rust/               ← Core de calcul Rust
│       └── src/
│           ├── algorithms/ ← A*pex + frontière de Pareto
│           ├── graph/      ← Structures Node, Edge, Graph
│           └── scoring/    ← KDE gaussien
└── tests/                  ← 102 tests Python + 19 tests Rust
```

**Protocole Python ↔ Rust :** Python sérialise le graphe enrichi (OSMnx + scores KDE + familiarité)
en JSON → Rust désérialise, exécute A\*pex, retourne les 3 routes → Python convertit en dataclasses.

---

## Documentation complète

[https://gillesto66.github.io/SafeRoute/](https://gillesto66.github.io/SafeRoute/)

---

## Développement

```bash
# Prérequis : Rust (https://rustup.rs)
git clone https://github.com/Gillesto66/SafeRoute.git
cd SafeRoute
pip install -e ".[dev,api]"
python -m maturin develop --release   # compile le core Rust

# Tests
python -m pytest tests/ -q            # 102 tests Python
cargo test --test integration         # 19 tests Rust
```

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le guide complet.

---

## Licence

MIT — voir [LICENSE](LICENSE)

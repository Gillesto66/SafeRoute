# Architecture

> Fait par Gillesto

## Vue d'ensemble

```
SafeRoute/
├── src/
│   ├── saferoute/          ← Package Python (src-layout PyPA)
│   │   ├── engine.py       ← Orchestrateur principal
│   │   ├── graph_cache.py  ← Cache .graphml + .csv.gz
│   │   ├── kde_scorer.py   ← Scoring KDE vectorisé
│   │   ├── familiarity.py  ← Familiarité utilisateur
│   │   ├── data_loader.py  ← Ingestion Police UK + SAPS
│   │   ├── exceptions.py   ← Hiérarchie SafeRouteError
│   │   └── api/            ← FastAPI REST
│   └── rust/               ← Core Rust (PyO3/maturin)
│       └── src/
│           ├── algorithms/ ← A*pex + Pareto
│           ├── graph/      ← Graph, Node, Edge
│           └── scoring/    ← KDE gaussien
└── tests/                  ← 102 tests Python
```

## Protocole Python ↔ Rust

```
Python                          Rust
  │                               │
  │  JSON (nodes + edges)         │
  │ ─────────────────────────►   │
  │  PyGraph.from_json()          │
  │                               │
  │  compute_safe_routes()        │
  │ ─────────────────────────►   │
  │                          run_apex()
  │                          BinaryHeap<Label>
  │                          ParetoSet
  │                               │
  │  Vec<PyRouteResult>           │
  │ ◄─────────────────────────   │
  │                               │
  ▼                               ▼
ParetoSet.from_results()
```

## Formule de coût

```
C = w₁ · Distance + w₂ · Risque − w₃ · Familiarité

w₁ = 1.0    (distance en mètres)
w₂ = 500.0  (risque ∈ [0,1], amplifié)
w₃ = 200.0  (familiarité ∈ [0,1], bonus)
```

# Changelog

> Fait par Gillesto — Format [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/)

## [0.1.0] — 2026-04-12

### Ajouté
- Algorithme A\*pex biobjectif (distance + risque) avec ε-approximation configurable
- Scoring KDE gaussien avec calibration automatique du bandwidth (règle de Silverman)
- Variable de familiarité : `C = w₁·D + w₂·R − w₃·F`
- 3 itinéraires Pareto-optimaux : `shortest`, `safest`, `balanced`
- Métadonnées enrichies : `estimated_time_min`, `comfort_score`, `node_count`
- Cache local `.graphml` + `.csv.gz` avec `platformdirs` (zéro chemin absolu)
- API REST FastAPI : 7 endpoints (`/route`, `/load-city`, `/risk-map`, `/nearest-node`, `/familiarity/*`, `/health`)
- Données réelles : Londres (501k nœuds, 100k crimes Police UK) + Le Cap (127k nœuds, SAPS)
- Core Rust compilé via PyO3/maturin — `saferoute_core.so`
- 102 tests Python + 20 tests Rust d'intégration
- CI/CD GitHub Actions : 3 OS × 3 Python + publication TestPyPI/PyPI

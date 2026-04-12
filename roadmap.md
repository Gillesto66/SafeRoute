# SafeRoute — Roadmap Technique
> Fait par Gillesto | Dernière mise à jour : Sprint 0 terminé

---

## Légende
- ✅ Fait — code présent, fonctionnel, testé
- 🟡 Partiel — squelette ou logique présente mais incomplet / non validé en conditions réelles
- ❌ À faire — non commencé

---

## Sprint 0 — Architecture & Fondations ✅ TERMINÉ

| Statut | Livrable |
|--------|----------|
| ✅ | Arborescence du projet (`core/`, `bindings/`, `api/`, `tests/`) |
| ✅ | `Cargo.toml` avec dépendances Rust (pyo3, serde, ordered-float, thiserror) |
| ✅ | `pyproject.toml` avec dépendances Python (maturin, osmnx, scipy, fastapi, pydantic) |
| ✅ | Structures de données Rust : `Node`, `Edge`, `Graph` avec liste d'adjacence |
| ✅ | Protocole de communication Python → Rust via JSON + `PyGraph.from_json()` |
| ✅ | Binding PyO3 : `lib.rs` expose `PyGraph` et `compute_safe_routes` à Python |
| ✅ | Dataclasses Python : `Route`, `RiskScore`, `ParetoSet` |
| ✅ | `README.md` avec instructions d'installation et d'utilisation |

---

## Phase 1 — Acquisition et Modélisation des Données ✅ TERMINÉE — 43/43 tests ✅

### 1.1 Graphe Routier OSM
| Statut | Tâche |
|--------|-------|
| ✅ | Intégration OSMnx dans `engine.py` (`graph_from_place` + `add_edge_lengths`) |
| ✅ | Sérialisation du graphe NetworkX → JSON → Rust |
| ✅ | **Cache local du graphe** — `graph_cache.py` : save/load `.graphml` + métadonnées JSON |
| ✅ | **Validation du graphe** — `graph_validator.py` : SCC, attributs, bbox, rapport complet |
| ✅ | **Extraction SCC principale** — `extract_largest_scc()` garantit la connexité totale |
| ✅ | **Script de téléchargement** — `scripts/download_cities.py` avec `--city`, `--force`, `--cache-dir` |
| ✅ | **Graphe Londres** : config OSMnx prête (`Greater London, United Kingdom`, walk) |
| ✅ | **Graphe Le Cap** : config OSMnx prête (`Cape Town, Western Cape, South Africa`, walk) |

### 1.2 Ingestion Données de Criminalité
| Statut | Tâche |
|--------|-------|
| ✅ | **`fetch_london_crimes()`** — requêtes par polygone d'arrondissement (pas de limite de rayon) |
| ✅ | **Pagination / couverture complète** — 32 arrondissements × N mois, requêtes parallèles (asyncio + semaphore) |
| ✅ | **Découpage en quadrants** — si >10 000 crimes dans un arrondissement (Westminster, Southwark) |
| ✅ | **Dédupliquation** par `persistent_id` Police UK |
| ✅ | **`fetch_cape_town_crimes()`** — 30 stations SAPS géolocalisées, distribution gaussienne pondérée par crime_index |
| ✅ | **Pondération par catégorie** — 15 catégories Londres + 15 catégories SAPS Le Cap |
| ✅ | **Stockage local** — `graph_cache.py` : crimes en `.csv.gz` (compressé, portable) |
| ✅ | **Validation des données** — `validate_crimes()` : doublons, hors bbox, poids invalides, rapport stats |

### 1.3 Scoring de Risque KDE
| Statut | Tâche |
|--------|-------|
| ✅ | KDE gaussien Rust (`risk.rs`) : noyau, haversine, normalisation — avec tests unitaires |
| ✅ | **`kde_scorer.py`** — module dédié remplaçant le KDE inline dans engine.py |
| ✅ | **Calibration du bandwidth** — règle de Silverman pondérée (n_effectif de Kish) |
| ✅ | **Limites du bandwidth** — plancher 200m, plafond 800m (distances piétonnes pertinentes) |
| ✅ | **Évaluation vectorisée** — batch numpy sur tous les centroïdes d'arcs (performance) |
| ✅ | **Pondération par type de crime** pour Le Cap (crime_index par station SAPS) |
| ✅ | **Statistiques KDE** — min, max, mean, std, p50, p90, p99 des scores |
| ✅ | **`get_risk_map_geojson()`** — export GeoJSON pour visualisation frontend |

---

## Phase 2 — Moteur "Safe-Path" ✅ TERMINÉE — 66/66 tests Python ✅ + 20 tests Rust

### 2.1 Algorithme A*pex Multi-Objectif
| Statut | Tâche |
|--------|-------|
| ✅ | Structure `Label` avec dominance de Pareto |
| ✅ | **`Label` implémente `Ord`** — bug bloquant corrigé, `BinaryHeap` compile |
| ✅ | `ParetoSet` : insertion, pruning, invariant garanti — 6 tests unitaires |
| ✅ | `run_apex()` : boucle BinaryHeap + pruning ε-approximé + formule `C = w1·D + w2·R - w3·F` |
| ✅ | Heuristique admissible haversine |
| ✅ | **Gestion des graphes déconnectés** — erreur explicite si source/target inatteignables |
| ✅ | **Test de scalabilité** — grille 1024 nœuds < 2s dans `tests/integration.rs` |
| ✅ | **20 tests Rust** dans `core/tests/integration.rs` (déclaré dans `Cargo.toml`) |

### 2.2 Variable de Familiarité
| Statut | Tâche |
|--------|-------|
| ✅ | **`familiarity.py`** — `FamiliarityMap` + `FamiliarityEngine` complets |
| ✅ | **Module de simulation** — `simulate_trajectories()` : N trajets via NetworkX shortest_path |
| ✅ | **Intégration dans la formule** — `C = w1·D + w2·R - w3·F` active dans `run_apex` |
| ✅ | **`record_trip()`** — mise à jour temps réel depuis un trajet utilisateur |
| ✅ | **Persistance** — `save()` / `load()` JSON pour conserver la familiarité entre sessions |
| ✅ | **Décroissance temporelle** — `decay()` : les routes non empruntées perdent en familiarité |

### 2.3 Frontière de Pareto — 3 Options Utilisateur
| Statut | Tâche |
|--------|-------|
| ✅ | Sélection shortest / safest / balanced |
| ✅ | **Métadonnées enrichies** — `estimated_time_min`, `node_count`, `comfort_score` sur chaque route |
| ✅ | Routes dédupliquées si la frontière de Pareto est dégénérée |

---

## Phase 3 — API, Tests & Déploiement ✅ TERMINÉE — 102/102 tests Python ✅

### 3.1 API FastAPI
| Statut | Tâche |
|--------|-------|
| ✅ | `POST /api/v1/route` — 3 itinéraires Pareto, schémas enrichis (temps, confort, familiarité) |
| ✅ | `GET /api/v1/health` — état du moteur + ville chargée |
| ✅ | **`POST /api/v1/load-city`** — charge une ville à la demande (london / cape_town) |
| ✅ | **`GET /api/v1/risk-map`** — heatmap GeoJSON consommable par Mapbox/Leaflet/Flutter |
| ✅ | **`POST /api/v1/nearest-node`** — convertit GPS → NodeId OSM (pour clients mobiles) |
| ✅ | **`POST /api/v1/familiarity/record`** — enregistre un trajet utilisateur |
| ✅ | **`GET /api/v1/familiarity/stats`** — statistiques de familiarité |
| ✅ | **Rate limiting** — 60 req/min par IP (in-memory, extensible Redis) |
| ✅ | **CORS restreint** — localhost:3000/8080/4200 (React/Vue/Angular dev) |
| ✅ | Sérialisation JSON compatible React / Flutter |

### 3.2 Tests
| Statut | Tâche |
|--------|-------|
| ✅ | Tests unitaires Rust : `pareto.rs`, `risk.rs` — intégrés dans le crate |
| ✅ | **20 tests Rust** dans `core/tests/integration.rs` |
| ✅ | **25 tests API** dans `test_phase3_api.py` (tous endpoints + rate limit + erreurs) |
| ✅ | **6 tests E2E** dans `test_phase3_e2e.py` (pipeline complète offline) |
| ✅ | Tests Phase 1 (43) + Phase 2 (23) + Phase 3 (31) + anciens (5) = **102 tests Python** |

### 3.3 Déploiement & Livraison
| Statut | Tâche |
|--------|-------|
| ✅ | **Notebook Jupyter** — `notebooks/saferoute_demo.ipynb` : heatmap + 3 itinéraires + frontière de Pareto |
| ✅ | **Carte interactive Folium** — heatmap de risque + 3 routes colorées dans le notebook |
| ✅ | **Docker** — `Dockerfile` multi-stage (builder Rust + runtime Python slim) |
| ✅ | **CI/CD GitHub Actions** — `cargo test` + `pytest` + `maturin build` (3 OS × 3 Python) |
| 🟡 | **Publication PyPI** — `maturin publish` (nécessite Rust installé + compte PyPI) |

---

## Bugs & Dettes Techniques Identifiés

| Priorité | Problème | Fichier |
|----------|----------|---------|
|  IMPORTANT | `fetch_london_crimes()` : à tester contre l'API réelle (réseau requis) | `data_loader.py` |
| 🟡 MINEUR | `allow_origins=["*"]` en CORS — à restreindre avant production | `api/main.py` |
| 🟡 MINEUR | `POST /familiarity` endpoint API non implémenté (Phase 3) | `api/routes.py` |

---

## Prochaines Actions Prioritaires (Phase 3)

1. **Installer Rust** via https://rustup.rs → `cargo test` (20 tests d'intégration)
2. **`maturin develop --release`** → compiler le core Rust et activer le binding Python
3. **`python scripts/download_cities.py`** → télécharger les vrais graphes (réseau requis)
4. **Notebook Jupyter** → démonstration visuelle des 3 itinéraires (livrable roadmap originale)
5. **Endpoints API manquants** : `POST /load-city`, `GET /risk-map`, `POST /familiarity`
6. **CI/CD GitHub Actions** : `cargo test` + `pytest` à chaque push

---

## Vider le cache pour passer en données réelles

```bash
# Option 1 — Supprimer uniquement les graphes (re-télécharge OSMnx)
del SafeRoute\data\cache\london_graph.graphml
del SafeRoute\data\cache\cape_town_graph.graphml

# Option 2 — Supprimer uniquement les crimes (re-télécharge Police UK)
del SafeRoute\data\cache\london_crimes.csv.gz
del SafeRoute\data\cache\cape_town_crimes.csv.gz

# Option 3 — Tout vider (recommandé pour passer au mode online)
Remove-Item -Recurse -Force SafeRoute\data\cache\*

# Puis re-télécharger avec les vraies données
python SafeRoute\scripts\download_cities.py

# Ou forcer le re-téléchargement même si le cache existe
python SafeRoute\scripts\download_cities.py --force
```

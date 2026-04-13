# SafeRoute — Roadmap Ultime de Production (PyPI-Ready)
> Fait par Gillesto | Industrialisation complète — build, audit, doc, versioning, publication

---

## Légende
- ✅ Fait — présent, fonctionnel, validé, Acceptance Criteria atteints
- 🟡 Partiel — squelette présent, Acceptance Criteria non atteints
- ❌ À faire — non commencé

---

## Architecture du pipeline de déploiement

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE COMPLET AVANT PUBLICATION PyPI                   │
│                                                                              │
│  CODE SOURCE                                                                 │
│      │                                                                       │
│      ▼                                                                       │
│  ① QUALITÉ PYTHON          ruff (lint) + mypy (types) + PEP 561             │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ② TESTS PYTHON            pytest 102 tests (smoke + integration)           │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ③ QUALITÉ RUST            cargo fmt + cargo clippy -D warnings             │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ④ SÉCURITÉ RUST           cargo audit (CVE check)                          │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑤ TESTS RUST              cargo test (20 tests intégration)                │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑥ VERSIONING              tag git == pyproject.toml == Cargo.toml          │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑦ BUILD WHEEL             maturin build --release (3 OS × 3 Python)       │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑧ AUDIT WHEEL             check-wheel-contents (pas de fichiers parasites) │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑨ DOCUMENTATION           mkdocs build (docstrings Google → HTML)          │
│      │  ✗ → bloque                                                           │
│      ▼                                                                       │
│  ⑩ PUBLICATION             maturin publish → TestPyPI → PyPI               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase A — Refactoring de Structure ✅ TERMINÉE

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | src-layout `src/saferoute/` | `python -m pytest tests/` découvre 102 tests sans config |
| ✅ | Rust dans `src/rust/` | `cargo test` fonctionne depuis `SafeRoute/` |
| ✅ | Workspace Rust racine `Cargo.toml` | `cargo build` depuis `SafeRoute/` sans descendre |
| ✅ | Suppression `bindings/`, `core/`, `api/` | Aucun répertoire résiduel |
| ✅ | `sys.path` injection supprimée dans `api/main.py` | `grep -r "bindings" src/` retourne vide |
| ✅ | `platformdirs` dans `graph_cache.py` | `SAFEROUTE_CACHE_DIR` ou `user_cache_dir("saferoute")` |
| ✅ | `.gitignore` complet | `data/cache/`, `target/`, `dist/`, `*.so`, `__pycache__/` exclus |
| ✅ | `conftest.py` isole le cache | `SAFEROUTE_CACHE_DIR` → tmpdir pendant les tests |

---

## Phase B — Industrialisation du Build ✅ Config / ❌ Exécution

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | `pyproject.toml` complet — maturin build-backend | `python -m maturin --version` ≥ 1.5 |
| ✅ | `[tool.maturin]` — `manifest-path`, `python-source`, `module-name` | `module-name = "saferoute.saferoute_core"` |
| ✅ | `compatibility = "manylinux2014"` | Wheels Linux compatibles PyPI |
| ✅ | `exclude` — `data/**`, `notebooks/**`, `scripts/**`, `tests/**` | Wheel < 5 MB |
| ✅ | Extras `[api]`, `[dev]`, `[docs]` (mkdocs) | `pip install "saferoute[docs]"` installe mkdocs |
| ✅ | `[profile.release]` — `lto=true`, `strip=true`, `panic="abort"` | `.so` < 2 MB |
| ✅ | `crate-type = ["cdylib", "rlib"]` | `cargo test` compile sans erreur |
| ✅ | `src/rust/Cargo.toml` version = `0.1.0` | Synchronisé avec `pyproject.toml` |
| ✅ | `scripts/bump_version.sh` | Met à jour `pyproject.toml` + `Cargo.toml` en une commande |
| 🟡 | `maturin develop --release` validé localement | **Bloqué : Rust non installé** — AC : `from saferoute.saferoute_core import PyGraph` sans erreur |
| ❌ | `maturin build --release` produit un wheel | AC : `dist/saferoute-0.1.0-*.whl` existe et contient `saferoute_core.pyd`/`.so` |

---

## Phase C — Qualité & Conformité ✅ TERMINÉE

### C.1 — Validation Python : ruff + mypy (PEP 561) ✅

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | `src/saferoute/py.typed` créé (fichier vide) | `mypy` ne lève pas `error: Skipping analyzing "saferoute"` |
| ✅ | `ruff>=0.4` dans `[dev]`, `mypy>=1.10` dans `[dev]` | `pip install -e ".[dev]"` installe les deux |
| ✅ | `[tool.ruff]` configuré dans `pyproject.toml` | `python -m ruff check src/` retourne 0 erreur |
| ✅ | `[tool.mypy]` configuré dans `pyproject.toml` | `warn_return_any = true`, `warn_unused_ignores = true` |
| ✅ | CI `publish.yml` — job `lint` (ruff + mypy) | Job bloque si erreur |

### C.2 — Audit de sécurité Rust : cargo-audit ✅

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | `src/rust/audit.toml` créé | `deny = ["warnings", "unmaintained", "unsound", "yanked"]` |
| ✅ | CI `publish.yml` — job `audit-rust` avec `--deny warnings` | Job bloque si CVE détectée |
| 🟡 | `cargo audit` exécuté localement | **Bloqué : Rust non installé** — AC : 0 vulnérabilité |

### C.3 — Gestion d'erreurs typée : exceptions.py ✅

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | `src/saferoute/exceptions.py` créé | `SafeRouteError(Exception)` présent |
| ✅ | `GraphNotLoadedError`, `RouteNotFoundError`, `CacheCorruptionError`, `UnsupportedCityError` | Chaque exception a une docstring Google |
| ✅ | `CacheCorruptionError` levée si `.graphml` corrompu | `try/except` autour de `ox.load_graphml()` dans `graph_cache.py` |
| ✅ | `UnsupportedCityError` levée dans `engine.py` | Remplace `ValueError` générique |
| ✅ | `GraphNotLoadedError` levée dans `engine.py` | Remplace `RuntimeError` générique |
| ✅ | Exceptions exposées dans `__init__.py` | `from saferoute import SafeRouteError` fonctionne |
| ✅ | 102 tests passent avec les nouvelles exceptions | `pytest tests/ -q` → 102 passed |

### C.4 — Documentation automatisée : mkdocs + mkdocstrings ✅

| Statut | Tâche | Acceptance Criteria |
|--------|-------|---------------------|
| ✅ | `mkdocs`, `mkdocstrings[python]`, `mkdocs-material` dans `[docs]` extra | `pip install "saferoute[docs]"` installe les 3 |
| ✅ | `mkdocs.yml` créé à la racine | Fichier valide avec navigation complète |
| ✅ | `docs/index.md` — page d'accueil | Description, installation, exemple 10 lignes |
| ✅ | `docs/installation.md`, `docs/quickstart.md`, `docs/architecture.md` | Pages présentes |
| ✅ | `docs/api/` — 6 pages par module | `engine.md`, `models.md`, `exceptions.md`, `graph_cache.md`, `kde_scorer.md`, `familiarity.md` |
| ✅ | `docs/contributing.md`, `docs/changelog.md` | Pages présentes |
| ✅ | CI `publish.yml` — job `docs` avec `mkdocs build --strict` | Job bloque si warning |
| ✅ | `mkdocs gh-deploy` dans `publish.yml` (production uniquement) | Déploiement GitHub Pages |
| 🟡 | `mkdocs build --strict` exécuté localement | AC : `pip install "saferoute[docs]"` puis `mkdocs build --strict` → 0 erreur |

### C.5 — Fichiers de packaging obligatoires ✅

| Statut | Fichier | Acceptance Criteria |
|--------|---------|---------------------|
| ✅ | `README.md` | Badge CI + `pip install saferoute` + exemple 10 lignes + lien doc |
| ✅ | `LICENSE` | Texte MIT complet avec année 2026 et auteur Gillesto |
| ✅ | `CHANGELOG.md` | Version `0.1.0` avec liste des fonctionnalités, format Keep a Changelog |
| ✅ | `CONTRIBUTING.md` | Setup dev : `rustup`, `maturin develop`, `pytest`, `ruff`, `mypy` |
| ✅ | `src/saferoute/py.typed` | Fichier vide — marqueur PEP 561 |

---

## Phase D — Versioning & Audit du Wheel ✅ TERMINÉE

### D.1 — Synchronisation versions + tests Rust ✅

| Statut | Tâche | Résultat réel |
|--------|-------|---------------|
| ✅ | `pyproject.toml` version = `0.1.0` | Confirmé |
| ✅ | `src/rust/Cargo.toml` version = `0.1.0` | Synchronisé |
| ✅ | PyO3 mis à jour vers `0.23` | Python 3.13 supporté (0.21 ne supportait que ≤ 3.12) |
| ✅ | Import inutilisé `Serialize` + `HashMap` supprimé dans `loader.rs` | 0 warning `cargo build` |
| ✅ | `cargo test --test integration` — 19 tests | **19/19 passed** en 0.01s |
| ✅ | `scripts/bump_version.sh` | Met à jour les deux fichiers en une commande |

> Note Windows : `cargo test --lib` échoue sur Python Microsoft Store (DLL virtuelle).
> Utiliser `cargo test --test integration` qui ne nécessite pas la DLL Python au runtime.

### D.2 — Build wheel + audit ✅

| Statut | Tâche | Résultat réel |
|--------|-------|---------------|
| ✅ | `maturin build --release --out dist/` | `saferoute-0.1.0-cp313-cp313-win_amd64.whl` produit en 1m04s |
| ✅ | Contenu du wheel vérifié | `saferoute_core.cp313-win_amd64.pyd` (285 KB) + tous les modules Python + `py.typed` + `LICENSE` |
| ✅ | Aucun fichier parasite | Pas de `data/`, `notebooks/`, `.graphml`, `.csv.gz` |
| ✅ | `check-wheel-contents dist/*.whl` | **OK** — 0 erreur |
| ✅ | Taille du wheel | ~500 KB (bien < 5 MB) |

---

## Phase E — Test de Déploiement 🟡 EN COURS

### E.1 — Prérequis ✅

| Étape | Action | Statut |
|-------|--------|--------|
| 1 | Rust 1.94.1 installé | ✅ `rustc 1.94.1` |
| 2 | `cargo --version` | ✅ `cargo 1.94.1` |
| 3 | `cargo install cargo-audit` | ❌ À faire (nécessite connexion) |
| 4 | Compte https://test.pypi.org | ✅ Compte PyPI existant |
| 5 | Compte https://pypi.org | ✅ Compte PyPI existant |
| 6 | API token TestPyPI | ❌ À générer |
| 7 | Secret GitHub `PYPI_TOKEN` | ❌ À ajouter |

### E.2 — Validation locale ✅ (partielle)

| Étape | Commande | Statut |
|-------|----------|--------|
| ① | `cargo test --test integration` | ✅ **19/19 passed** |
| ② | `python -m pytest tests/ -q` | ✅ **102/102 passed** |
| ③ | `maturin build --release` | ✅ `saferoute-0.1.0-cp313-cp313-win_amd64.whl` |
| ④ | `check-wheel-contents dist/*.whl` | ✅ **OK** |
| ⑤ | `cargo audit` | ❌ cargo-audit non installé |
| ⑥ | `mkdocs build --strict` | ❌ `pip install ".[docs]"` requis |

### E.3 — Publication TestPyPI ❌

```powershell
# Depuis SafeRoute/ — après avoir configuré le token
python -m maturin publish --repository testpypi
```

| Étape | Commande | Statut |
|-------|----------|--------|
| 1 | Générer token sur https://test.pypi.org | ❌ |
| 2 | `maturin publish --repository testpypi` | ❌ |
| 3 | Vérifier https://test.pypi.org/project/saferoute/ | ❌ |

### E.4 — Publication PyPI production ❌

```powershell
git tag v0.1.0
git push origin v0.1.0
# GitHub Actions → Publish to PyPI → target: pypi
```

| Étape | Action | Statut |
|-------|--------|--------|
| 1 | `git tag v0.1.0 && git push origin v0.1.0` | ❌ |
| 2 | GitHub Actions → `Publish to PyPI` → `target: pypi` | ❌ |
| 3 | `pip install saferoute` depuis PyPI | ❌ |

---

## Récapitulatif global

| Phase | Description | Statut | Bloquant |
|-------|-------------|--------|----------|
| **A** | Refactoring src-layout | ✅ Terminée | — |
| **B** | Build maturin configuré + wheel produit | ✅ Terminée | — |
| **C.1** | ruff + mypy + PEP 561 (`py.typed`) | ✅ Terminée | — |
| **C.2** | cargo-audit (CVE) + `audit.toml` | ✅ Config / ❌ Exécution locale | cargo-audit non installé |
| **C.3** | `exceptions.py` + gestion d'erreurs typée | ✅ Terminée | — |
| **C.4** | mkdocs + mkdocstrings + docs/ | ✅ Terminée | — |
| **C.5** | LICENSE, CHANGELOG, CONTRIBUTING, py.typed, README | ✅ Terminée | — |
| **D.1** | PyO3 0.23, versions sync, 19 tests Rust ✅ | ✅ Terminée | — |
| **D.2** | Wheel buildé + check-wheel-contents OK | ✅ Terminée | — |
| **E.1** | Rust installé, compte PyPI existant | ✅ Partielle | Token TestPyPI à générer |
| **E.2** | 102 tests Python + 19 tests Rust + wheel OK | ✅ Partielle | cargo-audit + mkdocs |
| **E.3** | Publication TestPyPI | ❌ | Token requis |
| **E.4** | Publication PyPI production | ❌ | E.3 validé |

---

## Ordre d'exécution recommandé

```
1. Installer Rust (rustup.rs)
   └── débloque : cargo-audit, maturin develop, cargo test
         │
         ▼
2. Créer exceptions.py + py.typed
   └── débloque : mypy sans erreur
         │
         ▼
3. Créer LICENSE + CHANGELOG.md + CONTRIBUTING.md
         │
         ▼
4. Configurer ruff + mypy → 0 erreur
         │
         ▼
5. cargo audit → 0 CVE
         │
         ▼
6. Créer mkdocs.yml + docs/ → mkdocs build --strict
         │
         ▼
7. Mettre à jour README.md (badges + lien doc)
         │
         ▼
8. Synchroniser versions pyproject.toml == Cargo.toml
         │
         ▼
9. maturin build --release → dist/*.whl
         │
         ▼
10. check-wheel-contents dist/*.whl
         │
         ▼
11. Test installation venv propre
         │
         ▼
12. maturin publish --repository testpypi
         │
         ▼
13. git tag v0.1.0 + publish.yml → PyPI
```

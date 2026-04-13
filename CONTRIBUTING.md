# Guide de contribution

> Fait par Gillesto

## Setup développeur

```bash
# 1. Installer Rust (https://rustup.rs)
# Windows : télécharger rustup-init.exe
# Linux/macOS :
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 2. Vérifier Rust
rustc --version   # >= 1.75
cargo --version

# 3. Cloner le dépôt
git clone https://github.com/Gillesto66/SafeRoute.git
cd SafeRoute

# 4. Installer les dépendances Python
pip install -e ".[dev,api,docs]"

# 5. Compiler le core Rust
python -m maturin develop --release

# 6. Vérifier l'installation complète
python -c "from saferoute.saferoute_core import PyGraph; print('Rust OK')"
python -m pytest tests/ -q
```

## Standards de qualité (gates bloquants)

Chaque contribution doit passer tous ces checks avant merge :

```bash
# Python — style et types
python -m ruff check src/
python -m ruff format src/
python -m mypy src/saferoute/ --ignore-missing-imports

# Python — tests
python -m pytest tests/ -v --tb=short

# Rust — style et linting
cargo fmt --check --manifest-path src/rust/Cargo.toml
cargo clippy --manifest-path src/rust/Cargo.toml -- -D warnings

# Rust — sécurité
cargo audit --manifest-path src/rust/Cargo.toml

# Rust — tests
cargo test --manifest-path src/rust/Cargo.toml --verbose

# Documentation
mkdocs build --strict
```

## Règle de versioning (SemVer 2.0.0)

**Aucun build de production ne peut être publié sans un tag Git correspondant
strictement à la version dans `pyproject.toml` ET `src/rust/Cargo.toml`.**

```bash
# Bumper la version (met à jour les deux fichiers)
bash scripts/bump_version.sh 0.2.0

# Committer et tagger
git add pyproject.toml src/rust/Cargo.toml
git commit -m "chore: bump version to 0.2.0"
git tag v0.2.0
git push origin main --tags

# Déclencher la publication depuis GitHub Actions
# → Actions → "Publish to PyPI" → Run workflow → target: testpypi
```

## En-têtes de fichiers

Chaque fichier source doit commencer par :
- Python : `# Fait par Gillesto`
- Rust : `// Fait par Gillesto`

## Docstrings

Standard Google obligatoire pour toutes les fonctions et classes publiques :

```python
def ma_fonction(arg1: str, arg2: int = 0) -> bool:
    """Description courte en une ligne.

    Description longue optionnelle sur plusieurs lignes.

    Args:
        arg1: Description du premier argument.
        arg2: Description du second argument.

    Returns:
        Description de la valeur retournée.

    Raises:
        SafeRouteError: Si quelque chose ne va pas.
    """
```

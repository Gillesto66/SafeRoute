# Contribution

> Fait par Gillesto

## Setup développeur

```bash
# 1. Installer Rust
# https://rustup.rs

# 2. Cloner et installer
git clone https://github.com/Gillesto66/SafeRoute.git
cd SafeRoute
pip install -e ".[dev,api,docs]"
python -m maturin develop --release

# 3. Vérifier
python -m pytest tests/ -q
cargo test --manifest-path src/rust/Cargo.toml
```

## Standards de qualité

```bash
# Linting Python
python -m ruff check src/
python -m ruff format src/

# Typage Python
python -m mypy src/saferoute/ --ignore-missing-imports

# Linting Rust
cargo fmt --manifest-path src/rust/Cargo.toml
cargo clippy --manifest-path src/rust/Cargo.toml -- -D warnings

# Audit sécurité Rust
cargo audit --manifest-path src/rust/Cargo.toml
```

## Règle de versioning

Aucun build de production ne peut être publié sans un tag Git correspondant
strictement à la version dans `pyproject.toml` ET `src/rust/Cargo.toml`.

```bash
bash scripts/bump_version.sh 0.2.0
git add pyproject.toml src/rust/Cargo.toml
git commit -m "chore: bump version to 0.2.0"
git tag v0.2.0
git push origin main --tags
```

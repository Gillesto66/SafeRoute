# Installation

> Fait par Gillesto

## Utilisateur final (Rust non requis)

```bash
pip install saferoute
pip install "saferoute[api]"   # avec FastAPI/uvicorn
```

## Développeur (Rust requis)

```bash
# 1. Installer Rust
# Windows : https://rustup.rs → rustup-init.exe
# Linux/macOS :
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 2. Cloner le dépôt
git clone https://github.com/Gillesto66/SafeRoute.git
cd SafeRoute

# 3. Installer les dépendances Python
pip install -e ".[dev,api]"

# 4. Compiler le core Rust
python -m maturin develop --release

# 5. Vérifier l'installation
python -c "from saferoute.saferoute_core import PyGraph; print('Rust OK')"
python -m pytest tests/ -q
```

## Pré-charger les données

```bash
# Télécharger les graphes OSMnx et les données de criminalité
python scripts/download_cities.py

# Mode offline (sans connexion internet)
python scripts/download_cities.py --offline
```

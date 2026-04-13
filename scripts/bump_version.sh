#!/usr/bin/env bash
# Fait par Gillesto
# bump_version.sh — Synchronise la version dans pyproject.toml ET Cargo.toml
#
# Usage : bash scripts/bump_version.sh 0.2.0
#
# Règle SemVer : les deux fichiers DOIVENT avoir la même version.
# Ce script garantit la synchronisation en une seule commande.

set -euo pipefail

NEW_VERSION="${1:-}"

if [ -z "$NEW_VERSION" ]; then
    echo "Usage: bash scripts/bump_version.sh <MAJOR.MINOR.PATCH>"
    echo "Exemple: bash scripts/bump_version.sh 0.2.0"
    exit 1
fi

# Validation format SemVer
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "❌ Format invalide : '$NEW_VERSION' — attendu MAJOR.MINOR.PATCH (ex: 0.2.0)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

PYPROJECT="$ROOT_DIR/pyproject.toml"
CARGO="$ROOT_DIR/src/rust/Cargo.toml"

# Lire les versions actuelles
CURRENT_PY=$(python3 -c "import tomllib; print(tomllib.load(open('$PYPROJECT','rb'))['project']['version'])")
CURRENT_RS=$(python3 -c "import tomllib; print(tomllib.load(open('$CARGO','rb'))['package']['version'])")

echo "Version actuelle : pyproject=$CURRENT_PY | Cargo=$CURRENT_RS"
echo "Nouvelle version : $NEW_VERSION"

# Mettre à jour pyproject.toml
sed -i "s/^version = \"$CURRENT_PY\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"

# Mettre à jour Cargo.toml
sed -i "s/^version *= *\"$CURRENT_RS\"/version = \"$NEW_VERSION\"/" "$CARGO"

# Vérification post-update
NEW_PY=$(python3 -c "import tomllib; print(tomllib.load(open('$PYPROJECT','rb'))['project']['version'])")
NEW_RS=$(python3 -c "import tomllib; print(tomllib.load(open('$CARGO','rb'))['package']['version'])")

if [ "$NEW_PY" != "$NEW_VERSION" ] || [ "$NEW_RS" != "$NEW_VERSION" ]; then
    echo "❌ Échec de la mise à jour : pyproject=$NEW_PY | Cargo=$NEW_RS"
    exit 1
fi

echo "✅ Version mise à jour : $NEW_VERSION"
echo ""
echo "Prochaines étapes :"
echo "  git add pyproject.toml src/rust/Cargo.toml"
echo "  git commit -m \"chore: bump version to $NEW_VERSION\""
echo "  git tag v$NEW_VERSION"
echo "  git push origin main --tags"

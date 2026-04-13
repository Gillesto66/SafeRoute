# Fait par Gillesto
# _cli.py — Point d'entrée CLI pour saferoute-download
#
# Installé comme script via [project.scripts] dans pyproject.toml :
#   saferoute-download --city london
#   saferoute-download --city cape_town --force
#   saferoute-download --offline

import sys
from pathlib import Path


def main() -> None:
    """Point d'entrée du script saferoute-download.

    Délègue à scripts/download_cities.py en ajoutant src/ au path si nécessaire.
    """
    # Quand installé via pip, saferoute est dans le path — import direct
    # Quand lancé en développement, le conftest.py gère le path
    try:
        from saferoute.graph_cache import GraphCache  # noqa: F401 — vérifie l'import
    except ImportError:
        print("Erreur : saferoute n'est pas installé. Lancez `pip install -e '.[dev]'`")
        sys.exit(1)

    # Importe et exécute le script de téléchargement
    import asyncio
    import importlib.util
    import os

    # Cherche download_cities.py dans scripts/ relatif au package installé
    scripts_dir = Path(__file__).resolve().parents[3] / "scripts"
    script_path = scripts_dir / "download_cities.py"

    if not script_path.exists():
        print(f"Script introuvable : {script_path}")
        print("Utilisez directement : python scripts/download_cities.py")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("download_cities", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    asyncio.run(module.main())

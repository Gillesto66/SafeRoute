# Fait par Gillesto
# conftest.py — Configuration pytest : ajoute saferoute au sys.path
#
# Permet de lancer pytest depuis n'importe quel répertoire sans pip install.
# Usage depuis SafeRoute/ :
#   python -m pytest tests/python/ -v

import sys
from pathlib import Path

# Ajoute bindings/python au path pour que `import saferoute` fonctionne
_bindings = Path(__file__).resolve().parents[2] / "bindings" / "python"
if str(_bindings) not in sys.path:
    sys.path.insert(0, str(_bindings))

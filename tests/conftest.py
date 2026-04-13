# Fait par Gillesto
# conftest.py — Configuration pytest pour la nouvelle structure src-layout
#
# Ajoute src/ au sys.path pour que `import saferoute` fonctionne
# sans installation préalable (mode développement).
# Configure SAFEROUTE_CACHE_DIR vers un répertoire temporaire
# pour isoler les tests du cache utilisateur réel.

import os
import sys
from pathlib import Path

# src-layout : ajoute SafeRoute/src/ au path
_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Ajoute SafeRoute/ au path pour que `from saferoute.api import ...` fonctionne
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def pytest_configure(config):
    """Isole le cache SafeRoute dans un répertoire temporaire pendant les tests."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="saferoute_test_cache_")
    os.environ.setdefault("SAFEROUTE_CACHE_DIR", tmp)

# Fait par Gillesto
# main.py — Point d'entrée FastAPI avec rate limiting et gestion d'état multi-ville
#
# Lancer : uvicorn api.main:app --reload  (depuis SafeRoute/)
# Docs   : http://localhost:8000/docs

import logging
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ajoute bindings/python au path si saferoute n'est pas installé
_bindings = Path(__file__).resolve().parents[1] / "bindings" / "python"
if str(_bindings) not in sys.path:
    sys.path.insert(0, str(_bindings))

from .routes import router, set_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Rate Limiter simple (in-memory, par IP) ───────────────────────────────────
# Pour la production, utiliser slowapi ou redis-based limiter.
# Ici : max 60 requêtes/minute par IP.

_rate_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 60       # requêtes max
RATE_WINDOW = 60.0    # par fenêtre de N secondes


async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - RATE_WINDOW

    # Nettoie les timestamps hors fenêtre
    _rate_store[client_ip] = [t for t in _rate_store[client_ip] if t > window_start]

    if len(_rate_store[client_ip]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit dépassé : {RATE_LIMIT} req/{RATE_WINDOW:.0f}s par IP"},
        )

    _rate_store[client_ip].append(now)
    return await call_next(request)


# ── Lifespan : initialisation du moteur ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from saferoute import SafeRouteEngine
    engine = SafeRouteEngine(eps=0.1)
    set_engine(engine)
    logger.info("SafeRoute engine initialisé (aucune ville chargée — appelez POST /api/v1/load-city)")
    yield
    logger.info("SafeRoute engine arrêté")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="SafeRoute API",
    description="""
## SafeRoute — Routage sûr multi-objectif

Calcule 3 itinéraires Pareto-optimaux entre deux points :
- **shortest** : le plus court
- **safest** : le plus sûr (évite les zones à forte criminalité)
- **balanced** : compromis confort (distance + sécurité + familiarité)

### Workflow typique
1. `POST /load-city` — charge Londres ou Le Cap
2. `POST /nearest-node` — convertit des coordonnées GPS en NodeId OSM
3. `POST /route` — calcule les 3 itinéraires
4. `GET /risk-map` — récupère la heatmap de risque (GeoJSON)
5. `POST /familiarity/record` — enregistre un trajet effectué
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — autorise React (localhost:3000) et Flutter en développement
# En production, remplacer par les domaines réels
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # React dev
        "http://localhost:8080",   # Vue/Angular dev
        "http://localhost:4200",   # Angular dev
        # Ajouter les domaines de production ici
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.middleware("http")(rate_limit_middleware)
app.include_router(router, prefix="/api/v1")

# Fait par Gillesto
# Dockerfile — Image de production SafeRoute API
#
# Build multi-stage :
#   Stage 1 (builder) : compile le core Rust avec maturin
#   Stage 2 (runtime) : image légère Python avec le wheel compilé
#
# Build  : docker build -t saferoute:latest .
# Run    : docker run -p 8000:8000 -v $(pwd)/data:/app/data saferoute:latest

# ── Stage 1 : compilation Rust ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Dépendances système pour Rust et compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Installe Rust via rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build

# Copie les sources
COPY core/ ./core/
COPY bindings/python/ ./bindings/python/

# Installe maturin et compile le wheel Rust
RUN pip install maturin
RUN cd bindings/python && \
    maturin build --release --out /wheels \
    --manifest-path ../../core/Cargo.toml

# ── Stage 2 : image de production ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Dépendances système minimales (GDAL pour geopandas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copie le wheel compilé depuis le builder
COPY --from=builder /wheels/*.whl /tmp/wheels/

# Installe les dépendances Python
COPY bindings/python/pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir \
    osmnx networkx geopandas shapely scipy numpy \
    fastapi "uvicorn[standard]" pydantic httpx \
    matplotlib folium \
    /tmp/wheels/*.whl

# Copie le code de l'application
COPY api/ ./api/
COPY bindings/python/saferoute/ ./saferoute/
COPY scripts/ ./scripts/

# Répertoire de cache persistant (monter un volume ici)
RUN mkdir -p /app/data/cache

# Variables d'environnement
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Port exposé
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

# Commande de démarrage
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

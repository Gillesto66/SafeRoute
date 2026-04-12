# Fait par Gillesto
# test_api.py — Tests d'intégration FastAPI (pytest + httpx)

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from api.main import app
import api.routes as routes_module
from saferoute.models import ParetoSet, Route


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine._current_city = "london"
    engine._nx_graph = MagicMock()  # non-None = ville chargée
    pareto = ParetoSet(
        shortest=Route([1, 2], 100.0, 0.9, "shortest"),
        safest=Route([1, 3], 800.0, 0.1, "safest"),
        balanced=Route([1, 2, 3], 400.0, 0.4, "balanced"),
    )
    engine.compute_routes.return_value = pareto
    return engine


@pytest.fixture
def client(mock_engine):
    routes_module._engine = mock_engine
    with TestClient(app, raise_server_exceptions=False) as c:
        routes_module._engine = mock_engine
        yield c
    routes_module._engine = None


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_compute_route(client):
    payload = {
        "city": "london",
        "source_node": 1,
        "target_node": 3,
        "eps": 0.1,
    }
    resp = client.post("/api/v1/route", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["shortest"]["route_type"] == "shortest"
    assert data["safest"]["total_risk"] < data["shortest"]["total_risk"]
    assert "distance_km" in data["shortest"]


def test_route_engine_error(client, mock_engine):
    mock_engine.compute_routes.side_effect = RuntimeError("Nœud introuvable")
    resp = client.post("/api/v1/route", json={
        "city": "london", "source_node": 1, "target_node": 999, "eps": 0.1
    })
    assert resp.status_code == 500

# Guide rapide

> Fait par Gillesto

## Calcul d'itinéraires

```python
from saferoute import SafeRouteEngine

engine = SafeRouteEngine(eps=0.1)
engine.load_city("london")

source = engine.nearest_node(lat=51.5074, lon=-0.1278)
target = engine.nearest_node(lat=51.5155, lon=-0.0922)

pareto = engine.compute_routes(source, target)

# Route la plus courte
print(f"Courte  : {pareto.shortest.total_distance_m:.0f}m, risque={pareto.shortest.total_risk:.3f}")
# Route la plus sûre
print(f"Sûre    : {pareto.safest.total_distance_m:.0f}m, risque={pareto.safest.total_risk:.3f}")
# Compromis
print(f"Équilibrée : {pareto.balanced.total_distance_m:.0f}m, risque={pareto.balanced.total_risk:.3f}")
```

## Enregistrer un trajet (familiarité)

```python
# Après avoir effectué un trajet, l'enregistrer pour réduire le coût de ces rues
engine.record_trip(pareto.shortest.path)
```

## Lancer l'API REST

```bash
uvicorn saferoute.api.main:app --reload
# → http://localhost:8000/docs
```

## Gestion des erreurs

```python
from saferoute.exceptions import SafeRouteError, GraphNotLoadedError

try:
    pareto = engine.compute_routes(source, target)
except GraphNotLoadedError:
    engine.load_city("london")
    pareto = engine.compute_routes(source, target)
except SafeRouteError as e:
    print(f"Erreur SafeRoute : {e}")
```

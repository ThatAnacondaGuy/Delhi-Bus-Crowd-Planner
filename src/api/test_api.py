"""
Sprint 4: Integration Tests for FastAPI Backend Service
Transport Stack Hackathon 2026 — Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)
"""

import pytest
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture(scope="module")
def client():
    """Initializes TestClient within the FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c

def test_get_frontend_html(client):
    """Test 1: Root endpoint GET / serves the interactive frontend HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Delhi Crowd-Aware Bus Journey Planner" in response.text
    assert "leaflet" in response.text.lower()
    assert "chart.js" in response.text.lower()

def test_api_health(client):
    """Test 2: GET /api/health returns router readiness and dataset indexing stats."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["ready"] is True
    assert data["stops_indexed"] == 6862
    assert data["routes_loaded"] == 2574
    assert data["transfer_edges"] > 20000

def test_stops_search_default_hubs(client):
    """Test 3: GET /api/stops/search with empty query returns 10 curated transit hubs."""
    response = client.get("/api/stops/search")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 10
    stops = data["stops"]
    names = [s["stop_name"] for s in stops]
    assert any("Nehru Place" in n for n in names)
    assert any("Dhaula Kuan" in n for n in names)
    assert any("Kashmere Gate" in n for n in names)
    assert any("ITO" in n for n in names)

def test_stops_search_query(client):
    """Test 4: GET /api/stops/search?q=nehru returns matching stops with lat/lon."""
    response = client.get("/api/stops/search?q=nehru&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    assert any("Nehru" in s["stop_name"] for s in data["stops"])
    first = data["stops"][0]
    assert "stop_id" in first
    assert "stop_lat" in first
    assert "stop_lon" in first

def test_plan_journey_peak_balanced(client):
    """Test 5: POST /api/plan evaluates peak hour balanced journey (Nehru Place -> Dhaula Kuan)."""
    payload = {
        "origin_stop_id": "2560",  # Nehru Place Terminal
        "dest_stop_id": "2944",    # Dhaula Kuan (Ring Road)
        "departure_time": "09:00",
        "day_type": "weekday",
        "beta": 0.6
    }
    response = client.post("/api/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "itineraries" in data
    assert len(data["itineraries"]) > 0
    assert "query_latency_ms" in data
    assert data["query_latency_ms"] < 3500  # under 3.5s for test client in constrained environments

    itin = data["itineraries"][0]
    assert "total_duration_min" in itin
    assert "transfers" in itin
    assert "estimated_fare_inr" in itin
    assert "avg_crowding_score" in itin
    assert "legs" in itin
    assert len(itin["legs"]) > 0

    bus_legs = [l for l in itin["legs"] if l["mode"] == "BUS"]
    assert len(bus_legs) > 0
    first_bus = bus_legs[0]
    assert "route_short_name" in first_bus
    assert "segments" in first_bus

def test_plan_journey_offpeak_least_crowded(client):
    """Test 6: POST /api/plan evaluates off-peak least crowded journey with high beta."""
    payload = {
        "origin_stop_id": "257",   # GTB Nagar
        "dest_stop_id": "7563",    # Pitampura
        "departure_time": "14:30",
        "day_type": "weekday",
        "beta": 1.8
    }
    response = client.post("/api/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["itineraries"]) > 0
    itin = data["itineraries"][0]
    assert itin["avg_crowding_score"] <= 0.35  # Low tier off-peak

def test_validation_metrics(client):
    """Test 7: GET /api/validation/metrics returns KPIs and validation distributions."""
    response = client.get("/api/validation/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "kpis" in data
    assert "diurnal_windows" in data
    assert "directional_asymmetry" in data
    assert "tier_distribution" in data
    assert data["kpis"]["total_passengers_modeled"] == "2,574,781"

def test_route_profile(client):
    """Test 8: GET /api/routes/717AUP/profile returns route stop-by-stop crowding sequence."""
    response = client.get("/api/routes/717AUP/profile?day_type=weekday&time_slot=18")
    assert response.status_code == 200
    data = response.json()
    assert data["route_short_name"] == "717AUP"
    assert "total_stops" in data
    assert data["total_stops"] > 10
    assert "segments" in data
    assert len(data["segments"]) == data["total_stops"] - 1
    assert "avg_crowding_score" in data

def test_invalid_stop_plan(client):
    """Test 9: POST /api/plan with non-existent stop ID returns 404 error."""
    payload = {
        "origin_stop_id": "INVALID_STOP_99999",
        "dest_stop_id": "2944",
        "departure_time": "09:00",
        "day_type": "weekday",
        "beta": 0.6
    }
    response = client.post("/api/plan", json=payload)
    assert response.status_code == 404
    assert "Could not resolve stops" in response.json()["detail"]

if __name__ == "__main__":
    pytest.main(["-v", "src/api/test_api.py"])

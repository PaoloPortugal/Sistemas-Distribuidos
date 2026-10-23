from fastapi.testclient import TestClient

from app.main import app


def test_salud():
    respuesta = TestClient(app).get("/salud")
    assert respuesta.status_code == 200

from fastapi.testclient import TestClient

from app.main import app, estado


def test_salud_con_el_consumidor_conectado(monkeypatch):
    monkeypatch.setattr(estado, "consumidor_conectado", True)

    respuesta = TestClient(app).get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["consumidor_conectado"] is True


def test_salud_sin_conexion_a_rabbitmq_responde_503(monkeypatch):
    monkeypatch.setattr(estado, "consumidor_conectado", False)

    respuesta = TestClient(app).get("/salud")

    assert respuesta.status_code == 503
    assert respuesta.json()["estado"] == "sin conexión a RabbitMQ"

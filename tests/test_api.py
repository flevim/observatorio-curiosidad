"""La API sirve lo exportado y valida entradas. Usa los datos de data/processed/web si existen."""

import pytest
from fastapi.testclient import TestClient

from observatorio.settings import PATHS
from observatorio_api.main import app, slugify

client = TestClient(app)
needs_data = pytest.mark.skipif(not (PATHS.web / "meta.json").exists(), reason="ejecuta export primero")


def test_slugify():
    assert slugify("Fusión Nuclear!") == "fusion-nuclear"


def test_rejects_bad_ids():
    assert client.get("/api/topics/..%2F..%2Fsecret").status_code in (400, 404)
    assert client.get("/api/countries/2025-13x/CL").status_code == 400
    assert client.get("/api/globe/NO_VALIDO").status_code == 400


@needs_data
def test_meta_and_search():
    meta = client.get("/api/meta").json()
    assert meta["temas"]
    r = client.get("/api/search", params={"q": "fusion"}).json()
    assert r and r[0]["id"] == "fusion-nuclear"


@needs_data
def test_country_without_data_is_flagged():
    meta = client.get("/api/meta").json()
    if not meta["periodos"]:
        pytest.skip("aún no hay rankings por país exportados")
    period = meta["periodos"][0]["id"]
    r = client.get(f"/api/countries/{period}/AQ").json()  # Antártida: nunca hay ranking
    assert r["sin_datos"] is True


def test_add_topic_rate_limit_per_ip(monkeypatch):
    import observatorio_api.main as m
    from fastapi import HTTPException

    class Req:
        headers = {"cf-connecting-ip": "203.0.113.7"}
        client = None

    monkeypatch.setattr(m, "_added", [])
    monkeypatch.setattr(m, "LIMITE_POR_HORA", 2)
    m._check_limits(Req())
    m._check_limits(Req())
    with pytest.raises(HTTPException) as e:
        m._check_limits(Req())
    assert e.value.status_code == 429

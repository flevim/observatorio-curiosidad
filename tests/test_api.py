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


def test_disputes_endpoint_serves_export_or_404():
    r = client.get("/api/disputa")
    if not (PATHS.web / "disputa.json").exists():
        assert r.status_code == 404
        return
    d = r.json()
    assert {"semana", "reglas", "articulos"} <= d.keys()
    for a in d["articulos"]:
        assert a["enlace"].startswith(f"https://{a['idioma']}.wikipedia.org/wiki/")


def test_job_status_reports_time_and_queue(monkeypatch, tmp_path):
    import time as _t

    import observatorio_api.main as m

    monkeypatch.setattr(m, "_HISTORIAL", tmp_path / "jobs_duracion.json")
    monkeypatch.setattr(m, "JOBS", {})
    assert m._estimate() == m.DURACION_POR_DEFECTO  # sin casos reales
    (tmp_path / "jobs_duracion.json").write_text("[100, 200, 160]", encoding="utf-8")
    assert m._estimate() == 160  # mediana de los últimos

    now = _t.time()
    m.JOBS["a"] = {"id": "a", "tema": "a", "nombre": "A", "estado": "descargando", "log": [], "avisos": [], "error": None,
                   "creado": now - 30, "fin": None, "etapas": {"descargando": 0}}
    m.JOBS["b"] = {"id": "b", "tema": "b", "nombre": "B", "estado": "en cola", "log": [], "avisos": [], "error": None,
                   "creado": now - 5, "fin": None, "etapas": {}}
    r = client.get("/api/jobs/b").json()
    assert r["delante"] == 1 and r["estimado"] == 320 and 4 <= r["transcurrido"] <= 6 and "creado" not in r
    assert client.get("/api/jobs/a").json()["delante"] == 0
    assert client.get("/api/jobs/no-existe").status_code == 404

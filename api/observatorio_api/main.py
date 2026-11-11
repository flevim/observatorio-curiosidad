"""API del Observatorio de la Curiosidad.

Sirve los agregados ya procesados de data/processed/web. Nunca llama a Wikimedia por pedido del
navegador; la única excepción es agregar un tema nuevo, que lanza el pipeline en segundo plano
(con la misma caché, pausas y reintentos que la línea de comandos).

Ejecutar:  uvicorn observatorio_api.main:app --app-dir api --port 8010
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from observatorio.settings import PATHS, SLUG_RE, TopicConfig, append_topic, contact, load_topics

app = FastAPI(title="Observatorio de la Curiosidad", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)

PERIOD_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
ISO_RE = re.compile(r"^[A-Z]{2}$")


def web_dir() -> Path:
    return PATHS.web


@lru_cache(maxsize=256)
def _read_cached(path: str, mtime: float) -> bytes:
    return Path(path).read_bytes()


def _stat(rel: str):
    p = web_dir() / rel
    if not p.exists():
        raise HTTPException(404, f"No existe {rel}. ¿Ejecutaste `python -m observatorio export`?")
    return p, p.stat()


def read_bytes(rel: str) -> bytes:
    p, st = _stat(rel)
    return _read_cached(str(p), st.st_mtime)


def json_file(rel: str, request: Request | None = None, media_type: str = "application/json") -> Response:
    """Respuesta con ETag: el navegador revalida (304) y nunca muestra datos viejos tras un `export`."""
    p, st = _stat(rel)
    etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    headers = {"Cache-Control": "no-cache", "ETag": etag}
    if request is not None and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(_read_cached(str(p), st.st_mtime), media_type=media_type, headers=headers)


def load(rel: str):
    return json.loads(read_bytes(rel))


def check_topic(tid: str) -> str:
    if not SLUG_RE.match(tid):
        raise HTTPException(400, "id de tema inválido")
    return tid


@app.get("/api/meta")
def meta(request: Request):
    return json_file("meta.json", request)


@app.get("/api/topics")
def topics():
    return load("meta.json")["temas"]


@app.get("/api/topics/{tid}")
def topic(tid: str, request: Request):
    return json_file(f"topics/{check_topic(tid)}.json", request)


@app.get("/api/topics/{tid}/daily")
def topic_daily(tid: str, request: Request):
    return json_file(f"topics/{check_topic(tid)}.daily.json", request)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


@app.get("/api/search")
def search(q: str = Query("", max_length=80), limit: int = Query(8, ge=1, le=30)):
    """Autocompletado sin tildes ni mayúsculas sobre nombres, descripciones y títulos por idioma."""
    fq = _fold(q.strip())
    if not fq:
        return []
    out = []
    for t in load("meta.json")["temas"]:
        name = _fold(t["nombre"])
        hay = name + " " + _fold(t.get("descripcion") or "")
        if fq in hay:
            score = 0 if name.startswith(fq) else 1 if fq in name else 2
            out.append((score, t["nombre"], t))
    return [t for _, _, t in sorted(out, key=lambda x: (x[0], x[1]))[:limit]]


@app.get("/api/graph")
def graph(request: Request):
    return json_file("graph.json", request)


@app.get("/api/globe/{key}")
def globe(key: str, request: Request):
    """key = 'periodo' (volumen de lectura) o un id de tema (presencia en rankings)."""
    if key != "periodo":
        check_topic(key)
    return json_file(f"globe/{key}.json", request)


@app.get("/api/countries/{period}")
def countries_period(period: str, request: Request):
    if not PERIOD_RE.match(period):
        raise HTTPException(400, "periodo inválido (AAAA-MM o AAAA-MM-DD)")
    return json_file(f"countries/{period}.json", request)


@app.get("/api/countries/{period}/{iso}")
def country(period: str, iso: str):
    if not PERIOD_RE.match(period) or not ISO_RE.match(iso):
        raise HTTPException(400, "parámetros inválidos")
    data = load(f"countries/{period}.json")
    if iso not in data:
        # Sin datos: no hay ranking publicado o el país no se descargó. No significa cero interés.
        return JSONResponse({"pais": iso, "periodo": period, "sin_datos": True})
    return {"pais": iso, "periodo": period, "sin_datos": False, **data[iso]}


@app.get("/api/perfil/{iso}")
def country_profile(iso: str, request: Request):
    """Curiosidades de un país en todo el periodo observado. Sin perfil = sin datos (no es «cero interés»)."""
    if not ISO_RE.match(iso):
        raise HTTPException(400, "código de país inválido")
    if not (web_dir() / "countries" / "perfil" / f"{iso}.json").exists():
        return JSONResponse({"pais": iso, "sin_datos": True})
    return json_file(f"countries/perfil/{iso}.json", request)


@app.get("/api/curiosidades")
def daily_index(request: Request):
    """Días con curiosidades (el más reciente primero)."""
    if not (web_dir() / "daily" / "index.json").exists():
        return {"dias": []}
    return json_file("daily/index.json", request)


@app.get("/api/curiosidades/{day}")
def daily_day(day: str, request: Request):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise HTTPException(400, "fecha inválida (AAAA-MM-DD)")
    return json_file(f"daily/{day}.json", request)


@app.get("/api/geo/{lod}")
def geo(lod: str, request: Request):
    name = {"110m": "countries.geojson", "50m": "countries-50m.geojson"}.get(lod)
    if not name:
        raise HTTPException(404)
    return json_file(name, request, media_type="application/geo+json")


@app.get("/api/findings")
def findings(request: Request):
    return json_file("findings.json", request)


@app.get("/api/clusters")
def clusters(request: Request):
    return json_file("clusters.json", request)


@app.get("/reporte")
def report():
    p = PATHS.reports / "observatorio.html"
    if not p.exists():
        raise HTTPException(404, "Genera el reporte con `python -m observatorio report`")
    return FileResponse(p, media_type="text/html")


# ---------------------------------------------------------------- agregar temas

JOBS: dict[str, dict] = {}
_job_lock = threading.Lock()


class NewTopic(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    titulo: str | None = Field(None, max_length=200, description="título del artículo en Wikipedia")
    idioma: str = Field("es", pattern=r"^[a-z]{2,3}(-[a-z]+)?$")
    wikidata: str | None = Field(None, pattern=r"^Q\d+$")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-")
    return s[:60] or "tema"


def _run_job(job_id: str, tid: str) -> None:
    from observatorio.analysis.run import analyze
    from observatorio.export import export
    from observatorio.pipeline import fetch
    from observatorio.report.build import build_report

    job = JOBS[job_id]

    def log(msg: str) -> None:
        job["log"].append(msg)

    try:
        with _job_lock:  # un pipeline a la vez
            job["estado"] = "descargando"
            report = fetch([tid], countries=False, progress=log)
            job["avisos"] = report.warnings
            job["estado"] = "analizando"
            analyze(progress=log)
            build_report()
            job["estado"] = "exportando"
            export(progress=log)
        _read_cached.cache_clear()
        job["estado"] = "listo"
    except BaseException as exc:  # noqa: BLE001 - se informa al usuario
        job["estado"] = "error"
        job["error"] = str(exc)


@app.post("/api/topics", status_code=202)
def add_topic(body: NewTopic):
    if not contact():
        raise HTTPException(503, "Falta OBSERVATORIO_CONTACT en .env: Wikimedia exige un contacto en el User-Agent para descargar datos.")
    if not body.titulo and not body.wikidata:
        raise HTTPException(422, "Indica el título del artículo en Wikipedia o un id de Wikidata (Q…)")
    cfg = load_topics()
    tid = slugify(body.nombre)
    if cfg.get(tid):
        raise HTTPException(409, f"Ya existe el tema '{tid}'")
    append_topic(TopicConfig(id=tid, nombre=body.nombre.strip(), seed_lang=body.idioma if body.titulo else None,
                             seed_title=body.titulo, wikidata=body.wikidata))
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"id": job_id, "tema": tid, "estado": "en cola", "log": [], "avisos": [], "error": None}
    threading.Thread(target=_run_job, args=(job_id, tid), daemon=True).start()
    return {"job": job_id, "tema": tid}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404)
    return JOBS[job_id]


@app.get("/api/health")
def health():
    return {"ok": True, "datos": (web_dir() / "meta.json").exists(), "contacto_configurado": bool(contact())}


# Web compilada (npm run build) servida desde la misma API en producción local.
_dist = PATHS.root / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")

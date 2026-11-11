"""Cliente HTTP con caché SQLite, pausas entre llamadas y reintentos con backoff exponencial.

Política de Wikimedia (https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/):
- User-Agent descriptivo con contacto.
- Peticiones en serie: esperar a que termine una antes de enviar la siguiente.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .settings import PATHS, min_interval, require_contact, user_agent

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class CachedResponse:
    status: int
    data: Any
    from_cache: bool


class HttpCache:
    """Guarda respuestas JSON por URL. Las respuestas 404 también se guardan (que no exista es un dato)."""

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS responses ("
                " url TEXT PRIMARY KEY, status INTEGER NOT NULL, body TEXT,"
                " fetched_at REAL NOT NULL, expires_at REAL)"
            )
            self._conn.commit()

    def get(self, url: str) -> tuple[int, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT status, body, expires_at FROM responses WHERE url = ?", (url,)
            ).fetchone()
        if row is None:
            return None
        status, body, expires_at = row
        if expires_at is not None and expires_at < time.time():
            return None
        return status, (json.loads(body) if body else None)

    def put(self, url: str, status: int, data: Any, ttl: float | None) -> None:
        now = time.time()
        expires = None if ttl is None else now + ttl
        body = json.dumps(data, ensure_ascii=False) if data is not None else None
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (url, status, body, fetched_at, expires_at) VALUES (?,?,?,?,?)",
                (url, status, body, now, expires),
            )
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class PoliteClient:
    """Cliente serializado: una petición a la vez, con pausa mínima y reintentos."""

    def __init__(
        self,
        cache: HttpCache | None = None,
        *,
        interval: float | None = None,
        max_retries: int = 6,
        backoff_base: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        require_contact: bool = True,
    ):
        self.require_contact = require_contact and transport is None
        self.cache = cache if cache is not None else HttpCache(PATHS.cache_db)
        self.interval = min_interval() if interval is None else interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._last = 0.0
        self._lock = threading.Lock()
        self.network_calls = 0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent(), "Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            transport=transport,
        )

    def get_json(self, url: str, params: dict | None = None, *, ttl: float | None = None,
                 not_found_ttl: float | None | str = "default") -> CachedResponse:
        """GET con caché. `ttl=None` guarda para siempre (datos de periodos ya cerrados).
        `not_found_ttl`: duración de la caché de un 400/404 (por defecto 7 días; None = para siempre)."""
        key = str(httpx.URL(url, params=params)) if params else url
        cached = self.cache.get(key)
        if cached is not None:
            return CachedResponse(cached[0], cached[1], True)
        if self.require_contact:
            require_contact()
        with self._lock:  # serializa: nunca dos peticiones simultáneas
            status, data = self._fetch(key)
        if status == 200:
            self.cache.put(key, status, data, ttl)
        elif status in (400, 404):
            # "Sin datos" puede cambiar si el periodo aún no se publica: por defecto, caché de una semana.
            nf = (7 * 86400 if ttl is None else ttl) if not_found_ttl == "default" else not_found_ttl
            self.cache.put(key, status, data, nf)
        return CachedResponse(status, data, False)

    def _fetch(self, url: str) -> tuple[int, Any]:
        attempt = 0
        while True:
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self._client.get(url)
                self.network_calls += 1
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise
                delay = self.backoff_base * (2**attempt)
                log.warning("error de red %s; reintento en %.1fs", exc, delay)
                self._sleep(delay)
                attempt += 1
                continue
            if resp.status_code == 200:
                return 200, resp.json()
            if resp.status_code in (400, 404):
                # 404: artículo o fecha sin datos. 400: parámetros inválidos. No se reintentan.
                try:
                    return resp.status_code, resp.json()
                except ValueError:
                    return resp.status_code, None
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                delay = self.backoff_base * (2**attempt)
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, float(retry_after))
                log.warning("HTTP %s en %s; reintento en %.1fs", resp.status_code, url, delay)
                self._sleep(delay)
                attempt += 1
                continue
            if resp.status_code == 403:
                raise PermissionError(
                    f"Wikimedia rechazó la petición (403) a {url}. Revisa que OBSERVATORIO_CONTACT en .env "
                    "tenga un contacto real; su política de User-Agent lo exige."
                )
            resp.raise_for_status()
            return resp.status_code, None

    def close(self) -> None:
        self._client.close()

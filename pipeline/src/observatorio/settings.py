"""Rutas del proyecto y configuración leída de config/*.yaml y .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _find_root() -> Path:
    env = os.environ.get("OBSERVATORIO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *here.parents]:
        if (parent / "config" / "topics.yaml").exists():
            return parent
    return Path.cwd()


ROOT = _find_root()


def _load_dotenv(path: Path) -> None:
    """Lector mínimo de .env (CLAVE=valor). No sobrescribe variables ya definidas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass
class Paths:
    root: Path = ROOT

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def cache_db(self) -> Path:
        return self.root / "data" / "cache" / "http_cache.sqlite"

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def analysis(self) -> Path:
        return self.processed / "analysis"

    @property
    def web(self) -> Path:
        return self.processed / "web"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def geo_cache(self) -> Path:
        return self.root / "data" / "cache" / "geo"

    def ensure(self) -> None:
        for p in [self.cache_db.parent, self.processed, self.analysis, self.web, self.reports, self.geo_cache]:
            p.mkdir(parents=True, exist_ok=True)


PATHS = Paths()

VERSION = "0.1.0"


class MissingContactError(RuntimeError):
    """Wikimedia exige un contacto real en el User-Agent y rechaza (403) las peticiones sin él."""


def contact() -> str | None:
    value = os.environ.get("OBSERVATORIO_CONTACT", "").strip()
    if not value or value.endswith("@ejemplo.org"):
        return None
    return value


def user_agent() -> str:
    """User-Agent según https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy"""
    import httpx

    c = contact() or "contact not configured"
    return f"ObservatorioCuriosidad/{VERSION} ({c}) httpx/{httpx.__version__}"


def require_contact() -> str:
    c = contact()
    if not c:
        raise MissingContactError(
            "Falta OBSERVATORIO_CONTACT en .env. La política de Wikimedia exige un contacto real "
            "(correo, URL o página de usuario de Wikimedia) en el User-Agent, y sin él responde 403. "
            "Copia .env.example a .env y completa ese valor. Las respuestas ya guardadas en la caché "
            "se siguen usando sin conexión."
        )
    return c


def min_interval() -> float:
    try:
        return max(0.05, float(os.environ.get("OBSERVATORIO_MIN_INTERVAL", "0.1")))
    except ValueError:
        return 0.1


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass
class TopicConfig:
    id: str
    nombre: str
    seed_lang: str | None = None
    seed_title: str | None = None
    wikidata: str | None = None
    openalex: str | None = None

    def to_yaml(self) -> dict:
        d: dict = {"id": self.id, "nombre": self.nombre}
        if self.seed_title:
            d["semilla"] = {"idioma": self.seed_lang, "titulo": self.seed_title}
        if self.wikidata:
            d["wikidata"] = self.wikidata
        if self.openalex:
            d["openalex"] = self.openalex
        return d


@dataclass
class TopicsConfig:
    languages: list[str]
    topics: list[TopicConfig] = field(default_factory=list)

    def get(self, topic_id: str) -> TopicConfig | None:
        return next((t for t in self.topics if t.id == topic_id), None)


def load_topics(path: Path | None = None) -> TopicsConfig:
    path = path or PATHS.config / "topics.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    langs = [str(x) for x in raw.get("idiomas", ["es", "en"])]
    topics = []
    seen = set()
    for item in raw.get("temas", []) or []:
        tid = str(item["id"])
        if not SLUG_RE.match(tid):
            raise ValueError(f"id de tema inválido: {tid!r}")
        if tid in seen:
            raise ValueError(f"id de tema repetido: {tid!r}")
        seen.add(tid)
        seed = item.get("semilla") or {}
        topics.append(
            TopicConfig(
                id=tid,
                nombre=str(item.get("nombre", tid)),
                seed_lang=seed.get("idioma"),
                seed_title=seed.get("titulo"),
                wikidata=item.get("wikidata"),
                openalex=item.get("openalex"),
            )
        )
    return TopicsConfig(languages=langs, topics=topics)


def append_topic(topic: TopicConfig, path: Path | None = None) -> None:
    """Agrega un tema al final de topics.yaml conservando los comentarios existentes."""
    path = path or PATHS.config / "topics.yaml"
    cfg = load_topics(path)
    if not SLUG_RE.match(topic.id):
        raise ValueError(f"id de tema inválido: {topic.id!r}")
    if cfg.get(topic.id):
        raise ValueError(f"el tema {topic.id!r} ya existe")
    line = "  - " + yaml.safe_dump(topic.to_yaml(), default_flow_style=True, allow_unicode=True, width=1000).strip()
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + line + "\n", encoding="utf-8")


@dataclass
class CountriesConfig:
    start: str
    sample_days: list[int]
    recent_full_days: int
    countries: list[str]


def load_countries(path: Path | None = None) -> CountriesConfig:
    path = path or PATHS.config / "countries.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return CountriesConfig(
        start=str(raw.get("inicio", "2021-01-01")),
        sample_days=[int(d) for d in raw.get("dias_muestreados_por_mes", [8, 22])],
        recent_full_days=int(raw.get("dias_recientes_completos", 14)),
        # YAML 1.1 lee NO (Noruega) sin comillas como False.
        countries=["NO" if c is False else str(c).upper() for c in raw.get("paises", [])],
    )

"""Orquestación de las etapas: fetch, analyze, report, export."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import pandas as pd

from .http import PoliteClient
from .demo import clear_demo
from .settings import PATHS, load_countries, load_topics, require_contact
from .sources.base import FetchReport
from .sources.wikipedia import WikipediaSource, save_json

log = logging.getLogger(__name__)

Progress = Callable[[str], None]


def _print(msg: str) -> None:
    print(msg, flush=True)


def load_resolved() -> dict[str, dict]:
    path = PATHS.processed / "topics_resolved.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _merge_parquet(path, new: pd.DataFrame, key_col: str, keys: set) -> pd.DataFrame:
    if path.exists():
        old = pd.read_parquet(path)
        old = old[~old[key_col].isin(keys)]
        new = pd.concat([old, new], ignore_index=True) if not new.empty else old
    new.to_parquet(path, index=False)
    return new


def fetch(
    topic_ids: list[str] | None = None,
    *,
    pageviews: bool = True,
    countries: bool = True,
    incremental: bool = False,
    progress: Progress = _print,
) -> FetchReport:
    PATHS.ensure()
    require_contact()  # falla temprano y con un mensaje claro si falta el contacto del User-Agent
    clear_demo()  # los datos reales nunca se mezclan con los sintéticos
    cfg = load_topics()
    topics = [t for t in cfg.topics if not topic_ids or t.id in topic_ids]
    unknown = set(topic_ids or []) - {t.id for t in cfg.topics}
    if unknown:
        raise SystemExit(f"temas desconocidos en topics.yaml: {', '.join(sorted(unknown))}")
    client = PoliteClient()
    src = WikipediaSource(client, cfg.languages)
    report = FetchReport("wikipedia")
    t0 = time.time()

    if pageviews:
        progress(f"Resolviendo {len(topics)} temas en Wikidata y {len(cfg.languages)} idiomas…")
        resolved_all = load_resolved()
        # Conserva solo temas que siguen en la configuración.
        resolved_all = {k: v for k, v in resolved_all.items() if cfg.get(k)}
        resolved = src.resolve(topics, report)
        resolved_all.update(resolved)
        save_json(resolved_all, PATHS.processed / "topics_resolved.json")

        progress("Descargando visitas por artículo (diarias y mensuales)…")
        pv_path = PATHS.processed / "pageviews.parquet"
        if incremental and pv_path.exists():
            old = pd.read_parquet(pv_path)
            daily_old = old[old["granularity"] == "daily"]
            since = {k: v.date() for k, v in daily_old.groupby(["topic_id", "series"])["date"].max().items()}
            pv = src.fetch_pageviews(resolved, report, progress, since=since)
            merged = pd.concat([old, pv], ignore_index=True).drop_duplicates(
                ["topic_id", "source", "series", "granularity", "date"], keep="last")
            merged.sort_values(["topic_id", "series", "granularity", "date"]).to_parquet(pv_path, index=False)
        else:
            pv = src.fetch_pageviews(resolved, report, progress)
            _merge_parquet(pv_path, pv, "topic_id", {t.id for t in topics})

        progress("Descargando totales por edición de idioma…")
        totals = src.fetch_project_totals(report)
        totals.to_parquet(PATHS.processed / "project_totals.parquet", index=False)

        progress("Descargando lo más leído en cada edición (últimos 7 días)…")
        trending = src.fetch_trending(report)
        if trending:
            save_json(trending, PATHS.processed / "trending.json")

        progress("Descargando relaciones (enlaces, categorías, Wikidata)…")
        relations = src.fetch_relations(resolved_all, report)
        save_json(relations, PATHS.processed / "relations.json")

    if countries:
        ccfg = load_countries()
        progress(f"Descargando rankings por país ({len(ccfg.countries)} países)…")
        tops = src.fetch_country_tops(ccfg, report, progress)
        tops.to_parquet(PATHS.processed / "country_top.parquet", index=False)

    elapsed = time.time() - t0
    out = {
        "fecha": pd.Timestamp.now(tz="UTC").isoformat(),
        "segundos": round(elapsed, 1),
        "llamadas_red": client.network_calls,
        "respuestas_en_cache": client.cache.count(),
        "avisos": report.warnings,
    }
    prev_path = PATHS.processed / "fetch_report.json"
    save_json(out, prev_path)
    progress(f"Listo en {elapsed:.0f}s: {client.network_calls} llamadas de red, {len(report.warnings)} avisos.")
    for w in report.warnings:
        progress(f"  aviso: {w}")
    client.close()
    return report


def fetch_disputes_to_disk(progress: Progress = _print) -> None:
    """«Bajo disputa»: artículos con más ediciones revertidas de lo habitual (ver analysis/disputes.py)."""
    from .sources.disputes import fetch_disputes

    PATHS.ensure()
    require_contact()
    client = PoliteClient()
    try:
        save_json(fetch_disputes(client, progress), PATHS.processed / "disputa.json")
    except Exception as e:  # un fallo aquí no debe frenar la actualización diaria
        progress(f"  aviso: bajo disputa no se pudo actualizar: {e}")
    finally:
        client.close()


def daily(progress: Progress = _print) -> None:
    """Actualización diaria (pensada para el programador de tareas):
    1. descarga solo los días nuevos de visitas y rankings (todo lo demás sale de la caché);
    2. recalcula el análisis, el reporte y la exportación, que incluye las curiosidades de cada día reciente.
    """
    from .analysis.run import analyze
    from .export import export
    from .report.build import build_report

    t0 = time.time()
    fetch(incremental=True, progress=progress)
    fetch_disputes_to_disk(progress=progress)
    analyze(progress=progress)
    build_report()
    export(progress=progress)
    idx = PATHS.web / "daily" / "index.json"
    last = json.loads(idx.read_text(encoding="utf-8"))["dias"][:1] if idx.exists() else []
    progress(f"Actualización diaria lista en {time.time() - t0:.0f}s. Último día con curiosidades: "
             f"{last[0]['fecha'] + ' (' + str(last[0]['n']) + ')' if last else 'ninguno'}.")

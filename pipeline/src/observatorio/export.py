"""Etapa `export`: precalcula los agregados JSON que sirve la API y consume la web.

Estructura de data/processed/web/:
  meta.json                 temas, periodos disponibles, fuentes, limitaciones
  topics/{id}.json          análisis completo + serie mensual por idioma
  topics/{id}.daily.json    serie diaria por idioma (se carga al abrir el tema)
  graph.json                relaciones semánticas y estadísticas + sugerencias
  globe/periodo.json        volumen aproximado de lectura por país y periodo
  globe/{id}.json           presencia del tema en el ranking de cada país y periodo
  countries/{periodo}.json  artículos más vistos por país en el periodo
  countries.geojson         geometría de países (Natural Earth, dominio público)
  findings.json, clusters.json, report_url
"""

from __future__ import annotations

import json
import shutil
from urllib.parse import quote
from pathlib import Path

import httpx
import pandas as pd

from .analysis import countries as C
from .analysis import curiosities as Q
from .analysis import weekly as W
from .analysis import timeseries as T
from .analysis.run import ALL, build_series
from .demo import is_demo
from .settings import PATHS, load_countries, load_topics
from .sources.wikipedia import WikipediaSource, iter_topic_titles, save_json

NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson"
)
NATURAL_EARTH_50M_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_50m_admin_0_countries.geojson"
)

LIMITACIONES = [
    "Las visitas a Wikipedia no representan a toda la población: reflejan a quienes usan Wikipedia, con acceso a internet y en esos idiomas.",
    "Las visitas por artículo NO tienen desglose por país. Se agrupan por edición de idioma, y un idioma no equivale a un país (el español se lee en más de 20 países; el inglés en todo el mundo).",
    "Los rankings por país vienen redondeados hacia arriba por Wikimedia por privacidad y omiten artículos con pocas visitas: son aproximados.",
    "Los rankings por país solo existen desde 2021 y por día. El mes se construye con días muestreados; un tema que estuvo de moda otros días puede no aparecer.",
    "El tráfico pasó en gran parte del escritorio al móvil y, en los últimos años, parte de las consultas se resuelven en buscadores o asistentes sin visitar Wikipedia.",
    "Se excluyen bots declarados y detectados (agent=user), pero algunos picos pueden deberse a tráfico automatizado no filtrado.",
    "Las visitas que llegan por un título de redirección se cuentan en esa redirección, no en el artículo, y no se suman aquí.",
    "Una correlación entre temas o idiomas no implica que uno cause al otro.",
]


def _round_coords(obj, nd=2):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], nd), round(obj[1], nd)]
        return [_round_coords(o, nd) for o in obj]
    return obj


def ensure_geojson(out_dir: Path) -> None:
    """Descarga Natural Earth (dominio público) una vez y deja solo las propiedades necesarias."""
    for url, name, nd in ((NATURAL_EARTH_URL, "countries.geojson", 2), (NATURAL_EARTH_50M_URL, "countries-50m.geojson", 3)):
        target = out_dir / name
        if target.exists():
            continue
        raw = PATHS.geo_cache / url.rsplit("/", 1)[-1]
        if not raw.exists():
            raw.parent.mkdir(parents=True, exist_ok=True)
            r = httpx.get(url, timeout=120, follow_redirects=True)
            r.raise_for_status()
            raw.write_bytes(r.content)
        data = json.loads(raw.read_text(encoding="utf-8"))
        feats = []
        for f in data["features"]:
            p = f["properties"]
            iso = p.get("ISO_A2_EH") or p.get("ISO_A2")
            if not iso or iso == "-99":
                iso = None
            feats.append(
                {
                    "type": "Feature",
                    "properties": {
                        "iso": iso,
                        "nombre": p.get("NAME_ES") or p.get("NAME"),
                        "name": p.get("NAME"),
                        "continente": p.get("CONTINENT"),
                    },
                    "geometry": {"type": f["geometry"]["type"], "coordinates": _round_coords(f["geometry"]["coordinates"], nd)},
                }
            )
        target.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _compact(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def _series_payload(d: dict[str, pd.Series], freq: str) -> dict:
    df = pd.DataFrame(d).asfreq(freq)
    fmt = "%Y-%m-%d" if freq == "D" else "%Y-%m"
    return {
        "inicio": df.index[0].strftime(fmt),
        "fechas": None if freq == "D" else [i.strftime(fmt) for i in df.index],
        "series": {c: [None if pd.isna(v) else int(v) for v in df[c].values] for c in df.columns},
    }


def recent_peaks(daily: dict, topics: dict, days: int = 240) -> dict[str, list[dict]]:
    """Picos de los últimos meses en cada idioma (para las curiosidades del día)."""
    out: dict[str, list[dict]] = {}
    for tid, d in daily.items():
        for lang, s in d.items():
            if lang == ALL or lang not in topics[tid].get("titulos", {}):
                continue
            for pk in T.detect_peaks(s.iloc[-days:]):
                out.setdefault(tid, []).append({"fecha": pk.fecha, "visitas": pk.visitas, "magnitud": pk.magnitud,
                                                "idioma": lang, "titulo": topics[tid]["titulos"][lang]})
    return out


def build_periods(tops: pd.DataFrame, recent_days: int) -> tuple[list[dict], pd.DataFrame]:
    """Periodos navegables: meses (días muestreados) y días recientes completos."""
    df = tops.copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    periods = []
    for m, g in df.groupby("month"):
        periods.append({"id": m.strftime("%Y-%m"), "tipo": "mes", "dias_muestreados": sorted(g["date"].dt.strftime("%Y-%m-%d").unique().tolist())})
    last_days = sorted(df["date"].unique())[-recent_days:] if recent_days else []
    for d in last_days:
        periods.append({"id": pd.Timestamp(d).strftime("%Y-%m-%d"), "tipo": "dia", "dias_muestreados": [pd.Timestamp(d).strftime("%Y-%m-%d")]})
    return periods, df


def export(progress=print) -> None:
    PATHS.ensure()
    out = PATHS.web
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cfg = load_topics()
    an = PATHS.analysis
    topics = json.loads((an / "topics.json").read_text(encoding="utf-8"))
    rel = json.loads((an / "relations.json").read_text(encoding="utf-8"))
    clusters = json.loads((an / "clusters.json").read_text(encoding="utf-8"))
    findings = json.loads((an / "findings.json").read_text(encoding="utf-8"))
    context = json.loads((an / "context.json").read_text(encoding="utf-8"))
    resolved = json.loads((PATHS.processed / "topics_resolved.json").read_text(encoding="utf-8"))
    pv = pd.read_parquet(PATHS.processed / "pageviews.parquet")
    pv = pv[pv["topic_id"].isin(topics)]
    daily, monthly = build_series(pv)

    progress("Exportando temas…")
    for tid, t in topics.items():
        payload = {**t, "mensual": _series_payload(monthly[tid], "MS")}
        _compact(payload, out / "topics" / f"{tid}.json")
        _compact(_series_payload(daily[tid], "D"), out / "topics" / f"{tid}.daily.json")

    progress("Exportando grafo de relaciones…")
    nodes = [{"id": tid, "nombre": t["nombre"], "grupo": t.get("grupo"), "visitas_12m": t["por_idioma"].get(ALL, {}).get("visitas_12m")} for tid, t in topics.items()]
    _compact({"nodos": nodes, "semanticas": rel["semanticas"], "estadisticas": rel["estadisticas"], "candidatos": rel["candidatos"]}, out / "graph.json")

    # ---- países
    periods: list[dict] = []
    tops_path = PATHS.processed / "country_top.parquet"
    countries_with_data: list[str] = []
    if tops_path.exists():
        progress("Exportando agregados por país y periodo…")
        tops = pd.read_parquet(tops_path)
        ccfg = load_countries()
        periods, df = build_periods(tops, ccfg.recent_full_days)
        countries_with_data = sorted(df["country"].unique().tolist())
        # Agregados por mes (días muestreados) y por cada día reciente, con la misma función.
        cma_month = C.country_month_articles(tops)
        frames = [cma_month.assign(period=cma_month["month"].dt.strftime("%Y-%m"))]
        recent = {p["id"] for p in periods if p["tipo"] == "dia"}
        day_str = tops["date"].dt.strftime("%Y-%m-%d")
        for d in sorted(recent):
            x = C.country_month_articles(tops[day_str == d])
            frames.append(x.assign(period=d))
        cma = pd.concat(frames, ignore_index=True)
        totals = (
            cma.groupby(["period", "country"])
            .agg(total=("views_sum", "sum"), days=("days", "first"))
            .reset_index()
        )
        totals["avg_daily"] = totals["total"] / totals["days"]
        presence = []
        for per, g in cma.groupby("period"):
            p = C.topic_presence(g, resolved)
            p["period"] = per
            presence.append(p)
        presence = pd.concat(presence, ignore_index=True) if presence else pd.DataFrame()

        period_ids = [p["id"] for p in periods]
        # globo: modo periodo
        vol = {c: [None] * len(period_ids) for c in countries_with_data}
        days_map = {c: [0] * len(period_ids) for c in countries_with_data}
        pidx = {p: i for i, p in enumerate(period_ids)}
        for r in totals.itertuples():
            vol[r.country][pidx[r.period]] = int(round(r.avg_daily))
            days_map[r.country][pidx[r.period]] = int(r.days)
        _compact({"periodos": period_ids, "metrica": "visitas diarias aprox. de los artículos del ranking", "valores": vol, "dias": days_map}, out / "globe" / "periodo.json")

        # globo: modo tema
        for tid in topics:
            sub = presence[presence["topic_id"] == tid] if not presence.empty else presence
            share = {c: [0.0] * len(period_ids) for c in countries_with_data}
            rank = {c: [None] * len(period_ids) for c in countries_with_data}
            for r in sub.itertuples():
                share[r.country][pidx[r.period]] = round(float(r.share_permil), 3)
                rank[r.country][pidx[r.period]] = int(r.best_rank)
            _compact({"periodos": period_ids, "metrica": "visitas del tema por cada 1.000 visitas del ranking del país", "valores": share, "puesto": rank}, out / "globe" / f"{tid}.json")

        # paneles por país: top 25 artículos de cada país y periodo + temas presentes
        # Misma correspondencia que usa el globo (sitelinks + destinos de redirección), para que panel y globo coincidan.
        title_to_topic = {(project, article): tid for tid, project, article in iter_topic_titles(resolved)}
        for per, g in cma.groupby("period"):
            payload = {}
            for c, gc in g.groupby("country"):
                gc = gc.sort_values("views_sum", ascending=False)
                is_topic = [title_to_topic.get((p_, a_)) is not None for p_, a_ in zip(gc["project"], gc["article"])]
                # Top 25 + cualquier artículo de un tema del observatorio aunque esté más abajo.
                top = gc[(gc["rank"] <= 25) | pd.Series(is_topic, index=gc.index)]
                payload[c] = {
                    "dias": int(gc["days"].iloc[0]),
                    "articulos_en_ranking": int(len(gc)),
                    "articulos": [
                        {
                            "articulo": a.article.replace("_", " "),
                            "proyecto": a.project,
                            "visitas_diarias_aprox": int(round(a.avg_daily)),
                            "dias_presente": int(a.days_present),
                            "tema": title_to_topic.get((a.project, a.article)),
                            "puesto": int(a.rank),
                        }
                        for a in top.itertuples()
                    ],
                }
            _compact(payload, out / "countries" / f"{per}.json")

    progress("Preparando geometría de países (Natural Earth)…")
    ensure_geojson(PATHS.geo_cache)
    for name in ("countries.geojson", "countries-50m.geojson"):
        shutil.copy(PATHS.geo_cache / name, out / name)

    daily_index: list[dict] = []
    day_files: list[dict] = []
    peaks: dict = {}
    cnames: dict[str, str] = {}
    if tops_path.exists():
        progress("Generando curiosidades por país y por día…")
        geo = json.loads((PATHS.geo_cache / "countries.geojson").read_text(encoding="utf-8"))
        cnames = {f["properties"]["iso"]: f["properties"]["nombre"] for f in geo["features"] if f["properties"]["iso"]}
        tnames = {tid: t["nombre"] for tid, t in topics.items()}
        for iso, prof in Q.country_profiles(tops, resolved, tnames).items():
            _compact({**prof, "nombre": cnames.get(iso, iso)}, out / "countries" / "perfil" / f"{iso}.json")
        peaks = recent_peaks(daily, topics)
        for d in sorted({p["id"] for p in periods if p["tipo"] == "dia"}):
            cur = Q.daily_curiosities(tops, resolved, tnames, pd.Timestamp(d), peaks, country_names=cnames)
            if cur:
                _compact(cur, out / "daily" / f"{d}.json")
                daily_index.append({"fecha": d, "n": len(cur["curiosidades"])})
                day_files.append(cur)
        _compact({"dias": sorted(daily_index, key=lambda x: x["fecha"], reverse=True)}, out / "daily" / "index.json")
        recent_days = sorted({p["id"] for p in periods if p["tipo"] == "dia"})
        _compact(Q.propagation(tops, resolved, tnames, recent_days), out / "propagacion.json")

    # Lo más leído en cada edición (último día publicado) y resumen semanal.
    trending_path = PATHS.processed / "trending.json"
    trending = json.loads(trending_path.read_text(encoding="utf-8")) if trending_path.exists() else {}
    if trending:
        last = trending["ultimo_dia"]
        tmap = {(lang, title.replace(" ", "_")): tid for tid, t in topics.items() for lang, title in (t.get("titulos") or {}).items()}
        _compact({
            "fecha": last,
            "por_idioma": {
                lang: [{**a, "articulo": a["articulo"].replace("_", " "), "tema": tmap.get((lang, a["articulo"])),
                        "url": f"https://{lang}.wikipedia.org/wiki/{quote(a['articulo'], safe='')}"} for a in days.get(last, [])[:25]]
                for lang, days in trending["por_idioma"].items()
            },
        }, out / "trending.json")
    if not peaks:
        peaks = recent_peaks(daily, topics)
    if not cnames and (PATHS.geo_cache / "countries.geojson").exists():
        geo = json.loads((PATHS.geo_cache / "countries.geojson").read_text(encoding="utf-8"))
        cnames = {f["properties"]["iso"]: f["properties"]["nombre"] for f in geo["features"] if f["properties"]["iso"]}
    weekly = W.build_weekly(daily, topics, day_files, trending, peaks, cnames)
    if weekly:
        _compact(weekly, out / "semana.json")

    report_path = PATHS.reports / "observatorio.html"
    meta = {
        "generado": pd.Timestamp.now(tz="UTC").isoformat(),
        "mes_final": context["mes_final"],
        "idiomas": cfg.languages,
        "temas": [
            {
                "id": tid,
                "nombre": t["nombre"],
                "descripcion": t.get("descripcion"),
                "grupo": t.get("grupo"),
                "tendencia": ((t["por_idioma"].get(ALL) or {}).get("tendencia") or {}).get("clase"),
                "visitas_12m": (t["por_idioma"].get(ALL) or {}).get("visitas_12m"),
                "idiomas": sorted(k for k in t["por_idioma"] if k != ALL),
                "wikidata": t.get("wikidata"),
                "openalex": t.get("openalex"),
            }
            for tid, t in sorted(topics.items(), key=lambda x: x[1]["nombre"])
        ],
        "periodos": periods,
        "paises_con_datos": countries_with_data,
        "fuentes": [
            {**WikipediaSource.info.__dict__},
            {"id": "openalex", "nombre": "OpenAlex (producción científica)", "estado": "previsto, no implementado", "url": "https://openalex.org"},
            {"id": "naturalearth", "nombre": "Natural Earth 1:110m y 1:50m, países (v5.1.2)", "url": "https://www.naturalearthdata.com/", "licencia": "Dominio público"},
        ],
        "limitaciones": LIMITACIONES,
        "proporcion_movil": context.get("proporcion_movil", {}),
        "reporte_disponible": report_path.exists(),
        "demo": is_demo(),
        "curiosidades_dias": [d["fecha"] for d in sorted(daily_index, key=lambda x: x["fecha"], reverse=True)],
    }
    _compact(meta, out / "meta.json")
    _compact(findings, out / "findings.json")
    _compact(clusters, out / "clusters.json")
    progress(f"Exportación lista en {out} ({len(topics)} temas, {len(periods)} periodos, {len(countries_with_data)} países).")

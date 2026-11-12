"""Resumen semanal: la última semana con datos frente a la anterior.

Todo sale de datos ya descargados: visitas diarias de los temas, curiosidades diarias (rankings por país),
picos detectados y lo más leído de cada edición. Cada frase cita sus números y enlaza su artículo.
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from .curiosities import edicion, fecha_corta, link
from .findings import num, pct

ALL = "todas"
MIN_VISITAS_SEMANA_PREVIA = 500  # evita porcentajes enormes sobre bases mínimas


def _topic_link(topic: dict) -> list[dict]:
    titles = topic.get("titulos") or {}
    for lang in ("es", "en"):
        if lang in titles:
            return [link(f"{lang}.wikipedia", titles[lang].replace(" ", "_"))]
    return []


def topic_movers(daily: dict[str, dict[str, pd.Series]], topics: dict, end: pd.Timestamp) -> tuple[list[dict], list[dict]]:
    """Temas que más suben y más bajan: visitas de la semana frente a la semana anterior (todos los idiomas)."""
    rows = []
    for tid, d in daily.items():
        s = d.get(ALL)
        if s is None or tid not in topics:
            continue
        week = s.loc[end - pd.Timedelta(days=6): end].sum()
        prev = s.loc[end - pd.Timedelta(days=13): end - pd.Timedelta(days=7)].sum()
        if prev >= MIN_VISITAS_SEMANA_PREVIA:
            rows.append((tid, float(week), float(prev), float(week / prev - 1)))
    rows.sort(key=lambda r: r[3], reverse=True)

    def item(r, sube: bool) -> dict:
        tid, week, prev, ch = r
        verbo = "subió" if sube else "bajó"
        return {
            "tipo": "sube" if sube else "baja",
            "texto": f"«{topics[tid]['nombre']}» {verbo} {pct(abs(ch))} frente a la semana anterior: "
                     f"{num(week)} visitas (antes {num(prev)}), sumando los idiomas analizados.",
            "tema": tid,
            "enlaces": _topic_link(topics[tid]),
        }

    sube = [item(r, True) for r in rows if r[3] > 0.05][:3]
    baja = [item(r, False) for r in reversed(rows) if r[3] < -0.05][:3]
    return sube, baja


def week_peaks(peaks: dict[str, list[dict]], topics: dict, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    items = []
    for tid, lst in peaks.items():
        for pk in lst:
            d = pd.Timestamp(pk["fecha"])
            if start <= d <= end and tid in topics:
                items.append((pk["magnitud"], {
                    "tipo": "pico",
                    "texto": f"Pico en «{topics[tid]['nombre']}» ({edicion(pk['idioma'] + '.wikipedia')}): {num(pk['visitas'])} visitas "
                             f"el {fecha_corta(d)}, {num(pk['magnitud'], 1)} veces lo habitual.",
                    "tema": tid,
                    "enlaces": [link(f"{pk['idioma']}.wikipedia", pk["titulo"].replace(" ", "_"))],
                }))
    return [i for _, i in sorted(items, key=lambda x: -x[0])[:4]]


def week_multicountry(day_files: list[dict], country_names: dict[str, str]) -> list[dict]:
    """Artículos que entraron a la vez en varios países durante la semana (unión de países y días)."""
    acc: dict[str, dict] = {}
    for day in day_files:
        for c in day.get("curiosidades", []):
            if c.get("tipo") != "varios_paises" or not c.get("enlaces"):
                continue
            url = c["enlaces"][0]["url"]
            e = acc.setdefault(url, {"enlace": c["enlaces"][0], "paises": set(), "dias": set()})
            e["paises"].update(c.get("paises") or [])
            e["dias"].add(day["fecha"])
    best = sorted(acc.values(), key=lambda e: (-len(e["paises"]), -len(e["dias"])))[:5]
    out = []
    for e in best:
        paises = sorted(e["paises"])
        nombres = ", ".join(country_names.get(p, p) for p in paises[:6]) + ("…" if len(paises) > 6 else "")
        out.append({
            "tipo": "varios_paises",
            "texto": f"«{e['enlace']['titulo']}» ({edicion(e['enlace']['proyecto'])}) entró de golpe en el ranking de "
                     f"{len(paises)} países ({nombres}), en {len(e['dias'])} {'día' if len(e['dias']) == 1 else 'días'} de la semana.",
            "paises": paises,
            "enlaces": [e["enlace"]],
        })
    return out


def week_trending(trending: dict, topics: dict, top: int = 10) -> dict[str, list[dict]]:
    """Lo más leído de la semana en cada edición: suma de visitas en los días publicados."""
    title_to_topic = {}
    for tid, t in topics.items():
        for lang, title in (t.get("titulos") or {}).items():
            title_to_topic[(lang, title.replace(" ", "_"))] = tid
    out: dict[str, list[dict]] = {}
    for lang, days in (trending.get("por_idioma") or {}).items():
        acc: dict[str, dict] = {}
        for _, arts in days.items():
            for a in arts:
                e = acc.setdefault(a["articulo"], {"visitas": 0, "dias": 0})
                e["visitas"] += a["visitas"]
                e["dias"] += 1
        best = sorted(acc.items(), key=lambda kv: -kv[1]["visitas"])[:top]
        out[lang] = [{
            "articulo": art.replace("_", " "),
            "visitas": v["visitas"],
            "dias": v["dias"],
            "url": f"https://{lang}.wikipedia.org/wiki/{quote(art, safe='')}",
            "tema": title_to_topic.get((lang, art)),
        } for art, v in best]
    return out


def build_weekly(daily: dict, topics: dict, day_files: list[dict], trending: dict, peaks: dict,
                 country_names: dict[str, str]) -> dict | None:
    ends = [d[ALL].index.max() for d in daily.values() if ALL in d and len(d[ALL])]
    if not ends:
        return None
    end = max(ends)
    start = end - pd.Timedelta(days=6)
    sube, baja = topic_movers(daily, topics, end)
    week_days = [f for f in day_files if start.strftime("%Y-%m-%d") <= f["fecha"] <= end.strftime("%Y-%m-%d")]
    return {
        "desde": start.strftime("%Y-%m-%d"),
        "hasta": end.strftime("%Y-%m-%d"),
        "secciones": [
            {"titulo": "Temas que más subieron", "curiosidades": sube},
            {"titulo": "Temas que más bajaron", "curiosidades": baja},
            {"titulo": "Picos de la semana", "curiosidades": week_peaks(peaks, topics, start, end)},
            {"titulo": "Lo que llegó a varios países", "curiosidades": week_multicountry(week_days, country_names)},
        ],
        "tendencias": week_trending(trending, topics) if trending else {},
        "tendencias_hasta": (trending or {}).get("ultimo_dia"),
        "nota": "Visitas exactas por edición de idioma (temas) y rankings por país aproximados. Una semana = 7 días hasta el "
                "último día publicado por Wikimedia.",
    }

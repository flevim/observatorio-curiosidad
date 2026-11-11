"""Curiosidades por país y por día, a partir de los rankings diarios por país (top-per-country).

Todo es descriptivo y aproximado (Wikimedia redondea las cifras y omite artículos con pocas visitas).
Cada curiosidad cita su número y enlaza el artículo de Wikipedia. No se atribuyen causas.
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from ..sources.wikipedia import is_article, iter_topic_titles
from .findings import MESES, num, pct

EDICIONES = {
    "es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "de": "alemán", "ja": "japonés", "it": "italiano",
    "ru": "ruso", "zh": "chino", "ar": "árabe", "pl": "polaco", "nl": "neerlandés", "sv": "sueco", "tr": "turco", "fa": "persa",
    "ko": "coreano", "id": "indonesio", "vi": "vietnamita", "uk": "ucraniano", "cs": "checo", "he": "hebreo", "hu": "húngaro",
    "fi": "finés", "da": "danés", "no": "noruego", "el": "griego", "ro": "rumano", "th": "tailandés", "hi": "hindi", "bn": "bengalí",
}


def edicion(project: str) -> str:
    code = project.split(".")[0]
    return f"Wikipedia en {EDICIONES.get(code, code)}"


def link(project: str, article: str) -> dict:
    return {
        "titulo": article.replace("_", " "),
        "proyecto": project,
        "url": f"https://{project}.org/wiki/{quote(article, safe='')}",
    }


def fecha_corta(d: pd.Timestamp) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _articles(tops: pd.DataFrame) -> pd.DataFrame:
    # Se recalcula siempre: la lista de portadas/páginas de servicio puede mejorar después de descargar.
    return tops[tops["article"].map(is_article)]


def _topic_map(resolved: dict) -> dict[tuple[str, str], str]:
    return {(p, a): t for t, p, a in iter_topic_titles(resolved)}


# ---------------------------------------------------------------- perfil por país


def country_profiles(tops: pd.DataFrame, resolved: dict, names: dict[str, str], recent_days: int = 90) -> dict[str, dict]:
    """Para cada país: qué ediciones lee, qué temas del observatorio aparecen, qué es constante y qué es solo suyo."""
    arts = _articles(tops)
    if arts.empty:
        return {}
    tmap = _topic_map(resolved)
    last = arts["date"].max()
    recent = arts[arts["date"] > last - pd.Timedelta(days=recent_days)]
    # En cuántos países aparece cada artículo en el periodo reciente (para detectar lo «propio» de un país).
    spread = recent.groupby(["project", "article"])["country"].nunique().rename("n_paises")
    out: dict[str, dict] = {}
    for iso, g in arts.groupby("country"):
        days = int(g["date"].nunique())
        cur: list[dict] = []

        # 1) Ediciones que se leen
        by_proj = g.groupby("project")["views_ceil"].sum().sort_values(ascending=False)
        share = by_proj / by_proj.sum()
        top_proj = [(p, s) for p, s in share.items() if s >= 0.05][:3]
        if top_proj:
            parts = [f"{pct(s)} en {edicion(p).replace('Wikipedia en ', '')}" for p, s in top_proj]
            cur.append({
                "tipo": "ediciones",
                "texto": f"De las visitas a artículos que entran en su ranking, {', '.join(parts[:-1]) + ' y ' + parts[-1] if len(parts) > 1 else parts[0]}.",
                "enlaces": [],
            })

        # 2) Temas del observatorio
        g_topics = g.assign(tema=[tmap.get((p, a)) for p, a in zip(g["project"], g["article"])]).dropna(subset=["tema"])
        temas = []
        for t, gt in g_topics.groupby("tema"):
            temas.append({
                "tema": t, "nombre": names.get(t, t), "dias": int(gt["date"].nunique()), "mejor_puesto": int(gt["rank"].min()),
                "ultima_vez": gt["date"].max().strftime("%Y-%m-%d"),
            })
        temas.sort(key=lambda x: (-x["dias"], x["mejor_puesto"]))
        if temas:
            t0 = temas[0]
            cur.append({
                "tipo": "temas",
                "texto": f"Del observatorio, el tema que más aparece es «{t0['nombre']}»: {t0['dias']} de {days} días observados, "
                         f"con su mejor puesto en el {t0['mejor_puesto']}."
                         + (f" También aparecen: {', '.join(x['nombre'] for x in temas[1:4])}." if len(temas) > 1 else ""),
                "tema": t0["tema"],
                "enlaces": [],
            })

        # 3) El artículo más constante (más días en el ranking)
        const = g.groupby(["project", "article"]).agg(dias=("date", "nunique"), visitas=("views_ceil", "sum")).sort_values(
            ["dias", "visitas"], ascending=False)
        if len(const):
            (p, a), r = next(iter(const.iterrows()))
            cur.append({
                "tipo": "constante",
                "texto": f"El artículo más constante es «{a.replace('_', ' ')}» ({edicion(p)}): estuvo en el ranking {int(r.dias)} de {days} días observados.",
                "enlaces": [link(p, a)],
            })

        # 4) Lo propio de los últimos meses: muy leído aquí y en casi ningún otro país
        gr = recent[recent["country"] == iso]
        if not gr.empty:
            loc = gr.groupby(["project", "article"]).agg(visitas=("views_ceil", "sum"), dias=("date", "nunique")).join(spread)
            loc = loc[(loc["n_paises"] <= 1) & (loc["dias"] >= 1)].sort_values("visitas", ascending=False).head(3)
            if len(loc):
                items = [f"«{a.replace('_', ' ')}»" for (_, a) in loc.index]
                cur.append({
                    "tipo": "propio",
                    "texto": f"En los últimos {recent_days} días, lo más leído que no entró en el ranking de ningún otro país observado: {', '.join(items)}.",
                    "enlaces": [link(p, a) for (p, a) in loc.index],
                })

        # 5) El día con el artículo más leído
        top_day = g.sort_values("views_ceil", ascending=False).iloc[0]
        cur.append({
            "tipo": "record",
            "texto": f"El mayor número de visitas a un artículo en un día observado fue para «{top_day['article'].replace('_', ' ')}» "
                     f"el {fecha_corta(top_day['date'])}: unas {num(top_day['views_ceil'])} visitas.",
            "enlaces": [link(top_day["project"], top_day["article"])],
        })

        out[iso] = {
            "pais": iso,
            "dias_observados": days,
            "desde": g["date"].min().strftime("%Y-%m-%d"),
            "hasta": g["date"].max().strftime("%Y-%m-%d"),
            "curiosidades": cur,
            "temas": temas,
        }
    return out


# ---------------------------------------------------------------- curiosidades del día


def daily_curiosities(tops: pd.DataFrame, resolved: dict, names: dict[str, str], day: pd.Timestamp,
                      topic_peaks: dict[str, list[dict]] | None = None, lookback: int = 7,
                      country_names: dict[str, str] | None = None) -> dict | None:
    """Qué hubo de nuevo en los rankings de un día frente a los `lookback` días anteriores observados."""
    cn = lambda iso: (country_names or {}).get(iso, iso)  # noqa: E731
    arts = _articles(tops)
    today = arts[arts["date"] == day]
    if today.empty:
        return None
    prev = arts[(arts["date"] < day) & (arts["date"] >= day - pd.Timedelta(days=lookback))]
    prev_days = int(prev["date"].nunique())
    tmap = _topic_map(resolved)
    items: list[dict] = []

    # 1) Artículos nuevos en varios países a la vez
    prev_keys = set(zip(prev["project"], prev["article"]))
    multi = today.groupby(["project", "article"]).agg(paises=("country", lambda s: sorted(set(s))), visitas=("views_ceil", "sum"))
    multi["n"] = multi["paises"].map(len)
    nuevos = multi[pd.Series([k not in prev_keys for k in multi.index], index=multi.index, dtype=bool)].sort_values(
        ["n", "visitas"], ascending=False)
    for (p, a), r in nuevos[nuevos["n"] >= 2].head(4).iterrows():
        items.append({
            "_peso": 3e9 + r.n * 1e6 + min(r.visitas, 999999),
            "tipo": "varios_paises",
            "texto": f"«{a.replace('_', ' ')}» ({edicion(p)}) entró en el ranking de {r.n} países a la vez "
                     f"({', '.join(cn(c) for c in r.paises[:6])}{'…' if r.n > 6 else ''}) sin haber aparecido en los {prev_days} días anteriores observados.",
            "paises": r.paises,
            "enlaces": [link(p, a)],
        })

    # 2) Novedades locales: entran en el top 10 de un país, en ningún otro país hoy y no estaban la semana anterior
    prev_by_country = set(zip(prev["country"], prev["project"], prev["article"]))
    local = today[(today["rank"] <= 10)].copy()
    # Máscaras con índice: con una lista vacía, df[[]] seleccionaría columnas en vez de filas.
    local = local[pd.Series([(c, p, a) not in prev_by_country for c, p, a in zip(local["country"], local["project"], local["article"])],
                            index=local.index, dtype=bool)]
    local = local[pd.Series([multi.loc[(p, a), "n"] == 1 for p, a in zip(local["project"], local["article"])],
                            index=local.index, dtype=bool)]
    for r in local.sort_values("views_ceil", ascending=False).drop_duplicates("country").head(6).itertuples():
        items.append({
            "_peso": 2e9 + (10 - int(r.rank)) * 1e6 + min(r.views_ceil, 999999),
            "tipo": "local",
            "texto": f"En {cn(r.country)}, «{r.article.replace('_', ' ')}» subió al puesto {r.rank} (≈ {num(r.views_ceil)} visitas) "
                     f"sin aparecer en ningún otro país ni en los días anteriores.",
            "paises": [r.country],
            "enlaces": [link(r.project, r.article)],
        })

    # 3) Temas del observatorio presentes en los rankings del día
    t_today = today.assign(tema=[tmap.get((p, a)) for p, a in zip(today["project"], today["article"])]).dropna(subset=["tema"])
    for t, gt in t_today.groupby("tema"):
        best = gt.sort_values("rank").iloc[0]
        items.append({
            "_peso": 1e9,
            "tipo": "tema",
            "texto": f"«{names.get(t, t)}» está en el ranking de {gt['country'].nunique()} {'país' if gt['country'].nunique() == 1 else 'países'}: mejor puesto {int(best['rank'])} en {cn(best['country'])}.",
            "tema": t,
            "paises": sorted(gt["country"].unique().tolist()),
            "enlaces": [link(best["project"], best["article"])],
        })

    # 4) Picos recientes en las visitas por idioma de los temas
    for t, peaks in (topic_peaks or {}).items():
        for pk in peaks:
            d = pd.Timestamp(pk["fecha"])
            if day - pd.Timedelta(days=2) <= d <= day:
                lg, title = pk["idioma"], pk["titulo"]
                items.append({
                    "_peso": 1.5e9 + min(pk["magnitud"], 999) * 1e3,
                    "tipo": "pico",
                    "texto": f"Pico de atención en «{names.get(t, t)}» ({edicion(lg + '.wikipedia')}): {num(pk['visitas'])} visitas el "
                             f"{fecha_corta(d)}, {num(pk['magnitud'], 1)} veces su nivel habitual.",
                    "tema": t,
                    "enlaces": [link(f"{lg}.wikipedia", title.replace(" ", "_"))],
                })

    # Lo más llamativo primero: varios países, picos, novedades locales (mejor puesto y más visitas) y temas.
    # Como máximo 4 novedades locales, para que no se repita la misma plantilla una y otra vez.
    items.sort(key=lambda c: -c.pop("_peso"))
    locales = [c for c in items if c["tipo"] == "local"][:4]
    items = [c for c in items if c["tipo"] != "local"] + locales
    return {
        "fecha": day.strftime("%Y-%m-%d"),
        "paises": int(today["country"].nunique()),
        "dias_comparados": prev_days,
        "curiosidades": items,
        "nota": "Rankings diarios por país de Wikimedia (aproximados). «Nuevo» = no estaba en los días anteriores observados.",
    }

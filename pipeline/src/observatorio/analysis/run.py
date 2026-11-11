"""Etapa `analyze`: calcula todas las métricas y las guarda en data/processed/analysis/*.json."""

from __future__ import annotations

import json
import math
from urllib.parse import quote
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from ..settings import PATHS, load_topics
from ..sources.wikipedia import WIKIDATA_PROPS, save_json
from . import countries as C
from . import timeseries as T
from .findings import build_findings

ALL = "todas"  # serie combinada de todos los idiomas
STAT_MIN_R = 0.25
STAT_MAX_P = 0.001


def _read(name: str) -> pd.DataFrame | None:
    p = PATHS.processed / name
    return pd.read_parquet(p) if p.exists() else None


def _json(name: str):
    p = PATHS.processed / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def last_complete_month(monthly: pd.DataFrame) -> pd.Timestamp:
    return monthly["date"].max()


def build_series(pv: pd.DataFrame) -> tuple[dict, dict]:
    """{topic: {lang: Series}} para diario y mensual, incluida la serie combinada 'todas'."""
    daily: dict[str, dict[str, pd.Series]] = {}
    monthly: dict[str, dict[str, pd.Series]] = {}
    for (tid, gran), g in pv.groupby(["topic_id", "granularity"]):
        target = daily if gran == "daily" else monthly
        d = target.setdefault(tid, {})
        for lang, gg in g.groupby("series"):
            d[lang] = gg.set_index("date")["value"].sort_index().astype(float)
    for target, freq in ((daily, "D"), (monthly, "MS")):
        for tid, d in target.items():
            if d:
                df = pd.DataFrame(d).asfreq(freq)
                # Serie combinada: suma de idiomas (0 antes de que exista el artículo en un idioma).
                d[ALL] = df.fillna(0).sum(axis=1)
    return daily, monthly


def relative_weight(monthly: dict, totals: pd.DataFrame | None, langs: list[str], end: pd.Timestamp) -> dict:
    """Peso del tema en cada idioma: (visitas del tema / visitas totales de la edición) en los últimos 12 meses,
    dividido por la media de esa proporción en los idiomas donde existe. 2,0 = pesa el doble que en el idioma medio."""
    if totals is None or totals.empty:
        return {}
    tot = totals[totals["access"] == "all-access"]
    start = end - pd.DateOffset(months=11)
    lang_total = tot[(tot["date"] >= start) & (tot["date"] <= end)].groupby("lang")["views"].sum()
    out = {}
    for tid, d in monthly.items():
        shares = {}
        for lang in langs:
            if lang in d and lang in lang_total.index and lang_total[lang] > 0:
                v = d[lang].loc[start:end].sum()
                if v > 0:
                    shares[lang] = v / lang_total[lang]
        if len(shares) >= 3:
            mean = float(np.mean(list(shares.values())))
            out[tid] = {
                lang: {"proporcion_por_millon": round(s * 1e6, 2), "indice": round(s / mean, 3)} for lang, s in shares.items()
            }
    return out


def mobile_share(totals: pd.DataFrame | None) -> dict:
    """Proporción de visitas móviles (web móvil + app) por idioma y año: contexto para las limitaciones."""
    if totals is None or totals.empty:
        return {}
    t = totals.copy()
    t["year"] = t["date"].dt.year
    piv = t.pivot_table(index=["lang", "year"], columns="access", values="views", aggfunc="sum").reset_index()
    out: dict = {}
    for _, row in piv.iterrows():
        allv = row.get("all-access")
        if not allv or (isinstance(allv, float) and math.isnan(allv)):
            continue
        mob = (row.get("mobile-web") or 0) + (row.get("mobile-app") or 0)
        out.setdefault(row["lang"], {})[int(row["year"])] = round(float(mob / allv), 3)
    return out


def semantic_relations(resolved: dict, relations: dict | None) -> list[dict]:
    """Relaciones semánticas entre temas del observatorio (enlaces, Wikidata, categorías)."""
    if not relations:
        return []
    out: dict[tuple[str, str], dict] = {}

    def add(a, b, kind, detail):
        key = tuple(sorted((a, b)))
        e = out.setdefault(key, {"a": key[0], "b": key[1], "tipo": "semantica", "evidencias": []})
        if detail not in e["evidencias"]:
            e["evidencias"].append(detail)

    names = {k: v["nombre"] for k, v in resolved.items()}
    for l in relations.get("links", []):
        if l["from"] in names and l["to"] in names:
            add(l["from"], l["to"], "enlace", f"El artículo «{names[l['from']]}» enlaza a «{names[l['to']]}» ({l['lang']}.wikipedia)")

    labels = relations.get("wikidata_labels", {})
    qid_to_tid = {v["wikidata"]: k for k, v in resolved.items()}
    for tid, r in resolved.items():
        for prop, vals in (r.get("claims") or {}).items():
            for v in vals:
                if v in qid_to_tid and qid_to_tid[v] != tid:
                    add(tid, qid_to_tid[v], "wikidata", f"Wikidata: «{names[tid]}» {WIKIDATA_PROPS[prop]} «{names[qid_to_tid[v]]}»")
    for a, b in combinations(sorted(resolved), 2):
        ca = {(p, v) for p, vs in (resolved[a].get("claims") or {}).items() for v in vs}
        cb = {(p, v) for p, vs in (resolved[b].get("claims") or {}).items() for v in vs}
        for p, v in sorted(ca & cb):
            if p in ("P31",) and v in ("Q5",):  # "ser humano" es demasiado genérico
                continue
            lab = (labels.get(v) or {}).get("es") or (labels.get(v) or {}).get("en") or v
            add(a, b, "wikidata", f"Wikidata: ambos tienen «{WIKIDATA_PROPS[p]}: {lab}»")
        cats = relations.get("categories", {})
        shared = set((cats.get(a) or {}).get("en", [])) & set((cats.get(b) or {}).get("en", []))
        if shared:
            add(a, b, "categoria", "Categorías compartidas en en.wikipedia: " + ", ".join(sorted(c.split(":", 1)[-1] for c in shared)[:4]))
    return list(out.values())


def candidate_topics(resolved: dict, relations: dict | None) -> dict[str, list[dict]]:
    """Temas relacionados en Wikidata que aún no están en el observatorio (sugerencias para agregar)."""
    if not relations:
        return {}
    labels = relations.get("wikidata_labels", {})
    in_set = {v["wikidata"] for v in resolved.values()}
    generic = {"Q5", "Q151885", "Q35120", "Q7184903", "Q11862829", "Q2995644", "Q1047113"}
    out = {}
    for tid, r in resolved.items():
        seen, items = set(), []
        for prop, vals in (r.get("claims") or {}).items():
            for v in vals:
                lab = labels.get(v) or {}
                if v in in_set or v in generic or v in seen or not (lab.get("eswiki") or lab.get("enwiki")):
                    continue
                seen.add(v)
                items.append(
                    {"wikidata": v, "relacion": WIKIDATA_PROPS[prop], "nombre": lab.get("es") or lab.get("en") or v,
                     "titulo_es": lab.get("eswiki"), "titulo_en": lab.get("enwiki")}
                )
        out[tid] = items[:12]
    return out


def statistical_relations(daily: dict) -> list[dict]:
    """Pares de temas cuyas anomalías semanales (sin tendencia y sin el factor común de Wikipedia) se correlacionan."""
    out = []
    ids = sorted(t for t in daily if ALL in daily[t])
    anoms = T.remove_common_factor({t: T.weekly_anomalies(daily[t][ALL]) for t in ids})
    for a, b in combinations(ids, 2):
        res = T.weekly_anomaly_corr(anoms[a], anoms[b], already_anomalies=True)
        if res is None:
            continue
        r, p, n = res
        if r >= STAT_MIN_R and p <= STAT_MAX_P:
            out.append({"a": a, "b": b, "tipo": "estadistica", "r": r, "p_valor": p, "semanas": n})
    return out


def _silhouette(dist: np.ndarray, labels: np.ndarray) -> float:
    n = len(labels)
    s = []
    for i in range(n):
        same = labels == labels[i]
        if same.sum() <= 1:
            s.append(0.0)
            continue
        a = dist[i, same & (np.arange(n) != i)].mean()
        b = min(dist[i, labels == l].mean() for l in set(labels) if l != labels[i])
        s.append((b - a) / max(a, b))
    return float(np.mean(s))


def clusters(monthly: dict, names: dict) -> dict:
    """Agrupamiento jerárquico (enlace promedio) con distancia 1 − correlación de log(visitas mensuales)
    estandarizadas, desde 2016. El número de grupos (2–6) se elige por la silueta media."""
    series = {t: np.log1p(d[ALL].loc["2016-01-01":]) for t, d in monthly.items() if ALL in d}
    df = pd.DataFrame(series).dropna()
    if df.shape[1] < 4 or len(df) < 24:
        return {"grupos": [], "metodo": "insuficientes datos"}
    z = (df - df.mean()) / df.std(ddof=0)
    corr = z.corr().clip(-1, 1)
    dist = (1 - corr.values)
    np.fill_diagonal(dist, 0)
    lk = linkage(squareform(dist, checks=False), method="average")
    best = None
    for k in range(2, min(7, df.shape[1])):
        lab = fcluster(lk, k, criterion="maxclust")
        sc = _silhouette(dist, lab)
        if best is None or sc > best[0]:
            best = (sc, k, lab)
    sc, k, lab = best
    groups = []
    for g in sorted(set(lab)):
        members = [c for c, l in zip(df.columns, lab) if l == g]
        sub = corr.loc[members, members].values
        within = float(sub[np.triu_indices(len(members), 1)].mean()) if len(members) > 1 else None
        profile = z[members].mean(axis=1)
        groups.append(
            {
                "id": int(g),
                "temas": members,
                "nombres": [names.get(m, m) for m in members],
                "correlacion_interna": None if within is None else round(within, 3),
                "perfil_anual": {str(y): round(float(v), 3) for y, v in profile.groupby(profile.index.year).mean().items()},
            }
        )
    return {
        "metodo": "jerárquico, enlace promedio, distancia = 1 − r de log(visitas mensuales) estandarizadas",
        "k": int(k),
        "silueta": round(sc, 3),
        "grupos": groups,
        "matriz_correlacion": {a: {b: round(float(corr.loc[a, b]), 3) for b in corr.columns} for a in corr.index},
    }


def country_summary(cp: pd.DataFrame, names: dict) -> dict:
    out = {}
    for tid, g in cp.groupby("topic_id"):
        by_country = g.groupby("country").agg(meses=("month", "nunique"), mejor_puesto=("best_rank", "min"), visitas=("views_sum", "sum"))
        out[tid] = {
            "paises": int(len(by_country)),
            "meses_con_presencia": int(g["month"].nunique()),
            "primera_vez": g["month"].min().strftime("%Y-%m"),
            "ultima_vez": g["month"].max().strftime("%Y-%m"),
            "top_paises": [
                {"pais": c, "meses": int(r.meses), "mejor_puesto": int(r.mejor_puesto), "visitas_aprox": int(r.visitas)}
                for c, r in by_country.sort_values(["meses", "visitas"], ascending=False).head(10).iterrows()
            ],
        }
    return out


def wiki_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"


def pageviews_url(lang: str, title: str, start: str, end: str) -> str:
    """Herramienta oficial de Wikimedia para ver las visitas de un artículo (permite verificar el dato)."""
    return (f"https://pageviews.wmcloud.org/?project={lang}.wikipedia.org&platform=all-access&agent=user"
            f"&redirects=0&start={start}&end={end}&pages={quote(title.replace(' ', '_'), safe='')}")


def add_links(findings: dict, topics: dict) -> None:
    """Agrega a cada hallazgo el artículo exacto que respalda el número (en el idioma del dato si lo hay)."""
    for h in findings["hallazgos"]:
        links = []
        lang = h["numeros"].get("idioma") if isinstance(h.get("numeros"), dict) else None
        main = h["numeros"].get("tema") if isinstance(h.get("numeros"), dict) else None
        for tid in ([main] if main else h["temas"][:2]):
            titles = topics.get(tid, {}).get("titulos") or {}
            for lg in [x for x in (lang, "es", "en") if x]:
                if lg in titles:
                    title = titles[lg]
                    link = {"tema": tid, "nombre": topics[tid]["nombre"], "idioma": lg, "titulo": title, "url": wiki_url(lg, title)}
                    fecha = h["numeros"].get("fecha") if isinstance(h.get("numeros"), dict) else None
                    if fecha:  # pico: ventana de dos meses alrededor de la fecha
                        d = pd.Timestamp(fecha)
                        link["visitas_url"] = pageviews_url(lg, title, (d - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
                                                            (d + pd.Timedelta(days=30)).strftime("%Y-%m-%d"))
                    else:
                        link["visitas_url"] = pageviews_url(lg, title, "2015-07-01", topics[tid]["por_idioma"].get(ALL, {}).get("ultimo_dia", ""))
                    links.append(link)
                    break
        h["enlaces"] = links


def analyze(progress=print) -> dict:
    PATHS.ensure()
    cfg = load_topics()
    pv = _read("pageviews.parquet")
    if pv is None or pv.empty:
        raise SystemExit("No hay datos. Ejecuta primero: python -m observatorio fetch")
    resolved = _json("topics_resolved.json") or {}
    resolved = {k: v for k, v in resolved.items() if cfg.get(k)}
    relations = _json("relations.json")
    totals = _read("project_totals.parquet")
    tops = _read("country_top.parquet")
    names = {t.id: t.nombre for t in cfg.topics}
    langs = cfg.languages

    pv = pv[pv["topic_id"].isin(resolved)]
    daily, monthly = build_series(pv)
    monthly_pv = pv[pv["granularity"] == "monthly"]
    end_month = last_complete_month(monthly_pv)

    progress("Analizando tendencias, picos y estacionalidad…")
    topics_out = {}
    for tid in sorted(daily):
        per_lang = {}
        for lang in [*langs, ALL]:
            if lang not in daily[tid]:
                continue
            ds = daily[tid][lang]
            ms = monthly[tid].get(lang)
            if ms is None:
                ms = ds.resample("MS").sum()
            ms = ms.loc[:end_month]
            peaks = T.detect_peaks(ds)
            halves = [p.vida_media_dias for p in peaks if p.vida_media_dias is not None]
            backs = [p.vuelta_normalidad_dias for p in peaks if p.vuelta_normalidad_dias is not None]
            last12 = ms.loc[end_month - pd.DateOffset(months=11) : end_month]
            per_lang[lang] = {
                "visitas_totales": int(ds.sum()),
                "visitas_12m": int(last12.sum()),
                "media_diaria_12m": round(float(last12.sum() / max(1, (end_month + pd.offsets.MonthEnd(0) - last12.index.min()).days + 1)), 1) if len(last12) else None,
                "primer_dia": ds.index.min().strftime("%Y-%m-%d"),
                "ultimo_dia": ds.index.max().strftime("%Y-%m-%d"),
                "tendencia": T.trend(ms),
                "estacionalidad": T.seasonality(ms),
                "picos": T.peaks_as_dicts(peaks, top=10),
                "n_picos": len(peaks),
                "vida_media_mediana": None if not halves else float(np.median(halves)),
                "vuelta_normalidad_mediana": None if not backs else float(np.median(backs)),
            }
        # Comparación entre idiomas: cada idioma frente al inglés (y español frente a inglés destacado).
        comps = []
        ref = "en"
        if ref in daily[tid]:
            for lang in langs:
                if lang == ref or lang not in daily[tid]:
                    continue
                lag = T.lagged_correlation(daily[tid][ref], daily[tid][lang])
                comps.append(
                    {
                        "idioma": lang,
                        "referencia": ref,
                        "r_mensual_log": T.monthly_log_corr(monthly[tid].get(ref, pd.Series(dtype=float)), monthly[tid].get(lang, pd.Series(dtype=float))),
                        "desfase": lag,
                    }
                )
        r = resolved.get(tid, {})
        topics_out[tid] = {
            "id": tid,
            "nombre": names.get(tid, tid),
            "wikidata": r.get("wikidata"),
            "descripcion": r.get("descripcion_es") or r.get("descripcion_en"),
            "titulos": r.get("titles", {}),
            "idiomas_sin_articulo": r.get("missing", []),
            "redirecciones": r.get("redirects", []),
            "openalex": r.get("openalex"),
            "por_idioma": per_lang,
            "comparacion_idiomas": comps,
        }

    progress("Calculando peso relativo por idioma, relaciones y grupos…")
    if totals is not None and not totals.empty:
        tot = totals[totals["access"] == "all-access"].pivot_table(index="date", columns="lang", values="views", aggfunc="sum")
        for tid, t in topics_out.items():
            present = [l for l in langs if l in monthly[tid] and l in tot.columns]
            if not present or ALL not in t["por_idioma"]:
                continue
            # Cada edición entra en el denominador solo desde el mes en que el artículo tiene visitas;
            # si no, la creación del artículo en otro idioma parecería una caída relativa.
            den = pd.Series(0.0, index=tot.index)
            num = pd.Series(0.0, index=tot.index)
            for l in present:
                m = monthly[tid][l].reindex(tot.index).fillna(0)
                first = m[m > 0].index.min()
                if pd.isna(first):
                    continue
                den = den + tot[l].where(tot.index >= first, 0).fillna(0)
                num = num + m
            share = (num / den.where(den > 0)).dropna().loc[:end_month] * 1e6
            t["por_idioma"][ALL]["tendencia_relativa"] = T.trend(share)

    weights = relative_weight(monthly, totals, langs, end_month)
    for tid, w in weights.items():
        topics_out[tid]["peso_relativo"] = w

    sem = semantic_relations(resolved, relations)
    stat = statistical_relations(daily)
    cands = candidate_topics(resolved, relations)
    cl = clusters(monthly, names)
    for g in cl.get("grupos", []):
        for t in g["temas"]:
            topics_out[t]["grupo"] = g["id"]

    country = {}
    if tops is not None and not tops.empty:
        progress("Agregando rankings por país…")
        cma = C.country_month_articles(tops)
        cp = C.topic_presence(cma, resolved)
        country = country_summary(cp, names)
        for tid, s in country.items():
            if tid in topics_out:
                topics_out[tid]["paises"] = s

    context = {
        "mes_final": end_month.strftime("%Y-%m"),
        "idiomas": langs,
        "proporcion_movil": mobile_share(totals),
        "generado": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    findings = build_findings(topics_out, sem, stat, cl, context)
    add_links(findings, topics_out)

    out_dir = PATHS.analysis
    save_json(topics_out, out_dir / "topics.json")
    save_json({"semanticas": sem, "estadisticas": stat, "candidatos": cands}, out_dir / "relations.json")
    save_json(cl, out_dir / "clusters.json")
    save_json(context, out_dir / "context.json")
    save_json(findings, out_dir / "findings.json")
    progress(f"Análisis listo: {len(topics_out)} temas, {len(sem)} relaciones semánticas, {len(stat)} estadísticas, "
             f"{len(cl.get('grupos', []))} grupos, {len(findings['hallazgos'])} hallazgos.")
    return topics_out

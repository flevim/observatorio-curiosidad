"""Datos SINTÉTICOS para pruebas automáticas y para revisar la interfaz sin conexión.

No representan la realidad. Cuando se generan en data/processed se escribe el marcador
data/processed/DEMO, la exportación lo propaga (meta.demo = true) y la web y el reporte
muestran un aviso permanente. `python -m observatorio fetch` borra el marcador y los datos sintéticos.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .settings import PATHS, load_countries, load_topics
from .sources.wikipedia import sample_days, save_json

DEMO_MARKER = "DEMO"


def synthetic_daily(rng: np.random.Generator, start: date, end: date, *, level: float, growth: float,
                    seasonal_amp: float = 0.0, seasonal_peak_month: int = 1, peaks: list[tuple[int, float, float]] = ()) -> pd.Series:
    idx = pd.date_range(start, end, freq="D")
    t = np.arange(len(idx)) / 365.25
    base = level * np.exp(np.log1p(growth) * t)
    if seasonal_amp:
        base *= 1 + seasonal_amp * np.cos(2 * np.pi * (idx.day_of_year.values / 365.25 - (seasonal_peak_month - 0.5) / 12))
    weekly = 1 + 0.08 * np.cos(2 * np.pi * idx.day_of_week.values / 7)
    y = base * weekly * rng.lognormal(0, 0.08, len(idx))
    for day_i, mult, half_life in peaks:
        k = np.arange(len(idx)) - day_i
        y += np.where(k >= 0, base[day_i] * mult * np.power(0.5, np.clip(k, 0, None) / half_life), 0)
    return pd.Series(np.round(y).astype("int64"), index=idx)


def generate(root_processed=None, *, seed: int = 7, today: date | None = None, n_topics: int | None = None) -> None:
    out = root_processed or PATHS.processed
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    cfg = load_topics()
    topics = cfg.topics[:n_topics] if n_topics else cfg.topics
    today = today or date.today()
    start, end = date(2015, 7, 1), today - timedelta(days=2)
    n_days = (end - start).days + 1
    lang_scale = {"en": 1.0, "es": 0.25, "de": 0.2, "fr": 0.15, "ja": 0.18, "ru": 0.14, "it": 0.1, "pt": 0.08, "zh": 0.06, "ar": 0.04}

    resolved, rows = {}, []
    for ti, t in enumerate(topics):
        level = float(rng.lognormal(7.5, 0.8))
        growth = float(rng.normal(0.0, 0.25))
        amp = 0.35 if ti % 5 == 0 else 0.0
        peak_days = sorted(rng.choice(np.arange(200, n_days - 30), size=3, replace=False).tolist())
        common_peaks = [(d, float(rng.uniform(5, 40)), float(rng.uniform(1.5, 12))) for d in peak_days]
        titles = {}
        for li, lang in enumerate(cfg.languages):
            lag = 0 if lang == "en" else int(rng.integers(0, 3))
            peaks = [(min(d + lag, n_days - 1), m * rng.uniform(0.6, 1.4), h) for d, m, h in common_peaks]
            s = synthetic_daily(rng, start, end, level=level * lang_scale.get(lang, 0.05), growth=growth,
                                seasonal_amp=amp, seasonal_peak_month=1 + ti % 12, peaks=peaks)
            titles[lang] = f"{t.nombre} ({lang})"
            for gran, ser in (("daily", s), ("monthly", s.resample("MS").sum().loc[: pd.Timestamp(today.replace(day=1)) - pd.Timedelta(days=1)])):
                rows.append(pd.DataFrame({"topic_id": t.id, "source": "wikipedia", "series": lang, "granularity": gran,
                                          "date": ser.index, "value": ser.values.astype("int64"), "exact": True}))
        resolved[t.id] = {
            "id": t.id, "nombre": t.nombre, "wikidata": f"Q{900000 + ti}", "label_es": t.nombre, "label_en": t.nombre,
            "descripcion_es": "tema de demostración (datos sintéticos)", "descripcion_en": None,
            "sitelinks": {lang: titles[lang] for lang in cfg.languages}, "titles": titles, "redirects": [], "missing": [],
            "openalex": t.openalex, "claims": {"P31": ["Q1"]} if ti % 2 == 0 else {"P279": ["Q2"]},
        }
    pd.concat(rows, ignore_index=True).to_parquet(out / "pageviews.parquet", index=False)
    save_json(resolved, out / "topics_resolved.json")

    ids = [t.id for t in topics]
    links = [{"from": ids[i], "to": ids[(i + 1) % len(ids)], "lang": "en"} for i in range(0, len(ids), 3)]
    save_json({"links": links, "categories": {}, "wikidata_labels": {"Q1": {"es": "concepto", "en": "concept"},
                                                                     "Q2": {"es": "disciplina", "en": "discipline"}}}, out / "relations.json")

    tot = []
    months = pd.date_range("2015-07-01", pd.Timestamp(today.replace(day=1)) - pd.Timedelta(days=1), freq="MS")
    for lang, sc in lang_scale.items():
        if lang not in cfg.languages:
            continue
        mobile = np.linspace(0.45, 0.75, len(months))
        allv = sc * 7e9 * np.ones(len(months))
        for access, v in (("all-access", allv), ("desktop", allv * (1 - mobile)), ("mobile-web", allv * mobile * 0.95), ("mobile-app", allv * mobile * 0.05)):
            tot.append(pd.DataFrame({"date": months, "views": v.astype("int64"), "lang": lang, "access": access}))
    pd.concat(tot, ignore_index=True).to_parquet(out / "project_totals.parquet", index=False)

    ccfg = load_countries()
    days = sample_days(ccfg, today)
    trows = []
    for c in ccfg.countries:
        size = float(rng.lognormal(9, 1))
        lang = {"ES": "es", "MX": "es", "AR": "es", "CL": "es", "CO": "es", "PE": "es", "BR": "pt", "PT": "pt", "FR": "fr", "DE": "de", "AT": "de",
                "JP": "ja", "IT": "it", "RU": "ru", "TW": "zh", "HK": "zh", "EG": "ar", "SA": "ar"}.get(c, "en")
        for d in days:
            n = 40
            arts = [(f"Artículo_{c}_{k}", f"{lang}.wikipedia", int(size * (n - k) / n) + 1000) for k in range(n)]
            for ti, t in enumerate(topics):
                if rng.random() < 0.08:
                    arts.append((titles_for(resolved, t.id, lang), f"{lang}.wikipedia", int(size * rng.uniform(0.05, 0.5)) + 1000))
            arts.sort(key=lambda a: -a[2])
            for r, (a, p, v) in enumerate(arts, start=1):
                trows.append({"country": c, "date": pd.Timestamp(d), "rank": r, "project": p, "article": a, "views_ceil": int(np.ceil(v / 100) * 100), "is_article": True})
    pd.DataFrame(trows).to_parquet(out / "country_top.parquet", index=False)
    (out / DEMO_MARKER).write_text("Datos sintéticos generados por `python -m observatorio demo`.\n", encoding="utf-8")


def titles_for(resolved: dict, tid: str, lang: str) -> str:
    return resolved[tid]["sitelinks"][lang].replace(" ", "_")


def is_demo() -> bool:
    return (PATHS.processed / DEMO_MARKER).exists()


def clear_demo() -> None:
    if is_demo():
        for name in ("pageviews.parquet", "topics_resolved.json", "relations.json", "project_totals.parquet", "country_top.parquet", DEMO_MARKER):
            p = PATHS.processed / name
            if p.exists():
                p.unlink()

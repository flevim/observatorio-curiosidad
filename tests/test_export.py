"""Agregados por país y exportación de extremo a extremo con datos sintéticos en un directorio temporal."""

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from observatorio.analysis import countries as C
from observatorio.settings import PATHS

ROOT = Path(__file__).resolve().parents[1]


def _tops():
    rows = []
    for d, views in (("2025-10-08", 3000), ("2025-10-22", 5000)):
        rows += [
            {"country": "CL", "date": pd.Timestamp(d), "rank": 1, "project": "es.wikipedia", "article": "Wikipedia:Portada", "views_ceil": 90000},
            {"country": "CL", "date": pd.Timestamp(d), "rank": 2, "project": "es.wikipedia", "article": "Ajedrez", "views_ceil": views},
            {"country": "CL", "date": pd.Timestamp(d), "rank": 3, "project": "es.wikipedia", "article": "Otro", "views_ceil": 2000},
        ]
    # MX solo tiene un día y no incluye el tema
    rows.append({"country": "MX", "date": pd.Timestamp("2025-10-08"), "rank": 1, "project": "es.wikipedia", "article": "Otro", "views_ceil": 4000})
    return pd.DataFrame(rows)


def test_country_month_articles_excludes_service_pages_and_averages():
    cma = C.country_month_articles(_tops())
    cl = cma[cma["country"] == "CL"].set_index("article")
    assert "Wikipedia:Portada" not in cl.index
    assert cl.loc["Ajedrez", "views_sum"] == 8000
    assert cl.loc["Ajedrez", "days"] == 2
    assert cl.loc["Ajedrez", "avg_daily"] == 4000
    assert cl.loc["Ajedrez", "rank"] == 1


def test_topic_presence_share():
    cma = C.country_month_articles(_tops())
    resolved = {"ajedrez": {"sitelinks": {"es": "Ajedrez", "en": "Chess"}, "redirects": []}}
    p = C.topic_presence(cma, resolved)
    assert set(p["country"]) == {"CL"}  # MX: sin presencia (no "cero datos")
    row = p.iloc[0]
    assert row["views_sum"] == 8000
    assert abs(row["share_permil"] - 8000 / 12000 * 1000) < 1e-9


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "topics.yaml", tmp_path / "config" / "topics.yaml")
    shutil.copy(ROOT / "config" / "countries.yaml", tmp_path / "config" / "countries.yaml")
    monkeypatch.setattr(PATHS, "root", tmp_path)
    PATHS.ensure()
    # Geometría mínima para no depender de la red.
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"iso": "CL", "nombre": "Chile"}, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
    for name in ("countries.geojson", "countries-50m.geojson"):
        (PATHS.geo_cache / name).write_text(json.dumps(geo), encoding="utf-8")
    return tmp_path


def test_end_to_end_export_numbers_match(tmp_root):
    from observatorio.analysis.run import analyze
    from observatorio.demo import generate
    from observatorio.export import export
    from observatorio.report.build import build_report

    generate(today=date(2025, 11, 10), n_topics=6)
    analyze(progress=lambda s: None)
    export(progress=lambda s: None)
    report = Path(build_report())
    assert report.exists() and "DATOS SINTÉTICOS" in report.read_text(encoding="utf-8")

    web = PATHS.web
    meta = json.loads((web / "meta.json").read_text(encoding="utf-8"))
    assert meta["demo"] is True
    assert len(meta["temas"]) == 6
    assert any(p["tipo"] == "mes" for p in meta["periodos"]) and any(p["tipo"] == "dia" for p in meta["periodos"])

    # El valor del globo para un tema/país/periodo coincide con la presencia calculada desde los datos crudos.
    tops = pd.read_parquet(PATHS.processed / "country_top.parquet")
    resolved = json.loads((PATHS.processed / "topics_resolved.json").read_text(encoding="utf-8"))
    cma = C.country_month_articles(tops)
    pres = C.topic_presence(cma, resolved)
    row = pres.sort_values("share_permil", ascending=False).iloc[0]
    g = json.loads((web / "globe" / f"{row.topic_id}.json").read_text(encoding="utf-8"))
    i = g["periodos"].index(row.month.strftime("%Y-%m"))
    assert g["valores"][row.country][i] == pytest.approx(row.share_permil, abs=1e-3)
    assert g["puesto"][row.country][i] == row.best_rank

    # El panel del país lista el tema con las mismas visitas diarias aproximadas.
    panel = json.loads((web / "countries" / f"{row.month.strftime('%Y-%m')}.json").read_text(encoding="utf-8"))
    arts = [a for a in panel[row.country]["articulos"] if a["tema"] == row.topic_id]
    assert arts and arts[0]["visitas_diarias_aprox"] == round(row.views_sum / row.days)

    # La serie mensual exportada suma lo mismo que la diaria original para un mes cerrado.
    t = json.loads((web / "topics" / f"{row.topic_id}.json").read_text(encoding="utf-8"))
    pv = pd.read_parquet(PATHS.processed / "pageviews.parquet")
    d = pv[(pv.topic_id == row.topic_id) & (pv.series == "es") & (pv.granularity == "daily")]
    oct_sum = int(d[(d.date >= "2025-10-01") & (d.date <= "2025-10-31")]["value"].sum())
    assert t["mensual"]["series"]["es"][t["mensual"]["fechas"].index("2025-10")] == oct_sum


def test_append_topic_keeps_comments(tmp_root):
    from observatorio.settings import TopicConfig, append_topic, load_topics

    append_topic(TopicConfig(id="volcan", nombre="Volcán", seed_lang="es", seed_title="Volcán"))
    text = (PATHS.config / "topics.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Temas del Observatorio")
    assert load_topics().get("volcan").seed_title == "Volcán"
    with pytest.raises(ValueError):
        append_topic(TopicConfig(id="volcan", nombre="X"))

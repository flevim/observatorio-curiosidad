"""Resumen semanal y lista de lo más leído."""

import numpy as np
import pandas as pd

from observatorio.analysis.weekly import topic_movers, week_multicountry, week_trending
from observatorio.sources.wikipedia import parse_top


def _series(prev_daily: float, week_daily: float, end="2026-11-10"):
    idx = pd.date_range(end=end, periods=14, freq="D")
    return pd.Series(np.r_[np.full(7, prev_daily), np.full(7, week_daily)], index=idx)


def test_topic_movers_up_and_down():
    daily = {"a": {"todas": _series(100, 150)}, "b": {"todas": _series(200, 100)}, "c": {"todas": _series(10, 100)}}
    topics = {k: {"nombre": k.upper(), "titulos": {"es": k}} for k in daily}
    sube, baja = topic_movers(daily, topics, pd.Timestamp("2026-11-10"))
    assert [x["tema"] for x in sube] == ["a"]  # c se descarta: semana previa con menos de 500 visitas
    assert "50 %" in sube[0]["texto"] and "1.050" in sube[0]["texto"]
    assert [x["tema"] for x in baja] == ["b"]


def test_parse_top_filters_service_pages():
    data = {"items": [{"articles": [
        {"article": "Wikipedia:Portada", "views": 900, "rank": 1},
        {"article": "Especial:Buscar", "views": 800, "rank": 2},
        {"article": "León_XIV", "views": 500, "rank": 3},
    ]}]}
    assert parse_top(data) == [{"articulo": "León_XIV", "visitas": 500, "puesto": 1}]


def test_week_trending_sums_days_and_marks_topics():
    trending = {"por_idioma": {"es": {
        "2026-11-09": [{"articulo": "Litio", "visitas": 10, "puesto": 1}, {"articulo": "X", "visitas": 30, "puesto": 2}],
        "2026-11-10": [{"articulo": "Litio", "visitas": 25, "puesto": 1}],
    }}}
    out = week_trending(trending, {"litio": {"titulos": {"es": "Litio"}}})["es"]
    assert out[0]["articulo"] == "Litio" and out[0]["visitas"] == 35 and out[0]["dias"] == 2 and out[0]["tema"] == "litio"


def test_week_multicountry_unions_countries():
    link = {"titulo": "A", "proyecto": "en.wikipedia", "url": "u"}
    days = [
        {"fecha": "2026-11-09", "curiosidades": [{"tipo": "varios_paises", "paises": ["CL", "AR"], "enlaces": [link]}]},
        {"fecha": "2026-11-10", "curiosidades": [{"tipo": "varios_paises", "paises": ["AR", "PE"], "enlaces": [link]}]},
    ]
    out = week_multicountry(days, {"CL": "Chile", "AR": "Argentina", "PE": "Perú"})
    assert out[0]["paises"] == ["AR", "CL", "PE"] and "3 países" in out[0]["texto"] and "2 días" in out[0]["texto"]

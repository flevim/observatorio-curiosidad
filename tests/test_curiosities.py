"""Curiosidades del día y perfiles por país sobre rankings pequeños construidos a mano."""

import pandas as pd

from observatorio.analysis.curiosities import country_profiles, daily_curiosities
from observatorio.sources.wikipedia import is_article


def _row(country, day, rank, article, views, project="es.wikipedia"):
    return {"country": country, "date": pd.Timestamp(day), "rank": rank, "project": project, "article": article, "views_ceil": views}


def _tops():
    rows = []
    for d in ["2026-11-01", "2026-11-02"]:
        rows += [_row("CL", d, 1, "Wikipedia:Portada", 90000), _row("CL", d, 2, "Cleopatra", 5000), _row("MX", d, 1, "Cleopatra", 7000)]
    d = "2026-11-03"
    rows += [
        _row("CL", d, 1, "Cleopatra", 5000),
        _row("CL", d, 2, "Noticia_local", 4000),          # nueva y solo en Chile
        _row("CL", d, 3, "Evento_global", 3000),          # nueva en varios países
        _row("MX", d, 1, "Evento_global", 6000),
        _row("AR", d, 1, "Evento_global", 2000),
        _row("AR", d, 2, "Litio", 1500),                  # tema del observatorio
    ]
    return pd.DataFrame(rows)


RESOLVED = {"litio": {"sitelinks": {"es": "Litio"}, "redirects": []}}
NAMES = {"litio": "Litio"}
CN = {"CL": "Chile", "MX": "México", "AR": "Argentina"}


def test_daily_detects_new_multicountry_local_and_topic():
    out = daily_curiosities(_tops(), RESOLVED, NAMES, pd.Timestamp("2026-11-03"), country_names=CN)
    kinds = {c["tipo"]: c for c in out["curiosidades"]}
    locales = " | ".join(c["texto"] for c in out["curiosidades"] if c["tipo"] == "local")
    assert out["dias_comparados"] == 2
    assert "Evento global" in kinds["varios_paises"]["texto"] and "3 países" in kinds["varios_paises"]["texto"]
    assert "En Chile, «Noticia local»" in locales
    assert kinds["tema"]["tema"] == "litio" and "1 país:" in kinds["tema"]["texto"]
    # Cleopatra ya estaba antes: no es novedad
    assert not any("Cleopatra" in c["texto"] for c in out["curiosidades"])
    assert kinds["varios_paises"]["enlaces"][0]["url"] == "https://es.wikipedia.org/wiki/Evento_global"


def test_daily_without_data_returns_none():
    assert daily_curiosities(_tops(), RESOLVED, NAMES, pd.Timestamp("2026-12-01")) is None


def test_country_profile_excludes_main_page_and_counts_days():
    prof = country_profiles(_tops(), RESOLVED, NAMES)
    cl = prof["CL"]
    assert cl["dias_observados"] == 3
    texts = " ".join(c["texto"] for c in cl["curiosidades"])
    assert "Portada" not in texts
    assert "«Cleopatra»" in texts and "3 de 3 días" in texts
    assert prof["AR"]["temas"][0]["tema"] == "litio"


def test_unprefixed_main_pages_are_not_articles():
    assert not is_article("Hauptseite")
    assert is_article("Hauptstadt")

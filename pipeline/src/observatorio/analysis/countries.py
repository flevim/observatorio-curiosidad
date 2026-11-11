"""Agregación de los rankings diarios por país (top-per-country) a meses.

La API solo publica rankings diarios. El "mes" se construye con los días muestreados
(config/countries.yaml). Por eso todas las cifras derivadas son aproximadas:
- views_ceil viene redondeado hacia arriba por Wikimedia (privacidad);
- un artículo con pocas visitas en un día no aparece en el ranking;
- solo se observan los días muestreados.
"""

from __future__ import annotations

import pandas as pd

from ..sources.wikipedia import is_article, iter_topic_titles


def _prepare(tops: pd.DataFrame) -> pd.DataFrame:
    df = tops.copy()
    df["is_article"] = df["article"].map(is_article)  # siempre con la regla vigente
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df


def days_sampled(tops: pd.DataFrame) -> pd.DataFrame:
    """Días con ranking disponible por país y mes: (country, month, days)."""
    df = _prepare(tops)
    return df.groupby(["country", "month"])["date"].nunique().rename("days").reset_index()


def country_month_articles(tops: pd.DataFrame) -> pd.DataFrame:
    """Suma por (país, mes, artículo) sobre los días muestreados, solo artículos (sin portadas ni especiales).

    Columnas: country, month, project, article, views_sum, days_present, best_rank, days, avg_daily, rank
    """
    df = _prepare(tops)
    ds = days_sampled(tops)
    arts = df[df["is_article"]]
    g = (
        arts.groupby(["country", "month", "project", "article"])
        .agg(views_sum=("views_ceil", "sum"), days_present=("date", "nunique"), best_rank=("rank", "min"))
        .reset_index()
    )
    g = g.merge(ds, on=["country", "month"], how="left")
    g["avg_daily"] = g["views_sum"] / g["days"]
    g = g.sort_values(["country", "month", "views_sum"], ascending=[True, True, False])
    g["rank"] = g.groupby(["country", "month"]).cumcount() + 1
    return g.reset_index(drop=True)


def country_month_totals(cma: pd.DataFrame) -> pd.DataFrame:
    """Total de visitas (aprox.) de los artículos del ranking por país y mes."""
    return (
        cma.groupby(["country", "month"])
        .agg(total_views=("views_sum", "sum"), n_articles=("article", "count"), days=("days", "first"))
        .reset_index()
        .assign(avg_daily_total=lambda d: d["total_views"] / d["days"])
    )


def topic_presence(cma: pd.DataFrame, resolved: dict[str, dict]) -> pd.DataFrame:
    """Presencia de cada tema en el ranking de cada país y mes.

    share_permil = visitas del tema / visitas de todos los artículos del ranking × 1000.
    Esta proporción no depende del tamaño del país, por eso se usa para colorear el globo.
    """
    keys = pd.DataFrame(list(iter_topic_titles(resolved)), columns=["topic_id", "project", "article"]).drop_duplicates()
    if keys.empty or cma.empty:
        return pd.DataFrame(
            columns=["country", "month", "topic_id", "views_sum", "days_present", "best_rank", "days", "share_permil", "articles"]
        )
    m = cma.merge(keys, on=["project", "article"], how="inner")
    totals = country_month_totals(cma)[["country", "month", "total_views"]]
    g = (
        m.groupby(["country", "month", "topic_id"])
        .agg(
            views_sum=("views_sum", "sum"),
            days_present=("days_present", "max"),
            best_rank=("rank", "min"),
            days=("days", "first"),
            articles=("article", lambda s: sorted(set(s))),
        )
        .reset_index()
        .merge(totals, on=["country", "month"], how="left")
    )
    g["share_permil"] = g["views_sum"] / g["total_views"] * 1000
    return g.drop(columns=["total_views"])

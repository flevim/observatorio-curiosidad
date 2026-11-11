"""Fuentes de datos. Cada una implementa observatorio.sources.base.DataSource."""

from .base import DataSource, FetchReport, SourceInfo
from .wikipedia import WikipediaSource

SOURCES: dict[str, type[DataSource]] = {"wikipedia": WikipediaSource}
# Futuro: SOURCES["openalex"] = OpenAlexSource  (ver docs/openalex.md)

__all__ = ["DataSource", "FetchReport", "SourceInfo", "WikipediaSource", "SOURCES"]

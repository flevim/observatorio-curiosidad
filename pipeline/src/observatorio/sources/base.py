"""Interfaz común de fuentes de datos.

Wikipedia es la primera fuente. OpenAlex (producción científica) será la segunda: implementará
esta misma interfaz y su serie se superpondrá a la curva de atención. Ver docs/openalex.md.

Contrato de datos: toda fuente entrega series en formato largo con estas columnas:

    topic_id     id del tema en config/topics.yaml
    source       "wikipedia", "openalex", ...
    series       nombre de la serie dentro de la fuente ("es", "en", "works", ...)
    granularity  "daily" | "monthly" | "yearly"
    date         fecha de inicio del periodo (datetime64)
    value        número (visitas, publicaciones, ...)
    exact        True si el valor es exacto; False si es aproximado/redondeado

El análisis y la exportación solo dependen de este contrato, no de la fuente concreta.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

from ..settings import TopicConfig

SERIES_COLUMNS = ["topic_id", "source", "series", "granularity", "date", "value", "exact"]


@dataclass
class SourceInfo:
    id: str
    nombre: str
    url: str
    licencia: str
    unidad: str  # qué mide cada valor ("visitas", "publicaciones")
    exacto: bool
    notas: list[str] = field(default_factory=list)


@dataclass
class FetchReport:
    """Resumen de una descarga: qué se obtuvo y qué problemas hubo (para mostrarlos, no esconderlos)."""

    source: str
    network_calls: int = 0
    cached_calls: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


class DataSource(ABC):
    """Una fuente que asocia temas a series temporales."""

    info: SourceInfo

    @abstractmethod
    def resolve(self, topics: list[TopicConfig]) -> dict[str, dict]:
        """Traduce cada tema a los identificadores propios de la fuente.

        Para Wikipedia: elemento de Wikidata y título exacto en cada idioma.
        Para OpenAlex: id del topic de OpenAlex.
        """

    @abstractmethod
    def fetch(self, topics: list[TopicConfig], report: FetchReport) -> None:
        """Descarga (o lee de la caché) los datos crudos de los temas."""

    @abstractmethod
    def series(self, topics: list[TopicConfig]) -> pd.DataFrame:
        """Devuelve las series en el formato largo SERIES_COLUMNS."""


def empty_series() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in SERIES_COLUMNS})

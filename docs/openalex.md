# Integración futura con OpenAlex

**Estado: prevista, no implementada.**

La pregunta que motiva la integración: **¿la curiosidad pública va delante o detrás de la producción científica?**
Por ejemplo, ¿las visitas a «CRISPR» o «Semaglutida» suben antes o después que el número de publicaciones?

## Qué ya está preparado

1. **Interfaz común de fuente de datos**, en `pipeline/src/observatorio/sources/base.py` (`DataSource`).
   Toda fuente entrega series en el mismo formato largo:
   `topic_id, source, series, granularity, date, value, exact`.
   El análisis (`analysis/timeseries.py`) trabaja sobre series de pandas y no sabe de dónde vienen.
2. **Asociación tema ↔ topic de OpenAlex**: cada tema de `config/topics.yaml` acepta una clave opcional `openalex:`
   (por ejemplo `openalex: T10856`). El valor viaja por `topics_resolved.json`, el análisis y la exportación,
   y la web ya lo muestra.
3. **Espacio en la interfaz**: el panel del tema tiene la sección «Producción científica (próximamente)», donde
   se superpondrá la curva de publicaciones a la de atención.
4. **Registro de fuentes**: `observatorio/sources/__init__.py` tiene un diccionario `SOURCES` donde se registrará
   `OpenAlexSource`.
5. **Variable de entorno reservada**: `OPENALEX_API_KEY` en `.env.example`.

## Acceso a OpenAlex (verificar al implementar)

- Según el encargo del proyecto, **desde febrero de 2026 la API exige una clave gratuita** con un presupuesto
  diario de uso. La documentación consultada el 11-11-2026 (help.openalex.org) dice que el uso básico es gratuito,
  que una clave gratuita multiplica por 10 el presupuesto diario y que el uso intensivo es de pago según consumo.
  En cualquier caso conviene usar siempre la clave. Se envía como parámetro `api_key=…`, y cada respuesta trae
  `meta.cost_usd` con el costo de la llamada. Antes de implementar, revisar las páginas *Authentication* y *Pricing*.
- **Snapshot gratuito** para descargas masivas: bucket público `s3://openalex/data/` (JSON Lines comprimido o
  Parquet), sin cuenta de AWS (`--no-sign-request`). Se actualiza trimestralmente y pesa unos 750 GB por formato,
  así que para 20–100 temas **la API es suficiente**. El snapshot solo se justifica si se analizan miles de temas.
- Licencia de los datos: CC0.

## Diseño propuesto

```
pipeline/src/observatorio/sources/openalex.py
  class OpenAlexSource(DataSource):
      info = SourceInfo(id="openalex", unidad="publicaciones", exacto=True, ...)
      resolve(topics)   -> {topic_id: {"openalex": "T…", "nombre": …}}
      fetch(topics, report)
      series(topics)    -> filas con source="openalex", series="works", granularity="monthly"
```

1. **Resolver el topic.** Si `openalex:` está en `topics.yaml`, usarlo tal cual. Si no, sugerir candidatos con
   `GET /topics?search=<label_en>` y **pedir confirmación** (no asociar automáticamente: los topics de OpenAlex son
   clústeres de investigación, no equivalen 1:1 a artículos de Wikipedia). Alternativa: buscar el QID de Wikidata
   del tema en `/concepts` (heredado) o en las palabras clave.
2. **Contar publicaciones por mes**:
   `GET /works?filter=topics.id:T…,from_publication_date=2015-07-01&group_by=publication_year` da el conteo anual
   en una sola llamada. Para meses: una llamada por mes con `from_publication_date`/`to_publication_date` y
   `per-page=1`, leyendo `meta.count` (~140 llamadas por tema). Reutilizar `PoliteClient` (caché SQLite, pausas,
   backoff) con `api_key` desde `.env`, y descartar el último año: los registros recientes siguen creciendo
   durante meses (retraso de indexación).
3. **Guardar** en `data/processed/openalex.parquet` con el mismo esquema de series.
4. **Analizar**: reutilizar `lagged_correlation`, pero sobre series mensuales y con desfases en meses (±24).
   Comparar el log de visitas mensuales (todos los idiomas) con el log de publicaciones, ambos sin tendencia
   (diferencia de la media móvil de 12 meses). Reportar el desfase solo si es estable al dividir el periodo en dos mitades.
5. **Exportar** `topics/{id}.json → ciencia: {fechas, publicaciones, desfase}` y dibujarlo en la sección ya reservada
   del panel, en **un gráfico aparte con el mismo eje de tiempo** (no con dos ejes Y), o con ambas series indexadas
   a base 100.

## Cautelas para la interpretación

- La producción científica tiene inercia (meses o años entre la investigación y la publicación) y la atención
  pública reacciona a eventos. Una correlación con desfase no demuestra que una cause la otra.
- La cobertura de OpenAlex varía por disciplina, idioma y año.
- Un topic de OpenAlex puede ser más amplio o más estrecho que el artículo de Wikipedia.

# Métodos de análisis

Implementación en `pipeline/src/observatorio/analysis/timeseries.py`, con pruebas en `tests/test_analysis.py`.
«Todos los idiomas» es la suma diaria de las ediciones analizadas (0 antes de que exista el artículo en una edición).

## Tendencia de largo plazo

- Serie: visitas **mensuales** (mínimo 24 meses), en logaritmo, para que la pendiente sea un cambio porcentual.
- Pendiente: **estimador de Theil-Sen** (mediana de las pendientes entre todos los pares de puntos), robusto a picos.
  Se reporta como cambio anual `exp(pendiente) − 1` con su intervalo de confianza del 95 %.
- Significación: **prueba de Mann-Kendall** (tau de Kendall frente al tiempo).
- Clase: «sube» si p < 0,05 y el cambio es ≥ +10 % anual; «baja» si p < 0,05 y es ≤ −10 % anual; si no, «se mantiene».
- Cautela: la autocorrelación mensual hace que el p-valor sea optimista. Por eso se exige además un umbral de magnitud.

## Picos de atención

- Línea base: **mediana de los 56 días previos** (sin incluir el día). Dispersión: MAD de esos días × 1,4826.
- Un día es anómalo si cumple las tres condiciones: z robusto ≥ 6, visitas ≥ 3 × línea base y exceso ≥ 200 visitas.
  La última evita «picos» en artículos con pocas visitas.
- Los días anómalos separados por ≤ 3 días forman un evento, cuya fecha es la del máximo.
- **Magnitud** = visitas del día máximo / línea base previa al evento.
- **Vida media** = días desde el máximo hasta que el exceso sobre la línea base cae a la mitad o menos.
- **Vuelta a la normalidad** = días hasta que el exceso queda por debajo del 10 % del exceso máximo durante 3 días
  seguidos (máximo 365 días). Si no ocurre, se informa «no volvió» (cambio de nivel).
- Si un evento empieza antes de que el anterior vuelva a la normalidad, se fusionan y queda el mayor.

## Estacionalidad

- Serie mensual en logaritmo, dividida por su **media móvil centrada 2×12** (elimina tendencia y nivel).
- Perfil estacional = promedio por mes del año (mínimo 3 años completos).
- **Fuerza** = 1 − var(residuo) / var(serie sin tendencia): proporción de la variación explicada por el mes del año.
- **Consistencia** = correlación de Pearson media entre los perfiles de cada año completo.
- «Estacional» si fuerza ≥ 0,3 y consistencia ≥ 0,4. El mapa de calor muestra el factor mensual (1 = normal).

## Comparación entre idiomas

- **Correlación mensual**: Pearson de log(visitas mensuales). Está dominada por la tendencia: dos series que crecen
  se correlacionan aunque no tengan relación.
- **Desfase**: correlación cruzada de **anomalías diarias**: log(1 + visitas) menos su mediana móvil centrada de
  28 días, que deja solo las subidas y bajadas de corto plazo. Se prueban desfases de −30 a +30 días.
  Un desfase positivo significa que el idioma va **detrás** del inglés. Solo se considera informativo si
  r ≥ 0,3 en el mejor desfase, el desfase es distinto de 0 y mejora en ≥ 0,02 la correlación del mismo día.
- **Peso relativo**: (visitas del tema en un idioma / visitas totales de esa edición) en los últimos 12 meses,
  dividido por el promedio de esa proporción entre idiomas. 2,0 significa que el tema pesa el doble que en el
  idioma promedio. Los totales vienen del endpoint `aggregate` (agent=user).

## Relaciones entre temas

- **Semánticas** (siempre separadas de las estadísticas):
  - enlaces directos entre los artículos (en.wikipedia y es.wikipedia);
  - Wikidata: un tema es valor de una propiedad del otro (subclase de, parte de, faceta de, usa, estudiado por…),
    o ambos comparten un valor (p. ej. los dos son «subclase de: medicamento»);
  - categorías visibles compartidas en en.wikipedia.
- **Estadísticas**: Pearson de **anomalías semanales** (log de las visitas semanales menos su mediana móvil de
  13 semanas) de la serie de todos los idiomas. Se informa si r ≥ 0,25 y p ≤ 0,001 (umbral estricto, porque se
  prueban 190 pares).
- Sugerencias: valores de Wikidata con artículo en es o en que aún no son temas del observatorio.

## Agrupamiento

- Matriz de correlación de log(visitas mensuales) estandarizadas desde 2016 (todos los idiomas).
- Agrupamiento jerárquico con enlace promedio y distancia 1 − r. El número de grupos (2 a 6) se elige por la
  silueta media.

## Rankings por país

- Por país y periodo: suma de `views_ceil` de cada artículo en los días observados, dividida por el número de días
  observados = visitas diarias aproximadas. Se excluyen portadas y páginas especiales.
- Presencia de un tema: suma de sus artículos (en cualquier edición con sitelink en Wikidata) /
  suma de todos los artículos del ranking × 1000 (‰). Mejor puesto = puesto más alto alcanzado en ese periodo.

## Hallazgos

`analysis/findings.py` redacta los hallazgos a partir de las métricas, y cada frase cita el número que la respalda.
Si un umbral no se cumple, se dice eso («ningún tema…») en lugar de forzar una conclusión. No se atribuyen causas
a los picos.

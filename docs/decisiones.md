# Decisiones de diseño

## Globo: globe.gl (sobre three.js)

Opciones evaluadas (noviembre de 2026):

| Opción | Licencia | A favor | En contra |
|---|---|---|---|
| **globe.gl 2.46** | MIT | Polígonos GeoJSON con color, altura y transición; atmósfera; cámara `pointOfView` con transición; `OrbitControls` (arrastre, rueda, pellizco); clic y *hover* por país; poco código | Pesa ~2 MB minificado (three.js), por eso se carga aparte |
| three.js directo | MIT | Control total | Hay que programar triangulación de polígonos esféricos, *picking*, cámara y atmósfera: mucho código para lo mismo |
| deck.gl `GlobeView` | MIT | Muy rápido con muchos datos | `GlobeView` sigue marcada como experimental; atmósfera y estética espacial requieren trabajo extra |
| MapLibre GL 5 (proyección globo) | BSD-3 | Cambio globo ↔ plano en la misma API, teselas vectoriales | Pensado para mapas con estilo y teselas; el fondo de espacio y la «atmósfera» son menos configurables; para ~180 polígonos es más infraestructura de la necesaria |

**Elegido: globe.gl.** Es la que cumple el requisito (globo 3D con países coloreados, rotación, zoom, clic, transición
de cámara y atmósfera) con menos código propio, con licencia MIT y rendimiento de sobra para unos 180 polígonos.
El mapa plano alternativo usa **d3-geo** (ISC, proyección Equal Earth) en SVG, lo que además lo hace navegable con
teclado y legible por lectores de pantalla.

Rendimiento:
- El globo (three.js) se carga de forma diferida (`React.lazy`), así que la primera pintura no lo espera.
- Geometría 1:110m de Natural Earth al alejarse y 1:50m al acercarse (altitud < 0,9): se reduce el detalle lejos.
- Al cambiar de periodo solo se recalculan los colores de los polígonos (sin regenerar la geometría), con una
  transición de 250 ms (0 ms con `prefers-reduced-motion`).
- El render se pausa cuando la pestaña no está visible.
- Los agregados por país, mes y tema se precalculan en `export` (≈1 MB por todos los temas), así que la línea de
  tiempo no consulta nada nuevo al moverse.

## Geometría de países: Natural Earth

`ne_110m_admin_0_countries` y `ne_50m_admin_0_countries`, versión 5.1.2, desde el repositorio oficial
`nvkelso/natural-earth-vector`. **Dominio público.** Se usa `ISO_A2_EH` (que corrige los `-99` de Francia y Noruega
en `ISO_A2`) y `NAME_ES`. Las coordenadas se redondean a 2 y 3 decimales para aligerar los archivos.
Natural Earth muestra las fronteras *de facto*; la interfaz no toma posición sobre territorios en disputa.

## Datos y caché

- **Caché HTTP en SQLite** (`data/cache/http_cache.sqlite`), clave = URL. Los datos de periodos cerrados se guardan
  para siempre; los 404/400 («no hay datos») durante 7 días, porque un día reciente puede publicarse más tarde.
- **Datos procesados en Parquet** (`data/processed/*.parquet`): formato columnar, tipado y rápido con pandas.
- **Exportación en JSON estático** (`data/processed/web/`): la API solo lee archivos; no hay base de datos ni
  servidor de cálculo. Es lo más simple que cumple el requisito de interacción fluida.
- Las peticiones a Wikimedia van **en serie** (nunca en paralelo), con pausa mínima configurable, backoff
  exponencial ante 429/5xx (respetando `Retry-After`) y sin reintentar 400/404. Así lo pide la política de acceso
  de la Analytics API.

## Rankings por país: muestreo de días

`top-per-country` solo existe **por día** (no hay ranking mensual) y desde **2021-01-01**. Descargar todos los
días de 66 países serían unas 136.000 llamadas en serie. Por eso se muestrean los días 8 y 22 de cada mes, más
todos los días de las últimas dos semanas (unas 10.000 llamadas, configurable en `config/countries.yaml`).
El «mes» de la app es el promedio de los días observados y se rotula como aproximado, indicando qué días se usaron.

## Colores

- Globo: escala secuencial de un solo tono (azul) en 6 pasos **cuantizados**, con cortes por cuantiles calculados
  sobre **todos** los periodos, para que un color signifique lo mismo en toda la línea de tiempo.
- Tres estados distintos, nunca confundidos: con valor (azul), «no aparece en el ranking» (gris sólido) y
  «sin datos» (transparente o rayado). Sin datos nunca se pinta como cero.
- En modo tema el color es **‰ de las visitas del ranking del país**, que no depende del tamaño del país
  (si se usaran visitas absolutas, Estados Unidos e India dominarían siempre).
- Series por idioma: español, inglés y un tercer idioma elegido llevan colores categóricos fijos de una paleta
  validada para daltonismo. Los demás idiomas van en gris de contexto, porque 10 colores no son distinguibles.

## Arquitectura

- Pipeline Python como paquete instalable (`pip install -e pipeline`), con CLI `python -m observatorio`.
- La API (FastAPI) importa el paquete del pipeline para reutilizar rutas y configuración, y para agregar temas
  desde la app (ejecuta el pipeline en segundo plano, de a un trabajo por vez).
- La web nunca llama a Wikimedia: todo pasa por la API.
- Sin Docker, colas ni base de datos: no hacen falta para este volumen.

## Exploración libre en Wikipedia (excepción a «la web no llama a Wikimedia»)

El buscador ofrece «Buscar en Wikipedia» para cualquier artículo. Esa vista consulta **en vivo**, desde el navegador,
la búsqueda de Wikipedia, el resumen del artículo, los enlaces interlingüísticos y la API de visitas de Wikimedia
(`web/src/lib/wikipedia.ts`). Es la única excepción a la regla de que la web solo lee datos procesados, porque no es
posible precalcular todos los artículos. Para no abusar del servicio, las peticiones van en serie, con caché en memoria
y sin cabeceras propias (con `Api-User-Agent`, la API de visitas rechaza el preflight CORS). La interfaz dice que son
datos en vivo y sin analizar. Desde ahí se puede proponer el artículo como tema: en local lo agrega la API; en la versión
publicada se abre una propuesta (issue) en GitHub con la línea lista para `config/topics.yaml`.

# Observatorio de la Curiosidad

Analiza cómo cambia la atención pública mundial sobre distintos temas usando las visitas a Wikipedia, y la muestra
en una aplicación web con un globo terráqueo 3D. Está preparado para cruzarse más adelante con la producción
científica de OpenAlex ([docs/openalex.md](docs/openalex.md)).

```
config/topics.yaml        temas (editable sin tocar código) e idiomas
config/countries.yaml     países y días muestreados para los rankings por país
pipeline/src/observatorio/
  sources/                base.py (interfaz DataSource) · wikipedia.py
  analysis/               timeseries.py (métodos) · countries.py · run.py · findings.py
  report/                 build.py → reports/observatorio.html
  export.py               agregados JSON para la API y la web
  http.py                 caché SQLite + peticiones en serie + backoff
api/observatorio_api/     FastAPI: sirve data/processed/web
web/                      React + TypeScript + Vite + globe.gl
tests/                    pytest
docs/                     decisiones, métodos, fuentes y limitaciones, OpenAlex
data/cache/               respuestas HTTP (SQLite) y geometría
data/processed/           Parquet, análisis y exportación
```

## Requisitos

- Python 3.12 o superior
- Node.js 20 o superior (probado con Node 24 y npm 11)

## Instalación

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements.txt -e pipeline
```

(En macOS o Linux, `.venv/bin/pip`.)

```bash
npm --prefix web ci
```

```bash
cp .env.example .env
```

Edita `.env` y pon en **`OBSERVATORIO_CONTACT`** un correo, una URL o tu página de usuario de Wikimedia.
Wikimedia lo exige en el User-Agent: sin contacto rechaza las consultas (403) y el pipeline no descarga nada.

## Ejecución

Pipeline completo (la primera vez tarda: los rankings por país son ~10.000 llamadas en serie, ~30–60 min;
después todo sale de la caché):

```bash
.venv/Scripts/python -m observatorio fetch
```

```bash
.venv/Scripts/python -m observatorio analyze
```

```bash
.venv/Scripts/python -m observatorio report
```

```bash
.venv/Scripts/python -m observatorio export
```

O todo junto: `python -m observatorio all`. Otras opciones:

- `fetch --skip-countries`: solo visitas por artículo y relaciones (unos minutos).
- `fetch --countries-only`: solo rankings por país.
- `fetch --topics bitcoin ajedrez`: solo esos temas.
- `demo`: genera **datos sintéticos** para probar sin conexión. La web y el reporte muestran un aviso permanente
  y el siguiente `fetch` los borra.

API y web en desarrollo (dos terminales):

```bash
.venv/Scripts/python -m uvicorn observatorio_api.main:app --app-dir api --port 8010
```

```bash
npm --prefix web run dev
```

Abre http://localhost:5180. El reporte está en `reports/observatorio.html` (también en http://localhost:8010/reporte).

Versión compilada servida por la propia API: `npm --prefix web run build` y abre http://localhost:8010.

Pruebas:

```bash
.venv/Scripts/python -m pytest
```

## Curiosidades diarias

Cada día Wikimedia publica los rankings del día anterior. El comando

```bash
.venv/Scripts/python -m observatorio daily
```

descarga solo lo nuevo (≈200 llamadas, ~5 min), recalcula todo y genera:

- **Curiosidades del día** (`data/processed/web/daily/AAAA-MM-DD.json`): artículos que entran a la vez en el ranking de
  varios países sin haber estado la semana anterior, novedades que solo aparecen en un país, temas del observatorio
  presentes ese día y picos recientes en las visitas de los temas. En la web: tarjeta de inicio → «Del día».
- **Perfil de cada país** (`countries/perfil/XX.json`): qué ediciones de Wikipedia lee, qué temas del observatorio
  aparecen, el artículo más constante, lo leído solo ahí en los últimos 90 días y el récord de visitas en un día.
  En la web: clic en un país → «Lo curioso en…».

Para que corra solo todos los días (Programador de tareas de Windows, usuario actual):

```bash
powershell -ExecutionPolicy Bypass -File scripts/registrar-tarea.ps1 -Hora 09:00
```

El registro queda en `data/daily.log`. Para quitar la tarea: `schtasks /Delete /TN "ObservatorioCuriosidad-diario" /F`.

## Publicar gratis (GitHub Pages)

La versión pública es un **sitio estático**: la web lee directamente los JSON exportados, sin servidor
(`VITE_STATIC=1`). Tiene todo menos «Agregar tema». El workflow `.github/workflows/publicar.yml`:

1. recupera `data/` de la caché de GitHub Actions;
2. ejecuta `python -m observatorio daily` (descarga solo lo nuevo, recalcula, genera las curiosidades);
3. compila la web en modo estático y arma el sitio con `python -m observatorio site`;
4. lo publica en GitHub Pages. Corre todos los días a las 13:00 UTC, al hacer push a `main` y a mano.

Pasos, una sola vez:

1. Crea un repositorio **público** en GitHub (Pages y Actions son gratis en repositorios públicos) y sube este proyecto.
2. Settings → Secrets and variables → Actions → secreto `OBSERVATORIO_CONTACT` con tu contacto para Wikimedia.
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions → «Actualizar y publicar» → Run workflow. La primera vez tarda ~1 h (descarga todo); luego, minutos.

El sitio queda en `https://<usuario>.github.io/<repositorio>/`. GitHub pausa los workflows programados de repositorios
sin actividad durante 60 días; si pasa, se reactivan desde la pestaña Actions.

**Cloudflare Pages** también sirve: la carpeta `site/` es un sitio estático normal. Compila con `VITE_BASE=/` y súbela
con `npx wrangler pages deploy site` o conecta el repositorio.

Probar el sitio estático en local:

```bash
cd web && VITE_STATIC=1 npm run build && cd .. && python -m observatorio site && python -m http.server -d site 8030
```

## Docker

Una sola imagen (`Dockerfile`, en dos etapas: compila la web con Node y luego instala el pipeline y la API en Python)
y dos servicios en `docker-compose.yml`:

- **web**: la API FastAPI, que sirve también la web compilada, en http://localhost:8010.
- **actualizador**: ejecuta `python -m observatorio daily` todos los días a la hora `OBSERVATORIO_HORA_DIARIA`
  (zona horaria `TZ`, por defecto America/Santiago). Reemplaza al Programador de tareas de Windows.

```bash
docker compose up -d --build
```

- `data/`, `config/` y `reports/` del proyecto se montan en los contenedores: se reutilizan los datos ya descargados
  y lo agregado desde la app persiste.
- `OBSERVATORIO_CONTACT` y el resto de la configuración vienen de `.env`.
- Sin datos previos, la primera carga completa se hace con
  `docker compose run --rm actualizador python -m observatorio all` (~1 h, por los rankings por país).
- Registro de la actualización: `docker compose logs actualizador` o `data/daily.log`.
- Si usas Docker, quita la tarea de Windows para no descargar dos veces:
  `schtasks /Delete /TN "ObservatorioCuriosidad-diario" /F`.

## Agregar temas

- **Desde la configuración**: añade una línea en `config/topics.yaml` con `id`, `nombre` y `semilla`
  (artículo de partida) o `wikidata`, y ejecuta `fetch --topics <id> --skip-countries`, `analyze`, `report` y `export`.
  Los rankings por país ya descargados se vuelven a cruzar con el tema nuevo.
- **Desde la app**: «Acerca de los datos» → «Agregar tema». La API agrega la línea a `topics.yaml` y ejecuta
  el pipeline de ese tema en segundo plano.

Los títulos de cada idioma se obtienen de Wikidata (sitelinks) y se siguen las redirecciones; no se adivinan.
El pipeline avisa si un tema no existe en un idioma o si dos temas son el mismo elemento de Wikidata.

## Estado

### Terminado

- Fuente Wikimedia: per-article (diario y mensual, agent=user, desde 2015-07), top-per-country (diario, muestreado),
  totales por edición y acceso, títulos por Wikidata con redirecciones, enlaces, categorías y relaciones de Wikidata.
- Caché SQLite, peticiones en serie, backoff exponencial, manejo de 400/403/404/429/5xx, User-Agent con contacto obligatorio.
- Análisis: tendencia (Theil-Sen + Mann-Kendall), picos con vida media y vuelta a la normalidad, estacionalidad,
  correlación y desfase entre idiomas, peso relativo por idioma, presencia en rankings por país, relaciones
  semánticas y estadísticas por separado, agrupamiento jerárquico y hallazgos redactados con números.
- Reporte HTML autocontenido: series por tema (escala log opcional), vida media, mapa de calor de estacionalidad,
  hallazgos sorprendentes, métodos y limitaciones.
- Exportación de agregados por país, periodo y tema; API FastAPI con ETag.
- Web: globo con rotación lenta, arrastre, zoom, transiciones de cámara, menos detalle al alejarse; clic en un país
  con panel de lo más leído; modo tema con serie de tiempo, picos, vida media, idiomas y países; grafo de relacionados
  (semántica continua, estadística discontinua) con navegación; línea de tiempo con reproducción; buscador con
  autocompletado; migas de pan; «Acerca de los datos»; agregar temas; estado en la URL; mapa plano y tabla
  navegables con teclado; hoja inferior deslizable en celular; `prefers-reduced-motion`; espacio reservado para OpenAlex.
- 29 pruebas: parseo, caché y reintentos, picos y vida media, desfases, tendencia, estacionalidad, agregados por
  país y exportación de extremo a extremo (los números del globo, del panel y de la serie cuadran).

### Datos reales (11-11-2026)

- 20 temas × 10 idiomas, visitas desde 2015-07 y rankings de 66 países desde 2021 (10.206 llamadas, ~55 min).
  Wikimedia no publica rankings de 11 países (Rusia, China, Turquía, Irán, Arabia Saudita, Emiratos, Vietnam, entre otros);
  la app los muestra como «sin datos».
- Cambio de tema: «Computación cuántica» usa el elemento de Wikidata Q176555, porque el original no tenía artículo en ruso.
  «Cambio climático» queda sin ruso (documentado en `config/topics.yaml`).
- Verificado: las 25.496 sumas mensuales hechas desde los datos diarios coinciden con el endpoint mensual de Wikimedia,
  y el globo coincide con el panel de cada país en las 93.500 combinaciones de tema, periodo y país.

### Pendiente

- Integración con OpenAlex (diseñada en [docs/openalex.md](docs/openalex.md), no implementada).
- Medir los fps del globo en un equipo de referencia.
- Al agregar un tema desde la app no se descargan rankings por país nuevos: se cruza con los ya descargados.

# Fuentes, licencias y limitaciones

## Fuentes de datos

| Fuente | Uso | Licencia |
|---|---|---|
| Wikimedia Analytics API, `pageviews/per-article` | Visitas diarias y mensuales por artículo y edición de idioma, agent=user, desde 2015-07-01 | CC0 |
| Wikimedia Analytics API, `pageviews/top-per-country` | Artículos más vistos por país y día, desde 2021-01-01, redondeados | CC0 |
| Wikimedia Analytics API, `pageviews/aggregate` | Totales por edición y tipo de acceso | CC0 |
| MediaWiki Action API (`action=query`) | Redirecciones, enlaces entre artículos, categorías | Metadatos. Los textos de Wikipedia son CC BY-SA, pero aquí no se reutilizan |
| Wikidata API (`wbgetentities`) | Títulos equivalentes entre idiomas (sitelinks), etiquetas, relaciones | CC0 |
| Natural Earth 1:110m y 1:50m, países (v5.1.2) | Geometría del globo y del mapa | Dominio público |

Documentación consultada en noviembre de 2026: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/

### Política de uso de Wikimedia

- **User-Agent con contacto real** (correo, URL o página de usuario). Sin él, Wikimedia responde 403 a las
  consultas automáticas. Se configura en `.env` → `OBSERVATORIO_CONTACT`, y el pipeline se niega a descargar sin él.
- **Peticiones en serie**: cada una espera a que termine la anterior, con pausa mínima (`OBSERVATORIO_MIN_INTERVAL`).
- Reintentos con backoff exponencial (1, 2, 4… s) ante 429 y 5xx, respetando `Retry-After`. Sin reintento para 400/404.
- Caché local para no repetir descargas.

## Software

React, react-dom (MIT) · globe.gl, three.js (MIT) · d3-geo (ISC) · Vite (MIT) · TypeScript (Apache-2.0) ·
FastAPI, uvicorn, httpx (BSD-3) · pandas, NumPy, SciPy (BSD-3) · PyArrow (Apache-2.0) · PyYAML (MIT) · pytest (MIT).

## Limitaciones (también en la app, en «Acerca de los datos»)

1. **No representa a toda la población.** Refleja a quienes leen Wikipedia, con internet y en esos idiomas.
2. **Idioma ≠ país.** Las visitas por artículo no traen desglose por país. El español se lee en más de 20 países,
   y el inglés en todo el mundo. El proyecto **no estima ni simula** visitas por país a partir del idioma.
3. **Rankings por país aproximados.** Wikimedia redondea hacia arriba (`views_ceil`), omite artículos con pocas
   visitas (en la práctica, menos de ~1.000 diarias en un país) y no publica países protegidos o con poco tráfico.
   Un tema ausente del ranking no tiene «cero interés».
4. **Muestreo de días.** El mes por país usa algunos días (por defecto 8 y 22). Un pico en otro día no se ve.
5. **Cambio de dispositivos y de hábitos.** El tráfico pasó del escritorio al móvil, y en los últimos años parte de
   las consultas se resuelven en buscadores o asistentes sin visitar Wikipedia. Las comparaciones entre épocas
   comparan públicos distintos.
6. **Bots.** `agent=user` excluye los bots declarados y los detectados, pero algunos picos pueden ser tráfico
   automatizado no filtrado.
7. **Redirecciones.** Las visitas a un título que redirige se cuentan en la redirección, no en el artículo, y aquí
   no se suman (subestima los temas con muchos nombres).
8. **Correlación no es causalidad**, ni entre temas ni entre idiomas.
9. **Elección de artículo.** Cada tema es un artículo por idioma (el del elemento de Wikidata). Los artículos
   vecinos (p. ej. «Inflación en Argentina») no se cuentan.

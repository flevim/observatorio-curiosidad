// Cliente de la API del Observatorio. La web nunca llama a Wikimedia directamente.

export type TopicSummary = {
  id: string
  nombre: string
  descripcion: string | null
  grupo: number | null
  tendencia: 'sube' | 'baja' | 'estable' | null
  visitas_12m: number | null
  idiomas: string[]
  wikidata: string | null
  openalex: string | null
}

export type Period = { id: string; tipo: 'mes' | 'dia'; dias_muestreados: string[] }

export type Meta = {
  generado: string
  mes_final: string
  idiomas: string[]
  temas: TopicSummary[]
  periodos: Period[]
  paises_con_datos: string[]
  fuentes: { id: string; nombre: string; url?: string; licencia?: string; estado?: string; notas?: string[] }[]
  limitaciones: string[]
  proporcion_movil: Record<string, Record<string, number>>
  reporte_disponible: boolean
  demo: boolean
  curiosidades_dias?: string[]
}

export type Trend = {
  clase: 'sube' | 'baja' | 'estable'
  cambio_anual: number
  cambio_anual_ic95: [number, number]
  p_valor: number
  desde: string
  hasta: string
}

export type Peak = {
  fecha: string
  inicio: string
  fin: string
  visitas: number
  linea_base: number
  magnitud: number
  exceso_total: number
  vida_media_dias: number | null
  vuelta_normalidad_dias: number | null
}

export type Seasonality = {
  estacional: boolean
  fuerza: number
  consistencia: number | null
  perfil: number[]
  mes_pico: number
  mes_valle: number
}

export type LangMetrics = {
  visitas_totales: number
  visitas_12m: number
  media_diaria_12m: number | null
  primer_dia: string
  ultimo_dia: string
  tendencia: Trend | null
  tendencia_relativa?: Trend | null
  estacionalidad: Seasonality | null
  picos: Peak[]
  n_picos: number
  vida_media_mediana: number | null
  vuelta_normalidad_mediana: number | null
}

export type LangComparison = {
  idioma: string
  referencia: string
  r_mensual_log: number | null
  desfase: { desfase_dias: number; r_max: number; r_0: number; dias: number; informativo: boolean } | null
}

export type SeriesPayload = {
  inicio: string
  fechas: string[] | null
  series: Record<string, (number | null)[]>
}

export type TopicDetail = {
  id: string
  nombre: string
  wikidata: string | null
  descripcion: string | null
  titulos: Record<string, string>
  idiomas_sin_articulo: string[]
  redirecciones: { lang: string; from: string; to: string }[]
  openalex: string | null
  por_idioma: Record<string, LangMetrics>
  comparacion_idiomas: LangComparison[]
  peso_relativo?: Record<string, { proporcion_por_millon: number; indice: number }>
  grupo?: number
  paises?: {
    paises: number
    meses_con_presencia: number
    primera_vez: string
    ultima_vez: string
    top_paises: { pais: string; meses: number; mejor_puesto: number; visitas_aprox: number }[]
  }
  mensual: SeriesPayload
}

export type GlobeData = {
  periodos: string[]
  metrica: string
  valores: Record<string, (number | null)[]>
  puesto?: Record<string, (number | null)[]>
  dias?: Record<string, number[]>
}

export type CountryArticle = {
  articulo: string
  proyecto: string
  visitas_diarias_aprox: number
  dias_presente: number
  tema: string | null
  puesto: number
}

export type CountryPanelData =
  | { pais: string; periodo: string; sin_datos: true }
  | { pais: string; periodo: string; sin_datos: false; dias: number; articulos_en_ranking: number; articulos: CountryArticle[] }

export type Graph = {
  nodos: { id: string; nombre: string; grupo: number | null; visitas_12m: number | null }[]
  semanticas: { a: string; b: string; evidencias: string[] }[]
  estadisticas: { a: string; b: string; r: number; semanas: number }[]
  candidatos: Record<string, { wikidata: string; relacion: string; nombre: string; titulo_es: string | null; titulo_en: string | null }[]>
}

export type FindingLink = { tema: string; nombre: string; idioma: string; titulo: string; url: string; visitas_url?: string }
export type Finding = { id: string; titulo: string; texto: string; temas: string[]; enlaces?: FindingLink[] }

export type CuriosityLink = { titulo: string; proyecto: string; url: string }
export type Curiosity = { tipo: string; texto: string; tema?: string; paises?: string[]; enlaces: CuriosityLink[] }
export type CountryProfile =
  | { pais: string; sin_datos: true }
  | { pais: string; sin_datos?: false; nombre: string; dias_observados: number; desde: string; hasta: string; curiosidades: Curiosity[];
      temas: { tema: string; nombre: string; dias: number; mejor_puesto: number; ultima_vez: string }[] }
export type DailyCuriosities = { fecha: string; paises: number; dias_comparados: number; curiosidades: Curiosity[]; nota: string }

const cache = new Map<string, Promise<unknown>>()

async function get<T>(path: string, useCache = true): Promise<T> {
  if (useCache && cache.has(path)) return cache.get(path) as Promise<T>
  const p = fetch(api_(path)).then(async (r) => {
    if (!r.ok) {
      const body = await r.json().catch(() => ({}))
      throw new Error(body.detail ?? `Error ${r.status} en ${path}`)
    }
    return r.json() as Promise<T>
  })
  cache.set(path, p)
  p.catch(() => cache.delete(path))
  return p
}

/**
 * Modo estático (VITE_STATIC=1): la web se publica sin servidor (GitHub Pages, Cloudflare Pages) y lee directamente
 * los JSON exportados, copiados en `<base>/data/`. Mismos datos que sirve la API, sin «Agregar tema».
 */
export const STATIC = import.meta.env.VITE_STATIC === '1'
/** Dirección de la API en un servidor propio (VITE_API_BASE, p. ej. https://api.midominio.org). Vacía = mismo origen. */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''
const api_ = (path: string) => (path.startsWith('/api') ? `${API_BASE}${path}` : path)
const BASE = import.meta.env.BASE_URL
const data = (file: string) => `${BASE}data/${file}`
export const reportUrl = STATIC ? `${BASE}reporte.html` : `${API_BASE}/reporte`

async function getOptional<T>(path: string, fallback: T): Promise<T> {
  try {
    return await get<T>(path)
  } catch {
    return fallback
  }
}

async function staticCountry(period: string, iso: string): Promise<CountryPanelData> {
  const all = await getOptional<Record<string, Omit<Extract<CountryPanelData, { sin_datos: false }>, 'pais' | 'periodo' | 'sin_datos'>>>(
    data(`countries/${period}.json`), {})
  return all[iso] ? { pais: iso, periodo: period, sin_datos: false, ...all[iso] } : { pais: iso, periodo: period, sin_datos: true }
}

export const api = {
  meta: () => get<Meta>(STATIC ? data('meta.json') : '/api/meta', false),
  topic: (id: string) => get<TopicDetail>(STATIC ? data(`topics/${id}.json`) : `/api/topics/${id}`),
  daily: (id: string) => get<SeriesPayload>(STATIC ? data(`topics/${id}.daily.json`) : `/api/topics/${id}/daily`),
  globe: (key: string) => get<GlobeData>(STATIC ? data(`globe/${key}.json`) : `/api/globe/${key}`),
  country: (period: string, iso: string) =>
    STATIC ? staticCountry(period, iso) : get<CountryPanelData>(`/api/countries/${period}/${iso}`),
  graph: () => get<Graph>(STATIC ? data('graph.json') : '/api/graph'),
  findings: () => get<{ hallazgos: Finding[]; sorprendentes: Finding[] }>(STATIC ? data('findings.json') : '/api/findings'),
  profile: (iso: string) =>
    STATIC
      ? getOptional<CountryProfile>(data(`countries/perfil/${iso}.json`), { pais: iso, sin_datos: true })
      : get<CountryProfile>(`/api/perfil/${iso}`),
  dailyIndex: () =>
    STATIC
      ? getOptional<{ dias: { fecha: string; n: number }[] }>(data('daily/index.json'), { dias: [] })
      : get<{ dias: { fecha: string; n: number }[] }>('/api/curiosidades', false),
  curiosities: (day: string) => get<DailyCuriosities>(STATIC ? data(`daily/${day}.json`) : `/api/curiosidades/${day}`),
  geo: (lod: '110m' | '50m') =>
    get<GeoJSON>(STATIC ? data(lod === '50m' ? 'countries-50m.geojson' : 'countries.geojson') : `/api/geo/${lod}`),
  addTopic: async (body: { nombre: string; titulo?: string; idioma: string; wikidata?: string }) => {
    const r = await fetch(`${API_BASE}/api/topics`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const data = await r.json()
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo agregar el tema')
    return data as { job: string; tema: string }
  },
  job: (id: string) => get<{ estado: string; log: string[]; avisos: string[]; error: string | null; tema: string }>(`/api/jobs/${id}`, false),
  clear: () => cache.clear(),
}

export type CountryFeature = {
  type: 'Feature'
  properties: { iso: string | null; nombre: string; name: string; continente: string }
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] }
}
export type GeoJSON = { type: 'FeatureCollection'; features: CountryFeature[] }

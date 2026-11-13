// Exploración libre: consultas EN VIVO a Wikipedia y a la API de visitas de Wikimedia desde el navegador.
// Es la única parte de la web que llama a Wikimedia directamente (no hay datos precalculados para cualquier
// artículo). Peticiones simples, sin cabeceras propias (con cabeceras, el preflight CORS de la API de visitas falla),
// una a la vez y con caché en memoria, para no cargar los servidores.

import type { SeriesPayload } from '../api'

export const LANGS = ['es', 'en', 'pt', 'fr', 'de', 'ja', 'it', 'ru', 'zh', 'ar']

export type SearchHit = { title: string; snippet: string }
export type ArticleSummary = {
  title: string
  displaytitle: string
  description?: string
  extract?: string
  thumbnail?: { source: string }
  wikibase_item?: string
  url: string
}

const cache = new Map<string, Promise<unknown>>()
let queue: Promise<unknown> = Promise.resolve()

export function getJson<T>(url: string): Promise<T> {
  if (cache.has(url)) return cache.get(url) as Promise<T>
  // En serie: cada petición espera a la anterior (lo que pide la política de uso de Wikimedia).
  const p = queue.then(async () => {
    const r = await fetch(url)
    if (r.status === 404) return null as T
    if (!r.ok) throw new Error(`Wikimedia respondió ${r.status}`)
    return (await r.json()) as T
  })
  queue = p.catch(() => undefined)
  cache.set(url, p)
  p.catch(() => cache.delete(url))
  return p
}

export const action = (lang: string, params: Record<string, string>) =>
  `https://${lang}.wikipedia.org/w/api.php?` +
  new URLSearchParams({ format: 'json', formatversion: '2', origin: '*', ...params }).toString()

/** HTML de Wikipedia (fragmentos con <span> y entidades &#039;) a texto plano, sin ejecutar nada. */
const plainText = (html: string) => new DOMParser().parseFromString(html, 'text/html').documentElement.textContent ?? ''

export const enc = (title: string) => encodeURIComponent(title.replace(/ /g, '_'))

export async function searchWikipedia(lang: string, q: string): Promise<SearchHit[]> {
  const data = await getJson<{ query?: { search: { title: string; snippet: string }[] } }>(
    action(lang, { action: 'query', list: 'search', srsearch: q, srlimit: '10', srnamespace: '0', srprop: 'snippet' }),
  )
  return (data?.query?.search ?? []).map((s) => ({ title: s.title, snippet: plainText(s.snippet) }))
}

export async function articleSummary(lang: string, title: string): Promise<ArticleSummary | null> {
  const s = await getJson<{
    title: string; displaytitle: string; description?: string; extract?: string; thumbnail?: { source: string }
    wikibase_item?: string; content_urls?: { desktop?: { page?: string } }
  }>(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${enc(title)}`)
  if (!s) return null
  return {
    title: s.title, displaytitle: plainText(s.displaytitle), description: s.description, extract: s.extract,
    thumbnail: s.thumbnail, wikibase_item: s.wikibase_item,
    url: s.content_urls?.desktop?.page ?? `https://${lang}.wikipedia.org/wiki/${enc(title)}`,
  }
}

/** Título del mismo artículo en cada idioma analizado (enlaces interlingüísticos), siguiendo redirecciones. */
export async function titlesByLang(lang: string, title: string): Promise<Record<string, string>> {
  const data = await getJson<{ query?: { pages?: { title: string; missing?: boolean; langlinks?: { lang: string; title: string }[] }[] } }>(
    action(lang, { action: 'query', prop: 'langlinks', titles: title, redirects: '1', lllimit: 'max' }),
  )
  const page = data?.query?.pages?.[0]
  if (!page || page.missing) return {}
  const out: Record<string, string> = { [lang]: page.title }
  for (const l of page.langlinks ?? []) if (LANGS.includes(l.lang)) out[l.lang] = l.title
  return out
}

const ymd = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '')

/** Visitas de personas (agent=user) de un artículo, mensuales desde 2015-07 o diarias de los últimos 365 días. */
export async function pageviews(lang: string, title: string, daily: boolean): Promise<Map<string, number>> {
  const now = new Date()
  let start: string, end: string
  if (daily) {
    const e = new Date(now.getTime() - 2 * 86400e3)
    end = ymd(e)
    start = ymd(new Date(e.getTime() - 364 * 86400e3))
  } else {
    start = '20150701'
    end = ymd(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0)))
  }
  const url = `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/${lang}.wikipedia/all-access/user/${enc(title)}/${daily ? 'daily' : 'monthly'}/${start}00/${end}00`
  const data = await getJson<{ items?: { timestamp: string; views: number }[] }>(url)
  const m = new Map<string, number>()
  for (const it of data?.items ?? []) {
    const t = it.timestamp
    m.set(daily ? `${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)}` : `${t.slice(0, 4)}-${t.slice(4, 6)}`, it.views)
  }
  return m
}

/** Junta las series de varios idiomas en el formato que usa el gráfico (fechas comunes; días sin visitas = 0). */
export function toPayload(series: Record<string, Map<string, number>>, daily: boolean): SeriesPayload | null {
  const keys = new Set<string>()
  for (const m of Object.values(series)) for (const k of m.keys()) keys.add(k)
  if (!keys.size) return null
  const sorted = [...keys].sort()
  // Fechas continuas entre la primera y la última.
  const fechas: string[] = []
  const d = new Date(sorted[0] + (daily ? 'T00:00:00Z' : '-01T00:00:00Z'))
  const last = sorted[sorted.length - 1]
  for (;;) {
    const k = daily ? d.toISOString().slice(0, 10) : d.toISOString().slice(0, 7)
    fechas.push(k)
    if (k >= last) break
    if (daily) d.setUTCDate(d.getUTCDate() + 1)
    else d.setUTCMonth(d.getUTCMonth() + 1)
  }
  const out: SeriesPayload['series'] = {}
  for (const [lang, m] of Object.entries(series)) {
    const first = [...m.keys()].sort()[0]
    out[lang] = fechas.map((f) => (f < first ? null : m.get(f) ?? 0))
  }
  return { inicio: fechas[0], fechas, series: out }
}

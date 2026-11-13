// «Revisar un artículo»: el análisis de «Bajo disputa» para cualquier artículo y período, calculado EN VIVO
// en el navegador con las mismas reglas que el ranking diario (lib/disputeRules.ts). Las peticiones van una a
// la vez (cola de lib/wikipedia.ts) y quedan en caché en memoria.

import type { DisputeArticle } from '../api'
import * as R from './disputeRules'
import { action, enc, getJson } from './wikipedia'

export const MAX_DAYS = 366
const HABITUAL_DAYS = 90
const REV_PAGES = 40       // hasta 20.000 ediciones
const DIFF_DAYS = 3
const DIFFS_PER_DAY = 10
const TOP_DAYS = 5

type Query<T> = { query?: T; continue?: Record<string, string> }

export type LiveResult = DisputeArticle & { periodo: { inicio: string; fin: string }; cortado: boolean }

async function canonical(lang: string, title: string): Promise<string | null> {
  const d = await getJson<Query<{ pages?: { title: string; missing?: boolean }[] }>>(
    action(lang, { action: 'query', titles: title, redirects: '1' }))
  const p = d?.query?.pages?.[0]
  return p && !p.missing ? p.title : null
}

async function revisions(lang: string, title: string, from: string, toExcl: string, progress: (s: string) => void) {
  const out: R.Rev[] = []
  let cont: Record<string, string> = {}
  for (let i = 0; i < REV_PAGES; i++) {
    const d = await getJson<Query<{ pages?: { revisions?: R.Rev[] }[] }>>(action(lang, {
      action: 'query', prop: 'revisions', titles: title, rvprop: 'ids|timestamp|user|tags|comment|size', rvlimit: 'max',
      rvstart: `${toExcl}T00:00:00Z`, rvend: `${from}T00:00:00Z`, ...cont,
    }))
    out.push(...(d?.query?.pages?.[0]?.revisions ?? []))
    progress(`Descargando el historial… ${out.length.toLocaleString('es')} ediciones`)
    if (!d?.continue) return { revs: out.reverse(), complete: true }
    cont = d.continue
  }
  return { revs: out.reverse(), complete: false }
}

async function protectionLog(lang: string, title: string, from: string, toExcl: string) {
  const d = await getJson<Query<{ logevents?: R.LogEvent[] }>>(action(lang, {
    action: 'query', list: 'logevents', letype: 'protect', letitle: title, lelimit: '100',
    lestart: `${toExcl}T00:00:00Z`, leend: `${from}T00:00:00Z`,
  }))
  return d?.query?.logevents ?? []
}

async function views(lang: string, title: string, from: string, to: string): Promise<Record<string, number>> {
  if (to < '2015-07-01') return {}
  const s = (from < '2015-07-01' ? '2015-07-01' : from).replace(/-/g, '')
  const url = `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/${lang}.wikipedia/all-access/user/${enc(title)}/daily/${s}00/${to.replace(/-/g, '')}00`
  try {
    const d = await getJson<{ items?: { timestamp: string; views: number }[] }>(url)
    const out: Record<string, number> = {}
    for (const it of d?.items ?? []) out[`${it.timestamp.slice(0, 4)}-${it.timestamp.slice(4, 6)}-${it.timestamp.slice(6, 8)}`] = it.views
    return out
  } catch {
    return {}
  }
}

async function diff(lang: string, r: R.Rev): Promise<[string[], string[]] | null> {
  if (!r.parentid) return null
  try {
    const d = await getJson<{ compare?: { body?: string } }>(action(lang, { action: 'compare', fromrev: String(r.parentid), torev: String(r.revid), prop: 'diff' }))
    return d?.compare?.body != null ? R.parseDiff(d.compare.body) : null
  } catch {
    return null
  }
}

const n = (x: number, d = 1) => x.toFixed(d).replace('.', ',')

function summary(s: R.Score, start: string, end: string, created: string | null): string {
  const len = Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1
  const obs = `Entre el ${start} y el ${end} (${len} días): ${s.revertidas_semana} de ${s.ediciones_semana} ediciones fueron revertidas después.`
  if (s.nuevo) return `${obs} El artículo se creó el ${created}, dentro del período: no hay días anteriores para comparar.`
  if (s.habitual_por_dia === null) return `${obs} No hay días anteriores para comparar.`
  if (!s.habitual_por_dia) return `${obs} En los ${s.dias_comparados} días anteriores no hubo ninguna edición revertida.`
  return `${obs} Lo habitual en los ${s.dias_comparados} días anteriores: ${n(s.habitual_por_dia, 2)} por día, es decir ` +
    `${n(s.esperadas_semana)} en ${len} días. En el período hubo ${n(s.veces ?? 0)} veces lo habitual.`
}

/** Analiza un artículo entre start y end (AAAA-MM-DD, inclusive) contra los 90 días anteriores. */
export async function analyzeArticle(lang: string, query: string, start: string, end: string, progress: (s: string) => void): Promise<LiveResult> {
  progress('Buscando el artículo…')
  const title = await canonical(lang, query)
  if (!title) throw new Error(`No existe «${query}» en ${lang}.wikipedia.`)
  const histStart = R.addDays(start, -HABITUAL_DAYS)
  const endExcl = R.addDays(end, 1)
  const { revs, complete } = await revisions(lang, title, histStart, endExcl, progress)
  const s = R.scoreArticle(revs, start, end, complete, histStart)
  const days = R.disputedDays(revs, start, end, s.habitual_por_dia, TOP_DAYS)
  const byDay = new Map(days.map((d) => [d, revs.filter((r) => r.timestamp.slice(0, 10) === d)]))
  const diffs = new Map<number, [string[], string[]]>()
  const toRead = [...days].sort((a, b) => byDay.get(b)!.filter(R.isReverted).length - byDay.get(a)!.filter(R.isReverted).length).slice(0, DIFF_DAYS)
  let done = 0
  const total = toRead.reduce((t, d) => t + Math.min(DIFFS_PER_DAY, byDay.get(d)!.filter(R.isReverted).length), 0)
  for (const d of toRead) {
    for (const r of byDay.get(d)!.filter(R.isReverted).slice(0, DIFFS_PER_DAY)) {
      progress(`Leyendo lo que cambiaron las ediciones revertidas… ${++done} de ${total}`)
      const got = await diff(lang, r)
      if (got) diffs.set(r.revid, got)
    }
  }
  progress('Descargando protecciones y visitas…')
  const chartStart = R.addDays(start, -30)
  const [log, vw] = await Promise.all([protectionLog(lang, title, histStart, endExcl), views(lang, title, chartStart, end)])
  return {
    id: `live:${lang}:${title}`,
    titulo: title,
    idioma: lang,
    enlace: R.wikiUrl(lang, title),
    historial: R.historyUrl(lang, title),
    registro_protecciones: R.protectLogUrl(lang, title),
    ...s,
    historial_completo: complete,
    resumen: summary(s, start, end, s.creado),
    dias_disputa: days.map((d) => R.describeDay(d, byDay.get(d)!, diffs, lang)),
    protecciones: R.protectionsIn(log, histStart),
    serie: R.series(revs, vw, chartStart, end),
    periodo: { inicio: start, fin: end },
    cortado: !complete,
  }
}

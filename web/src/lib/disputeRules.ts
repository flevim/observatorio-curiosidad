// Reglas de «Bajo disputa», copia exacta de pipeline/src/observatorio/analysis/disputes.py.
// Sin DOM ni dependencias: tests/test_disputes.py ejecuta este archivo con Node sobre el mismo caso
// que usa Python y exige los mismos números. Si cambias una regla, cámbiala en los dos lados.

export const MIN_REVERTED = 8
export const MIN_SCORE = 3.0
const REVERT_TAGS = new Set(['mw-undo', 'mw-rollback', 'mw-manual-revert'])
const SECTION_RE = /\/\*\s*(.+?)\s*\*\//g
const FRAG_MAX = 220

export type Rev = {
  revid: number; parentid?: number; timestamp: string; user?: string; tags?: string[]; comment?: string
  anon?: boolean; temp?: boolean
}
export type Frag = { texto: string; veces: number }
export type Score = {
  revertidas_semana: number; ediciones_semana: number; habitual_por_dia: number | null; dias_comparados: number
  esperadas_semana: number; veces: number | null; puntaje: number; creado: string | null; nuevo: boolean; entra: boolean
}
export type Day = {
  dia: string; ediciones: number; revertidas: number; reversiones: number; minutos: number; editores: number; sin_cuenta: number
  secciones: { seccion: string; ediciones: number }[]; entraba: Frag[]; salia: Frag[]; diffs_revisados: number
  frases: string[]; enlaces: { hora: string; url: string }[]
}

const day = (ts: string) => ts.slice(0, 10)
const round = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d
const daysBetween = (a: string, b: string) => Math.round((Date.parse(a + 'T00:00:00Z') - Date.parse(b + 'T00:00:00Z')) / 86400000)
export const addDays = (iso: string, n: number) => new Date(Date.parse(iso + 'T00:00:00Z') + n * 86400000).toISOString().slice(0, 10)

export const wikiUrl = (lang: string, title: string) => `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`
export const diffUrl = (lang: string, r: Rev) => `https://${lang}.wikipedia.org/w/index.php?diff=${r.revid}&oldid=${r.parentid ?? 0}`
export const historyUrl = (lang: string, title: string) =>
  `https://${lang}.wikipedia.org/w/index.php?title=${encodeURIComponent(title.replace(/ /g, '_'))}&action=history`
export const protectLogUrl = (lang: string, title: string) =>
  `https://${lang}.wikipedia.org/w/index.php?title=Special:Log&type=protect&page=${encodeURIComponent(title.replace(/ /g, '_'))}`

export const isReverted = (r: Rev) => (r.tags ?? []).includes('mw-reverted')
export const isRevert = (r: Rev) => (r.tags ?? []).some((t) => REVERT_TAGS.has(t))
export const isAnonymous = (r: Rev) => !!(r.anon || r.temp || String(r.user ?? '').startsWith('~'))

type Counts = { ediciones: number; revertidas: number; reversiones: number }
export function dailyCounts(revs: Rev[]): Map<string, Counts> {
  const out = new Map<string, Counts>()
  for (const r of revs) {
    const k = day(r.timestamp)
    const c = out.get(k) ?? { ediciones: 0, revertidas: 0, reversiones: 0 }
    c.ediciones++
    c.revertidas += +isReverted(r)
    c.reversiones += +isRevert(r)
    out.set(k, c)
  }
  return out
}

/** Compara las revertidas del período [start, end] con lo habitual del artículo antes del período. */
export function scoreArticle(revs: Rev[], start: string, end: string, complete: boolean, histStart: string): Score {
  const period = revs.filter((r) => start <= day(r.timestamp) && day(r.timestamp) <= end)
  const before = revs.filter((r) => day(r.timestamp) < start)
  const obs = period.filter(isReverted).length
  let first = histStart
  if (!complete && revs.length) {
    const oldest = revs.map((r) => day(r.timestamp)).sort()[0]
    first = oldest > histStart ? oldest : histStart
  }
  const created = complete && revs.length && !revs[0].parentid ? day(revs[0].timestamp) : null
  if (created && created > first) first = created
  const baseDays = Math.max(0, daysBetween(start, first))
  const habitual = baseDays ? before.filter(isReverted).length / baseDays : null
  const len = daysBetween(end, start) + 1
  const expected = habitual !== null ? len * habitual : 0
  const score = (obs - expected) / Math.sqrt(expected + 1)
  return {
    revertidas_semana: obs,
    ediciones_semana: period.length,
    habitual_por_dia: habitual === null ? null : round(habitual, 2),
    dias_comparados: baseDays,
    esperadas_semana: round(expected, 1),
    veces: expected ? round(obs / expected, 1) : null,
    puntaje: round(score, 2),
    creado: created,
    nuevo: !!(created && created >= start),
    entra: obs >= MIN_REVERTED && score >= MIN_SCORE && obs >= 3 * expected,
  }
}

export function disputedDays(revs: Rev[], start: string, end: string, habitual: number | null, top = 3): string[] {
  const counts = dailyCounts(revs)
  const h = habitual ?? 0
  const days = [...counts.entries()]
    .filter(([d, c]) => start <= d && d <= end && c.revertidas >= 3 && c.revertidas >= 3 * h + 2)
    .map(([d]) => d)
  return days.sort((a, b) => counts.get(b)!.revertidas - counts.get(a)!.revertidas).slice(0, top).sort()
}

// ---------------- diffs

const CELL_RE = /<td class="(diff-addedline|diff-deletedline)[^"]*"[^>]*>([\s\S]*?)<\/td>/g
const INLINE_RE = /<(ins|del) class="diffchange[^"]*">([\s\S]*?)<\/\1>/g
const TAG_RE = /<[^>]+>/g
const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }

function unescapeHtml(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10))
    return ENTITIES[e.toLowerCase()] ?? m
  })
}

function clean(s: string): string {
  const t = unescapeHtml(s.replace(TAG_RE, '')).replace(/\s+/g, ' ').trim()
  const cps = [...t]
  return cps.length <= FRAG_MAX ? t : cps.slice(0, FRAG_MAX - 1).join('') + '…'
}

/** Fragmentos agregados y quitados de un diff HTML de MediaWiki (mismas reglas que Python). */
export function parseDiff(body: string): [string[], string[]] {
  const added: string[] = [], removed: string[] = []
  for (const [, kind, cell] of (body ?? '').matchAll(CELL_RE)) {
    const target = kind === 'diff-addedline' ? added : removed
    const inline = [...cell.matchAll(INLINE_RE)].map((m) => m[2])
    for (const p of inline.length ? inline : [cell]) {
      const t = clean(p)
      if ([...t].length >= 2 && /[\p{L}\p{N}_]/u.test(t)) target.push(t)
    }
  }
  return [added, removed]
}

function mostCommon(items: string[], k: number): [string, number][] {
  const m = new Map<string, number>()
  for (const i of items) m.set(i, (m.get(i) ?? 0) + 1)
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, k)
}
export const topFragments = (items: string[], k = 4): Frag[] => mostCommon(items, k).map(([texto, veces]) => ({ texto, veces }))

const n1 = (x: number, d = 1) => x.toFixed(d).replace('.', ',')
function span(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = minutes / 60
  return h >= 3 ? `${h.toFixed(0)} h` : `${n1(h)} h`
}

export function describeDay(d: string, revsDay: Rev[], diffs: Map<number, [string[], string[]]>, lang: string): Day {
  const reverted = revsDay.filter(isReverted)
  const times = reverted.map((r) => Date.parse(r.timestamp)).sort((a, b) => a - b)
  const minutes = times.length > 1 ? Math.floor((times[times.length - 1] - times[0]) / 60000) : 0
  const editors = new Set(reverted.map((r) => r.user))
  const anon = new Set(reverted.filter(isAnonymous).map((r) => r.user))
  const sections = mostCommon(revsDay.flatMap((r) => [...(r.comment ?? '').matchAll(SECTION_RE)].map((m) => m[1])), 3)
  const added = reverted.flatMap((r) => diffs.get(r.revid)?.[0] ?? [])
  const removed = reverted.flatMap((r) => diffs.get(r.revid)?.[1] ?? [])
  const revisadas = reverted.filter((r) => diffs.has(r.revid)).length

  const frases = [`${revsDay.length} ediciones; ${reverted.length} fueron revertidas después` + (minutes ? `, en un lapso de ${span(minutes)}` : '') + '.']
  frases.push(`Las revertidas vienen de ${editors.size} ${editors.size === 1 ? 'editor' : 'editores'}`
    + (anon.size ? `, ${anon.size} sin cuenta (IP o cuenta temporal).` : ', todos con cuenta.'))
  if (sections.length) {
    const [s, n] = sections[0]
    frases.push(`Sección más tocada ese día: «${s}» (${n} ${n === 1 ? 'edición' : 'ediciones'}).`)
  }
  const ent = topFragments(added, 3), sal = topFragments(removed, 3)
  const fr = (f: Frag) => `«${f.texto}»` + (f.veces > 1 ? ` (${f.veces} veces)` : '')
  if (ent.length) frases.push('Entraba: ' + ent.map(fr).join('; ') + '.')
  if (sal.length) frases.push('Salía: ' + sal.map(fr).join('; ') + '.')
  return {
    dia: d, ediciones: revsDay.length, revertidas: reverted.length, reversiones: revsDay.filter(isRevert).length, minutos: minutes,
    editores: editors.size, sin_cuenta: anon.size,
    secciones: sections.map(([seccion, ediciones]) => ({ seccion, ediciones })),
    entraba: ent, salia: sal, diffs_revisados: revisadas, frases,
    enlaces: reverted.slice(0, 20).map((r) => ({ hora: r.timestamp.slice(11, 16), url: diffUrl(lang, r) })),
  }
}

const PROTECT_ACTIONS: Record<string, string> = {
  protect: 'protegido', modify: 'cambio de protección', unprotect: 'desprotegido', move_prot: 'protección trasladada con el título',
}
export type LogEvent = { timestamp: string; action?: string; comment?: string; params?: { description?: string } }
export function protectionsIn(log: LogEvent[], since: string) {
  return log.filter((e) => (e.timestamp ?? '').slice(0, 10) >= since).map((e) => ({
    fecha: e.timestamp.slice(0, 16).replace('T', ' '),
    accion: PROTECT_ACTIONS[e.action ?? ''] ?? e.action ?? '',
    nivel: (e.params?.description ?? '').replace(/‎/g, ' ').trim(),
    motivo: e.comment ?? '',
  }))
}

export function series(revs: Rev[], views: Record<string, number>, start: string, end: string): [string, number, number, number | null][] {
  const counts = dailyCounts(revs)
  const out: [string, number, number, number | null][] = []
  for (let d = start; d <= end; d = addDays(d, 1)) {
    const c = counts.get(d)
    out.push([d, c?.ediciones ?? 0, c?.revertidas ?? 0, views[d] ?? null])
  }
  return out
}

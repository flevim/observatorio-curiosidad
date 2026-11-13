import { useEffect, useMemo, useRef, useState } from 'react'
import type { DisputeArticle, DisputeEdit, Disputes, Fragment } from '../api'
import { dateLabel, lang, num } from '../lib/format'
import { analyzeArticle, diffRows, MAX_DAYS, type DiffRow, type LiveResult, type Seg } from '../lib/disputeLive'
import { addDays } from '../lib/disputeRules'
import { LANGS, searchWikipedia } from '../lib/wikipedia'

/** Casos mediáticos para probar: artículo, idioma y un período alrededor del momento clave. */
const EJEMPLOS = [
  { lang: 'es', titulo: 'Elección presidencial de Chile de 2025', inicio: '2025-09-01', fin: '2026-01-31' },
  { lang: 'es', titulo: 'José Antonio Kast', inicio: '2025-09-01', fin: '2026-01-31' },
  { lang: 'es', titulo: 'Jeannette Jara', inicio: '2025-09-01', fin: '2026-01-31' },
  { lang: 'en', titulo: '2024 United States presidential election', inicio: '2024-07-01', fin: '2024-12-31' },
  { lang: 'en', titulo: 'Kamala Harris', inicio: '2024-07-01', fin: '2024-12-31' },
  { lang: 'en', titulo: '2020 United States presidential election', inicio: '2020-10-01', fin: '2021-01-31' },
]
const yesterday = () => addDays(new Date().toISOString().slice(0, 10), -1)

type Initial = { lang: string; titulo: string; inicio: string | null; fin: string | null }
/** Búsqueda guardada en el enlace: #vista=disputa&art=es:Título&desde=AAAA-MM-DD&hasta=AAAA-MM-DD */
function readShared(): Initial | null {
  const p = new URLSearchParams(location.hash.slice(1))
  const art = p.get('art')
  const i = art?.indexOf(':') ?? -1
  if (!art || i < 1) return null
  return { lang: art.slice(0, i), titulo: art.slice(i + 1), inicio: p.get('desde'), fin: p.get('hasta') }
}
function writeShared(r: LiveResult | null) {
  const p = new URLSearchParams(location.hash.slice(1))
  if (r) {
    p.set('art', `${r.idioma}:${r.titulo}`); p.set('desde', r.periodo.inicio); p.set('hasta', r.periodo.fin)
  } else {
    p.delete('art'); p.delete('desde'); p.delete('hasta')
  }
  history.replaceState(null, '', `#${p}`)
}

const fmtDay = (iso: string) => dateLabel(iso.slice(0, 10))
const veces = (a: DisputeArticle) =>
  a.nuevo ? 'artículo nuevo' : a.veces ? `${num(a.veces, 1)} × lo habitual` : 'antes: ninguna revertida'

/** Sección «Bajo disputa»: ranking automático de artículos con más ediciones revertidas de lo habitual. */
export default function DisputeView({ data }: { data: Disputes }) {
  const [filter, setFilter] = useState<string>('todos')
  const [selId, setSelId] = useState<string | null>(null)
  const items = useMemo(() => data.articulos.filter((a) => filter === 'todos' || a.idioma === filter), [data, filter])
  const ranked = items.filter((a) => !a.nuevo)
  const nuevos = items.filter((a) => a.nuevo)
  const [live, setLiveState] = useState<LiveResult | null>(null)
  const [copied, setCopied] = useState(false)
  const initial = useMemo(readShared, [])
  const setLive = (r: LiveResult | null) => { setLiveState(r); setCopied(false); writeShared(r) }
  const sel = items.find((a) => a.id === selId) ?? ranked[0] ?? nuevos[0] ?? null
  const langs = data.idiomas.filter((l) => data.articulos.some((a) => a.idioma === l))

  const toDetail = () => {
    if (window.matchMedia('(max-width: 767px)').matches) document.getElementById('disp-detail')?.scrollIntoView({ block: 'start' })
  }
  const pick = (a: DisputeArticle) => {
    setLive(null)
    setSelId(a.id)
    if (window.matchMedia('(max-width: 767px)').matches) document.getElementById('disp-detail')?.scrollIntoView({ block: 'start' })
  }
  const row = (a: DisputeArticle) => (
    <li key={a.id}>
      <button className={a.id === sel?.id ? 'on' : ''} aria-pressed={a.id === sel?.id} onClick={() => pick(a)}>
        <span className="pp-title">{a.titulo}</span>
        <span className="pp-meta">{a.idioma} · {a.revertidas_semana} revertidas de {a.ediciones_semana} · {veces(a)}</span>
      </button>
    </li>
  )

  return (
    <div className="disp-view">
      <section className="disp-side" aria-labelledby="disp-title">
        <p className="kicker"><span className="rule" aria-hidden="true" />Semana del {fmtDay(data.semana.inicio)} al {fmtDay(data.semana.fin)} · UTC</p>
        <h2 id="disp-title" className="prop-side-title">Bajo <em>disputa</em></h2>
        <p className="hero-lede">Artículos de Wikipedia con muchas más ediciones revertidas de lo habitual. Todo sale de datos públicos y cada número enlaza a su fuente.</p>
        <LiveSearch initial={initial} onResult={(r) => { setLive(r); toDetail() }} />
        <h3 className="disp-sub">Ranking de la semana</h3>
        <div className="seg disp-langs" role="group" aria-label="Idioma">
          {['todos', ...langs].map((l) => (
            <button key={l} aria-pressed={filter === l} onClick={() => setFilter(l)}>{l === 'todos' ? 'Todos' : l}</button>
          ))}
        </div>
        {ranked.length > 0 ? <ol className="prop-pick disp-pick">{ranked.map(row)}</ol>
          : <p className="hint">Esta semana ningún artículo superó las reglas en este idioma.</p>}
        {nuevos.length > 0 && (
          <>
            <h3 className="disp-sub">Creados esta semana</h3>
            <p className="muted small">No tienen días anteriores con qué comparar; se ordenan por cantidad de revertidas.</p>
            <ol className="prop-pick disp-pick">{nuevos.map(row)}</ol>
          </>
        )}
        <details className="disp-method">
          <summary>Cómo se calcula</summary>
          <ul>
            <li>Una edición <b>revertida</b> es la que Wikipedia marcó después con la etiqueta <code>mw-reverted</code>: alguien la deshizo.</li>
            <li>Candidatos: los {data.reglas.candidatos_por_idioma} artículos con más ediciones revertidas en la semana (sin bots) en cada idioma: {data.idiomas.join(', ')}.</li>
            <li><b>Lo habitual</b> = ediciones revertidas por día en los días anteriores a la semana (hasta 83). Esperadas = 7 × lo habitual. En «Revisar un artículo», lo habitual son los 90 días anteriores al período elegido y las esperadas se multiplican por los días del período.</li>
            <li>Entra al ranking si tuvo al menos {data.reglas.min_revertidas} revertidas, al menos el triple de las esperadas y un puntaje ≥ {num(data.reglas.min_puntaje, 0)}. Puntaje = (observadas − esperadas) / √(esperadas + 1).</li>
            <li><b>Día en disputa</b>: ≥ 3 revertidas y ≥ 3 × lo habitual + 2.</li>
            <li><b>Entraba / salía</b>: texto que las ediciones revertidas agregaban o quitaban, copiado tal cual del diff de hasta {data.reglas.diffs_por_dia} ediciones por día. Se cuentan repeticiones exactas.</li>
            <li>Las protecciones y sus motivos se copian textuales del registro de Wikipedia.</li>
            <li>Mide conflicto, no intención: no sabemos quién editó ni si hubo coordinación.</li>
          </ul>
          <p className="muted small">Actualizado {data.generado.replace('T', ' ').slice(0, 16)} UTC.{data.avisos.map((a) => ` ${a}`).join('')}</p>
        </details>
      </section>

      <section id="disp-detail" className="disp-detail" aria-live="polite">
        {live ? (
          <>
            <p className="disp-live-head">
              <span>Tu búsqueda · calculado en vivo con datos de Wikipedia</span>
              <span className="disp-live-actions">
                <button className="link" onClick={() => navigator.clipboard?.writeText(location.href).then(() => setCopied(true), () => {})}>
                  {copied ? 'Enlace copiado' : 'Copiar enlace'}
                </button>
                <button className="link" onClick={() => setLive(null)}>Volver al ranking</button>
              </span>
            </p>
            {live.cortado && <p className="muted small">El artículo tiene tantas ediciones que el historial se cortó en las 20.000 más recientes: lo habitual se calcula con lo descargado.</p>}
            <Detail a={live} semana={live.periodo} protLabel="Protecciones en el período y los 90 días anteriores" />
          </>
        ) : sel ? <Detail a={sel} semana={data.semana} /> : <p className="hint">Sin artículos para mostrar.</p>}
      </section>
    </div>
  )
}

function LiveSearch({ onResult, initial }: { onResult: (r: LiveResult) => void; initial: Initial | null }) {
  const [lng, setLng] = useState(initial?.lang ?? 'es')
  const [q, setQ] = useState(initial?.titulo ?? '')
  const [hits, setHits] = useState<string[]>([])
  const [mode, setMode] = useState<'90' | 'fechas'>('90')
  const [start, setStart] = useState(addDays(yesterday(), -89))
  const [end, setEnd] = useState(yesterday())
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const typed = useRef(false)
  const ranInitial = useRef(false)

  useEffect(() => {
    if (!typed.current || q.trim().length < 2) { setHits([]); return }
    const t = setTimeout(() => {
      searchWikipedia(lng, q.trim()).then((h) => setHits(h.slice(0, 6).map((x) => x.title)), () => setHits([]))
    }, 350)
    return () => clearTimeout(t)
  }, [q, lng])

  const run = async (title: string, l = lng, s0 = mode === '90' ? addDays(yesterday(), -89) : start, e0 = mode === '90' ? yesterday() : end) => {
    if (!title.trim()) { setError('Escribe el nombre de un artículo.'); return }
    if (s0 > e0) { setError('La fecha de inicio debe ser anterior a la de término.'); return }
    if ((Date.parse(e0) - Date.parse(s0)) / 86400000 + 1 > MAX_DAYS) { setError(`El período puede durar hasta ${MAX_DAYS} días.`); return }
    if (e0 > yesterday()) { setError('El período debe terminar a más tardar ayer.'); return }
    setError(null); setHits([]); typed.current = false
    try {
      onResult(await analyzeArticle(l, title.trim(), s0, e0, setBusy))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar Wikipedia.')
    } finally {
      setBusy(null)
    }
  }

  // Enlace compartido: se repite la búsqueda guardada en la URL al abrir la página.
  useEffect(() => {
    if (!initial || ranInitial.current) return
    ranInitial.current = true
    const okDate = (d: string | null) => !!d && /^\d{4}-\d{2}-\d{2}$/.test(d)
    if (okDate(initial.inicio) && okDate(initial.fin)) {
      setMode('fechas'); setStart(initial.inicio!); setEnd(initial.fin!)
      run(initial.titulo, initial.lang, initial.inicio!, initial.fin!)
    } else run(initial.titulo, initial.lang)
  })

  return (
    <form className="disp-search" onSubmit={(e) => { e.preventDefault(); run(q) }} aria-label="Revisar un artículo">
      <h3 className="disp-sub">Revisar un artículo</h3>
      <div className="disp-search-row">
        <label className="sr-only" htmlFor="disp-lang">Idioma</label>
        <select id="disp-lang" value={lng} onChange={(e) => setLng(e.target.value)}>
          {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <label className="sr-only" htmlFor="disp-q">Artículo de Wikipedia</label>
        <input id="disp-q" type="search" placeholder="Artículo de Wikipedia" value={q} autoComplete="off"
          onChange={(e) => { typed.current = true; setQ(e.target.value) }} />
      </div>
      {hits.length > 0 && (
        <ul className="disp-hits" aria-label="Sugerencias">
          {hits.map((h) => <li key={h}><button type="button" className="link" onClick={() => { setQ(h); run(h) }}>{h}</button></li>)}
        </ul>
      )}
      <div className="seg disp-period" role="group" aria-label="Período">
        <button type="button" aria-pressed={mode === '90'} onClick={() => setMode('90')}>Últimos 90 días</button>
        <button type="button" aria-pressed={mode === 'fechas'} onClick={() => setMode('fechas')}>Elegir fechas</button>
      </div>
      {mode === 'fechas' && (
        <div className="disp-dates">
          <label>Desde <input type="date" value={start} min="2001-01-15" max={yesterday()} onChange={(e) => setStart(e.target.value)} /></label>
          <label>Hasta <input type="date" value={end} min="2001-01-15" max={yesterday()} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
      )}
      <button type="submit" className="ghost disp-go" disabled={!!busy}>{busy ? 'Revisando…' : 'Revisar'}</button>
      {busy && <p className="muted small" role="status">{busy}</p>}
      {error && <p className="disp-error" role="alert">{error}</p>}
      <p className="disp-ex-h">Casos mediáticos</p>
      <ul className="disp-ex">
        {EJEMPLOS.map((x) => (
          <li key={x.titulo}>
            <button type="button" className="link" disabled={!!busy} onClick={() => {
              setLng(x.lang); setQ(x.titulo); setMode('fechas'); setStart(x.inicio); setEnd(x.fin); run(x.titulo, x.lang, x.inicio, x.fin)
            }}>{x.titulo}</button>
            <span className="muted"> · {x.lang} · {x.inicio.slice(0, 7)} a {x.fin.slice(0, 7)}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">Se calcula en tu navegador con las mismas reglas del ranking, comparando el período con los 90 días anteriores. Un artículo muy editado puede tardar unos segundos.</p>
    </form>
  )
}

function Detail({ a, semana, protLabel = 'Protecciones en los últimos 90 días' }: { a: DisputeArticle; semana: Disputes['semana']; protLabel?: string }) {
  return (
    <article className="disp-article">
      <div className="disp-a">
      <p className="eyebrow">{lang(a.idioma)} · {a.idioma}.wikipedia</p>
      <h2 className="disp-title"><a href={a.enlace} target="_blank" rel="noreferrer">{a.titulo} ↗</a></h2>
      <p className="disp-summary">{a.resumen}</p>
      {a.pico && <p className="disp-summary">{a.pico.frase}</p>}
      <p className="disp-links">
        <a href={a.historial} target="_blank" rel="noreferrer">Historial completo ↗</a>
        <a href={a.registro_protecciones} target="_blank" rel="noreferrer">Registro de protecciones ↗</a>
      </p>

      <Chart a={a} semana={semana} />

      <h3>{protLabel}</h3>
      {a.protecciones.length === 0 ? <p className="muted">Ninguna.</p> : (
        <ul className="disp-prot">
          {a.protecciones.map((p, i) => (
            <li key={i}>
              <span className="disp-when">{p.fecha} UTC</span>
              <span><b>{p.accion}</b>{p.nivel ? <> · <code>{p.nivel}</code></> : null}</span>
              {p.motivo && <span className="disp-why">Motivo: «{p.motivo}»</span>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">Mide conflicto, no intención: no sabemos quién editó ni si hubo coordinación. Los motivos de protección los escriben los administradores de Wikipedia.</p>
      </div>

      <div className="disp-b">
      <h3>Días en disputa</h3>
      {a.dias_disputa.length === 0 && <p className="muted">Las revertidas se repartieron en la semana: ningún día cumple la regla de «día en disputa».</p>}
      {a.dias_disputa.map((d) => (
        <section key={d.dia} className="disp-day">
          <h4>{dateLabel(d.dia)}</h4>
          {d.frases.filter((f) => !f.startsWith('Entraba') && !f.startsWith('Salía')).map((f) => <p key={f}>{f}</p>)}
          {(d.entraba.length > 0 || d.salia.length > 0) && (
            <div className="disp-frags">
              {d.entraba.length > 0 && <Frags title="Entraba" items={d.entraba} />}
              {d.salia.length > 0 && <Frags title="Salía" items={d.salia} />}
              <p className="muted small">Texto tal cual, del diff de {d.diffs_revisados} de {d.revertidas} ediciones revertidas ese día.
                {a.version_actual ? ` «Hoy» = versión actual del artículo (${a.version_actual.fecha} UTC).` : ''}</p>
            </div>
          )}
          {d.diffs_revisados === 0 && d.revertidas > 0 && (
            <p className="muted small">El texto de este día no se revisó: solo se leen los diffs de los 2 días con más revertidas de cada artículo. Las ediciones están enlazadas abajo.</p>
          )}
          {d.enlaces.length > 0 && <EditList lang={a.idioma} edits={d.enlaces} total={d.revertidas} />}
        </section>
      ))}
      </div>
    </article>
  )
}

// ---------------- visor de modificaciones

const sign = (b: number) => (b > 0 ? `+${num(b)}` : b < 0 ? `−${num(-b)}` : '0')

/** Recorta el texto sin cambios de una línea larga, conservando los trozos marcados completos. */
function compact(segs: Seg[]): Seg[] {
  if (!segs.some((s) => s.m) || segs.every((s) => s.m)) {
    const t = segs.map((s) => s.t).join('')
    return t.length > 1500 ? [{ t: t.slice(0, 1500) + '…', m: segs[0]?.m ?? false }] : segs
  }
  return segs.map((s, i) => {
    if (s.m || s.t.length <= 200) return s
    if (i === 0) return { t: '…' + s.t.slice(-100), m: false }
    if (i === segs.length - 1) return { t: s.t.slice(0, 100) + '…', m: false }
    return { t: s.t.slice(0, 80) + ' … ' + s.t.slice(-80), m: false }
  })
}

function EditItem({ lang: lng, e }: { lang: string; e: DisputeEdit }) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<DiffRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && !rows && !err) {
      if (!e.parentid) { setErr('Es la primera versión del artículo: no hay versión anterior con qué comparar.'); return }
      diffRows(lng, e.parentid, e.revid).then(setRows, (x) => setErr(x instanceof Error ? x.message : 'No se pudo cargar la modificación.'))
    }
  }
  return (
    <li className={open ? 'open' : ''}>
      <button className="disp-edit-btn" aria-expanded={open} onClick={toggle}>
        <span className="disp-edit-meta">{e.hora} UTC · {e.sin_cuenta ? 'sin cuenta' : 'con cuenta'}{e.bytes !== null ? ` · ${sign(e.bytes)} bytes` : ''}</span>
        <span className="disp-edit-sum">{e.comentario ? `«${e.comentario}»` : 'sin resumen de edición'}</span>
      </button>
      {open && (
        <div className="disp-diff">
          {err && <p className="disp-error">{err}</p>}
          {!err && !rows && <p className="muted small" role="status">Cargando la modificación…</p>}
          {rows && rows.length === 0 && <p className="muted small">Esta edición no cambió el texto (por ejemplo, solo movió algo de lugar).</p>}
          {rows?.map((r, i) => r.tipo === 'linea' ? <p key={i} className="dl-line">{r.texto}</p>
            : r.tipo === 'contexto' ? (r.texto.trim() ? <p key={i} className="dl-ctx">{r.texto.length > 220 ? r.texto.slice(0, 220) + '…' : r.texto}</p> : null)
            : (
              <div key={i}>
                {r.antes && <p className="dl-del"><span className="dl-sign" aria-label="se quitó">−</span>{compact(r.antes).map((s, j) => s.m ? <del key={j}>{s.t}</del> : <span key={j}>{s.t}</span>)}</p>}
                {r.despues && <p className="dl-add"><span className="dl-sign" aria-label="se agregó">+</span>{compact(r.despues).map((s, j) => s.m ? <ins key={j}>{s.t}</ins> : <span key={j}>{s.t}</span>)}</p>}
              </div>
            ))}
          <p className="muted small">Diff de Wikipedia mostrado como texto (código fuente del artículo). <a href={e.url} target="_blank" rel="noreferrer">Verlo en Wikipedia ↗</a></p>
        </div>
      )}
    </li>
  )
}

function EditList({ lang: lng, edits, total }: { lang: string; edits: DisputeEdit[]; total: number }) {
  return (
    <div className="disp-edits">
      <p className="disp-frag-h">Ediciones revertidas ese día ({edits.length}{total > edits.length ? ` de ${total}` : ''}) · toca una para ver qué cambió</p>
      <ul>{edits.map((e) => <EditItem key={e.revid} lang={lng} e={e} />)}</ul>
    </div>
  )
}

function Frags({ title, items }: { title: string; items: Fragment[] }) {
  return (
    <div>
      <p className="disp-frag-h">{title}</p>
      <ul className="disp-frag-list">
        {items.map((f) => (
          <li key={f.texto}>
            <code>{f.texto}</code>{f.veces > 1 && <span className="muted"> × {f.veces}</span>}
            {f.hoy !== undefined && <span className={f.hoy ? 'disp-now yes' : 'disp-now no'}> · {f.hoy ? 'hoy está en el artículo' : 'hoy no está en el artículo'}</span>}
            {f.hoy && f.contexto && <details className="disp-ctx"><summary>dónde está</summary><p>{f.contexto}</p></details>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Visitas (arriba, escala raíz) y ediciones por día (abajo; en rosa, las revertidas después). */
function Chart({ a, semana }: { a: DisputeArticle; semana: Disputes['semana'] }) {
  const W = 640, X0 = 8, PW = W - 16, n = a.serie.length, bw = PW / n
  const vmax = Math.max(1, ...a.serie.map((s) => s[3] ?? 0))
  const emax = Math.max(1, ...a.serie.map((s) => s[1]))
  const x = (i: number) => X0 + i * bw
  const idx = (day: string) => a.serie.findIndex((s) => s[0] === day.slice(0, 10))
  let path = ''
  a.serie.forEach((s, i) => {
    if (s[3] == null) return
    path += `${path ? 'L' : 'M'}${(x(i) + bw / 2).toFixed(1)} ${(96 - 76 * Math.sqrt(s[3] / vmax)).toFixed(1)}`
  })
  const ws = idx(semana.inicio)
  const months = a.serie.map((s, i) => [s[0], i] as const).filter(([d]) => d.endsWith('-01'))
  const totalViews = a.serie.reduce((t, s) => t + (s[3] ?? 0), 0)
  return (
    <figure className="disp-chart">
      <svg viewBox={`0 0 ${W} 250`} role="img" aria-label={`${a.titulo}: visitas y ediciones diarias en 90 días. Máximo de visitas ${num(vmax)} en un día; máximo de ediciones ${emax}.`}>
        {ws >= 0 && <rect x={x(ws)} y={10} width={(n - ws) * bw} height={210} className="disp-week" />}
        <text x={X0} y={20} className="disp-lbl">Visitas por día · máx. {num(vmax)}</text>
        <path d={path} className="disp-views" />
        <text x={X0} y={124} className="disp-lbl">Ediciones por día · máx. {emax}</text>
        {a.serie.map((s, i) => {
          if (!s[1]) return null
          const h = 82 * s[1] / emax, hr = 82 * s[2] / emax
          return (
            <g key={s[0]}>
              <rect x={x(i) + 0.3} y={218 - h} width={Math.max(1, bw - 0.6)} height={h - hr} className="disp-ed" />
              {s[2] > 0 && <rect x={x(i) + 0.3} y={218 - hr} width={Math.max(1, bw - 0.6)} height={hr} className="disp-rev" />}
            </g>
          )
        })}
        <line x1={X0} x2={X0 + PW} y1={218} y2={218} className="disp-axis" />
        {a.protecciones.map((p, i) => {
          const j = idx(p.fecha)
          return j < 0 ? null : <line key={i} x1={x(j) + bw / 2} x2={x(j) + bw / 2} y1={10} y2={218} className="disp-prot-line" />
        })}
        {months.map(([d, i]) => <text key={d} x={x(i)} y={238} className="disp-lbl">{dateLabel(d).split(' de ')[1] ?? d}</text>)}
      </svg>
      <figcaption className="disp-legend">
        <span><i className="sw ed" />edición que se quedó</span>
        <span><i className="sw rev" />revertida después</span>
        <span><i className="sw prot" />protección</span>
        <span><i className="sw week" />período analizado</span>
        <span className="muted">Visitas en el gráfico: {num(totalViews)} · escala raíz</span>
      </figcaption>
    </figure>
  )
}

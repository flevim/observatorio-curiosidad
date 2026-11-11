import { useEffect, useMemo, useState } from 'react'
import { api, STATIC, type SeriesPayload, type TopicSummary } from '../api'
import { lang as langName, num } from '../lib/format'
import {
  articleSummary, LANGS, pageviews, searchWikipedia, titlesByLang, toPayload,
  type ArticleSummary, type SearchHit,
} from '../lib/wikipedia'
import TimeSeriesChart, { HL_COLORS } from './TimeSeriesChart'

const REPO = import.meta.env.VITE_REPO_URL ?? 'https://github.com/flevim/observatorio-curiosidad'

type Props = {
  query: string
  topics: TopicSummary[]
  onTopic: (id: string) => void
  onClose: () => void
}

/** Búsqueda libre en Wikipedia con visitas en vivo. No es parte del análisis: se dice en la interfaz. */
export default function ExplorePanel({ query, topics, onTopic, onClose }: Props) {
  const [lang, setLang] = useState('es')
  const [q, setQ] = useState(query)
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [title, setTitle] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => setQ(query), [query])
  useEffect(() => {
    if (!q.trim()) return
    setHits(null)
    setErr(null)
    setTitle(null)
    searchWikipedia(lang, q.trim()).then(setHits, (e) => setErr(String(e.message ?? e)))
  }, [q, lang])

  return (
    <div className="panel-body">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Exploración en vivo · Wikipedia</p>
          <h2 id="panel-title">{title ?? `«${q}»`}</h2>
        </div>
        <button className="icon" onClick={onClose} aria-label="Cerrar exploración">×</button>
      </header>
      <p className="source">
        Consulta directa a Wikipedia y a la API de visitas de Wikimedia desde tu navegador. <strong>Datos en vivo, no analizados</strong>:
        sin picos, estacionalidad, relaciones ni datos por país, que solo existen para los temas del observatorio.
      </p>

      {title ? (
        <Article lang={lang} title={title} topics={topics} onTopic={onTopic} onBack={() => setTitle(null)} />
      ) : (
        <>
          <div className="controls-row">
            <label className="check">
              Buscar en{' '}
              <select value={lang} onChange={(e) => setLang(e.target.value)}>
                {LANGS.map((l) => <option key={l} value={l}>{langName(l)} ({l})</option>)}
              </select>
            </label>
          </div>
          <form className="explore-form" onSubmit={(e) => { e.preventDefault(); setQ(String(new FormData(e.currentTarget).get('q') ?? '')) }}>
            <label className="sr-only" htmlFor="explore-q">Buscar en Wikipedia</label>
            <input id="explore-q" name="q" defaultValue={q} key={q} placeholder="Buscar en Wikipedia" />
            <button className="ghost" type="submit">Buscar</button>
          </form>
          {err && <p role="alert">No se pudo consultar Wikipedia: {err}</p>}
          {!hits && !err && <p className="muted">Buscando en {langName(lang)}.wikipedia…</p>}
          {hits && !hits.length && <p className="muted">Sin resultados en {langName(lang)}. Prueba otro idioma o palabra.</p>}
          {hits && hits.length > 0 && (
            <ol className="hits">
              {hits.map((h) => (
                <li key={h.title}>
                  <button className="link strong" onClick={() => setTitle(h.title)}>{h.title}</button>
                  <p className="muted small">{h.snippet}…</p>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}

function Article({ lang, title, topics, onTopic, onBack }: {
  lang: string; title: string; topics: TopicSummary[]; onTopic: (id: string) => void; onBack: () => void
}) {
  const [summary, setSummary] = useState<ArticleSummary | null>(null)
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [daily, setDaily] = useState(false)
  const [log, setLog] = useState(false)
  const [series, setSeries] = useState<Record<string, Map<string, number>>>({})
  const [loading, setLoading] = useState<string | null>('Cargando artículo…')
  const [err, setErr] = useState<string | null>(null)
  const [proposal, setProposal] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setSummary(null); setTitles({}); setSeries({}); setErr(null); setLoading('Cargando artículo…')
    ;(async () => {
      const s = await articleSummary(lang, title)
      if (!alive) return
      setSummary(s)
      const t = await titlesByLang(lang, s?.title ?? title)
      if (!alive) return
      setTitles(t)
    })().catch((e) => alive && setErr(String(e.message ?? e)))
    return () => { alive = false }
  }, [lang, title])

  // Visitas de cada idioma, una consulta a la vez.
  useEffect(() => {
    const entries = Object.entries(titles)
    if (!entries.length) return
    let alive = true
    setSeries({})
    ;(async () => {
      const acc: Record<string, Map<string, number>> = {}
      for (const [i, [l, t]] of entries.entries()) {
        if (!alive) return
        setLoading(`Visitas: ${i + 1} de ${entries.length} idiomas…`)
        acc[l] = await pageviews(l, t, daily)
        if (alive) setSeries({ ...acc })
      }
      if (alive) setLoading(null)
    })().catch((e) => alive && (setErr(String(e.message ?? e)), setLoading(null)))
    return () => { alive = false }
  }, [titles, daily])

  const payload: SeriesPayload | null = useMemo(() => toPayload(series, daily), [series, daily])
  const highlight = ['es', 'en', ...(lang !== 'es' && lang !== 'en' ? [lang] : [])].filter((l) => l in series)
  const known = topics.find((t) => t.wikidata && t.wikidata === summary?.wikibase_item)
  const totals = Object.entries(series)
    .map(([l, m]) => {
      const vals = [...m.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([, v]) => v)
      return { l, total: vals.slice(daily ? -365 : -12).reduce((a, b) => a + b, 0) }
    })
    .sort((a, b) => b.total - a.total)

  const propose = async () => {
    if (!summary) return
    if (STATIC) return
    setProposal('Enviando…')
    try {
      const r = await api.addTopic({ nombre: summary.title, titulo: summary.title, idioma: lang })
      setProposal(`Agregado como «${r.tema}». La API lo está descargando y analizando; aparecerá en unos minutos.`)
    } catch (e) {
      setProposal(String((e as Error).message))
    }
  }
  const issueUrl = summary
    ? `${REPO}/issues/new?${new URLSearchParams({
        title: `Proponer tema: ${summary.title}`,
        body: `Propongo agregar este tema al observatorio.\n\n- Artículo: ${summary.url}\n- Idioma: ${lang}\n- Wikidata: ${summary.wikibase_item ?? '—'}\n\nLínea para config/topics.yaml:\n\n    - {id: …, nombre: ${summary.title}, ${summary.wikibase_item ? `wikidata: ${summary.wikibase_item}` : `semilla: {idioma: ${lang}, titulo: ${summary.title}}`}}`,
      })}`
    : REPO

  return (
    <div className="explore-article">
      <button className="ghost back-link" onClick={onBack}>← Resultados</button>
      {err && <p role="alert">No se pudo consultar Wikimedia: {err}</p>}
      {summary && (
        <>
          {summary.description && <p className="muted">{summary.description}</p>}
          <div className="summary-row">
            {summary.thumbnail && <img src={summary.thumbnail.source} alt="" className="thumb" loading="lazy" />}
            {summary.extract && <p className="extract">{summary.extract}</p>}
          </div>
          <ul className="f-links">
            <li><a href={summary.url} target="_blank" rel="noreferrer">Abrir en Wikipedia ↗</a></li>
            {summary.wikibase_item && (
              <li><a href={`https://www.wikidata.org/wiki/${summary.wikibase_item}`} target="_blank" rel="noreferrer">Wikidata {summary.wikibase_item} ↗</a></li>
            )}
          </ul>
          {known && (
            <p className="known">
              Este artículo es un tema del observatorio, con análisis completo y datos por país.{' '}
              <button className="link strong" onClick={() => onTopic(known.id)}>Ver «{known.nombre}»</button>
            </p>
          )}
        </>
      )}

      <h3>Visitas en Wikipedia</h3>
      <p className="source">
        Visitas de personas (agent=user) por edición de idioma · exactas · {daily ? 'diarias, últimos 365 días' : 'mensuales desde julio 2015'} ·
        Wikimedia, en vivo. No son visitas por país.
      </p>
      <div className="controls-row">
        <div className="seg" role="group" aria-label="Granularidad">
          <button aria-pressed={!daily} onClick={() => setDaily(false)}>Mensual</button>
          <button aria-pressed={daily} onClick={() => setDaily(true)}>Diaria · 365 días</button>
        </div>
        <label className="check"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> Escala log</label>
      </div>
      <div className="legend-row">
        {highlight.map((l, i) => <span key={l}><i className="sw" style={{ background: HL_COLORS[i] }} />{langName(l)}</span>)}
        <span><i className="sw" style={{ background: 'rgba(236,235,243,0.18)' }} />otros idiomas</span>
      </div>
      {payload ? (
        <TimeSeriesChart data={payload} daily={daily} highlight={highlight} log={log} label={`Visitas de ${title} por idioma`} />
      ) : !loading && <p className="muted">Sin visitas registradas.</p>}
      {loading && <p className="muted small" aria-live="polite">{loading}</p>}

      {totals.length > 0 && (
        <div className="scroll">
          <table>
            <thead><tr><th>Idioma</th><th>Artículo</th><th className="n">{daily ? 'Últimos 365 días' : 'Últimos 12 meses'}</th></tr></thead>
            <tbody>
              {totals.map(({ l, total }) => (
                <tr key={l}>
                  <td>{langName(l)}</td>
                  <td><a href={`https://${l}.wikipedia.org/wiki/${encodeURIComponent(titles[l].replace(/ /g, '_'))}`} target="_blank" rel="noreferrer" lang={l}>{titles[l]} ↗</a></td>
                  <td className="n">{num(total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {Object.keys(titles).length > 0 && Object.keys(titles).length < LANGS.length && (
        <p className="muted small">Sin artículo en: {LANGS.filter((l) => !(l in titles)).map(langName).join(', ')}.</p>
      )}

      {!known && summary && (
        <section className="placeholder">
          <h3>¿Analizarlo a fondo?</h3>
          <p className="muted small">
            Como tema del observatorio tendría tendencia, picos, vida media, estacionalidad, relaciones y presencia en los rankings por país,
            y se actualizaría cada día.
          </p>
          {STATIC ? (
            <a className="chip accent" href={issueUrl} target="_blank" rel="noreferrer">Proponer como tema ↗</a>
          ) : (
            <button className="chip accent" onClick={propose}>Agregar como tema</button>
          )}
          {proposal && <p className="muted small" role="status">{proposal}</p>}
        </section>
      )}
    </div>
  )
}

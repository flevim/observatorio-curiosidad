import { useEffect, useState } from 'react'
import { api, type Graph, type SeriesPayload, type TopicDetail } from '../api'
import { countryName, dateLabel, lang, MESES, num, pct, wikiUrl } from '../lib/format'
import RelatedGraph from './RelatedGraph'
import TimeSeriesChart, { HL_COLORS } from './TimeSeriesChart'

type Props = {
  topicId: string
  graph: Graph | null
  periodLabel: string
  onNavigate: (id: string) => void
  onClose: () => void
  onSelectCountry: (iso: string) => void
}

const days = (n: number) => `${num(n, 1)} ${n === 1 ? 'día' : 'días'}`

const trendTxt = { sube: 'sube', baja: 'baja', estable: 'se mantiene' } as const

export default function TopicPanel({ topicId, graph, periodLabel, onNavigate, onClose, onSelectCountry }: Props) {
  const [t, setT] = useState<TopicDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [daily, setDaily] = useState(false)
  const [dailyData, setDailyData] = useState<SeriesPayload | null>(null)
  const [log, setLog] = useState(false)
  const [compare, setCompare] = useState<string>('')
  const [peakLang, setPeakLang] = useState('todas')

  useEffect(() => {
    setT(null)
    setErr(null)
    setDailyData(null)
    api.topic(topicId).then(setT, (e) => setErr(String(e.message ?? e)))
  }, [topicId])
  useEffect(() => {
    if (daily && !dailyData) api.daily(topicId).then(setDailyData, (e) => setErr(String(e.message ?? e)))
  }, [daily, dailyData, topicId])

  if (err) return <div className="panel-body"><p role="alert">No se pudo cargar el tema: {err}</p></div>
  if (!t) return <div className="panel-body"><p className="muted">Cargando…</p></div>

  const all = t.por_idioma['todas']
  const langs = Object.keys(t.por_idioma).filter((l) => l !== 'todas')
  const highlight = ['es', 'en', compare].filter((l) => l && langs.includes(l))
  const peakM = t.por_idioma[peakLang] ?? all
  const tr = all?.tendencia
  const rtr = all?.tendencia_relativa
  const payload = daily ? dailyData : t.mensual
  const comp = t.comparacion_idiomas
  const es = comp.find((c) => c.idioma === 'es')

  return (
    <div className="panel-body">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Tema</p>
          <h2 id="panel-title">{t.nombre}</h2>
          {t.descripcion && <p className="muted">{t.descripcion}</p>}
        </div>
        <button className="icon" onClick={onClose} aria-label="Cerrar panel del tema">×</button>
      </header>

      <section aria-labelledby="h-serie">
        <h3 id="h-serie">Atención en el tiempo</h3>
        <p className="source">
          Visitas de personas por edición de idioma de Wikipedia · exactas · {daily ? 'diarias' : 'mensuales'}, jul 2015 – {all?.ultimo_dia.slice(0, 7)}.
          <strong> No son visitas por país.</strong>
        </p>
        <div className="controls-row">
          <div className="seg" role="group" aria-label="Granularidad">
            <button aria-pressed={!daily} onClick={() => setDaily(false)}>Mensual</button>
            <button aria-pressed={daily} onClick={() => setDaily(true)}>Diaria</button>
          </div>
          <label className="check"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> Escala log</label>
          <label className="check">
            Comparar con{' '}
            <select value={compare} onChange={(e) => setCompare(e.target.value)}>
              <option value="">—</option>
              {langs.filter((l) => l !== 'es' && l !== 'en').map((l) => <option key={l} value={l}>{lang(l)}</option>)}
            </select>
          </label>
        </div>
        <div className="legend-row">
          {highlight.map((l, i) => (
            <span key={l}><i className="sw" style={{ background: HL_COLORS[i] }} />{lang(l)}</span>
          ))}
          <span><i className="sw" style={{ background: 'rgba(236,232,224,0.18)' }} />otros idiomas</span>
        </div>
        {payload ? (
          <TimeSeriesChart
            data={payload}
            daily={daily}
            highlight={highlight}
            log={log}
            label={`Visitas ${daily ? 'diarias' : 'mensuales'} de ${t.nombre} por idioma`}
            markers={(all?.picos ?? []).slice(0, 5).map((p) => ({ date: p.fecha, label: `Pico ${dateLabel(p.fecha)}: ×${num(p.magnitud, 1)}` }))}
          />
        ) : (
          <p className="muted">Cargando serie diaria…</p>
        )}
        <p className="muted small">Líneas verticales: los 5 picos mayores (todos los idiomas). Usa ← → sobre el gráfico para recorrerlo con teclado.</p>
        {t.idiomas_sin_articulo.length > 0 && (
          <p className="muted small">Sin artículo en: {t.idiomas_sin_articulo.map(lang).join(', ')}.</p>
        )}
      </section>

      <section aria-labelledby="h-resumen">
        <h3 id="h-resumen">Resumen</h3>
        <dl className="stats">
          <div><dt>Tendencia (visitas)</dt><dd>{tr ? `${trendTxt[tr.clase]} (${tr.cambio_anual >= 0 ? '+' : '−'}${pct(Math.abs(tr.cambio_anual))}/año)` : '—'}</dd></div>
          <div>
            <dt>Tendencia relativa a Wikipedia</dt>
            <dd>{rtr ? `${trendTxt[rtr.clase]} (${rtr.cambio_anual >= 0 ? '+' : '−'}${pct(Math.abs(rtr.cambio_anual))}/año)` : '—'}</dd>
          </div>
          <div><dt>Visitas 12 meses</dt><dd>{num(all?.visitas_12m ?? 0)}</dd></div>
          <div><dt>Picos detectados</dt><dd>{all?.n_picos ?? 0}</dd></div>
          <div><dt>Vida media (mediana)</dt><dd>{all?.vida_media_mediana != null ? days(all.vida_media_mediana) : '—'}</dd></div>
          <div><dt>Vuelta a lo normal</dt><dd>{all?.vuelta_normalidad_mediana != null ? days(all.vuelta_normalidad_mediana) : '—'}</dd></div>
          <div>
            <dt>Estacionalidad</dt>
            <dd>{all?.estacionalidad?.estacional ? `sí, máximo en ${MESES[all.estacionalidad.mes_pico - 1]}` : 'no clara'}</dd>
          </div>
        </dl>
        {tr && (
          <p className="muted small">
            Tendencia: Theil-Sen + Mann-Kendall ({tr.p_valor < 0.001 ? 'p < 0,001' : `p = ${num(tr.p_valor, 2)}`}), {tr.desde} a {tr.hasta}.
            La relativa usa la proporción del tema sobre todas las visitas de sus ediciones, porque Wikipedia en conjunto también cambió de tamaño.
            {rtr && rtr.clase !== tr.clase && ` Aquí difieren: en visitas ${trendTxt[tr.clase]}, pero en proporción ${trendTxt[rtr.clase]}.`}
          </p>
        )}
      </section>

      <section aria-labelledby="h-picos">
        <h3 id="h-picos">Picos de atención</h3>
        <label className="check">
          Idioma{' '}
          <select value={peakLang} onChange={(e) => setPeakLang(e.target.value)}>
            <option value="todas">todos sumados</option>
            {langs.map((l) => <option key={l} value={l}>{lang(l)}</option>)}
          </select>
        </label>
        {peakM && peakM.picos.length ? (
          <div className="scroll">
            <table>
              <thead><tr><th>Fecha</th><th className="n">Visitas</th><th className="n">× normal</th><th className="n">Vida media</th><th className="n">Vuelta</th></tr></thead>
              <tbody>
                {peakM.picos.slice(0, 6).map((p) => (
                  <tr key={p.fecha}>
                    <td>{p.fecha}</td>
                    <td className="n">{num(p.visitas)}</td>
                    <td className="n">{num(p.magnitud, 1)}</td>
                    <td className="n">{p.vida_media_dias ?? '—'} d</td>
                    <td className="n">{p.vuelta_normalidad_dias == null ? 'no volvió' : `${p.vuelta_normalidad_dias} d`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">Sin picos detectados con el criterio actual.</p>}
        <p className="muted small">Vida media: días hasta que el exceso sobre lo normal cae a la mitad. Algunos picos pueden deberse a bots no filtrados.</p>
      </section>

      <section aria-labelledby="h-idiomas">
        <h3 id="h-idiomas">Comparación entre idiomas</h3>
        {es?.desfase && (
          <p>
            {es.desfase.informativo
              ? `El interés en español llega ${Math.abs(es.desfase.desfase_dias)} días ${es.desfase.desfase_dias > 0 ? 'después' : 'antes'} que en inglés (r = ${num(es.desfase.r_max, 2)}).`
              : `Las subidas y bajadas en español e inglés coinciden mejor el mismo día o no tienen un desfase claro (r = ${num(es.desfase.r_0, 2)}).`}
          </p>
        )}
        <div className="scroll">
          <table>
            <thead><tr><th>Idioma</th><th className="n">Visitas 12 m</th><th className="n">Peso relativo</th><th className="n">Desfase vs. inglés</th></tr></thead>
            <tbody>
              {langs.map((l) => {
                const c = comp.find((x) => x.idioma === l)
                const w = t.peso_relativo?.[l]
                return (
                  <tr key={l}>
                    <td>{lang(l)}</td>
                    <td className="n">{num(t.por_idioma[l].visitas_12m)}</td>
                    <td className="n">{w ? `${num(w.indice, 1)}×` : '—'}</td>
                    <td className="n">{l === 'en' ? 'referencia' : c?.desfase ? (c.desfase.informativo ? `${c.desfase.desfase_dias > 0 ? '+' : ''}${c.desfase.desfase_dias} d` : 'no concluyente') : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">Peso relativo: proporción del tema entre todas las visitas de esa edición, frente al promedio de idiomas (1× = promedio). Un idioma no es un país.</p>
      </section>

      <section aria-labelledby="h-paises">
        <h3 id="h-paises">En los rankings por país</h3>
        <p className="source">Rankings diarios por país de Wikimedia, días muestreados desde 2021 · aproximados (redondeados por privacidad).</p>
        {t.paises ? (
          <>
            <p>Apareció en el ranking de {t.paises.paises} países, en {t.paises.meses_con_presencia} meses ({t.paises.primera_vez} a {t.paises.ultima_vez}).</p>
            <ul className="chips">
              {t.paises.top_paises.slice(0, 8).map((p) => (
                <li key={p.pais}>
                  <button className="link" onClick={() => onSelectCountry(p.pais)}>{countryName(p.pais)}</button>{' '}
                  <span className="muted">{p.meses} meses, mejor puesto {p.mejor_puesto}</span>
                </li>
              ))}
            </ul>
            <p className="muted small">El globo muestra la presencia en {periodLabel}.</p>
          </>
        ) : <p className="muted">No apareció en los rankings por país muestreados. Eso no significa cero interés: solo entran artículos con muchas visitas diarias.</p>}
      </section>

      <section aria-labelledby="h-rel">
        <h3 id="h-rel">Temas relacionados</h3>
        {graph ? <RelatedGraph graph={graph} topic={t.id} onNavigate={onNavigate} /> : <p className="muted">Cargando…</p>}
      </section>

      <section aria-labelledby="h-ciencia" className="placeholder">
        <h3 id="h-ciencia">Producción científica (próximamente)</h3>
        <p className="muted">
          Aquí se superpondrá la curva de publicaciones científicas de OpenAlex sobre la curva de atención, para preguntar si la curiosidad
          pública va delante o detrás de la ciencia. {t.openalex ? `Topic de OpenAlex asociado: ${t.openalex}.` : 'Este tema aún no tiene un topic de OpenAlex asociado.'}
        </p>
      </section>

      <section aria-labelledby="h-articulos">
        <h3 id="h-articulos">Artículos en Wikipedia</h3>
        <p className="muted small">Los artículos exactos cuyas visitas se miden aquí (títulos obtenidos de Wikidata).</p>
        <ul className="articles">
          {Object.entries(t.titulos).map(([l, x]) => (
            <li key={l}>
              <span className="muted">{lang(l)}</span>
              <a href={wikiUrl(`${l}.wikipedia`, x)} target="_blank" rel="noreferrer" lang={l}>{x} ↗</a>
            </li>
          ))}
        </ul>
        <p className="muted small">
          Wikidata: {t.wikidata ? <a href={`https://www.wikidata.org/wiki/${t.wikidata}`} target="_blank" rel="noreferrer">{t.wikidata} ↗</a> : '—'}
        </p>
      </section>
    </div>
  )
}

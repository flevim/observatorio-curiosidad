import { useEffect, useState } from 'react'
import { api, reportUrl, type DailyCuriosities, type Finding, type Trending, type Weekly } from '../api'
import { dateLabel, lang } from '../lib/format'
import CuriosityList from './CuriosityList'
import TrendingList from './TrendingList'

type Props = {
  onTopic: (id: string) => void
  onCountry: (iso: string) => void
  onExplore: (q: string) => void
  reportAvailable: boolean
}

type Tab = 'dia' | 'tendencias' | 'semana' | 'hallazgos'

/** Tarjeta de inicio: curiosidades del día (se renuevan con la actualización diaria) y hallazgos de fondo. */
export default function Findings({ onTopic, onCountry, onExplore, reportAvailable }: Props) {
  const [items, setItems] = useState<Finding[]>([])
  const [days, setDays] = useState<string[]>([])
  const [dayIdx, setDayIdx] = useState(0)
  const [day, setDay] = useState<DailyCuriosities | null>(null)
  const [tab, setTab] = useState<Tab>('dia')
  const [trending, setTrending] = useState<Trending | null>(null)
  const [weekly, setWeekly] = useState<Weekly | null>(null)
  const [open, setOpen] = useState(() => window.matchMedia('(min-width: 768px)').matches)

  useEffect(() => {
    api.findings().then((f) => setItems(f.sorprendentes), () => setItems([]))
    api.trending().then(setTrending, () => setTrending(null))
    api.weekly().then(setWeekly, () => setWeekly(null))
    api.dailyIndex().then(
      (d) => {
        setDays(d.dias.map((x) => x.fecha))
        if (!d.dias.length) setTab('hallazgos')
      },
      () => setTab('hallazgos'),
    )
  }, [])
  useEffect(() => {
    if (!days[dayIdx]) return
    api.curiosities(days[dayIdx]).then(setDay, () => setDay(null))
  }, [days, dayIdx])

  if (!items.length && !days.length) return null
  return (
    <section className="findings" aria-label="Curiosidades y hallazgos">
      <div className="findings-head">
        <div className="seg small" role="tablist" aria-label="Contenido">
          {days.length > 0 && (
            <button role="tab" aria-selected={tab === 'dia'} aria-pressed={tab === 'dia'} onClick={() => { setTab('dia'); setOpen(true) }}>
              Del día
            </button>
          )}
          {trending && (
            <button role="tab" aria-selected={tab === 'tendencias'} aria-pressed={tab === 'tendencias'} onClick={() => { setTab('tendencias'); setOpen(true) }}>
              Tendencias
            </button>
          )}
          {weekly && (
            <button role="tab" aria-selected={tab === 'semana'} aria-pressed={tab === 'semana'} onClick={() => { setTab('semana'); setOpen(true) }}>
              Semana
            </button>
          )}
          <button role="tab" aria-selected={tab === 'hallazgos'} aria-pressed={tab === 'hallazgos'} onClick={() => { setTab('hallazgos'); setOpen(true) }}>
            Hallazgos
          </button>
        </div>
        <button className="findings-toggle" aria-expanded={open} aria-controls="findings-body" onClick={() => setOpen(!open)}
          aria-label={open ? 'Contraer' : 'Expandir'}>
          {open ? '−' : '+'}
        </button>
      </div>

      {open && tab === 'dia' && (
        <div id="findings-body" role="tabpanel">
          <div className="day-nav">
            <button className="ghost small-btn" disabled={dayIdx >= days.length - 1} onClick={() => setDayIdx(dayIdx + 1)} aria-label="Día anterior">←</button>
            <p className="day-title">{days[dayIdx] ? dateLabel(days[dayIdx]) : ''}</p>
            <button className="ghost small-btn" disabled={dayIdx <= 0} onClick={() => setDayIdx(dayIdx - 1)} aria-label="Día siguiente">→</button>
          </div>
          {day ? (
            <>
              {day.curiosidades.length ? (
                <CuriosityList items={day.curiosidades} onTopic={onTopic} onCountry={onCountry} />
              ) : <p className="muted pad">Nada nuevo ese día en los países observados.</p>}
              <p className="muted small pad">
                Comparado con los {day.dias_comparados} días anteriores observados, en {day.paises} países. Rankings diarios de Wikimedia
                (aproximados). Wikimedia publica cada día con ~1 día de retraso; se actualiza con <code>python -m observatorio daily</code>.
              </p>
            </>
          ) : <p className="muted pad">Cargando…</p>}
        </div>
      )}

      {open && tab === 'tendencias' && trending && (
        <div id="findings-body" role="tabpanel">
          <p className="day-title pad-top">Lo más leído en Wikipedia · {dateLabel(trending.fecha)}</p>
          <TrendingList data={trending.por_idioma} onTopic={onTopic} onExplore={onExplore} />
          <p className="muted small pad">
            Artículos más vistos de cada edición ese día (visitas de personas), sin portada ni páginas especiales. Algunas listas
            incluyen artículos inflados por tráfico automatizado. Un idioma no es un país.
          </p>
        </div>
      )}

      {open && tab === 'semana' && weekly && (
        <div id="findings-body" role="tabpanel">
          <p className="day-title pad-top">Semana del {dateLabel(weekly.desde)} al {dateLabel(weekly.hasta)}</p>
          {weekly.secciones.filter((s) => s.curiosidades.length).map((s) => (
            <section key={s.titulo} className="week-sec">
              <p className="week-title">{s.titulo}</p>
              <CuriosityList items={s.curiosidades} onTopic={onTopic} onCountry={onCountry} />
            </section>
          ))}
          {Object.keys(weekly.tendencias).length > 0 && (
            <section className="week-sec">
              <p className="week-title">Lo más leído de la semana</p>
              <TrendingList data={weekly.tendencias} showDays limit={10} onTopic={onTopic} onExplore={onExplore} />
            </section>
          )}
          <p className="muted small pad">{weekly.nota}</p>
        </div>
      )}

      {open && tab === 'hallazgos' && (
        <div id="findings-body" role="tabpanel">
          <ol>
            {items.map((f) => (
              <li key={f.id}>
                <p className="f-title">{f.titulo}</p>
                <p className="f-text">{f.texto}</p>
                <ul className="f-links">
                  {f.temas.length > 0 && (
                    <li><button className="link" onClick={() => onTopic(f.temas[0])}>Ver en el observatorio</button></li>
                  )}
                  {(f.enlaces ?? []).map((l) => (
                    <li key={l.url}>
                      <a href={l.url} target="_blank" rel="noreferrer" lang={l.idioma} title={`Abrir «${l.titulo}» en Wikipedia en ${lang(l.idioma)}`}>
                        {l.titulo} ↗
                      </a>
                      <span className="lang">{l.idioma}.wikipedia</span>
                    </li>
                  ))}
                  {f.enlaces?.[0]?.visitas_url && (
                    <li>
                      <a href={f.enlaces[0].visitas_url} target="_blank" rel="noreferrer" title="Gráfico de visitas en la herramienta oficial de Wikimedia, para verificar el dato">
                        Verificar visitas ↗
                      </a>
                    </li>
                  )}
                </ul>
              </li>
            ))}
          </ol>
          <p className="muted small pad">
            Visitas a Wikipedia por edición de idioma, desde julio de 2015. Los números se calculan, no se interpretan: no dicen la causa.
            {reportAvailable && <> <a href={reportUrl} target="_blank" rel="noreferrer">Reporte completo</a>.</>}
          </p>
        </div>
      )}
    </section>
  )
}

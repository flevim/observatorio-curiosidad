import { useEffect, useMemo, useState } from 'react'
import type { PropArticle } from '../api'
import { countryName, dateLabel, num } from '../lib/format'

export const PROP_NEW = '#f2559a' // llegó ese día
export const PROP_OLD = '#2a9db6' // ya estaba
export const PROP_WAIT = 'rgba(236,235,243,0.10)' // con datos, pero aún no llega

type Props = {
  art: PropArticle
  dayIdx: number
  onDay: (i: number) => void
  reducedMotion: boolean
  controls?: boolean // false: la reproducción está en la barra inferior de la vista Propagación
  onCountry: (iso: string) => void
  onTopic: (id: string) => void
  onClose: () => void
}

/** Días de la propagación de un artículo, desde su primer día hasta el último país al que llegó. */
export function propDays(art: PropArticle): string[] {
  const ds = [...new Set(Object.values(art.paises).map((p) => p.dia))].sort()
  const out: string[] = []
  const d = new Date(ds[0] + 'T00:00:00Z')
  const last = ds[ds.length - 1]
  for (;;) {
    const k = d.toISOString().slice(0, 10)
    out.push(k)
    if (k >= last) break
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

export default function PropagationPanel({ art, dayIdx, onDay, reducedMotion, controls = true, onCountry, onTopic, onClose }: Props) {
  const days = useMemo(() => propDays(art), [art])
  const [playing, setPlaying] = useState(false)
  const day = days[Math.min(dayIdx, days.length - 1)]

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      if (dayIdx >= days.length - 1) {
        setPlaying(false)
        return
      }
      onDay(dayIdx + 1)
    }, reducedMotion ? 1600 : 1100)
    return () => clearInterval(t)
  }, [playing, dayIdx, days.length, onDay, reducedMotion])

  const byDay = days.map((d) => ({
    d,
    paises: Object.entries(art.paises).filter(([, p]) => p.dia === d).sort((a, b) => b[1].visitas - a[1].visitas),
  }))
  const arrived = Object.values(art.paises).filter((p) => p.dia <= day).length
  const nuevos = Object.values(art.paises).filter((p) => p.dia === day).length

  return (
    <div className="panel-body">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Propagación</p>
          <h2 id="panel-title">{art.titulo}</h2>
          <p className="muted">
            Llegó a {art.n} países en {art.dias_propagacion + 1} {art.dias_propagacion === 0 ? 'día' : 'días'}, empezando en{' '}
            {countryName(art.origen)} el {dateLabel(art.inicio)}.
          </p>
        </div>
        <button className="icon" onClick={onClose} aria-label="Cerrar propagación">×</button>
      </header>
      <ul className="f-links">
        <li><a href={art.enlace.url} target="_blank" rel="noreferrer">{art.enlace.titulo} ↗</a><span className="lang">{art.enlace.proyecto.replace('.wikipedia', '')}</span></li>
        {art.tema && <li><button className="link" onClick={() => onTopic(art.tema!)}>Ver el tema</button></li>}
      </ul>
      <p className="source">
        Primer día en que el artículo entra en el ranking diario de cada país (Wikimedia, aproximado). El origen es el país con más
        visitas el primer día. Que llegue antes a un país no significa que la noticia viajara de uno a otro.
      </p>

      <h3>Día a día</h3>
      {controls && <div className="prop-controls">
        <button className="play" onClick={() => {
          if (!playing && dayIdx >= days.length - 1) onDay(0)
          setPlaying(!playing)
        }} aria-label={playing ? 'Pausar' : 'Reproducir la propagación'}>
          {playing ? '❚❚' : '▶'}
        </button>
        <input type="range" min={0} max={days.length - 1} step={1} value={dayIdx}
          onChange={(e) => { setPlaying(false); onDay(Number(e.target.value)) }}
          aria-label="Día de la propagación" aria-valuetext={dateLabel(day)} />
      </div>}
      <p className="prop-day"><b>{dateLabel(day)}</b> · {arrived} {arrived === 1 ? 'país' : 'países'} · {nuevos} {nuevos === 1 ? 'nuevo' : 'nuevos'}</p>
      <ul className="prop-legend">
        <li><i style={{ background: PROP_NEW }} />llega ese día</li>
        <li><i style={{ background: PROP_OLD }} />ya había llegado</li>
        <li><i style={{ background: PROP_WAIT }} />aún no llega</li>
        <li><i className="hatch" />sin datos</li>
      </ul>

      <h3>Llegadas</h3>
      <ol className="prop-list">
        {byDay.filter((g) => g.paises.length).map((g) => (
          <li key={g.d} className={g.d === day ? 'now' : g.d < day ? 'past' : ''}>
            <p className="prop-date">{dateLabel(g.d)} · {g.paises.length}</p>
            <p className="prop-countries">
              {g.paises.map(([iso, p], i) => (
                <span key={iso}>
                  <button className="link" onClick={() => onCountry(iso)}>{countryName(iso)}</button>
                  <span className="muted"> ≈{num(p.visitas)}</span>{i < g.paises.length - 1 ? ', ' : ''}
                </span>
              ))}
            </p>
          </li>
        ))}
      </ol>
      <p className="muted small">Visitas: máximo diario aproximado en el ranking de ese país.</p>
    </div>
  )
}

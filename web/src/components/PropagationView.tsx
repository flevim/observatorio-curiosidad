import { useEffect, useState } from 'react'
import type { PropArticle } from '../api'
import { countryName, dateLabel, periodLabel } from '../lib/format'

/** Lista de artículos que viajaron entre países (columna izquierda de la vista Propagación). */
export function PropagationList({ items, selectedId, onSelect, dias }: {
  items: PropArticle[]; selectedId: string | null; onSelect: (a: PropArticle) => void; dias: number
}) {
  return (
    <section className="prop-side" aria-labelledby="prop-side-title">
      <p className="kicker"><span className="rule" aria-hidden="true" />Últimos {dias} días</p>
      <h2 id="prop-side-title" className="prop-side-title">Cómo <em>viajan</em> los artículos</h2>
      <p className="hero-lede">Artículos que entraron en el ranking de 4 o más países. Elige uno y míralo recorrer el mundo.</p>
      <ol className="prop-pick">
        {items.map((a) => (
          <li key={a.id}>
            <button className={a.id === selectedId ? 'on' : ''} aria-pressed={a.id === selectedId} onClick={() => onSelect(a)}>
              <span className="pp-title">{a.titulo}</span>
              <span className="pp-meta">{a.n} países · {a.dias_propagacion + 1} {a.dias_propagacion === 0 ? 'día' : 'días'} · desde {countryName(a.origen)}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** Línea de tiempo de la propagación (barra inferior): reproducir, avanzar día a día, cuántos países lleva. */
export function PropagationTimeline({ days, dayIdx, onDay, arrived, nuevos, reducedMotion }: {
  days: string[]; dayIdx: number; onDay: (i: number) => void; arrived: number; nuevos: number; reducedMotion: boolean
}) {
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      if (dayIdx >= days.length - 1) return setPlaying(false)
      onDay(dayIdx + 1)
    }, reducedMotion ? 1600 : 1100)
    return () => clearInterval(t)
  }, [playing, dayIdx, days.length, onDay, reducedMotion])

  if (!days.length) return null
  const day = days[Math.min(dayIdx, days.length - 1)]
  return (
    <div className="timeline" role="group" aria-label="Línea de tiempo de la propagación">
      <button className="play" aria-label={playing ? 'Pausar' : 'Reproducir la propagación'}
        onClick={() => { if (!playing && dayIdx >= days.length - 1) onDay(0); setPlaying(!playing) }}>
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="tl-main">
        <div className="tl-top">
          <output className="tl-label" aria-live={playing ? 'off' : 'polite'}>{dateLabel(day)}</output>
          <span className="tl-label prop-count">{arrived} {arrived === 1 ? 'país' : 'países'} · <b>{nuevos} {nuevos === 1 ? 'nuevo' : 'nuevos'}</b></span>
        </div>
        <input type="range" min={0} max={days.length - 1} step={1} value={dayIdx}
          onChange={(e) => { setPlaying(false); onDay(Number(e.target.value)) }}
          aria-label="Día de la propagación" aria-valuetext={dateLabel(day)} />
        <div className="tl-ends"><span>{periodLabel(days[0])}</span><span>{periodLabel(days[days.length - 1])}</span></div>
      </div>
    </div>
  )
}

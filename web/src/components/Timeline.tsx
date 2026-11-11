import { useEffect } from 'react'
import type { Period } from '../api'
import { periodLabel } from '../lib/format'

type Props = {
  periods: Period[] // ya filtrados por tipo
  index: number
  onIndex: (i: number) => void
  playing: boolean
  onPlaying: (p: boolean) => void
  kind: 'mes' | 'dia'
  onKind: (k: 'mes' | 'dia') => void
}

export default function Timeline({ periods, index, onIndex, playing, onPlaying, kind, onKind }: Props) {
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      onIndex(index >= periods.length - 1 ? 0 : index + 1)
    }, kind === 'mes' ? 700 : 1000)
    return () => clearInterval(t)
  }, [playing, index, periods.length, onIndex, kind])

  if (!periods.length) return null
  const p = periods[index]
  const first = periods[0]
  const last = periods[periods.length - 1]
  return (
    <div className="timeline" role="group" aria-label="Línea de tiempo">
      <button
        className="play"
        onClick={() => onPlaying(!playing)}
        aria-label={playing ? 'Pausar animación' : 'Reproducir la evolución en el tiempo'}
      >
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="tl-main">
        <div className="tl-top">
          <output className="tl-label" aria-live={playing ? 'off' : 'polite'}>
            {p.tipo === 'mes' ? periodLabel(p.id) : `Día ${periodLabel(p.id)}`}
          </output>
          <div className="seg small" role="group" aria-label="Tipo de periodo">
            <button aria-pressed={kind === 'mes'} onClick={() => onKind('mes')}>Meses</button>
            <button aria-pressed={kind === 'dia'} onClick={() => onKind('dia')}>Días recientes</button>
          </div>
        </div>
        <input
          type="range"
          min={0}
          max={periods.length - 1}
          value={index}
          onChange={(e) => {
            onPlaying(false)
            onIndex(Number(e.target.value))
          }}
          aria-label="Periodo"
          aria-valuetext={periodLabel(p.id)}
        />
        <div className="tl-ends muted small">
          <span>{periodLabel(first.id)}</span>
          <span>{periodLabel(last.id)}</span>
        </div>
      </div>
    </div>
  )
}

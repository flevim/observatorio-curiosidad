import { ABSENT, RAMP, type Scale } from '../lib/scale'

type Props = { scale: Scale | null; title: string; topicMode: boolean; caption: string }

export default function Legend({ scale, title, topicMode, caption }: Props) {
  const e = scale?.edges ?? []
  const f = scale?.format ?? String
  const steps = e.length
    ? RAMP.slice(0, e.length + 1).map((c, i) => ({
        c,
        label: i === 0 ? `< ${f(e[0])}` : i === e.length ? `≥ ${f(e[e.length - 1])}` : `${f(e[i - 1])}–${f(e[i])}`,
      }))
    : []
  return (
    <div className="legend" aria-label="Leyenda del mapa">
      <p className="legend-title">{title}</p>
      {steps.length > 0 && (
        <ul className="ramp">
          {steps.map((s) => (
            <li key={s.c}><i style={{ background: s.c }} />{s.label}</li>
          ))}
        </ul>
      )}
      <ul className="legend-extra">
        {topicMode && <li><i style={{ background: ABSENT }} />no aparece en el ranking</li>}
        <li><i className="hatch" />sin datos (no es cero)</li>
      </ul>
      <p className="legend-caption">{caption}</p>
    </div>
  )
}

import type { Graph } from '../api'
import { num } from '../lib/format'

type Props = {
  graph: Graph
  topic: string
  onNavigate: (id: string) => void
}

type Edge = { id: string; nombre: string; sem: string[] | null; stat: number | null }

/** Grafo radial: el tema al centro y sus vecinos alrededor.
 *  Línea continua = relación semántica (enlaces / Wikidata). Línea discontinua = estadística (atención que sube y baja junta). */
export default function RelatedGraph({ graph, topic, onNavigate }: Props) {
  const names = Object.fromEntries(graph.nodos.map((n) => [n.id, n.nombre]))
  const edges = new Map<string, Edge>()
  for (const s of graph.semanticas) {
    const other = s.a === topic ? s.b : s.b === topic ? s.a : null
    if (other) edges.set(other, { id: other, nombre: names[other] ?? other, sem: s.evidencias, stat: edges.get(other)?.stat ?? null })
  }
  for (const s of graph.estadisticas) {
    const other = s.a === topic ? s.b : s.b === topic ? s.a : null
    if (other) {
      const e = edges.get(other)
      edges.set(other, { id: other, nombre: names[other] ?? other, sem: e?.sem ?? null, stat: s.r })
    }
  }
  const list = [...edges.values()].sort((a, b) => Number(!!b.sem && !!b.stat) - Number(!!a.sem && !!a.stat) || (b.stat ?? 0) - (a.stat ?? 0)).slice(0, 10)
  const cands = graph.candidatos[topic] ?? []

  if (!list.length) {
    return (
      <div>
        <p className="muted">Sin relaciones con otros temas del observatorio.</p>
        {cands.length > 0 && <Candidates cands={cands} />}
      </div>
    )
  }

  const W = 360
  const H = 260
  const cx = W / 2
  const cy = H / 2
  const R = 100
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="graph" role="group" aria-label="Temas relacionados">
        {list.map((e, i) => {
          const a = (i / list.length) * Math.PI * 2 - Math.PI / 2
          const x = cx + Math.cos(a) * R * 1.25
          const y = cy + Math.sin(a) * R * 0.95
          return (
            <g key={e.id}>
              {e.sem && <line x1={cx} y1={cy} x2={x} y2={y} className="edge sem" />}
              {e.stat != null && <line x1={cx} y1={cy} x2={x} y2={y} className="edge stat" transform={e.sem ? `translate(0,4)` : undefined} />}
              <g
                className="gnode"
                tabIndex={0}
                role="button"
                aria-label={`${e.nombre}: ${[e.sem && 'relación semántica', e.stat != null && `relación estadística r = ${num(e.stat, 2)}`].filter(Boolean).join(' y ')}`}
                onClick={() => onNavigate(e.id)}
                onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), onNavigate(e.id))}
              >
                <title>{[e.sem?.slice(0, 2).join('\n'), e.stat != null ? `Co-movimiento semanal r = ${num(e.stat, 2)}` : ''].filter(Boolean).join('\n')}</title>
                <circle cx={x} cy={y} r={20} className="hit" />
                <circle cx={x} cy={y} r={7} />
                <text x={x} y={y + (y > cy ? 20 : -12)} textAnchor="middle">{e.nombre}</text>
              </g>
            </g>
          )
        })}
        <circle cx={cx} cy={cy} r={9} className="gcenter" />
      </svg>
      <div className="glegend">
        <span><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" className="edge sem" /></svg> semántica (enlaces, Wikidata)</span>
        <span><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" className="edge stat" /></svg> estadística (suben y bajan juntos)</span>
      </div>
      <p className="muted small">Una relación estadística no implica causalidad.</p>
      {cands.length > 0 && <Candidates cands={cands} />}
    </div>
  )
}

function Candidates({ cands }: { cands: Graph['candidatos'][string] }) {
  return (
    <details className="cands">
      <summary>Relacionados en Wikidata, aún sin datos ({cands.length})</summary>
      <ul>
        {cands.map((c) => (
          <li key={c.wikidata}>
            {c.nombre} <span className="muted">({c.relacion})</span>
          </li>
        ))}
      </ul>
      <p className="muted small">Puedes agregarlos con «Agregar tema» en «Acerca de los datos».</p>
    </details>
  )
}

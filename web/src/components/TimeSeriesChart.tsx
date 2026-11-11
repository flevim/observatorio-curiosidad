import { useEffect, useMemo, useRef, useState } from 'react'
import type { SeriesPayload } from '../api'
import { compact, lang, num } from '../lib/format'

// Colores categóricos fijos por idioma resaltado (paleta validada, variante oscura); el resto en gris de contexto.
export const HL_COLORS = ['#2a9db6', '#c08a1a', '#dd3f86'] // es, en, comparación: validados para daltonismo sobre #08070c
const CTX = 'rgba(236,235,243,0.18)'

type Props = {
  data: SeriesPayload
  daily: boolean
  highlight: string[] // hasta 3 idiomas, en orden fijo de color
  log: boolean
  markers?: { date: string; label: string }[]
  label: string
}

function datesOf(p: SeriesPayload, daily: boolean): string[] {
  if (p.fechas) return p.fechas
  const n = Object.values(p.series)[0]?.length ?? 0
  const out: string[] = []
  const d = new Date(p.inicio + 'T00:00:00Z')
  for (let i = 0; i < n; i++) {
    out.push(d.toISOString().slice(0, daily ? 10 : 7))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

export default function TimeSeriesChart({ data, daily, highlight, log, markers = [], label }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(380)
  const [hover, setHover] = useState<number | null>(null)
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, e.contentRect.width)))
    if (ref.current) ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])

  const H = 220
  const L = 60
  const R = 26
  const T = 10
  const B = 24
  const dates = useMemo(() => datesOf(data, daily), [data, daily])
  const keys = useMemo(() => Object.keys(data.series).filter((k) => k !== 'todas'), [data])
  const n = dates.length

  const { fy, ticks, paths } = useMemo(() => {
    let max = 1
    let min = Infinity
    for (const k of keys) for (const v of data.series[k]) if (v != null && v > 0) {
      if (v > max) max = v
      if (v < min) min = v
    }
    const ph = H - T - B
    let fy: (v: number) => number
    let ticks: number[]
    if (log) {
      const lo = Math.floor(Math.log10(Math.max(min, 1)))
      const hi = Math.ceil(Math.log10(max))
      fy = (v) => T + ph - ((Math.log10(Math.max(v, 1)) - lo) / Math.max(hi - lo, 1)) * ph
      ticks = []
      for (let e = lo; e <= hi; e++) ticks.push(10 ** e)
    } else {
      const top = max * 1.05
      fy = (v) => T + ph - (v / top) * ph
      const step = 10 ** Math.floor(Math.log10(top / 4))
      const s = [1, 2, 2.5, 5, 10].map((m) => m * step).find((x) => top / x <= 5) ?? step
      ticks = []
      for (let v = 0; v <= top; v += s) ticks.push(v)
    }
    const fx = (i: number) => L + (i / Math.max(n - 1, 1)) * (w - L - R)
    const paths: Record<string, string> = {}
    for (const k of keys) {
      let d = ''
      let pen = false
      data.series[k].forEach((v, i) => {
        if (v == null || (log && v <= 0)) {
          pen = false
          return
        }
        d += `${pen ? 'L' : 'M'}${fx(i).toFixed(1)},${fy(v).toFixed(1)}`
        pen = true
      })
      paths[k] = d
    }
    return { fy, ticks, paths }
  }, [data, keys, log, w, n])

  const fx = (i: number) => L + (i / Math.max(n - 1, 1)) * (w - L - R)
  const order = [...keys.filter((k) => !highlight.includes(k)), ...highlight.filter((k) => keys.includes(k))]
  const yearTicks = dates
    .map((d, i) => [d, i] as const)
    .filter(([d]) => (daily ? d.endsWith('-01-01') : d.endsWith('-01')) && Number(d.slice(0, 4)) % 2 === 0)

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const i = Math.round(((e.clientX - r.left) / r.width) * (n - 1))
    setHover(Math.max(0, Math.min(n - 1, i)))
  }
  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? (daily ? 30 : 12) : 1
    if (e.key === 'ArrowRight') setHover((h) => Math.min(n - 1, (h ?? n - 1) + step))
    else if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? n - 1) - step))
    else if (e.key === 'Escape') setHover(null)
    else return
    e.preventDefault()
  }

  const tipRows = hover == null ? [] : keys
    .map((k) => [k, data.series[k][hover]] as const)
    .filter(([, v]) => v != null)
    .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))

  return (
    <div className="tschart" ref={ref}>
      <svg
        width={w}
        height={H}
        role="img"
        aria-label={label}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={w - R} y1={fy(t)} y2={fy(t)} className="grid" />
            <text x={L - 6} y={fy(t) + 4} className="tick" textAnchor="end">{compact(t)}</text>
          </g>
        ))}
        {yearTicks.map(([d, i]) => (
          <text key={d} x={fx(i)} y={H - 6} className="tick" textAnchor="middle">{d.slice(0, 4)}</text>
        ))}
        <line x1={L} x2={w - R} y1={H - B} y2={H - B} className="axis" />
        {markers.map((m) => {
          const i = dates.indexOf(daily ? m.date : m.date.slice(0, 7))
          if (i < 0) return null
          return <line key={m.date} x1={fx(i)} x2={fx(i)} y1={T} y2={H - B} className="marker"><title>{m.label}</title></line>
        })}
        {order.map((k) => {
          const hi = highlight.indexOf(k)
          return (
            <path
              key={k}
              d={paths[k]}
              fill="none"
              stroke={hi >= 0 ? HL_COLORS[hi] : CTX}
              strokeWidth={hi >= 0 ? 2 : 1}
              strokeLinejoin="round"
              opacity={hi >= 0 ? 1 : 0.8}
            />
          )
        })}
        {hover != null && <line x1={fx(hover)} x2={fx(hover)} y1={T} y2={H - B} className="xhair" />}
        <rect x={L} y={T} width={w - L - R} height={H - T - B} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover != null && (
        <div className="tstip" style={{ left: Math.min(fx(hover) + 10, w - 160) }} aria-live="polite">
          <b>{dates[hover]}</b>
          {tipRows.slice(0, 6).map(([k, v]) => (
            <div key={k}>
              <i className="sw" style={{ background: highlight.includes(k) ? HL_COLORS[highlight.indexOf(k)] : CTX }} />
              {lang(k)}: {num(v ?? 0)}
            </div>
          ))}
          {tipRows.length > 6 && <div className="muted">+{tipRows.length - 6} idiomas</div>}
        </div>
      )}
    </div>
  )
}

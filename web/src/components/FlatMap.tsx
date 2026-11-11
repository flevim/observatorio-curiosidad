import { useMemo } from 'react'
import { geoEqualEarth, geoPath } from 'd3-geo'
import type { CountryFeature, GeoJSON } from '../api'
import { type CountryState, stateColor } from '../lib/scale'

type Props = {
  geo: GeoJSON
  stateFor: (iso: string | null) => CountryState
  describe: (f: CountryFeature, s: CountryState) => string
  selected: string | null
  onSelect: (iso: string | null, name: string) => void
}

const W = 960
const H = 500

/** Vista alternativa: mapa plano (Equal Earth) navegable con teclado (Tab + Enter). */
export default function FlatMap({ geo, stateFor, describe, selected, onSelect }: Props) {
  const paths = useMemo(() => {
    const proj = geoEqualEarth().fitSize([W, H], geo as never)
    const path = geoPath(proj)
    return geo.features
      .filter((f) => f.properties.continente !== 'Antarctica')
      .map((f) => ({ f, d: path(f as never) ?? '' }))
      .sort((a, b) => (a.f.properties.nombre < b.f.properties.nombre ? -1 : 1))
  }, [geo])

  return (
    <svg className="flatmap" viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Mapa plano de países">
      <defs>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(255,255,255,0.18)" strokeWidth="1.5" />
        </pattern>
      </defs>
      {paths.map(({ f, d }) => {
        const s = stateFor(f.properties.iso)
        const label = describe(f, s).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
        const isSel = f.properties.iso === selected
        return (
          <path
            key={f.properties.name}
            d={d}
            fill={s.kind === 'nodata' ? 'url(#hatch)' : stateColor(s)}
            className={`country${isSel ? ' selected' : ''}`}
            tabIndex={f.properties.iso ? 0 : -1}
            role="button"
            aria-label={label}
            aria-pressed={isSel}
            onClick={() => onSelect(f.properties.iso, f.properties.nombre)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(f.properties.iso, f.properties.nombre)
              }
            }}
          >
            <title>{label}</title>
          </path>
        )
      })}
    </svg>
  )
}

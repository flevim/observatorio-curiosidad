// Escala de color secuencial (un solo tono, cian) para fondo oscuro: lo bajo se funde con el fondo,
// lo alto es claro. Pasos cuantizados para que la leyenda sea legible y los colores comparables en el tiempo.
import type { GlobeData } from '../api'

// Segundo color de la identidad (el primero, naranja, es para acciones): cian, de oscuro a claro.
export const RAMP = ['#0d4250', '#13627a', '#1c84a0', '#3aa6c2', '#7cc9db', '#c6ecf3']
export const NO_DATA = 'rgba(0,0,0,0)' // sin datos: se ve la Tierra, sin color encima
export const ABSENT = 'rgba(236,232,224,0.16)' // hay ranking, pero el tema no aparece
export const SELECTED_STROKE = '#f0601a'

/** Color sobre el globo: el mismo paso de la rampa, con algo de transparencia para que se vea el relieve. */
const withAlpha = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

export type CountryState =
  | { kind: 'nodata' }
  | { kind: 'absent' }
  | { kind: 'value'; value: number; bin: number; rank?: number | null }

export type Scale = { edges: number[]; format: (v: number) => string; unit: string }

/** Cortes por cuantiles de log(valor) sobre TODOS los periodos: el mismo color significa lo mismo en toda la línea de tiempo. */
export function buildScale(data: GlobeData, unit: string, format: (v: number) => string): Scale {
  const vals: number[] = []
  for (const arr of Object.values(data.valores)) for (const v of arr) if (v != null && v > 0) vals.push(Math.log(v))
  vals.sort((a, b) => a - b)
  const edges: number[] = []
  if (vals.length) {
    for (let i = 1; i < RAMP.length; i++) edges.push(Math.exp(vals[Math.floor((i / RAMP.length) * (vals.length - 1))]))
  }
  // Cortes redondeados a 2 cifras significativas, sin repetir.
  const nice = [...new Set(edges.map((e) => Number(e.toPrecision(2))))]
  return { edges: nice, format, unit }
}

export function binOf(scale: Scale, v: number): number {
  let i = 0
  while (i < scale.edges.length && v >= scale.edges[i]) i++
  return Math.min(i, RAMP.length - 1)
}

/**
 * Estado de un país en un periodo.
 * - modo periodo: valor = volumen; null = sin datos.
 * - modo tema: si el país tiene ranking en ese periodo (volume != null) y el tema no aparece -> "absent".
 */
export function countryState(
  iso: string | null,
  idx: number,
  data: GlobeData | null,
  volume: GlobeData | null,
  scale: Scale | null,
  topicMode: boolean,
): CountryState {
  if (!iso || !data || !scale) return { kind: 'nodata' }
  const hasRanking = volume?.valores[iso]?.[idx] != null
  if (!hasRanking) return { kind: 'nodata' }
  const v = data.valores[iso]?.[idx]
  if (topicMode && (!v || v <= 0)) return { kind: 'absent' }
  if (v == null) return { kind: 'nodata' }
  return { kind: 'value', value: v, bin: binOf(scale, v), rank: data.puesto?.[iso]?.[idx] }
}

export function stateColor(s: CountryState): string {
  if (s.kind === 'nodata') return NO_DATA
  if (s.kind === 'absent') return ABSENT
  return RAMP[s.bin]
}

export function globeColor(s: CountryState): string {
  if (s.kind === 'value') return withAlpha(RAMP[s.bin], 0.82)
  return stateColor(s)
}

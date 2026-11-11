export const IDIOMAS: Record<string, string> = {
  es: 'español', en: 'inglés', pt: 'portugués', fr: 'francés', de: 'alemán', ja: 'japonés',
  it: 'italiano', ru: 'ruso', zh: 'chino', ar: 'árabe', todas: 'todos los idiomas',
}

export const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

const nf0 = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 2, minimumFractionDigits: 2 })

export const num = (x: number, dec = 0) => (dec === 0 ? nf0 : dec === 1 ? nf1 : nf2).format(x)
export const pct = (x: number) => `${nf0.format(x * 100)} %`

export function compact(x: number): string {
  if (x >= 1e6) return `${nf1.format(x / 1e6)} M`
  if (x >= 1e4) return `${nf0.format(x / 1e3)} mil`
  return nf0.format(x)
}

export function periodLabel(id: string): string {
  const [y, m, d] = id.split('-')
  if (d) return `${Number(d)} ${MESES[Number(m) - 1].slice(0, 3)} ${y}`
  return `${MESES[Number(m) - 1]} ${y}`
}

export function dateLabel(iso: string): string {
  const [y, m, d] = iso.split('-')
  return d ? `${Number(d)} de ${MESES[Number(m) - 1]} de ${y}` : `${MESES[Number(m) - 1]} de ${y}`
}

export const lang = (code: string) => IDIOMAS[code] ?? code

const regionNames = new Intl.DisplayNames(['es'], { type: 'region' })
export function countryName(iso: string, fallback?: string): string {
  try {
    return regionNames.of(iso) ?? fallback ?? iso
  } catch {
    return fallback ?? iso
  }
}

export const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function fold(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

export function wikiUrl(project: string, article: string): string {
  return `https://${project}.org/wiki/${encodeURIComponent(article.replace(/ /g, '_'))}`
}

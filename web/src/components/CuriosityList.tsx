import type { Curiosity } from '../api'
import { countryName } from '../lib/format'

type Props = {
  items: Curiosity[]
  onTopic?: (id: string) => void
  onCountry?: (iso: string) => void
  hideCountries?: boolean
}

/** Lista de curiosidades: texto con su número, enlaces a Wikipedia y accesos al tema o a los países. */
export default function CuriosityList({ items, onTopic, onCountry, hideCountries }: Props) {
  return (
    <ul className="curiosities">
      {items.map((c, i) => (
        <li key={i}>
          <p className="c-text">{c.texto}</p>
          <ul className="f-links">
            {c.tema && onTopic && (
              <li><button className="link" onClick={() => onTopic(c.tema!)}>Ver el tema</button></li>
            )}
            {c.enlaces.map((l) => (
              <li key={l.url}>
                <a href={l.url} target="_blank" rel="noreferrer" title={`Abrir en ${l.proyecto}`}>{l.titulo} ↗</a>
                <span className="lang">{l.proyecto.replace('.wikipedia', '')}</span>
              </li>
            ))}
            {!hideCountries && onCountry && (c.paises ?? []).length <= 6 &&
              (c.paises ?? []).map((iso) => (
                <li key={iso}><button className="link" onClick={() => onCountry(iso)}>{countryName(iso)}</button></li>
              ))}
          </ul>
        </li>
      ))}
    </ul>
  )
}

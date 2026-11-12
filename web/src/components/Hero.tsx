import { useMemo } from 'react'
import type { Meta, PropArticle } from '../api'
import Findings from './Findings'
import SearchBox from './SearchBox'

type Props = {
  meta: Meta
  onTopic: (id: string) => void
  onCountry: (iso: string) => void
  onExplore: (q: string) => void
  onPropagation: (a: PropArticle) => void
}

/** Portada: qué es esto, buscador grande, accesos rápidos y las curiosidades del día. */
export default function Hero({ meta, onTopic, onCountry, onExplore, onPropagation }: Props) {
  // Accesos rápidos: los tres temas con más visitas en los últimos 12 meses.
  const quick = useMemo(
    () => [...meta.temas].sort((a, b) => (b.visitas_12m ?? 0) - (a.visitas_12m ?? 0)).slice(0, 3),
    [meta.temas],
  )
  const surprise = () => {
    const t = meta.temas[Math.floor(Math.random() * meta.temas.length)]
    if (t) onTopic(t.id)
  }
  const last = meta.curiosidades_dias?.[0]

  return (
    <section className="hero" aria-labelledby="hero-title">
      <p className="kicker">
        <span className="rule" aria-hidden="true" />
        Desde julio 2015 · {meta.idiomas.length} idiomas · {meta.paises_con_datos.length} países
      </p>
      <h1 id="hero-title" className="hero-title">
        ¿Qué le da <em>curiosidad</em> al mundo?
      </h1>
      <p className="hero-lede">
        Lo que la gente lee en Wikipedia, país por país y día a día. Busca un tema del observatorio, cualquier artículo de
        Wikipedia, o toca un país en el globo para ver lo que se encontró ahí.
      </p>

      <p className="step">A — Tema o artículo</p>
      <SearchBox topics={meta.temas} onPick={onTopic} onExplore={onExplore} big />

      <p className="step step-row">
        <span>B — O prueba</span>
        <span className="step-hint">o toca un país en el globo</span>
      </p>
      <div className="chips-row">
        {quick.map((t) => (
          <button key={t.id} className="chip" onClick={() => onTopic(t.id)}>{t.nombre}</button>
        ))}
        <button className="chip accent" onClick={surprise}>Sorpréndeme</button>
      </div>

      <p className="step">C — {last ? 'Lo curioso, día a día' : 'Hallazgos'}</p>
      <Findings onTopic={onTopic} onCountry={onCountry} onExplore={onExplore} onPropagation={onPropagation} reportAvailable={meta.reporte_disponible} />
    </section>
  )
}

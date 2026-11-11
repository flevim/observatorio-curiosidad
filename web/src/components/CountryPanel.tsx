import { useEffect, useState } from 'react'
import { api, type CountryPanelData, type CountryProfile, type Period } from '../api'
import CuriosityList from './CuriosityList'
import { countryName, num, periodLabel, wikiUrl } from '../lib/format'

const listFmt = new Intl.ListFormat('es', { style: 'long', type: 'conjunction' })

type Props = {
  iso: string
  name: string
  period: Period
  topicNames: Record<string, string>
  onTopic: (id: string) => void
  onClose: () => void
}

export default function CountryPanel({ iso, name, period, topicNames, onTopic, onClose }: Props) {
  const [data, setData] = useState<CountryPanelData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [profile, setProfile] = useState<CountryProfile | null>(null)

  useEffect(() => {
    setProfile(null)
    api.profile(iso).then(setProfile, () => setProfile({ pais: iso, sin_datos: true }))
  }, [iso])

  useEffect(() => {
    setData(null)
    setErr(null)
    api.country(period.id, iso).then(setData, (e) => setErr(String(e.message ?? e)))
  }, [iso, period.id])

  return (
    <div className="panel-body">
      <header className="panel-head">
        <div>
          <p className="eyebrow">País</p>
          <h2 id="panel-title">{countryName(iso, name)}</h2>
          <p className="muted">{period.tipo === 'mes' ? periodLabel(period.id) : `Día ${periodLabel(period.id)}`}</p>
        </div>
        <button className="icon" onClick={onClose} aria-label="Cerrar panel del país">×</button>
      </header>
      <section aria-labelledby="h-curioso" className="country-curious">
        <h3 id="h-curioso">Lo curioso en {countryName(iso, name)}</h3>
        {!profile && <p className="muted">Cargando…</p>}
        {profile?.sin_datos && (
          <p className="nodata-note">
            <strong>Sin datos.</strong> Wikimedia no publica rankings de este país (por privacidad o poco tráfico), o no está entre los
            países descargados. No significa que no haya interés.
          </p>
        )}
        {profile && !profile.sin_datos && (
          <>
            <CuriosityList items={profile.curiosidades} onTopic={onTopic} hideCountries />
            <p className="muted small">
              {profile.dias_observados} días observados entre {profile.desde} y {profile.hasta} · rankings diarios de Wikimedia · aproximado.
            </p>
          </>
        )}
      </section>

      <h3>Lo más leído en {period.tipo === 'mes' ? periodLabel(period.id) : `el día ${periodLabel(period.id)}`}</h3>
      <p className="source">
        Fuente: rankings diarios por país de Wikimedia (top-per-country). Cifras <strong>aproximadas</strong>: Wikimedia las redondea por
        privacidad y omite artículos con pocas visitas.
        {period.tipo === 'mes' && ` Mes construido con ${period.dias_muestreados.length} días observados (días ${listFmt.format(period.dias_muestreados.map((d) => String(Number(d.slice(8)))))}), no con el mes completo.`}
      </p>
      {err && <p role="alert">No se pudo cargar: {err}</p>}
      {!data && !err && <p className="muted">Cargando…</p>}
      {data?.sin_datos && (
        <p className="nodata-note">
          <strong>Sin datos</strong> para este país en este periodo. Wikimedia no publica ranking para países con poco tráfico o protegidos,
          o el país no está en la lista descargada (config/countries.yaml). No significa que no haya interés.
        </p>
      )}
      {data && !data.sin_datos && (
        <>
          <p className="muted small">
            Visitas diarias promedio en los días observados. {data.articulos_en_ranking} artículos en el ranking (sin portadas ni páginas especiales).
          </p>
          <ol className="toplist">
            {data.articulos.map((a) => (
              <li key={a.proyecto + a.articulo} value={a.puesto}>
                <div className="toprow">
                  {a.tema ? (
                    <button className="link strong" onClick={() => onTopic(a.tema!)}>{a.articulo}</button>
                  ) : (
                    <a href={wikiUrl(a.proyecto, a.articulo)} target="_blank" rel="noreferrer">{a.articulo}</a>
                  )}
                  <span className="num">≈ {num(a.visitas_diarias_aprox)}</span>
                </div>
                <div className="muted small">
                  {a.proyecto.replace('.wikipedia', '')} · presente {a.dias_presente} de {data.dias} días
                  {a.tema && <> · tema del observatorio: {topicNames[a.tema] ?? a.tema}</>}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { api, reportUrl, STATIC, type Finding, type Meta } from '../api'
import { lang, pct } from '../lib/format'
import type { TopicJob } from './TopicJobs'

type Props = { meta: Meta; onClose: () => void; onQueued: (job: TopicJob) => void }

/** Diálogo "Acerca de los datos": fuentes, limitaciones en lenguaje simple, hallazgos y agregar temas. */
export default function About({ meta, onClose, onQueued }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [findings, setFindings] = useState<Finding[]>([])
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    const d = ref.current!
    // Esc dispara "cancel": se cierra desmontando el componente (una sola fuente de verdad: el estado de App).
    const cancel = (e: Event) => {
      e.preventDefault()
      onCloseRef.current()
    }
    d.addEventListener('cancel', cancel)
    if (!d.open) d.showModal()
    return () => d.removeEventListener('cancel', cancel)
  }, [])
  useEffect(() => {
    api.findings().then((f) => setFindings(f.sorprendentes), () => {})
  }, [])
  const ms = meta.proporcion_movil.en ?? {}
  const years = Object.keys(ms).sort()

  return (
    <dialog ref={ref} className="about" aria-labelledby="about-title">
      <div className="about-inner">
        <header className="panel-head">
          <h2 id="about-title">Acerca de los datos</h2>
          <button className="icon" onClick={() => onClose()} aria-label="Cerrar">×</button>
        </header>
        {meta.demo && <p className="demo-note">Estás viendo DATOS SINTÉTICOS de prueba. No describen la realidad.</p>}

        <h3>Qué muestra cada vista</h3>
        <ul>
          <li><strong>Globo y mapa</strong>: los rankings diarios de artículos más vistos <em>por país</em> que publica Wikimedia desde 2021. Son <strong>aproximados</strong>: vienen redondeados y omiten artículos con pocas visitas. Para cada mes se observan algunos días (muestreo), no todos.</li>
          <li><strong>Panel del tema</strong>: las visitas de personas (sin bots identificados) a los artículos de cada <em>edición de idioma</em> desde julio de 2015. Son <strong>exactas</strong>, pero no dicen desde qué país se leyeron.</li>
          <li>Un idioma no equivale a un país: el español se lee en más de 20 países, y el inglés en todo el mundo.</li>
          <li>Gris rayado o «sin datos» significa que no hay información, nunca «cero interés».</li>
          <li><strong>Búsqueda en Wikipedia</strong>: cualquier artículo, con sus visitas consultadas en vivo a Wikimedia desde tu navegador
            (Wikimedia ve tu búsqueda, como al usar Wikipedia). Son datos sin analizar: sin picos, estacionalidad ni datos por país.</li>
        </ul>

        <h3>Limitaciones</h3>
        <ul>{meta.limitaciones.map((l) => <li key={l}>{l}</li>)}</ul>
        {years.length > 1 && (
          <p className="muted">Ejemplo: en Wikipedia en inglés, la proporción de visitas desde móviles fue {pct(ms[years[0]])} en {years[0]} y {pct(ms[years[years.length - 1]])} en {years[years.length - 1]}.</p>
        )}

        {findings.length > 0 && (
          <>
            <h3>Hallazgos sorprendentes</h3>
            <ol>{findings.map((f) => <li key={f.id}><strong>{f.titulo}.</strong> {f.texto}</li>)}</ol>
            {meta.reporte_disponible && <p><a href={reportUrl} target="_blank" rel="noreferrer">Abrir el reporte completo</a></p>}
          </>
        )}

        <h3>Fuentes y licencias</h3>
        <ul>
          {meta.fuentes.map((f) => (
            <li key={f.id}>
              {f.url ? <a href={f.url} target="_blank" rel="noreferrer">{f.nombre}</a> : f.nombre}
              {f.licencia && ` — ${f.licencia}`}
              {f.estado && ` — ${f.estado}`}
            </li>
          ))}
          <li>Globo: globe.gl y three.js (licencia MIT).</li>
        </ul>
        <p className="muted small">Idiomas analizados: {meta.idiomas.map(lang).join(', ')}. Datos generados el {meta.generado.slice(0, 10)}.</p>

        {STATIC ? (
          <p className="muted small">
            Esta es la versión pública de solo lectura: se actualiza sola cada día. Para agregar temas, edita
            config/topics.yaml en el repositorio o usa la versión local con la API.
          </p>
        ) : (
          <AddTopic onQueued={onQueued} />
        )}
      </div>
    </dialog>
  )
}

function AddTopic({ onQueued }: { onQueued: (job: TopicJob) => void }) {
  const [nombre, setNombre] = useState('')
  const [titulo, setTitulo] = useState('')
  const [idioma, setIdioma] = useState('es')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [queued, setQueued] = useState<number | null>(null)
  const [perm, setPerm] = useState(() => ('Notification' in window ? Notification.permission : 'denied'))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setStatus('Enviando…')
    try {
      const wikidata = /^Q\d+$/.test(titulo.trim()) ? titulo.trim() : undefined
      const { job, tema, estimado } = await api.addTopic({ nombre, titulo: wikidata ? undefined : titulo, idioma, wikidata })
      onQueued({ job, tema, nombre: nombre.trim(), estado: 'en cola', transcurrido: 0, estimado, delante: 0 })
      setQueued(Math.max(1, Math.round(estimado / 60)))
      setStatus(null)
      setNombre('')
      setTitulo('')
    } catch (err) {
      setStatus(String((err as Error).message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="addtopic" onSubmit={submit}>
      <h3>Agregar tema</h3>
      <p className="muted small">
        Se agrega a config/topics.yaml y la API descarga sus datos (con caché y pausas), recalcula el análisis y actualiza la exportación.
        Los rankings por país del tema se cruzan con lo ya descargado. Puede tardar algunos minutos.
      </p>
      <label>Nombre en español <input required minLength={2} value={nombre} onChange={(e) => setNombre(e.target.value)} /></label>
      <label>Título exacto del artículo en Wikipedia, o id de Wikidata (Q…) <input required value={titulo} onChange={(e) => setTitulo(e.target.value)} /></label>
      <label>Edición del título
        <select value={idioma} onChange={(e) => setIdioma(e.target.value)}>
          {['es', 'en', 'pt', 'fr', 'de', 'it'].map((l) => <option key={l} value={l}>{lang(l)}</option>)}
        </select>
      </label>
      <button type="submit" disabled={busy}>Agregar</button>
      {status && <p role="status" className="muted small">{status}</p>}
      {queued !== null && (
        <div className="addtopic-ok" role="status">
          <p>Recibido. Suele tardar unos {queued} {queued === 1 ? 'minuto' : 'minutos'}: se descargan sus visitas desde 2015 en 10 idiomas,
            se recalcula el análisis y se actualiza el sitio. Puedes cerrar esta ventana y seguir navegando: abajo a la derecha verás el avance
            y un aviso cuando esté listo.</p>
          {perm === 'default' && (
            <button type="button" className="link" onClick={() => Notification.requestPermission().then(setPerm, () => {})}>
              Avisarme también con una notificación del navegador
            </button>
          )}
          {perm === 'granted' && <p className="muted small">Te llegará una notificación del navegador aunque estés en otra pestaña.</p>}
        </div>
      )}
    </form>
  )
}

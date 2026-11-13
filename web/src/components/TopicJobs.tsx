import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

/** Un tema que alguien agregó desde este navegador y que el servidor está procesando. */
export type TopicJob = {
  job: string; tema: string; nombre: string; estado: string; transcurrido: number; estimado: number; delante: number
  error?: string | null; visto?: boolean
}

const KEY = 'curiosity.temas-en-proceso'
const DONE = new Set(['listo', 'error'])
const ETAPA: Record<string, string> = {
  'en cola': 'en la fila', descargando: 'descargando datos de Wikipedia', analizando: 'recalculando el análisis',
  exportando: 'actualizando el sitio',
}
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const mins = (s: number) => (s < 90 ? '1 minuto' : `${Math.round(s / 60)} minutos`)

function load(): TopicJob[] {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '[]') } catch { return [] }
}
function save(jobs: TopicJob[]) {
  try { localStorage.setItem(KEY, JSON.stringify(jobs)) } catch { /* sin almacenamiento: el aviso dura mientras la página esté abierta */ }
}

function notify(title: string, body: string) {
  try {
    if ('Notification' in window && Notification.permission === 'granted') new Notification(title, { body })
  } catch { /* algunos navegadores no permiten notificaciones desde esta página */ }
}

/** Estado de los temas en proceso: sobrevive a cerrar el diálogo y a recargar la página (se guarda en este navegador). */
export function useTopicJobs(onReady: () => void) {
  const [jobs, setJobs] = useState<TopicJob[]>(load)
  const onReadyRef = useRef(onReady)
  onReadyRef.current = onReady
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs
  useEffect(() => save(jobs), [jobs])

  const pending = jobs.some((j) => !DONE.has(j.estado))
  useEffect(() => {
    if (!pending) return
    let stop = false
    const tick = async () => {
      const current = jobsRef.current.filter((j) => !DONE.has(j.estado))
      const updates = await Promise.all(current.map(async (j) => {
        try {
          const r = await api.job(j.job)
          return { ...j, estado: r.estado, transcurrido: r.transcurrido, estimado: r.estimado, delante: r.delante, error: r.error }
        } catch (e) {
          return { ...j, estado: 'error', error: e instanceof Error ? e.message : 'Se perdió el contacto con el servidor.' }
        }
      }))
      if (stop) return
      // Las transiciones se detectan aquí (no dentro de setJobs, que React puede aplicar más tarde).
      const before = new Map(jobsRef.current.map((j) => [j.job, j.estado]))
      let ready = false
      for (const u of updates) {
        const prev = before.get(u.job)
        if (u.estado === 'listo' && prev !== 'listo') { ready = true; notify('Tema agregado', `«${u.nombre}» ya está en el observatorio.`) }
        if (u.estado === 'error' && prev !== 'error') notify('No se pudo agregar el tema', `«${u.nombre}»: ${u.error ?? 'error'}`)
      }
      setJobs((all) => all.map((j) => updates.find((x) => x.job === j.job) ?? j))
      if (ready) onReadyRef.current()
    }
    tick()
    const t = setInterval(tick, 3000)
    return () => { stop = true; clearInterval(t) }
  }, [pending])

  // Título de la pestaña: avisa también si la página está en segundo plano.
  useEffect(() => {
    const unseen = jobs.filter((j) => j.estado === 'listo' && !j.visto).length
    document.title = pending ? '… Curiosity' : unseen ? `(${unseen}) Curiosity` : 'Curiosity'
  }, [jobs, pending])

  const add = useCallback((j: TopicJob) => setJobs((all) => [...all.filter((x) => x.job !== j.job), j]), [])
  const dismiss = useCallback((id: string) => setJobs((all) => all.filter((x) => x.job !== id)), [])
  return { jobs, add, dismiss }
}

/** Aviso fijo abajo a la derecha: avance de cada tema y «listo» con acceso directo. */
export function TopicJobsNotice({ jobs, onOpen, onDismiss }: { jobs: TopicJob[]; onOpen: (tema: string) => void; onDismiss: (job: string) => void }) {
  if (!jobs.length) return null
  return (
    <div className="jobs-notice" role="status" aria-live="polite">
      {jobs.map((j) => (
        <div key={j.job} className={`jobs-item ${j.estado === 'listo' ? 'ok' : j.estado === 'error' ? 'bad' : ''}`}>
          {j.estado === 'listo' ? (
            <p>«{j.nombre}» ya está en el observatorio. <span className="muted">Tardó {mmss(j.transcurrido)}.</span></p>
          ) : j.estado === 'error' ? (
            <p>No se pudo agregar «{j.nombre}»: {j.error ?? 'error desconocido'}</p>
          ) : (
            <p>
              Agregando «{j.nombre}» · {ETAPA[j.estado] ?? j.estado}
              <span className="muted"> · {mmss(j.transcurrido)} de unos {mins(j.estimado)}{j.delante ? ` · ${j.delante} ${j.delante === 1 ? 'tema' : 'temas'} antes en la fila` : ''}</span>
            </p>
          )}
          <div className="jobs-actions">
            {j.estado === 'listo' && <button className="link" onClick={() => { onOpen(j.tema); onDismiss(j.job) }}>Ver tema</button>}
            {DONE.has(j.estado) && <button className="link" onClick={() => onDismiss(j.job)} aria-label={`Cerrar aviso de «${j.nombre}»`}>Cerrar</button>}
          </div>
        </div>
      ))}
    </div>
  )
}

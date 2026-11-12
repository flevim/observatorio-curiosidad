import { useMemo, useState } from 'react'
import type { DisputeArticle, Disputes } from '../api'
import { dateLabel, lang, num } from '../lib/format'

const fmtDay = (iso: string) => dateLabel(iso.slice(0, 10))
const veces = (a: DisputeArticle) =>
  a.nuevo ? 'artículo nuevo' : a.veces ? `${num(a.veces, 1)} × lo habitual` : 'antes: ninguna revertida'

/** Sección «Bajo disputa»: ranking automático de artículos con más ediciones revertidas de lo habitual. */
export default function DisputeView({ data }: { data: Disputes }) {
  const [filter, setFilter] = useState<string>('todos')
  const [selId, setSelId] = useState<string | null>(null)
  const items = useMemo(() => data.articulos.filter((a) => filter === 'todos' || a.idioma === filter), [data, filter])
  const ranked = items.filter((a) => !a.nuevo)
  const nuevos = items.filter((a) => a.nuevo)
  const sel = items.find((a) => a.id === selId) ?? ranked[0] ?? nuevos[0] ?? null
  const langs = data.idiomas.filter((l) => data.articulos.some((a) => a.idioma === l))

  const pick = (a: DisputeArticle) => {
    setSelId(a.id)
    if (window.matchMedia('(max-width: 767px)').matches) document.getElementById('disp-detail')?.scrollIntoView({ block: 'start' })
  }
  const row = (a: DisputeArticle) => (
    <li key={a.id}>
      <button className={a.id === sel?.id ? 'on' : ''} aria-pressed={a.id === sel?.id} onClick={() => pick(a)}>
        <span className="pp-title">{a.titulo}</span>
        <span className="pp-meta">{a.idioma} · {a.revertidas_semana} revertidas de {a.ediciones_semana} · {veces(a)}</span>
      </button>
    </li>
  )

  return (
    <div className="disp-view">
      <section className="disp-side" aria-labelledby="disp-title">
        <p className="kicker"><span className="rule" aria-hidden="true" />Semana del {fmtDay(data.semana.inicio)} al {fmtDay(data.semana.fin)} · UTC</p>
        <h2 id="disp-title" className="prop-side-title">Bajo <em>disputa</em></h2>
        <p className="hero-lede">Artículos de Wikipedia con muchas más ediciones revertidas de lo habitual. Todo sale de datos públicos y cada número enlaza a su fuente.</p>
        <div className="seg disp-langs" role="group" aria-label="Idioma">
          {['todos', ...langs].map((l) => (
            <button key={l} aria-pressed={filter === l} onClick={() => setFilter(l)}>{l === 'todos' ? 'Todos' : l}</button>
          ))}
        </div>
        {ranked.length > 0 ? <ol className="prop-pick disp-pick">{ranked.map(row)}</ol>
          : <p className="hint">Esta semana ningún artículo superó las reglas en este idioma.</p>}
        {nuevos.length > 0 && (
          <>
            <h3 className="disp-sub">Creados esta semana</h3>
            <p className="muted small">No tienen días anteriores con qué comparar; se ordenan por cantidad de revertidas.</p>
            <ol className="prop-pick disp-pick">{nuevos.map(row)}</ol>
          </>
        )}
        <details className="disp-method">
          <summary>Cómo se calcula</summary>
          <ul>
            <li>Una edición <b>revertida</b> es la que Wikipedia marcó después con la etiqueta <code>mw-reverted</code>: alguien la deshizo.</li>
            <li>Candidatos: los {data.reglas.candidatos_por_idioma} artículos con más ediciones revertidas en la semana (sin bots) en cada idioma: {data.idiomas.join(', ')}.</li>
            <li><b>Lo habitual</b> = ediciones revertidas por día en los días anteriores a la semana (hasta 83). Esperadas = 7 × lo habitual.</li>
            <li>Entra al ranking si tuvo al menos {data.reglas.min_revertidas} revertidas, al menos el triple de las esperadas y un puntaje ≥ {num(data.reglas.min_puntaje, 0)}. Puntaje = (observadas − esperadas) / √(esperadas + 1).</li>
            <li><b>Día en disputa</b>: ≥ 3 revertidas y ≥ 3 × lo habitual + 2.</li>
            <li><b>Entraba / salía</b>: texto que las ediciones revertidas agregaban o quitaban, copiado tal cual del diff de hasta {data.reglas.diffs_por_dia} ediciones por día. Se cuentan repeticiones exactas.</li>
            <li>Las protecciones y sus motivos se copian textuales del registro de Wikipedia.</li>
            <li>Mide conflicto, no intención: no sabemos quién editó ni si hubo coordinación.</li>
          </ul>
          <p className="muted small">Actualizado {data.generado.replace('T', ' ').slice(0, 16)} UTC.{data.avisos.map((a) => ` ${a}`).join('')}</p>
        </details>
      </section>

      <section id="disp-detail" className="disp-detail" aria-live="polite">
        {sel ? <Detail a={sel} semana={data.semana} /> : <p className="hint">Sin artículos para mostrar.</p>}
      </section>
    </div>
  )
}

function Detail({ a, semana }: { a: DisputeArticle; semana: Disputes['semana'] }) {
  return (
    <article>
      <p className="eyebrow">{lang(a.idioma)} · {a.idioma}.wikipedia</p>
      <h2 className="disp-title"><a href={a.enlace} target="_blank" rel="noreferrer">{a.titulo} ↗</a></h2>
      <p className="disp-summary">{a.resumen}</p>
      <p className="disp-links">
        <a href={a.historial} target="_blank" rel="noreferrer">Historial completo ↗</a>
        <a href={a.registro_protecciones} target="_blank" rel="noreferrer">Registro de protecciones ↗</a>
      </p>

      <Chart a={a} semana={semana} />

      <h3>Días en disputa</h3>
      {a.dias_disputa.length === 0 && <p className="muted">Las revertidas se repartieron en la semana: ningún día cumple la regla de «día en disputa».</p>}
      {a.dias_disputa.map((d) => (
        <section key={d.dia} className="disp-day">
          <h4>{dateLabel(d.dia)}</h4>
          {d.frases.filter((f) => !f.startsWith('Entraba') && !f.startsWith('Salía')).map((f) => <p key={f}>{f}</p>)}
          {(d.entraba.length > 0 || d.salia.length > 0) && (
            <div className="disp-frags">
              {d.entraba.length > 0 && <Frags title="Entraba" items={d.entraba} />}
              {d.salia.length > 0 && <Frags title="Salía" items={d.salia} />}
              <p className="muted small">Texto tal cual, del diff de {d.diffs_revisados} de {d.revertidas} ediciones revertidas ese día.</p>
            </div>
          )}
          {d.diffs_revisados === 0 && d.revertidas > 0 && (
            <p className="muted small">El texto de este día no se revisó: solo se leen los diffs de los 2 días con más revertidas de cada artículo. Las ediciones están enlazadas abajo.</p>
          )}
          {d.enlaces.length > 0 && (
            <details className="disp-diffs">
              <summary>Ver las ediciones revertidas ({d.enlaces.length}{d.revertidas > d.enlaces.length ? ` de ${d.revertidas}` : ''})</summary>
              <p>{d.enlaces.map((e) => <a key={e.url} href={e.url} target="_blank" rel="noreferrer">{e.hora} UTC</a>)}</p>
            </details>
          )}
        </section>
      ))}

      <h3>Protecciones en los últimos 90 días</h3>
      {a.protecciones.length === 0 ? <p className="muted">Ninguna.</p> : (
        <ul className="disp-prot">
          {a.protecciones.map((p, i) => (
            <li key={i}>
              <span className="disp-when">{p.fecha} UTC</span>
              <span><b>{p.accion}</b>{p.nivel ? <> · <code>{p.nivel}</code></> : null}</span>
              {p.motivo && <span className="disp-why">Motivo: «{p.motivo}»</span>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">Mide conflicto, no intención: no sabemos quién editó ni si hubo coordinación. Los motivos de protección los escriben los administradores de Wikipedia.</p>
    </article>
  )
}

function Frags({ title, items }: { title: string; items: { texto: string; veces: number }[] }) {
  return (
    <div>
      <p className="disp-frag-h">{title}</p>
      <ul className="disp-frag-list">
        {items.map((f) => <li key={f.texto}><code>{f.texto}</code>{f.veces > 1 && <span className="muted"> × {f.veces}</span>}</li>)}
      </ul>
    </div>
  )
}

/** Visitas (arriba, escala raíz) y ediciones por día (abajo; en rosa, las revertidas después). */
function Chart({ a, semana }: { a: DisputeArticle; semana: Disputes['semana'] }) {
  const W = 640, X0 = 8, PW = W - 16, n = a.serie.length, bw = PW / n
  const vmax = Math.max(1, ...a.serie.map((s) => s[3] ?? 0))
  const emax = Math.max(1, ...a.serie.map((s) => s[1]))
  const x = (i: number) => X0 + i * bw
  const idx = (day: string) => a.serie.findIndex((s) => s[0] === day.slice(0, 10))
  let path = ''
  a.serie.forEach((s, i) => {
    if (s[3] == null) return
    path += `${path ? 'L' : 'M'}${(x(i) + bw / 2).toFixed(1)} ${(96 - 76 * Math.sqrt(s[3] / vmax)).toFixed(1)}`
  })
  const ws = idx(semana.inicio)
  const months = a.serie.map((s, i) => [s[0], i] as const).filter(([d]) => d.endsWith('-01'))
  const totalViews = a.serie.reduce((t, s) => t + (s[3] ?? 0), 0)
  return (
    <figure className="disp-chart">
      <svg viewBox={`0 0 ${W} 250`} role="img" aria-label={`${a.titulo}: visitas y ediciones diarias en 90 días. Máximo de visitas ${num(vmax)} en un día; máximo de ediciones ${emax}.`}>
        {ws >= 0 && <rect x={x(ws)} y={10} width={(n - ws) * bw} height={210} className="disp-week" />}
        <text x={X0} y={20} className="disp-lbl">Visitas por día · máx. {num(vmax)}</text>
        <path d={path} className="disp-views" />
        <text x={X0} y={124} className="disp-lbl">Ediciones por día · máx. {emax}</text>
        {a.serie.map((s, i) => {
          if (!s[1]) return null
          const h = 82 * s[1] / emax, hr = 82 * s[2] / emax
          return (
            <g key={s[0]}>
              <rect x={x(i) + 0.3} y={218 - h} width={Math.max(1, bw - 0.6)} height={h - hr} className="disp-ed" />
              {s[2] > 0 && <rect x={x(i) + 0.3} y={218 - hr} width={Math.max(1, bw - 0.6)} height={hr} className="disp-rev" />}
            </g>
          )
        })}
        <line x1={X0} x2={X0 + PW} y1={218} y2={218} className="disp-axis" />
        {a.protecciones.map((p, i) => {
          const j = idx(p.fecha)
          return j < 0 ? null : <line key={i} x1={x(j) + bw / 2} x2={x(j) + bw / 2} y1={10} y2={218} className="disp-prot-line" />
        })}
        {months.map(([d, i]) => <text key={d} x={x(i)} y={238} className="disp-lbl">{dateLabel(d).split(' de ')[1] ?? d}</text>)}
      </svg>
      <figcaption className="disp-legend">
        <span><i className="sw ed" />edición que se quedó</span>
        <span><i className="sw rev" />revertida después</span>
        <span><i className="sw prot" />protección</span>
        <span><i className="sw week" />semana analizada</span>
        <span className="muted">Visitas en 90 días: {num(totalViews)} · escala raíz</span>
      </figcaption>
    </figure>
  )
}

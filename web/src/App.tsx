import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { geoCentroid } from 'd3-geo'
import { api, type PropArticle, type Propagation, type Disputes, type CountryFeature, type GeoJSON, type GlobeData, type Graph, type Meta } from './api'
import About from './components/About'
import CountryPanel from './components/CountryPanel'
import CountryTable from './components/CountryTable'
import FlatMap from './components/FlatMap'
import Hero from './components/Hero'
import ExplorePanel from './components/ExplorePanel'
import PropagationPanel, { PROP_NEW, PROP_OLD, PROP_WAIT, propDays } from './components/PropagationPanel'
import { PropagationList, PropagationTimeline } from './components/PropagationView'
import DisputeView from './components/DisputeView'
import type { Arc } from './components/GlobeView'
import Legend from './components/Legend'
import SearchBox from './components/SearchBox'
import Timeline from './components/Timeline'
import TopicPanel from './components/TopicPanel'
import { compact, countryName, num, periodLabel, prefersReducedMotion } from './lib/format'
import { buildScale, countryState, type CountryState } from './lib/scale'

const GlobeView = lazy(() => import('./components/GlobeView'))

type View = 'globo' | 'mapa' | 'tabla' | 'propagacion' | 'disputa'
type Panel = { kind: 'topic' } | { kind: 'country'; iso: string; name: string } | { kind: 'explore'; query: string } | null

// Estado inicial leído una sola vez desde el enlace (#tema=…&periodo=…&pais=…&vista=…).
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1))
  return { tema: p.get('tema'), periodo: p.get('periodo'), pais: p.get('pais'), vista: p.get('vista') as View | null }
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [geo, setGeo] = useState<GeoJSON | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initial] = useState(readHash)

  const [topic, setTopic] = useState<string | null>(initial.tema)
  const [trail, setTrail] = useState<string[]>(initial.tema ? [initial.tema] : [])
  const [kind, setKind] = useState<'mes' | 'dia'>(initial.periodo && initial.periodo.length === 10 ? 'dia' : 'mes')
  const [periodId, setPeriodId] = useState<string | null>(initial.periodo)
  const [playing, setPlaying] = useState(false)
  const [panel, setPanel] = useState<Panel>(initial.tema ? { kind: 'topic' } : null)
  const [selected, setSelected] = useState<string | null>(initial.pais)
  const [view, setView] = useState<View>(initial.vista ?? 'globo')
  const [about, setAbout] = useState(false)
  const [sheet, setSheet] = useState<'peek' | 'full'>('peek')
  const [reduced, setReduced] = useState(prefersReducedMotion())
  // El globo gira al inicio; con «reducir movimiento» parte quieto, pero el botón permite activarlo.
  const [rotate, setRotate] = useState(() => !prefersReducedMotion())

  const [todayIsos, setTodayIsos] = useState<string[]>([])
  const [volume, setVolume] = useState<GlobeData | null>(null)
  const [topicData, setTopicData] = useState<GlobeData | null>(null)

  const loadMeta = useCallback(() => {
    api.meta().then(setMeta, (e) => setError(String(e.message ?? e)))
    api.graph().then(setGraph, () => {})
  }, [])
  useEffect(() => {
    loadMeta()
    api.geo('110m').then(setGeo, (e) => setError(String(e.message ?? e)))
    api.globe('periodo').then(setVolume, () => setVolume({ periodos: [], metrica: '', valores: {} }))
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [loadMeta])

  // Países con curiosidades en el último día: se marcan con un punto en el globo.
  useEffect(() => {
    api.dailyIndex().then((d) => d.dias[0] && api.curiosities(d.dias[0].fecha)).then(
      (day) => day && setTodayIsos([...new Set(day.curiosidades.flatMap((c) => c.paises ?? []))]),
      () => {},
    )
  }, [])
  const highlights = useMemo(() => {
    if (!geo) return []
    return todayIsos.flatMap((iso) => {
      const f = geo.features.find((x) => x.properties.iso === iso)
      if (!f) return []
      const [lng, lat] = geoCentroid(f as never)
      return [{ iso, lat, lng, label: `<b>${countryName(iso)}</b><br/><small>con curiosidades del día</small>` }]
    })
  }, [geo, todayIsos])

  // Modo propagación: el globo colorea por día de llegada y dibuja arcos desde el país de origen.
  const [propDay, setPropDay] = useState(0)
  const [propData, setPropData] = useState<Propagation | null>(null)
  const [propSelId, setPropSelId] = useState<string | null>(null)
  useEffect(() => {
    if (view === 'propagacion' && !propData) api.propagation().then((d) => setPropData(d ?? { dias: [], articulos: [] }), () => {})
  }, [view, propData])
  const [dispData, setDispData] = useState<Disputes | null | undefined>(undefined)
  useEffect(() => {
    if (view === 'disputa' && dispData === undefined) api.disputes().then((d) => setDispData(d), () => setDispData(null))
  }, [view, dispData])
  const propArt =
    view === 'propagacion' && propData?.articulos.length
      ? propData.articulos.find((a) => a.id === propSelId) ?? propData.articulos[0]
      : null
  const propOverride = useMemo(() => {
    if (!propArt || !geo) return null
    const days = propDays(propArt)
    const day = days[Math.min(propDay, days.length - 1)]
    const conDatos = new Set(meta?.paises_con_datos ?? [])
    const cent = (iso: string) => {
      const f = geo.features.find((x) => x.properties.iso === iso)
      return f ? geoCentroid(f as never) : null
    }
    const o = cent(propArt.origen)
    const arcs: Arc[] = []
    if (o) {
      for (const [iso, p] of Object.entries(propArt.paises)) {
        if (iso === propArt.origen || p.dia > day) continue
        const c = cent(iso)
        if (c) arcs.push({ startLng: o[0], startLat: o[1], endLng: c[0], endLat: c[1], color: p.dia === day ? PROP_NEW : 'rgba(42,157,182,0.55)' })
      }
    }
    return {
      color: (iso: string | null) => {
        if (!iso) return null
        const p = propArt.paises[iso]
        if (p && p.dia <= day) return p.dia === day ? PROP_NEW : PROP_OLD
        return conDatos.has(iso) ? PROP_WAIT : null
      },
      arcs,
      focus: o ? { lat: o[1], lng: o[0] } : null,
    }
  }, [propArt, propDay, geo, meta])

  useEffect(() => {
    if (!topic) return setTopicData(null)
    api.globe(topic).then(setTopicData, () => setTopicData(null))
  }, [topic])

  const periods = useMemo(() => (meta?.periodos ?? []).filter((p) => p.tipo === kind), [meta, kind])
  // El periodo se guarda por id: si no existe en la lista actual (o no hay ninguno elegido), se usa el último.
  const found = periodId ? periods.findIndex((p) => p.id === periodId) : -1
  const idx = found >= 0 ? found : periods.length - 1
  const setIdx = useCallback((i: number) => setPeriodId(periods[i]?.id ?? null), [periods])
  const period = idx >= 0 ? periods[idx] : undefined
  const globalIdx = period && volume ? volume.periodos.indexOf(period.id) : -1

  const topicMode = !!topic && !!topicData
  const active = topicMode ? topicData : volume
  const scale = useMemo(() => {
    if (!active) return null
    return topicMode
      ? buildScale(active, '‰', (v) => num(v, v < 1 ? 2 : 1))
      : buildScale(active, 'visitas/día', compact)
  }, [active, topicMode])

  const stateFor = useCallback(
    (iso: string | null): CountryState => countryState(iso, globalIdx, active, volume, scale, topicMode),
    [globalIdx, active, volume, scale, topicMode],
  )

  const topicNames = useMemo(() => Object.fromEntries((meta?.temas ?? []).map((t) => [t.id, t.nombre])), [meta])
  const describe = useCallback(
    (f: CountryFeature, s: CountryState) => {
      const name = countryName(f.properties.iso ?? '', f.properties.nombre)
      const per = period ? periodLabel(period.id) : ''
      let v = 'sin datos (no es cero)'
      if (s.kind === 'absent') v = `${topicNames[topic!] ?? ''} no aparece en el ranking`
      if (s.kind === 'value')
        v = topicMode
          ? `≈ ${num(s.value, 2)} de cada 1.000 visitas del ranking${s.rank ? ` · mejor puesto ${s.rank}` : ''}`
          : `≈ ${compact(s.value)} visitas/día en los artículos del ranking`
      return `<b>${name}</b><br/>${per}: ${v}<br/><small>aproximado · Wikimedia top-per-country</small>`
    },
    [period, topicMode, topic, topicNames],
  )

  // Estado en la URL para poder compartir o volver atrás.
  useEffect(() => {
    const p = new URLSearchParams()
    if (topic) p.set('tema', topic)
    if (period) p.set('periodo', period.id)
    if (selected) p.set('pais', selected)
    if (view !== 'globo') p.set('vista', view)
    history.replaceState(null, '', `#${p}`)
  }, [topic, period, selected, view])

  const goTopic = useCallback(
    (id: string, fromTrail = false) => {
      setTopic(id)
      setPanel({ kind: 'topic' })
      setSheet('peek')
      setTrail((t) => {
        if (fromTrail) return t.slice(0, t.indexOf(id) + 1)
        const i = t.indexOf(id)
        return i >= 0 ? t.slice(0, i + 1) : [...t, id].slice(-8)
      })
    },
    [],
  )

  const pickPropagation = useCallback((art: PropArticle) => {
    setPropSelId(art.id)
    setPropDay(0)
    setSheet('peek')
  }, [])
  const changeView = useCallback((v: View) => {
    setView(v)
    if (v === 'propagacion' || v === 'disputa') {
      setPanel(null)
      setSelected(null)
      setPlaying(false)
    }
  }, [])

  const explore = useCallback((query: string) => {
    setPanel({ kind: 'explore', query })
    setSheet('peek')
    setPlaying(false)
  }, [])

  const selectCountry = useCallback((iso: string | null, name: string) => {
    if (!iso) return
    setSelected(iso)
    setPanel({ kind: 'country', iso, name })
    setSheet('peek')
    setPlaying(false)
  }, [])

  if (error) return <div className="fatal"><h1>Observatorio de la Curiosidad</h1><p role="alert">No se pudieron cargar los datos: {error}</p><p>Ejecuta el pipeline (<code>python -m observatorio all</code>) y la API.</p></div>
  if (!meta || !geo) return <div className="loading" aria-busy="true">Cargando el observatorio…</div>

  const hasPeriods = !!period && globalIdx >= 0
  const isProp = view === 'propagacion'
  const isDisp = view === 'disputa'
  const isHome = !panel && view !== 'tabla' && !isProp && !isDisp
  const hasPanel = (!!panel && !isDisp) || (isProp && !!propArt)
  const pDays = propArt ? propDays(propArt) : []
  const pDay = pDays[Math.min(propDay, pDays.length - 1)]
  const pArrived = propArt ? Object.values(propArt.paises).filter((p) => p.dia <= pDay).length : 0
  const pNew = propArt ? Object.values(propArt.paises).filter((p) => p.dia === pDay).length : 0
  const legendTitle = topicMode ? `«${topicNames[topic!]}» en los rankings por país` : 'Lectura de Wikipedia por país'
  const caption = hasPeriods
    ? `${topicMode ? 'Visitas al tema por cada 1.000 visitas del ranking del país' : 'Visitas diarias de los artículos del ranking'} · ${period.tipo === 'mes' ? `${periodLabel(period.id)} (${period.dias_muestreados.length} días muestreados)` : `día ${periodLabel(period.id)}`} · aproximado · Wikimedia`
    : 'Aún no se descargaron rankings por país.'

  return (
    <div className={`app${hasPanel ? ' has-panel' : ''}${isHome ? ' home' : ''}${isProp ? ' prop-view' : ''}${isDisp ? ' disp-mode' : ''}`} data-reduced-motion={reduced}>
      <div className="frame" aria-hidden="true" />
      <a href="#main-panel" className="skip">Saltar al panel</a>
      <header className="topbar">
        <div className="brand-wrap">
          <h1 className="brand">
            <button className="brand-btn" onClick={() => { setTopic(null); setTrail([]); setPanel(null); setSelected(null) }}>
              Curiosity<span className="dot">.</span>
            </button>
          </h1>
          <button className="howto" onClick={() => setAbout(true)}>
            Observatorio · Cómo funciona <span className="box" aria-hidden="true">?</span>
          </button>
        </div>
        <div className="top-right">
          {!isHome && <SearchBox topics={meta.temas} onPick={(id) => goTopic(id)} onExplore={explore} />}
          <span className="stamp">Datos al <b>{periodLabel(meta.curiosidades_dias?.[0] ?? meta.mes_final)}</b> · UTC</span>
          <div className="seg" role="group" aria-label="Vista">
            {(['globo', 'mapa', 'tabla', 'propagacion', 'disputa'] as View[]).map((v) => (
              <button key={v} aria-pressed={view === v} className={v === 'propagacion' || v === 'disputa' ? 'seg-accent' : undefined} onClick={() => changeView(v)}>
                {v === 'globo' ? 'Globo' : v === 'mapa' ? 'Mapa' : v === 'tabla' ? 'Tabla' : v === 'propagacion' ? 'Propagación' : 'Bajo disputa'}
              </button>
            ))}
          </div>
        </div>
      </header>

      {meta.demo && <p className="demo-banner" role="note">DATOS SINTÉTICOS DE PRUEBA: no describen la realidad.</p>}

      <nav className="crumbs" aria-label="Historial de temas">
        {trail.length > 0 && (
          <ol>
            <li><button className="link" onClick={() => { setTopic(null); setTrail([]); setPanel(null) }}>Inicio</button></li>
            {trail.map((id) => (
              <li key={id}>
                <button className="link" aria-current={id === topic ? 'page' : undefined} onClick={() => goTopic(id, true)}>{topicNames[id] ?? id}</button>
              </li>
            ))}
          </ol>
        )}
      </nav>

      <main className="stage" aria-label="Mapa de atención">
        {(view === 'globo' || isProp) && (
          <Suspense fallback={<div className="loading">Cargando globo…</div>}>
            <GlobeView
              geo={geo}
              stateFor={stateFor}
              describe={describe}
              selected={selected}
              onSelect={selectCountry}
              reducedMotion={reduced}
              rotate={rotate && !propArt}
              highlights={highlights}
              override={propOverride}
              colorKey={`${topic}|${globalIdx}|${!!topicData}|${!!volume}|${propArt?.id ?? ''}|${propDay}`}
            />
          </Suspense>
        )}
        {view === 'mapa' && <FlatMap geo={geo} stateFor={stateFor} describe={describe} selected={selected} onSelect={selectCountry} />}
        {view === 'tabla' && (
          <CountryTable
            isos={meta.paises_con_datos}
            stateFor={stateFor}
            valueLabel={topicMode ? '‰ del ranking' : 'Visitas/día (aprox.)'}
            topicMode={topicMode}
            onSelect={selectCountry}
            selected={selected}
          />
        )}
        {isHome && <Hero meta={meta} onTopic={(id) => goTopic(id)} onCountry={(iso) => selectCountry(iso, countryName(iso))} onExplore={explore} />}
        {isProp && propData && (
          propData.articulos.length ? (
            <PropagationList items={propData.articulos.slice(0, 20)} selectedId={propArt?.id ?? null} onSelect={pickPropagation} dias={propData.dias.length} />
          ) : <p className="hint prop-empty">Aún no hay artículos que hayan pasado por varios países en los días recientes.</p>
        )}
        {view === 'globo' && (
          <button className="rotate-toggle ghost" aria-pressed={rotate} onClick={() => setRotate(!rotate)}>
            {rotate ? 'Pausar giro' : 'Girar globo'}
          </button>
        )}
        {isDisp && (dispData ? <DisputeView data={dispData} />
          : <p className="hint prop-empty">{dispData === null ? 'Aún no hay datos de «Bajo disputa». Ejecuta: python -m observatorio disputa && python -m observatorio export' : 'Cargando…'}</p>)}
        <div className="overlay-bottom">
          {!propArt && !isDisp && <Legend scale={hasPeriods ? scale : null} title={legendTitle} topicMode={topicMode} caption={caption} />}
        </div>
      </main>

      <footer className="bottombar">
        {isDisp ? (
          <p className="disp-foot">Fuente: Wikipedia (historial de ediciones, registro de protecciones) y Wikimedia (visitas). Se actualiza cada día.</p>
        ) : isProp ? (
          <PropagationTimeline days={pDays} dayIdx={Math.min(propDay, Math.max(0, pDays.length - 1))} onDay={setPropDay}
            arrived={pArrived} nuevos={pNew} reducedMotion={reduced} />
        ) : (<>
        <Timeline periods={periods} index={Math.max(0, idx)} onIndex={setIdx} playing={playing} onPlaying={setPlaying} kind={kind} onKind={(k) => { setKind(k); setPlaying(false) }} />
        <label className="country-pick">
          <span className="sr-only">Elegir país</span>
          <select value={selected ?? ''} onChange={(e) => e.target.value && selectCountry(e.target.value, countryName(e.target.value))}>
            <option value="">País…</option>
            {[...meta.paises_con_datos].sort((a, b) => countryName(a).localeCompare(countryName(b), 'es')).map((iso) => (
              <option key={iso} value={iso}>{countryName(iso)}</option>
            ))}
          </select>
        </label>
        </>)}
      </footer>

      {hasPanel && (
        <aside id="main-panel" className={`panel sheet-${sheet}`} aria-labelledby="panel-title" tabIndex={-1}>
          <button
            className="sheet-handle"
            aria-label={sheet === 'peek' ? 'Expandir panel' : 'Contraer panel'}
            onClick={() => setSheet(sheet === 'peek' ? 'full' : 'peek')}
            onPointerDown={(e) => {
              const y0 = e.clientY
              const up = (ev: PointerEvent) => {
                const dy = ev.clientY - y0
                if (dy < -30) setSheet('full')
                else if (dy > 30) {
                  if (sheet === 'full') setSheet('peek')
                  else setPanel(null)
                }
                window.removeEventListener('pointerup', up)
              }
              window.addEventListener('pointerup', up)
            }}
          />
          {isProp && propArt && (
            <PropagationPanel
              art={propArt}
              dayIdx={propDay}
              onDay={setPropDay}
              reducedMotion={reduced}
              controls={false}
              onCountry={(iso) => { setView('globo'); selectCountry(iso, countryName(iso)) }}
              onTopic={(id) => { setView('globo'); goTopic(id) }}
              onClose={() => changeView('globo')}
            />
          )}
          {!isProp && panel?.kind === 'topic' && topic && (
            <TopicPanel
              topics={meta.temas}
              topicId={topic}
              graph={graph}
              periodLabel={period ? periodLabel(period.id) : ''}
              onNavigate={(id) => goTopic(id)}
              onClose={() => setPanel(null)}
              onSelectCountry={(iso) => selectCountry(iso, countryName(iso))}
            />
          )}
          {!isProp && panel?.kind === 'country' && period && (
            <CountryPanel
              iso={panel.iso}
              name={panel.name}
              period={period}
              topicNames={topicNames}
              onTopic={(id) => goTopic(id)}
              onClose={() => { setPanel(topic ? { kind: 'topic' } : null); setSelected(null) }}
            />
          )}
          {!isProp && panel?.kind === 'explore' && (
            <ExplorePanel
              query={panel.query}
              topics={meta.temas}
              onTopic={(id) => goTopic(id)}
              onClose={() => setPanel(topic ? { kind: 'topic' } : null)}
            />
          )}
          {!isProp && panel?.kind === 'country' && topic && (
            <button className="ghost back-topic" onClick={() => setPanel({ kind: 'topic' })}>← Volver a «{topicNames[topic]}»</button>
          )}
        </aside>
      )}

      {about && <About meta={meta} onClose={() => setAbout(false)} onTopicAdded={(id) => { loadMeta(); goTopic(id) }} />}
    </div>
  )
}

import { useEffect, useRef } from 'react'
import Globe from 'globe.gl'
import { MeshPhongMaterial, Color } from 'three'
import { geoCentroid } from 'd3-geo'
import type { CountryFeature, GeoJSON } from '../api'
import { api } from '../api'
import { SELECTED_STROKE, type CountryState, stateColor } from '../lib/scale'
import { countryName } from '../lib/format'

type Props = {
  geo: GeoJSON
  stateFor: (iso: string | null) => CountryState
  describe: (f: CountryFeature, s: CountryState) => string
  selected: string | null
  onSelect: (iso: string | null, name: string) => void
  reducedMotion: boolean
  rotate: boolean // preferencia de la persona (botón «Girar»)
  colorKey: string // cambia cuando cambian los colores (tema, periodo)
}

type GlobeInstance = InstanceType<typeof Globe>

const IDLE_RESUME_MS = 8000

export default function GlobeView({ geo, stateFor, describe, selected, onSelect, reducedMotion, rotate, colorKey }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const globe = useRef<GlobeInstance | null>(null)
  const lod = useRef<'110m' | '50m'>('110m')
  const latest = useRef({ stateFor, describe, selected, onSelect, rotate })
  latest.current = { stateFor, describe, selected, onSelect, rotate }
  const interacting = useRef(false)
  const idleTimer = useRef<number | undefined>(undefined)

  // Gira si la persona lo quiere, no hay un país seleccionado y no está arrastrando/haciendo zoom.
  const applyRotation = () => {
    const g = globe.current
    if (!g) return
    const on = latest.current.rotate && !latest.current.selected && !interacting.current
    g.controls().autoRotate = on
    if (host.current) host.current.dataset.autorotate = String(on)
  }

  // Crear el globo una sola vez.
  useEffect(() => {
    const el = host.current!
    const g = new Globe(el, { rendererConfig: { antialias: true, alpha: true, powerPreference: 'high-performance' } })
      .backgroundColor('rgba(0,0,0,0)')
      .showAtmosphere(true)
      .atmosphereColor('#3987e5')
      .atmosphereAltitude(0.16)
      .showGraticules(false)
      .polygonsData(geo.features)
      .polygonAltitude(0.006)
      .polygonSideColor(() => 'rgba(20,30,50,0.6)')
      .polygonStrokeColor(() => '#0b1220')
      .polygonsTransitionDuration(reducedMotion ? 0 : 250)
      .polygonLabel((d: object) => {
        const f = d as CountryFeature
        return latest.current.describe(f, latest.current.stateFor(f.properties.iso))
      })
      .onPolygonClick((d: object) => {
        const f = d as CountryFeature
        latest.current.onSelect(f.properties.iso, f.properties.nombre)
      })
      .onPolygonHover((d: object | null) => {
        el.style.cursor = d ? 'pointer' : 'grab'
      })
      .pointOfView({ lat: 15, lng: -40, altitude: 2.4 })
    const mat = g.globeMaterial() as MeshPhongMaterial
    mat.color = new Color('#0c1729')
    mat.emissive = new Color('#050a14')
    mat.shininess = 6
    const controls = g.controls()
    controls.autoRotateSpeed = 0.5
    controls.enableDamping = true
    controls.minDistance = 130
    controls.maxDistance = 600
    // Al interactuar se pausa el giro; se retoma tras unos segundos de quietud.
    const stop = () => {
      interacting.current = true
      window.clearTimeout(idleTimer.current)
      applyRotation()
    }
    const scheduleResume = () => {
      window.clearTimeout(idleTimer.current)
      idleTimer.current = window.setTimeout(() => {
        interacting.current = false
        applyRotation()
      }, IDLE_RESUME_MS)
    }
    const onWheel = () => {
      stop()
      scheduleResume()
    }
    el.addEventListener('pointerdown', stop)
    window.addEventListener('pointerup', scheduleResume)
    el.addEventListener('wheel', onWheel, { passive: true })

    // Menos detalle al alejarse: 1:110m lejos, 1:50m cerca.
    g.onZoom(({ altitude }) => {
      const want = altitude < 0.9 ? '50m' : '110m'
      if (want === lod.current) return
      lod.current = want
      ;(want === '50m' ? api.geo('50m') : Promise.resolve(geo)).then((gj) => {
        if (lod.current === want) g.polygonsData(gj.features)
      })
    })

    const resize = new ResizeObserver(() => g.width(el.clientWidth).height(el.clientHeight))
    resize.observe(el)
    // Pausar el render cuando la pestaña no está visible.
    const vis = () => (document.hidden ? g.pauseAnimation() : g.resumeAnimation())
    document.addEventListener('visibilitychange', vis)
    globe.current = g
    applyRotation()
    return () => {
      window.clearTimeout(idleTimer.current)
      window.removeEventListener('pointerup', scheduleResume)
      resize.disconnect()
      document.removeEventListener('visibilitychange', vis)
      el.removeEventListener('pointerdown', stop)
      el.removeEventListener('wheel', onWheel)
      g._destructor?.()
      el.innerHTML = ''
      globe.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Reaplicar colores cuando cambian tema, periodo o selección.
  useEffect(() => {
    const g = globe.current
    if (!g) return
    g.polygonCapColor((d: object) => stateColor(latest.current.stateFor((d as CountryFeature).properties.iso)))
      .polygonStrokeColor((d: object) => ((d as CountryFeature).properties.iso === selected ? SELECTED_STROKE : '#0b1220'))
      .polygonAltitude((d: object) => ((d as CountryFeature).properties.iso === selected ? 0.03 : 0.006))
  }, [colorKey, selected])

  useEffect(() => {
    applyRotation()
    globe.current?.polygonsTransitionDuration(reducedMotion ? 0 : 250)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, selected, rotate])

  // Acercar la cámara al país seleccionado.
  useEffect(() => {
    const g = globe.current
    if (!g || !selected) return
    const f = geo.features.find((x) => x.properties.iso === selected)
    if (!f) return
    const [lng, lat] = geoCentroid(f as never)
    g.pointOfView({ lat, lng, altitude: Math.min(g.pointOfView().altitude, 1.5) }, reducedMotion ? 0 : 1100)
  }, [selected, geo, reducedMotion])

  return (
    <div
      ref={host}
      className="globe"
      role="img"
      aria-label={`Globo terráqueo interactivo${selected ? `, país seleccionado: ${countryName(selected)}` : ''}. Usa la vista de mapa plano o de tabla para navegar con teclado.`}
    />
  )
}

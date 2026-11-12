import { useState } from 'react'
import { api, STATIC, type TrendingItem } from '../api'
import { lang as langName, num } from '../lib/format'
import { LANGS } from '../lib/wikipedia'

const REPO = import.meta.env.VITE_REPO_URL ?? 'https://github.com/flevim/observatorio-curiosidad'

type Props = {
  data: Record<string, TrendingItem[]>
  showDays?: boolean // en el resumen semanal: cuántos días estuvo en la lista
  limit?: number
  onTopic: (id: string) => void
  onExplore: (q: string) => void
}

/** Lo más leído en una edición de Wikipedia, con acciones: ver el tema, explorar en vivo o agregarlo como tema. */
export default function TrendingList({ data, showDays, limit = 15, onTopic, onExplore }: Props) {
  const langs = LANGS.filter((l) => data[l]?.length)
  const [lang, setLang] = useState(langs.includes('es') ? 'es' : langs[0])
  const [status, setStatus] = useState<Record<string, string>>({})
  if (!langs.length) return <p className="muted pad">Sin datos de lo más leído todavía.</p>
  const items = (data[lang] ?? []).slice(0, limit)

  const add = async (a: TrendingItem) => {
    setStatus((s) => ({ ...s, [a.articulo]: 'Enviando…' }))
    try {
      const r = await api.addTopic({ nombre: a.articulo, titulo: a.articulo, idioma: lang })
      setStatus((s) => ({ ...s, [a.articulo]: `Agregado como «${r.tema}»; se está descargando.` }))
    } catch (e) {
      setStatus((s) => ({ ...s, [a.articulo]: String((e as Error).message) }))
    }
  }
  const issue = (a: TrendingItem) =>
    `${REPO}/issues/new?${new URLSearchParams({
      title: `Proponer tema: ${a.articulo}`,
      body: `Propongo agregar este tema (estuvo entre lo más leído de ${lang}.wikipedia).\n\n- Artículo: ${a.url}\n\nLínea para config/topics.yaml:\n\n    - {id: …, nombre: ${a.articulo}, semilla: {idioma: ${lang}, titulo: ${a.articulo}}}`,
    })}`

  return (
    <div className="trending">
      <label className="check pad-x">
        Edición{' '}
        <select value={lang} onChange={(e) => setLang(e.target.value)}>
          {langs.map((l) => <option key={l} value={l}>{langName(l)}</option>)}
        </select>
      </label>
      <ol className="trend-list">
        {items.map((a) => (
          <li key={a.articulo}>
            <div className="toprow">
              <a href={a.url} target="_blank" rel="noreferrer" lang={lang}>{a.articulo} ↗</a>
              <span className="num">{num(a.visitas)}</span>
            </div>
            <ul className="f-links">
              {showDays && a.dias != null && <li className="muted">{a.dias} {a.dias === 1 ? 'día' : 'días'} en la lista</li>}
              {a.tema ? (
                <li><button className="link" onClick={() => onTopic(a.tema!)}>Ver el tema</button></li>
              ) : (
                <>
                  <li><button className="link" onClick={() => onExplore(a.articulo)}>Explorar</button></li>
                  <li>
                    {STATIC ? (
                      <a href={issue(a)} target="_blank" rel="noreferrer">Proponer como tema ↗</a>
                    ) : (
                      <button className="link" onClick={() => add(a)} disabled={!!status[a.articulo]}>Agregar como tema</button>
                    )}
                  </li>
                </>
              )}
            </ul>
            {status[a.articulo] && <p className="muted small" role="status">{status[a.articulo]}</p>}
          </li>
        ))}
      </ol>
    </div>
  )
}

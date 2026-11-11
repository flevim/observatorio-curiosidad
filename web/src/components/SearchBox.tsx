import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { TopicSummary } from '../api'
import { fold } from '../lib/format'

type Props = { topics: TopicSummary[]; onPick: (id: string) => void; big?: boolean }

/** Combobox accesible (patrón ARIA 1.2) con autocompletado sin tildes. Filtra en el cliente: la lista ya está en meta. */
export default function SearchBox({ topics, onPick, big }: Props) {
  const input = useRef<HTMLInputElement>(null)
  // Atajo «/» para enfocar el buscador (como en muchos sitios de búsqueda), salvo si ya se escribe en un campo.
  useEffect(() => {
    if (!big) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) && !t.isContentEditable) {
        e.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [big])
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const id = useId()
  const results = useMemo(() => {
    const f = fold(q.trim())
    const scored = topics
      .map((t) => {
        const n = fold(t.nombre)
        const s = !f ? 3 : n.startsWith(f) ? 0 : n.includes(f) ? 1 : fold(t.descripcion ?? '').includes(f) ? 2 : -1
        return { t, s }
      })
      .filter((x) => x.s >= 0)
      .sort((a, b) => a.s - b.s || a.t.nombre.localeCompare(b.t.nombre, 'es'))
    return scored.slice(0, 8).map((x) => x.t)
  }, [q, topics])

  const pick = (t: TopicSummary) => {
    onPick(t.id)
    setQ('')
    setOpen(false)
  }

  return (
    <div className={`search${big ? ' search-big' : ''}`}>
      <svg className="search-icon" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M11 11l4 4" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <label htmlFor={`${id}-in`} className="sr-only">Buscar tema</label>
      <input
        id={`${id}-in`}
        type="search"
        ref={input}
        placeholder={big ? 'Buscar un tema' : 'Buscar tema…'}
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${id}-${results[active].id}` : undefined}
        value={q}
        autoComplete="off"
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            setOpen(true)
            setActive((a) => Math.min(results.length - 1, a + 1))
            e.preventDefault()
          } else if (e.key === 'ArrowUp') {
            setActive((a) => Math.max(0, a - 1))
            e.preventDefault()
          } else if (e.key === 'Enter' && results[active]) {
            pick(results[active])
            e.preventDefault()
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {big && <kbd className="kbd" aria-hidden="true">/</kbd>}
      {open && results.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="search-list">
          {results.map((t, i) => (
            <li
              key={t.id}
              id={`${id}-${t.id}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(t)
              }}
              onMouseEnter={() => setActive(i)}
            >
              <span>{t.nombre}</span>
              {t.descripcion && <span className="muted small">{t.descripcion}</span>}
            </li>
          ))}
        </ul>
      )}
      {open && q && results.length === 0 && <div className="search-list empty">Sin resultados. Puedes agregarlo desde «Acerca de los datos».</div>}
    </div>
  )
}

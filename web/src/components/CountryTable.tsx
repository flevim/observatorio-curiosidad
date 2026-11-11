import { useState } from 'react'
import type { CountryState } from '../lib/scale'
import { countryName, num } from '../lib/format'

type Props = {
  isos: string[]
  stateFor: (iso: string | null) => CountryState
  valueLabel: string
  topicMode: boolean
  onSelect: (iso: string, name: string) => void
  selected: string | null
}

/** Vista alternativa en tabla: todos los países descargados, ordenables, navegables con teclado. */
export default function CountryTable({ isos, stateFor, valueLabel, topicMode, onSelect, selected }: Props) {
  const [sortBy, setSortBy] = useState<'valor' | 'nombre'>('valor')
  const rows = isos.map((iso) => ({ iso, name: countryName(iso), s: stateFor(iso) }))
  rows.sort((a, b) => {
    if (sortBy === 'nombre') return a.name.localeCompare(b.name, 'es')
    const va = a.s.kind === 'value' ? a.s.value : a.s.kind === 'absent' ? 0 : -1
    const vb = b.s.kind === 'value' ? b.s.value : b.s.kind === 'absent' ? 0 : -1
    return vb - va
  })
  return (
    <div className="table-view">
      <table>
        <caption className="sr-only">Países con su valor en el periodo seleccionado</caption>
        <thead>
          <tr>
            <th aria-sort={sortBy === 'nombre' ? 'ascending' : 'none'}><button className="link" onClick={() => setSortBy('nombre')}>País</button></th>
            <th className="n" aria-sort={sortBy === 'valor' ? 'descending' : 'none'}><button className="link" onClick={() => setSortBy('valor')}>{valueLabel}</button></th>
            {topicMode && <th className="n">Mejor puesto</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.iso} className={r.iso === selected ? 'sel' : ''}>
              <td><button className="link" onClick={() => onSelect(r.iso, r.name)}>{r.name}</button></td>
              <td className="n">
                {r.s.kind === 'value' ? `≈ ${num(r.s.value, topicMode ? 2 : 0)}` : r.s.kind === 'absent' ? 'no aparece' : 'sin datos'}
              </td>
              {topicMode && <td className="n">{r.s.kind === 'value' && r.s.rank ? r.s.rank : '—'}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

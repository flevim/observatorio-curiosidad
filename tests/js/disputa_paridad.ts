// Ejecuta las reglas de la web (web/src/lib/disputeRules.ts) sobre el caso que le pasa tests/test_disputes.py
// y escribe el resultado en JSON por stdout. Uso: node tests/js/disputa_paridad.ts <caso.json>
import { readFileSync } from 'node:fs'
import * as R from '../../web/src/lib/disputeRules.ts'

const c = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const score = R.scoreArticle(c.revs, c.inicio, c.fin, c.completo, c.desde)
const days = R.disputedDays(c.revs, c.inicio, c.fin, score.habitual_por_dia, 5)
const diffs = new Map<number, [string[], string[]]>(Object.entries(c.diffs).map(([k, v]) => [Number(k), R.parseDiff(v as string)]))
const describe = days.map((d) => R.describeDay(d, c.revs.filter((r: R.Rev) => r.timestamp.startsWith(d)), diffs, 'es'))
process.stdout.write(JSON.stringify({ score, days, describe, protecciones: R.protectionsIn(c.log, c.desde) }))

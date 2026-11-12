"""«Bajo disputa»: artículos con más ediciones revertidas de lo habitual, descritos solo con reglas fijas.

Todo lo que se muestra sale de datos públicos de Wikipedia y se puede comprobar con un enlace:
- Una edición «revertida» es la que Wikipedia marcó después con la etiqueta `mw-reverted`
  (alguien la deshizo). Una «reversión» es la edición que deshace (`mw-undo`, `mw-rollback`,
  `mw-manual-revert`).
- Lo habitual de cada artículo = ediciones revertidas por día en los días anteriores a la semana
  analizada (hasta 83 días). Esperado en la semana = 7 × lo habitual.
- Puntaje = (observadas − esperadas) / √(esperadas + 1). Entra en el ranking si hubo al menos
  MIN_REVERTED revertidas en la semana, el puntaje es ≥ MIN_SCORE y las observadas son al menos el
  triple de las esperadas.
- Día en disputa = día de la semana con ≥ 3 revertidas y ≥ 3 × lo habitual + 2.
- Fragmentos: texto que las ediciones revertidas agregaban («entraba») o quitaban («salía»),
  tal cual, sacado del diff de cada edición. Se cuentan las repeticiones exactas.
- Las protecciones y sus motivos se copian textuales del registro de Wikipedia.
No se interpreta la intención de nadie: no sabemos quién editó ni si hubo coordinación.
"""

from __future__ import annotations

import html
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import quote

MIN_REVERTED = 8
MIN_SCORE = 3.0
REVERT_TAGS = {"mw-undo", "mw-rollback", "mw-manual-revert"}
SECTION_RE = re.compile(r"/\*\s*(.+?)\s*\*/")
FRAG_MAX = 220


def wiki_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"


def diff_url(lang: str, rev: dict) -> str:
    return f"https://{lang}.wikipedia.org/w/index.php?diff={rev['revid']}&oldid={rev.get('parentid', 0)}"


def history_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/w/index.php?title={quote(title.replace(' ', '_'), safe='')}&action=history"


def protect_log_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/w/index.php?title=Special:Log&type=protect&page={quote(title.replace(' ', '_'), safe='')}"


def _day(ts: str) -> str:
    return ts[:10]


def is_reverted(rev: dict) -> bool:
    return "mw-reverted" in (rev.get("tags") or [])


def is_revert(rev: dict) -> bool:
    return bool(REVERT_TAGS & set(rev.get("tags") or []))


def is_anonymous(rev: dict) -> bool:
    """IP o cuenta temporal (las cuentas temporales empiezan con «~»)."""
    return bool(rev.get("anon") or rev.get("temp") or str(rev.get("user", "")).startswith("~"))


def daily_counts(revs: list[dict]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for r in revs:
        c = out[_day(r["timestamp"])]
        c["ediciones"] += 1
        c["revertidas"] += is_reverted(r)
        c["reversiones"] += is_revert(r)
    return out


def score_article(revs: list[dict], week_start: date, week_end: date, history_complete: bool, history_start: date) -> dict:
    """Compara las revertidas de la semana [week_start, week_end] con lo habitual del artículo."""
    ws, we = week_start.isoformat(), week_end.isoformat()
    week = [r for r in revs if ws <= _day(r["timestamp"]) <= we]
    before = [r for r in revs if _day(r["timestamp"]) < ws]
    obs = sum(map(is_reverted, week))
    # Días de comparación: desde el inicio de la ventana hasta el día anterior a la semana. Si el
    # historial se cortó (artículo muy editado), desde la edición más antigua que se descargó.
    first = history_start
    if not history_complete and revs:
        first = max(history_start, date.fromisoformat(min(_day(r["timestamp"]) for r in revs)))
    # Artículo creado dentro de la ventana: la primera revisión no tiene revisión anterior.
    created = _day(revs[0]["timestamp"]) if history_complete and revs and not revs[0].get("parentid") else None
    if created:
        first = max(first, date.fromisoformat(created))
    base_days = max(0, (week_start - first).days)
    habitual = (sum(map(is_reverted, before)) / base_days) if base_days else None
    expected = 7 * habitual if habitual is not None else 0.0
    score = (obs - expected) / math.sqrt(expected + 1)
    return {
        "revertidas_semana": obs,
        "ediciones_semana": len(week),
        "habitual_por_dia": None if habitual is None else round(habitual, 2),
        "dias_comparados": base_days,
        "esperadas_semana": round(expected, 1),
        "veces": None if not expected else round(obs / expected, 1),
        "puntaje": round(score, 2),
        "creado": created,
        "nuevo": bool(created and created >= ws),
        "entra": obs >= MIN_REVERTED and score >= MIN_SCORE and obs >= 3 * expected,
    }


def disputed_days(revs: list[dict], week_start: date, week_end: date, habitual: float | None, top: int = 3) -> list[str]:
    counts = daily_counts(revs)
    h = habitual or 0.0
    days = [d for d, c in counts.items()
            if week_start.isoformat() <= d <= week_end.isoformat() and c["revertidas"] >= 3 and c["revertidas"] >= 3 * h + 2]
    return sorted(sorted(days, key=lambda d: -counts[d]["revertidas"])[:top])


# ---------------- diffs

_CELL_RE = re.compile(r'<td class="(diff-addedline|diff-deletedline)[^"]*"[^>]*>(.*?)</td>', re.S)
_INLINE_RE = re.compile(r'<(ins|del) class="diffchange[^"]*">(.*?)</\1>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    s = html.unescape(_TAG_RE.sub("", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= FRAG_MAX else s[: FRAG_MAX - 1] + "…"


def parse_diff(body: str) -> tuple[list[str], list[str]]:
    """Fragmentos agregados y quitados de un diff HTML de MediaWiki.
    Si la línea tiene cambios marcados dentro, se toman solo esos trozos; si no, la línea completa."""
    added, removed = [], []
    for kind, cell in _CELL_RE.findall(body or ""):
        target = added if kind == "diff-addedline" else removed
        inline = _INLINE_RE.findall(cell)
        parts = [t for _, t in inline] if inline else [cell]
        for p in parts:
            t = _clean(p)
            if len(t) >= 2 and re.search(r"\w", t):
                target.append(t)
    return added, removed


def top_fragments(items: list[str], k: int = 4) -> list[dict]:
    return [{"texto": t, "veces": n} for t, n in Counter(items).most_common(k)]


# ---------------- descripción de un día (solo reglas)

def _span(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h = minutes / 60
    return f"{h:.0f} h" if h >= 3 else f"{h:.1f} h".replace(".", ",")


def describe_day(day: str, revs_day: list[dict], diffs: dict[int, tuple[list[str], list[str]]], lang: str) -> dict:
    reverted = [r for r in revs_day if is_reverted(r)]
    times = sorted(datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in reverted)
    span = int((times[-1] - times[0]).total_seconds() // 60) if len(times) > 1 else 0
    editors = {r.get("user") for r in reverted}
    anon = {r.get("user") for r in reverted if is_anonymous(r)}
    sections = Counter(m for r in revs_day for m in SECTION_RE.findall(r.get("comment") or ""))
    added = [f for r in reverted for f in diffs.get(r["revid"], ([], []))[0]]
    removed = [f for r in reverted for f in diffs.get(r["revid"], ([], []))[1]]
    revisadas = sum(1 for r in reverted if r["revid"] in diffs)

    frases = [f"{len(revs_day)} ediciones; {len(reverted)} fueron revertidas después"
              + (f", en un lapso de {_span(span)}" if span else "") + "."]
    frases.append(f"Las revertidas vienen de {len(editors)} {'editor' if len(editors) == 1 else 'editores'}"
                  + (f", {len(anon)} sin cuenta (IP o cuenta temporal)." if anon else ", todos con cuenta."))
    if sections:
        s, n = sections.most_common(1)[0]
        frases.append(f"Sección más tocada ese día: «{s}» ({n} {'edición' if n == 1 else 'ediciones'}).")
    ent, sal = top_fragments(added, 3), top_fragments(removed, 3)
    if ent:
        frases.append("Entraba: " + "; ".join(f"«{f['texto']}»" + (f" ({f['veces']} veces)" if f["veces"] > 1 else "") for f in ent) + ".")
    if sal:
        frases.append("Salía: " + "; ".join(f"«{f['texto']}»" + (f" ({f['veces']} veces)" if f["veces"] > 1 else "") for f in sal) + ".")
    return {
        "dia": day,
        "ediciones": len(revs_day),
        "revertidas": len(reverted),
        "reversiones": sum(map(is_revert, revs_day)),
        "minutos": span,
        "editores": len(editors),
        "sin_cuenta": len(anon),
        "secciones": [{"seccion": s, "ediciones": n} for s, n in sections.most_common(3)],
        "entraba": ent,
        "salia": sal,
        "diffs_revisados": revisadas,
        "frases": frases,
        "enlaces": [{"hora": r["timestamp"][11:16], "url": diff_url(lang, r)} for r in reverted[:20]],
    }


PROTECT_ACTIONS = {"protect": "protegido", "modify": "cambio de protección", "unprotect": "desprotegido",
                   "move_prot": "protección trasladada con el título"}


def protections_in(log: list[dict], since: date) -> list[dict]:
    out = []
    for e in log:
        if e.get("timestamp", "")[:10] < since.isoformat():
            continue
        out.append({
            "fecha": e["timestamp"][:16].replace("T", " "),
            "accion": PROTECT_ACTIONS.get(e.get("action"), e.get("action")),
            "nivel": (e.get("params") or {}).get("description", "").replace("‎", " ").strip(),
            "motivo": e.get("comment", ""),
        })
    return out


def _n(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def summary_sentence(s: dict) -> str:
    obs = f"Esta semana: {s['revertidas_semana']} de {s['ediciones_semana']} ediciones fueron revertidas después."
    if s.get("nuevo"):
        return f"{obs} El artículo se creó el {s['creado']}, dentro de la semana: no hay días anteriores para comparar."
    if s["habitual_por_dia"] is None:
        return f"{obs} No hay días anteriores para comparar (el historial descargado no alcanza antes de la semana)."
    if not s["habitual_por_dia"]:
        return f"{obs} En los {s['dias_comparados']} días anteriores no hubo ninguna edición revertida."
    return (f"{obs} Lo habitual en los {s['dias_comparados']} días anteriores: {_n(s['habitual_por_dia'], 2)} por día, "
            f"es decir {_n(s['esperadas_semana'])} en 7 días. Esta semana hubo {_n(s['veces'])} veces lo habitual.")


def series(revs: list[dict], views: dict[str, int], start: date, end: date) -> list[list]:
    """[día, ediciones, revertidas, visitas] para cada día de la ventana (visitas None si no hay dato)."""
    counts = daily_counts(revs)
    out, d = [], start
    while d <= end:
        k = d.isoformat()
        c = counts.get(k, Counter())
        out.append([k, c["ediciones"], c["revertidas"], views.get(k)])
        d += timedelta(days=1)
    return out

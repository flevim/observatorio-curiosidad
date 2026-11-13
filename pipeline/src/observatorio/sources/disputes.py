"""Descarga para «Bajo disputa»: ediciones revertidas recientes, historial, diffs y protecciones.

Llamadas por idioma (acotadas):
1. Cambios recientes con la etiqueta `mw-reverted` de los últimos 7 días (sin bots, espacio de artículos).
2. Para los CANDIDATES artículos con más revertidas: historial de 90 días, registro de protecciones y visitas.
3. Para los DIFF_ARTICLES que entran al ranking: el diff de hasta DIFFS_PER_DAY ediciones revertidas en
   cada día en disputa (los diffs no cambian nunca: se guardan en caché para siempre).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from ..analysis import disputes as D
from ..http import PoliteClient
from .wikipedia import DAY, encode_title, wiki_api

LANGS = ("es", "en", "pt", "fr", "de")
WEEK = 7
WINDOW = 90
CANDIDATES = 15
DIFF_ARTICLES = 8
DIFFS_PER_DAY = 10
KEEP = 10
RC_PAGES = 120
REV_PAGES = 12


def _q(client: PoliteClient, lang: str, params: dict, ttl: float | None) -> dict:
    base = {"format": "json", "formatversion": "2"}
    r = client.get_json(wiki_api(lang), {**base, **params}, ttl=ttl)
    return r.data if r.status == 200 and isinstance(r.data, dict) else {}


def _ts(d: date) -> str:
    return f"{d.isoformat()}T00:00:00Z"


def reverted_titles(client: PoliteClient, lang: str, start: date, end_excl: date) -> tuple[Counter, bool]:
    """Títulos con ediciones (de no-bots) que luego fueron revertidas, entre start y end_excl."""
    counts: Counter = Counter()
    cont: dict = {}
    for _ in range(RC_PAGES):
        d = _q(client, lang, {"action": "query", "list": "recentchanges", "rctag": "mw-reverted", "rcnamespace": 0,
                               "rcshow": "!bot", "rctype": "edit", "rcprop": "title", "rclimit": "max",
                               "rcstart": _ts(end_excl), "rcend": _ts(start), **cont}, ttl=6 * 3600)
        for c in (d.get("query") or {}).get("recentchanges", []):
            counts[c["title"]] += 1
        if "continue" not in d:
            return counts, True
        cont = d["continue"]
    return counts, False


def revisions(client: PoliteClient, lang: str, title: str, start: date, end_excl: date) -> tuple[list[dict], bool]:
    """Historial (más antiguo primero) entre start y end_excl. Devuelve (revisiones, completo)."""
    out: list[dict] = []
    cont: dict = {}
    for _ in range(REV_PAGES):
        d = _q(client, lang, {"action": "query", "prop": "revisions", "titles": title,
                               "rvprop": "ids|timestamp|user|tags|comment|size", "rvlimit": "max",
                               "rvstart": _ts(end_excl), "rvend": _ts(start), **cont}, ttl=6 * 3600)
        pages = (d.get("query") or {}).get("pages") or [{}]
        out += pages[0].get("revisions", [])
        if "continue" not in d:
            return out[::-1], True
        cont = d["continue"]
    return out[::-1], False


def protection_log(client: PoliteClient, lang: str, title: str) -> list[dict]:
    d = _q(client, lang, {"action": "query", "list": "logevents", "letype": "protect", "letitle": title, "lelimit": 50}, ttl=6 * 3600)
    return (d.get("query") or {}).get("logevents", [])


def views(client: PoliteClient, lang: str, title: str, start: date, end: date) -> dict[str, int]:
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/"
           f"{encode_title(title)}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00")
    r = client.get_json(url, ttl=6 * 3600, not_found_ttl=DAY)
    if r.status != 200:
        return {}
    return {f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}": i["views"] for i in r.data.get("items", [])}


def current_version(client: PoliteClient, lang: str, title: str) -> dict | None:
    """Texto actual (wikitexto) del artículo, para ver qué quedó de lo disputado."""
    d = _q(client, lang, {"action": "query", "prop": "revisions", "titles": title, "rvprop": "ids|timestamp|content",
                           "rvslots": "main", "rvlimit": 1}, ttl=6 * 3600)
    revs = ((d.get("query") or {}).get("pages") or [{}])[0].get("revisions") or []
    if not revs:
        return None
    r = revs[0]
    return {"revid": r["revid"], "fecha": r["timestamp"][:16].replace("T", " "),
            "texto": ((r.get("slots") or {}).get("main") or {}).get("content", "")}


def diff(client: PoliteClient, lang: str, rev: dict) -> tuple[list[str], list[str]] | None:
    if not rev.get("parentid"):
        return None
    d = _q(client, lang, {"action": "compare", "fromrev": rev["parentid"], "torev": rev["revid"], "prop": "diff"}, ttl=None)
    body = (d.get("compare") or {}).get("body")
    return D.parse_diff(body) if body is not None else None


def fetch_disputes(client: PoliteClient, progress: Callable[[str], None] = lambda s: None,
                   today: date | None = None, langs: tuple[str, ...] = LANGS) -> dict:
    today = today or datetime.now(timezone.utc).date()
    week_end = today - timedelta(days=1)            # último día completo (UTC)
    week_start = today - timedelta(days=WEEK)
    hist_start = today - timedelta(days=WINDOW)
    articles: list[dict] = []
    notes: list[str] = []
    for lang in langs:
        counts, complete = reverted_titles(client, lang, week_start, today)
        if not complete:
            notes.append(f"{lang}: la lista de cambios recientes se cortó en {RC_PAGES} páginas; puede faltar algún artículo.")
        cands = [t for t, n in counts.most_common(CANDIDATES) if n >= D.MIN_REVERTED]
        progress(f"Bajo disputa · {lang}: {sum(counts.values()):,} ediciones revertidas en 7 días, {len(cands)} candidatos")
        scored = []
        for title in cands:
            revs, full = revisions(client, lang, title, hist_start, today)
            s = D.score_article(revs, week_start, week_end, full, hist_start)
            if s["entra"]:
                scored.append((s["puntaje"], title, revs, full, s))
        scored.sort(key=lambda t: -t[0])
        for i, (_, title, revs, full, s) in enumerate(scored[:KEEP]):
            days = D.disputed_days(revs, week_start, week_end, s["habitual_por_dia"])
            by_day = {d: [r for r in revs if r["timestamp"][:10] == d] for d in days}
            diffs: dict[int, tuple[list[str], list[str]]] = {}
            if i < DIFF_ARTICLES:
                for d in days[:2]:
                    for r in [r for r in by_day[d] if D.is_reverted(r)][:DIFFS_PER_DAY]:
                        got = diff(client, lang, r)
                        if got is not None:
                            diffs[r["revid"]] = got
            log = protection_log(client, lang, title)
            vw = views(client, lang, title, hist_start, week_end)
            sizes = D.sizes_of(revs)
            described = [D.describe_day(d, by_day[d], diffs, lang, sizes) for d in days]
            cur = current_version(client, lang, title) if any(d["entraba"] or d["salia"] for d in described) else None
            if cur:
                for d in described:
                    D.mark_current(d, cur["texto"])
            serie = D.series(revs, vw, hist_start, week_end)
            articles.append({
                "id": f"{lang}:{title}",
                "titulo": title,
                "idioma": lang,
                "enlace": D.wiki_url(lang, title),
                "historial": D.history_url(lang, title),
                "registro_protecciones": D.protect_log_url(lang, title),
                **s,
                "historial_completo": full,
                "resumen": D.summary_sentence(s),
                "dias_disputa": described,
                "version_actual": None if not cur else {"revid": cur["revid"], "fecha": cur["fecha"]},
                "pico": D.peak_vs_dispute(serie, week_start.isoformat(), week_end.isoformat()),
                "protecciones": D.protections_in(log, hist_start),
                "serie": serie,
            })
    articles.sort(key=lambda a: -a["puntaje"])
    return {
        "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "semana": {"inicio": week_start.isoformat(), "fin": week_end.isoformat()},
        "ventana": {"inicio": hist_start.isoformat(), "fin": week_end.isoformat()},
        "idiomas": list(langs),
        "reglas": {"min_revertidas": D.MIN_REVERTED, "min_puntaje": D.MIN_SCORE, "candidatos_por_idioma": CANDIDATES,
                   "diffs_por_dia": DIFFS_PER_DAY},
        "avisos": notes,
        "articulos": articles,
    }

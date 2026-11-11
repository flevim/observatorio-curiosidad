"""Fuente Wikipedia: Wikimedia Pageviews API, MediaWiki Action API y Wikidata.

Endpoints usados (https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/):
- per-article/{project}/all-access/user/{title}/{daily|monthly}/{start}/{end}
  Visitas de un artículo, solo agentes humanos (agent=user). Sin desglose por país.
- top-per-country/{country}/all-access/{yyyy}/{mm}/{dd}
  Artículos más vistos en un país, SOLO por día y desde 2021-01-01. Los conteos (views_ceil)
  vienen redondeados hacia arriba por privacidad y la API omite artículos con pocas visitas.
- aggregate/{project}/{access}/user/monthly/{start}/{end}
  Total de visitas de cada edición de idioma (para normalizar y ver el cambio a móvil).
- MediaWiki API (action=query) para redirecciones, enlaces y categorías.
- Wikidata API (wbgetentities) para títulos equivalentes entre idiomas (sitelinks) y relaciones.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

from ..http import PoliteClient
from ..settings import PATHS, CountriesConfig, TopicConfig
from .base import SERIES_COLUMNS, DataSource, FetchReport, SourceInfo, empty_series

log = logging.getLogger(__name__)

PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DATA_START = date(2015, 7, 1)
COUNTRY_DATA_START = date(2021, 1, 1)
DAY = 86400.0

# Insignias de Wikidata que marcan un sitelink que apunta a una redirección.
REDIRECT_BADGES = {"Q70893996", "Q70894304"}

# Propiedades de Wikidata que expresan relaciones semánticas útiles entre temas.
WIKIDATA_PROPS = {
    "P31": "instancia de",
    "P279": "subclase de",
    "P361": "parte de",
    "P527": "tiene partes",
    "P1269": "faceta de",
    "P2579": "estudiado por",
    "P366": "tiene uso",
    "P2283": "usa",
    "P1535": "usado por",
    "P1542": "tiene efecto",
    "P828": "tiene causa",
    "P101": "campo de trabajo",
    "P921": "tema principal",
    "P136": "género",
}

NON_WIKI_SITES = {
    "commonswiki", "specieswiki", "wikidatawiki", "metawiki", "mediawikiwiki",
    "sourceswiki", "outreachwiki", "wikimaniawiki", "incubatorwiki", "foundationwiki",
}


def wiki_api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def encode_title(title: str) -> str:
    """Título en formato URL de la API REST: espacios como _ y todo codificado (incluida /)."""
    return quote(title.replace(" ", "_"), safe="")


def site_to_lang(site: str) -> str | None:
    """'eswiki' -> 'es', 'zh_yuewiki' -> 'zh-yue'. Devuelve None para sitios que no son Wikipedia."""
    if site in NON_WIKI_SITES or not re.fullmatch(r"[a-z_]+wiki", site):
        return None
    return site[: -len("wiki")].replace("_", "-")


def per_article_url(lang: str, title: str, granularity: str, start: date, end: date) -> str:
    fmt = "%Y%m%d"
    return (
        f"{PAGEVIEWS}/per-article/{lang}.wikipedia/all-access/user/{encode_title(title)}/"
        f"{granularity}/{start.strftime(fmt)}00/{end.strftime(fmt)}00"
    )


def top_per_country_url(country: str, day: date, access: str = "all-access") -> str:
    return f"{PAGEVIEWS}/top-per-country/{country}/{access}/{day.year}/{day.month:02d}/{day.day:02d}"


def aggregate_url(lang: str, access: str, start: date, end: date) -> str:
    return (
        f"{PAGEVIEWS}/aggregate/{lang}.wikipedia/{access}/user/monthly/"
        f"{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00"
    )


# ---------------------------------------------------------------- parsers (puros, probados)


def _ts(ts: str) -> pd.Timestamp:
    return pd.Timestamp(datetime.strptime(ts[:8], "%Y%m%d"))


def parse_per_article(data: dict | None) -> pd.DataFrame:
    """JSON de per-article -> DataFrame(date, views). Sin datos -> DataFrame vacío."""
    items = (data or {}).get("items") or []
    if not items:
        return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "views": pd.Series(dtype="int64")})
    df = pd.DataFrame({"date": [_ts(i["timestamp"]) for i in items], "views": [int(i["views"]) for i in items]})
    return df.sort_values("date").reset_index(drop=True)


def parse_aggregate(data: dict | None) -> pd.DataFrame:
    return parse_per_article(data)


def parse_top_per_country(data: dict | None) -> pd.DataFrame:
    """JSON de top-per-country -> DataFrame(country, date, rank, project, article, views_ceil)."""
    rows = []
    for item in (data or {}).get("items") or []:
        d = pd.Timestamp(int(item["year"]), int(item["month"]), int(item["day"]))
        for a in item.get("articles") or []:
            rows.append(
                {
                    "country": item["country"],
                    "date": d,
                    "rank": int(a["rank"]),
                    "project": a["project"],
                    "article": a["article"],
                    "views_ceil": int(a["views_ceil"]),
                }
            )
    cols = ["country", "date", "rank", "project", "article", "views_ceil"]
    return pd.DataFrame(rows, columns=cols)


def sample_days(cfg: CountriesConfig, today: date) -> list[date]:
    """Días a descargar para los rankings por país: días fijos de cada mes + los últimos N días."""
    start = max(date.fromisoformat(cfg.start), COUNTRY_DATA_START)
    last = today - timedelta(days=2)  # los datos del día se publican con retraso
    days: set[date] = set()
    y, m = start.year, start.month
    while date(y, m, 1) <= last:
        for d in cfg.sample_days:
            try:
                day = date(y, m, d)
            except ValueError:
                continue
            if start <= day <= last:
                days.add(day)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for i in range(cfg.recent_full_days):
        day = last - timedelta(days=i)
        if day >= start:
            days.add(day)
    return sorted(days)


# Páginas que no son artículos (portadas, búsquedas, páginas especiales) en los rankings por país.
NAMESPACE_PREFIXES = (
    "Special:", "Especial:", "Spécial:", "Spezial:", "Speciale:", "Служебная:", "特別:", "Especial:",
    "Wikipedia:", "Wikipédia:", "Википедия:", "ويكيبيديا:", "Portal:", "File:", "Archivo:", "Fichier:",
    "Datei:", "Help:", "Ayuda:", "Category:", "Categoría:", "Catégorie:", "Kategorie:", "Template:",
    "Plantilla:", "User:", "Usuario:", "Talk:", "Discusión:", "خاص:", "Заглавная_страница",
    "メインページ", "Pagina_principale", "Main_Page", "-", "Undefined",
)


# Portadas con título sin prefijo de espacio de nombres.
MAIN_PAGES = {
    "Hauptseite", "Portada", "Accueil", "Página_principal", "Pagina_principale", "Strona_główna", "Hoofdpagina",
    "Huvudsida", "首页", "Wikipedia:首页", "Головна_сторінка", "Etusivu", "Forside", "Hovedside", "Kezdőlap",
    "Hlavní_strana", "Pagina_principală", "Ana_Sayfa", "대문", "Trang_Chính", "Halaman_Utama", "หน้าหลัก",
}


def is_article(article: str) -> bool:
    return article not in MAIN_PAGES and not any(article == p or article.startswith(p) for p in NAMESPACE_PREFIXES)


# ---------------------------------------------------------------- fuente


class WikipediaSource(DataSource):
    info = SourceInfo(
        id="wikipedia",
        nombre="Wikipedia (Wikimedia Pageviews API)",
        url="https://wikimedia.org/api/rest_v1/metrics/pageviews/",
        licencia="Datos de visitas: CC0. Contenido de Wikidata: CC0.",
        unidad="visitas de personas (agent=user)",
        exacto=True,
        notas=[
            "Las visitas por artículo no tienen desglose por país; se agrupan por edición de idioma.",
            "Un idioma no equivale a un país.",
            "Los rankings por país vienen redondeados por privacidad (aproximados) y solo existen desde 2021.",
        ],
    )

    def __init__(self, client: PoliteClient, languages: list[str], *, today: date | None = None):
        self.client = client
        self.languages = languages
        self.today = today or datetime.now(timezone.utc).date()

    # ---------------- resolución de títulos

    def _query(self, api: str, params: dict, ttl: float | None = 30 * DAY) -> dict:
        base = {"action": "query", "format": "json", "formatversion": "2"}
        resp = self.client.get_json(api, {**base, **params}, ttl=ttl)
        return resp.data or {}

    def _query_all(self, api: str, params: dict, ttl: float | None = 30 * DAY) -> list[dict]:
        """Sigue la paginación (continue) de la MediaWiki API y devuelve todas las páginas."""
        pages: dict[str, dict] = {}
        cont: dict = {}
        for _ in range(50):
            data = self._query(api, {**params, **cont}, ttl)
            for p in (data.get("query") or {}).get("pages") or []:
                key = p.get("title")
                if key in pages:
                    for k, v in p.items():
                        if isinstance(v, list):
                            pages[key].setdefault(k, []).extend(v)
                else:
                    pages[key] = p
            if "continue" not in data:
                break
            cont = {k: v for k, v in data["continue"].items()}
        return list(pages.values())

    def _seed_qid(self, topic: TopicConfig, report: FetchReport) -> str | None:
        if topic.wikidata:
            return topic.wikidata
        if not topic.seed_title or not topic.seed_lang:
            report.warn(f"[{topic.id}] sin semilla ni wikidata en topics.yaml")
            return None
        data = self._query(
            wiki_api(topic.seed_lang),
            {"titles": topic.seed_title, "redirects": "1", "prop": "pageprops", "ppprop": "wikibase_item"},
        )
        q = data.get("query") or {}
        for r in q.get("redirects") or []:
            report.warn(f"[{topic.id}] la semilla '{r['from']}' redirige a '{r['to']}' ({topic.seed_lang})")
        pages = q.get("pages") or []
        if not pages or pages[0].get("missing"):
            report.warn(f"[{topic.id}] no existe el artículo semilla '{topic.seed_title}' en {topic.seed_lang}")
            return None
        qid = (pages[0].get("pageprops") or {}).get("wikibase_item")
        if not qid:
            report.warn(f"[{topic.id}] '{topic.seed_title}' no tiene elemento de Wikidata")
        return qid

    def _entities(self, qids: list[str], props: str, languages: str = "es|en") -> dict:
        out: dict = {}
        for i in range(0, len(qids), 50):
            chunk = qids[i : i + 50]
            resp = self.client.get_json(
                WIKIDATA_API,
                {"action": "wbgetentities", "format": "json", "ids": "|".join(chunk), "props": props, "languages": languages},
                ttl=30 * DAY,
            )
            out.update((resp.data or {}).get("entities") or {})
        return out

    def _verify_titles(self, lang: str, titles: list[str]) -> tuple[dict[str, str], set[str]]:
        """Sigue redirecciones. Devuelve {título pedido: título final} y el conjunto de títulos inexistentes."""
        final: dict[str, str] = {}
        missing: set[str] = set()
        for i in range(0, len(titles), 50):
            chunk = titles[i : i + 50]
            data = self._query(wiki_api(lang), {"titles": "|".join(chunk), "redirects": "1"})
            q = data.get("query") or {}
            norm = {n["from"]: n["to"] for n in q.get("normalized") or []}
            redir = {r["from"]: r["to"] for r in q.get("redirects") or []}
            missing_titles = {p["title"] for p in q.get("pages") or [] if p.get("missing") or p.get("invalid")}
            for t in chunk:
                t2 = norm.get(t, t)
                t3 = redir.get(t2, t2)
                if t3 in missing_titles:
                    missing.add(t)
                else:
                    final[t] = t3
        return final, missing

    def resolve(self, topics: list[TopicConfig], report: FetchReport | None = None) -> dict[str, dict]:
        report = report or FetchReport(self.info.id)
        qids = {t.id: self._seed_qid(t, report) for t in topics}
        entities = self._entities(sorted({q for q in qids.values() if q}), "sitelinks|labels|descriptions|claims")
        resolved: dict[str, dict] = {}
        seen_qids: dict[str, str] = {}
        for t in topics:
            qid = qids.get(t.id)
            ent = entities.get(qid or "", {})
            if not qid or "missing" in ent or not ent:
                report.warn(f"[{t.id}] no se pudo resolver en Wikidata; el tema queda sin datos")
                continue
            if qid in seen_qids:
                report.warn(f"[{t.id}] es el mismo elemento de Wikidata ({qid}) que '{seen_qids[qid]}': tema redundante")
            seen_qids[qid] = t.id
            sitelinks: dict[str, str] = {}
            redirect_badges: list[str] = []
            for site, sl in (ent.get("sitelinks") or {}).items():
                lang = site_to_lang(site)
                if lang:
                    sitelinks[lang] = sl["title"]
                    if REDIRECT_BADGES & set(sl.get("badges") or []):
                        redirect_badges.append(lang)
            labels = ent.get("labels") or {}
            descs = ent.get("descriptions") or {}
            resolved[t.id] = {
                "id": t.id,
                "nombre": t.nombre,
                "wikidata": qid,
                "label_es": (labels.get("es") or {}).get("value"),
                "label_en": (labels.get("en") or {}).get("value"),
                "descripcion_es": (descs.get("es") or {}).get("value"),
                "descripcion_en": (descs.get("en") or {}).get("value"),
                "sitelinks": sitelinks,  # todos los idiomas (para cruzar con rankings por país)
                "titles": {},  # idiomas configurados, ya verificados
                "redirects": [],
                "missing": [],
                "openalex": t.openalex,
                "claims": _extract_claims(ent),
            }
            if redirect_badges:
                report.warn(f"[{t.id}] sitelinks marcados como redirección en: {', '.join(sorted(redirect_badges))}")

        # Verificación de títulos por idioma (sigue redirecciones; agrupado para pocas llamadas).
        for lang in self.languages:
            wanted = {tid: r["sitelinks"][lang] for tid, r in resolved.items() if lang in r["sitelinks"]}
            final, missing = self._verify_titles(lang, sorted(set(wanted.values())))
            for tid, r in resolved.items():
                if lang not in r["sitelinks"]:
                    r["missing"].append(lang)
                    report.warn(f"[{tid}] no tiene artículo en {lang}.wikipedia")
                    continue
                title = r["sitelinks"][lang]
                if title in missing:
                    r["missing"].append(lang)
                    report.warn(f"[{tid}] el sitelink '{title}' de {lang} no existe")
                    continue
                if final[title] != title:
                    r["redirects"].append({"lang": lang, "from": title, "to": final[title]})
                    report.warn(f"[{tid}] {lang}: '{title}' redirige a '{final[title]}'")
                r["titles"][lang] = final[title]
        return resolved

    # ---------------- visitas por artículo

    def _end_dates(self) -> tuple[date, date]:
        daily_end = self.today - timedelta(days=2)
        first_this_month = self.today.replace(day=1)
        monthly_end = first_this_month - timedelta(days=1)
        return daily_end, monthly_end

    def fetch_pageviews(
        self, resolved: dict[str, dict], report: FetchReport, progress: Callable[[str], None] = lambda s: None,
        since: dict[tuple[str, str], date] | None = None,
    ) -> pd.DataFrame:
        """Visitas diarias y mensuales. Con `since` {(tema, idioma): último día guardado} la serie diaria se pide
        solo desde ese día menos 7 (solape para absorber correcciones), en vez de desde 2015."""
        daily_end, monthly_end = self._end_dates()
        frames = []
        for tid, r in resolved.items():
            for lang, title in r["titles"].items():
                last = (since or {}).get((tid, lang))
                daily_start = max(DATA_START, last - timedelta(days=7)) if last else DATA_START
                for gran, start, end, ttl in (("daily", daily_start, daily_end, 2 * DAY), ("monthly", DATA_START, monthly_end, None)):
                    if start > end:
                        continue
                    url = per_article_url(lang, title, gran, start, end)
                    resp = self.client.get_json(url, ttl=ttl)
                    report.network_calls += 0 if resp.from_cache else 1
                    report.cached_calls += 1 if resp.from_cache else 0
                    if resp.status != 200:
                        report.warn(f"[{tid}] {lang} '{title}' {gran}: HTTP {resp.status} (sin datos)")
                        continue
                    df = parse_per_article(resp.data)
                    if df.empty:
                        continue
                    frames.append(
                        pd.DataFrame(
                            {
                                "topic_id": tid,
                                "source": "wikipedia",
                                "series": lang,
                                "granularity": gran,
                                "date": df["date"],
                                "value": df["views"].astype("int64"),
                                "exact": True,
                            }
                        )
                    )
            progress(f"visitas: {tid}")
        if not frames:
            return empty_series()
        out = pd.concat(frames, ignore_index=True)
        return _fill_missing_days(out)

    def fetch_project_totals(self, report: FetchReport) -> pd.DataFrame:
        """Total mensual de visitas de cada edición, por tipo de acceso (escritorio, web móvil, app)."""
        _, monthly_end = self._end_dates()
        rows = []
        for lang in self.languages:
            for access in ("all-access", "desktop", "mobile-web", "mobile-app"):
                resp = self.client.get_json(aggregate_url(lang, access, DATA_START, monthly_end), ttl=None)
                if resp.status != 200:
                    report.warn(f"total {lang} {access}: HTTP {resp.status}")
                    continue
                df = parse_aggregate(resp.data)
                df["lang"] = lang
                df["access"] = access
                rows.append(df)
        if not rows:
            return pd.DataFrame(columns=["date", "views", "lang", "access"])
        return pd.concat(rows, ignore_index=True)

    # ---------------- rankings por país

    def fetch_country_tops(
        self, cfg: CountriesConfig, report: FetchReport, progress: Callable[[str], None] = lambda s: None
    ) -> pd.DataFrame:
        days = sample_days(cfg, self.today)
        frames = []
        total = len(days) * len(cfg.countries)
        done = 0
        for country in cfg.countries:
            empty_days = 0
            for day in days:
                # «Sin datos» de un día antiguo no va a cambiar: se guarda para siempre (los países protegidos no
                # se vuelven a pedir cada semana). Para días recientes, solo 2 días por si aún no se publicaba.
                old_day = day < self.today - timedelta(days=10)
                resp = self.client.get_json(top_per_country_url(country, day), ttl=None, not_found_ttl=None if old_day else 2 * DAY)
                done += 1
                if resp.from_cache:
                    report.cached_calls += 1
                else:
                    report.network_calls += 1
                if resp.status != 200:
                    empty_days += 1
                    continue
                frames.append(parse_top_per_country(resp.data))
            if empty_days:
                report.warn(f"ranking {country}: {empty_days} de {len(days)} días sin datos")
            progress(f"rankings: {country} ({done}/{total})")
        if not frames:
            return parse_top_per_country(None)
        out = pd.concat(frames, ignore_index=True)
        out["is_article"] = out["article"].map(is_article)
        return out

    # ---------------- relaciones semánticas

    def fetch_relations(self, resolved: dict[str, dict], report: FetchReport) -> dict:
        """Enlaces entre artículos (en, es), categorías compartidas y relaciones de Wikidata."""
        links: list[dict] = []
        for lang in ("en", "es"):
            title_to_tid = {r["titles"][lang]: tid for tid, r in resolved.items() if lang in r["titles"]}
            all_titles = list(title_to_tid)
            for tid, r in resolved.items():
                if lang not in r["titles"]:
                    continue
                others = [t for t in all_titles if t != r["titles"][lang]]
                for i in range(0, len(others), 50):
                    pages = self._query_all(
                        wiki_api(lang),
                        {"titles": r["titles"][lang], "prop": "links", "pltitles": "|".join(others[i : i + 50]), "pllimit": "max"},
                    )
                    for p in pages:
                        for link in p.get("links") or []:
                            target = title_to_tid.get(link["title"])
                            if target:
                                links.append({"from": tid, "to": target, "lang": lang})

        categories: dict[str, dict[str, list[str]]] = {}
        for lang in ("en", "es"):
            for tid, r in resolved.items():
                if lang not in r["titles"]:
                    continue
                pages = self._query_all(
                    wiki_api(lang),
                    {"titles": r["titles"][lang], "prop": "categories", "clshow": "!hidden", "cllimit": "max"},
                )
                cats = sorted({c["title"] for p in pages for c in (p.get("categories") or [])})
                categories.setdefault(tid, {})[lang] = cats

        # Etiquetas de los valores de Wikidata (para explicar la relación en español).
        value_qids = sorted({v for r in resolved.values() for vals in r["claims"].values() for v in vals})
        labels = {}
        ents = self._entities(value_qids, "labels|sitelinks", "es|en")
        for q, e in ents.items():
            lab = e.get("labels") or {}
            labels[q] = {
                "es": (lab.get("es") or {}).get("value"),
                "en": (lab.get("en") or {}).get("value"),
                "eswiki": ((e.get("sitelinks") or {}).get("eswiki") or {}).get("title"),
                "enwiki": ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title"),
            }
        return {"links": links, "categories": categories, "wikidata_labels": labels}

    # ---------------- interfaz común

    def fetch(self, topics: list[TopicConfig], report: FetchReport) -> None:  # pragma: no cover - ver pipeline.py
        raise NotImplementedError("usa observatorio.pipeline.fetch, que coordina todas las descargas")

    def series(self, topics: list[TopicConfig]) -> pd.DataFrame:
        path = PATHS.processed / "pageviews.parquet"
        if not path.exists():
            return empty_series()
        df = pd.read_parquet(path)
        ids = {t.id for t in topics}
        return df[df["topic_id"].isin(ids)][SERIES_COLUMNS].reset_index(drop=True)


def _extract_claims(entity: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for prop in WIKIDATA_PROPS:
        vals = []
        for c in (entity.get("claims") or {}).get(prop) or []:
            dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(dv, dict) and dv.get("id"):
                vals.append(dv["id"])
        if vals:
            out[prop] = vals
    return out


def _fill_missing_days(df: pd.DataFrame) -> pd.DataFrame:
    """La API omite los días con 0 visitas. Se rellenan con 0 dentro del rango de cada serie diaria."""
    daily = df[df["granularity"] == "daily"]
    other = df[df["granularity"] != "daily"]
    filled = []
    for (tid, series), g in daily.groupby(["topic_id", "series"], sort=False):
        idx = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        s = g.set_index("date")["value"].reindex(idx, fill_value=0)
        filled.append(
            pd.DataFrame(
                {"topic_id": tid, "source": "wikipedia", "series": series, "granularity": "daily",
                 "date": idx, "value": s.values.astype("int64"), "exact": True}
            )
        )
    return pd.concat([*filled, other], ignore_index=True) if filled else other


def save_json(obj, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def iter_topic_titles(resolved: dict[str, dict]) -> Iterable[tuple[str, str, str]]:
    """(topic_id, project, article) con todos los sitelinks, para cruzar con los rankings por país."""
    for tid, r in resolved.items():
        for lang, title in r["sitelinks"].items():
            yield tid, f"{lang}.wikipedia", title.replace(" ", "_")
        for red in r.get("redirects") or []:
            yield tid, f"{red['lang']}.wikipedia", red["to"].replace(" ", "_")

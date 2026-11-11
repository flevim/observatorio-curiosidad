"""Parseo de la API de Wikimedia, URLs, muestreo de días y caché HTTP."""

from datetime import date

import httpx
import pandas as pd
import pytest

from observatorio.http import HttpCache, PoliteClient
from observatorio.settings import CountriesConfig
from observatorio.sources.wikipedia import (
    encode_title,
    is_article,
    parse_per_article,
    parse_top_per_country,
    per_article_url,
    sample_days,
    site_to_lang,
    _fill_missing_days,
)

PER_ARTICLE = {
    "items": [
        {"project": "es.wikipedia", "article": "Ajedrez", "granularity": "daily", "timestamp": "2024010200", "access": "all-access", "agent": "user", "views": 120},
        {"project": "es.wikipedia", "article": "Ajedrez", "granularity": "daily", "timestamp": "2024010100", "access": "all-access", "agent": "user", "views": 100},
        {"project": "es.wikipedia", "article": "Ajedrez", "granularity": "daily", "timestamp": "2024010400", "access": "all-access", "agent": "user", "views": 90},
    ]
}

TOP_COUNTRY = {
    "items": [
        {
            "country": "CL", "access": "all-access", "year": "2025", "month": "10", "day": "15",
            "articles": [
                {"article": "Wikipedia:Portada", "project": "es.wikipedia", "views_ceil": 16600, "rank": 1},
                {"article": "Ajedrez", "project": "es.wikipedia", "views_ceil": 1200, "rank": 2},
            ],
        }
    ]
}


def test_parse_per_article_sorts_and_types():
    df = parse_per_article(PER_ARTICLE)
    assert list(df["date"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]
    assert df["views"].tolist() == [100, 120, 90]


def test_parse_per_article_empty():
    assert parse_per_article(None).empty
    assert parse_per_article({"items": []}).empty


def test_fill_missing_days_inserts_zero():
    df = parse_per_article(PER_ARTICLE)
    long = pd.DataFrame({"topic_id": "t", "source": "wikipedia", "series": "es", "granularity": "daily",
                         "date": df["date"], "value": df["views"], "exact": True})
    out = _fill_missing_days(long)
    assert len(out) == 4
    assert out.set_index("date").loc["2024-01-03", "value"] == 0


def test_parse_top_per_country():
    df = parse_top_per_country(TOP_COUNTRY)
    assert len(df) == 2
    assert df.iloc[1].to_dict() | {} == {
        "country": "CL", "date": pd.Timestamp("2025-10-15"), "rank": 2, "project": "es.wikipedia", "article": "Ajedrez", "views_ceil": 1200,
    }


def test_is_article_filters_service_pages():
    assert not is_article("Wikipedia:Portada")
    assert not is_article("Main_Page")
    assert not is_article("Special:Search")
    assert not is_article("-")
    assert is_article("Ajedrez")
    assert is_article("Mainz")  # no confundir prefijos parecidos


def test_urls_and_titles():
    assert encode_title("AC/DC song") == "AC%2FDC_song"
    url = per_article_url("es", "Vacuna de ARNm", "daily", date(2015, 7, 1), date(2025, 1, 31))
    assert url.endswith("/per-article/es.wikipedia/all-access/user/Vacuna_de_ARNm/daily/2015070100/2025013100")
    assert site_to_lang("eswiki") == "es"
    assert site_to_lang("zh_yuewiki") == "zh-yue"
    assert site_to_lang("commonswiki") is None
    assert site_to_lang("eswikiquote") is None


def test_sample_days_respects_start_and_delay():
    cfg = CountriesConfig(start="2020-06-01", sample_days=[8, 22, 31], recent_full_days=3, countries=["CL"])
    days = sample_days(cfg, date(2021, 3, 5))
    assert days[0] == date(2021, 1, 8)  # la API no tiene datos antes de 2021
    assert date(2021, 1, 31) in days and date(2021, 2, 28) not in days  # 31 de febrero no existe
    assert days[-1] == date(2021, 3, 3)  # hoy menos 2 días
    assert date(2021, 3, 1) in days  # últimos 3 días completos


# ---------------------------------------------------------------- caché y cliente


def _client(handler, sleeps=None):
    cache = HttpCache(":memory:")
    return PoliteClient(cache, interval=0, transport=httpx.MockTransport(handler), sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_cache_avoids_second_call():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler)
    r1 = c.get_json("https://x.test/a")
    r2 = c.get_json("https://x.test/a")
    assert r1.data == r2.data == {"ok": 1}
    assert not r1.from_cache and r2.from_cache
    assert len(calls) == 1


def test_404_is_cached_and_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404, json={"title": "Not found."})

    c = _client(handler)
    assert c.get_json("https://x.test/missing").status == 404
    assert c.get_json("https://x.test/missing").from_cache
    assert len(calls) == 1


def test_429_retries_with_exponential_backoff_and_retry_after():
    sleeps, n = [], {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429)
        if n["i"] == 2:
            return httpx.Response(503, headers={"Retry-After": "5"})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, sleeps)
    c.backoff_base = 1.0
    assert c.get_json("https://x.test/r").data == {"ok": True}
    assert sleeps == [1.0, 5.0]  # 1 s (2^0) y luego Retry-After 5 s > 2 s (2^1)


def test_gives_up_after_max_retries():
    c = _client(lambda req: httpx.Response(500), [])
    c.max_retries = 2
    with pytest.raises(httpx.HTTPStatusError):
        c.get_json("https://x.test/boom")


def test_403_explains_user_agent_policy():
    c = _client(lambda req: httpx.Response(403, text="robot policy"), [])
    with pytest.raises(PermissionError, match="OBSERVATORIO_CONTACT"):
        c.get_json("https://x.test/forbidden")


def test_cache_ttl_expiry(tmp_path):
    cache = HttpCache(tmp_path / "c.sqlite")
    cache.put("u", 200, {"a": 1}, ttl=-1)  # ya vencida
    assert cache.get("u") is None
    cache.put("u", 200, {"a": 2}, ttl=None)
    assert cache.get("u") == (200, {"a": 2})

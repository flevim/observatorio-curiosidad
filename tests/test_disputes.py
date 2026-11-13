"""«Bajo disputa»: reglas sobre historiales y diffs construidos a mano."""

from datetime import date

from observatorio.analysis import disputes as D

WS, WE, HS = date(2026, 11, 5), date(2026, 11, 11), date(2026, 8, 14)


def rev(i, ts, reverted=False, revert=False, user="Ana", parent=None, comment="", anon=False):
    tags = (["mw-reverted"] if reverted else []) + (["mw-undo"] if revert else [])
    r = {"revid": i, "parentid": i - 1 if parent is None else parent, "timestamp": ts, "user": user, "tags": tags, "comment": comment}
    if anon:
        r["anon"] = True
    return r


def history(base_reverted=2, week_reverted=10):
    revs = [rev(1, "2026-08-20T10:00:00Z", parent=7)]  # el artículo ya existía antes de la ventana
    revs += [rev(10 + i, f"2026-09-{10 + i:02d}T10:00:00Z", reverted=True) for i in range(base_reverted)]
    revs += [rev(100 + i, f"2026-11-08T10:{i:02d}:00Z", reverted=True, user=f"~2026-{i % 3}") for i in range(week_reverted)]
    revs += [rev(200, "2026-11-08T11:00:00Z", revert=True, comment="/* Biografía */ revierto")]
    return revs


def test_score_compares_with_habitual():
    s = D.score_article(history(), WS, WE, True, HS)
    assert s["revertidas_semana"] == 10 and s["dias_comparados"] == 83
    assert s["habitual_por_dia"] == round(2 / 83, 2) and s["entra"] and not s["nuevo"]
    assert "veces lo habitual" in D.summary_sentence(s)


def test_habitual_activity_does_not_enter():
    # 56 revertidas en los 83 días anteriores (≈ 4,7 por semana): 10 en la semana no llega al triple.
    busy = [rev(500 + i, f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}T09:00:00Z", reverted=True) for i in range(56)]
    s = D.score_article(history(base_reverted=0)[:1] + busy + history(base_reverted=0)[1:], WS, WE, True, HS)
    assert s["revertidas_semana"] == 10 and not s["entra"]


def test_new_article_is_flagged_without_habitual():
    revs = [rev(1, "2026-11-06T08:00:00Z", parent=0)] + [rev(2 + i, f"2026-11-07T09:{i:02d}:00Z", reverted=True) for i in range(9)]
    s = D.score_article(revs, WS, WE, True, HS)
    assert s["nuevo"] and s["creado"] == "2026-11-06" and s["habitual_por_dia"] is None
    assert "se creó el 2026-11-06" in D.summary_sentence(s)


def test_disputed_days_and_description():
    revs = history()
    days = D.disputed_days(revs, WS, WE, 2 / 83)
    assert days == ["2026-11-08"]
    day = [r for r in revs if r["timestamp"].startswith("2026-11-08")]
    diffs = {100 + i: (["neonazi"], ["abogado"]) for i in range(4)}
    out = D.describe_day("2026-11-08", day, diffs, "es")
    assert out["revertidas"] == 10 and out["minutos"] == 9 and out["editores"] == 3 and out["sin_cuenta"] == 3
    assert out["entraba"][0] == {"texto": "neonazi", "veces": 4} and out["salia"][0]["texto"] == "abogado"
    assert out["secciones"][0]["seccion"] == "Biografía"
    assert "Entraba: «neonazi» (4 veces)." in out["frases"]
    assert out["enlaces"][0]["url"] == "https://es.wikipedia.org/w/index.php?diff=100&oldid=99"


def test_parse_diff_inline_and_full_lines():
    body = (
        '<tr><td class="diff-deletedline diff-side-deleted"><div>es un <del class="diffchange diffchange-inline">abogado</del> chileno</div></td>'
        '<td class="diff-addedline diff-side-added"><div>es un <ins class="diffchange diffchange-inline">político &amp; abogado</ins> chileno</div></td></tr>'
        '<tr><td class="diff-addedline diff-side-added"><div>[[Categoría:Nueva]]</div></td></tr>'
        '<tr><td class="diff-addedline diff-side-added"><div> , </div></td></tr>'
    )
    added, removed = D.parse_diff(body)
    assert added == ["político & abogado", "[[Categoría:Nueva]]"]
    assert removed == ["abogado"]


def test_protections_are_copied_verbatim():
    log = [{"timestamp": "2026-11-10T21:03:00Z", "action": "modify", "comment": "Persistent [[WP:Vandalism|vandalism]]",
            "params": {"description": "‎[edit=autoconfirmed]"}},
           {"timestamp": "2020-01-01T00:00:00Z", "action": "protect", "comment": "viejo", "params": {}}]
    out = D.protections_in(log, HS)
    assert out == [{"fecha": "2026-11-10 21:03", "accion": "cambio de protección", "nivel": "[edit=autoconfirmed]",
                    "motivo": "Persistent [[WP:Vandalism|vandalism]]"}]


def test_web_rules_match_python(tmp_path):
    """La web recalcula «Bajo disputa» en el navegador: sus reglas (TypeScript) deben dar los mismos números."""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    root = Path(__file__).resolve().parents[1]
    body = ('<td class="diff-deletedline"><div>un <del class="diffchange diffchange-inline">abogado</del></div></td>'
            '<td class="diff-addedline"><div>un <ins class="diffchange diffchange-inline">neonazi &amp; «más»</ins></div></td>'
            '<td class="diff-addedline"><div>[[Categoría:Nueva]]</div></td>')
    revs = history(base_reverted=3, week_reverted=12)
    revs += [rev(400 + i, f"2026-11-10T0{i}:15:00Z", reverted=True, user="10.0.0.1", anon=True, comment="/* Ficha */") for i in range(5)]
    revs.sort(key=lambda r: r["timestamp"])
    log = [{"timestamp": "2026-11-10T21:03:00Z", "action": "move_prot", "comment": "Persistent [[WP:Vandalism|vandalism]]",
            "params": {"description": "\u200e[edit=autoconfirmed]"}}]
    case = {"revs": revs, "inicio": WS.isoformat(), "fin": WE.isoformat(), "completo": True, "desde": HS.isoformat(),
            "diffs": {str(100 + i): body for i in range(6)} | {"400": body}, "log": log}
    f = tmp_path / "caso.json"
    f.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([node, str(root / "tests/js/disputa_paridad.ts"), str(f)], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    js = json.loads(out.stdout)

    py_score = D.score_article(revs, WS, WE, True, HS)
    py_score.pop("entra"), js["score"].pop("entra")
    assert js["score"] == py_score
    py_days = D.disputed_days(revs, WS, WE, py_score["habitual_por_dia"], top=5)
    assert len(py_days) == 2 and js["days"] == py_days
    diffs = {int(k): D.parse_diff(v) for k, v in case["diffs"].items()}
    py_desc = [D.describe_day(d, [r for r in revs if r["timestamp"].startswith(d)], diffs, "es") for d in py_days]
    assert js["describe"] == json.loads(json.dumps(py_desc))
    assert js["protecciones"] == D.protections_in(log, HS)

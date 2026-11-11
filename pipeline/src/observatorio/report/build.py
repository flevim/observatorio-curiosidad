"""Reporte HTML autocontenido (sin dependencias externas): reports/observatorio.html"""

from __future__ import annotations

import html
import json
import math

import numpy as np
import pandas as pd

from ..analysis.findings import IDIOMAS, MESES, num, pct
from ..analysis.run import ALL, build_series
from ..demo import is_demo
from ..export import LIMITACIONES
from ..settings import PATHS

E = html.escape
SERIES_HL = {"es": "var(--s1)", "en": "var(--s2)"}  # el resto, gris de contexto


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.ceil(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step) + 1)]


def _fmt_axis(v: float) -> str:
    if v >= 1e6:
        return f"{num(v / 1e6, 1 if v % 1e6 else 0)} M"
    if v >= 1e3:
        return f"{num(v / 1e3, 0)} mil"
    return num(v)


def line_chart(dates: list[str], series: dict[str, list[float | None]], *, log: bool, title: str, uid: str) -> str:
    """Serie mensual con idiomas superpuestos. es y en en color; los demás idiomas en gris de contexto."""
    W, H, L, R, T, B = 760, 280, 64, 56, 16, 28
    pw, ph = W - L - R, H - T - B
    vals = [v for s in series.values() for v in s if v]
    if not vals:
        return "<p>Sin datos.</p>"
    if log:
        lo, hi = math.log10(max(min(vals), 1)), math.log10(max(vals))
        lo, hi = math.floor(lo), math.ceil(hi)
        ticks = [10**e for e in range(int(lo), int(hi) + 1)]
        fy = lambda v: T + ph - (math.log10(max(v, 1)) - lo) / max(hi - lo, 1e-9) * ph
    else:
        lo, hi = 0, max(vals) * 1.05
        ticks = _nice_ticks(0, hi)
        fy = lambda v: T + ph - (v - lo) / (hi - lo) * ph
    n = len(dates)
    fx = lambda i: L + i / max(n - 1, 1) * pw
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{E(title)}" data-uid="{uid}">']
    for t in ticks:
        y = fy(t)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{L - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{_fmt_axis(t)}</text>')
    for i, d in enumerate(dates):
        if d.endswith("-01") and int(d[:4]) % 2 == 0:
            x = fx(i)
            out.append(f'<text x="{x:.1f}" y="{H - 8}" class="tick" text-anchor="middle">{d[:4]}</text>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{T + ph}" y2="{T + ph}" class="axis"/>')
    order = [k for k in series if k not in SERIES_HL] + [k for k in SERIES_HL if k in series]
    for k in order:
        pts, path = series[k], []
        for i, v in enumerate(pts):
            if v is None or (log and v <= 0):
                continue
            path.append(f"{'M' if not path else 'L'}{fx(i):.1f},{fy(v):.1f}")
        if not path:
            continue
        cls = f'line hl" style="stroke:{SERIES_HL[k]}' if k in SERIES_HL else "line ctx"
        out.append(f'<path d="{" ".join(path)}" class="{cls}"><title>{E(IDIOMAS.get(k, k))}</title></path>')
        if k in SERIES_HL:
            last = next((i for i in range(len(pts) - 1, -1, -1) if pts[i]), None)
            if last is not None:
                out.append(f'<text x="{fx(last) + 6:.1f}" y="{fy(pts[last]) + 4:.1f}" class="dlabel">{k}</text>')
    out.append(f'<line class="xhair" x1="0" x2="0" y1="{T}" y2="{T + ph}" style="display:none"/>')
    out.append(f'<rect class="hit" x="{L}" y="{T}" width="{pw}" height="{ph}" fill="transparent"/>')
    out.append("</svg>")
    return "".join(out)


def bar_chart(items: list[tuple[str, float, str]], *, unit: str, label: str) -> str:
    """Barras horizontales (una sola serie). items = (etiqueta, valor, texto tooltip)."""
    rowh, L, R = 26, 180, 70
    W = 760
    H = rowh * len(items) + 24
    mx = max(v for _, v, _ in items) or 1
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{E(label)}">']
    for t in _nice_ticks(0, mx, 4):
        x = L + t / mx * (W - L - R)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="0" y2="{H - 20}" class="grid"/>')
        out.append(f'<text x="{x:.1f}" y="{H - 6}" class="tick" text-anchor="middle">{num(t, 0)}</text>')
    for i, (lab, v, tip) in enumerate(items):
        y = i * rowh + 4
        w = max(v / mx * (W - L - R), 2)
        out.append(f'<text x="{L - 8}" y="{y + 15}" class="rowlabel" text-anchor="end">{E(lab)}</text>')
        out.append(f'<g class="bar"><title>{E(tip)}</title><rect x="{L}" y="{y + 3}" width="{w:.1f}" height="{rowh - 10}" rx="4"/>'
                   f'<rect x="{L}" y="{y}" width="{W - L - R}" height="{rowh}" fill="transparent"/></g>')
        out.append(f'<text x="{L + w + 6:.1f}" y="{y + 15}" class="val">{num(v, 1)} {unit}</text>')
    out.append("</svg>")
    return "".join(out)


DIV_NEG = ["#256abf", "#5598e7", "#9ec5f4"]  # azul (por debajo de lo normal)
DIV_POS = ["#f2b8b8", "#e66767", "#c33a39"]  # rojo (por encima)


def _div_color(f: float) -> str:
    """Factor estacional (1 = normal) -> color divergente con punto medio gris."""
    d = math.log(max(f, 1e-6))
    if abs(d) < 0.05:
        return "var(--mid)"
    steps = DIV_POS if d > 0 else DIV_NEG[::-1]
    i = min(int(abs(d) / 0.1), 2)
    return steps[i] if d > 0 else DIV_NEG[2 - i]


def heatmap(rows: list[tuple[str, list[float], bool]]) -> str:
    cw, ch, L = 46, 24, 180
    W, H = L + 12 * cw + 10, len(rows) * ch + 30
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Mapa de calor de estacionalidad">']
    for m in range(12):
        out.append(f'<text x="{L + m * cw + cw / 2}" y="14" class="tick" text-anchor="middle">{MESES[m][:3]}</text>')
    for r, (lab, prof, seasonal) in enumerate(rows):
        y = 22 + r * ch
        out.append(f'<text x="{L - 8}" y="{y + 16}" class="rowlabel{" strong" if seasonal else ""}" text-anchor="end">{E(lab)}{" *" if seasonal else ""}</text>')
        for m, f in enumerate(prof):
            out.append(f'<rect x="{L + m * cw + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="3" fill="{_div_color(f)}">'
                       f'<title>{E(lab)} · {MESES[m]}: {pct(f - 1, 0) if f >= 1 else "−" + pct(1 - f, 0)} respecto de lo normal</title></rect>')
    out.append("</svg>")
    return "".join(out)


CSS = """
:root{color-scheme:light;--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--ctx:#c3c2b7;--bar:#2a78d6;--mid:#f0efec;--border:rgba(11,11,11,.10);--warn:#8a5a00;--warnbg:#fff4d6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--ctx:#4a4a46;--bar:#3987e5;--mid:#383835;--border:rgba(255,255,255,.10);--warn:#fab219;--warnbg:#2a2210}}
:root[data-theme=dark]{color-scheme:dark;--bg:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--ctx:#4a4a46;--bar:#3987e5;--mid:#383835;--border:rgba(255,255,255,.10);--warn:#fab219;--warnbg:#2a2210}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 80px}h1{font-size:1.8rem;margin:.2em 0}h2{margin-top:2.2em;font-size:1.35rem;border-bottom:1px solid var(--border);padding-bottom:.3em}
h3{font-size:1.1rem;margin:1.6em 0 .4em}p,li{color:var(--ink)}.meta{color:var(--ink2);font-size:.92rem}
.demo{background:var(--warnbg);color:var(--warn);border:1px solid var(--warn);padding:10px 14px;border-radius:6px;font-weight:600}
.chart{width:100%;height:auto;background:var(--surface);border:1px solid var(--border);border-radius:6px}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis)}.tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.line{fill:none;stroke-width:2;stroke-linejoin:round}.line.ctx{stroke:var(--ctx);stroke-width:1.2}.dlabel{fill:var(--ink2);font-size:12px;font-weight:600}
.rowlabel{fill:var(--ink2);font-size:12px}.rowlabel.strong{fill:var(--ink);font-weight:600}.val{fill:var(--ink2);font-size:11px;font-variant-numeric:tabular-nums}
.bar rect:first-of-type{fill:var(--bar)}.bar:hover rect:first-of-type{opacity:.8}.xhair{stroke:var(--muted);stroke-dasharray:3 3}
table{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--ink2);font-weight:600}td.n,th.n{text-align:right}.scroll{overflow-x:auto}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.85rem;color:var(--ink2);margin:6px 0}.sw{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
.tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:6px 9px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9;font-variant-numeric:tabular-nums}
.toggle{font-size:.9rem;color:var(--ink2)}.charts .log{display:none}.charts.logon .log{display:block}.charts.logon .lin{display:none}
details{margin:.4em 0}summary{cursor:pointer;color:var(--ink2)}nav a{color:var(--s1)}a{color:var(--s1)}
"""

JS = """
const tip=document.querySelector('.tip');
document.querySelectorAll('input.logsw').forEach(cb=>cb.addEventListener('change',e=>{document.querySelectorAll('.charts').forEach(c=>c.classList.toggle('logon',e.target.checked))}));
document.querySelectorAll('svg[data-uid]').forEach(svg=>{
 const d=window.SERIES[svg.dataset.uid];if(!d)return;const hit=svg.querySelector('.hit'),xh=svg.querySelector('.xhair');
 const L=+hit.getAttribute('x'),W=+hit.getAttribute('width');
 hit.addEventListener('mousemove',ev=>{const p=svg.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());
  const i=Math.max(0,Math.min(d.fechas.length-1,Math.round((q.x-L)/W*(d.fechas.length-1))));const x=L+i/(d.fechas.length-1)*W;
  xh.setAttribute('x1',x);xh.setAttribute('x2',x);xh.style.display='';
  const rows=Object.entries(d.series).filter(([k,v])=>v[i]!=null).sort((a,b)=>b[1][i]-a[1][i]).map(([k,v])=>`<div>${k}: ${v[i].toLocaleString('es')}</div>`).join('');
  tip.innerHTML=`<b>${d.fechas[i]}</b>${rows}`;tip.style.display='block';tip.style.left=Math.min(ev.clientX+14,innerWidth-180)+'px';tip.style.top=(ev.clientY+10)+'px';});
 hit.addEventListener('mouseleave',()=>{tip.style.display='none';xh.style.display='none'});
});
"""


def _trend_txt(tr: dict | None) -> str:
    if not tr:
        return "—"
    return {"sube": "sube", "baja": "baja", "estable": "estable"}[tr["clase"]] + f" ({'+' if tr['cambio_anual'] >= 0 else '−'}{pct(abs(tr['cambio_anual']))}/año)"


def build_report() -> str:
    an = PATHS.analysis
    topics = json.loads((an / "topics.json").read_text(encoding="utf-8"))
    findings = json.loads((an / "findings.json").read_text(encoding="utf-8"))
    clusters = json.loads((an / "clusters.json").read_text(encoding="utf-8"))
    rel = json.loads((an / "relations.json").read_text(encoding="utf-8"))
    context = json.loads((an / "context.json").read_text(encoding="utf-8"))
    pv = pd.read_parquet(PATHS.processed / "pageviews.parquet")
    pv = pv[pv["topic_id"].isin(topics)]
    _, monthly = build_series(pv)
    end = context["mes_final"]
    names = {k: v["nombre"] for k, v in topics.items()}
    demo = is_demo()

    P: list[str] = []
    a = P.append
    a('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    a(f"<title>Observatorio de la Curiosidad</title><style>{CSS}</style></head><body><div class='tip'></div><main>")
    a("<h1>Observatorio de la Curiosidad</h1>")
    a(f"<p class='meta'>Atención pública en Wikipedia a {len(topics)} temas en {len(context['idiomas'])} idiomas, julio de 2015 a {end}. "
      f"Fuente: Wikimedia Pageviews API (visitas de personas, agent=user; cifras exactas por artículo). Generado el {context['generado'][:10]}.</p>")
    if demo:
        a("<p class='demo'>DATOS SINTÉTICOS DE PRUEBA. Este reporte se generó con <code>python -m observatorio demo</code> "
          "y no describe la realidad. Configura OBSERVATORIO_CONTACT y ejecuta <code>fetch</code> para usar datos reales.</p>")
    a("<nav class='meta'><a href='#sorprendentes'>Hallazgos sorprendentes</a> · <a href='#hallazgos'>Todos los hallazgos</a> · <a href='#resumen'>Resumen</a> · "
      "<a href='#vida-media'>Vida media</a> · <a href='#estacionalidad'>Estacionalidad</a> · <a href='#temas'>Temas</a> · <a href='#relaciones'>Relaciones</a> · "
      "<a href='#metodos'>Métodos y limitaciones</a></nav>")

    def links(h: dict) -> str:
        items = [f"<a href='{E(l['url'])}' lang='{E(l['idioma'])}' target='_blank' rel='noreferrer'>{E(l['titulo'])} ({E(l['idioma'])}.wikipedia) ↗</a>"
                 for l in h.get("enlaces") or []]
        if h.get("enlaces") and h["enlaces"][0].get("visitas_url"):
            items.append(f"<a href='{E(h['enlaces'][0]['visitas_url'])}' target='_blank' rel='noreferrer'>verificar visitas ↗</a>")
        return f"<br><span class='meta'>{' · '.join(items)}</span>" if items else ""

    a("<h2 id='sorprendentes'>Hallazgos sorprendentes</h2><ol>")
    for h in findings["sorprendentes"]:
        a(f"<li><strong>{E(h['titulo'])}.</strong> {E(h['texto'])}{links(h)}</li>")
    a("</ol>")
    a("<h2 id='hallazgos'>Todos los hallazgos</h2>")
    for h in findings["hallazgos"]:
        a(f"<h3>{E(h['titulo'])}</h3><p>{E(h['texto'])}{links(h)}</p>")

    # Resumen
    a("<h2 id='resumen'>Resumen por tema</h2><p class='meta'>Todos los idiomas sumados. Tendencia: Theil-Sen + Mann-Kendall sobre visitas mensuales.</p>")
    a("<div class='scroll'><table><thead><tr><th>Tema</th><th>Tendencia</th><th class='n'>Visitas 12 meses</th><th class='n'>Picos</th>"
      "<th class='n'>Vida media (mediana, días)</th><th>Estacional</th><th class='n'>Grupo</th></tr></thead><tbody>")
    for tid, t in sorted(topics.items(), key=lambda x: -(x[1]["por_idioma"].get(ALL, {}).get("visitas_12m") or 0)):
        m = t["por_idioma"].get(ALL, {})
        s = m.get("estacionalidad")
        a(f"<tr><td><a href='#t-{tid}'>{E(t['nombre'])}</a></td><td>{_trend_txt(m.get('tendencia'))}</td><td class='n'>{num(m.get('visitas_12m') or 0)}</td>"
          f"<td class='n'>{m.get('n_picos', 0)}</td><td class='n'>{'—' if m.get('vida_media_mediana') is None else num(m['vida_media_mediana'], 1)}</td>"
          f"<td>{'sí, máx. ' + MESES[s['mes_pico'] - 1] if s and s['estacional'] else 'no'}</td><td class='n'>{t.get('grupo', '—')}</td></tr>")
    a("</tbody></table></div>")

    # Vida media
    items = []
    for tid, t in topics.items():
        m = t["por_idioma"].get(ALL, {})
        if m.get("vida_media_mediana") is not None:
            items.append((t["nombre"], m["vida_media_mediana"], f"{t['nombre']}: mediana {num(m['vida_media_mediana'], 1)} días en {m['n_picos']} picos"))
    items.sort(key=lambda x: -x[1])
    a("<h2 id='vida-media'>Vida media de la atención</h2><p class='meta'>Días que tarda el exceso de visitas sobre la línea base en reducirse a la mitad tras un pico "
      "(mediana de los picos de cada tema, todos los idiomas sumados). Más largo = la atención dura más.</p>")
    a(bar_chart(items, unit="d", label="Vida media de la atención por tema") if items else "<p>No se detectaron picos.</p>")

    # Estacionalidad
    rows = []
    for tid, t in sorted(topics.items(), key=lambda x: x[1]["nombre"]):
        s = t["por_idioma"].get(ALL, {}).get("estacionalidad")
        if s:
            rows.append((t["nombre"], s["perfil"], s["estacional"]))
    a("<h2 id='estacionalidad'>Estacionalidad</h2><p class='meta'>Visitas de cada mes respecto de la media móvil de 12 meses (sin tendencia), promediado entre años. "
      "Rojo: más interés que lo normal; azul: menos; gris: normal. * = patrón estacional consistente (fuerza ≥ 0,3 y correlación entre años ≥ 0,4).</p>")
    a(heatmap(rows) if rows else "<p>Datos insuficientes.</p>")

    # Temas
    a("<h2 id='temas'>Temas</h2><label class='toggle'><input type='checkbox' class='logsw'> Escala logarítmica</label>")
    a("<div class='legend'><span><i class='sw' style='background:var(--s1)'></i>español (es)</span><span><i class='sw' style='background:var(--s2)'></i>inglés (en)</span>"
      "<span><i class='sw' style='background:var(--ctx)'></i>otros idiomas (pasa el cursor para ver valores)</span></div>")
    series_js = {}
    for tid, t in sorted(topics.items(), key=lambda x: x[1]["nombre"]):
        d = {k: v for k, v in monthly[tid].items() if k != ALL}
        df = pd.DataFrame(d).asfreq("MS").loc[:end]
        dates = [i.strftime("%Y-%m") for i in df.index]
        ser = {c: [None if pd.isna(v) else float(v) for v in df[c].values] for c in df.columns}
        series_js[tid] = {"fechas": dates, "series": {k: [None if v is None else int(v) for v in vs] for k, vs in ser.items()}}
        a(f"<h3 id='t-{tid}'>{E(t['nombre'])}</h3>")
        if t.get("descripcion"):
            a(f"<p class='meta'>{E(t['descripcion'])} · Wikidata {E(t.get('wikidata') or '')}</p>")
        a(f"<div class='charts'><div class='lin'>{line_chart(dates, ser, log=False, title='Visitas mensuales de ' + t['nombre'], uid=tid)}</div>"
          f"<div class='log'>{line_chart(dates, ser, log=True, title='Visitas mensuales (escala log) de ' + t['nombre'], uid=tid)}</div></div>")
        if t.get("idiomas_sin_articulo"):
            a(f"<p class='meta'>Sin artículo en: {', '.join(IDIOMAS.get(l, l) for l in t['idiomas_sin_articulo'])}.</p>")
        m = t["por_idioma"].get(ALL, {})
        peaks = (m.get("picos") or [])[:5]
        if peaks:
            a("<details><summary>Principales picos (todos los idiomas)</summary><div class='scroll'><table><tr><th>Fecha</th><th class='n'>Visitas</th>"
              "<th class='n'>× línea base</th><th class='n'>Vida media</th><th class='n'>Vuelta a lo normal</th></tr>")
            for p in peaks:
                a(f"<tr><td>{p['fecha']}</td><td class='n'>{num(p['visitas'])}</td><td class='n'>{num(p['magnitud'], 1)}</td>"
                  f"<td class='n'>{'—' if p['vida_media_dias'] is None else str(p['vida_media_dias']) + ' d'}</td>"
                  f"<td class='n'>{'no volvió' if p['vuelta_normalidad_dias'] is None else str(p['vuelta_normalidad_dias']) + ' d'}</td></tr>")
            a("</table></div></details>")
        comps = t.get("comparacion_idiomas") or []
        if comps:
            w = t.get("peso_relativo") or {}
            a("<details><summary>Comparación entre idiomas (frente al inglés)</summary><div class='scroll'><table><tr><th>Idioma</th><th class='n'>r mensual (log)</th>"
              "<th class='n'>Desfase (días)</th><th class='n'>r en ese desfase</th><th class='n'>Peso relativo</th></tr>")
            for c in comps:
                lg = c["desfase"]
                lagtxt = "—" if not lg else (f"{lg['desfase_dias']:+d}" + ("" if lg["informativo"] else " (no concluyente)"))
                a(f"<tr><td>{IDIOMAS.get(c['idioma'], c['idioma'])}</td><td class='n'>{'—' if c['r_mensual_log'] is None else num(c['r_mensual_log'], 2)}</td>"
                  f"<td class='n'>{lagtxt}</td><td class='n'>{'—' if not lg else num(lg['r_max'], 2)}</td>"
                  f"<td class='n'>{num(w[c['idioma']]['indice'], 2) if c['idioma'] in w else '—'}</td></tr>")
            a("</table><p class='meta'>Desfase positivo: el idioma va detrás del inglés. Peso relativo 2,0 = el tema pesa el doble en ese idioma que en el idioma promedio.</p></div></details>")

    # Relaciones
    a("<h2 id='relaciones'>Relaciones entre temas</h2>")
    a("<h3>Semánticas (Wikipedia y Wikidata)</h3>")
    if rel["semanticas"]:
        a("<ul>" + "".join(f"<li><strong>{E(names[r['a']])} – {E(names[r['b']])}</strong>: {E('; '.join(r['evidencias'][:2]))}</li>" for r in rel["semanticas"]) + "</ul>")
    else:
        a("<p>No se encontraron vínculos directos entre los temas.</p>")
    a("<h3>Estadísticas (atención que sube y baja junta)</h3>")
    if rel["estadisticas"]:
        a("<ul>" + "".join(f"<li>{E(names[r['a']])} – {E(names[r['b']])}: r = {num(r['r'], 2)} ({r['semanas']} semanas)</li>"
                         for r in sorted(rel["estadisticas"], key=lambda r: -r["r"])) + "</ul>")
    else:
        a("<p>Ningún par supera el umbral (r ≥ 0,25, p ≤ 0,001).</p>")
    a("<h3>Grupos con trayectorias parecidas</h3><ul>")
    for g in clusters.get("grupos", []):
        a(f"<li>Grupo {g['id']}: {E(', '.join(g['nombres']))}" + ("" if g["correlacion_interna"] is None else f" (correlación interna media {num(g['correlacion_interna'], 2)})") + "</li>")
    a(f"</ul><p class='meta'>{E(clusters.get('metodo', ''))}.</p>")

    # Métodos y limitaciones
    a("<h2 id='metodos'>Métodos y limitaciones</h2><ul>"
      "<li><b>Tendencia</b>: pendiente de Theil-Sen del logaritmo de las visitas mensuales; «sube/baja» si Mann-Kendall da p &lt; 0,05 y el cambio supera ±10 % anual.</li>"
      "<li><b>Picos</b>: línea base = mediana de los 56 días previos; pico si el z robusto (MAD) ≥ 6, triplica la línea base y la supera en ≥ 200 visitas.</li>"
      "<li><b>Vida media</b>: días hasta que el exceso sobre la línea base cae a la mitad; <b>vuelta a lo normal</b>: días hasta que cae bajo el 10 % durante 3 días seguidos.</li>"
      "<li><b>Estacionalidad</b>: serie mensual sin tendencia (media móvil centrada 2×12); fuerza = varianza explicada por el perfil mensual.</li>"
      "<li><b>Desfase</b>: correlación cruzada de anomalías diarias (log menos mediana móvil de 28 días), −30 a +30 días.</li>"
      "<li><b>Relaciones estadísticas</b>: correlación de Pearson de anomalías semanales sin tendencia.</li></ul><h3>Limitaciones</h3><ul>")
    for l in LIMITACIONES:
        a(f"<li>{E(l)}</li>")
    ms = context.get("proporcion_movil", {}).get("en", {})
    if ms:
        ys = sorted(ms, key=int)
        a(f"<li>Contexto: la proporción móvil en Wikipedia en inglés fue {pct(ms[ys[0]])} en {ys[0]} y {pct(ms[ys[-1]])} en {ys[-1]}.</li>")
    a("</ul></main>")
    a(f"<script>window.SERIES={json.dumps(series_js, separators=(',', ':'))};{JS}</script></body></html>")

    PATHS.reports.mkdir(parents=True, exist_ok=True)
    path = PATHS.reports / "observatorio.html"
    path.write_text("".join(P), encoding="utf-8")
    return str(path)

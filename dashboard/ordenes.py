import html
import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs
from sqlalchemy import create_engine, text


# ─────────────────────────────────────
# 0. AJUSTES
# ─────────────────────────────────────

DB_URL = "postgresql+psycopg2://karen@localhost:5432/Viz2026"
ANIO = 2026

# Paleta basada en Cornflower (#6495ED); quien tiene más importe toma el primer color
PALETA = [
    "#6495ED",  # cornflower
    "#2F4B8F",  # azul marino
    "#3FB8AF",  # turquesa
    "#9B7EDE",  # violeta suave
    "#F28B82",  # coral
    "#F4B860",  # ámbar
    "#4C5FD5",  # índigo
    "#6CCB9A",  # menta
    "#E58FB6",  # rosa
    "#8392AB",  # gris azulado
]

MESES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MESES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ─────────────────────────────────────
# 1. UTILIDADES
# ─────────────────────────────────────

def fmt_dinero(v: float) -> str:
    return f"${v:,.2f}"


def sparkline_svg(valores, ancho=260, alto=70, pad=8) -> str:
    """Mini gráfica de línea + área para el indicador principal."""
    n = len(valores)
    if n < 2:
        return ""
    mn, mx = min(valores), max(valores)
    rango = (mx - mn) or 1
    pts = [
        (i * ancho / (n - 1), pad + (1 - (v - mn) / rango) * (alto - 2 * pad))
        for i, v in enumerate(valores)
    ]
    linea = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = f"{linea} L{ancho},{alto} L0,{alto} Z"
    ux, uy = pts[-1]
    return (
        f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Importe total por mes">'
        f'<path d="{area}" fill="rgba(255,255,255,.28)"/>'
        f'<path d="{linea}" fill="none" stroke="#fff" stroke-width="2.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ux:.1f}" cy="{uy:.1f}" r="4.5" fill="#fff" stroke="#1E2A4A" stroke-width="2"/>'
        f"</svg>"
    )


# ─────────────────────────────────────
# 2. CONSULTA
# ─────────────────────────────────────
# "semana" son bloques de días del mes: 1 = días 1-7, 2 = 8-14, ... 5 = 29 en adelante.

engine = create_engine(DB_URL)

query = text("""
    SELECT
        EXTRACT(MONTH FROM "Fecha")::INTEGER AS mes,
        (FLOOR((EXTRACT(DAY FROM "Fecha") - 1) / 7) + 1)::INTEGER
            AS semana,
        COALESCE(
            NULLIF(TRIM("Responsable"), ''),
            'Sin responsable'
        ) AS responsable,
        SUM("Total") AS importe_total,
        COUNT(*) AS num_ordenes
    FROM ordenes_punto_venta
    WHERE "Fecha" >= '2026-01-01'
      AND "Fecha" < '2027-01-01'
    GROUP BY mes, semana, responsable
    ORDER BY mes, semana, responsable;
""")

with engine.connect() as connection:
    df = pd.read_sql(query, connection)

if df.empty:
    raise ValueError(f"No se encontraron órdenes de {ANIO}.")

df["mes"] = df["mes"].astype(int)
df["semana"] = df["semana"].astype(int)
# SUM() llega como Decimal; se convierte a número para sumar y exportar sin sorpresas
df["importe_total"] = pd.to_numeric(df["importe_total"], errors="coerce").fillna(0.0)
df["num_ordenes"] = df["num_ordenes"].astype(int)


# ─────────────────────────────────────
# 3. PREPARAR LOS DATOS
# ─────────────────────────────────────

total_importe = df["importe_total"].sum()
total_ordenes = int(df["num_ordenes"].sum())
ticket = total_importe / total_ordenes if total_ordenes else 0

meses_disponibles = sorted(df["mes"].unique().tolist())
ultimo_mes = meses_disponibles[-1]

por_resp = (
    df.groupby("responsable")
    .agg(importe=("importe_total", "sum"), ordenes=("num_ordenes", "sum"))
    .sort_values("importe", ascending=False)
)
responsables = por_resp.index.tolist()
color_de = {r: PALETA[i % len(PALETA)] for i, r in enumerate(responsables)}

por_mes = df.groupby("mes")["importe_total"].sum().sort_index()
spark = sparkline_svg(por_mes.tolist())

filas_resp = "".join(
    f"""
    <li>
      <button type="button" class="user-row" data-r="{html.escape(r, quote=True)}" aria-pressed="false">
        <span class="dot" style="background:{color_de[r]}"></span>
        <span class="user-main">
          <span class="user-name">{html.escape(r)}</span>
          <span class="user-meta">{int(v['ordenes']):,} órdenes</span>
        </span>
        <span class="user-avg">{fmt_dinero(v['importe'])}</span>
      </button>
    </li>"""
    for r, v in por_resp.iterrows()
)

botones_vista = f'<button type="button" data-v="anual" aria-pressed="false">{ANIO}</button>' + "".join(
    f'<button type="button" data-v="{m}" aria-pressed="false">{MESES_CORTO[m - 1]}</button>'
    for m in meses_disponibles
)

data_json = (
    df[["mes", "semana", "responsable", "importe_total", "num_ordenes"]]
    .to_json(orient="records", force_ascii=False)
    .replace("</", "<\\/")  # evita cerrar el <script> por accidente
)


# ─────────────────────────────────────
# 4. PLANTILLA HTML
# ─────────────────────────────────────

PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Órdenes del punto de venta</title>
<style>
:root {
  --bg: #F4F7FD;
  --card: #FFFFFF;
  --ink: #1E2A4A;
  --muted: #5B6A8A;
  --line: #DCE4F5;
  --accent: #6495ED;        /* cornflower */
  --accent-strong: #3F68C4; /* para texto sobre blanco */
  --accent-soft: #E8EFFC;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: linear-gradient(180deg, #E2EBFC 0, var(--bg) 340px) no-repeat, var(--bg);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
}

.container { width: min(1240px, 100%); margin: 0 auto; padding: 32px 28px 40px; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; border-radius: 8px; }

h1 { font-size: clamp(26px, 3vw, 32px); letter-spacing: -0.7px; margin: 0 0 4px; }
.subtitle { color: var(--muted); font-size: 15px; margin: 0 0 24px; }

.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; }

.kpis { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: 14px; margin-bottom: 18px; }
.side-kpis { display: grid; gap: 14px; }
.kpi { padding: 18px 22px; display: flex; flex-direction: column; justify-content: center; }
.kpi-label { color: var(--muted); font-size: 13.5px; margin-bottom: 4px; }
.kpi-value { font-size: clamp(22px, 2.4vw, 30px); font-weight: 700; letter-spacing: -0.8px; line-height: 1.15; overflow-wrap: anywhere; }
.kpi-sub { color: var(--muted); font-size: 13px; margin-top: 4px; }

.hero {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 24px;
  padding: 26px 28px; border: 0; color: #0F1D40;
  background: linear-gradient(135deg, #6495ED 0%, #82AAF4 100%);
  box-shadow: 0 10px 30px -12px rgba(100, 149, 237, .7);
}
.hero .kpi-label { color: #1E2A4A; opacity: .8; font-size: 14px; }
.hero-value { font-size: clamp(34px, 4.6vw, 54px); font-weight: 750; letter-spacing: -2px; line-height: 1.05; overflow-wrap: anywhere; }
.hero-sub { font-size: 13.5px; margin-top: 8px; opacity: .8; }
.spark { flex: 1; min-width: 140px; max-width: 300px; }
.spark svg { width: 100%; height: auto; display: block; overflow: visible; }
.spark-cap { display: block; font-size: 12px; opacity: .8; text-align: right; margin-top: 6px; }

.main-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start; }

.panel { padding: 22px 22px 12px; }
.panel h2, .users h2 { font-size: 17px; margin: 0 0 12px; letter-spacing: -0.2px; }

.seg { display: flex; flex-wrap: wrap; background: var(--accent-soft); border-radius: 10px; padding: 3px; gap: 2px; width: fit-content; max-width: 100%; }
.seg button {
  border: 0; background: none; padding: 7px 13px; border-radius: 8px; font: inherit;
  font-size: 13.5px; color: var(--muted); cursor: pointer;
}
.seg button[aria-pressed="true"] { background: #fff; color: var(--ink); font-weight: 600; box-shadow: 0 1px 3px rgba(30, 42, 74, .12); }

.selection { font-size: 13.5px; color: var(--muted); display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin: 10px 0 4px; min-height: 30px; }
.link-btn { background: none; border: 0; color: var(--accent-strong); font-weight: 600; font-size: 13.5px; cursor: pointer; padding: 4px 6px; }
.link-btn[hidden] { display: none; }

.users { padding: 20px 12px 12px; }
.users h2 { margin: 0 0 2px 8px; }
.users .desc { color: var(--muted); font-size: 12.5px; margin: 0 0 10px 8px; }
.user-list { list-style: none; margin: 0; padding: 0; max-height: 440px; overflow-y: auto; }
.user-row {
  width: 100%; display: grid; grid-template-columns: 12px 1fr auto; column-gap: 10px;
  align-items: center; text-align: left; border: 1px solid transparent; background: none;
  color: inherit; font: inherit; padding: 10px; border-radius: 10px; cursor: pointer;
}
.user-row:hover { background: var(--bg); }
.user-row[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.user-main { display: flex; flex-direction: column; min-width: 0; }
.user-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-meta { color: var(--muted); font-size: 12px; }
.user-avg { font-size: 13.5px; font-weight: 600; }

@media (max-width: 960px) {
  .main-grid { grid-template-columns: 1fr; }
  .side-kpis { grid-template-columns: 1fr 1fr; }
  .user-list { max-height: 340px; }
}
@media (max-width: 620px) {
  .container { padding: 20px 14px 28px; }
  .kpis, .side-kpis { grid-template-columns: 1fr; }
  .hero { flex-direction: column; align-items: flex-start; padding: 22px 20px; }
  .spark { width: 100%; max-width: none; }
  .panel { padding: 18px 12px 10px; }
}
@media (prefers-reduced-motion: no-preference) {
  .user-row, .seg button { transition: background .15s, border-color .15s; }
}
</style>
</head>

<body>
<main class="container">

  <h1>Órdenes del punto de venta</h1>
  <p class="subtitle">Importe por responsable durante __YEAR__.</p>

  <section class="kpis" aria-label="Resumen general">
    <article class="card hero">
      <div>
        <div class="kpi-label">Importe total</div>
        <div class="hero-value" data-count="__TOTAL_NUM__" data-fmt="money">__TOTAL__</div>
        <div class="hero-sub">suma de todas las órdenes de __YEAR__</div>
      </div>
      <div class="spark">__SPARK__<span class="spark-cap">Importe por mes</span></div>
    </article>
    <div class="side-kpis">
      <article class="card kpi">
        <div class="kpi-label">Órdenes</div>
        <div class="kpi-value" data-count="__ORDENES_NUM__" data-fmt="int">__ORDENES__</div>
      </article>
      <article class="card kpi">
        <div class="kpi-label">Ticket promedio</div>
        <div class="kpi-value">__TICKET__</div>
        <div class="kpi-sub">importe por orden</div>
      </article>
    </div>
  </section>

  <div class="main-grid">

    <section class="card panel" aria-labelledby="t-semanal">
      <h2 id="t-semanal">Importe por responsable</h2>

      <div class="seg" role="group" aria-label="Elegir periodo">__BOTONES__</div>

      <div class="selection" aria-live="polite">
        <span id="selectionText">Todos los responsables</span>
        <button class="link-btn" id="clearBtn" type="button" hidden>Quitar selección</button>
      </div>

      <div role="img" aria-label="Gráfica de barras apiladas con el importe por responsable">
        <div id="grafica" style="width:100%;height:440px"></div>
      </div>
    </section>

    <aside class="card users" aria-labelledby="t-resp">
      <h2 id="t-resp">Responsables</h2>
      <p class="desc">Importe de todo __YEAR__.</p>
      <ul class="user-list">__FILAS__</ul>
    </aside>

  </div>
</main>

<script>__PLOTLYJS__</script>
<script>
const rawData = __DATA__;
const colors = __COLORES_JSON__;
const responsables = __RESP_JSON__;
const mesesDisponibles = __MESES_JSON__;
const YEAR = __YEAR__;
const MES_CORTO = __MES_CORTO_JSON__;
const MES_LARGO = __MES_LARGO_JSON__;

const rows = Array.from(document.querySelectorAll(".user-row"));
const segBtns = Array.from(document.querySelectorAll(".seg button"));
const selectionText = document.getElementById("selectionText");
const clearBtn = document.getElementById("clearBtn");
const selected = new Set();
let vista = __ULTIMO_MES__;   // "anual" o número de mes

function money(v) {
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Las "semanas" son bloques de días: 1-7, 8-14, 15-21, 22-28 y 29 en adelante
function rangoSemana(mes, w) {
  const diasMes = new Date(YEAR, mes, 0).getDate();
  const ini = (w - 1) * 7 + 1;
  const fin = w >= 5 ? diasMes : Math.min(w * 7, diasMes);
  return ini === fin ? String(ini) : ini + "–" + fin;
}

function render() {
  const anual = vista === "anual";
  const filas = anual ? rawData : rawData.filter(r => r.mes === vista);

  let claves, etiquetas;
  if (anual) {
    claves = mesesDisponibles;
    etiquetas = claves.map(m => MES_CORTO[m - 1]);
  } else {
    const maxW = Math.max(...filas.map(r => r.semana));
    claves = Array.from({ length: maxW }, (_, i) => i + 1);
    etiquetas = claves.map(w => rangoSemana(vista, w));
  }

  // responsable -> clave -> { imp, ord }
  const acum = {};
  filas.forEach(r => {
    const k = anual ? r.mes : r.semana;
    acum[r.responsable] = acum[r.responsable] || {};
    const a = acum[r.responsable][k] = acum[r.responsable][k] || { imp: 0, ord: 0 };
    a.imp += Number(r.importe_total);
    a.ord += Number(r.num_ordenes);
  });

  const any = selected.size > 0;
  const traces = responsables.map(resp => ({
    type: "bar",
    name: resp,
    x: etiquetas,
    y: claves.map(k => acum[resp] && acum[resp][k] ? acum[resp][k].imp : null),
    customdata: claves.map(k => acum[resp] && acum[resp][k] ? acum[resp][k].ord : 0),
    marker: { color: colors[resp] },
    visible: !any || selected.has(resp),
    hovertemplate: "%{y:$,.2f} (%{customdata} órdenes)"
  }));

  const layout = {
    barmode: "stack",
    bargap: 0.28,
    hovermode: "x unified",
    showlegend: false,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color: "#5B6A8A", size: 12 },
    margin: { l: 10, r: 16, t: 16, b: 10 },
    hoverlabel: { bgcolor: "#FFFFFF", bordercolor: "#DCE4F5", font: { color: "#1E2A4A" } },
    xaxis: { type: "category", categoryorder: "array", categoryarray: etiquetas,
             title: { text: anual ? "Mes" : "Días del mes" }, showgrid: false, automargin: true },
    yaxis: { title: { text: "Importe" }, tickprefix: "$", tickformat: "~s",
             gridcolor: "#E6ECF8", zeroline: false, automargin: true }
  };

  Plotly.react("grafica", traces, layout,
    { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] });

  // Resumen de la selección para el periodo que se está viendo
  if (!any) {
    selectionText.textContent = "Todos los responsables";
  } else {
    let imp = 0, ord = 0;
    filas.forEach(r => { if (selected.has(r.responsable)) { imp += Number(r.importe_total); ord += Number(r.num_ordenes); } });
    const quien = selected.size === 1 ? Array.from(selected)[0] : selected.size + " responsables";
    const cuando = anual ? YEAR : MES_LARGO[vista - 1];
    selectionText.textContent = quien + ": " + money(imp) + " en " + cuando + " (" + ord.toLocaleString("en-US") + " órdenes)";
  }
}

function actualizar() {
  rows.forEach(r => r.setAttribute("aria-pressed", selected.has(r.dataset.r)));
  segBtns.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === String(vista))));
  clearBtn.hidden = selected.size === 0;
  render();
}

rows.forEach(r => r.addEventListener("click", () => {
  const k = r.dataset.r;
  selected.has(k) ? selected.delete(k) : selected.add(k);
  actualizar();
}));

clearBtn.addEventListener("click", () => { selected.clear(); actualizar(); });

segBtns.forEach(b => b.addEventListener("click", () => {
  vista = b.dataset.v === "anual" ? "anual" : Number(b.dataset.v);
  actualizar();
}));

actualizar();

// Un solo momento animado: los números cuentan hasta su valor al cargar
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.querySelectorAll("[data-count]").forEach(el => {
    const target = parseFloat(el.dataset.count), kind = el.dataset.fmt;
    const show = v => el.textContent = kind === "money" ? money(v) : Math.round(v).toLocaleString("en-US");
    const t0 = performance.now(), D = 900;
    (function step(t) {
      const p = Math.min(1, (t - t0) / D);
      show(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step); else show(target);
    })(t0);
  });
}
</script>

</body>
</html>
"""

reemplazos = {
    "__YEAR__": str(ANIO),
    "__TOTAL_NUM__": f"{total_importe:.2f}",
    "__TOTAL__": fmt_dinero(total_importe),
    "__SPARK__": spark,
    "__ORDENES_NUM__": str(total_ordenes),
    "__ORDENES__": f"{total_ordenes:,}",
    "__TICKET__": fmt_dinero(ticket),
    "__BOTONES__": botones_vista,
    "__FILAS__": filas_resp,
    "__COLORES_JSON__": json.dumps(color_de, ensure_ascii=False),
    "__RESP_JSON__": json.dumps(responsables, ensure_ascii=False),
    "__MESES_JSON__": json.dumps(meses_disponibles),
    "__MES_CORTO_JSON__": json.dumps(MESES_CORTO, ensure_ascii=False),
    "__MES_LARGO_JSON__": json.dumps(MESES_LARGO, ensure_ascii=False),
    "__ULTIMO_MES__": str(ultimo_mes),
    "__DATA__": data_json,
    "__PLOTLYJS__": None,  # se inserta al final: el bundle es enorme
}

documento = PLANTILLA
for clave, valor in reemplazos.items():
    if valor is not None:
        documento = documento.replace(clave, valor)
documento = documento.replace("__PLOTLYJS__", get_plotlyjs())


# ─────────────────────────────────────
# 5. GUARDAR EL HTML
# ─────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

salida = OUTPUT_DIR / "ordenes.html"
salida.write_text(documento, encoding="utf-8")

print(f"Dashboard generado: {salida}")
print(f"Órdenes analizadas: {total_ordenes:,}")
print(f"Importe total: {fmt_dinero(total_importe)}")

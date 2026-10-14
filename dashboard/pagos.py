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

# Paleta basada en Cornflower (#6495ED); el método con más importe toma el primer color
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

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


# ─────────────────────────────────────
# 1. UTILIDADES
# ─────────────────────────────────────

def fmt_dinero(v: float) -> str:
    return f"${v:,.2f}"


def fmt_fecha(d: pd.Timestamp) -> str:
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


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
# 2. CONSULTA (solo 2025 y 2026)
# ─────────────────────────────────────

engine = create_engine(DB_URL)

query = text("""
    SELECT
        TO_TIMESTAMP(LEFT(TRIM("Fecha"), 19), 'YYYY-MM-DD HH24:MI:SS')::date AS fecha,
        COALESCE(
            NULLIF(TRIM("Método de pago"), ''),
            'Sin método'
        ) AS metodo_pago,
        SUM("Importe") AS importe_total
    FROM pagos_punto_venta
    WHERE TRIM("Fecha") ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$'
      AND LEFT(TRIM("Fecha"), 10) >= '2025-01-01'
      AND LEFT(TRIM("Fecha"), 10) < '2027-01-01'
    GROUP BY fecha, metodo_pago
    ORDER BY fecha, metodo_pago;
""")

with engine.connect() as connection:
    df = pd.read_sql(query, connection)

if df.empty:
    raise ValueError(
        "No se encontraron pagos de 2025-2026. "
        "Revisa el formato de la columna Fecha."
    )

df["fecha"] = pd.to_datetime(df["fecha"])
# SUM() llega como Decimal; se convierte a número para sumar y exportar sin sorpresas
df["importe_total"] = pd.to_numeric(df["importe_total"], errors="coerce").fillna(0.0)


# ─────────────────────────────────────
# 3. PREPARAR LOS DATOS
# ─────────────────────────────────────

total_importe = df["importe_total"].sum()

por_metodo = (
    df.groupby("metodo_pago")["importe_total"].sum().sort_values(ascending=False)
)
metodos = por_metodo.index.tolist()
color_de = {m: PALETA[i % len(PALETA)] for i, m in enumerate(metodos)}

metodo_top = metodos[0]
share_top = (por_metodo.iloc[0] / total_importe * 100) if total_importe else 0

rango_fechas = f"{fmt_fecha(df['fecha'].min())} a {fmt_fecha(df['fecha'].max())}"

por_mes = df.groupby(df["fecha"].dt.to_period("M"))["importe_total"].sum().sort_index()
spark = sparkline_svg(por_mes.tolist())

filas_metodos = "".join(
    f"""
    <li>
      <button type="button" class="user-row" data-m="{html.escape(m, quote=True)}"
              data-total="{v:.2f}" aria-pressed="false">
        <span class="dot" style="background:{color_de[m]}"></span>
        <span class="user-main">
          <span class="user-name">{html.escape(m)}</span>
          <span class="user-meta">{(v / total_importe * 100 if total_importe else 0):.1f}% del total</span>
        </span>
        <span class="user-avg">{fmt_dinero(v)}</span>
      </button>
    </li>"""
    for m, v in por_metodo.items()
)

# Datos crudos para que el selector de periodo funcione sin conexión
data_json = (
    df.assign(fecha=df["fecha"].dt.strftime("%Y-%m-%d"))
    [["fecha", "metodo_pago", "importe_total"]]
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
<title>Pagos del punto de venta</title>
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

.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
.seg { display: inline-flex; background: var(--accent-soft); border-radius: 10px; padding: 3px; gap: 2px; }
.seg button {
  border: 0; background: none; padding: 7px 14px; border-radius: 8px; font: inherit;
  font-size: 13.5px; color: var(--muted); cursor: pointer;
}
.seg button[aria-pressed="true"] { background: #fff; color: var(--ink); font-weight: 600; box-shadow: 0 1px 3px rgba(30, 42, 74, .12); }
.selection { font-size: 13.5px; color: var(--muted); display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.link-btn { background: none; border: 0; color: var(--accent-strong); font-weight: 600; font-size: 13.5px; cursor: pointer; padding: 4px 6px; }
.link-btn[hidden] { display: none; }

.users { padding: 20px 12px 12px; }
.users h2 { margin-left: 8px; }
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

  <h1>Pagos del punto de venta</h1>
  <p class="subtitle">Del __RANGO__</p>

  <section class="kpis" aria-label="Resumen general">
    <article class="card hero">
      <div>
        <div class="kpi-label">Importe total</div>
        <div class="hero-value" data-count="__TOTAL_NUM__" data-fmt="money">__TOTAL__</div>
        <div class="hero-sub">en todos los métodos de pago</div>
      </div>
      <div class="spark">__SPARK__<span class="spark-cap">Importe por mes</span></div>
    </article>
    <div class="side-kpis">
      <article class="card kpi">
        <div class="kpi-label">Método principal</div>
        <div class="kpi-value">__TOP__</div>
        <div class="kpi-sub">__TOP_SHARE__% del importe total</div>
      </article>
      <article class="card kpi">
        <div class="kpi-label">Métodos de pago</div>
        <div class="kpi-value" data-count="__METODOS_NUM__" data-fmt="int">__METODOS__</div>
      </article>
    </div>
  </section>

  <div class="main-grid">

    <section class="card panel" aria-labelledby="t-importe">
      <h2 id="t-importe">Importe por método de pago</h2>

      <div class="toolbar">
        <div class="seg" role="group" aria-label="Agrupar por">
          <button type="button" data-p="Día" aria-pressed="false">Día</button>
          <button type="button" data-p="Semana" aria-pressed="false">Semana</button>
          <button type="button" data-p="Mes" aria-pressed="true">Mes</button>
          <button type="button" data-p="Trimestre" aria-pressed="false">Trimestre</button>
        </div>
        <div class="selection" aria-live="polite">
          <span id="selectionText">Todos los métodos</span>
          <button class="link-btn" id="clearBtn" type="button" hidden>Quitar selección</button>
        </div>
      </div>

      <div role="img" aria-label="Gráfica de barras apiladas con el importe por método de pago">
        <div id="grafica" style="width:100%;height:440px"></div>
      </div>
    </section>

    <aside class="card users" aria-labelledby="t-metodos">
      <h2 id="t-metodos">Métodos de pago</h2>
      <ul class="user-list">__FILAS__</ul>
    </aside>

  </div>
</main>

<script>__PLOTLYJS__</script>
<script>
const rawData = __DATA__;
const colors = __COLORES_JSON__;
const metodos = __METODOS_JSON__;
const MES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

const rows = Array.from(document.querySelectorAll(".user-row"));
const segBtns = Array.from(document.querySelectorAll(".seg button"));
const selectionText = document.getElementById("selectionText");
const clearBtn = document.getElementById("clearBtn");
const selected = new Set();
let periodo = "Mes";

function money(v) {
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Clave de orden + etiqueta de cada fila según el periodo elegido
function periodoDe(fecha) {
  const [y, m, d] = fecha.split("-").map(Number);
  if (periodo === "Día") {
    return { key: y * 10000 + m * 100 + d, label: d + " " + MES[m - 1] + " " + y };
  }
  if (periodo === "Semana") {
    const t = new Date(Date.UTC(y, m - 1, d));
    t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7)); // lunes
    return { key: t.getTime(),
             label: t.getUTCDate() + " " + MES[t.getUTCMonth()] + " " + t.getUTCFullYear() };
  }
  if (periodo === "Mes") {
    return { key: y * 100 + m, label: MES[m - 1] + " " + y };
  }
  const q = Math.floor((m - 1) / 3) + 1;
  return { key: y * 10 + q, label: "T" + q + " " + y };
}

function render() {
  const buckets = new Map();   // etiqueta -> { key, valores: {metodo: importe} }
  rawData.forEach(r => {
    const p = periodoDe(r.fecha);
    if (!buckets.has(p.label)) buckets.set(p.label, { key: p.key, valores: {} });
    const b = buckets.get(p.label);
    b.valores[r.metodo_pago] = (b.valores[r.metodo_pago] || 0) + Number(r.importe_total);
  });

  const ordenados = Array.from(buckets.entries()).sort((a, b) => a[1].key - b[1].key);
  const etiquetas = ordenados.map(e => e[0]);
  const any = selected.size > 0;

  const traces = metodos.map(m => ({
    type: "bar",
    name: m,
    x: etiquetas,
    y: ordenados.map(e => e[1].valores[m] || 0),
    marker: { color: colors[m] },
    visible: !any || selected.has(m),
    hovertemplate: "%{y:$,.2f}"
  }));

  const layout = {
    barmode: "stack",
    bargap: 0.25,
    hovermode: "x unified",
    showlegend: false,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color: "#5B6A8A", size: 12 },
    margin: { l: 10, r: 16, t: 16, b: 10 },
    hoverlabel: { bgcolor: "#FFFFFF", bordercolor: "#DCE4F5", font: { color: "#1E2A4A" } },
    xaxis: { type: "category", categoryorder: "array", categoryarray: etiquetas,
             nticks: 12, showgrid: false, automargin: true },
    yaxis: { title: { text: "Importe" }, tickprefix: "$", tickformat: "~s",
             gridcolor: "#E6ECF8", zeroline: false, automargin: true }
  };

  Plotly.react("grafica", traces, layout,
    { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] });
}

function paintSelection() {
  rows.forEach(r => r.setAttribute("aria-pressed", selected.has(r.dataset.m)));
  if (selected.size === 0) {
    selectionText.textContent = "Todos los métodos";
  } else {
    let total = 0;
    rows.forEach(r => { if (selected.has(r.dataset.m)) total += parseFloat(r.dataset.total); });
    const quien = selected.size === 1 ? Array.from(selected)[0] : selected.size + " métodos";
    selectionText.textContent = quien + ": " + money(total) + " en total";
  }
  clearBtn.hidden = selected.size === 0;
  render();
}

rows.forEach(r => r.addEventListener("click", () => {
  const m = r.dataset.m;
  selected.has(m) ? selected.delete(m) : selected.add(m);
  paintSelection();
}));

clearBtn.addEventListener("click", () => { selected.clear(); paintSelection(); });

segBtns.forEach(b => b.addEventListener("click", () => {
  periodo = b.dataset.p;
  segBtns.forEach(x => x.setAttribute("aria-pressed", x === b));
  render();
}));

render();

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
    "__RANGO__": rango_fechas,
    "__TOTAL_NUM__": f"{total_importe:.2f}",
    "__TOTAL__": fmt_dinero(total_importe),
    "__SPARK__": spark,
    "__TOP_SHARE__": f"{share_top:.1f}",
    "__TOP__": html.escape(metodo_top),
    "__METODOS_NUM__": str(len(metodos)),
    "__METODOS__": f"{len(metodos):,}",
    "__FILAS__": filas_metodos,
    "__COLORES_JSON__": json.dumps(color_de, ensure_ascii=False),
    "__METODOS_JSON__": json.dumps(metodos, ensure_ascii=False),
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

salida = OUTPUT_DIR / "pagos.html"
salida.write_text(documento, encoding="utf-8")

print(f"Dashboard generado: {salida}")
print(f"Importe total: {fmt_dinero(total_importe)}")
print(f"Registros consultados: {len(df):,}")
print(f"Métodos de pago: {len(metodos)}")

import html
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text


# ─────────────────────────────────────
# 0. AJUSTES
# ─────────────────────────────────────

DB_URL = "postgresql+psycopg2://karen@localhost:5432/Viz2026"

# Sesiones más largas que esto se señalan como posible cierre olvidado
UMBRAL_SESION_LARGA_H = 24

# Paleta basada en Cornflower (#6495ED) + acentos que armonizan con él
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

def fmt_horas(h: float) -> str:
    horas = int(h)
    minutos = round((h - horas) * 60)
    if minutos == 60:
        horas, minutos = horas + 1, 0
    return f"{horas} h {minutos:02d} min"


def fmt_fecha(d: pd.Timestamp) -> str:
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


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
        f'<svg viewBox="0 0 {ancho} {alto}" role="img" '
        f'aria-label="Promedio semanal de duración">'
        f'<path d="{area}" fill="rgba(255,255,255,.28)"/>'
        f'<path d="{linea}" fill="none" stroke="#fff" stroke-width="2.5" '
        f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
        f'<circle cx="{ux:.1f}" cy="{uy:.1f}" r="4.5" fill="#fff" stroke="#1E2A4A" stroke-width="2" '
        f'vector-effect="non-scaling-stroke"/></svg>'
    )


def fmt_sesiones(n: int) -> str:
    return f"{n:,} sesión" if n == 1 else f"{n:,} sesiones"


# ─────────────────────────────────────
# 2. CONSULTAS
# ─────────────────────────────────────

engine = create_engine(DB_URL)

query_sesiones = text("""
    SELECT
        "ID de sesión" AS id_sesion,
        "Abierta por" AS usuario,
        DATE_TRUNC('week', "Fecha de apertura")::date AS semana,
        EXTRACT(
            EPOCH FROM ("Fecha de cierre" - "Fecha de apertura")
        ) / 3600.0 AS duracion_horas
    FROM sesion_punto_venta
    WHERE "Fecha de apertura" IS NOT NULL
      AND "Fecha de cierre" IS NOT NULL
      AND "Fecha de cierre" >= "Fecha de apertura"
      AND "Abierta por" IS NOT NULL
      AND TRIM("Abierta por") <> ''
    ORDER BY semana, usuario;
""")

query_abiertas = text("""
    SELECT COUNT(*) FROM sesion_punto_venta
    WHERE "Fecha de apertura" IS NOT NULL
      AND "Fecha de cierre" IS NULL;
""")

with engine.connect() as connection:
    df = pd.read_sql(query_sesiones, connection)
    sesiones_abiertas = connection.execute(query_abiertas).scalar() or 0

if df.empty:
    raise ValueError("No se encontraron sesiones cerradas válidas.")


# ─────────────────────────────────────
# 3. PREPARAR LOS DATOS
# ─────────────────────────────────────

df["semana"] = pd.to_datetime(df["semana"])

resumen = (
    df.groupby(["semana", "usuario"], as_index=False)
    .agg(duracion_promedio=("duracion_horas", "mean"),
         sesiones=("id_sesion", "count"))
)
resumen["semana_label"] = resumen["semana"].apply(fmt_fecha)
resumen["dur_texto"] = resumen["duracion_promedio"].apply(fmt_horas)
resumen["ses_texto"] = resumen["sesiones"].apply(fmt_sesiones)

promedio_general = df["duracion_horas"].mean()
total_sesiones = len(df)
total_usuarios = df["usuario"].nunique()
sesiones_largas = int((df["duracion_horas"] > UMBRAL_SESION_LARGA_H).sum())

usuarios = sorted(df["usuario"].unique().tolist())
color_de = {u: PALETA[i % len(PALETA)] for i, u in enumerate(usuarios)}

stats = (
    df.groupby("usuario")
    .agg(prom=("duracion_horas", "mean"), n=("id_sesion", "count"))
    .sort_values("prom", ascending=False)
)


por_semana = df.groupby("semana")["duracion_horas"].mean().sort_index()
spark = sparkline_svg(por_semana.tolist())
n_semanas = len(por_semana)

# ─────────────────────────────────────
# 4. GRÁFICA
# ─────────────────────────────────────

fig = go.Figure()

# El orden de las trazas == orden de `usuarios` (el JS depende de esto)
for u in usuarios:
    d = resumen[resumen["usuario"] == u]
    fig.add_trace(go.Scatter(
        x=d["semana"],
        y=d["duracion_promedio"],
        name=u,
        mode="lines+markers",
        connectgaps=True,
        line=dict(color=color_de[u], width=2.5),
        fill="none",
        fillcolor=hex_rgba(color_de[u], 0.12),
        marker=dict(size=7),
        customdata=d[["semana_label", "ses_texto", "dur_texto"]].values,
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            "Semana del %{customdata[0]}<br>"
            "Promedio: %{customdata[2]}<br>"
            "%{customdata[1]}"
            "<extra></extra>"
        ),
    ))

fig.add_hline(
    y=promedio_general,
    line=dict(color="#9AA9C7", width=1.5, dash="dot"),
    annotation_text=f"Promedio general: {fmt_horas(promedio_general)}",
    annotation_position="top left",
    annotation_font_size=11,
    annotation_bgcolor="rgba(255,255,255,.85)",
)

semanas = sorted(pd.to_datetime(resumen["semana"].unique()))
paso = max(1, math.ceil(len(semanas) / 8))
marcas = semanas[::paso]
tick_vals = [d.strftime("%Y-%m-%d") for d in marcas]
tick_text = [f"{d.day} {MESES[d.month - 1]} {str(d.year)[2:]}" for d in marcas]

fig.update_layout(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
              color="#5B6A8A", size=12),
    hovermode="closest",
    hoverdistance=40,
    showlegend=False,
    margin=dict(l=10, r=16, t=28, b=10),
    height=440,
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#DCE4F5",
                    font=dict(color="#1E2A4A")),
    xaxis=dict(showgrid=False, tickmode="array", tickvals=tick_vals,
               ticktext=tick_text, automargin=True),
    yaxis=dict(title="Horas promedio por sesión", rangemode="tozero",
               gridcolor="#E6ECF8", zeroline=False, automargin=True),
)

chart_html = fig.to_html(
    full_html=False,
    include_plotlyjs=True,  # usa "cdn" para un HTML más ligero
    div_id="grafica",
    config={"responsive": True, "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]},
)


# ─────────────────────────────────────
# 5. LISTA DE USUARIOS (leyenda + filtro)
# ─────────────────────────────────────

filas_usuarios = "".join(
    f"""
    <li>
      <button type="button" class="user-row" data-user="{html.escape(u, quote=True)}"
              data-avg="{r['prom']:.4f}" data-n="{int(r['n'])}" aria-pressed="false">
        <span class="dot" style="background:{color_de[u]}"></span>
        <span class="user-name">{html.escape(u)}</span>
        <span class="user-avg">{fmt_horas(r['prom'])}</span>
      </button>
    </li>"""
    for u, r in stats.iterrows()
)

buscador = (
    '<input id="userSearch" type="search" placeholder="Buscar usuario" '
    'aria-label="Buscar usuario">'
    if len(usuarios) > 8 else ""
)

avisos = []
if sesiones_abiertas:
    avisos.append(f"{sesiones_abiertas:,} sesiones siguen abiertas y no se incluyen.")
if sesiones_largas:
    avisos.append(f"{sesiones_largas:,} sesiones duran más de "
                  f"{UMBRAL_SESION_LARGA_H} h y pueden subir el promedio.")
nota_datos = (
    '<div class="note" role="note">' + " ".join(avisos) + "</div>" if avisos else ""
)


# ─────────────────────────────────────
# 6. PLANTILLA HTML
# ─────────────────────────────────────

PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sesiones del punto de venta</title>
<style>
:root {
  --bg: #F4F7FD;
  --card: #FFFFFF;
  --ink: #1E2A4A;
  --muted: #5B6A8A;
  --line: #DCE4F5;
  --accent: #6495ED;       /* cornflower */
  --accent-strong: #3F68C4; /* para texto sobre blanco (mejor contraste) */
  --accent-soft: #E8EFFC;
  --warn-bg: #FFF6E5;
  --warn-line: #F4D9A6;
  --warn-ink: #7A4B0A;
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
.kpi-value { font-size: clamp(24px, 2.6vw, 32px); font-weight: 700; letter-spacing: -0.8px; line-height: 1.15; }

.hero {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 24px;
  padding: 26px 28px; border: 0; color: #0F1D40;
  background: linear-gradient(135deg, #6495ED 0%, #82AAF4 100%);
  box-shadow: 0 10px 30px -12px rgba(100, 149, 237, .7);
}
.hero .kpi-label { color: #1E2A4A; opacity: .8; font-size: 14px; }
.hero-value { font-size: clamp(36px, 5vw, 58px); font-weight: 750; letter-spacing: -2px; line-height: 1.05; }
.hero-sub { font-size: 13.5px; margin-top: 8px; opacity: .8; }
.spark { flex: 1; min-width: 140px; max-width: 300px; }
.spark svg { width: 100%; height: auto; display: block; overflow: visible; }
.spark-cap { display: block; font-size: 12px; opacity: .8; text-align: right; margin-top: 6px; }

.note {
  background: var(--warn-bg); border: 1px solid var(--warn-line); color: var(--warn-ink);
  border-radius: 12px; padding: 11px 16px; font-size: 13.5px; margin-bottom: 18px;
}

.main-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start; }

.panel { padding: 22px 22px 12px; }
.panel h2, .users h2 { font-size: 17px; margin: 0 0 12px; letter-spacing: -0.2px; }

.selection-bar {
  display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  background: var(--accent-soft); border-radius: 10px; padding: 8px 14px;
  font-size: 13.5px; margin-bottom: 8px; min-height: 40px;
}
.link-btn { background: none; border: 0; color: var(--accent-strong); font-weight: 600; font-size: 13.5px; cursor: pointer; padding: 4px 6px; }
.link-btn[hidden] { display: none; }

.users { padding: 20px 12px 12px; }
.users h2 { margin-left: 8px; }
#userSearch {
  width: calc(100% - 8px); margin: 0 4px 8px; padding: 9px 12px; font-size: 13.5px;
  border: 1px solid var(--line); border-radius: 9px; background: var(--card); color: var(--ink);
}
.user-list { list-style: none; margin: 0; padding: 0; max-height: 440px; overflow-y: auto; }
.user-row {
  width: 100%; display: grid; grid-template-columns: 12px 1fr auto; column-gap: 10px;
  align-items: center; text-align: left; border: 1px solid transparent; background: none;
  color: inherit; font: inherit; padding: 10px; border-radius: 10px; cursor: pointer;
}
.user-row:hover { background: var(--bg); }
.user-row[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.user-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-avg { font-size: 13.5px; color: var(--muted); }
.empty { color: var(--muted); font-size: 13.5px; padding: 10px; margin: 0; }

@media (max-width: 960px) {
  .side-kpis { grid-template-columns: 1fr 1fr; }
  .main-grid { grid-template-columns: 1fr; }
  .user-list { max-height: 340px; }
}
@media (max-width: 620px) {
  .container { padding: 20px 14px 28px; }
  .kpis { grid-template-columns: 1fr; }
  .hero { flex-direction: column; align-items: flex-start; padding: 22px 20px; }
  .spark { width: 100%; max-width: none; }
  .panel { padding: 18px 12px 10px; }
}
@media (prefers-reduced-motion: no-preference) {
  .user-row { transition: background .15s, border-color .15s; }
}
</style>
</head>

<body>
<main class="container">

  <h1>Sesiones del punto de venta</h1>
  <p class="subtitle">Duración de las sesiones de caja, semana a semana.</p>

  <section class="kpis" aria-label="Resumen general">
    <article class="card hero">
      <div>
        <div class="kpi-label">Duración promedio</div>
        <div class="hero-value" data-count="__PROMEDIO_NUM__" data-fmt="h">__PROMEDIO__</div>
        <div class="hero-sub">por sesión, en __NSEM__ semanas</div>
      </div>
      <div class="spark">__SPARK__<span class="spark-cap">Promedio semanal</span></div>
    </article>
    <div class="side-kpis">
      <article class="card kpi">
        <div class="kpi-label">Sesiones analizadas</div>
        <div class="kpi-value" data-count="__SESIONES_NUM__" data-fmt="int">__SESIONES__</div>
      </article>
      <article class="card kpi">
        <div class="kpi-label">Usuarios</div>
        <div class="kpi-value" data-count="__USUARIOS_NUM__" data-fmt="int">__USUARIOS__</div>
      </article>
    </div>
  </section>

  __NOTA__

  <div class="main-grid">

    <section class="card panel" aria-labelledby="t-evolucion">
      <h2 id="t-evolucion">Evolución semanal</h2>

      <div class="selection-bar" aria-live="polite">
        <span id="selectionText">Todos los usuarios</span>
        <button class="link-btn" id="clearBtn" type="button" hidden>Quitar selección</button>
      </div>

      <div role="img" aria-label="Gráfica de líneas con la duración promedio semanal por usuario">
        __GRAFICA__
      </div>
    </section>

    <aside class="card users" aria-labelledby="t-usuarios">
      <h2 id="t-usuarios">Usuarios</h2>
      __BUSCADOR__
      <ul class="user-list">__FILAS__</ul>
      <p class="empty" id="noResults" hidden>Ningún usuario coincide.</p>
    </aside>

  </div>
</main>

<script>
const GRAFICA = "grafica";
const usersInTraceOrder = __USUARIOS_JSON__;
const rows = Array.from(document.querySelectorAll(".user-row"));
const selected = new Set();
const selectionText = document.getElementById("selectionText");
const clearBtn = document.getElementById("clearBtn");

function fmtH(h) {
  let H = Math.floor(h), M = Math.round((h - H) * 60);
  if (M === 60) { H += 1; M = 0; }
  return H + " h " + String(M).padStart(2, "0") + " min";
}

function paint() {
  const any = selected.size > 0;

  Plotly.restyle(GRAFICA, {
    opacity: usersInTraceOrder.map(u => !any || selected.has(u) ? 1 : 0.12),
    "line.width": usersInTraceOrder.map(u => !any ? 2.5 : (selected.has(u) ? 3.5 : 1.5)),
    fill: usersInTraceOrder.map(u => any && selected.has(u) ? "tozeroy" : "none")
  });

  rows.forEach(r => r.setAttribute("aria-pressed", selected.has(r.dataset.user)));

  if (!any) {
    selectionText.textContent = "Todos los usuarios";
  } else {
    let sum = 0, n = 0;
    rows.forEach(r => {
      if (selected.has(r.dataset.user)) {
        sum += parseFloat(r.dataset.avg) * parseInt(r.dataset.n);
        n += parseInt(r.dataset.n);
      }
    });
    const quien = selected.size === 1 ? Array.from(selected)[0] : selected.size + " usuarios";
    selectionText.textContent =
      quien + ": " + fmtH(sum / n) + " en promedio (" + n.toLocaleString("en-US") + " sesiones)";
  }
  clearBtn.hidden = !any;
}

rows.forEach(r => r.addEventListener("click", () => {
  const u = r.dataset.user;
  selected.has(u) ? selected.delete(u) : selected.add(u);
  paint();
}));

clearBtn.addEventListener("click", () => { selected.clear(); paint(); });

const search = document.getElementById("userSearch");
if (search) {
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let visibles = 0;
    rows.forEach(r => {
      const show = r.dataset.user.toLowerCase().includes(q);
      r.parentElement.hidden = !show;
      if (show) visibles++;
    });
    document.getElementById("noResults").hidden = visibles > 0;
  });
}

// Un solo momento animado: los números cuentan hasta su valor al cargar
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.querySelectorAll("[data-count]").forEach(el => {
    const target = parseFloat(el.dataset.count), kind = el.dataset.fmt;
    const show = v => el.textContent = kind === "h" ? fmtH(v) : Math.round(v).toLocaleString("en-US");
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
    "__PROMEDIO__": fmt_horas(promedio_general),
    "__SESIONES__": f"{total_sesiones:,}",
    "__USUARIOS__": f"{total_usuarios:,}",
    "__PROMEDIO_NUM__": f"{promedio_general:.4f}",
    "__SESIONES_NUM__": str(total_sesiones),
    "__USUARIOS_NUM__": str(total_usuarios),
    "__NSEM__": str(n_semanas),
    "__SPARK__": spark,
    "__NOTA__": nota_datos,
    "__BUSCADOR__": buscador,
    "__FILAS__": filas_usuarios,
    "__USUARIOS_JSON__": json.dumps(usuarios, ensure_ascii=False),
    "__GRAFICA__": chart_html,  # al final: el bundle de Plotly es enorme
}

documento = PLANTILLA
for clave, valor in reemplazos.items():
    documento = documento.replace(clave, valor)



# ─────────────────────────────────────
# 7. GUARDAR EL HTML
# ─────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

salida = OUTPUT_DIR / "sesiones.html"
salida.write_text(documento, encoding="utf-8")

print(f"Dashboard generado: {salida}")
print(f"Sesiones analizadas: {total_sesiones:,}")
print(f"Usuarios: {total_usuarios:,}")
print(f"Duración promedio: {fmt_horas(promedio_general)}")

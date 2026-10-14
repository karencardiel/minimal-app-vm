from dash import Dash, html, dcc, Input, Output
from sqlalchemy import create_engine, text
import pandas as pd
import plotly.express as px

# Connect to PostgreSQL
engine = create_engine(
    "postgresql+psycopg2://karen@localhost:5432/Viz2026"
)

# Get data directly from the database
query = text("""
    SELECT
        EXTRACT(MONTH FROM "Fecha") AS mes,
        FLOOR((EXTRACT(DAY FROM "Fecha") - 1) / 7) + 1 AS semana,
        "Responsable",
        SUM("Total") AS importe_total
    FROM ordenes_punto_venta
    WHERE EXTRACT(YEAR FROM "Fecha") = 2026
    GROUP BY mes, semana, "Responsable"
    ORDER BY mes, semana, "Responsable";
""")

with engine.connect() as connection:
    df = pd.read_sql(query, connection)

df["mes"] = df["mes"].astype(int)
df["semana"] = df["semana"].astype(int)

months = {
    1: "January", 2: "February", 3: "March",
    4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September",
    10: "October", 11: "November", 12: "December"
}

# ─────────────────────────────────────
# DESIGN: paleta basada en Cornflower (#6495ED)
# ─────────────────────────────────────

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

CSS = """
:root {
  --bg: #F4F7FD; --card: #FFFFFF; --ink: #1E2A4A; --muted: #5B6A8A;
  --line: #DCE4F5; --accent: #6495ED; --accent-soft: #E8EFFC;
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
h1 { font-size: clamp(24px, 3vw, 32px); letter-spacing: -0.7px; margin: 0 0 22px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; }
.panel { padding: 22px 22px 12px; }
.field-label { display: block; font-size: 13.5px; color: var(--muted); margin-bottom: 6px; }
.dropdown { max-width: 280px; margin-bottom: 8px; }

/* Dropdown de Dash (react-select) */
.dropdown .Select-control { border: 1px solid var(--line); border-radius: 10px; }
.dropdown .Select.is-focused > .Select-control,
.dropdown .Select-control:hover { border-color: var(--accent); box-shadow: none; }
.dropdown .Select-menu-outer { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.dropdown .Select-option.is-focused { background: var(--accent-soft); }
.dropdown .Select-option.is-selected { background: var(--accent); color: #fff; }

@media (max-width: 620px) {
  .container { padding: 20px 14px 28px; }
  .panel { padding: 18px 12px 10px; }
}
"""

app = Dash(__name__, title="Sales by Month, Week and Responsible Person")
app.index_string = (
    """<!DOCTYPE html>
<html lang="en">
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>"""
    + CSS
    + """</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""
)


def aplicar_estilo(fig):
    """Mismo estilo para la gráfica normal y la vacía."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
                  color="#5B6A8A", size=12),
        title=dict(font=dict(size=17, color="#1E2A4A"), x=0.01),
        margin=dict(l=10, r=10, t=60, b=10),
        bargap=0.28,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#DCE4F5",
                        font=dict(color="#1E2A4A")),
        legend=dict(orientation="v", yanchor="top", y=1,
                    xanchor="left", x=1.02),
    )
    fig.update_xaxes(showgrid=False, automargin=True)
    fig.update_yaxes(gridcolor="#E6ECF8", zeroline=False, automargin=True,
                     tickprefix="$", tickformat=",.0f")
    return fig


app.layout = html.Main(
    className="container",
    children=[
        html.H1("Sales by Month, Week and Responsible Person"),

        html.Div(
            className="card panel",
            children=[
                html.Label("Select month:", htmlFor="month-dropdown",
                           className="field-label"),

                dcc.Dropdown(
                    id="month-dropdown",
                    className="dropdown",
                    options=[{"label": "All months", "value": "all"}] + [
                        {"label": months[m], "value": m}
                        for m in sorted(df["mes"].unique())
                    ],
                    value=int(df["mes"].min()) if not df.empty else None,
                    clearable=True
                ),

                dcc.Graph(id="sales-chart", config={"displaylogo": False})
            ]
        )
    ]
)


@app.callback(
    Output("sales-chart", "figure"),
    Input("month-dropdown", "value")
)
def update_chart(selected_month):
    # "All months" (o dropdown vacío): una barra por mes en lugar de por semana
    if selected_month in (None, "all"):
        by_month = (
            df.groupby(["mes", "Responsable"], as_index=False)["importe_total"].sum()
        )
        by_month["mes_nombre"] = by_month["mes"].map(months)

        fig = px.bar(
            by_month,
            x="mes_nombre",
            y="importe_total",
            color="Responsable",
            barmode="group",
            title="Total Sales by Month and Responsible Person",
            labels={
                "mes_nombre": "Month",
                "importe_total": "Total Amount",
                "Responsable": "Responsible Person"
            },
            category_orders={
                "mes_nombre": [months[m] for m in sorted(df["mes"].unique())]
            },
            color_discrete_sequence=PALETA
        )
        fig.update_layout(
            xaxis=dict(type="category"),
            legend_title="Responsible Person"
        )
        return aplicar_estilo(fig)

    filtered_df = df.copy()

    if selected_month is not None:
        filtered_df = filtered_df[
            filtered_df["mes"] == selected_month
        ]

    if filtered_df.empty:
        return aplicar_estilo(px.bar(title="No data available for this month"))

    fig = px.bar(
        filtered_df,
        x="semana",
        y="importe_total",
        color="Responsable",
        barmode="group",
        title="Total Sales by Week and Responsible Person",
        labels={
            "semana": "Week of the Month",
            "importe_total": "Total Amount",
            "Responsable": "Responsible Person"
        },
        category_orders={
            "semana": [1, 2, 3, 4, 5]
        },
        color_discrete_sequence=PALETA
    )

    fig.update_layout(
        xaxis=dict(type="category"),
        legend_title="Responsible Person"
    )

    return aplicar_estilo(fig)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
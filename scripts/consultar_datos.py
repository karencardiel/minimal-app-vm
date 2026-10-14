
from sqlalchemy import create_engine, text
import pandas as pd

# Connect to the database
engine = create_engine(
    "postgresql+psycopg2://karen@localhost:5432/Viz2026"
)

# Query: total amount by month, week and responsible person
query = text("""
    SELECT
        EXTRACT(MONTH FROM "Fecha") AS mes,
        FLOOR((EXTRACT(DAY FROM "Fecha") - 1) / 7) + 1 AS semana,
        "Responsable",
        SUM("Total") AS importe_total
    FROM ordenes_punto_venta
    WHERE EXTRACT(YEAR FROM "Fecha") = 2026
    GROUP BY
        mes,
        semana,
        "Responsable"
    ORDER BY
        mes,
        semana,
        "Responsable";
""")

# Execute the query and save results in a DataFrame
with engine.connect() as connection:
    df = pd.read_sql(query, connection)

print(df.head(20))
print("\nTotal rows:", len(df))

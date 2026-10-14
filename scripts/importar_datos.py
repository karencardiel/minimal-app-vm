
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
import unicodedata

# Connect to PostgreSQL
engine = create_engine(
    "postgresql+psycopg2://karen@localhost:5432/Viz2026"
)

# Excel folder
folder = Path("data")

# Names of the Excel files and their SQL tables
files = {
    "Tabla dinámica Análisis de Punto de venta (report.pos.order)(4).xlsx":
        "tabla_dinamica_analisis_punto_venta",

    "Sesión de Punto de venta (pos.session).xlsx":
        "sesion_punto_venta",

    "Pagos en Punto de venta (pos.payment)(1).xlsx":
        "pagos_punto_venta",

    "Órdenes del Punto de venta (pos.order)(2).xlsx":
        "ordenes_punto_venta"
}

# Import each file into its corresponding table
for filename, table_name in files.items():
    filepath = folder / filename

    if not filepath.exists():
        print(f"File not found: {filepath}")
        continue

    df = pd.read_excel(filepath)

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="replace",
        index=False
    )

    print(f"Imported: {filename}")
    print(f"Table: {table_name}")
    print(f"Rows: {len(df)}")
    print("-" * 40)

print("Import process finished!")

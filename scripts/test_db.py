
from sqlalchemy import create_engine, text

engine = create_engine(
    "postgresql+psycopg2://karen@localhost:5432/Viz2026"
)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT current_database()"))
        print("Connected to database:", result.scalar())
except Exception as error:
    print("Connection error:", error)

# POS Sales Dashboard

This project contains three interactive visualizations for point-of-sale data: **orders, payments, and sessions**. It uses Python, Plotly, and Dash to explore the data, with a PostgreSQL connection to retrieve information from SQL tables.

## How to Run

1. Install the required libraries:

   ```bash
   pip install -r requirements.txt
   ```

2. Make sure PostgreSQL is running and the database connection is configured correctly.

3. Generate the three visualizations:

   ```bash
   python3 dashboard/ordenes.py
   python3 dashboard/pagos.py
   python3 dashboard/sesiones.py
   ```

4. Run the main dashboard:

   ```bash
   python3 dashboard/app.py
   ```

5. Open http://127.0.0.1:8050/ in your browser.

The project requires access to the database and its corresponding tables to display the visualizations.

import sqlite3


connection = sqlite3.connect(
    "data/orbitx_shipments.db"
)

cursor = connection.cursor()

cursor.execute(
    """
    SELECT
        tracking_id,
        status,
        current_location,
        current_lat,
        current_lon
    FROM shipments
    WHERE tracking_id = ?
    """,
    ("OX10452",),
)

shipment = cursor.fetchone()

print(shipment)

connection.close()
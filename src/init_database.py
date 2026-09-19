import os
import sqlite3


DATABASE_PATH = "data/orbitx_shipments.db"


shipments = [
    (
        "OX10451",
        "Nasr City, Cairo",
        30.0566,
        31.3301,
        "Dokki, Giza",
        30.0384,
        31.2122,
        "Same-Day",
        "Delivered",
        "Dokki Delivery Station",
        30.0384,
        31.2122,
        "2026-09-17",
        "2026-09-17 16:25",
        1,
        "Delivered successfully.",
    ),
    (
        "OX10452",
        "New Cairo, Cairo",
        30.0074,
        31.4913,
        "Heliopolis, Cairo",
        30.0910,
        31.3220,
        "Express",
        "Out for Delivery",
        "Heliopolis Delivery Station",
        30.0865,
        31.3300,
        "2026-09-19",
        "2026-09-19 10:42",
        0,
        "Courier route assigned for final delivery.",
    ),
    (
        "OX10453",
        "Alexandria",
        31.2001,
        29.9187,
        "Maadi, Cairo",
        29.9602,
        31.2569,
        "Standard",
        "In Transit",
        "Cairo North Transit Hub",
        30.1300,
        31.2450,
        "2026-09-20",
        "2026-09-19 00:35",
        0,
        "Shipment is moving toward the destination hub.",
    ),
    (
        "OX10454",
        "Cairo",
        30.0444,
        31.2357,
        "Dubai",
        25.2048,
        55.2708,
        "International",
        "Customs Clearance",
        "Dubai Customs Facility",
        25.2532,
        55.3657,
        "2026-09-23",
        "2026-09-19 08:10",
        0,
        "Shipment is under customs processing.",
    ),
    (
        "OX10455",
        "Giza",
        30.0131,
        31.2089,
        "New Cairo, Cairo",
        30.0074,
        31.4913,
        "Express",
        "Delivery Attempt Failed",
        "New Cairo Delivery Station",
        30.0125,
        31.4800,
        "2026-09-20",
        "2026-09-19 15:40",
        1,
        "Recipient was unavailable during the first delivery attempt.",
    ),
]


def create_database():

    os.makedirs(
        "data",
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        DROP TABLE IF EXISTS shipments
        """
    )

    cursor.execute(
        """
        CREATE TABLE shipments (
            tracking_id TEXT PRIMARY KEY,
            origin TEXT NOT NULL,
            origin_lat REAL NOT NULL,
            origin_lon REAL NOT NULL,
            destination TEXT NOT NULL,
            destination_lat REAL NOT NULL,
            destination_lon REAL NOT NULL,
            service TEXT NOT NULL,
            status TEXT NOT NULL,
            current_location TEXT,
            current_lat REAL,
            current_lon REAL,
            expected_delivery TEXT,
            last_update TEXT,
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        )
        """
    )

    cursor.executemany(
        """
        INSERT INTO shipments (
            tracking_id,
            origin,
            origin_lat,
            origin_lon,
            destination,
            destination_lat,
            destination_lon,
            service,
            status,
            current_location,
            current_lat,
            current_lon,
            expected_delivery,
            last_update,
            delivery_attempts,
            notes
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        shipments,
    )

    connection.commit()

    connection.close()


def main():

    create_database()

    print(
        "OrbitX shipment database created successfully."
    )

    print(
        f"Loaded {len(shipments)} demo shipments."
    )


if __name__ == "__main__":
    main()
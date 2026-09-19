import json
import sqlite3

import requests
from langchain_core.tools import tool

from src.config import (
    DATABASE_PATH,
    ORS_API_KEY,
)
from src.reranker import (
    create_reranker,
    rerank_documents,
)
from src.retrieval import retrieve_documents


ranker = create_reranker()


def get_shipment_record(tracking_id: str):

    tracking_id = tracking_id.strip().upper()

    with sqlite3.connect(DATABASE_PATH) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
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
            FROM shipments
            WHERE tracking_id = ?
            """,
            (tracking_id,),
        )

        shipment = cursor.fetchone()

    if shipment is None:
        return None

    return {
        "tracking_id": shipment[0],
        "origin": shipment[1],
        "origin_lat": shipment[2],
        "origin_lon": shipment[3],
        "destination": shipment[4],
        "destination_lat": shipment[5],
        "destination_lon": shipment[6],
        "service": shipment[7],
        "status": shipment[8],
        "current_location": shipment[9],
        "current_lat": shipment[10],
        "current_lon": shipment[11],
        "expected_delivery": shipment[12],
        "last_update": shipment[13],
        "delivery_attempts": shipment[14],
        "notes": shipment[15],
    }


@tool
def search_knowledge_base(query: str) -> str:
    """Search OrbitX policies, services, delivery rules, and support information."""

    documents = retrieve_documents(query)

    reranked_documents = rerank_documents(
        query,
        documents,
        ranker,
    )

    results = []

    for document in reranked_documents:

        page = document.metadata.get(
            "page",
            0,
        )

        results.append(
            f"[Source: page {page + 1}]\n"
            f"{document.page_content}"
        )

    return "\n\n".join(results)


@tool
def track_shipment(tracking_id: str) -> str:
    """Track an OrbitX shipment using its tracking ID."""

    try:

        shipment = get_shipment_record(
            tracking_id
        )

    except sqlite3.Error:

        return (
            "The shipment database is "
            "currently unavailable."
        )

    if shipment is None:

        return (
            f"No shipment was found with tracking ID "
            f"{tracking_id.strip().upper()}."
        )

    result = {
        "tracking_id": shipment["tracking_id"],
        "origin": shipment["origin"],
        "destination": shipment["destination"],
        "service": shipment["service"],
        "status": shipment["status"],
        "current_location": shipment["current_location"],
        "expected_delivery": shipment["expected_delivery"],
        "last_update": shipment["last_update"],
        "delivery_attempts": shipment["delivery_attempts"],
        "notes": shipment["notes"],
    }

    return json.dumps(
        result,
        indent=2,
    )


def geocode_location(
    location: str,
    country_hint: str | None = None,
):

    search_text = location

    if country_hint:

        search_text = (
            f"{location}, {country_hint}"
        )

    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )

    headers = {
        "Authorization": ORS_API_KEY
    }

    params = {
        "text": search_text,
        "size": 1,
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    features = data.get(
        "features",
        [],
    )

    if not features:
        return None

    return features[0][
        "geometry"
    ]["coordinates"]


def get_route_details(
    origin_coordinates,
    destination_coordinates,
):

    url = (
        "https://api.heigit.org/"
        "openrouteservice/v2/directions/"
        "driving-car/geojson"
    )

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/geo+json",
    }

    body = {
        "coordinates": [
            origin_coordinates,
            destination_coordinates,
        ]
    }

    response = requests.post(
        url,
        headers=headers,
        json=body,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    feature = data[
        "features"
    ][0]

    summary = feature[
        "properties"
    ]["summary"]

    route_path = feature[
        "geometry"
    ]["coordinates"]

    distance_km = (
        summary["distance"] / 1000
    )

    duration_minutes = (
        summary["duration"] / 60
    )

    if len(route_path) > 300:

        step = max(
            1,
            len(route_path) // 300,
        )

        route_path = route_path[
            ::step
        ]

    return {
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "route_path": route_path,
    }


def get_shipment_map_data(
    tracking_id: str,
):

    if not ORS_API_KEY:
        return None

    try:

        shipment = get_shipment_record(
            tracking_id
        )

    except sqlite3.Error:

        return None

    if shipment is None:
        return None

    origin_coordinates = [
        shipment["origin_lon"],
        shipment["origin_lat"],
    ]

    destination_coordinates = [
        shipment["destination_lon"],
        shipment["destination_lat"],
    ]

    current_coordinates = None

    if (
        shipment["current_lat"] is not None
        and shipment["current_lon"] is not None
    ):

        current_coordinates = [
            shipment["current_lon"],
            shipment["current_lat"],
        ]

    route_path = []

    distance_km = None
    duration_minutes = None

    if (
        shipment["service"].lower()
        != "international"
    ):

        try:

            route = get_route_details(
                origin_coordinates,
                destination_coordinates,
            )

            route_path = route[
                "route_path"
            ]

            distance_km = route[
                "distance_km"
            ]

            duration_minutes = route[
                "duration_minutes"
            ]

        except (
            requests.RequestException,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):

            route_path = [
                origin_coordinates,
                destination_coordinates,
            ]

    else:

        route_path = [
            origin_coordinates,
            destination_coordinates,
        ]

    points = [
        {
            "name": "Origin",
            "location": shipment["origin"],
            "coordinates": origin_coordinates,
            "color": [15, 23, 42],
        },
        {
            "name": "Destination",
            "location": shipment["destination"],
            "coordinates": destination_coordinates,
            "color": [37, 99, 235],
        },
    ]

    if current_coordinates:

        points.append(
            {
                "name": "Latest recorded location",
                "location": shipment[
                    "current_location"
                ],
                "coordinates": current_coordinates,
                "color": [14, 165, 233],
            }
        )

    return {
        "points": points,
        "route_path": route_path,
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
    }


@tool
def estimate_delivery_quote(
    origin: str,
    destination: str,
    weight_kg: float,
    service_type: str,
    insurance: bool = False,
    declared_value: float = 0,
) -> str:
    """Estimate an OrbitX domestic delivery price using live route distance."""

    if not ORS_API_KEY:

        return (
            "The routing API key is not configured."
        )

    if weight_kg <= 0:

        return (
            "Shipment weight must be greater "
            "than 0 kg."
        )

    if weight_kg > 30:

        return (
            "Shipments above 30 kg require "
            "OrbitX freight support."
        )

    service = (
        service_type
        .strip()
        .lower()
        .replace("_", "-")
    )

    if service == "same day":
        service = "same-day"

    pricing = {
        "standard": {
            "base": 45,
            "extra_weight": 12,
            "distance": 0.55,
        },
        "express": {
            "base": 70,
            "extra_weight": 16,
            "distance": 0.75,
        },
        "same-day": {
            "base": 95,
            "extra_weight": 20,
            "distance": 1,
        },
    }

    if service not in pricing:

        return (
            "Service type must be Standard, "
            "Express, or Same-Day."
        )

    if insurance:

        if declared_value <= 0:

            return (
                "A declared value is required "
                "when insurance is selected."
            )

        if declared_value > 50000:

            return (
                "The maximum declared value "
                "is 50,000 EGP."
            )

    try:

        origin_coordinates = geocode_location(
            origin,
            "Egypt",
        )

        destination_coordinates = geocode_location(
            destination,
            "Egypt",
        )

        if origin_coordinates is None:

            return (
                f"Could not find the origin: "
                f"{origin}."
            )

        if destination_coordinates is None:

            return (
                f"Could not find the destination: "
                f"{destination}."
            )

        route = get_route_details(
            origin_coordinates,
            destination_coordinates,
        )

        distance_km = route[
            "distance_km"
        ]

        duration_minutes = route[
            "duration_minutes"
        ]

    except (
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):

        return (
            "The routing service is currently "
            "unavailable."
        )

    if (
        service == "same-day"
        and distance_km > 60
    ):

        return json.dumps(
            {
                "available": False,
                "service": "Same-Day",
                "distance_km": round(
                    distance_km,
                    2,
                ),
                "reason": (
                    "Same-Day delivery is only "
                    "available for routes up to 60 km."
                ),
                "recommended_service": "Express",
            },
            indent=2,
        )

    service_pricing = pricing[
        service
    ]

    base_fee = service_pricing[
        "base"
    ]

    extra_weight = max(
        0,
        weight_kg - 2,
    )

    weight_fee = (
        extra_weight
        * service_pricing[
            "extra_weight"
        ]
    )

    if service == "same-day":

        distance_fee = (
            distance_km
            * service_pricing[
                "distance"
            ]
        )

    else:

        extra_distance = max(
            0,
            distance_km - 30,
        )

        distance_fee = (
            extra_distance
            * service_pricing[
                "distance"
            ]
        )

    insurance_fee = 0

    if insurance:

        insurance_fee = max(
            20,
            declared_value * 0.02,
        )

    subtotal = (
        base_fee
        + weight_fee
        + distance_fee
    )

    total = (
        subtotal
        + insurance_fee
    )

    result = {
        "available": True,
        "origin": origin,
        "destination": destination,
        "distance_km": round(
            distance_km,
            2,
        ),
        "estimated_drive_time_minutes": round(
            duration_minutes
        ),
        "weight_kg": weight_kg,
        "service": (
            "Same-Day"
            if service == "same-day"
            else service.title()
        ),
        "insurance": insurance,
        "declared_value": declared_value,
        "price_breakdown": {
            "base_fee": round(
                base_fee,
                2,
            ),
            "extra_weight_fee": round(
                weight_fee,
                2,
            ),
            "distance_fee": round(
                distance_fee,
                2,
            ),
            "insurance_fee": round(
                insurance_fee,
                2,
            ),
            "subtotal": round(
                subtotal,
                2,
            ),
        },
        "estimated_price": round(
            total,
            2,
        ),
        "currency": "EGP",
    }

    return json.dumps(
        result,
        indent=2,
    )


TOOLS = [
    search_knowledge_base,
    track_shipment,
    estimate_delivery_quote,
]